"""Retained data survives package retirement; erasure is separately serialized."""
from contextlib import contextmanager
from types import SimpleNamespace
import backend.database  # noqa: F401
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from backend.db.base import Base
from backend.db.authority import CoreAuthorityGuard
from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationExtensionInstallation, ApplicationRetainedData, ModulePackage
from backend.db.user import User
from backend.routes import application_extensions as routes
from backend.services.authority_metadata import read_authority_guard
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token
from three_mm_runtime.application_activation import application_instance_id
from three_mm_runtime.update_helper_client import UpdateHelperError

BASE='/api/v1/application-extensions'
MODULE='org.example.retained'
INSTANCE='a'*24  # The persisted installation identity is authoritative, not a guessed hash.


@pytest.fixture
def retained(tmp_path, monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'retained.db'),connect_args={'check_same_thread':False,'timeout':.2})
    @event.listens_for(engine,'connect')
    def wal(connection,_):connection.execute('PRAGMA journal_mode=WAL')
    Base.metadata.create_all(engine)
    with Session(engine) as db,db.begin():
        db.add_all([User(id=1,username='admin',role='admin'),User(id=2,username='user',role='user'),CoreAuthorityGuard(singleton_id=1)])
    app=FastAPI();app.include_router(routes.router);sessions=[];calls=[]
    def database():
        with Session(engine) as db:sessions.append(db);yield db
    app.dependency_overrides[get_db]=database
    monkeypatch.setattr(routes,'get_settings',lambda:SimpleNamespace(applications=SimpleNamespace(helper_socket=tmp_path/'helper.sock')))
    def erase(_self,instance,actor,*,module_id,guard_generation,guard_revision):
        assert instance==INSTANCE and module_id==MODULE and actor==1
        assert sessions[-1].in_transaction()
        # The helper observes the committed version while the API owns its writer.
        with Session(engine) as reader:
            row=reader.get(ApplicationRetainedData,MODULE);assert row and row.instance_id==instance
            guard=read_authority_guard(reader)
            assert guard.generation==guard_generation and guard.revision==guard_revision
            assert reader.scalar(select(ApplicationExtensionInstallation.id)) is None
        with Session(engine) as writer:
            with pytest.raises(OperationalError):
                writer.connection().exec_driver_sql('UPDATE core_authority_guard SET revision=revision+1 WHERE singleton_id=1')
                writer.commit()
        calls.append({'instance':instance,'module_id':module_id,'guard_revision':guard_revision})
    monkeypatch.setattr(routes.UpdateHelperClient,'erase_application_extension_data',erase)
    with TestClient(app) as client:
        yield SimpleNamespace(engine=engine,client=client,sessions=sessions,calls=calls,monkeypatch=monkeypatch,
            admin={'Authorization':'Bearer '+create_access_token('1',{'role':'admin'})},
            user={'Authorization':'Bearer '+create_access_token('2',{'role':'user'})})
    engine.dispose()


def keep(s,module=MODULE,instance=INSTANCE,name='Retained app'):
    with Session(s.engine) as db,db.begin():db.add(ApplicationRetainedData(module_id=module,instance_id=instance,name=name))


def package(s,module=MODULE):
    with Session(s.engine) as db,db.begin():
        row=ModulePackage(module_id=module,version='1.0.0',sha256='b'*64,manifest={'name':'Old app','entrypoints':{'core':'application-extension.json'}},
            size_bytes=3,file_path='missing-obsolete.zip',registrations=[])
        db.add(row);db.flush();return row.id


def test_catalog_and_erasure_work_after_last_package_is_gone(retained):
    s=retained;keep(s)
    assert s.client.get(BASE+'/retained-data',headers=s.admin).json()==[{'module_id':MODULE,'instance_id':INSTANCE,'name':'Retained app'}]
    response=s.client.delete(BASE+'/'+MODULE+'/data',headers=s.admin)
    assert response.status_code==200,response.text
    assert s.calls[0]['instance']==INSTANCE
    assert s.client.get(BASE+'/retained-data',headers=s.admin).json()==[]
    with Session(s.engine) as db:
        assert db.get(ApplicationRetainedData,MODULE) is None
        assert db.scalar(select(AuditLog.action))=='APPLICATION_EXTENSION_DATA_ERASED'


def test_existing_package_fallback_first_persists_a_durable_cleanup_identity(retained):
    s=retained;package(s)
    canonical=application_instance_id(MODULE)
    def fail(_self,instance,actor,**context):
        assert instance==canonical
        with Session(s.engine) as reader:assert reader.get(ApplicationRetainedData,MODULE).instance_id==canonical
        raise UpdateHelperError('private-path-secret')
    s.monkeypatch.setattr(routes.UpdateHelperClient,'erase_application_extension_data',fail)
    response=s.client.delete(BASE+'/'+MODULE+'/data',headers=s.admin)
    assert response.status_code==409 and 'private-path-secret' not in response.text
    with Session(s.engine) as db,db.begin():
        assert db.get(ApplicationRetainedData,MODULE).name=='Old app'
        db.delete(db.scalar(select(ModulePackage)))
    assert s.client.get(BASE+'/retained-data',headers=s.admin).json()==[{'module_id':MODULE,'instance_id':canonical,'name':'Old app'}]


