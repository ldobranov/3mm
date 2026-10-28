"""Real human/session/build/service grant admission + raw HTTP + signed worker."""
import hashlib
import os
from pathlib import Path
import tempfile
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, update
from sqlalchemy.orm import Session
from backend.db.module import ApplicationExtensionInstallation as Installation, ApplicationPermissionGrant
from backend.db.session import UserSession
from backend.routes import application_extensions as routes, application_file_transfers as files
from backend.tests.test_application_ui_authority import ui_app, managed_installed, source_subject, source_installed, adopt
from backend.tests.test_application_file_execution import revoke
from backend.tests.test_application_authority_management import identity
from backend.tests.test_application_access import kiosk_enrollment,kiosk_claim
from backend.utils.db_utils import get_db
from three_mm_runtime.application_file_executor import ApplicationFileExecutor

pytestmark = [pytest.mark.skipif(os.name != 'posix', reason='Actual POSIX runtime'), pytest.mark.parametrize('ui_app', ['files'], indirect=True)]


@pytest.fixture
def environment(ui_app, monkeypatch):
    s = ui_app
    adopt(s, scopes=s.manager.inspect(1)['scopes'])
    with tempfile.TemporaryDirectory(prefix='media-http-', dir='/tmp') as temporary:
        s.runtime = Path(temporary) / ('a'*24)
        (s.runtime/'run').mkdir(parents=True)
        (s.runtime/'data').mkdir()
        s.secret = b's'*32
        with s.engine.begin() as db:
            db.execute(update(Installation).values(socket_path=str(s.runtime/'run/service.sock')))
            for name in ('records_manage','files_read','files_write','files_publish','files_transform'):
                db.execute(ApplicationPermissionGrant.__table__.insert().values(application_installation_id=1,user_id=2,permission_id=name))
        monkeypatch.setattr(files, '_secret', lambda _: s.secret)
        app = FastAPI()
        app.include_router(routes.router)
        def session():
            with Session(s.engine) as db:
                yield db
        app.dependency_overrides[get_db] = session
        s.binding = {'host_version':1,'entrypoint_id':'operations','artifact_sha256':s.validated.sha256,'built_ui_sha256':s.build.built_ui_sha256}
        s.query = urlencode({k:v for k,v in s.binding.items() if k != 'host_version'})
        s.base = '/api/v1/application-extensions/'+s.validated.manifest.module_id+'/files'
        s.auth = {'Authorization':'Bearer '+s.user_token}
        metadata = {'instance_id':'a'*24,'sha256':s.validated.sha256,'storage':s.validated.application_extension.storage.model_dump(mode='json')}
        with ApplicationFileExecutor(s.runtime, metadata, s.secret), TestClient(app) as client:
            s.client = client
            yield s


def control(s, operation, *, binding=None, auth=None, **fields):
    return s.client.post(s.base+'/control', headers=s.auth if auth is None else auth,
        json={'ui_context':binding or s.binding, 'file_request':{'file_request_version':2,'request_id':identity(),'operation':operation,**fields}})


def upload(s, data):
    digest = hashlib.sha256(data).hexdigest()
    response = control(s,'begin',file_id='sample',size_bytes=len(data),sha256=digest,filename='данни.bin',content_type='application/octet-stream',expected_sha256=None)
    assert response.status_code == 200, response.text
    upload_id = response.json()['upload_id']
    for offset in range(0,len(data),256*1024):
        response = s.client.post(s.base+'/uploads/'+upload_id+'/chunks?'+s.query+'&offset='+str(offset), headers={**s.auth,'Content-Type':'application/octet-stream'},content=data[offset:offset+256*1024])
        assert response.status_code == 200, response.text
    response = control(s,'finalize',upload_id=upload_id)
    assert response.status_code == 200, response.text
    return response.json()['file']


