"""Independent native Agent, public HTTP and session-worker artifacts.

Builds offline from exact installed dependency locks. Reuses the same pointer,
journal, recovery and Core-continuity transaction as Platform Runtime/hosts.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path,PurePosixPath
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import time
from urllib.parse import urlsplit
import venv
import zipfile

from deployment.component_store import ComponentStore,release_mutation_lock,_digest,_id,_json,_write,_fsync

CONTRACTS={"agent":{"device_contract":1},"public-web":{"public_web_contract":1},"session-worker":{"session_profile":"isolated_session_v1"},"session-node":{"session_link_contract":1},"session-relay":{"session_relay_contract":1}}
CONTRACT_FILE="deployment/service-components-contract.json"
ROLES={"agent":("agent.cli","3mm-agent.service","3mm"),
    "public-web":("three_mm_public_web.server","3mm-public-web.socket","3mm-public"),
    "session-worker":("three_mm_runtime.session_worker","3mm-session-worker.socket","3mm-app"),
    "session-node":("three_mm_runtime.session_node","3mm-session-node.service","3mm"),
    "session-relay":("three_mm_runtime.session_relay","3mm-session-relay.service","3mm-relay")}
MAX_BYTES=128*1024*1024


def startup_probe_seconds(component):
    # ARMv6 cold imports need a larger bounded preparation/readiness window.
    return 90 if component in {'agent','session-node','session-worker'} and platform.machine() == 'armv6l' else 20
ENTRY=b"""import asyncio,importlib,importlib.util,json,os,sys,zipfile
from pathlib import Path
base=Path(sys.argv[0]).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(base/'vendor'))
with zipfile.ZipFile(sys.argv[0]) as z:identity=json.loads(z.read('component-build.json'))
from three_mm_runtime.component_identity import set_component_identity
set_component_identity(identity['component'],identity['build_id'])
modules={'agent':'agent.cli','public-web':'three_mm_public_web.server','session-worker':'three_mm_runtime.session_worker','session-node':'three_mm_runtime.session_node','session-relay':'three_mm_runtime.session_relay'}
module=importlib.import_module(modules[identity['component']])
if sys.argv[1:]==['--component-info']:
    if identity['component']=='agent':importlib.import_module('gpiod')
    if identity['component']=='session-worker':importlib.import_module('three_mm_application_sdk.session')
    if any(importlib.util.find_spec(n) is not None for n in ('backend','sqlalchemy')):
        raise RuntimeError('Core code/dependencies are visible')
    print(json.dumps(identity,sort_keys=True))
else:
    if os.geteuid()==0:raise RuntimeError('Service component requires a non-root principal')
    if identity['component']=='session-worker':asyncio.run(module.main())
    else:module.main()
