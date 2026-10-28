"""Current Core pairing: real UI review, sealed/encrypted receipts and sessions."""
import base64,json,os,uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select,func,update
from sqlalchemy.orm import Session
from backend.db.module import ApplicationKioskEnrollment as Enrollment,ApplicationKioskTerminal as Terminal,ApplicationExtensionInstallation as Installation
from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.audit_log import AuditLog
from backend.db.session import UserSession
from backend.routes import application_extensions as routes,modules,auth_refresh
from backend.services import application_kiosks as service
from backend.services.application_access import resolve_application_principal
from backend.tests.test_application_ui_authority import ui_app,managed_installed,source_subject,source_installed,adopt
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import decode_token,create_access_token

pytestmark=[pytest.mark.skipif(os.name!='posix',reason='Protected Linux Core key'),pytest.mark.parametrize('ui_app',['kiosk'],indirect=True)]
def rid():return uuid.uuid4().hex
def proof(value=b'p'):return base64.urlsafe_b64encode(value*32).decode().rstrip('=')

@pytest.fixture
def kiosk(ui_app):
    s=ui_app;adopt(s)
    app=FastAPI();app.include_router(routes.router);app.include_router(modules.router);app.include_router(auth_refresh.router,prefix='/api')
    def db():
        with Session(s.engine) as session:yield session
    app.dependency_overrides[get_db]=db
    with TestClient(app) as client:
        s.client=client;s.base='/api/v1/application-extensions/'+s.validated.manifest.module_id+'/kiosk'
        s.auth={'Authorization':'Bearer '+s.token}
        yield s

def enroll(s,request=None,auth=None):
    body=request or {'request_id':rid(),'label':'Tablet','expires_in_minutes':15}
    response=s.client.post(s.base+'/enrollments',json=body,headers=s.auth if auth is None else auth)
    return response,body

def claim(s,code,request=None):
    body=request or {'request_id':rid(),'code':code,'recovery_proof':proof()}
    return s.client.post(s.base+'/enrollments/claim',json=body),body

def pair(s):
    code,_=enroll(s);assert code.status_code==201,code.text
    response,body=claim(s,code.json()['code']);assert response.status_code==200,response.text
    return response.json(),body

def test_enrollment_and_claim_recover_without_another_terminal_or_plaintext_secret(kiosk):
    s=kiosk
    first,body=enroll(s);assert first.status_code==201,first.text
    same,_=enroll(s,body);assert same.json()==first.json()
    assert enroll(s,body|{'label':'Changed'})[0].status_code==409
    claimed,request=claim(s,first.json()['code']);assert claimed.status_code==200,claimed.text
    recovered,_=claim(s,first.json()['code'],request)
    assert recovered.status_code==200 and recovered.json()['credential']==claimed.json()['credential']
    assert recovered.json()['terminal_id']==claimed.json()['terminal_id']
    assert claim(s,first.json()['code'])[0].status_code==409
    assert claim(s,first.json()['code'],request|{'recovery_proof':proof(b'q')})[0].status_code==409
    with Session(s.engine) as db:
        assert db.scalar(select(func.count()).select_from(Terminal))==1
        serialized=str([r.payload for r in db.scalars(select(Action))])+str([r.changes for r in db.scalars(select(AuditLog))])
        for secret in (first.json()['code'],claimed.json()['credential'],claimed.json()['access_token'],request['recovery_proof']):assert secret not in serialized
    assert claimed.headers['cache-control']=='no-store'

def test_concurrent_claims_have_one_terminal_and_recover_only_the_winning_proof(kiosk):
    s=kiosk;created,_=enroll(s);code=created.json()['code']
    bodies=[dict(request_id=rid(),code=code,recovery_proof=proof(v)) for v in (b'p',b'q')]
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda b:claim(s,code,b)[0],bodies))
    assert sorted(r.status_code for r in results)==[200,409]
    winner=next(i for i,r in enumerate(results) if r.status_code==200)
    assert claim(s,code,bodies[winner])[0].status_code==200
    assert claim(s,code,bodies[1-winner])[0].status_code==409
    with Session(s.engine) as db:assert db.scalar(select(func.count()).select_from(Terminal))==1

def test_current_admin_login_survives_refresh_but_not_replacement(kiosk):
    s=kiosk;response,request=enroll(s);assert response.status_code==201
    renewed=s.client.post('/api/user/refresh',headers=s.auth);assert renewed.status_code==200
    s.auth={'Authorization':'Bearer '+renewed.json()['token']}
    assert enroll(s,request)[0].json()==response.json()
    replacement=create_access_token('1',{'sid':1,'token_version':0})
    with s.engine.begin() as db:db.execute(update(UserSession).where(UserSession.id==1).values(token=replacement))
    assert enroll(s,request,{'Authorization':'Bearer '+replacement})[0].status_code==409
    assert enroll(s,auth={'Authorization':'Bearer '+s.user_token})[0].status_code==403
    assert s.client.get(s.base+'/terminals').status_code==401

