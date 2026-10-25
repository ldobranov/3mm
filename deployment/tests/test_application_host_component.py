"""Independent native host artifacts and real per-application process updates."""
from contextlib import contextmanager
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import socket
import threading
import sys
import tarfile
import tempfile
import time
import zipfile

import pytest

from deployment import application_host_component as component
from three_mm_runtime.application_transport import ApplicationServiceClient
from backend.tests.test_platform_runtime_process import (
    stack, identity_app, managed_installed, source_subject, source_installed,
    checkpoint_app, activate_identity_grant, identity, activate,
)

pytestmark=pytest.mark.skipif(sys.platform!='linux',reason='Native Linux dependency closure and real Unix processes')
SOURCE=Path(__file__).resolve().parents[2]
INSTANCE='1'*24
OTHER='2'*24


def digest(blob):return hashlib.sha256(blob).hexdigest()


@pytest.fixture(scope='module')
def artifacts(tmp_path_factory):
    good=component.build_component(SOURCE)
    results=[good]
    for label,broken in [('b',False),('bad',True)]:
        source=tmp_path_factory.mktemp('host-source-'+label)
        for name in [*component.inputs(SOURCE),'deployment/application-host-contract.json','deployment/application-host-requirements.txt']:
            target=source/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/name,target)
        path=source/'three_mm_runtime/application_host.py';text=path.read_text()+'\n# '+label+'\n'
        if broken:text=text.replace('def main() -> None:', 'def main() -> None:\n    raise RuntimeError("injected unhealthy host")')
        path.write_text(text)
        results.append(component.build_component(source))
    return results


def test_native_artifact_is_reproducible_minimal_and_core_free(artifacts,tmp_path):
    blob,metadata=artifacts[0]
    assert component.build_component(SOURCE)[0]==blob
    assert len(metadata['binding']['dependencies'])==8
    assert not any(n.startswith(('backend/','three_mm_provisioning/')) for n in metadata['binding']['sources'])
    store=component.HostStore(tmp_path/'default',tmp_path/'updates',tmp_path/'releases')
    build=store.bootstrap(blob,digest(blob))
    result=subprocess.run([str(store.root/'current/.venv/bin/python'),'-I',str(store.root/'current/host.pyz'),'--component-info'],
        env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(SOURCE)},cwd=SOURCE,capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['build_id']==build
    assert 'backend' not in (store.root/'current/.venv/pyvenv.cfg').read_text()


@pytest.mark.parametrize('damage',['digest','host_contract','authority_contract','target','traversal','symlink','duplicate','native_file'])
def test_invalid_host_payload_is_refused_before_pointer_or_service_mutation(artifacts,tmp_path,damage):
    blob,metadata=artifacts[0];meta,files=component.validate_artifact(blob,digest(blob));meta=copy.deepcopy(meta)
    if damage=='digest':
        with pytest.raises(ValueError):component.validate_artifact(blob,'f'*64)
        return
    if damage in {'host_contract','authority_contract'}:meta['binding'][damage]=999
    elif damage=='target':meta['binding']['target']['python_tag']='foreign'
    elif damage=='native_file':files[next(n for n in files if n.endswith('.so'))]=b'changed'
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w') as archive:
        for name,value in {'component.json':component._json(meta),**files}.items():
            item=tarfile.TarInfo(name);item.size=len(value);archive.addfile(item,io.BytesIO(value))
        if damage in {'traversal','symlink','duplicate'}:
            item=tarfile.TarInfo('../outside' if damage=='traversal' else 'host.pyz')
            if damage=='symlink':item.type=tarfile.SYMTYPE;item.linkname='/etc/3mm'
            archive.addfile(item)
    invalid=output.getvalue();store=component.HostStore(tmp_path/'host',tmp_path/'updates',tmp_path/'releases')
    with pytest.raises(ValueError):store.stage(invalid,digest(invalid))
    assert not (store.root/'current').exists() and list(store.releases.iterdir())==[]


