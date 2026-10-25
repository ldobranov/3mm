"""Real package/lifecycle/denial checks for data-only language extensions."""
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
import pytest
import backend.database
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from backend.db.base import Base
from backend.db.user import User
from backend.db.language_pack import LanguagePack
from backend.db.module import ModulePackage
from backend.routes import modules, language_routes
from backend.services.language_extensions import available_languages, BundledLanguagePackages
from backend.services.module_packages import ModulePackageError, validate_module_package
from backend.utils import jwt_utils
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token

ROOT=Path(__file__).resolve().parents[2]
BASE='/api/v1/modules/languages'

def package(*, version='1.0.0', code='de', extra=None, values=None):
    module_id='org.example.language.'+code
    manifest={'manifest_version':2,'module_id':module_id,'name':'Example language','version':version,
        'runtimes':['ui'],'entrypoints':{'ui':'language-extension.json'},
        'compatibility':{'protocol':'1.0','architectures':['any']},
        'health_check':{'type':'json_file','path':'language-extension.json'}}
    definition={'language_extension_version':1,'module_id':module_id,'version':version,'code':code,
        'name':'Example language','native_name':'Example','locale':code,'frontend':values or {'test':{'greeting':version}},'backend':{}}
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive:
        archive.writestr('manifest.json',json.dumps(manifest))
        archive.writestr('language-extension.json',json.dumps(definition))
        if extra:archive.writestr(extra,'must never run')
    return stream.getvalue()

@pytest.fixture
def runtime(tmp_path,monkeypatch):
    monkeypatch.setattr(jwt_utils,'SECRET_KEY','test-only-language-key-at-least-32-bytes')
    config=SimpleNamespace(backend=SimpleNamespace(uploads_dir=tmp_path/'uploads'))
    monkeypatch.setattr(modules,'get_settings',lambda:config)
    monkeypatch.setattr(modules,'compile_ui_package',lambda *_:pytest.fail('Language data must never invoke the UI compiler'))
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db=Session(engine)
    admin=User(username='admin',email='admin@example.test',hashed_password='unused',role='admin')
    viewer=User(username='viewer',email='viewer@example.test',hashed_password='unused',role='user')
    db.add_all([admin,viewer]);db.commit()
    headers=lambda user:{'Authorization':'Bearer '+create_access_token(str(user.id),{'role':'admin'})}
    app=FastAPI();app.include_router(modules.router);app.include_router(language_routes.router,prefix='/api')
    app.dependency_overrides[get_db]=lambda:db
    with TestClient(app) as client:
        yield SimpleNamespace(client=client,db=db,admin=admin,viewer=viewer,headers=headers,config=config,tmp=tmp_path)
    db.close();engine.dispose()

def upload(runtime,**changes):
    response=runtime.client.post('/api/v1/modules/packages',headers=runtime.headers(runtime.admin),
        files={'package':('language.zip',package(**changes),'application/zip')})
    assert response.status_code==200,response.text
    return response.json()['sha256']

@pytest.mark.parametrize('extra,values', [('entry.py',None),('source/frontend/Entry.vue',None),(None,{'constructor':'x'}),(None,{'key':['not text']}),(None,{'key':'x'*16001})])
def test_language_package_rejects_code_and_unbounded_or_unsafe_data(extra,values):
    with pytest.raises(ModulePackageError):validate_module_package(package(extra=extra,values=values))

def test_stage_enable_replace_disable_and_rollback_are_data_only(runtime):
    r=runtime;c=r.client;headers=r.headers(r.admin)
    first=upload(r)
    assert available_languages(r.db)==['en']
    assert c.get('/api/translations/de').json()['frontend']=={}
    assert c.post(f'{BASE}/packages/{first}/enable',headers=headers).status_code==200
    assert available_languages(r.db)==['de','en']
    response=c.get('/api/translations/de')
    assert response.headers['cache-control']=='no-store'
    assert response.json()['frontend']['test']['greeting']=='1.0.0'
    second=upload(r,version='2.0.0')
    assert c.post(f'{BASE}/packages/{second}/enable',headers=headers).status_code==200
    assert c.post(f'{BASE}/packages/{first}/disable',headers=headers).status_code==200
    assert c.get('/api/translations/de').json()['frontend']['test']['greeting']=='2.0.0'
    assert c.post(f'{BASE}/packages/{first}/enable',headers=headers).status_code==200
    assert c.get('/api/translations/de').json()['frontend']['test']['greeting']=='1.0.0'
    assert len(list(r.db.scalars(select(LanguagePack))))==1
    assert c.post(f'{BASE}/packages/{first}/disable',headers=headers).status_code==200
    assert available_languages(r.db)==['en']
    assert c.get('/api/translations/de').json()['frontend']=={}

