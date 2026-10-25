"""Actual Core HTTP/admission process + independently updated Runtime processes."""
from contextlib import contextmanager
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import signal
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import urllib.request

import pytest
from sqlalchemy import create_engine,update,select
from sqlalchemy.orm import sessionmaker

from backend.tests.test_application_identity_read import (
    identity_app,activate_identity_grant,managed_installed,source_subject,
    source_installed,checkpoint_app,identity,
)
from backend.db.module import ModulePackage,ApplicationSyncCheckpoint,ApplicationExtensionInstallation
from backend.db.authority import CoreAuthorityGuard
from backend.services.application_platform import ApplicationPlatformServer,CoreRuntimeAuthorityServer
from backend.utils.jwt_utils import create_access_token
from three_mm_application_sdk import ApplicationPlatformClient,ApplicationPlatformError
from three_mm_platform_wire import process_generation
from three_mm_platform_runtime.server import probe_runtime
from deployment.platform_runtime_component import RuntimeStore,build_component,INPUTS

pytestmark=pytest.mark.skipif(os.name!='posix',reason='Real Linux processes, Unix credentials and immutable Runtime artifacts')
SOURCE=Path(__file__).resolve().parents[2]


def digest(value):return hashlib.sha256(value).hexdigest()

def core_digest():
    files={}
    for package in ('backend','three_mm_protocol','three_mm_application_sdk','three_mm_platform_wire'):
        for path in (SOURCE/package).rglob('*.py'):
            if not {'tests','__pycache__'}&set(path.parts):files[path.relative_to(SOURCE).as_posix()]=digest(path.read_bytes())
    return digest(json.dumps(files,sort_keys=True).encode())


