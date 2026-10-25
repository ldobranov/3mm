"""Native self-contained application-host artifacts and per-instance updates.

Reuses the proven Runtime journal/pointer transaction. Never enables an application,
changes a wheel/active metadata/data/grant, or restarts Core/Platform Runtime.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import socket
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import time
import uuid
import venv
import zipfile

from deployment.platform_runtime_component import (
    RuntimeStore, _digest, _fsync, _id, _json, _write, core_fingerprint,
)
from three_mm_platform_wire import AUTHORITY_CONTRACT, peer_identity, read_frame, remaining
from three_mm_platform_runtime.server import probe_runtime
from three_mm_runtime.application_host_identity import HOST_CONTRACT
from three_mm_runtime.application_transport import (
    ApplicationServiceClient, read_message, send_message, sign_message, verify_message,
)

ROOT = Path("/opt/3mm-application-hosts")
STATE = Path("/var/lib/3mm-application-host-updates")
APPLICATIONS = Path("/var/lib/3mm/application-extensions")
KEYS = Path("/etc/3mm/application-extensions")
MAX_BYTES = 64 * 1024 * 1024
HOST_PROBE_SECONDS = 2
RUNTIME_FILES = (
    "__init__.py", "application_host.py", "application_host_identity.py",
    "application_transport.py", "application_file_executor.py",
    "application_relational_runtime.py", "application_relational_session.py",
    "application_relational_startup.py", "application_relational_boot_policy.py",
    "application_relational_migrations.py",
)
ENTRY = b"""import importlib.util,json,os,sys,zipfile
from pathlib import Path
base=Path(sys.argv[0]).resolve().parent
sys.path.insert(0,str(base/'vendor'))
from three_mm_runtime.application_host import main
if sys.argv[1:]==['--component-info']:
    import _cffi_backend
    import cryptography.hazmat.bindings._rust
    import three_mm_runtime.application_relational_boot_policy
    if any(importlib.util.find_spec(n) is not None for n in ('backend','sqlalchemy','fastapi')):
        raise RuntimeError('Core dependencies are visible to the application host')
    with zipfile.ZipFile(sys.argv[0]) as z: print(z.read('host-build.json').decode())
else:
    if os.geteuid()==0: raise RuntimeError('Application host requires a non-root service principal')
    main()