"""


def target_identity():
    if sys.platform!="linux" or platform.python_implementation()!="CPython" or sys.version_info<(3,12):
        raise ValueError("Native service artifacts require Linux CPython >=3.12")
    return {"python_tag":sys.implementation.cache_tag,"platform":sysconfig.get_platform(),"machine":platform.machine()}


def validate_contract(path):
    value=json.loads(Path(path).read_bytes())
    if type(value.get('schema_version')) is not int or _json(value)!=_json({"schema_version":1,"components":CONTRACTS}):
        raise ValueError("Service component contracts are unsupported")
    return value


def _name(name):
    path=PurePosixPath(name)
    return (bool(name) and name==path.as_posix() and not path.is_absolute() and not {'.','..'}&set(path.parts)
        and not any(c in name for c in ('\\',':','\0')))


def _source_name(name,component):
    p=PurePosixPath(name)
    if component!='session-relay' and len(p.parts)==2 and p.suffix=='.py' and p.parts[0] in {'three_mm_protocol','three_mm_platform_wire'}:return True
    if name in {'three_mm_runtime/__init__.py','three_mm_runtime/component_identity.py'}:return True
    if component=='session-relay':return name=='three_mm_runtime/session_relay.py'
    if component=='agent':
        return ((p.parts[0]=='agent' and p.suffix=='.py' and not {'tests','__pycache__'}&set(p.parts))
            or (len(p.parts)==2 and p.parts[0]=='three_mm_provisioning' and p.suffix=='.py')
            or name=='three_mm_runtime/session_output.py')
    if component=='public-web':return len(p.parts)==2 and p.parts[0]=='three_mm_public_web' and p.suffix=='.py'
    if component=='session-node':
        return ((len(p.parts)==2 and p.parts[0]=='three_mm_application_sdk' and p.suffix=='.py')
            or name in {'agent/__init__.py','agent/device_transport.py','agent/credentials.py'}
            or name in {'three_mm_runtime/session_worker.py','three_mm_runtime/session_worker_client.py',
                'three_mm_runtime/session_node.py','three_mm_runtime/session_link.py','three_mm_runtime/session_link_config.py'})
    return ((len(p.parts)==2 and p.parts[0]=='three_mm_application_sdk' and p.suffix=='.py')
        or name=='three_mm_runtime/session_worker.py')


def inputs(source,component):
    if component not in ROLES:raise ValueError("Unknown service component")
    names=[]
    for folder in ('agent','three_mm_runtime','three_mm_provisioning','three_mm_protocol','three_mm_application_sdk','three_mm_platform_wire','three_mm_public_web'):
        for path in (Path(source)/folder).rglob('*.py'):
            name=path.relative_to(source).as_posix()
            if _source_name(name,component):names.append(name)
    return sorted(names)


def _archive(metadata,files):
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w') as tar:
        for name,data in sorted({'component.json':_json(metadata),**files}.items()):
            entry=tarfile.TarInfo(name);entry.size=len(data);entry.mode=0o444;entry.mtime=0;tar.addfile(entry,io.BytesIO(data))
    return output.getvalue()


def build_component(source,component):
    source=Path(source).resolve();target=target_identity();validate_contract(source/CONTRACT_FILE)
    if component not in ROLES:raise ValueError("Unknown service component")
    code={}
    for name in inputs(source,component):
        path=source/name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source):raise ValueError("Unsafe service source")
        code[name]=path.read_bytes().replace(b'\r\n',b'\n')
    code['__main__.py']=ENTRY
    lock=('deployment/service-agent-requirements.txt' if component=='agent' else
          'deployment/session-node-requirements.txt' if component=='session-node' else
          'deployment/session-relay-requirements.txt' if component=='session-relay' else
          'deployment/session-worker-requirements.txt' if component=='session-worker' else
          'deployment/application-host-requirements.txt')
    vendor={};dependencies={}
    for line in (source/lock).read_text().splitlines():
        name,version=line.split('==');distribution=importlib.metadata.distribution(name)
        if distribution.version!=version:raise ValueError('Builder dependency differs from lock: '+name)
        dependencies[name]=version
        for item in distribution.files or ():
            name=item.as_posix()
            if name.endswith('.pyc') or '__pycache__' in item.parts or item.parts[:4]==('..','..','..','bin'):continue
            if not _name(name):raise ValueError('Dependency escapes its package root')
            path=Path(distribution.locate_file(item))
            if path.is_symlink() or not path.is_file():raise ValueError('Dependency must be regular')
            dest='vendor/'+name;data=path.read_bytes()
            if dest in vendor and vendor[dest]!=data:raise ValueError('Dependency collision')
            vendor[dest]=data
    binding={'component':component,'contracts':CONTRACTS[component],'target':target,'dependencies':dependencies,
        'sources':{n:_digest(v) for n,v in code.items()},'vendor':{n:_digest(v) for n,v in vendor.items()}}
    identifier=_digest(_json(binding));identity={'component':component,'build_id':identifier,'contracts':CONTRACTS[component]}
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
        for name,data in sorted({**code,'component-build.json':_json(identity)}.items()):
            entry=zipfile.ZipInfo(name,(2026,1,1,0,0,0));entry.create_system=3;entry.external_attr=0o100444<<16
            entry.compress_type=zipfile.ZIP_DEFLATED;bundle.writestr(entry,data)
    files={'service.pyz':output.getvalue(),**vendor}
    metadata={'schema_version':1,'component':component,'build_id':identifier,'binding':binding,'files':{n:_digest(v) for n,v in files.items()}}
    blob=_archive(metadata,files);validate_artifact(blob,_digest(blob),component)
    return blob,metadata


def validate_artifact(blob,expected,component):
    if component not in ROLES or not _id(expected) or len(blob)>MAX_BYTES or _digest(blob)!=expected:raise ValueError('Service artifact digest/size is invalid')
    files={};total=0
    with tarfile.open(fileobj=io.BytesIO(blob),mode='r:') as tar:
        for item in tar:
            if not item.isfile() or not _name(item.name) or item.name in files or item.size>MAX_BYTES or len(files)>=8192:raise ValueError('Unsafe service artifact member')
            total+=item.size
            if total>MAX_BYTES:raise ValueError('Service artifact exceeds budget')
            files[item.name]=tar.extractfile(item).read(item.size+1)
    if 'component.json' not in files or len(files['component.json'])>2*1024*1024:raise ValueError('Service manifest unavailable')
    metadata=json.loads(files.pop('component.json'));binding=metadata.get('binding')
    if (set(metadata)!={'schema_version','component','build_id','binding','files'} or type(metadata['schema_version']) is not int
        or metadata['schema_version']!=1 or metadata['component']!=component or not isinstance(binding,dict)
        or set(binding)!={'component','contracts','target','dependencies','sources','vendor'}
        or binding['component']!=component or _json(binding['contracts'])!=_json(CONTRACTS[component]) or binding['target']!=target_identity()
        or (not binding['dependencies'] and component!='session-relay') or not all(isinstance(n,str) and isinstance(v,str) for n,v in binding['dependencies'].items())
        or metadata['build_id']!=_digest(_json(binding)) or metadata['files']!={n:_digest(v) for n,v in files.items()}
        or set(files)!={'service.pyz',*binding['vendor']}
        or any(not n.startswith('vendor/') or not _name(n) or not _id(h) or _digest(files[n])!=h for n,h in binding['vendor'].items())):
        raise ValueError('Service manifest binding is invalid')
    with zipfile.ZipFile(io.BytesIO(files['service.pyz'])) as bundle:
        infos=bundle.infolist()
        if len(infos)>8192 or sum(i.file_size for i in infos)>MAX_BYTES or any(i.is_dir() or not stat.S_ISREG(i.external_attr>>16) for i in infos):raise ValueError('Service executable exceeds budget')
        names=bundle.namelist();expected_names=set(binding['sources'])|{'component-build.json'}
        if set(names)!=expected_names or len(names)!=len(expected_names):raise ValueError('Service executable inventory changed')
        if (any(not _source_name(n,component) and n!='__main__.py' for n in binding['sources'])
            or any(not _id(h) or _digest(bundle.read(n))!=h for n,h in binding['sources'].items())
            or sum(i.file_size for i in bundle.infolist())>MAX_BYTES
            or json.loads(bundle.read('component-build.json'))!={'component':component,'build_id':metadata['build_id'],'contracts':CONTRACTS[component]}):
            raise ValueError('Service executable binding changed')
    return metadata,files


class ServiceStore(ComponentStore):
    requires_active=True
    def __init__(self,component,root=None,state=None):
        if component not in ROLES:raise ValueError('Unknown service component')
        self.component=component
        super().__init__(root or Path('/opt/3mm-'+component),state or Path('/var/lib/3mm-'+component+'-updates'))
    def metadata(self,identifier):
        if not _id(identifier):raise ValueError('Invalid service build')
        directory=self.releases/identifier;artifact=directory/'artifact.tar'
        if directory.is_symlink() or artifact.is_symlink() or artifact.stat().st_size>MAX_BYTES:raise ValueError('Unsafe installed service artifact')
        blob=artifact.read_bytes();metadata,files=validate_artifact(blob,_digest(blob),self.component)
        if metadata['build_id']!=identifier:raise ValueError('Service pointer identity changed')
        for name,data in {'component.json':_json(metadata),**files}.items():
            path=directory/name
            if path.is_symlink() or not path.is_file() or path.stat().st_size!=len(data) or _digest(path.read_bytes())!=_digest(data):raise ValueError('Installed service payload changed')
        return metadata
    def stage(self,blob,sha256):
        metadata,files=validate_artifact(blob,sha256,self.component);identifier=metadata['build_id'];target=self.releases/identifier
        if target.exists() or target.is_symlink():
            if self.metadata(identifier)!=metadata or not (target/'.venv/bin/python').is_file():raise ValueError('Service environment incomplete')
            return identifier
        temporary=Path(tempfile.mkdtemp(prefix='.stage-',dir=self.releases));temporary.chmod(0o755)
        try:
            for name,data in {'artifact.tar':blob,'component.json':_json(metadata),**files}.items():
                path=temporary/name;path.parent.mkdir(parents=True,exist_ok=True);_write(path,data,0o444)
            venv.EnvBuilder(with_pip=False,symlinks=True).create(temporary/'.venv')
            credentials={}
            if os.geteuid()==0:
                import pwd
                try:user=pwd.getpwnam(ROLES[self.component][2])
                except KeyError:user=pwd.getpwnam('3mm')
                credentials={'user':user.pw_uid,'group':user.pw_gid,'extra_groups':[]}
            result=subprocess.run([str(temporary/'.venv/bin/python'),'-I',str(temporary/'service.pyz'),'--component-info'],
                cwd=temporary,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},capture_output=True,text=True,timeout=startup_probe_seconds(self.component),**credentials)
            if result.returncode or json.loads(result.stdout).get('build_id')!=identifier:raise ValueError('Isolated service import check failed: '+result.stderr[-800:])
            temporary.chmod(0o555);temporary.rename(target);_fsync(self.releases);return identifier
        finally:
            if temporary.exists() and temporary.resolve().parent==self.releases.resolve():shutil.rmtree(temporary)
    def activate(self,blob,sha256,*,control,health,fingerprint):
        if not control.active():raise ValueError('Update requires an active component; cannot enable one')
        return super().activate(blob,sha256,control=control,health=health,fingerprint=fingerprint)
    def rollback(self,*,control,health,fingerprint):
        previous=self.target('previous')
        if previous is None:raise ValueError('No previous service component')
        blob=(self.releases/previous/'artifact.tar').read_bytes()
        return self.activate(blob,_digest(blob),control=control,health=health,fingerprint=fingerprint)


class ServiceControl:
    def __init__(self,component):self.component=component;self.unit=ROLES[component][1]
    def active(self):
        result=subprocess.run(['/usr/bin/systemctl','is-active','--quiet',self.unit],timeout=5)
        if result.returncode not in (0,3):raise ValueError('Component service state unavailable')
        return result.returncode==0
    def stop(self):
        subprocess.run(['/usr/bin/systemctl','stop',self.unit],check=True,timeout=25)
        if self.component in {'public-web','session-worker','session-node'}:
            name=('3mm-public-web.service' if self.component=='public-web' else
                  '3mm-session-worker-node@*.service' if self.component=='session-node' else '3mm-session-worker@*.service')
            subprocess.run(['/usr/bin/systemctl','stop',name],check=True,timeout=25)
    def start(self):
        # A bad candidate may exhaust systemd's restart burst. Recovery must
        # clear only this component's failure counter before starting the old pin.
        units=[self.unit]
        if self.component=='public-web':units.append('3mm-public-web.service')
        subprocess.run(['/usr/bin/systemctl','reset-failed',*units],check=True,timeout=10)
        subprocess.run(['/usr/bin/systemctl','start',self.unit],check=True,timeout=25)


def fingerprint():
    profile=Path('/opt/3mm/current/.3mm-install-profile')
    if profile.is_file() and profile.read_text().strip()=='node':
        result=subprocess.run(['/usr/bin/systemctl','show','3mm-core.service','--property=MainPID','--value'],capture_output=True,text=True,timeout=5)
        if result.stdout.strip() not in {'','0'}:raise ValueError('Unexpected Core process on Node profile')
        return {'pid':0,'generation':{'profile':'node','marker_sha256':_digest(profile.read_bytes())},'release':str(profile.parent.resolve())}
    from deployment.platform_runtime_component import core_fingerprint
    value=core_fingerprint();validate_contract(Path(value['release'])/CONTRACT_FILE);return value


def _http_identity(url, *, timeout=2):
    """Local component identity with one absolute connect/header/body deadline."""
    parsed=urlsplit(url)
    if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Component health must use a fixed loopback endpoint')
    deadline=time.monotonic()+timeout;data=bytearray();length=None;start=None
    with socket.create_connection((parsed.hostname,parsed.port or 80),timeout=timeout) as connection:
        connection.settimeout(max(.001,deadline-time.monotonic()))
        connection.sendall(('GET '+parsed.path+' HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n').encode('ascii'))
        while len(data)<8192:
            left=deadline-time.monotonic()
            if left<=0:raise TimeoutError('Component health deadline expired')
            connection.settimeout(left);chunk=connection.recv(min(2048,8192-len(data)))
            if not chunk:raise ValueError('Component health response is incomplete')
            data.extend(chunk)
            if start is None and b'\r\n\r\n' in data:
                headers,_,body=data.partition(b'\r\n\r\n');start=len(headers)+4
                if len(headers)>4096:raise ValueError('Component health headers exceed budget')
                lines=headers.decode('ascii').split('\r\n')
                if len(lines[0].split(' '))<2 or lines[0].split(' ')[1]!='200':raise ValueError('Component health failed')
                lengths=[line.split(':',1)[1].strip() for line in lines[1:] if line.lower().startswith('content-length:')]
                if len(lengths)!=1 or not lengths[0].isdigit() or any(line.lower().startswith('transfer-encoding:') for line in lines[1:]):raise ValueError('Component health framing is invalid')
                length=int(lengths[0])
                if not 1<=length<=4096:raise ValueError('Component health body exceeds budget')
            if start is not None and len(data)>=start+length:
                if len(data)!=start+length:raise ValueError('Component health response has a tail')
                return json.loads(data[start:])
    raise ValueError('Component health response exceeds budget')


def health(store,control,identifier):
    metadata=store.metadata(identifier)
    if not control.active():raise ValueError('Component listener is unavailable')
    if store.component in {'agent','public-web'}:
        url=('http://127.0.0.1:8890/component-health' if store.component=='agent' else 'http://127.0.0.1:8081/__3mm_component__/health')
        deadline=time.monotonic()+(startup_probe_seconds(store.component) if platform.machine()=='armv6l' else 15)
        while True:
            try:
                result=_http_identity(url)
                unit='3mm-public-web.service' if store.component=='public-web' else control.unit
                process=subprocess.run(['/usr/bin/systemctl','show',unit,'--property=MainPID','--value'],capture_output=True,text=True,check=True,timeout=5)
                if result!={'component':store.component,'build_id':identifier,'pid':int(process.stdout.strip())} or result['pid']<=0:raise ValueError('Loaded component identity changed')
                break
            except (OSError,ValueError):
                if time.monotonic()>=deadline:raise
                time.sleep(.1)
    if store.component in {'session-node','session-relay'}:
        import pwd
        name=store.component
        path=Path('/run/3mm-'+name+('/support.json' if name=='session-node' else '/identity.json'))
        uid=pwd.getpwnam(ROLES[name][2]).pw_uid
        deadline=time.monotonic()+startup_probe_seconds(name)
        while True:
            try:
                # A service may be active before its cold imports and first
                # readiness publication finish. Read only bounded regular files
                # from the expected principal; never follow links or open FIFOs.
                fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
            except FileNotFoundError:
                value=None
            else:
                with os.fdopen(fd,'rb') as stream:
                    info=os.fstat(stream.fileno())
                    if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=uid
                        or info.st_mode&0o022 or not 1<=info.st_size<=4096):
                        raise ValueError('Session component identity is untrusted')
                    data=stream.read(4097)
                if len(data)>4096:raise ValueError('Session component identity exceeds budget')
                value=json.loads(data)
                if type(value) is not dict:raise ValueError('Session component identity is malformed')
            if value is not None:
                remaining=deadline-time.monotonic()
                if remaining<=0:raise ValueError('Session component readiness deadline expired')
                pid=int(subprocess.check_output(['/usr/bin/systemctl','show',control.unit,'--property=MainPID','--value'],
                    text=True,timeout=min(5,remaining)).strip())
                expires=value.get('expires_at')
                if (value.get('component')==name and value.get('build_id')==identifier
                    and type(value.get('pid')) is int and value['pid']==pid and pid>0
                    and type(expires) in {int,float} and 0<expires-time.time()<=12):
                    break
            if not control.active():raise ValueError('Component listener is unavailable')
            remaining=deadline-time.monotonic()
            if remaining<=0:raise ValueError('Session component readiness deadline expired')
            time.sleep(min(.1,remaining))
    # Per-connection session workers have no permanent PID. Validate the listening
    # socket and exact immutable artifact; OS/provider admission stays unchanged.
    core=fingerprint()
    return {'build_id':metadata['build_id'],'core_pid':core['pid'],'core_process_generation':core['generation']}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('component',choices=ROLES)
    parser.add_argument('action',choices=('build','bootstrap','update','rollback','recover','probe','status'))
    parser.add_argument('--source',type=Path,default=Path.cwd());parser.add_argument('--output',type=Path)
    parser.add_argument('--artifact',type=Path);parser.add_argument('--sha256')
    args=parser.parse_args(argv)
    if args.action=='build':
        if args.output is None:parser.error('--output is required')
        blob,metadata=build_component(args.source,args.component);args.output.write_bytes(blob);print(json.dumps(metadata));return 0
    if os.geteuid()!=0:raise ValueError('Installed component management requires root')
    store=ServiceStore(args.component);control=ServiceControl(args.component)
    if args.action=='bootstrap':
        with store.locked():
            if store.pending() is not None:raise ValueError('Resolve pending component update before bootstrap')
            current=store.target('current')
            if current is not None:print(current);return 0
        blob,_=build_component(args.source,args.component);print(store.bootstrap(blob,_digest(blob)));return 0
    if args.action=='status':print(json.dumps({'current':store.target('current'),'previous':store.target('previous'),'pending':store.pending()}));return 0
    probe=lambda identifier:health(store,control,identifier)
    if args.action=='probe':print(json.dumps(probe(store.target('current'))));return 0
    with release_mutation_lock():
        if args.action=='recover':
            with store.locked():store.recover(control,probe)
            result={'status':'recovered'}
        elif args.action=='rollback':result=store.rollback(control=control,health=probe,fingerprint=fingerprint)
        else:
            if args.artifact is None or args.sha256 is None:parser.error('--artifact and --sha256 are required')
            result=store.activate(args.artifact.read_bytes(),args.sha256,control=control,health=probe,fingerprint=fingerprint)
    print(json.dumps(result));return 0


if __name__=='__main__':raise SystemExit(main())
