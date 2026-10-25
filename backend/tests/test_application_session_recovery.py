"""Real current administrator/login, exact ownership and read-only reconciliation."""
import asyncio
import json
from sqlalchemy import select,update
import pytest
from starlette.websockets import WebSocketDisconnect

from backend.db.audit_log import AuditLog
from backend.db.session import UserSession
from backend.tests.test_application_browser_sessions import (
    browser_app,connect,issue,checkpoint_app,managed_installed,session_app,source_installed,source_subject,
)
from sqlalchemy.orm import Session


def fenced(s):
    s.provider.fail_close=True
    ticket=issue(s).json()
    with connect(s,ticket) as ws:
        ws.send_json({'op':'authenticate','ticket':ticket['ticket']})
        sid=ws.receive_json()['acceptance']['session_id'];ws.receive_bytes()
        ws.send_json({'op':'close','session_id':sid})
        with pytest.raises(WebSocketDisconnect):ws.receive_json()
    assert s.browser.owned[sid].finalized and s.browser.owned[sid].failed
    return sid


def endpoint(s):
    return '/api/v1/application-extensions/'+s.validated.manifest.module_id+'/session-recovery'


def admin(s):return {'Authorization':'Bearer '+s.token}


def test_fresh_administrator_read_only_confirmation_releases_only_exact_fence(browser_app):
    s=browser_app;sid=fenced(s);calls=[]
    async def confirm():calls.append(sid)
    s.provider.confirm_cleanup=confirm
    before=s.client.get(endpoint(s),headers=admin(s))
    assert before.status_code==200 and before.headers['cache-control']=='no-store'
    assert before.json()['sessions'][0]['state']=='cleanup_required'
    result=s.client.post(endpoint(s)+'/'+sid+'/confirm-cleanup',headers=admin(s))
    assert result.status_code==200 and result.json()['state']=='cleanup_confirmed'
    assert calls==[sid] and len(s.provider.opened)==1 and len(s.provider.closed)==1 and not s.provider.inputs
    assert not s.browser.owned and not s.browser.leases and not s.browser.reservations
    assert s.client.get(endpoint(s),headers=admin(s)).json()['sessions']==[]
    with Session(s.engine) as db:
        rows=[json.loads(row.changes) if isinstance(row.changes,str) else row.changes for row in db.scalars(select(AuditLog).where(AuditLog.action=='APPLICATION_SESSION_LIFECYCLE'))]
    assert any(row['outcome']=='cleanup_reconciled' and row['session_id']==sid and row['reconciled_by']==1 for row in rows)


@pytest.mark.parametrize('fault',['no_actor','operator','other_app','other_session','no_proof','false_proof','actor_revoked_during_io'])
def test_recovery_never_clears_without_current_admin_exact_owner_and_proof(browser_app,fault):
    s=browser_app;sid=fenced(s);calls=[]
    async def confirm():
        calls.append(sid)
        if fault=='false_proof':return True
        if fault=='actor_revoked_during_io':
            with s.engine.begin() as db:db.execute(update(UserSession).where(UserSession.id==1).values(is_active=False))
    if fault!='no_proof':s.provider.confirm_cleanup=confirm
    path=endpoint(s)+'/'+sid+'/confirm-cleanup';headers=admin(s)
    if fault=='no_actor':headers={}
    elif fault=='operator':headers=s.auth
    elif fault=='other_app':path=path.replace(s.validated.manifest.module_id,'org.example.other')
    elif fault=='other_session':path=path.replace(sid,'ses_'+'f'*32)
    result=s.client.post(path,headers=headers)
    assert result.status_code in {401,403,404,409}
    assert sid in s.browser.owned and sid in s.browser.leases and s.browser.owned[sid].failed
    assert len(s.provider.opened)==1 and len(s.provider.closed)==1 and not s.provider.inputs
