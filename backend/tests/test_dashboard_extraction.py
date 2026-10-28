"""Retirement preserves layout/grant evidence without retaining Core authority."""
import hashlib
import json
import subprocess
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from backend.tests.test_migration_history import _alembic, _head_revision
from backend.tests.test_core_product_extraction import seed, table
from backend.services.module_packages import validate_module_package
from backend.tests.test_compiled_ui import package
from backend.db.module_reference import ModulePackageRetainedReference
from backend.routes import modules
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token

ARCHIVES = ('retired_displays','retired_widgets','retired_role_dashboard_grants',
    'retired_dashboard_permissions','retired_dashboard_role_permissions','retired_dashboard_group_permissions')


def rows(engine, name):
    with engine.connect() as connection:
        target = table(connection, name)
        columns = [c for c in target.c if name != 'users' or c.name != 'subject_id']
        return sorted(connection.execute(sa.select(*columns)).all(), key=repr)


@pytest.fixture
def retired(tmp_path):
    url='sqlite:///'+str(tmp_path/'dashboards.db');_alembic(url,'upgrade','6b41c293da31')
    engine=sa.create_engine(url)
    valid=validate_module_package(package())
    with engine.begin() as connection:
        seed(connection,'users',id=7,username='owner',email='owner@example.test',role='user')
        seed(connection,'users',id=8,username='admin',email='admin@example.test',role='admin')
        seed(connection,'roles',id=7,name='Dashboard editors');seed(connection,'groups',id=7,name='Visitors')
        seed(connection,'roles',id=9,name='Settings readers')
        seed(connection,'module_packages',id=7,module_id=valid.manifest.module_id,version=valid.manifest.version,
            manifest=valid.manifest.model_dump(mode='json'),sha256=valid.sha256,file_path='unchanged.zip',registrations=[])
        seed(connection,'displays',id=7,user_id=7,title='Запазено табло',slug='private',is_public=False)
        for identifier,kind in ((11,f'compiled:{valid.manifest.module_id}:{valid.manifest.version}:clock'),
                (12,f'compiled:{valid.manifest.module_id}:9.0.0:clock'),(13,'TEXT')):
            seed(connection,'widgets',id=identifier,display_id=7,type=kind,config={'text':'данни','nested':[1,False]},x=3,y=4,width=5,height=6,z_index=2)
        seed(connection,'role_dashboard_grants',role_id=7,display_id=7,permission_level='edit')
        seed(connection,'permissions',id=21,user_id=7,granted_by=8,entity_type='dashboard',entity_id=7,permission_level='EDIT')
        seed(connection,'permissions',id=22,user_id=7,granted_by=8,entity_type='widget',entity_id=11,permission_level='VIEW')
        seed(connection,'permissions',id=23,user_id=7,granted_by=8,entity_type='settings',entity_id=99,permission_level='VIEW')
        seed(connection,'role_permissions',role_id=7,entity_type='dashboard',entity_id=7,permission_level='edit')
        seed(connection,'role_permissions',role_id=9,entity_type='settings',entity_id=3,permission_level='view')
        seed(connection,'group_permissions',group_id=7,entity_type='widget',entity_id=11,permission_level='view')
    before={name:rows(engine,name) for name in ('displays','widgets','role_dashboard_grants','permissions','role_permissions','group_permissions','users','roles')}
    _alembic(url,'upgrade','head');_alembic(url,'check')
    yield engine,url,before,valid
    engine.dispose()


def test_populated_retirement_preserves_data_scopes_and_exact_package_reference(retired):
    engine,url,before,valid=retired
    names=set(sa.inspect(engine).get_table_names())
    assert not {'displays','widgets','role_dashboard_grants'} & names
    for name in ('displays','widgets','role_dashboard_grants'):assert rows(engine,'retired_'+name)==before[name]
    assert rows(engine,'retired_dashboard_permissions')==before['permissions'][:2]
    assert rows(engine,'permissions')==before['permissions'][2:]
    assert rows(engine,'retired_dashboard_role_permissions')==before['role_permissions'][:1]
    assert rows(engine,'role_permissions')==before['role_permissions'][1:]
    assert rows(engine,'retired_dashboard_group_permissions')==before['group_permissions']
    assert rows(engine,'group_permissions')==[]
    assert rows(engine,'users')==before['users'] and rows(engine,'roles')==before['roles']
    with engine.connect() as connection:
        retained=connection.execute(sa.select(ModulePackageRetainedReference)).all()
        assert len(retained)==1 and retained[0].package_id==7 and retained[0].resource_ref=='resource:11'
        assert connection.exec_driver_sql('PRAGMA foreign_key_check').all()==[]
    for name in ARCHIVES: assert sa.inspect(engine).get_foreign_keys(name)==[]
    _alembic(url,'upgrade','head')
    assert len(rows(engine,'module_package_retained_references'))==1


def test_retained_data_never_restores_old_grants_on_downgrade(retired):
    engine,url,before,valid=retired
    snapshots={name:rows(engine,name) for name in ARCHIVES}
    with pytest.raises(subprocess.CalledProcessError):_alembic(url,'downgrade','6b41c293da31')
    assert {name:rows(engine,name) for name in ARCHIVES}==snapshots
    with engine.connect() as connection:
        assert connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()==_head_revision()


def test_reference_inspection_and_retirement_are_admin_only_without_product_imports(retired):
    engine,url,before,valid=retired
    with Session(engine) as db:
        app=FastAPI();app.include_router(modules.router);app.dependency_overrides[get_db]=lambda:db
        base=f'/api/v1/modules/compiled-ui/packages/{valid.manifest.module_id}/{valid.manifest.version}'
        admin={'Authorization':'Bearer '+create_access_token('8',{'role':'admin'})}
        viewer={'Authorization':'Bearer '+create_access_token('7',{'role':'admin'})}
        with TestClient(app) as client:
            assert client.get(base+'/retained-references').status_code==401
            assert client.get(base+'/retained-references',headers=viewer).status_code==403
            found=client.get(base+'/retained-references',headers=admin)
            assert found.status_code==200 and len(found.json()['references'])==1
            assert found.json()['truncated'] is False
            assert client.delete(base,headers=admin).status_code==409


def test_removing_current_principals_cannot_cascade_into_retired_evidence(retired):
    engine,url,before,valid=retired
    preserved={name:rows(engine,name) for name in ARCHIVES}
    with engine.connect() as connection:
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')
        connection.execute(sa.text('DELETE FROM permissions WHERE user_id=7'))
        connection.execute(sa.text('DELETE FROM role_permissions WHERE role_id=7'))
        connection.execute(sa.text('DELETE FROM users WHERE id=7'))
        connection.execute(sa.text('DELETE FROM roles WHERE id=7'))
        connection.commit()
        assert connection.exec_driver_sql('PRAGMA foreign_key_check').all()==[]
    assert {name:rows(engine,name) for name in ARCHIVES}==preserved
