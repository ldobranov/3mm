"""Retirement data isolation and unchanged language/navigation consumers."""
import json,subprocess
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from backend.tests.test_migration_history import _alembic
from backend.tests.test_core_product_extraction import seed,table
from backend.tests.test_language_extensions import package as language_blob
from backend.services.module_packages import validate_module_package
from backend.routes import settings,language_routes
from backend.utils.db_utils import get_db

CONTENT=('extensions','pages','extension_tables','extension_fields','table_translations','migration_history','setting_translations','language_packs')

def rows(engine,name):
    with engine.connect() as db:return db.execute(sa.select(table(db,name))).all()

def preceding(tmp_path):
    url='sqlite:///'+str(tmp_path/'content.db');_alembic(url,'upgrade','8d63e4b5fc53')
    return sa.create_engine(url),url

@pytest.mark.parametrize('enabled',[True,False])
def test_populated_content_preserves_values_menu_labels_and_language_selection(tmp_path,enabled):
    engine,url=preceding(tmp_path)
    blob=language_blob();validated=validate_module_package(blob);archive=tmp_path/'language.zip';archive.write_bytes(blob)
    items=[{'path':'/devices','label':{'en':'Devices','bg':'Устройства'},'audience':'admin'},
        {'path':'/','label':{'en':'Home','bg':'Начало'},'audience':'public'}]
    with engine.begin() as db:
        seed(db,'users',id=7,username='owner',email='owner@example.test')
        seed(db,'users',id=8,username='admin',email='admin@example.test',role='admin')
        seed(db,'roles',id=7,name='Old content');seed(db,'roles',id=8,name='Current settings')
        seed(db,'groups',id=7,name='Old group');seed(db,'groups',id=8,name='Current group')
        seed(db,'extensions',id=7,user_id=7,manifest={'legacy':{'preserved':'данни'}})
        seed(db,'pages',id=7,owner_id=7,title={'en':'Page','bg':'Страница'},content={'bg':'Съдържание'},slug='old-page',is_public=False,allowed_roles=['custom'])
        seed(db,'menus',id=7,name='Main',items=items,structure={'config':{'position':'sidebar'}},default_language='bg',is_active=True)
        seed(db,'settings',id=7,key='header_message',value='Header')
        seed(db,'setting_translations',id=7,setting_id=7,language_code='bg',translated_value='Запазено заглавие')
        seed(db,'extension_tables',id=7,extension_id=7,table_name='menus',table_schema={'label':{'type':'json'}},translatable_fields=['label'])
        seed(db,'extension_fields',id=7,extension_id=7,table_name='menus',field_name='label',field_type='json')
        seed(db,'table_translations',id=7,extension_id=7,table_name='menus',record_id=7,language_code='bg',translation_data={'legacy_label':'Запазен превод'})
        seed(db,'migration_history',id=7,migration_type='menu_data',status='completed')
        seed(db,'module_packages',id=7,module_id=validated.manifest.module_id,version=validated.manifest.version,
            sha256=validated.sha256,manifest=validated.manifest.model_dump(mode='json'),file_path=str(archive))
        seed(db,'language_packs',id=7,code='de',name='Cached metadata',native_name='Old name',locale='de',extension_id=7,
            module_package_id=7,is_active=enabled,frontend_translations={'preserved_cache':'yes'})
        seed(db,'permissions',id=11,user_id=7,granted_by=8,entity_type='page',entity_id=7,permission_level='VIEW')
        seed(db,'permissions',id=12,user_id=7,granted_by=8,entity_type='extension',entity_id=7,permission_level='EDIT')
        seed(db,'permissions',id=13,user_id=7,granted_by=8,entity_type='settings',entity_id=7,permission_level='VIEW')
        seed(db,'role_permissions',role_id=7,entity_type='page',entity_id=7,permission_level='view')
        seed(db,'role_permissions',role_id=8,entity_type='settings',entity_id=7,permission_level='view')
        seed(db,'group_permissions',group_id=7,entity_type='extension',entity_id=7,permission_level='edit')
    before={name:rows(engine,name) for name in (*CONTENT,'menus','settings','permissions','role_permissions','group_permissions','module_packages')}
    _alembic(url,'upgrade','head');_alembic(url,'check')
    names=set(sa.inspect(engine).get_table_names());assert not set(CONTENT)&names
    for name in CONTENT:
        assert rows(engine,'retired_'+name)==before[name]
        assert sa.inspect(engine).get_foreign_keys('retired_'+name)==[]
    for name in ('menus','settings','module_packages'):assert rows(engine,name)==before[name]
    assert [tuple(row) for row in rows(engine,'language_extension_installations')]==[('de',7,enabled)]
    assert rows(engine,'permissions')==before['permissions'][2:]
    assert rows(engine,'retired_content_permissions')==before['permissions'][:2]
    assert rows(engine,'role_permissions')==before['role_permissions'][1:]
    assert rows(engine,'retired_content_role_permissions')==before['role_permissions'][:1]
    assert rows(engine,'retired_content_group_permissions')==before['group_permissions']
    app=FastAPI();app.include_router(settings.router);app.include_router(language_routes.router,prefix='/api')
    with Session(engine) as db:
        app.dependency_overrides[get_db]=lambda:db
        with TestClient(app) as client:
            menu=client.get('/menu/read/bg');assert menu.status_code==200 and menu.json()['items'][0]['items']==items
            assert client.get('/language/available').json()['languages']==(['de','en'] if enabled else ['en'])
            expected=validated.language_extension.frontend if enabled else {}
            assert client.get('/api/translations/de').json()['frontend']==expected
    preserved={name:rows(engine,'retired_'+name) for name in CONTENT}
    with engine.connect() as db:
        db.exec_driver_sql('PRAGMA foreign_keys=ON')
        db.exec_driver_sql('DELETE FROM permissions WHERE user_id=7');db.exec_driver_sql('DELETE FROM users WHERE id=7');db.exec_driver_sql('DELETE FROM roles WHERE id=7');db.commit()
        assert db.exec_driver_sql('PRAGMA foreign_key_check').all()==[]
    assert {name:rows(engine,'retired_'+name) for name in CONTENT}==preserved
    with pytest.raises(subprocess.CalledProcessError):_alembic(url,'downgrade','8d63e4b5fc53')
    assert {name:rows(engine,'retired_'+name) for name in CONTENT}==preserved
    _alembic(url,'upgrade','head');engine.dispose()

