"""Browser admission -> signed SDK -> actual native host and response FD relay."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

import backend.database
import backend.config
from backend.config import ApplicationRuntimeSettings
from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.module import ApplicationExtensionInstallation as Installation, ApplicationPermissionGrant
from backend.db.session import UserSession
from backend.db.user import User
from backend.db.audit_log import AuditLog
from backend.routes import application_extensions as routes, auth_refresh
from backend.services import application_delegations as service
from backend.services.application_platform import ApplicationPlatformServer
from backend.tests.test_application_ui_authority import ui_app, managed_installed, source_subject, source_installed, adopt
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token, decode_token
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError
from three_mm_platform_runtime.responses import ApplicationResponses

pytestmark = [pytest.mark.skipif(os.name != 'posix', reason='Real Linux signed Unix IPC'),
    pytest.mark.parametrize('ui_app', ['delegations'], indirect=True)]


@pytest.fixture
def stack(ui_app, monkeypatch):
    import pwd
    s = ui_app
    adopt(s)
    monkeypatch.setattr(backend.database, 'SessionLocal', sessionmaker(s.engine))
    with Session(s.engine) as db, db.begin():
        db.add(ApplicationPermissionGrant(application_installation_id=1, user_id=2, permission_id='records_manage'))
        s.subject = db.get(User, 2).subject_id
    with tempfile.TemporaryDirectory(prefix='c2d-', dir='/tmp') as temporary:
        root = Path(temporary); s.native_root = root
        for name in ('data','run'): (root/name).mkdir()
        secret = b's'*32; (root/('a'*24+'.key')).write_bytes(secret)
        metadata = dict(module_id=s.validated.manifest.module_id, version=s.validated.manifest.version,
            sha256=s.validated.sha256, instance_id='a'*24, storage=s.validated.application_extension.storage.model_dump(mode='json'),
            operations=[op.model_dump(mode='json') for op in s.validated.application_extension.operations])
        with Session(s.engine) as db: metadata['configuration']=db.get(Installation,1).configuration
        (root/'metadata.json').write_text(json.dumps(metadata))
        # A separate process runs the production host/SDK, not a mocked handler.
        code = '''import json,sys,time
from pathlib import Path
from three_mm_runtime.application_host import _serve_requests
r=Path(sys.argv[1])
class Service:
 def handle(self,op,payload,context):
  value={'operation':op,'payload':payload,'user_id':context.actor.user_id,'subject_id':context.actor.subject_id,
   'permissions':context.permission_ids,'admin':context.actor.platform_administrator,
   'executor':context.executor.model_dump(mode='json'),'delegation':context.delegation.model_dump(mode='json')}
  with (r/'calls').open('a') as out: out.write(json.dumps(value)+'\\n')
  if (r/'wait').exists():
   until=time.monotonic()+3
   while not (r/'release').exists() and time.monotonic()<until: time.sleep(.01)
  if (r/'fail').exists(): raise RuntimeError('lost after effect')
  return {}
_serve_requests(json.loads((r/'metadata.json').read_text()),r,b's'*32,Service(),None)
'''
        process = subprocess.Popen([sys.executable,'-c',code,str(root)], stderr=subprocess.PIPE)
        platform = ApplicationPlatformServer(root/'core.sock',root,group='missing-test-group')
        responses = ApplicationResponses(root/'response.sock',root/'unused.sock',core_uid=os.geteuid())
        worker = None
        try:
            deadline=time.monotonic()+5
            while not (root/'run/service.sock').exists() and time.monotonic()<deadline:
                if process.poll() is not None: pytest.fail(process.stderr.read().decode())
                time.sleep(.01)
            assert (root/'run/service.sock').exists()
            responses.start(); worker=threading.Thread(target=responses.serve_forever,daemon=True); worker.start()
            settings=ApplicationRuntimeSettings(root=root,key_root=root,runtime_user=pwd.getpwuid(os.geteuid()).pw_name,
                application_response_socket=root/'response.sock',helper_socket=root/'unused.sock')
            monkeypatch.setattr(backend.config,'get_settings',lambda:type('Settings',(),{'applications':settings})())
            monkeypatch.setattr(routes,'get_settings',backend.config.get_settings)
            with s.engine.begin() as db: db.execute(update(Installation).values(socket_path=str(root/'run/service.sock')))
            platform.start()
            s.sdk=ApplicationPlatformClient(platform.socket_path,'a'*24,secret)
            app=FastAPI(); app.include_router(routes.router); app.include_router(auth_refresh.router,prefix='/api')
            def session():
                with Session(s.engine) as db: yield db
            app.dependency_overrides[get_db]=session
            s.binding=dict(host_version=1,entrypoint_id='operations',artifact_sha256=s.validated.sha256,built_ui_sha256=s.build.built_ui_sha256)
            s.base='/api/v1/application-extensions/'+s.validated.manifest.module_id
            s.headers={'Authorization':'Bearer '+s.user_token}
            with TestClient(app) as client:
                s.client=client
                yield s
        finally:
            platform.stop(); responses.close()
            if worker: worker.join(timeout=3)
            process.terminate(); process.wait(timeout=5); process.stderr.close()


def create(s, identifier='c'*32, **changes):
    return s.client.post(s.base+'/ui-host/operations/delegations',headers=s.headers,
        json=dict(request_id=identifier,operation_id='pulse_ui',payload={},ttl_seconds=60,ui_context=s.binding)|changes)


def calls(s):
    path=s.native_root/'calls'
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_real_worker_preserves_human_and_executor_and_consumes_once(stack):
    s=stack
    access=s.client.get(s.base+'/ui-host/operations/access',headers=s.headers,params={
        'artifact_sha256':s.validated.sha256,'built_ui_sha256':s.build.built_ui_sha256})
    assert access.status_code==200,access.text
    assert access.json()['actor']['subject_id']==s.subject
    assert access.json()['delegated_operation_ids']==['pulse_ui']
    pending=create(s,payload={'value':7}); assert pending.status_code==200,pending.text
    assert pending.json()['status']=='pending' and not calls(s)
    assert create(s,payload={'value':7}).json()==pending.json()
    assert create(s,payload={'value':8}).status_code==409
    assert create(s,payload={'value':7},ttl_seconds=90).status_code==409
    result=s.sdk.execute_delegation('c'*32)
    assert result['status']=='succeeded', result
    assert s.sdk.execute_delegation('c'*32)==result
    assert s.sdk.lookup_delegation('c'*32)==result
    assert s.client.get(s.base+'/delegations/'+'c'*32,headers=s.headers).json()==result
    recorded=calls(s); assert len(recorded)==1
    assert recorded[0]['user_id']==2 and recorded[0]['subject_id']==s.subject
    assert recorded[0]['payload']=={'value':7}
    assert recorded[0]['permissions']==['records_manage'] and recorded[0]['admin'] is False
    assert recorded[0]['executor']==result['executor']
    assert recorded[0]['delegation']['initiator']==result['initiator']
    assert recorded[0]['delegation']['redelegation_allowed'] is False
    with Session(s.engine) as db:
        audits=db.scalars(select(AuditLog).where(AuditLog.action.like('APPLICATION_DELEGATION_%'))).all()
        assert len(audits)==3
        assert s.user_token not in str([a.changes for a in audits])


@pytest.mark.parametrize('state',['cancelled','expired','boot','unsupported','stale_host','permission','session','login','user','subject','epoch','configuration','grant','key','ui'])
def test_no_dispatch_after_cancel_expiry_or_authority_change(stack,monkeypatch,state):
    s=stack; response=create(s); assert response.status_code==200,response.text
    if state=='cancelled':
        assert s.client.post(s.base+'/delegations/'+'c'*32+'/cancel',headers=s.headers).json()['status']=='cancelled'
        assert s.sdk.execute_delegation('c'*32)['status']=='cancelled'
    elif state in {'expired','boot'}:
        original=service.authority._clock
        monkeypatch.setattr(service.authority,'_clock',lambda:('different-boot',original()[1]) if state=='boot' else (original()[0],original()[1]+400_000))
        assert s.sdk.execute_delegation('c'*32)['status']=='expired'
    elif state in {'unsupported','stale_host'}:
        original=service.ApplicationServiceClient.invoke
        def changed(*a,**kw):
            value=original(*a,**kw)
            if state=='unsupported': value.pop('operation_delegation_contract')
            else: value['configuration_sha256']='f'*64
            return value
        monkeypatch.setattr(service.ApplicationServiceClient,'invoke',changed)
        with pytest.raises(ApplicationPlatformError): s.sdk.execute_delegation('c'*32)
    else:
        with Session(s.engine) as db,db.begin():
            if state=='permission': db.execute(delete(ApplicationPermissionGrant))
            elif state=='session': db.get(UserSession,2).is_active=False
            elif state=='login': db.get(UserSession,2).token=create_access_token('2',{'sid':2,'token_version':0})
            elif state=='user': db.get(User,2).is_blocked=True
            elif state=='subject': db.get(User,2).subject_id='usr_'+'f'*32
            elif state=='epoch': db.get(Installation,1).authority_epoch='f'*32
            elif state=='configuration': db.get(Installation,1).configuration={}
        if state=='grant':
            status=s.manager.inspect(1)
            s.manager.revoke(1,actor_token=s.token,request_id='f'*32,expected_revision=status['grant_record_revision'])
        if state=='key': (s.native_root/('a'*24+'.key')).write_bytes(b'x'*32)
        if state=='ui': (s.build.path/'assets/operations.mjs').write_text('changed')
        with pytest.raises(ApplicationPlatformError): s.sdk.execute_delegation('c'*32)
    assert not calls(s)


def test_refresh_keeps_login_identity_and_cannot_extend_issued_intent(stack):
    s=stack; pending=create(s).json()
    refreshed=s.client.post('/api/user/refresh',headers=s.headers)
    assert refreshed.status_code==200,refreshed.text
    token=refreshed.json()['token']
    assert decode_token(token)['jti']==decode_token(s.user_token)['jti']
    s.headers={'Authorization':'Bearer '+token}
    result=s.sdk.execute_delegation('c'*32)
    assert result['status']=='succeeded' and result['expires_at']==pending['expires_at']
    # Replacing a login, even with the same numeric session and user, revokes
    # the old login's refresh and receipt access.
    with Session(s.engine) as db,db.begin(): db.get(UserSession,2).token=create_access_token('2',{'sid':2,'token_version':0})
    assert s.client.post('/api/user/refresh',headers=s.headers).status_code==401
    assert s.client.get(s.base+'/delegations/'+'c'*32,headers=s.headers).status_code==401


@pytest.mark.parametrize('fault',['lost','revoked','restart'])
def test_uncertain_outcome_is_never_replayed(stack,monkeypatch,fault):
    s=stack; assert create(s).status_code==200
    if fault=='lost': (s.native_root/'fail').touch()
    if fault=='revoked': (s.native_root/'wait').touch()
    if fault=='restart':
        with s.manager.keys.locked() as key,Session(s.engine) as db,service.authority_transaction(db):
            row,value=service._load(db,s.manager,key,1,'c'*32)
            value.update(state='running'); value['data']['executor_generation']='previous-core'
            service.authority._save(db,key,service.KIND,row,value)
        assert s.sdk.execute_delegation('c'*32)['status']=='unknown'
        assert not calls(s); return
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(s.sdk.execute_delegation,'c'*32)
        if fault=='revoked':
            deadline=time.monotonic()+3
            while not calls(s) and time.monotonic()<deadline: time.sleep(.01)
            assert calls(s)
            with s.engine.begin() as db: db.execute(delete(ApplicationPermissionGrant))
            (s.native_root/'release').touch()
        result=future.result(timeout=6)
    assert result['status']=='unknown' and result['result'] is None
    if fault=='revoked':
        with Session(s.engine) as db,db.begin(): db.add(ApplicationPermissionGrant(application_installation_id=1,user_id=2,permission_id='records_manage'))
    assert s.sdk.execute_delegation('c'*32)['status']=='unknown'
    assert len(calls(s))==1


def test_concurrent_claims_never_dispatch_twice(stack):
    s=stack; assert create(s).status_code==200
    def consume(identifier):
        try: return s.sdk.execute_delegation(identifier)['status']
        except ApplicationPlatformError: return 'busy'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(consume,['c'*32,'c'*32]))
    assert 'succeeded' in results and set(results)<={'running','succeeded','busy'}
    assert s.sdk.lookup_delegation('c'*32)['status']=='succeeded'
    assert len(calls(s))==1


def test_changed_native_peer_is_refused_before_operation_bytes(stack,monkeypatch):
    s=stack; assert create(s).status_code==200
    invoke=service.ApplicationServiceClient.invoke
    monkeypatch.setattr(service.ApplicationServiceClient,'invoke',lambda *a,**kw:invoke(*a,**kw)|{'pid':os.getpid()})
    assert s.sdk.execute_delegation('c'*32)['status']=='unknown'
    assert not calls(s)


def test_browser_cannot_choose_identity_or_delegate_an_undeclared_operation(stack):
    s=stack
    assert create(s,actor={'user_id':1}).status_code==422
    assert create(s,executor={'module_id':'org.example.other'}).status_code==422
    assert create(s,ui_context=s.binding|{'actor':{'user_id':1}}).status_code==422
    assert create(s,operation_id='health').status_code==403
    assert not calls(s)
    with Session(s.engine) as db: assert not db.scalars(select(Action).where(Action.request_id=='c'*32)).all()


def test_a_different_valid_login_cannot_read_or_cancel_the_intent(stack):
    s=stack; assert create(s).status_code==200
    token=create_access_token('2',{'sid':9,'token_version':0})
    with Session(s.engine) as db,db.begin():
        db.add(UserSession(id=9,user_id=2,token=token,is_active=True,expires_at=datetime.utcnow()+timedelta(hours=1)))
    auth={'Authorization':'Bearer '+token}
    assert s.client.get(s.base+'/delegations/'+'c'*32,headers=auth).status_code==403
    assert s.client.post(s.base+'/delegations/'+'c'*32+'/cancel',headers=auth).status_code==403
    assert s.sdk.execute_delegation('c'*32)['status']=='succeeded'
    assert len(calls(s))==1