def test_platform_admin_requires_explicit_file_permission(environment):
    s=environment
    with s.engine.begin() as db:
        db.execute(ApplicationPermissionGrant.__table__.insert().values(application_installation_id=1,user_id=1,permission_id='records_manage'))
    auth={'Authorization':'Bearer '+s.token}
    fields=dict(file_id='admin_file',size_bytes=1,sha256=hashlib.sha256(b'x').hexdigest(),
        filename='x',content_type='application/octet-stream',expected_sha256=None)
    assert control(s,'begin',auth=auth,**fields).status_code==403
    with s.engine.begin() as db:
        for permission in ('files_read','files_write'):
            db.execute(ApplicationPermissionGrant.__table__.insert().values(application_installation_id=1,user_id=1,permission_id=permission))
    assert control(s,'begin',auth=auth,**fields).status_code==200
    with s.engine.begin() as db:
        db.execute(delete(ApplicationPermissionGrant).where(ApplicationPermissionGrant.user_id==1,
            ApplicationPermissionGrant.permission_id=='files_write'))
    assert control(s,'begin',auth=auth,**fields).status_code==403


def test_http_stream_private_public_revocation_and_no_tokens_in_urls(environment):
    s = environment
    data = b'CAP11 raw stream'*80000
    metadata = upload(s,data)
    response = s.client.get(s.base+'/sample/content?'+s.query,headers=s.auth)
    assert response.status_code == 200 and response.content == data
    assert response.headers['cache-control'] == 'no-store'
    assert 'attachment;' in response.headers['content-disposition']
    link = control(s,'link',file_id='sample',sha256=metadata['sha256'],token='b'*64,ttl_seconds=60,max_downloads=1).json()
    path=s.base+'/links/'+link['link_id']
    page=s.client.get(path+'/open')
    assert page.status_code == 200 and 'location.hash' in page.text
    assert 'b'*64 not in page.text and "form-action 'self'" in page.headers['content-security-policy']
    assert s.client.post(path+'/content',data={'token':'c'*64}).status_code == 403
    public=s.client.post(path+'/content',data={'token':'b'*64})
    assert public.status_code == 200 and public.content == data
    # Human sharing permission is separate from ordinary write access.
    with s.engine.begin() as db:
        db.execute(delete(ApplicationPermissionGrant).where(ApplicationPermissionGrant.permission_id=='files_publish'))
    assert control(s,'link',file_id='sample',sha256=metadata['sha256'],token='c'*64,ttl_seconds=60,max_downloads=1).status_code==403
    revoke(s)
    assert s.client.get(s.base+'/sample/content?'+s.query,headers=s.auth).status_code==403
    assert s.client.post(path+'/content',data={'token':'b'*64}).status_code==403
    assert (s.runtime/'data/sdk-media/index.json').exists()


@pytest.mark.parametrize('fault',['session','user_permission','service_grant','build','anonymous','kiosk','disable','uninstall'])
def test_denial_happens_before_bytes_or_new_files(environment,fault):
    s=environment
    if fault=='session':
        with s.engine.begin() as db:
            db.execute(update(UserSession).where(UserSession.user_id==2).values(is_active=False))
    if fault=='user_permission':
        with s.engine.begin() as db:
            db.execute(delete(ApplicationPermissionGrant).where(ApplicationPermissionGrant.permission_id=='files_write'))
    if fault=='service_grant':revoke(s)
    if fault in {'disable','uninstall'}:
        with s.engine.begin() as db:
            db.execute(update(Installation).values(enabled=False,status='disabled' if fault=='disable' else 'uninstalled'))
    binding={**s.binding,'built_ui_sha256':'f'*64} if fault=='build' else s.binding
    auth={} if fault=='anonymous' else s.auth
    if fault=='kiosk':
        base=s.base.removesuffix('/files')
        enrollment=s.client.post(base+'/kiosk/enrollments',headers={'Authorization':'Bearer '+s.token},json=kiosk_enrollment('File-denial fixture'))
        assert enrollment.status_code==201,enrollment.text
        claim=s.client.post(base+'/kiosk/enrollments/claim',json=kiosk_claim(enrollment.json()['code']))
        assert claim.status_code==200,claim.text
        auth={'Authorization':'Bearer '+claim.json()['access_token']}
    response=control(s,'begin',binding=binding,auth=auth,file_id='sample',size_bytes=0,sha256=hashlib.sha256(b'').hexdigest(),filename='a',content_type='text/plain',expected_sha256=None)
    assert response.status_code in {401,403,404,409}, response.text
    assert not (s.runtime/'data/sdk-media').exists()