def _serve_core(state,base,runtime_uid,core_uid,core_gid,pipe):
    try:
        if os.geteuid()==0:
            os.setgroups([runtime_uid]);os.setgid(core_gid);os.setuid(core_uid)
        import backend.main as main
        import backend.database as database
        from backend.utils.db_utils import get_db
        from backend.services.application_authority_management import ApplicationAuthorityManager
        from backend.services.application_authority_keys import CoreReviewKeyStore
        import uvicorn
        settings=main.app_settings.model_copy(deep=True)
        settings.backend.uploads_dir=base/'core/uploads'
        settings.applications.key_root=base/'core/transport'
        settings.applications.runtime_socket=base/'runtime/runtime.sock'
        settings.applications.root=base/'applications'
        settings.applications.authority_socket=base/'authority/gate.sock'
        settings.applications.application_response_socket=base/'responses/runtime.sock'
        main.app_settings=settings
        database.SessionLocal=sessionmaker(bind=state.engine)
        def dbs():
            with database.SessionLocal() as db:yield db
        main.app.dependency_overrides[get_db]=dbs;main.app.dependency_overrides[database.get_db]=dbs
        main.get_db=dbs;main.init_db=lambda:None
        # No outbound update check or provider delivery is needed for this proof.
        class Idle:
            _worker_task=None
            async def start(self):
                self.loop=__import__("asyncio").get_running_loop()
            async def stop(self):pass
        main.system_update_check_manager=Idle()
        # Fault only this owned test Core, after durable send and before FD handoff.
        from backend.services import application_events as event_broker
        sender=event_broker._send_event_invocation
        def send_event(prepared,request_id):
            origin=sender(prepared,request_id)
            if (base/'crash-before-handoff').exists():os._exit(17)
            return origin
        event_broker._send_event_invocation=send_event
        group=__import__('grp').getgrgid(runtime_uid).gr_name if runtime_uid!=os.getuid() else 'missing-test-group'
        original_factory=main._runtime_authority
        if runtime_uid!=core_uid:
            settings.applications.runtime_user=__import__('pwd').getpwuid(runtime_uid).pw_name
            gate=original_factory()  # The real production UID/group checks, no test authority substitute.
        else:
            # Same-user functional lab is supplemented by the separate-user root proof.
            gate=CoreRuntimeAuthorityServer(settings.applications.authority_socket,settings.applications.key_root,
                runtime_uid=runtime_uid,group=group)
        from backend.services import application_connector_transport as connector_broker
        connector_sender=connector_broker.begin_connector
        def begin_connector(*args,**kwargs):
            result=connector_sender(*args,**kwargs)
            if (base/'crash-before-connector-handoff').exists():os._exit(18)
            return result
        connector_broker.begin_connector=begin_connector
        if hasattr(state,'connector_worker_uid'):
            gate.connector_worker_uid=state.connector_worker_uid
            gate.connector_worker_path=base/'connectors/worker.sock'
        if getattr(state,'response_relay',False):
            from backend.routes import application_operations, application_extensions
            settings.applications.runtime_user=__import__('pwd').getpwuid(runtime_uid).pw_name
            application_operations.get_settings=lambda:settings
            application_extensions.get_settings=lambda:settings
        main._runtime_authority=lambda:gate
        server=uvicorn.Server(uvicorn.Config(main.app,host='127.0.0.1',port=0,log_level='error',access_log=False))
        worker=threading.Thread(target=server.run,daemon=True);worker.start()
        deadline=time.monotonic()+15
        while not server.started:
            if not worker.is_alive() or time.monotonic()>deadline:raise RuntimeError('Core test process failed startup')
            time.sleep(.02)
        port=server.servers[0].sockets[0].getsockname()[1]
        pipe.send({'port':port,'pid':os.getpid(),'digest':core_digest()})
        while worker.is_alive():
            if not pipe.poll(.1):continue
            action=pipe.recv()
            if action=='stop':break
            if action=='revoke':
                state.manager.revoke(1,actor_token=state.token,request_id=identity(),
                    expected_revision=state.manager.inspect(1)['grant_record_revision'])
            elif action=='compatibility':
                with state.engine.begin() as db:db.execute(update(ApplicationExtensionInstallation).values(authority_mode='compatibility'))
            elif action=='recover':
                with state.engine.begin() as db:db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            elif action=='authority_stop':gate.stop()
            elif action=='authority_start':gate.start()
            elif action=='event_enqueue':
                from backend.db.device import DeviceEvent
                from backend.services.application_events import enqueue_application_event
                with database.SessionLocal() as db:
                    event=db.scalar(select(DeviceEvent).order_by(DeviceEvent.id.desc()).limit(1))
                    enqueue_application_event(db,event,settings.applications)
            elif action=='event_expire':
                from backend.db.module import ApplicationEventDelivery
                with database.SessionLocal() as db:
                    for delivery in db.scalars(select(ApplicationEventDelivery).where(ApplicationEventDelivery.status=='delivering')):
                        delivery.dispatch_metadata={**delivery.dispatch_metadata,'deadline_ms':0}
                    db.commit()
            elif action=='event_retry':
                from backend.services.application_events import request_application_event_retry
                with database.SessionLocal() as db:request_application_event_retry(db)
            elif action=='threadpool_tokens':
                import asyncio,anyio
                async def tokens():return anyio.to_thread.current_default_thread_limiter().borrowed_tokens
                pipe.send(asyncio.run_coroutine_threadsafe(tokens(),main.system_update_check_manager.loop).result(timeout=2));continue
            elif action=='count':
                with state.engine.connect() as db:pipe.send(db.execute(select(ApplicationSyncCheckpoint.id)).all());continue
            elif action!='fingerprint':raise ValueError('Unknown test control command')
            pipe.send({'pid':os.getpid(),'generation':process_generation(os.getpid(),core_uid),
                'release':str(SOURCE),'metadata_sha256':core_digest()})
        server.should_exit=True;worker.join(timeout=10)
    except BaseException as error:
        try:pipe.send({'error':repr(error)})
        except OSError:pass
        raise
    finally:pipe.close()


class RuntimeProcesses:
    def __init__(self,store,base,core_uid,runtime_uid):
        self.store=store;self.base=base;self.core_uid=core_uid;self.runtime_uid=runtime_uid
        self.process=None;self.log=(base/'runtime.log').open('ab');self.calls=[]
    def active(self):return self.process is not None and self.process.poll() is None
    def stop(self):
        self.calls.append('stop-runtime')
        if not self.active():return
        self.process.terminate()
        try:self.process.wait(timeout=.5)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
    def start(self):
        self.calls.append('start-runtime');assert not self.active()
        path=self.store.root/'current'
        command=[str(path/'.venv/bin/python'),'-I',str(path/'runtime.pyz'),
            '--socket',str(self.base/'runtime/runtime.sock'),'--authority-socket',str(self.base/'authority/gate.sock'),
            '--core-uid',str(self.core_uid)]
        if getattr(self,'event_worker',False): command+=['--events']
        if getattr(self,'response_path',None) is not None:
            command+=['--response-socket',str(self.response_path)]
            if os.geteuid()==0:command+=['--response-group',__import__('grp').getgrgid(self.core_uid).gr_name]
        if getattr(self,'public_web_path',None) is not None:
            command+=['--public-web-socket',str(self.public_web_path)]
        kwargs={}
        if os.geteuid()==0:
            kwargs={'user':self.runtime_uid,'group':self.runtime_uid,'extra_groups':[]}
            command+=['--socket-group',__import__('grp').getgrgid(self.core_uid).gr_name]
        self.process=subprocess.Popen(command,cwd=path,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},
            stdout=self.log,stderr=self.log,**kwargs)
    def health(self,identifier):
        deadline=time.monotonic()+3
        while True:
            try:return probe_runtime(self.base/'runtime/runtime.sock',expected_uid=self.runtime_uid,expected_build=identifier,require_public_web=getattr(self,'public_web_path',None) is not None,require_events=getattr(self,'event_worker',False),require_responses=getattr(self,'response_path',None) is not None)
            except (OSError,ValueError):
                if time.monotonic()>deadline:raise
                time.sleep(.03)