def make_application(base,instance,uid,gid):
    root=base/'applications'/instance
    release=root/'releases'/('a'*64);release.mkdir(parents=True)
    for name in ('run','data'):(root/name).mkdir()
    package='neutral_'+instance[:4]
    with zipfile.ZipFile(release/'service.whl','w') as wheel:
        wheel.writestr(package+'/__init__.py','')
        wheel.writestr(package+'/service.py',"""import importlib.util,os
from three_mm_application_sdk import ApplicationMigration

def migrations():
    return [ApplicationMigration('0001',lambda db:db.execute('CREATE TABLE records (value TEXT)'))]

class Service:
    def __init__(self,context):
        assert importlib.util.find_spec('backend') is None
        self.context=context
    def handle(self,operation,payload,context):
        return {'status':'ready','module_id':self.context.module_id,'pid':os.getpid()}

def create(context):return Service(context)
""")
    metadata={'instance_id':instance,'module_id':'org.example.'+instance[:4],'version':'1.0.0',
        'sha256':'a'*64,'wheel':'service.whl','entrypoint':package+'.service:create',
        'configuration':{},'storage':{'schema_revision':'0001','migration_entrypoint':package+'.service:migrations'},
        'health_operation_id':'ready','operations':[{'operation_id':'ready','audiences':['internal'],'idempotency':'forbidden'}]}
    (root/'active.json').write_text(json.dumps(metadata))
    (base/'keys').mkdir(exist_ok=True);(base/'keys'/(instance+'.key')).write_bytes(b's'*32)
    if os.geteuid()==0:
        for name in ('run','data'):os.chown(root/name,uid,gid)
        os.chown(base/'keys'/(instance+'.key'),0,gid);(base/'keys'/(instance+'.key')).chmod(0o640)
    return metadata


class HostProcesses:
    def __init__(self,store,base,instance,metadata,uid,gid,continuity):
        self.store=store;self.base=base;self.instance=instance;self.metadata=metadata
        self.uid=uid;self.gid=gid;self.process=None;self.calls=[];self.continuity=continuity
        self.log=(base/(instance+'.log')).open('ab')
    def active(self):return self.process is not None and self.process.poll() is None
    def stop(self):
        self.calls.append('stop:'+self.instance)
        if not self.active():return
        self.process.terminate()
        try:self.process.wait(timeout=.5)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
    def start(self):
        self.calls.append('start:'+self.instance);path=self.store.root/'current'
        kwargs={'user':self.uid,'group':self.gid,'extra_groups':[]} if os.geteuid()==0 else {}
        self.process=subprocess.Popen([str(path/'.venv/bin/python'),'-I',str(path/'host.pyz'),
            '--instance',self.instance,'--root',str(self.base/'applications'),'--key-root',str(self.base/'keys')],
            cwd=path,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},stdout=self.log,stderr=self.log,**kwargs)
    def health(self,build):
        deadline=time.monotonic()+5
        while True:
            try:
                component.host_probe(self.instance,self.base/'applications'/self.instance/'run/service.sock',b's'*32,
                    expected_uid=self.uid,expected_build=build,metadata=self.metadata)
                assert self.call()['status']=='ready'
                current=self.continuity()
                return {'core_pid':current['pid'],'core_process_generation':current['generation']}
            except (OSError,ValueError,RuntimeError):
                if not self.active():raise ValueError('Host failed startup')
                if time.monotonic()>deadline:raise
                time.sleep(.02)
    def call(self):
        return ApplicationServiceClient(self.base/'applications'/self.instance/'run/service.sock',b's'*32,
            timeout_seconds=1).invoke('ready',{}, {'audience':'internal'})


@contextmanager
def running_hosts(s,artifacts):
    with tempfile.TemporaryDirectory(prefix='p4c-hosts-',dir='/tmp') as directory:
        base=Path(directory);base.chmod(0o755)
        if os.geteuid()==0:
            import pwd
            user=pwd.getpwnam('3mm-app');uid,gid=user.pw_uid,user.pw_gid
        else:uid,gid=os.geteuid(),os.getegid()
        host_root=base/'hosts';state=host_root/'updates'
        default=component.HostStore(host_root/'default',state/'default',host_root/'releases')
        blob,meta=artifacts[0];default.bootstrap(blob,digest(blob))
        def continuity():
            return {**s.command('fingerprint'),'runtime_pid':s.control.process.pid,
                'runtime_build':s.store.target('current')}
        controls=[]
        try:
            for instance in (INSTANCE,OTHER):
                metadata=make_application(base,instance,uid,gid)
                component.bind_instance(instance,root=host_root)
                store=component.store_for(instance,root=host_root,state=state)
                control=HostProcesses(store,base,instance,metadata,uid,gid,continuity)
                controls.append(control);control.start();control.health(meta['build_id'])
            yield controls,continuity,base
        finally:
            for control in controls:control.stop();control.log.close()