def test_raw_chunk_bounds_and_receipt_owner(environment):
    s=environment
    metadata=upload(s,b'hello')
    assert s.client.get(s.base+'/sample/chunks?'+s.query+'&sha256='+metadata['sha256']+'&offset=0&length=2',headers=s.auth).content==b'he'
    assert s.client.post(s.base+'/uploads/'+'a'*32+'/chunks?'+s.query+'&offset=0',headers={**s.auth,'Content-Type':'application/octet-stream'},content=b'x'*(256*1024+1)).status_code==413
    assert s.client.post(s.base+'/control',headers=s.auth,content=b'x'*8193).status_code==413


def test_cross_origin_browser_can_read_required_file_integrity_headers(environment):
    from fastapi.middleware.cors import CORSMiddleware
    from backend.main import app as core_app
    s=environment
    metadata=upload(s,b'cross-port download')
    cors=next(item for item in core_app.user_middleware if item.cls is CORSMiddleware)
    # Use the actual Core middleware options; only the fixture's allowed origin
    # differs. Same-origin unit responses do not model browser header filtering.
    options={**cors.kwargs,'allow_origins':['http://rasp-3mm.local:8080']}
    app=FastAPI();app.include_router(routes.router);app.add_middleware(CORSMiddleware,**options)
    app.dependency_overrides[get_db]=s.client.app.dependency_overrides[get_db]
    with TestClient(app) as client:
        url=s.base+'/sample/chunks?'+s.query+'&sha256='+metadata['sha256']+'&offset=0&length=256'
        response=client.get(url,headers={**s.auth,'Origin':'http://rasp-3mm.local:8080'})
        assert response.status_code==200,response.text
        assert response.headers['access-control-allow-origin']=='http://rasp-3mm.local:8080'
        exposed={name.strip().lower() for name in response.headers['access-control-expose-headers'].split(',')}
        assert {'x-content-sha256','x-chunk-sha256'}<=exposed
        assert response.headers['x-content-sha256']==metadata['sha256']
        assert response.headers['x-chunk-sha256']==hashlib.sha256(response.content).hexdigest()
        denied=client.get(url,headers={**s.auth,'Origin':'http://untrusted.invalid'})
        assert 'access-control-allow-origin' not in denied.headers


def test_revocation_between_stream_chunks_stops_remaining_bytes(environment):
    import anyio
    from fastapi import HTTPException
    s=environment
    upload(s,b'x'*(512*1024))
    with Session(s.engine) as db:
        response=files.download(s.validated.manifest.module_id,'sample','operations',s.validated.sha256,s.build.built_ui_sha256,s.auth['Authorization'],db)
    async def consume():
        iterator=response.body_iterator
        first=await anext(iterator)
        assert len(first)==256*1024
        revoke(s)
        with pytest.raises(HTTPException) as denied:await anext(iterator)
        assert denied.value.status_code==403
    anyio.run(consume)


def test_current_private_grant_cannot_publish_or_transform_with_human_permission(environment):
    from backend.services import application_consent as consent
    s=environment
    metadata=upload(s,b'hello')
    preview=consent.preview(s.manager,1,actor_token=s.token,request_id=identity())
    selected=[scope for scope in preview['scopes'] if scope not in {'storage:private_files_publish','storage:private_files_transform'}]
    consent.allow(s.manager,1,actor_token=s.token,request_id=identity(),preview_id=preview['preview_id'],expected_revision=preview['revision'],
        fingerprint=preview['fingerprint'],scopes=selected,user_permissions=[p['permission_id'] for p in preview['user_permissions']],accept_native_code=True)
    assert control(s,'stat',file_id='sample').status_code==200
    assert control(s,'link',file_id='sample',sha256=metadata['sha256'],token='c'*64,ttl_seconds=60,max_downloads=1).status_code==403
    assert control(s,'transform',file_id='sample',sha256=metadata['sha256'],output_id='preview',width=10,height=10,format='png').status_code==403


def test_initial_consent_leaves_public_and_image_processing_unselected(ui_app):
    from backend.services import application_consent as consent
    s=ui_app
    preview=consent.preview(s.manager,1,actor_token=s.token,request_id=identity())
    assert 'storage:private_files_publish' in preview['scopes']
    assert 'storage:private_files_transform' in preview['scopes']
    assert 'storage:private_files_publish' not in preview['selected_scopes']
    assert 'storage:private_files_transform' not in preview['selected_scopes']
    assert len(preview['resources']['private_files'])==4