@pytest.fixture
def stack(identity_app,monkeypatch):
    activate_identity_grant(identity_app)
    with core_stack(identity_app,monkeypatch) as state:yield state


@contextmanager
def core_stack(state,monkeypatch):
    with tempfile.TemporaryDirectory(prefix='p4-',dir='/tmp') as directory:
        base=Path(directory);base.chmod(0o755)
        core_uid=1000 if os.geteuid()==0 else os.getuid()
        runtime_uid=65534 if os.geteuid()==0 else os.getuid()
        core_gid=core_uid
        core=base/'core';core.mkdir(mode=0o700)
        original_uploads=state.root
        uploads=core/'uploads';shutil.copytree(original_uploads,uploads)
        keys=core/'review';shutil.copytree(state.key_directory,keys)
        database=core/'3mm.db'
        with state.engine.connect() as connection,sqlite3.connect(database) as destination:
            connection.connection.driver_connection.backup(destination)
        state.engine=create_engine(f'sqlite:///{database}',connect_args={'check_same_thread':False})
        state.root=uploads;state.key_directory=keys
        state.manager.engine=state.engine;state.manager.uploads_root=uploads
        state.manager.keys._engine=state.engine;state.manager.keys._directory=keys
        state.keys._engine=state.engine;state.keys._directory=keys
        with state.engine.begin() as db:
            rows=db.execute(select(ModulePackage.id,ModulePackage.file_path)).all()
            for identifier,path in rows:db.execute(update(ModulePackage).where(ModulePackage.id==identifier).values(file_path=str(uploads/Path(path).relative_to(original_uploads))))
        (core/'transport').mkdir(mode=0o700);(core/'transport'/('a'*24+'.key')).write_bytes(b's'*32)
        (core/'transport'/('a'*24+'.key')).chmod(0o600);database.chmod(0o600)
        (base/'authority').mkdir(mode=0o750);(base/'runtime').mkdir(mode=0o755)
        if os.geteuid()==0:
            for path in [core,*core.rglob('*')]:os.chown(path,core_uid,core_gid)
            os.chown(base/'authority',core_uid,runtime_uid)
            os.chown(base/'runtime',runtime_uid,core_gid);(base/'runtime').chmod(0o2750)
        parent,child=multiprocessing.get_context('fork').Pipe()
        process=multiprocessing.get_context('fork').Process(target=_serve_core,args=(state,base,runtime_uid,core_uid,core_gid,child))
        process.start();child.close()
        assert parent.poll(20),'Core did not start';ready=parent.recv();assert 'error' not in ready,ready
        store=RuntimeStore(base/'components',base/'updates')
        control=RuntimeProcesses(store,base,core_uid,runtime_uid)
        def command(action):
            parent.send(action);assert parent.poll(10),'Core control timeout'
            value=parent.recv();assert not isinstance(value,dict) or 'error' not in value,value
            return value
        def http(path='/ready',headers=None):
            request=urllib.request.Request(f'http://127.0.0.1:{ready["port"]}'+path,headers=headers or {})
            with urllib.request.urlopen(request,timeout=2) as response:return response.status,json.load(response)
        client=ApplicationPlatformClient(base/'runtime/runtime.sock','a'*24,b's'*32)
        def artifact(name,broken=False):
            source=base/('source-'+name)
            for item in INPUTS:
                target=source/item;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/item,target)
            path=source/'three_mm_platform_runtime/server.py'
            text=path.read_text()+'\n# '+name+'\n'
            if broken:text=text.replace('try:runtime.start();runtime.serve_forever()','try:raise RuntimeError("injected bad artifact")')
            path.write_text(text)
            return build_component(source)
        s=type('Stack',(),{})();s.base=base;s.core=process;s.control=control;s.store=store;s.client=client
        s.url=lambda:"http://127.0.0.1:"+str(ready["port"])
        s.command=command;s.http=http;s.artifact=artifact;s.runtime_uid=runtime_uid;s.core_uid=core_uid
        def restart_core():
            nonlocal process,parent,ready
            if process.is_alive():process.kill();process.join(timeout=3)
            parent.close()
            parent,child=multiprocessing.get_context('fork').Pipe()
            process=multiprocessing.get_context('fork').Process(target=_serve_core,
                args=(state,base,runtime_uid,core_uid,core_gid,child))
            process.start();child.close()
            assert parent.poll(20);ready=parent.recv();assert 'error' not in ready,ready
            s.core=process
            return ready
        s.restart_core=restart_core
        s.state=state
        s.admin={'Authorization':'Bearer '+create_access_token('1',{'role':'admin'})}
        try:yield s
        finally:
            control.stop();control.log.close()
            if process.is_alive():
                try:parent.send('stop')
                except OSError:pass
                process.join(timeout=10)
            if process.is_alive():process.kill();process.join(timeout=3)
            parent.close();state.engine.dispose()