@pytest.mark.parametrize('fault',['expired','boot','disabled','incarnation','ui','revoked','foreign_module'])
def test_expiry_owner_and_current_code_trust_deny_recovery_or_renewal(kiosk,monkeypatch,fault):
    s=kiosk;identity,request=pair(s)
    if fault in {'expired','boot'}:
        clock=service.authority._clock
        monkeypatch.setattr(service.authority,'_clock',lambda:('another-boot',clock()[1]) if fault=='boot' else (clock()[0],clock()[1]+2_000_000))
        assert claim(s,request['code'],request)[0].status_code==410
        return
    if fault=='disabled':
        with s.engine.begin() as db:db.execute(update(Installation).values(enabled=False,status='disabled'))
    if fault=='incarnation':
        with s.engine.begin() as db:db.execute(update(Installation).values(authority_incarnation=rid()))
    if fault=='ui':(s.build.path/'assets/registration.mjs').write_text('changed')
    if fault=='revoked':assert s.client.delete(s.base+'/terminals/'+identity['terminal_id'],headers=s.auth).status_code==200
    url=s.base if fault!='foreign_module' else s.base.replace(s.validated.manifest.module_id,'org.example.foreign')
    response=s.client.post(url+'/sessions',json={k:identity[k] for k in ('terminal_id','credential')})
    assert response.status_code in (401,404,409)
    if fault=='foreign_module':
        assert s.client.post(url+'/enrollments/claim',json=request).status_code==404
        assert claim(s,request['code'],request)[0].status_code==200
    else:assert claim(s,request['code'],request)[0].status_code in (401,409)

@pytest.mark.parametrize('fault',['boot','monotonic','seal','missing_key'])
def test_unclaimed_codes_require_original_live_sealed_issuance(kiosk,monkeypatch,fault):
    s=kiosk;created,_=enroll(s);assert created.status_code==201
    if fault in {'boot','monotonic'}:
        clock=service.authority._clock
        monkeypatch.setattr(service.authority,'_clock',lambda:('other-boot',clock()[1]) if fault=='boot' else (clock()[0],clock()[1]+2_000_000))
    elif fault=='seal':
        with s.engine.begin() as db:db.execute(update(Action).values(seal='f'*64))
    else:(s.key_directory/'configuration-key.json').unlink()
    result,_=claim(s,created.json()['code'])
    assert result.status_code in (409,410),result.text
    with Session(s.engine) as db:assert db.scalar(select(func.count()).select_from(Terminal))==0
    assert s.client.get(s.base+'/terminals',headers=s.auth).status_code==200

def test_incarnation_is_checked_on_every_kiosk_token_and_no_user_identity_is_borrowed(kiosk):
    s=kiosk;identity,_=pair(s)
    with Session(s.engine) as db:
        actor=resolve_application_principal('Bearer '+identity['access_token'],db)
        assert actor.kind=='kiosk' and actor.user_id is None and not actor.is_admin
    token=decode_token(identity['access_token']);token['incarnation']='f'*32
    forged=create_access_token(token.pop('sub'),token)
    with Session(s.engine) as db,pytest.raises(Exception) as denied:resolve_application_principal('Bearer '+forged,db)
    assert denied.value.status_code==401
    original=decode_token(identity['access_token'])
    for changed in ({'sub':'1'},{'sid':1},{'role':'admin'},{'subject_id':'usr_'+'1'*32}):
        claims=original|changed
        mixed=create_access_token(claims.pop('sub'),claims)
        with Session(s.engine) as db,pytest.raises(Exception) as denied:resolve_application_principal('Bearer '+mixed,db)
        assert denied.value.status_code==401
    catalog=s.client.get('/api/v1/modules/compiled-ui/catalog',headers={'Authorization':'Bearer '+identity['access_token']})
    assert catalog.status_code==200,catalog.text
    assert all(e['application_audience']=='kiosk' for p in catalog.json()['items'] for e in p['entrypoints'])

def test_admin_revoke_and_metadata_remain_available_when_optional_ui_is_broken(kiosk):
    s=kiosk;identity,_=pair(s);(s.build.path/'assets/registration.mjs').write_text('broken')
    listed=s.client.get(s.base+'/terminals',headers=s.auth)
    assert listed.status_code==200 and 'credential' not in listed.text and 'access_token' not in listed.text
    for _ in range(2):assert s.client.delete(s.base+'/terminals/'+identity['terminal_id'],headers=s.auth).status_code==200
