"""Health admission races and signed completion without granting relational SQL."""
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import update
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.services import application_health_probe as health
from backend.services.application_extensions import ApplicationGatewayError
from backend.tests.test_application_connectors import connector_db
from backend.tests.test_module_packages import application_package, application_definition
from backend.services.module_packages import validate_module_package
from three_mm_runtime.application_transport import sign_message, verify_message, ApplicationTransportError

pytestmark=pytest.mark.skipif(os.name!='posix',reason='Linux Runtime account admission')


@pytest.fixture
def health_db(connector_db,tmp_path):
    import pwd
    db,app=connector_db;package=db.get(ModulePackage,app.module_package_id)
    blob=application_package();validated=validate_module_package(blob)
    path=tmp_path/'app.zip';path.write_bytes(blob)
    package.file_path=str(path);package.sha256=validated.sha256
    package.module_id=app.module_id=validated.manifest.module_id
    package.version=app.active_version=validated.manifest.version
    db.commit()
    (tmp_path/(app.instance_id+'.key')).write_bytes(b's'*32)
    settings=SimpleNamespace(key_root=tmp_path,runtime_user=pwd.getpwuid(os.geteuid()).pw_name,
        application_response_socket=tmp_path/'unused.sock')
    return db,app,package,settings


def probe_for(app,package):
    return health.HealthProbe(app.id,health._snapshot(app,package),b's'*32,'r'*32,'health')


def response(probe,**changes):
    return sign_message({'version':1,'timestamp':int(time.time()),'request_id':probe.request_id,
        'ok':True,'result':{'status':'ready'},**changes},probe.secret)


@pytest.mark.parametrize('drift',['disabled','epoch','incarnation','package','mode','socket','key','deadline'])
def test_health_admission_rechecks_after_reservation_before_send(health_db,monkeypatch,drift):
    db,app,package,settings=health_db;closed=[]
    waiter=SimpleNamespace(handoff_deadline=time.monotonic()+2,close=lambda:closed.append(True))
    def reserve(cls,*args):
        assert not db.in_transaction()
        if drift=='disabled':db.execute(update(Installation).values(enabled=False))
        elif drift=='epoch':db.execute(update(Installation).values(authority_epoch='e'*32))
        elif drift=='incarnation':db.execute(update(Installation).values(authority_incarnation='e'*32))
        elif drift=='package':db.execute(update(ModulePackage).values(sha256='e'*64))
        elif drift=='mode':db.execute(update(Installation).values(authority_mode='enforced'))
        elif drift=='socket':db.execute(update(Installation).values(socket_path='changed'))
        elif drift=='key':(settings.key_root/(app.instance_id+'.key')).write_bytes(b'x'*32)
        else:waiter.handoff_deadline=0
        db.commit();return waiter
    monkeypatch.setattr(health.ResponseWaiter,'reserve',classmethod(reserve))
    with pytest.raises((ApplicationGatewayError,TimeoutError)):health.begin_health_probe(db,app,package,settings)
    assert closed==[True] and not db.in_transaction()


def test_health_send_releases_db_and_uses_declared_timeout(health_db,monkeypatch):
    db,app,package,settings=health_db;closed=[];sent=[]
    waiter=SimpleNamespace(handoff_deadline=time.monotonic()+2,close=lambda:closed.append('waiter'),handoff=lambda origin:None)
    class Origin:
        def settimeout(self,value):assert 0<value<=2
        def connect(self,path):assert not db.in_transaction()
        def sendall(self,data):assert not db.in_transaction();sent.append(json.loads(data))
        def close(self):closed.append('origin')
        def recv(self,*args):pytest.fail('Core read the application response')
    monkeypatch.setattr(health.ResponseWaiter,'reserve',classmethod(lambda *args:waiter))
    monkeypatch.setattr(health.socket,'socket',lambda *args:Origin())
    probe,actual=health.begin_health_probe(db,app,package,settings)
    assert actual is waiter and waiter.timeout_seconds==10 and closed==['origin']
    request=verify_message(sent[0],b's'*32,expected_request_id=probe.request_id)
    assert request['operation_id']=='health' and request['context']['audience']=='internal'
    assert request['payload']=={} and 'relational_invocation' not in request


