"""Native service artifacts and independent real-process update/rollback."""
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
import zipfile

import pytest
from deployment import service_component as component
from backend.tests.test_platform_runtime_process import (
    stack,identity_app,managed_installed,source_subject,source_installed,checkpoint_app,
)

ROOT=Path(__file__).resolve().parents[2]
pytestmark=pytest.mark.skipif(os.name!='posix',reason='Native Linux component environment and processes')
CACHE={}


def digest(data):return hashlib.sha256(data).hexdigest()


def artifacts(role):
    if role not in CACHE:
        a=component.build_component(ROOT,role)
        with tempfile.TemporaryDirectory(prefix='3mm-svc-source-',dir='/tmp') as directory:
            source=Path(directory)
            for name in component.inputs(ROOT,role)+[component.CONTRACT_FILE,'deployment/application-host-requirements.txt','deployment/service-agent-requirements.txt','deployment/session-node-requirements.txt','deployment/session-worker-requirements.txt','deployment/session-relay-requirements.txt']:
                target=source/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
            target=source/(component.ROLES[role][0].replace('.','/')+'.py')
            target.write_bytes(target.read_bytes()+b'\n# independent candidate B\n')
            b=component.build_component(source,role)
        CACHE[role]=a,b
    return CACHE[role]


@pytest.mark.parametrize('role',component.ROLES)
def test_native_service_is_reproducible_and_contains_no_core(role):
    blob,metadata=artifacts(role)[0]
    assert blob==component.build_component(ROOT,role)[0]
    parsed,files=component.validate_artifact(blob,digest(blob),role)
    assert parsed==metadata and parsed['binding']['contracts']==component.CONTRACTS[role]
    with zipfile.ZipFile(io.BytesIO(files['service.pyz'])) as archive:
        assert not any(n.startswith(('backend/','deployment/')) for n in archive.namelist())
        if role=='agent':assert not any(n.startswith('three_mm_application_sdk/') for n in archive.namelist())
    assert not any('sqlalchemy' in n.lower() for n in files)


@pytest.mark.parametrize('role',component.ROLES)
def test_foreign_contract_target_digest_and_modified_payload_cannot_stage(role):
    blob,metadata=artifacts(role)[0]
    with tempfile.TemporaryDirectory(prefix='3mm-svc-deny-',dir='/tmp') as directory:
        store=component.ServiceStore(role,Path(directory)/'component',Path(directory)/'journal')
        with pytest.raises(ValueError):store.stage(blob,'0'*64)
        other='public-web' if role!='public-web' else 'session-worker'
        with pytest.raises(ValueError):component.validate_artifact(blob,digest(blob),other)
        parsed,files=component.validate_artifact(blob,digest(blob),role)
        parsed['binding']['contracts']={'unsupported':2}
        bad=component._archive(parsed,files)
        with pytest.raises(ValueError):store.stage(bad,digest(bad))
        parsed,files=component.validate_artifact(blob,digest(blob),role)
        files['service.pyz']+=b'corrupt'
        bad=component._archive(parsed,files)
        with pytest.raises(ValueError):store.stage(bad,digest(bad))
        assert store.target('current') is None


