from datetime import UTC, datetime
import socket
import time
import sys
from types import SimpleNamespace

import backend.database  # noqa: F401 - register all model metadata
import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from backend.config import ApplicationRuntimeSettings
from backend.db.base import Base
from backend.db.device import Device, DeviceEvent
from backend.db.module import (
    ApplicationEventCursor,
    ApplicationEventDelivery,
    ApplicationExtensionInstallation,
    ModulePackage,
)
from backend.services.application_events import (
    application_event_status,
    enqueue_application_event,
    claim_event_delivery, complete_event_delivery, request_application_event_retry,
)
from backend.services.application_extensions import ApplicationGatewayError
from three_mm_protocol import ApplicationExtensionV1


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux boot clock and durable FD claims")

DEVICE_ID = "dev_0123456789abcdef0123456789abcdef"


def admitted_call(calls, *args, **kwargs):
    assert kwargs["before_dispatch"]()
    calls.append((args, kwargs))
    return {}


def application_definition() -> ApplicationExtensionV1:
    event_schema = {
        "type": "object",
        "properties": {
            "event_id": {"type": "string"},
            "device_id": {"type": "string"},
            "event_type": {"type": "string"},
            "occurred_at": {"type": "string"},
            "payload": {"type": "object"},
        },
        "required": ["event_id", "device_id", "event_type", "occurred_at", "payload"],
        "additionalProperties": False,
    }
    return ApplicationExtensionV1.model_validate(
        {
            "application_extension_version": 1,
            "module_id": "org.3mm.broker-test",
            "version": "1.0.0",
            "service": {
                "artifact": "service/broker_test.whl",
                "artifact_sha256": "a" * 64,
                "entrypoint": "broker_test:create_service",
                "health_operation_id": "health",
            },
            "operations": [
                {
                    "operation_id": "health",
                    "kind": "query",
                    "audiences": ["internal"],
                    "idempotency": "forbidden",
                    "output_schema": {
                        "type": "object",
                        "properties": {"status": {"type": "string", "enum": ["ready"]}},
                        "required": ["status"],
                        "additionalProperties": False,
                    },
                },
                {
                    "operation_id": "process_scan",
                    "kind": "command",
                    "audiences": ["internal"],
                    "idempotency": "required",
                    "input_schema": event_schema,
                },
            ],
            "event_subscriptions": [
                {
                    "subscription_id": "identifier_scans",
                    "event_type": "identifier.scan.v1",
                    "capability_id": "identifier.scan.v1",
                    "handler_operation_id": "process_scan",
                    "device_scope_config_key": "READER_DEVICE_ID",
                    "max_backlog": 2,
                }
            ],
            "storage": {
                "schema_revision": "0001",
                "migration_entrypoint": "broker_test:get_migrations",
            },
        }
    )