def test_language_lifecycle_checks_real_role_and_current_revocation(runtime):
    r=runtime;digest=upload(r)
    operations=[('get',f'{BASE}/catalog'),('post',f'{BASE}/packages/{digest}/enable'),
        ('post',f'{BASE}/packages/{digest}/disable'),('delete',f'{BASE}/packages/{digest}')]
    for method,url in operations:
        assert r.client.request(method,url).status_code==401
        assert r.client.request(method,url,headers=r.headers(r.viewer)).status_code==403
    token=r.headers(r.admin)
    r.admin.token_version+=1;r.db.commit()
    for method,url in operations:assert r.client.request(method,url,headers=token).status_code==401
    r.admin.is_blocked=True;r.db.commit()
    assert r.client.get(f'{BASE}/catalog',headers=r.headers(r.admin)).status_code==401

def test_tampered_language_becomes_unavailable_and_can_still_be_disabled(runtime):
    r=runtime;digest=upload(r);headers=r.headers(r.admin)
    assert r.client.post(f'{BASE}/packages/{digest}/enable',headers=headers).status_code==200
    record=r.db.scalar(select(ModulePackage).where(ModulePackage.sha256==digest))
    Path(record.file_path).write_bytes(b'broken package')
    assert available_languages(r.db)==['en']
    assert r.client.get('/api/translations/de').json()['frontend']=={}
    assert r.client.get(f'{BASE}/catalog',headers=headers).json()['items'][0]['status']=='unavailable'
    assert r.client.post(f'{BASE}/packages/{digest}/disable',headers=headers).status_code==200
    assert r.client.post(f'{BASE}/packages/{digest}/enable',headers=headers).status_code==409

def test_bundled_language_is_generic_and_never_resurrects_after_disable_or_delete(runtime):
    r=runtime;directory=r.tmp/'bundles'/'any-name';directory.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(package())) as archive:
        for name in archive.namelist():(directory/name).write_bytes(archive.read(name))
    def sessions():yield r.db
    seed=BundledLanguagePackages(sessions,r.config,r.tmp/'bundles')
    seed.seed()
    assert available_languages(r.db)==['de','en']
    digest=r.db.scalar(select(ModulePackage.sha256))
    headers=r.headers(r.admin)
    assert r.client.post(f'{BASE}/packages/{digest}/disable',headers=headers).status_code==200
    seed.seed();assert available_languages(r.db)==['en']
    assert r.client.delete(f'{BASE}/packages/{digest}',headers=headers).status_code==200
    seed.seed();assert list(r.db.scalars(select(ModulePackage)))==[]

def test_bulgarian_delivery_contains_the_moved_ui_and_device_dictionaries():
    directory=ROOT/'modules/language-bg';stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive:
        for name in ('manifest.json','language-extension.json'):archive.writestr(name,(directory/name).read_bytes())
    definition=validate_module_package(stream.getvalue()).language_extension
    assert definition.code=='bg'
    assert definition.frontend['mainServer']['devices']['title']
    assert definition.frontend['uiPlatform']['language']=='Език'
    assert definition.frontend['applicationAuthority']['manage']
    assert definition.frontend['packageInspection']['help']


def test_language_module_migration_preserves_existing_translation_rows(tmp_path):
    from backend.tests.test_migration_history import _alembic
    from sqlalchemy import inspect,text
    url=f"sqlite:///{(tmp_path/'upgrade.db').as_posix()}"
    _alembic(url,'upgrade','fcd45b0213c4')
    engine=create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO language_packs (name,code,native_name,locale,frontend_translations,is_active) VALUES ('Existing','de','Existing','de','{\"kept\":\"yes\"}',1)"))
    engine.dispose()
    _alembic(url,'upgrade','head');_alembic(url,'check')
    engine=create_engine(url)
    with engine.connect() as connection:
        row=connection.execute(text('SELECT frontend_translations,module_package_id,is_active FROM language_packs')).one()
        assert json.loads(row[0])=={'kept':'yes'} and row[1] is None and row[2]==1
    engine.dispose()
    _alembic(url,'downgrade','fcd45b0213c4')
    engine=create_engine(url)
    assert 'module_package_id' not in {item['name'] for item in inspect(engine).get_columns('language_packs')}
    with engine.connect() as connection:assert connection.execute(text('SELECT count(*) FROM language_packs')).scalar()==1
    engine.dispose()