class Control:
    def __init__(self,store,root):
        self.store=store;self.root=root;self.process=None;self.calls=[];self.listening=True;self.fail_build=None
        with socket.socket() as free:free.bind(('127.0.0.1',0));self.port=free.getsockname()[1]
        self.state=root/'data';self.state.mkdir(mode=0o700)
        self.options={}
        if os.geteuid()==0:
            import pwd
            user=pwd.getpwnam('3mm-app' if store.component=='session-worker' else '3mm-public' if store.component=='public-web' else '3mm')
            self.options={'user':user.pw_uid,'group':user.pw_gid,'extra_groups':[]};os.chown(self.state,user.pw_uid,user.pw_gid)
        self.logs=(root/'service.log').open('ab')
    def active(self):return self.listening if self.store.component=='session-worker' else self.process is not None and self.process.poll() is None
    def stop(self):
        self.calls.append('stop');self.listening=False
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
    def start(self):
        self.calls.append('start');self.listening=True
        if self.store.component=='session-worker':return
        current=self.store.root/'current';command=[str(current/'.venv/bin/python'),'-I',str(current/'service.pyz')]
        command+=(['--host','127.0.0.1','--port',str(self.port),'--data-dir',str(self.state),'--hardware-profile','mock-linux','--role','standalone']
            if self.store.component=='agent' else ['--runtime-socket',str(self.root/'missing-runtime.sock'),'--host','127.0.0.1','--port',str(self.port)])
        self.process=subprocess.Popen(command,cwd=current,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},stdout=self.logs,stderr=self.logs,**self.options)
    def health(self,identifier,core):
        if self.store.component=='session-worker':
            current=self.store.root/'current'
            result=subprocess.run([str(current/'.venv/bin/python'),'-I',str(current/'service.pyz'),'--component-info'],
                env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},capture_output=True,text=True,check=True,timeout=10,**self.options)
            assert json.loads(result.stdout)['build_id']==identifier
        else:
            path='/component-health' if self.store.component=='agent' else '/__3mm_component__/health'
            deadline=time.monotonic()+8
            while True:
                if self.process.poll() is not None:raise AssertionError((self.root/'service.log').read_text())
                try:
                    value=component._http_identity(f'http://127.0.0.1:{self.port}'+path,timeout=1)
                    assert value=={'component':self.store.component,'build_id':identifier,'pid':self.process.pid};break
                except OSError:
                    if time.monotonic()>=deadline:raise
                    time.sleep(.05)
        if identifier==self.fail_build:raise ValueError('Candidate readiness fault')
        return {'core_pid':core['pid'],'core_process_generation':core['generation']}


@pytest.mark.parametrize('role',('agent','public-web','session-worker'))
def test_independent_component_update_rollback_and_bad_candidate_preserve_core(stack,role):
    s=stack;before=s.command('fingerprint');a,b=artifacts(role)
    with tempfile.TemporaryDirectory(prefix='3mm-svc-update-',dir='/tmp') as directory:
        root=Path(directory);root.chmod(0o755)
        store=component.ServiceStore(role,root/'component',root/'journal')
        store.bootstrap(a[0],digest(a[0]));control=Control(store,root)
        try:
            control.start();health=lambda identifier:control.health(identifier,s.command('fingerprint'))
            health(a[1]['build_id'])
            sentinel=control.state/'provider-data';sentinel.write_text('preserve me')
            old_pid=control.process.pid if control.process is not None else None
            store.activate(b[0],digest(b[0]),control=control,health=health,fingerprint=lambda:s.command('fingerprint'))
            assert store.target('current')==b[1]['build_id'] and store.target('previous')==a[1]['build_id']
            if old_pid is not None:assert control.process.pid!=old_pid
            assert sentinel.read_text()=='preserve me' and s.command('fingerprint')==before
            store.rollback(control=control,health=health,fingerprint=lambda:s.command('fingerprint'))
            assert store.target('current')==a[1]['build_id']
            control.fail_build=b[1]['build_id']
            with pytest.raises(ValueError,match='readiness fault'):
                store.activate(b[0],digest(b[0]),control=control,health=health,fingerprint=lambda:s.command('fingerprint'))
            assert store.target('current')==a[1]['build_id'] and store.pending() is None
            assert health(a[1]['build_id'])['core_pid']==before['pid']
            assert s.command('fingerprint')==before and s.http('/settings/read')[0]==200
            control.stop()
            with pytest.raises(ValueError,match='active component'):
                store.activate(b[0],digest(b[0]),control=control,health=health,fingerprint=lambda:s.command('fingerprint'))
        finally:control.stop();control.logs.close()