def activate(s,artifact):
    blob,metadata=artifact
    return s.store.activate(blob,digest(blob),control=s.control,health=s.control.health,
                            fingerprint=lambda:s.command('fingerprint'))


def test_independent_update_rollback_kill_and_hang_preserve_real_core(stack,monkeypatch):
    s=stack;before=s.command('fingerprint');a=s.artifact('a');b=s.artifact('b');bad=s.artifact('bad',broken=True)
    activate(s,a);assert s.http()[0]==200
    first=s.client.discover_platform();assert s.client.get_installation_identity()['sdk_version']=='1.3'
    request_id='platform_'+identity()
    s.client._exchange('installation.identity.get',{},request_id)
    pid=s.control.process.pid;activate(s,b)
    with pytest.raises(ApplicationPlatformError) as error:s.client._exchange('installation.identity.get',{},request_id)
    assert error.value.reason=='request_replayed'
    assert s.control.process.pid!=pid and s.command('fingerprint')==before
    assert s.client.discover_platform()['transport_generation']!=first['transport_generation']
    s.store.rollback(control=s.control,health=s.control.health,fingerprint=lambda:s.command('fingerprint'))
    assert s.store.target('current')==a[1]['build_id'] and s.command('fingerprint')==before
    with pytest.raises((OSError,ValueError)):activate(s,bad)
    assert s.store.target('current')==a[1]['build_id'] and s.command('fingerprint')==before
    assert s.client.get_installation_identity()['sdk_version']=='1.3'
    s.control.process.kill();s.control.process.wait(timeout=3)
    assert s.http()[0]==200 and s.http('/settings/read')[0]==200
    assert s.http('/api/v1/diagnostics/components',headers=s.admin)[0]==200
    with pytest.raises(ApplicationPlatformError):s.client.get_installation_identity()
    activate(s,b)
    os.kill(s.control.process.pid,signal.SIGSTOP)
    monkeypatch.setattr('three_mm_application_sdk.REQUEST_TIMEOUT_SECONDS',.15)
    with pytest.raises(ApplicationPlatformError) as error:s.client.get_installation_identity()
    assert error.value.reason=='deadline_exceeded' and s.http()[0]==200
    activate(s,a);assert s.command('fingerprint')==before
    assert set(s.control.calls)=={'stop-runtime','start-runtime'}


def test_revoke_recovery_and_authority_loss_cannot_fall_back_or_cache_rights(stack):
    s=stack;activate(s,s.artifact('a'))
    assert s.client.get_installation_identity()['sdk_version']=='1.3'
    old=ApplicationPlatformClient(s.base/'core/platform.sock','a'*24,b's'*32)
    with pytest.raises(ApplicationPlatformError):old.get_installation_identity()
    s.command('revoke')
    with pytest.raises(ApplicationPlatformError):s.client.get_installation_identity()
    before=s.client.discover_platform();s.command('recover');after=s.client.discover_platform()
    assert before['recovery_generation']!=after['recovery_generation']
    with pytest.raises(ApplicationPlatformError):s.client.get_installation_identity()
    s.command('authority_stop')
    with pytest.raises(ApplicationPlatformError):s.client.discover_platform()
    assert s.http()[0]==200