@pytest.mark.parametrize('case',['registered_custom','inbound_fk'])
def test_unknown_data_ownership_refuses_before_any_schema_or_value_change(tmp_path,case):
    engine,url=preceding(tmp_path)
    with engine.begin() as db:
        seed(db,'extensions',id=7)
        db.exec_driver_sql('CREATE TABLE independent_data (id INTEGER PRIMARY KEY, extension_id INTEGER REFERENCES extensions(id), value TEXT)')
        db.exec_driver_sql("INSERT INTO independent_data VALUES (7,7,'preserved')")
        if case=='registered_custom':seed(db,'extension_tables',id=7,extension_id=7,table_name='independent_data',table_schema={},translatable_fields=[])
    names=set(sa.inspect(engine).get_table_names());data=rows(engine,'independent_data')
    with pytest.raises(subprocess.CalledProcessError):_alembic(url,'upgrade','head')
    assert set(sa.inspect(engine).get_table_names())==names
    assert rows(engine,'independent_data')==data
    with engine.connect() as db:assert db.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='8d63e4b5fc53'
    engine.dispose()

def test_optional_unregistered_prototype_content_is_retained_without_schema_guessing(tmp_path):
    engine,url=preceding(tmp_path)
    with engine.begin() as db:
        db.exec_driver_sql('CREATE TABLE extension_multilingual_content (id INTEGER PRIMARY KEY, content_data JSON)')
        db.exec_driver_sql('INSERT INTO extension_multilingual_content VALUES (1,\'{"bg":"Запазено"}\')')
    before=rows(engine,'extension_multilingual_content');_alembic(url,'upgrade','head');_alembic(url,'check')
    assert rows(engine,'retired_extension_multilingual_content')==before
    with pytest.raises(subprocess.CalledProcessError):_alembic(url,'downgrade','8d63e4b5fc53')
    engine.dispose()