@pytest.mark.parametrize('damage',['signature','request','timestamp','schema','missing','extra','type','error','disabled','epoch','incarnation','package','mode','socket','key'])
def test_failed_health_completion_keeps_timestamp_empty(health_db,damage):
    db,app,package,settings=health_db;probe=probe_for(app,package);raw=response(probe)
    if damage=='signature':raw['signature']='0'*64
    elif damage=='request':raw=response(probe,request_id='foreign')
    elif damage=='timestamp':raw=response(probe,timestamp=int(time.time())-60)
    elif damage=='schema':raw=response(probe,result={'status':'failed'})
    elif damage=='missing':raw=response(probe,result={})
    elif damage=='extra':raw=response(probe,result={'status':'ready','secret':'private'})
    elif damage=='type':raw=response(probe,result=[])
    elif damage=='error':raw=response(probe,ok=False,error='failure')
    elif damage=='disabled':app.enabled=False
    elif damage=='epoch':app.authority_epoch='e'*32
    elif damage=='incarnation':app.authority_incarnation='e'*32
    elif damage=='package':package.sha256='e'*64
    elif damage=='mode':app.authority_mode='enforced'
    elif damage=='socket':app.socket_path='changed'
    else:(settings.key_root/(app.instance_id+'.key')).write_bytes(b'x'*32)
    db.commit()
    with pytest.raises((ApplicationGatewayError,ApplicationTransportError)):health.finish_health_probe(db,probe,raw,settings)
    db.rollback();assert db.get(Installation,probe.installation_id).health_checked_at is None


def test_finish_cas_refuses_lifecycle_change_after_result_validation(health_db,monkeypatch):
    db,app,package,settings=health_db;probe=probe_for(app,package)
    validate=health.validate_operation_payload
    def changed(value,schema):
        validate(value,schema)
        db.execute(update(Installation).values(authority_epoch='e'*32));db.commit()
    monkeypatch.setattr(health,'validate_operation_payload',changed)
    with pytest.raises(ApplicationGatewayError,match='changed'):health.finish_health_probe(db,probe,response(probe),settings)
    db.rollback();assert db.get(Installation,probe.installation_id).health_checked_at is None


def test_current_valid_health_commits_timestamp_without_changing_epoch(health_db):
    db,app,package,settings=health_db;probe=probe_for(app,package)
    assert health.finish_health_probe(db,probe,response(probe),settings)=={'status':'ready'}
    assert db.get(Installation,probe.installation_id).health_checked_at is not None
    assert app.authority_epoch==probe.snapshot[2]


@pytest.mark.parametrize('point',['initial','reserved','finish'])
def test_health_preserves_current_native_ui_trust_gate(health_db,monkeypatch,point):
    import backend.services.application_extensions as gateway
    from backend.services.compiled_ui import CompiledUiBuildError
    db,app,package,settings=health_db;app.authority_mode='enforced';db.commit()
    validated=gateway.load_application_package(package)
    monkeypatch.setattr(gateway,'load_application_package',lambda p:SimpleNamespace(application_extension=validated.application_extension,compiled_ui=object()))
    calls=[];closed=[]
    def ui(*args):
        calls.append(True)
        if point!='reserved' or len(calls)>1:raise CompiledUiBuildError('Application UI code trust is unavailable')
    monkeypatch.setattr('backend.services.compiled_ui.application_ui_artifact',ui)
    waiter=SimpleNamespace(handoff_deadline=time.monotonic()+2,close=lambda:closed.append(True))
    monkeypatch.setattr(health.ResponseWaiter,'reserve',classmethod(lambda *args:waiter))
    with pytest.raises(ApplicationGatewayError,match='trust'):
        if point=='finish':
            probe=probe_for(app,package);health.finish_health_probe(db,probe,response(probe),settings)
        else:health.begin_health_probe(db,app,package,settings)
    db.rollback();assert app.health_checked_at is None
    assert closed==([True] if point=='reserved' else [])


def test_relational_health_cannot_request_host_metadata_or_sql_ticket(health_db,monkeypatch):
    from three_mm_protocol.tests.test_application_relational_storage import relational_request
    db,app,package,settings=health_db
    definition=application_definition();definition['service']['sdk_version']='1.3'
    definition['storage']['relational']=relational_request()
    blob=application_package(definition=definition);Path(package.file_path).write_bytes(blob)
    package.sha256=validate_module_package(blob).sha256;db.commit()
    monkeypatch.setattr('backend.services.application_relational.prepare_host_invocation',lambda *a,**k:pytest.fail('Health performed host metadata IPC'))
    prepared=health._prepare(app,package,settings,'health','r'*32)
    assert prepared.relational_invocation is None and prepared.context['audience']=='internal'
    probe=probe_for(app,package)
    assert health.finish_health_probe(db,probe,response(probe),settings)=={'status':'ready'}