def test_units_use_independent_artifacts_and_filtered_agent_environment():
    for role,unit in [('agent','3mm-agent.service'),('public-web','3mm-public-web.service'),('session-worker','3mm-session-worker@.service')]:
        text=(ROOT/'deployment/systemd'/unit).read_text()
        assert '/opt/3mm/current' not in text
        assert '/opt/3mm-'+role+'/current/service.pyz' in text
    agent=(ROOT/'deployment/systemd/3mm-agent.service').read_text()
    assert 'EnvironmentFile=-/etc/3mm-agent/agent.env' in agent
    installer=(ROOT/'deployment/install-systemd.sh').read_text()
    assert 'agent_environment_backup_created' in installer and 'agent-environment-was-absent' in installer
    assert 'service_component agent bootstrap' in installer
    assert 'service_component public-web bootstrap' in installer
    assert 'service_component session-worker bootstrap' in installer


def test_service_contract_versions_reject_boolean_and_float_aliases(tmp_path):
    for wrong in (True,1.0):
        contracts=json.loads(json.dumps(component.CONTRACTS));contracts['agent']['device_contract']=wrong
        path=tmp_path/'contracts.json';path.write_text(json.dumps({'schema_version':1,'components':contracts}))
        with pytest.raises(ValueError,match='unsupported'):component.validate_contract(path)


@pytest.mark.parametrize('phase',['headers','body'])
def test_component_probe_trickle_cannot_hold_update_or_prevent_rollback(phase):
    import threading
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
    def serve():
        connection,_=listener.accept()
        with connection:
            connection.recv(4096)
            if phase=='body':connection.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 1024\r\n\r\n')
            for _ in range(30):
                try:connection.sendall(b'x');time.sleep(.04)
                except OSError:return
    worker=threading.Thread(target=serve,daemon=True);worker.start();start=time.monotonic()
    try:
        with pytest.raises(TimeoutError):component._http_identity(f'http://127.0.0.1:{listener.getsockname()[1]}/health',timeout=.15)
        assert time.monotonic()-start<.4
    finally:listener.close();worker.join(timeout=1)


def test_component_update_does_not_enable_a_service_stopped_during_staging(tmp_path):
    from deployment.component_store import ComponentStore
    class Store(ComponentStore):
        requires_active=True
        def stage(self,blob,sha):control.running=False;return 'b'*64
        def metadata(self,identifier):return {'build_id':identifier}
        def target(self,name):return 'a'*64 if name=='current' else None
    class Control:
        running=True
        def active(self):return self.running
        def stop(self):pytest.fail('Stopped service was mutated')
        def start(self):pytest.fail('Stopped service was enabled')
    control=Control();store=Store(tmp_path/'component',tmp_path/'journal')
    with pytest.raises(ValueError,match='active component'):
        store.activate(b'', 'b'*64,control=control,health=lambda build:None,fingerprint=lambda:{'pid':10,'generation':{}})
    assert store.pending() is None


def test_component_release_lock_conflicts_with_installer_and_rejects_symlinks(tmp_path):
    import fcntl
    from deployment.component_store import release_mutation_lock
    path=tmp_path/'release.lock'
    with path.open('w') as owner:
        fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            with release_mutation_lock(path):pytest.fail('Concurrent release mutation admitted')
    with release_mutation_lock(path):assert path.stat().st_mode & 0o077==0
    alias=tmp_path/'alias';alias.symlink_to(path)
    with pytest.raises(OSError):
        with release_mutation_lock(alias):pytest.fail('Symlinked mutation lock admitted')


def test_component_recovery_resets_only_its_systemd_failure_counter(monkeypatch):
    calls=[]
    monkeypatch.setattr(component.subprocess,'run',lambda args,**kwargs:calls.append(args))
    for role in component.ROLES:
        calls.clear();control=component.ServiceControl(role);control.start()
        assert calls[0][1]=='reset-failed' and calls[1][1:] == ['start',control.unit]
        assert all('3mm-core.service' not in call for call in calls)
        if role=='public-web':assert '3mm-public-web.service' in calls[0]


def test_core_is_favored_over_optional_workers_under_global_oom():
    assert 'OOMScoreAdjust=-500' in (ROOT/'deployment/systemd/3mm-core.service').read_text()
    for name in ('agent','public-web','session-worker@','platform-runtime','connector-worker','application-extension@'):
        assert 'OOMScoreAdjust=300' in (ROOT/('deployment/systemd/3mm-'+name+'.service')).read_text()


