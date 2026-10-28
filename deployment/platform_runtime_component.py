"""Independent immutable platform Runtime artifact, transactional switch/rollback.

Each activation targets one process role and its own release pins/journal. No Core DB,
application grant or signing key is read by this stdlib-only deployment adapter.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
import venv
import zipfile

from deployment.component_store import ComponentStore
from three_mm_platform_wire import AUTHORITY_CONTRACT, peer_identity, process_generation
from three_mm_platform_runtime.server import probe_runtime
from deployment.deployment_contract import validate_platform_runtime_contract

UNIT="3mm-platform-runtime.service"
ROOT=Path("/opt/3mm-platform-runtime")
STATE=Path("/var/lib/3mm-platform-updates")
SOCKET=Path("/run/3mm-platform/runtime.sock")
MAX_ARTIFACT=2*1024*1024
INPUTS=("three_mm_platform_wire/__init__.py","three_mm_platform_wire/task_time.py","three_mm_platform_runtime/__init__.py",
        "three_mm_platform_runtime/__main__.py","three_mm_platform_runtime/server.py",
        "three_mm_platform_runtime/public_web.py","three_mm_platform_runtime/events.py","three_mm_platform_runtime/connector_worker.py","three_mm_platform_runtime/responses.py","three_mm_platform_runtime/tasks.py")


def _json(value):return json.dumps(value,sort_keys=True,separators=(",", ":"),allow_nan=False).encode()
def _digest(value):return hashlib.sha256(value).hexdigest()
def _id(value):return isinstance(value,str) and re.fullmatch(r"[0-9a-f]{64}",value) is not None


def build_component(source):
    source=Path(source).resolve();files={}
    for name in INPUTS:
        path=source/name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source):
            raise ValueError("Runtime source must be a regular repository file")
        files[name]=path.read_bytes().replace(b"\r\n",b"\n")
    files["__main__.py"]=b"from three_mm_platform_runtime.server import main\nraise SystemExit(main())\n"
    build_id=_digest(_json({k:_digest(v) for k,v in files.items()}))
    files["runtime-build.json"]=_json({"build_id":build_id,"authority_contract":AUTHORITY_CONTRACT})
    output=io.BytesIO()
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        for name,value in sorted(files.items()):
            entry=zipfile.ZipInfo(name,(2026,1,1,0,0,0));entry.create_system=3
            entry.external_attr=0o100644<<16;entry.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(entry,value)
    code=output.getvalue()
    metadata={"schema_version":1,"component":"platform-runtime","build_id":build_id,
        "authority_contract":AUTHORITY_CONTRACT,"python_min":[3,12],
        "runtime_sha256":_digest(code),"runtime_bytes":len(code)}
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode="w") as archive:
        for name,value in [("component.json",_json(metadata)),("runtime.pyz",code)]:
            item=tarfile.TarInfo(name);item.size=len(value);item.mode=0o644;item.mtime=0
            archive.addfile(item,io.BytesIO(value))
    blob=output.getvalue()
    validate_artifact(blob,_digest(blob))
    return blob,metadata


def validate_metadata(value,code):
    if (not isinstance(value,dict) or set(value)!={"schema_version","component","build_id","authority_contract","python_min","runtime_sha256","runtime_bytes"}
            or type(value["schema_version"]) is not int or value["schema_version"]!=1
            or value["component"]!="platform-runtime" or not _id(value["build_id"])
            or type(value["authority_contract"]) is not int or value["authority_contract"]!=AUTHORITY_CONTRACT
            or value["python_min"]!=[3,12] or sys.version_info<(3,12)
            or value["runtime_sha256"]!=_digest(code) or value["runtime_bytes"]!=len(code)):
        raise ValueError("Runtime artifact contract or digest is unsupported")
    with zipfile.ZipFile(io.BytesIO(code)) as archive:
        # Validate the immutable release's own file set, not this updater's build
        # inputs. Independent component update/rollback must survive added workers.
        expected=set(archive.namelist())
        required={"__main__.py", "runtime-build.json", "three_mm_platform_wire/__init__.py",
            "three_mm_platform_runtime/__init__.py", "three_mm_platform_runtime/__main__.py", "three_mm_platform_runtime/server.py"}
        def source(name):
            parts=name.split('/')
            return (len(parts)==2 and parts[0] in {"three_mm_platform_wire","three_mm_platform_runtime"}
                and re.fullmatch(r"[a-z_][a-z0-9_]*\.py",parts[1]) is not None)
        if (not required<=expected or len(expected)>64 or len(archive.namelist())!=len(expected)
                or any(name not in {"__main__.py","runtime-build.json"} and not source(name) for name in expected)):
            raise ValueError("Runtime executable payload is invalid")
        if (any(info.file_size>MAX_ARTIFACT or info.is_dir() or not stat.S_ISREG(info.external_attr>>16)
                for info in archive.infolist()) or sum(info.file_size for info in archive.infolist())>MAX_ARTIFACT):
            raise ValueError("Runtime executable exceeds its budget")
        files={name:archive.read(name) for name in expected-{"runtime-build.json"}}
        if (sum(len(value) for value in files.values())>MAX_ARTIFACT
                or _digest(_json({k:_digest(v) for k,v in files.items()}))!=value["build_id"]
                or json.loads(archive.read("runtime-build.json"))!={"build_id":value["build_id"],"authority_contract":AUTHORITY_CONTRACT}):
            raise ValueError("Runtime executable identity is invalid")
    return value


def validate_artifact(blob,sha256):
    if len(blob)>MAX_ARTIFACT or not _id(sha256) or _digest(blob)!=sha256:
        raise ValueError("Runtime archive digest or size is invalid")
    files={}
    try:
        with tarfile.open(fileobj=io.BytesIO(blob),mode="r:") as archive:
            for member in archive:
                if (member.name not in {"component.json","runtime.pyz"} or not member.isfile()
                        or member.name in files or member.size>MAX_ARTIFACT):
                    raise ValueError("Runtime archive contains unsupported files")
                files[member.name]=archive.extractfile(member).read(member.size+1)
        if set(files)!={"component.json","runtime.pyz"}:raise ValueError("Runtime archive is incomplete")
        value=json.loads(files["component.json"])
        return validate_metadata(value,files["runtime.pyz"]),files["runtime.pyz"]
    except (tarfile.TarError,zipfile.BadZipFile,KeyError,UnicodeError,TypeError) as error:
        raise ValueError("Runtime artifact is invalid") from error


def _fsync(path):
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def _write(path,blob,mode=0o600):
    temporary=path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
    with os.fdopen(fd,"wb") as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    temporary.replace(path);_fsync(path.parent)


class SystemdRuntime:
    def __init__(self, unit=UNIT): self.unit=unit
    def active(self):
        result=subprocess.run(["/usr/bin/systemctl","is-active","--quiet",self.unit],check=False,timeout=5)
        if result.returncode not in (0,3):raise ValueError("Runtime service state is unavailable")
        return result.returncode==0
    def stop(self):subprocess.run(["/usr/bin/systemctl","stop",self.unit],check=True,timeout=15)
    def start(self):
        subprocess.run(["/usr/bin/systemctl","reset-failed",self.unit],check=True,timeout=5)
        subprocess.run(["/usr/bin/systemctl","start",self.unit],check=True,timeout=15)


def core_fingerprint():
    result=subprocess.run(["/usr/bin/systemctl","show","3mm-core.service","--property=MainPID","--value"],
                          check=True,capture_output=True,text=True,timeout=5)
    pid=int(result.stdout.strip())
    if pid<=0:raise ValueError("Core must remain running during an independent Runtime update")
    import pwd
    uid=pwd.getpwnam("3mm").pw_uid
    release=Path("/opt/3mm/current").resolve(strict=True)
    metadata=(release/".3mm-release.json").read_bytes()
    validate_platform_runtime_contract((release/"deployment/platform-runtime-contract.json").read_bytes())
    return {"pid":pid,"generation":process_generation(pid,uid),
            "release":str(release),"metadata_sha256":_digest(metadata)}


class RuntimeStore(ComponentStore):
    def __init__(self,root=ROOT,state=STATE):super().__init__(root,state)

    def metadata(self,identifier):
        if not _id(identifier):raise ValueError("Runtime release identity is invalid")
        directory=self.releases/identifier
        if directory.is_symlink() or not directory.is_dir():raise ValueError("Runtime release is unavailable")
        code=directory/"runtime.pyz";manifest=directory/"component.json"
        if code.is_symlink() or manifest.is_symlink():raise ValueError("Runtime release payload must be regular")
        if code.stat().st_size>MAX_ARTIFACT or manifest.stat().st_size>8192:raise ValueError("Runtime release is too large")
        result=validate_metadata(json.loads(manifest.read_bytes()),code.read_bytes())
        if result["build_id"]!=identifier:raise ValueError("Runtime release identity changed")
        return result


    def stage(self,blob,sha256):
        metadata,code=validate_artifact(blob,sha256);identifier=metadata["build_id"]
        target=self.releases/identifier
        if target.exists() or target.is_symlink():
            if self.metadata(identifier)!=metadata:raise ValueError("Immutable Runtime release already differs")
            if not (target/".venv/bin/python").is_file():raise ValueError("Runtime environment is incomplete")
            return identifier
        temporary=Path(tempfile.mkdtemp(prefix=".stage-",dir=self.releases))
        _write(temporary/"runtime.pyz",code,0o444);_write(temporary/"component.json",_json(metadata),0o444)
        venv.EnvBuilder(with_pip=False,symlinks=True).create(temporary/".venv")
        os.chmod(temporary,0o555);temporary.rename(target);_fsync(self.releases)
        return identifier


    def rollback(self,*,control,health,fingerprint):
        identifier=self.target("previous")
        if identifier is None:raise ValueError("No previous Runtime release")
        directory=self.releases/identifier
        code=(directory/"runtime.pyz").read_bytes();metadata=self.metadata(identifier)
        output=io.BytesIO()
        with tarfile.open(fileobj=output,mode="w") as archive:
            for name,value in [("component.json",_json(metadata)),("runtime.pyz",code)]:
                item=tarfile.TarInfo(name);item.size=len(value);archive.addfile(item,io.BytesIO(value))
        blob=output.getvalue()
        return self.activate(blob,_digest(blob),control=control,health=health,fingerprint=fingerprint)




def runtime_health(identifier):
    import pwd
    uid=pwd.getpwnam("3mm-platform").pw_uid
    deadline=time.monotonic()+15
    while True:
        try:return probe_runtime(SOCKET,expected_uid=uid,expected_build=identifier,require_public_web=True,require_events=True,require_responses=True)
        except (OSError,ValueError):
            if time.monotonic()>=deadline:raise
            time.sleep(.1)


def connector_health(identifier):
    import pwd
    from three_mm_platform_runtime.connector_worker import probe_worker
    uid=pwd.getpwnam("3mm-connectors").pw_uid
    deadline=time.monotonic()+15
    while True:
        try:
            result=probe_worker(Path("/run/3mm-connectors/worker.sock"),expected_uid=uid,expected_build=identifier)
            core=core_fingerprint()
            return {**result,"core_pid":core["pid"],"core_process_generation":core["generation"]}
        except (OSError,ValueError):
            if time.monotonic()>=deadline:raise
            time.sleep(.1)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component",choices=("platform-runtime","connector-worker"),default="platform-runtime")
    sub=parser.add_subparsers(dest="operation",required=True)
    build=sub.add_parser("build");build.add_argument("--source",type=Path,required=True);build.add_argument("--output",type=Path,required=True)
    boot=sub.add_parser("bootstrap");boot.add_argument("--source",type=Path,required=True)
    update=sub.add_parser("update");update.add_argument("--artifact",type=Path,required=True);update.add_argument("--sha256",required=True)
    sub.add_parser("rollback");sub.add_parser("recover");sub.add_parser("probe")
    args=parser.parse_args(argv)
    if args.operation=="build":
        blob,metadata=build_component(args.source);args.output.write_bytes(blob)
        print(json.dumps({"build_id":metadata["build_id"],"sha256":_digest(blob),"bytes":len(blob)}));return 0
    if os.geteuid()!=0:raise ValueError("Runtime activation requires the local administrator")
    if args.operation=="bootstrap":
        validate_platform_runtime_contract((args.source/"deployment/platform-runtime-contract.json").read_bytes())
    if args.component=="connector-worker":
        store=RuntimeStore(Path("/opt/3mm-connector-worker"),Path("/var/lib/3mm-connector-updates"))
        control=SystemdRuntime("3mm-connector-worker.service");health=connector_health
    else:
        store=RuntimeStore();control=SystemdRuntime();health=runtime_health
    if args.operation=="bootstrap":
        blob,_=build_component(args.source);print(store.bootstrap(blob,_digest(blob)));return 0
    if args.operation=="probe":health(store.target("current"));return 0
    import fcntl
    fd=os.open("/run/lock/3mm-release-mutation.lock",os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.operation=="update":
            blob=args.artifact.read_bytes();result=store.activate(blob,args.sha256,control=control,health=health,fingerprint=core_fingerprint)
        elif args.operation=="rollback":result=store.rollback(control=control,health=health,fingerprint=core_fingerprint)
        else:
            with store.locked():store.recover(control,health)
            result={"status":"recovered"}
        print(json.dumps(result));return 0
    finally:os.close(fd)


if __name__=="__main__":raise SystemExit(main())