def update_host(control,artifact,continuity):
    blob,metadata=artifact
    return control.store.activate(blob,digest(blob),control=control,health=control.health,fingerprint=continuity)


def snapshots(base):
    return {p.relative_to(base).as_posix():digest(p.read_bytes()) for p in (base/'applications').rglob('*')
        if p.is_file() and not p.is_socket() and ('run' not in p.relative_to(base).parts)}


def test_one_host_update_rollback_and_bad_candidate_preserve_real_core_runtime_other_host_and_data(stack,artifacts):
    s=stack;activate(s,s.artifact('transport'))
    with running_hosts(s,artifacts) as (controls,continuity,base):
        selected,other=controls;before=continuity();other_pid=other.process.pid;saved=snapshots(base)
        old_pid=selected.process.pid;update_host(selected,artifacts[1],continuity)
        assert selected.process.pid!=old_pid and other.process.pid==other_pid
        assert continuity()==before and snapshots(base)==saved and other.call()['status']=='ready'
        assert s.http()[0]==200 and s.client.get_installation_identity()['sdk_version']=='1.3'
        selected.store.rollback(control=selected,health=selected.health,fingerprint=continuity)
        assert selected.store.target('current')==artifacts[0][1]['build_id']
        with pytest.raises(ValueError):update_host(selected,artifacts[2],continuity)
        assert selected.store.target('current')==artifacts[0][1]['build_id']
        assert continuity()==before and snapshots(base)==saved and other.process.pid==other_pid
        assert selected.call()['status']=='ready' and other.call()['status']=='ready'
        selected.stop()
        with pytest.raises(ValueError,match='already active'):update_host(selected,artifacts[1],continuity)
        assert s.http()[0]==200 and continuity()==before


def test_interrupted_host_update_recovers_only_host_and_hang_does_not_block_core(stack,artifacts):
    s=stack;activate(s,s.artifact('transport'))
    with running_hosts(s,artifacts) as (controls,continuity,base):
        selected,other=controls;before=continuity();other_pid=other.process.pid
        class Interrupted(BaseException):pass
        start=selected.start
        def interrupt():raise Interrupted()
        selected.start=interrupt
        with pytest.raises(Interrupted):update_host(selected,artifacts[1],continuity)
        assert selected.store.pending()['phase']=='switching'
        selected.start=start
        with selected.store.locked():selected.store.recover(selected,selected.health)
        assert selected.store.pending() is None and selected.call()['status']=='ready'
        os.kill(selected.process.pid,signal.SIGSTOP)
        assert s.http()[0]==200 and other.call()['status']=='ready' and continuity()==before
        update_host(selected,artifacts[1],continuity)
        assert selected.call()['status']=='ready' and other.process.pid==other_pid and continuity()==before


@pytest.mark.skipif(os.name!='posix' or os.geteuid()!=0,reason='Separate isolated root driver; no installed service/account changes')
def test_separate_host_principal_cannot_read_core_and_uses_own_artifact(stack,artifacts,monkeypatch):
    s=stack;activate(s,s.artifact('transport'))
    with running_hosts(s,artifacts) as (controls,continuity,base):
        selected,other=controls;assert selected.uid not in {0,s.core_uid,s.runtime_uid}
        python=selected.store.root/'current/.venv/bin/python'
        for protected in (s.base/'core/3mm.db',s.base/'core/transport'/('a'*24+'.key')):
            result=subprocess.run([str(python),'-I','-c','from pathlib import Path;Path('+repr(str(protected))+').read_bytes()'],
                user=selected.uid,group=selected.gid,extra_groups=[],capture_output=True,timeout=3)
            assert result.returncode!=0 and b'PermissionError' in result.stderr
        monkeypatch.setattr(component,"APPLICATIONS",base/"applications")
        monkeypatch.setattr(component,"KEYS",base/"keys")
        monkeypatch.setattr(component,"fingerprint",lambda instance:continuity())
        selected.health=lambda build:component.health(selected.instance,build)
        before=continuity();other_pid=other.process.pid
        update_host(selected,artifacts[1],continuity)
        assert selected.call()['status']=='ready' and other.process.pid==other_pid and continuity()==before