@pytest.mark.skipif(os.name!='posix' or os.geteuid()!=0,reason='Explicit isolated root proof for distinct unprivileged OS principals')
def test_distinct_principals_cannot_read_core_data_or_bypass_private_admission(stack):
    s=stack;assert s.core_uid!=s.runtime_uid and s.runtime_uid>0
    artifact=s.artifact('separate');activate(s,artifact)
    assert s.client.get_installation_identity()['sdk_version']=='1.3'
    assert (s.base/'runtime/runtime.sock').stat().st_gid==s.core_uid
    python=s.store.root/'current/.venv/bin/python'
    result=subprocess.run([str(python),'-I','-c','import os; assert os.getgroups()==[]'],
        user=s.runtime_uid,group=s.runtime_uid,extra_groups=[],capture_output=True,timeout=5)
    assert result.returncode==0,result.stderr
    script='from pathlib import Path; Path('+repr(str(s.base/'core/3mm.db'))+').read_bytes()'
    result=subprocess.run([str(python),'-I','-c',script],user=s.runtime_uid,group=s.runtime_uid,extra_groups=[],capture_output=True,timeout=5)
    assert result.returncode!=0 and b'PermissionError' in result.stderr
    script='from pathlib import Path; Path('+repr(str(s.base/'core/transport'/('a'*24+'.key')))+').read_bytes()'
    result=subprocess.run([str(python),'-I','-c',script],user=s.runtime_uid,group=s.runtime_uid,extra_groups=[],capture_output=True,timeout=5)
    assert result.returncode!=0 and b'PermissionError' in result.stderr
    # Root can traverse DAC but is still not the Runtime principal admitted by Core.
    bypass=ApplicationPlatformClient(s.base/'authority/gate.sock','a'*24,b's'*32)
    with pytest.raises(ApplicationPlatformError):bypass.get_installation_identity()
    # Runtime peer identity does not substitute for a current application grant.
    import hmac
    request={'version':1,'request_id':'platform_'+identity(),'timestamp':int(time.time()),
        'instance_id':'a'*24,'action':'checkpoint.put','checkpoint_id':'forbidden',
        'expected_revision':0,'value':{}}
    from three_mm_platform_wire import canonical
    request['signature']=hmac.new(b's'*32,canonical(request),hashlib.sha256).hexdigest()
    encoded=json.dumps(request).encode()+b'\n'
    script=('import socket; s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(2);'
        's.connect('+repr(str(s.base/'authority/gate.sock'))+');s.sendall('+repr(b'\0'+encoded)+');'
        'import json; r=json.loads(s.recv(4096));assert r["ok"] is False and r["reason"]=="operation_denied";s.close()')
    result=subprocess.run([str(python),'-I','-c',script],user=s.runtime_uid,group=s.runtime_uid,
        extra_groups=[],capture_output=True,timeout=5)
    assert result.returncode==0,result.stderr
    assert s.command('count')==[]
    before=s.command('fingerprint');activate(s,s.artifact('separate-b'))
    assert before==s.command('fingerprint') and s.http()[0]==200


def test_runtime_identity_never_uses_compatibility_identity_initialization(stack):
    s=stack;activate(s,s.artifact('compatibility'))
    assert s.client.get_installation_identity()['sdk_version']=='1.3'
    s.command('compatibility')
    with pytest.raises(ApplicationPlatformError,match='Scoped installation identity read is unavailable'):
        s.client.get_installation_identity()
    assert s.http()[0]==200


@pytest.mark.parametrize("identity_app", [("1.3", True)], indirect=True)
def test_real_checkpoint_mutation_replay_and_revocation_share_the_only_runtime_path(stack):
    s=stack;before=s.command('fingerprint');activate(s,s.artifact('mutations'))
    assert not (s.base/'core/platform.sock').exists()
    assert s.client.get_checkpoint('catalog')['revision']==0
    saved=s.client.put_checkpoint('catalog',expected_revision=0,value={'step':'one'})
    assert saved['revision']==1 and s.client.get_checkpoint('catalog')==saved
    with pytest.raises(ApplicationPlatformError):
        s.client.put_checkpoint('cursor',expected_revision=0,value={})
    with pytest.raises(ApplicationPlatformError):
        s.client.put_checkpoint('catalog',expected_revision=0,value={'step':'duplicate'})
    activate(s,s.artifact('mutations-b'))
    assert s.client.get_checkpoint('catalog')==saved and s.command('fingerprint')==before
    s.command('revoke')
    with pytest.raises(ApplicationPlatformError):s.client.get_checkpoint('catalog')
    with pytest.raises(ApplicationPlatformError):s.client.put_checkpoint('catalog',expected_revision=1,value={})
    assert len(s.command('count'))==1 and s.http()[0]==200