@pytest.fixture
def broker_db(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'events.db'}")
    Base.metadata.create_all(engine)
    db = Session(engine)
    device = Device(
        device_id=DEVICE_ID,
        display_name="reader",
        role="node",
        protocol_version="1.0",
        approved_at=datetime.now(UTC),
    )
    package = ModulePackage(
        module_id="org.3mm.broker-test",
        version="1.0.0",
        manifest={
            "permissions": ["data.read", "data.write", "events.consume", "process.spawn"],
            "capabilities": {"consumes": ["identifier.scan.v1"]},
            "configuration_defaults": {"READER_DEVICE_ID": DEVICE_ID},
        },
        sha256="b" * 64,
        size_bytes=1,
        file_path="unused.zip",
        registrations=[],
    )
    db.add_all([device, package])
    db.flush()
    installation = ApplicationExtensionInstallation(
        module_id=package.module_id,
        module_package_id=package.id,
        instance_id="1" * 24,
        active_version="1.0.0",
        status="active",
        enabled=True,
        socket_path="unused.sock",
    )
    db.add(installation)
    db.commit()
    monkeypatch.setattr(
        "backend.services.application_events.load_application_definition",
        lambda _package: application_definition(),
    )
    from backend.services import application_extensions as gateway, application_events as broker
    key_root=tmp_path/'keys';key_root.mkdir()
    (key_root/(installation.instance_id+'.key')).write_bytes(b's'*32)
    monkeypatch.setattr(gateway,'load_application_package',lambda p:SimpleNamespace(
        application_extension=application_definition(),compiled_ui=None))
    state=SimpleNamespace(db=db,device=device,installation=installation,package=package,
        settings=ApplicationRuntimeSettings(key_root=key_root),calls=[],mode='valid')
    def send(prepared,request_id):
        assert not db.in_transaction()
        with Session(engine) as observer:
            current=observer.scalar(select(ApplicationEventDelivery).where(
                ApplicationEventDelivery.status=='delivering'))
            assert current.attempts>=1
        state.calls.append((prepared.operation_id,prepared.payload,prepared.context))
        if state.mode=='send_error':raise OSError('test service unavailable')
        from three_mm_runtime.application_transport import sign_message,send_message
        left,right=socket.socketpair()
        with right:send_message(right,sign_message({'version':1,'request_id':request_id,
            'timestamp':int(time.time()),'ok':True,'result':{}},prepared.secret))
        return left
    monkeypatch.setattr(broker,'_send_event_invocation',send)
    yield state
    db.close()
    engine.dispose()