@pytest.fixture
def session_readiness(monkeypatch,tmp_path):
    from types import SimpleNamespace
    import pwd
    support=tmp_path/'identity.json';clock=[0.0];sleeps=[]
    monkeypatch.setattr(component,'Path',lambda value:support)
    monkeypatch.setattr(pwd,'getpwnam',lambda name:SimpleNamespace(pw_uid=os.geteuid()))
    monkeypatch.setattr(component.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(component.time,'time',lambda:1000.0+clock[0])
    monkeypatch.setattr(component.platform,'machine',lambda:'armv6l')
    monkeypatch.setattr(component,'fingerprint',lambda:{'pid':17,'generation':{'core':'unchanged'}})
    monkeypatch.setattr(component.subprocess,'check_output',lambda *args,**kwargs:'123\n')
    def sleep(delay):clock[0]+=delay;sleeps.append(delay)
    monkeypatch.setattr(component.time,'sleep',sleep)
    def payload(role,**overrides):
        value={'component':role,'build_id':'b'*64,'pid':123,'expires_at':1008.0+clock[0]}
        value.update(overrides);support.write_text(json.dumps(value));support.chmod(0o644)
    class Control:
        unit='owned-component.service'
        def active(self):return True
    def check(role):
        store=SimpleNamespace(component=role,metadata=lambda build:{'build_id':build})
        return component.health(store,Control(),'b'*64)
    return SimpleNamespace(path=support,clock=clock,sleeps=sleeps,payload=payload,check=check,sleep=sleep)


@pytest.mark.parametrize('role',['session-node','session-relay'])
def test_session_component_health_waits_for_first_support_file(session_readiness,monkeypatch,role):
    s=session_readiness
    def publish(delay):
        s.sleep(delay)
        if s.clock[0]>=.3:s.payload(role)
    monkeypatch.setattr(component.time,'sleep',publish)
    result=s.check(role)
    assert .3<=s.clock[0]<.5 and s.sleeps
    assert result=={'build_id':'b'*64,'core_pid':17,'core_process_generation':{'core':'unchanged'}}


@pytest.mark.parametrize('role',['session-node','session-relay'])
def test_session_component_health_waits_for_old_process_support_replacement(session_readiness,monkeypatch,role):
    s=session_readiness;s.payload(role,pid=122)
    def replace(delay):
        s.sleep(delay)
        if s.clock[0]>=.2:s.payload(role)
    monkeypatch.setattr(component.time,'sleep',replace)
    assert s.check(role)['core_pid']==17 and .2<=s.clock[0]<.4


@pytest.mark.parametrize('role',['session-node','session-relay'])
@pytest.mark.parametrize('wrong',[{'pid':122},{'build_id':'a'*64},{'expires_at':999.0},{'expires_at':float('inf')}])
def test_session_component_health_never_accepts_wrong_identity(session_readiness,role,wrong):
    s=session_readiness;s.payload(role,**wrong)
    with pytest.raises(ValueError,match='readiness deadline'):
        s.check(role)
    expected=90 if role=='session-node' else 20
    assert s.clock[0]==pytest.approx(expected) and max(s.sleeps)<=.1


@pytest.mark.parametrize('unsafe',['writable','symlink','malformed','hardlink'])
def test_session_component_health_refuses_untrusted_identity_without_polling(session_readiness,unsafe):
    s=session_readiness;s.payload('session-node')
    if unsafe=='writable':s.path.chmod(0o666)
    elif unsafe=='symlink':
        original=s.path.with_name('real.json');s.path.rename(original);s.path.symlink_to(original)
    elif unsafe=='hardlink':os.link(s.path,s.path.with_name('alias.json'))
    else:s.path.write_text('not JSON')
    with pytest.raises((ValueError,OSError)):
        s.check('session-node')
    assert s.clock[0]==0 and not s.sleeps