"""


def instance_id(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{24}", value) is None:
        raise ValueError("Application instance is invalid")
    return value


def validate_host_contract(data):
    value = json.loads(data)
    if (not isinstance(value,dict) or type(value.get("schema_version")) is not int or type(value.get("host_contract")) is not int
            or type(value.get("authority_contract")) is not int or value != {
                "schema_version": 1, "host_contract": HOST_CONTRACT, "authority_contract": AUTHORITY_CONTRACT}):
        raise ValueError("Core/application-host contracts are unsupported")
    return value


def target_identity():
    if sys.platform != "linux" or platform.python_implementation() != "CPython" or sys.version_info < (3, 12):
        raise ValueError("Build/install the native application host on Linux CPython >=3.12")
    return {"python_tag": sys.implementation.cache_tag, "platform": sysconfig.get_platform(),
            "machine": platform.machine()}


def inputs(source):
    source = Path(source)
    names = ["three_mm_runtime/" + name for name in RUNTIME_FILES]
    for package in ("three_mm_protocol", "three_mm_application_sdk", "three_mm_platform_wire"):
        names.extend(p.relative_to(source).as_posix() for p in (source / package).glob("*.py"))
    return sorted(names)


def _source_name(name):
    return (name == "__main__.py" or name in {"three_mm_runtime/" + n for n in RUNTIME_FILES}
        or (len(PurePosixPath(name).parts) == 2 and name.endswith(".py")
            and name.split('/')[0] in {"three_mm_protocol", "three_mm_application_sdk", "three_mm_platform_wire"}))


def _name(name):
    p = PurePosixPath(name)
    return (name == p.as_posix() and not p.is_absolute() and not {'..','.'} & set(p.parts)
            and not any(c in name for c in ('\\', ':', '\0')))


def _archive(metadata, files):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as bundle:
        for name, data in sorted({"component.json": _json(metadata), **files}.items()):
            info = tarfile.TarInfo(name); info.size = len(data); info.mode = 0o444; info.mtime = 0
            bundle.addfile(info, io.BytesIO(data))
    return output.getvalue()


def build_component(source):
    source = Path(source).resolve(); target = target_identity()
    validate_host_contract((source / "deployment/application-host-contract.json").read_bytes())
    code = {}
    for name in inputs(source):
        path = source / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source):
            raise ValueError("Host source must be a regular repository file")
        code[name] = path.read_bytes().replace(b"\r\n", b"\n")
    code['__main__.py'] = ENTRY
    vendor = {}; versions = {}
    for line in (source / "deployment/application-host-requirements.txt").read_text().splitlines():
        name, version = line.split('=='); distribution = importlib.metadata.distribution(name)
        if distribution.version != version:
            raise ValueError("Host builder environment differs from its dependency lock: " + name)
        versions[name] = version
        for item in distribution.files or ():
            name = item.as_posix()
            if name.endswith('.pyc') or '__pycache__' in item.parts: continue
            if item.parts[:4] == ('..','..','..','bin'): continue  # Build-time console scripts are not worker imports.
            if not _name(name): raise ValueError("Host dependency escapes its package root")
            path = Path(distribution.locate_file(item))
            if path.is_symlink() or not path.is_file(): raise ValueError("Host dependency must be regular")
            data = path.read_bytes(); destination = 'vendor/' + name
            if destination in vendor and vendor[destination] != data: raise ValueError("Dependency file collision")
            vendor[destination] = data
    binding = {"host_contract": HOST_CONTRACT, "authority_contract": AUTHORITY_CONTRACT,
        "target": target, "dependencies": versions,
        "sources": {n:_digest(v) for n,v in code.items()},
        "vendor": {n:_digest(v) for n,v in vendor.items()}}
    identifier = _digest(_json(binding))
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, data in sorted({**code, 'host-build.json': _json({
                'build_id':identifier,'host_contract':HOST_CONTRACT,'authority_contract':AUTHORITY_CONTRACT})}.items()):
            info=zipfile.ZipInfo(name,(2026,1,1,0,0,0));info.create_system=3
            info.external_attr=0o100444<<16;info.compress_type=zipfile.ZIP_DEFLATED;bundle.writestr(info,data)
    files = {'host.pyz':output.getvalue(), **vendor}
    metadata = {"schema_version":1,"component":"application-host","build_id":identifier,
        "binding":binding,"files":{n:_digest(v) for n,v in files.items()}}
    blob = _archive(metadata, files)
    validate_artifact(blob, _digest(blob))
    return blob, metadata


def validate_artifact(blob, expected):
    if len(blob)>MAX_BYTES or not _id(expected) or _digest(blob)!=expected:
        raise ValueError("Host archive size/digest is invalid")
    files = {}; total = 0
    with tarfile.open(fileobj=io.BytesIO(blob),mode='r:') as bundle:
        for item in bundle:
            if (not item.isfile() or not _name(item.name) or item.name in files
                    or item.size>MAX_BYTES or len(files)>=2048):
                raise ValueError("Host archive contains unsupported paths/files")
            total += item.size
            if total>MAX_BYTES: raise ValueError("Host archive exceeds its budget")
            files[item.name] = bundle.extractfile(item).read(item.size+1)
    if 'component.json' not in files or len(files['component.json'])>512*1024:
        raise ValueError("Host manifest is missing/oversized")
    metadata=json.loads(files.pop('component.json'))
    if not isinstance(metadata,dict) or not isinstance(metadata.get('binding'),dict):
        raise ValueError('Host manifest must be an object')
    binding=metadata['binding']
    if (set(metadata)!={'schema_version','component','build_id','binding','files'}
            or type(metadata['schema_version']) is not int or metadata['schema_version']!=1
            or metadata['component']!='application-host' or not _id(metadata['build_id'])
            or set(binding)!={'host_contract','authority_contract','target','dependencies','sources','vendor'}
            or type(binding['host_contract']) is not int or binding['host_contract']!=HOST_CONTRACT
            or type(binding['authority_contract']) is not int or binding['authority_contract']!=AUTHORITY_CONTRACT
            or binding['target']!=target_identity() or _digest(_json(binding))!=metadata['build_id']
            or metadata['files']!={n:_digest(v) for n,v in files.items()}
            or set(files)!={'host.pyz',*binding['vendor']}
            or any(not n.startswith('vendor/') for n in binding['vendor'])
            or binding['vendor']!={n:_digest(files[n]) for n in binding['vendor']}
            or not binding['sources'] or any(not _source_name(n) for n in binding['sources'])):
        raise ValueError("Host artifact contract/target/payload is unsupported")
    with zipfile.ZipFile(io.BytesIO(files['host.pyz'])) as bundle:
        names=bundle.namelist()
        if (set(names)!={*binding['sources'],'host-build.json'} or len(names)!=len(set(names))
                or any(i.is_dir() or i.file_size>MAX_BYTES or (i.external_attr>>16)&0o170000 != 0o100000 for i in bundle.infolist())
                or sum(i.file_size for i in bundle.infolist())>MAX_BYTES):
            raise ValueError("Host executable payload is invalid")
        if (binding['sources']!={n:_digest(bundle.read(n)) for n in binding['sources']}
                or json.loads(bundle.read('host-build.json'))!={'build_id':metadata['build_id'],
                    'host_contract':HOST_CONTRACT,'authority_contract':AUTHORITY_CONTRACT}):
            raise ValueError("Host executable identity changed")
    return metadata, files


class HostStore(RuntimeStore):
    def __init__(self, root, state, releases):
        super().__init__(root,state)
        self.releases=Path(releases);self.releases.mkdir(parents=True,exist_ok=True,mode=0o755)
        if self.releases.is_symlink(): raise ValueError("Host releases cannot be symlinked")

    def metadata(self, identifier):
        if not _id(identifier): raise ValueError("Host build ID is invalid")
        directory=self.releases/identifier
        artifact=directory/'artifact.tar'
        if directory.is_symlink() or not directory.is_dir() or artifact.is_symlink() or artifact.stat().st_size>MAX_BYTES:
            raise ValueError("Immutable host artifact is unavailable")
        blob=artifact.read_bytes();metadata,files=validate_artifact(blob,_digest(blob))
        if metadata['build_id']!=identifier: raise ValueError("Host pointer identity changed")
        for name,data in {'component.json':_json(metadata),**files}.items():
            path=directory/name
            if path.is_symlink() or not path.is_file() or path.stat().st_size!=len(data) or _digest(path.read_bytes())!=_digest(data):
                raise ValueError("Installed host payload changed")
        return metadata

    def stage(self, blob, sha256):
        metadata,files=validate_artifact(blob,sha256);identifier=metadata['build_id'];target=self.releases/identifier
        if target.exists() or target.is_symlink():
            if self.metadata(identifier)!=metadata or not (target/'.venv/bin/python').is_file():
                raise ValueError("Existing host environment is incomplete")
            return identifier
        temporary=Path(tempfile.mkdtemp(prefix='.stage-',dir=self.releases));temporary.chmod(0o755)
        try:
            for name,data in {'artifact.tar':blob,'component.json':_json(metadata),**files}.items():
                path=temporary/name;path.parent.mkdir(parents=True,exist_ok=True);_write(path,data,0o444)
            venv.EnvBuilder(with_pip=False,symlinks=True).create(temporary/'.venv')
            credentials={}
            if os.geteuid()==0:
                import pwd
                user=pwd.getpwnam('3mm-app')
                credentials={'user':user.pw_uid,'group':user.pw_gid,'extra_groups':[]}
            result=subprocess.run([str(temporary/'.venv/bin/python'),'-I',str(temporary/'host.pyz'),'--component-info'],
                cwd=temporary,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},capture_output=True,text=True,
                timeout=15,**credentials)
            if result.returncode or json.loads(result.stdout).get('build_id')!=identifier:
                raise ValueError("Isolated host dependency/import check failed: "+result.stderr[-800:])
            os.chmod(temporary,0o555);temporary.rename(target);_fsync(self.releases)
            return identifier
        finally:
            if temporary.exists() and temporary.resolve().parent==self.releases.resolve():
                shutil.rmtree(temporary)

    def activate(self, blob, sha256, *, control, health, fingerprint):
        if not control.active(): raise ValueError("Update requires an already active application; it cannot enable one")
        return super().activate(blob,sha256,control=control,health=health,fingerprint=fingerprint)

    def rollback(self, *, control, health, fingerprint):
        previous=self.target('previous')
        if previous is None: raise ValueError("No previous application host")
        blob=(self.releases/previous/'artifact.tar').read_bytes()
        return self.activate(blob,_digest(blob),control=control,health=health,fingerprint=fingerprint)


def prepare_instances(root=ROOT):
    """Prepare only root-owned mutable instance pointers before helper hardening."""
    directory=Path(root)/'instances'
    if directory.is_symlink(): raise ValueError("Host instance directory cannot be symlinked")
    directory.mkdir(parents=True,exist_ok=True,mode=0o755)
    info=directory.stat()
    if not directory.is_dir() or info.st_uid!=os.geteuid() or info.st_mode&0o022:
        raise ValueError("Host instance directory ownership is unsafe")
    return directory


def store_for(instance, *, root=ROOT, state=STATE):
    return HostStore(Path(root)/'instances'/instance_id(instance),Path(state)/instance,Path(root)/'releases')


def bind_instance(instance, *, root=ROOT):
    root=Path(root);state=STATE if root==ROOT else root/'updates'
    store=store_for(instance,root=root,state=state)
    with store.locked():
        if store.pending() is not None: raise ValueError("Resolve the pending host update before activation")
        if store.target('current') is not None: return store.target('current')
        default=HostStore(root/'default',state/'default',root/'releases').target('current')
        if default is None: raise ValueError("Independent application host is not installed")
        store.link('current',default);return default


class ApplicationControl:
    def __init__(self,instance): self.unit='3mm-application-extension@'+instance_id(instance)+'.service'
    def active(self):
        # Prepared applications may be running with boot deliberately disabled.
        return subprocess.run(['/usr/bin/systemctl','is-active','--quiet',self.unit],timeout=5).returncode==0
    def stop(self): subprocess.run(['/usr/bin/systemctl','stop',self.unit],check=True,timeout=35)
    def start(self):
        subprocess.run(['/usr/bin/systemctl','reset-failed',self.unit],check=True,timeout=5)
        subprocess.run(['/usr/bin/systemctl','start',self.unit],check=True,timeout=35)


def _metadata(instance):
    path=APPLICATIONS/instance/'active.json'
    if path.is_symlink() or path.stat().st_size>131072: raise ValueError("Application metadata is invalid")
    value=json.loads(path.read_bytes())
    if value.get('instance_id')!=instance: raise ValueError("Application metadata binding changed")
    return value


def fingerprint(instance):
    value=core_fingerprint();release=Path(value['release'])
    validate_host_contract((release/'deployment/application-host-contract.json').read_bytes())
    import pwd
    peer=probe_runtime(Path('/run/3mm-platform/runtime.sock'),expected_uid=pwd.getpwnam('3mm-platform').pw_uid)
    return {**value,'platform_runtime':{k:peer[k] for k in ('pid','build_id','core_pid','core_process_generation','authority_contract')},'application_metadata':_digest(_json(_metadata(instance)))}


def _host_call(path, secret, operation, expected_uid, *, max_bytes=16384):
    request_id=uuid.uuid4().hex;deadline=time.monotonic()+HOST_PROBE_SECONDS
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(remaining(deadline));connection.connect(str(path));pid,uid,_=peer_identity(connection)
        if uid!=expected_uid: raise ValueError("Application host principal is not trusted")
        connection.settimeout(remaining(deadline))
        send_message(connection,sign_message({'version':1,'request_id':request_id,'timestamp':int(time.time()),
            'operation_id':operation,'payload':{},'context':{'audience':'internal'}},secret))
        response=verify_message(read_frame(connection,deadline,max_bytes=max_bytes),secret,expected_request_id=request_id)
    if response.get('ok') is not True or not isinstance(response.get('result'),dict):
        raise ValueError("Application host response is unavailable")
    return pid,uid,response['result']


def host_probe(instance, path, secret, *, expected_uid, expected_build, metadata):
    pid,uid,result=_host_call(path,secret,'three_mm.host.info',expected_uid)
    if result!={'host_contract':HOST_CONTRACT,'build_id':expected_build,
            'pid':pid,'uid':uid,'instance_id':instance,'metadata_sha256':_digest(_json(metadata))}:
        raise ValueError("Application host build/process binding is unavailable")
    return result


def health(instance, build):
    import pwd
    metadata=_metadata(instance);secret=(KEYS/(instance+'.key')).read_bytes()
    if len(secret)!=32: raise ValueError("Application transport key is invalid")
    deadline=time.monotonic()+15
    while True:
        try:
            host_probe(instance,APPLICATIONS/instance/'run/service.sock',secret,expected_uid=pwd.getpwnam('3mm-app').pw_uid,
                expected_build=build,metadata=metadata)
            _,_,result=_host_call(APPLICATIONS/instance/'run/service.sock',secret,metadata['health_operation_id'],
                pwd.getpwnam('3mm-app').pw_uid,max_bytes=1024*1024)
            if result.get('status') not in {'ok','ready'}: raise ValueError("Application is not ready")
            current=fingerprint(instance)
            return {'core_pid':current['pid'],'core_process_generation':current['generation']}
        except (OSError,ValueError,RuntimeError):
            if time.monotonic()>=deadline: raise
            time.sleep(.1)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='operation',required=True)
    build=sub.add_parser('build');build.add_argument('--source',type=Path,required=True);build.add_argument('--output',type=Path,required=True)
    bootstrap=sub.add_parser('bootstrap');bootstrap.add_argument('--source',type=Path,required=True)
    for name in ('update','rollback','recover','probe'):
        command=sub.add_parser(name);command.add_argument('--instance',required=True)
        if name=='update':command.add_argument('--artifact',type=Path,required=True);command.add_argument('--sha256',required=True)
    args=parser.parse_args()
    if args.operation=='build':
        blob,metadata=build_component(args.source);args.output.write_bytes(blob)
        print(json.dumps({'build_id':metadata['build_id'],'sha256':_digest(blob),'bytes':len(blob),'target':metadata['binding']['target']}));return
    if os.geteuid()!=0: raise ValueError("Host component administration requires the local administrator")
    if args.operation=='bootstrap':
        prepare_instances(ROOT)
        validate_host_contract((args.source/'deployment/application-host-contract.json').read_bytes())
        store=HostStore(ROOT/'default',STATE/'default',ROOT/'releases')
        if store.target('current') is None:
            blob,_=build_component(args.source);store.bootstrap(blob,_digest(blob))
        return
    from three_mm_runtime.application_lifecycle import _release_lock
    with _release_lock():
        instance=instance_id(args.instance);store=store_for(instance);control=ApplicationControl(instance)
        callbacks=dict(control=control,health=lambda build:health(instance,build),fingerprint=lambda:fingerprint(instance))
        if args.operation=='update':
            blob=args.artifact.read_bytes();result=store.activate(blob,args.sha256,**callbacks)
        elif args.operation=='rollback':result=store.rollback(**callbacks)
        elif args.operation=='recover':
            with store.locked():store.recover(control,callbacks['health'])
            result={'status':'recovered'}
        else:result=health(instance,store.target('current'))
        print(json.dumps(result))


if __name__=='__main__':main()