def add_event(db: Session, device: Device, suffix: str) -> DeviceEvent:
    event = DeviceEvent(
        device_id=device.id,
        event_id=f"evt_{suffix:0<32}"[:36],
        event_type="identifier.scan.v1",
        payload={
            "schema_version": 1,
            "capability_id": "identifier.scan.v1",
            "opaque_identifier": f"TAG-{suffix}",
            "reader_id": "reader.mock.1",
            "adapter_kind": "mock",
            "sequence": 1,
            "device_health": "ok",
            "scan_metadata": {},
        },
        occurred_at=datetime.now(UTC),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def pump(db,settings,*,force=False,generation='test-runtime'):
    from three_mm_platform_wire import read_frame
    if force:request_application_event_retry(db)
    for _ in range(100):
        begin,origin=claim_event_delivery(db,settings,runtime_generation=generation)
        if begin['idle']:return
        try:
            with origin:response=read_frame(origin,time.monotonic()+1,max_bytes=1024*1024)
            complete_event_delivery(db,settings,begin['receipt'],runtime_generation=generation,response=response)
        except (OSError,ValueError):
            complete_event_delivery(db,settings,begin['receipt'],runtime_generation=generation,failure='handler_unavailable')
    raise AssertionError('Test pump exceeded its bound')


def row(s):
    s.db.expire_all()
    return s.db.scalar(select(ApplicationEventDelivery).order_by(ApplicationEventDelivery.id))


def test_enqueue_only_persists_and_completion_is_idempotent(broker_db):
    s=broker_db;event=add_event(s.db,s.device,'a')
    enqueue_application_event(s.db,event,s.settings)
    enqueue_application_event(s.db,event,s.settings)
    assert row(s).status=='pending' and row(s).attempts==0 and not s.calls
    begin,origin=claim_event_delivery(s.db,s.settings,runtime_generation='owner')
    assert row(s).status=='delivering' and row(s).attempts==1
    from three_mm_platform_wire import read_frame
    with origin:response=read_frame(origin,time.monotonic()+1)
    for _ in range(2):complete_event_delivery(s.db,s.settings,begin['receipt'],runtime_generation='owner',response=response)
    pump(s.db,s.settings)
    cursor=s.db.scalar(select(ApplicationEventCursor))
    assert cursor.acknowledged_count==1 and cursor.last_event_id==event.event_id
    assert len(s.calls)==1 and s.calls[0][1]['event_id']==s.calls[0][2]['idempotency_key']==event.event_id


def test_failed_delivery_is_durable_backed_off_and_bounded(broker_db):
    s=broker_db;s.mode='send_error';event=add_event(s.db,s.device,'b')
    enqueue_application_event(s.db,event,s.settings)
    pump(s.db,s.settings)
    assert row(s).attempts==1 and row(s).status=='pending'
    pump(s.db,s.settings);assert row(s).attempts==1
    for _ in range(4):pump(s.db,s.settings,force=True)
    assert row(s).status=='dead_letter' and row(s).attempts==5
    assert row(s).last_error=='dispatch_unconfirmed'
    assert s.db.scalar(select(ApplicationEventCursor)).dead_letter_count==1
    pump(s.db,s.settings,force=True);assert len(s.calls)==5


@pytest.mark.parametrize('change',['mode','device','permission','capability','scope'])
def test_enqueue_fresh_declared_source_and_mode_only(broker_db,change):
    s=broker_db;event=add_event(s.db,s.device,'c');s.db.expire_on_commit=False
    with Session(s.db.get_bind()) as writer:
        if change=='mode':writer.execute(update(ApplicationExtensionInstallation).values(authority_mode='review_required'))
        elif change=='device':writer.execute(update(Device).values(revoked_at=datetime.now(UTC)))
        else:
            manifest=dict(s.package.manifest)
            if change=='permission':manifest['permissions']=[]
            elif change=='capability':manifest['capabilities']={'consumes':[]}
            else:manifest['configuration_defaults']={'READER_DEVICE_ID':'foreign'}
            writer.execute(update(ModulePackage).values(manifest=manifest))
        writer.commit()
    enqueue_application_event(s.db,event,s.settings)
    assert row(s) is None and not s.calls


@pytest.mark.parametrize('mode',['enforced','review_required'])
def test_declarations_are_not_event_grants(broker_db,mode):
    s=broker_db;s.installation.authority_mode=mode;s.db.commit()
    enqueue_application_event(s.db,add_event(s.db,s.device,'denied'),s.settings)
    assert row(s) is None and not s.calls


@pytest.mark.parametrize('change',['enforced','review_required','scope','permission','capability','event_type','event_capability','device','artifact'])
def test_retry_rechecks_current_authority_without_replaying_denied_data(broker_db,change):
    s=broker_db;s.mode='send_error';event=add_event(s.db,s.device,'pending')
    enqueue_application_event(s.db,event,s.settings);pump(s.db,s.settings)
    assert row(s).attempts==1
    if change in {'enforced','review_required'}:s.installation.authority_mode=change
    elif change=='scope':s.installation.configuration={'READER_DEVICE_ID':'foreign'}
    elif change=='permission':s.package.manifest={**s.package.manifest,'permissions':[]}
    elif change=='capability':s.package.manifest={**s.package.manifest,'capabilities':{'consumes':[]}}
    elif change=='event_type':event.event_type='other.event.v1'
    elif change=='event_capability':event.payload={**event.payload,'capability_id':'foreign'}
    elif change=='device':s.device.revoked_at=datetime.now(UTC)
    elif change=='artifact':s.installation.active_version='2.0.0'
    s.db.commit();pump(s.db,s.settings,force=True)
    assert row(s).status=='dead_letter' and row(s).attempts==1 and len(s.calls)==1
    assert s.db.scalar(select(ApplicationEventCursor)).dead_letter_count==1
    assert application_event_status(s.db)[0]['backlog']==0 and s.db.get(DeviceEvent,event.id) is not None


@pytest.mark.parametrize('change',['enforced','review_required','disable','epoch','configuration','device_revoke'])
def test_change_after_preflight_denies_before_attempt_or_service_io(broker_db,monkeypatch,change):
    from backend.services import application_extensions as gateway
    s=broker_db;event=add_event(s.db,s.device,'race')
    enqueue_application_event(s.db,event,s.settings)
    def preflight(_package):
        with Session(s.db.get_bind()) as writer:
            if change=='device_revoke':writer.execute(update(Device).values(revoked_at=datetime.now(UTC)))
            else:
                values={'enforced':{'authority_mode':'enforced'},'review_required':{'authority_mode':'review_required'},
                    'disable':{'enabled':False,'status':'disabled'},'epoch':{'authority_epoch':'e'*32},
                    'configuration':{'configuration':{'READER_DEVICE_ID':'foreign'}}}[change]
                writer.execute(update(ApplicationExtensionInstallation).values(**values))
            writer.commit()
        return SimpleNamespace(application_extension=application_definition(),compiled_ui=None)
    monkeypatch.setattr(gateway,'load_application_package',preflight)
    pump(s.db,s.settings)
    assert row(s).status=='dead_letter' and row(s).attempts==0 and not s.calls


def test_fifo_backlog_and_admin_retry_do_not_steal_inflight_claim(broker_db):
    s=broker_db
    for suffix in ['first','second','overflow']:enqueue_application_event(s.db,add_event(s.db,s.device,suffix),s.settings)
    begin,origin=claim_event_delivery(s.db,s.settings,runtime_generation='owner')
    original=row(s).dispatch_id
    request_application_event_retry(s.db)
    assert claim_event_delivery(s.db,s.settings,runtime_generation='other')[0]['idle']
    assert row(s).dispatch_id==original and application_event_status(s.db)[0]['backlog']==2
    from three_mm_platform_wire import read_frame
    with origin:response=read_frame(origin,time.monotonic()+1)
    complete_event_delivery(s.db,s.settings,begin['receipt'],runtime_generation='owner',response=response)
    pump(s.db,s.settings)
    assert [c[1]['event_id'] for c in s.calls]==['evt_first000000000000000000000000000','evt_second00000000000000000000000000']
    cursor=s.db.scalar(select(ApplicationEventCursor))
    assert cursor.acknowledged_count==2 and cursor.dead_letter_count==1


@pytest.mark.parametrize('change',['expiry','reboot'])
def test_lost_response_has_one_durable_attempt_and_fresh_claim_after_expiry(broker_db,monkeypatch,change):
    from backend.services import application_events as broker
    s=broker_db;clock=['a'*36,1000];monkeypatch.setattr(broker,'_clock',lambda:tuple(clock))
    event=add_event(s.db,s.device,'lost');enqueue_application_event(s.db,event,s.settings)
    first,origin=claim_event_delivery(s.db,s.settings,runtime_generation='old');origin.close()
    assert claim_event_delivery(s.db,s.settings,runtime_generation='new')[0]['idle']
    if change=='expiry':clock[1]+=broker.CLAIM_LEASE_MS+1
    else:clock[:]=['b'*36,1]
    second,origin=claim_event_delivery(s.db,s.settings,runtime_generation='new')
    assert row(s).attempts==2 and second['receipt']!=first['receipt']
    with pytest.raises(ValueError):complete_event_delivery(s.db,s.settings,first['receipt'],runtime_generation='old',failure='handler_unavailable')
    from three_mm_platform_wire import read_frame
    with origin:response=read_frame(origin,time.monotonic()+1)
    complete_event_delivery(s.db,s.settings,second['receipt'],runtime_generation='new',response=response)
    assert row(s).status=='acknowledged' and s.calls[0][2]['idempotency_key']==s.calls[1][2]['idempotency_key']


@pytest.mark.parametrize('damage',['owner','receipt','response','expired'])
def test_result_cannot_complete_foreign_forged_or_expired_attempt(broker_db,monkeypatch,damage):
    from backend.services import application_events as broker
    from three_mm_platform_wire import read_frame
    s=broker_db;clock=['a'*36,1000];monkeypatch.setattr(broker,'_clock',lambda:tuple(clock))
    enqueue_application_event(s.db,add_event(s.db,s.device,'result'),s.settings)
    begin,origin=claim_event_delivery(s.db,s.settings,runtime_generation='owner')
    with origin:response=read_frame(origin,time.monotonic()+1)
    receipt=dict(begin['receipt']);owner='owner'
    if damage=='owner':owner='foreign'
    elif damage=='receipt':receipt['dispatch_id']='f'*32
    elif damage=='expired':clock[1]+=broker.CLAIM_LEASE_MS+1
    elif damage=='response':response['result']={'tampered':True}
    if damage=='response':
        complete_event_delivery(s.db,s.settings,receipt,runtime_generation=owner,response=response)
        assert row(s).status=='pending' and row(s).last_error=='response_invalid'
    else:
        with pytest.raises(ValueError):complete_event_delivery(s.db,s.settings,receipt,runtime_generation=owner,response=response)
        assert row(s).status=='delivering'
    assert s.db.scalar(select(ApplicationEventCursor)).acknowledged_count==0


def test_already_admitted_success_is_accounted_after_disable(broker_db):
    from three_mm_platform_wire import read_frame
    s=broker_db;enqueue_application_event(s.db,add_event(s.db,s.device,'admitted'),s.settings)
    begin,origin=claim_event_delivery(s.db,s.settings,runtime_generation='owner')
    with origin:response=read_frame(origin,time.monotonic()+1)
    s.installation.enabled=False;s.installation.status='disabled';s.db.commit()
    complete_event_delivery(s.db,s.settings,begin['receipt'],runtime_generation='owner',response=response)
    assert row(s).status=='acknowledged'


def test_old_terminal_attempt_can_be_pruned_without_losing_outcome_counter(broker_db,monkeypatch):
    from backend.services import application_events as broker
    s=broker_db;monkeypatch.setattr(broker,'MAX_STORED_DEAD_LETTERS',1)
    event=add_event(s.db,s.device,'old');enqueue_application_event(s.db,event,s.settings)
    # A newer terminal row precedes this older attempt's fifth failed outcome.
    newer=add_event(s.db,s.device,'newer')
    s.db.add(ApplicationEventDelivery(application_installation_id=s.installation.id,
        subscription_id='identifier_scans',device_event_id=newer.id,status='dead_letter',attempts=5))
    old=row(s);old.attempts=4;s.db.commit();s.mode='send_error'
    pump(s.db,s.settings)
    assert s.db.get(ApplicationEventDelivery,old.id) is None
    assert s.db.scalar(select(ApplicationEventCursor)).dead_letter_count==1


def test_preexisting_exhausted_pending_attempt_is_not_dispatched_a_sixth_time(broker_db):
    s=broker_db;enqueue_application_event(s.db,add_event(s.db,s.device,'exhausted'),s.settings)
    row(s).attempts=5;s.db.commit();pump(s.db,s.settings)
    assert row(s).status=='dead_letter' and row(s).attempts==5 and not s.calls
    assert row(s).last_error=='attempt_limit_exhausted'


def test_paused_subscription_cannot_starve_an_active_head_at_batch_limit(broker_db,monkeypatch):
    from backend.services import application_events as broker
    s=broker_db;monkeypatch.setattr(broker,'MAX_DRAIN_BATCH',1)
    package=ModulePackage(module_id='org.example.paused',version='1.0.0',manifest={},sha256='c'*64,
        size_bytes=1,file_path='unused',registrations=[])
    s.db.add(package);s.db.flush()
    paused=ApplicationExtensionInstallation(module_id=package.module_id,module_package_id=package.id,
        instance_id='2'*24,active_version=package.version,enabled=False,status='disabled',socket_path='unused')
    s.db.add(paused);s.db.flush()
    event=add_event(s.db,s.device,'paused')
    s.db.add(ApplicationEventDelivery(application_installation_id=paused.id,subscription_id='paused',
        device_event_id=event.id,status='pending'));s.db.commit()
    enqueue_application_event(s.db,add_event(s.db,s.device,'active'),s.settings)
    pump(s.db,s.settings)
    assert len(s.calls)==1
    assert s.db.scalar(select(ApplicationEventDelivery).where(
        ApplicationEventDelivery.application_installation_id==s.installation.id)).status=='acknowledged'
    assert s.db.scalar(select(ApplicationEventDelivery).where(
        ApplicationEventDelivery.application_installation_id==paused.id)).status=='pending'
