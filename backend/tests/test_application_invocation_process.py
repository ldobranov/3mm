"""Real HTTP human/kiosk response delegation, revocation and no replay."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
import time
import urllib.request
import urllib.error

import pytest
from sqlalchemy import delete,update
from backend.db.base import Base
from backend.db.module import ApplicationPermissionGrant,ApplicationKioskTerminal,ApplicationExtensionInstallation
from backend.db.user import User
from backend.tests.test_application_health_process import (
    health_stack,identity_app,managed_installed,source_subject,source_installed,checkpoint_app,
    core_stack,activate,activate_identity_grant,wait_for,
)
from backend.utils.jwt_utils import create_access_token

pytestmark=pytest.mark.skipif(os.name!='posix',reason='Real Unix processes and descriptor transfer')


@pytest.fixture
def health_core(identity_app,monkeypatch,request):
    from backend.services import application_invocation_relay as relay
    from backend.tests.test_module_packages import application_definition
    from backend.tests.test_application_identity_authority import store_identity_package
    import backend.tests.test_application_health_process as peer
    monkeypatch.setattr(peer,'SERVICE',peer.SERVICE.replace("else {'status':'ready'})", "else ({'status':'ready'} if request['operation_id']=='health' else {}))"))
    state=identity_app
    definition=state.validated.application_extension.model_dump(mode='json');standard=application_definition()
    definition['permissions']=standard['permissions']
    standard['operations'][2]['emitted_events']=[]
    definition['operations'] += [standard['operations'][1],standard['operations'][2]]
    store_identity_package(state,definition)
    activate_identity_grant(state);Base.metadata.create_all(state.engine);state.response_relay=True
    prepare=relay._prepare
    def short(*args,**kwargs):
        result=replace(prepare(*args,**kwargs),timeout_seconds=5 if 'saturated' in request.node.name else 1)
        if 'slow_admission' in request.node.name and not kwargs['defer_relational']:
            time.sleep(2.15)  # Longer than the real response-handoff budget.
        return result
    monkeypatch.setattr(relay,'_prepare',short)
    with core_stack(state,monkeypatch) as s:yield s


@pytest.fixture
def invoked(health_stack):
    from sqlalchemy import select
    from backend.db.module import ApplicationExtensionInstallation
    s=health_stack
    with s.state.engine.begin() as db:module=db.scalar(select(ApplicationExtensionInstallation.module_id).where(ApplicationExtensionInstallation.id==1))
    def post(audience='administrator',operation='approve',headers=None,key='explicit-0001',body=None):
        segment='' if audience=='administrator' else '/'+audience
        url=s.url()+f'/api/v1/application-extensions/{module}{segment}/operations/{operation}'
        data=json.dumps(body or {'payload':{},'idempotency_key':key}).encode()
        request=urllib.request.Request(url,data=data,headers={**((s.operator if audience=='operator' else s.admin) if headers is None else headers),'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=3) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:return error.code,json.load(error)
    s.invoke=post;s.operator={'Authorization':'Bearer '+s.state.user_token}
    # This fixture explicitly adds the reference's human operation declarations.
    with s.state.engine.begin() as db:db.execute(ApplicationPermissionGrant.__table__.insert().values(application_installation_id=1,user_id=2,permission_id='records_manage'))
    yield s


def test_admin_operator_and_kiosk_contexts_use_original_signed_replies(invoked):
    s=invoked
    first=s.invoke();assert first[0]==200,first
    second=s.invoke('operator');assert second[0]==200,second
    terminal='b'*32
    from sqlalchemy import select
    with s.state.engine.begin() as db:
        incarnation=db.scalar(select(ApplicationExtensionInstallation.authority_incarnation).where(ApplicationExtensionInstallation.id==1))
        db.execute(ApplicationKioskTerminal.__table__.insert().values(terminal_id=terminal,application_installation_id=1,installation_incarnation=incarnation,label='Fixture',credential_hash='x',enabled=True))
    token=create_access_token('kiosk:'+terminal,{'token_type':'application_kiosk','module_id':s.state.validated.manifest.module_id,'terminal_id':terminal,'incarnation':incarnation})
    assert s.invoke('kiosk','register',{'Authorization':'Bearer '+token})[0]==200
    sent=s.seen();assert len(sent)==3
    assert [x['context']['audience'] for x in sent]==['administrator','operator','kiosk']
    assert sent[1]['context']['user_id']==2 and sent[2]['context']['terminal_id']==terminal
    assert all(x['context']['idempotency_key']=='explicit-0001' for x in sent)


def test_concurrent_slow_admission_reserves_only_when_ready_to_dispatch(invoked):
    s=invoked
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending=[pool.submit(s.invoke,'operator',key='explicit-'+str(n)) for n in range(2)]
        assert [p.result(timeout=4)[0] for p in pending]==[200,200]
    assert len(s.seen())==2
    assert {x['context']['idempotency_key'] for x in s.seen()}=={'explicit-0','explicit-1'}


@pytest.mark.parametrize('mode',['hang','trickle','signature','request_id','size','failure'])
def test_command_reply_failure_is_bounded_and_does_not_replay(invoked,mode):
    s=invoked;(s.health_root/'mode').write_text(mode);start=time.monotonic()
    assert s.invoke()[0]==409
    assert time.monotonic()-start<2 and len(s.seen())==1
    assert s.seen()[0]['context']['idempotency_key']=='explicit-0001'
    assert s.http('/api/v1/diagnostics/components',headers=s.admin)[0]==200


@pytest.mark.parametrize('change',['permission','session','disable','revoke'])
def test_waiting_operator_result_is_not_disclosed_after_revocation(invoked,change):
    s=invoked;(s.health_root/'mode').write_text('pause')
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(s.invoke,'operator');wait_for(lambda:s.seen())
        if change=='revoke':s.command('revoke')
        else:
            from backend.db.module import ApplicationExtensionInstallation
            with s.state.engine.begin() as db:
                if change=='permission':db.execute(delete(ApplicationPermissionGrant).where(ApplicationPermissionGrant.user_id==2))
                elif change=='session':db.execute(update(User).where(User.id==2).values(token_version=User.token_version+1))
                else:db.execute(update(ApplicationExtensionInstallation).where(ApplicationExtensionInstallation.id==1).values(enabled=False,status='disabled'))
        (s.health_root/'mode').write_text('valid');assert pending.result(timeout=2)[0]==409
    assert len(s.seen())==1


def test_saturated_operation_relay_keeps_admin_threads_and_database_free(invoked):
    s=invoked;(s.health_root/'mode').write_text('pause')
    with ThreadPoolExecutor(max_workers=10) as pool:
        pending=[]
        for count in range(1,9):
            pending.append(pool.submit(s.invoke));wait_for(lambda:len(s.seen())==count)
        assert s.command('threadpool_tokens')<2
        assert s.invoke()[0]==409 and len(s.seen())==8
        assert s.http('/settings/read')[0]==200
        (s.health_root/'mode').write_text('valid');assert all(p.result(timeout=2)[0]==200 for p in pending)


def test_runtime_loss_update_and_rollback_do_not_replay_a_command(invoked):
    s=invoked;before=s.command('fingerprint');a=s.store.target('current');(s.health_root/'mode').write_text('pause')
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(s.invoke);wait_for(lambda:s.seen());s.control.stop();assert pending.result(timeout=2)[0]==409
    assert len(s.seen())==1
    (s.health_root/'mode').write_text('valid');activate(s,s.artifact('http-b'));assert s.invoke()[0]==200
    s.store.rollback(control=s.control,health=s.control.health,fingerprint=lambda:s.command('fingerprint'))
    assert s.store.target('current')==a and s.invoke()[0]==200
    assert len(s.seen())==3 and s.command('fingerprint')==before