def test_failed_erase_keeps_record_and_commits_revision_fence(retained):
    s=retained;keep(s)
    with Session(s.engine) as db:before=read_authority_guard(db).revision
    def fail(*_args,**_kwargs):raise UpdateHelperError('private-erasure-diagnostic')
    s.monkeypatch.setattr(routes.UpdateHelperClient,'erase_application_extension_data',fail)
    response=s.client.delete(BASE+'/'+MODULE+'/data',headers=s.admin)
    assert response.status_code==409 and 'private-erasure-diagnostic' not in response.text
    with Session(s.engine) as db:
        assert db.get(ApplicationRetainedData,MODULE) is not None
        assert read_authority_guard(db).revision==before+2
        assert db.scalar(select(AuditLog.action))=='APPLICATION_EXTENSION_DATA_ERASE_FAILED'


@pytest.mark.parametrize('conflict',['module','instance'])
def test_installed_owner_hides_retained_entry_and_blocks_erase(retained,conflict):
    s=retained;keep(s);pid=package(s)
    with Session(s.engine) as db,db.begin():
        db.add(ApplicationExtensionInstallation(module_id=MODULE if conflict=='module' else 'org.example.other',module_package_id=pid,
            instance_id=INSTANCE if conflict=='instance' else 'c'*24,status='recovery_required',enabled=False,socket_path='pending'))
    assert s.client.get(BASE+'/retained-data',headers=s.admin).json()==[]
    assert s.client.delete(BASE+'/'+MODULE+'/data',headers=s.admin).status_code==409
    assert not s.calls


def test_reinstall_in_gap_between_metadata_and_erasure_prevents_helper_effect(retained):
    s=retained;keep(s);pid=package(s);original=routes._lifecycle_write;phases=[]
    @contextmanager
    def gap(db,**kwargs):
        with original(db,**kwargs) as authority:yield authority
        phases.append(True)
        if len(phases)==1:
            with Session(s.engine) as writer,writer.begin():
                writer.add(ApplicationExtensionInstallation(module_id=MODULE,module_package_id=pid,instance_id=INSTANCE,
                    status='activating',enabled=False,socket_path='pending'))
    s.monkeypatch.setattr(routes,'_lifecycle_write',gap)
    assert s.client.delete(BASE+'/'+MODULE+'/data',headers=s.admin).status_code==409
    assert not s.calls
    with Session(s.engine) as db:assert db.get(ApplicationRetainedData,MODULE) is not None


def test_retained_data_requires_admin_and_known_valid_identity(retained):
    s=retained;keep(s,name=None)
    assert s.client.get(BASE+'/retained-data').status_code==401
    assert s.client.get(BASE+'/retained-data',headers=s.user).status_code==403
    assert s.client.delete(BASE+'/'+MODULE+'/data',headers=s.user).status_code==403
    assert s.client.delete(BASE+'/org.example.unknown/data',headers=s.admin).status_code==404
    assert s.client.delete(BASE+'/invalid/data',headers=s.admin).status_code==422
    assert s.client.get(BASE+'/retained-data',headers=s.admin).json()[0]['name']==MODULE
    assert not s.calls


def test_fresh_activation_cannot_replace_preserved_runtime_identity(retained):
    s = retained
    keep(s)
    package(s)
    helper_calls = []
    definition = SimpleNamespace(service=SimpleNamespace(startup_timeout_seconds=1))
    s.monkeypatch.setattr(routes, '_definition', lambda _package: definition)
    s.monkeypatch.setattr(routes, 'validate_public_http_candidate', lambda *_args: None)
    s.monkeypatch.setattr(routes, 'device_configuration_keys', lambda _definition: ())
    s.monkeypatch.setattr(routes, 'resolve_application_configuration', lambda *_args, **_kwargs: {})
    s.monkeypatch.setattr(routes.UpdateHelperClient, 'activate_application_extension',
        lambda *_args, **_kwargs: helper_calls.append(True))
    response = s.client.post(BASE + '/packages/' + 'b' * 64 + '/activate', headers=s.admin)
    assert response.status_code == 409, response.text
    assert 'Erase preserved application data' in response.json()['detail']
    assert not helper_calls
    with Session(s.engine) as db:
        assert db.scalar(select(ApplicationExtensionInstallation.id)) is None
        assert db.get(ApplicationRetainedData, MODULE).instance_id == INSTANCE