def test_existing_instance_keeps_its_host_when_default_for_new_instances_moves(artifacts,tmp_path):
    root=tmp_path/'hosts';state=root/'updates'
    default=component.HostStore(root/'default',state/'default',root/'releases')
    first,_=artifacts[0];second,_=artifacts[1]
    a=default.bootstrap(first,digest(first));assert component.bind_instance(INSTANCE,root=root)==a
    b=default.stage(second,digest(second));default.link('current',b)
    assert component.bind_instance(INSTANCE,root=root)==a
    assert component.bind_instance(OTHER,root=root)==b
    assert default.bootstrap(first,digest(first))==b


def test_host_metadata_deadline_is_absolute_under_trickled_response(tmp_path,monkeypatch):
    monkeypatch.setattr(component,'HOST_PROBE_SECONDS',.1)
    path=tmp_path/'probe.sock';ready=threading.Event();done=threading.Event()
    def serve():
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
            listener.bind(str(path));listener.listen(1);ready.set()
            connection,_=listener.accept()
            with connection:
                connection.recv(4096)
                while not done.is_set():
                    try:connection.sendall(b' ')
                    except OSError:break
                    done.wait(.03)
    worker=threading.Thread(target=serve,daemon=True);worker.start();assert ready.wait(1)
    started=time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            component.host_probe(INSTANCE,path,b's'*32,expected_uid=os.geteuid(),expected_build='a'*64,metadata={})
        assert time.monotonic()-started<.5
    finally:done.set();worker.join(timeout=1)


def test_prepared_start_binds_a_host_before_systemd_and_missing_default_never_starts(artifacts,tmp_path,monkeypatch):
    from types import SimpleNamespace
    from three_mm_runtime.application_relational_activation import PreparedServiceSupervisor
    import three_mm_runtime.application_activation as activation
    root=tmp_path/'hosts';default=component.HostStore(root/'default',root/'updates/default',root/'releases')
    blob,metadata=artifacts[0];default.bootstrap(blob,digest(blob))
    calls=[]
    def systemctl(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1 if 'is-enabled' in args else 0)
    monkeypatch.setattr(activation.subprocess,'run',systemctl)
    PreparedServiceSupervisor(host_root=root).start(INSTANCE)
    assert component.store_for(INSTANCE,root=root,state=root/'updates').target('current')==metadata['build_id']
    assert calls==[['/usr/bin/systemctl','start','3mm-application-extension@'+INSTANCE+'.service']]
    with pytest.raises(ValueError,match='not installed'):
        PreparedServiceSupervisor(host_root=tmp_path/'absent').start(OTHER)
    assert len(calls)==1
    control=component.ApplicationControl(INSTANCE)
    assert control.active()  # Active prepared host, deliberately not enabled for boot.
    control.stop();control.start()
    assert [args[1] for args in calls]==['start','is-active','stop','reset-failed','start']
    assert calls[-2]==['/usr/bin/systemctl','reset-failed',control.unit]
    assert not any('enable' in args or 'disable' in args for args in calls)


def test_bootstrap_instance_directory_preparation_is_idempotent_and_separate(tmp_path):
    root=tmp_path/'hosts'
    path=component.prepare_instances(root)
    assert path==root/'instances' and path.is_dir()
    assert component.prepare_instances(root)==path
    assert not (root/'releases').exists() and not (root/'default').exists()


@pytest.mark.parametrize('damage',['symlink','writable','file'])
def test_bootstrap_refuses_unsafe_instance_directory(tmp_path,damage):
    root=tmp_path/'hosts';root.mkdir();path=root/'instances'
    if damage=='symlink':
        outside=tmp_path/'outside';outside.mkdir();path.symlink_to(outside,target_is_directory=True)
    elif damage=='writable':path.mkdir(mode=0o777);path.chmod(0o777)
    else:path.write_text('not a directory')
    with pytest.raises((ValueError,FileExistsError)):
        component.prepare_instances(root)
    assert not (root/'default').exists() and not (root/'releases').exists()
