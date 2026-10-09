from datetime import UTC, datetime

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
    retry_application_events,
)
from backend.services.application_extensions import ApplicationGatewayError
from three_mm_protocol import ApplicationExtensionV1


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
    yield db, device, installation, package
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


def test_event_is_acknowledged_once_after_handler_returns(monkeypatch, broker_db):
    db, device, _installation, _package = broker_db
    event = add_event(db, device, "a")
    calls = []
    monkeypatch.setattr(
        "backend.services.application_events.invoke_application",
        lambda *args, **kwargs: admitted_call(calls, *args, **kwargs),
    )

    enqueue_application_event(db, event, ApplicationRuntimeSettings())
    enqueue_application_event(db, event, ApplicationRuntimeSettings())

    delivery = db.scalar(select(ApplicationEventDelivery))
    cursor = db.scalar(select(ApplicationEventCursor))
    assert delivery.status == "acknowledged"
    assert delivery.attempts == 1
    assert cursor.acknowledged_count == 1
    assert cursor.last_event_id == event.event_id
    assert len(calls) == 1
    assert calls[0][0][4]["event_id"] == event.event_id
    assert calls[0][0][5]["idempotency_key"] == event.event_id


def test_failed_delivery_is_durable_and_dead_letters_after_bound(monkeypatch, broker_db):
    db, device, _installation, _package = broker_db
    event = add_event(db, device, "b")

    def fail(*_args, **_kwargs):
        raise ApplicationGatewayError("service unavailable")

    monkeypatch.setattr("backend.services.application_events.invoke_application", fail)
    for _attempt in range(5):
        enqueue_application_event(db, event, ApplicationRuntimeSettings())

    delivery = db.scalar(select(ApplicationEventDelivery))
    cursor = db.scalar(select(ApplicationEventCursor))
    assert delivery.status == "dead_letter"
    assert delivery.attempts == 5
    assert delivery.last_error == "service unavailable"
    assert cursor.dead_letter_count == 1


def test_device_scope_and_manifest_permission_fail_closed(monkeypatch, broker_db):
    db, device, _installation, package = broker_db
    event = add_event(db, device, "c")
    package.manifest = {
        **package.manifest,
        "configuration_defaults": {"READER_DEVICE_ID": "another-device"},
    }
    db.commit()
    monkeypatch.setattr(
        "backend.services.application_events.invoke_application",
        lambda *_args, **_kwargs: pytest.fail("handler must not be called"),
    )

    enqueue_application_event(db, event, ApplicationRuntimeSettings())

    assert db.scalar(select(ApplicationEventDelivery)) is None


def test_saved_installation_device_binding_overrides_package_default(
    monkeypatch, broker_db
):
    db, device, installation, package = broker_db
    package.manifest = {
        **package.manifest,
        "configuration_defaults": {"READER_DEVICE_ID": "another-device"},
    }
    installation.configuration = {"READER_DEVICE_ID": DEVICE_ID}
    db.commit()
    event = add_event(db, device, "d")
    calls = []
    monkeypatch.setattr(
        "backend.services.application_events.invoke_application",
        lambda *args, **kwargs: admitted_call(calls, *args, **kwargs),
    )

    enqueue_application_event(db, event, ApplicationRuntimeSettings())

    assert db.scalar(select(ApplicationEventDelivery)).status == "acknowledged"
    assert len(calls) == 1


@pytest.mark.parametrize("mode", ["enforced", "review_required"])
def test_opted_in_event_declarations_are_not_grants(monkeypatch, broker_db, mode):
    db, device, installation, _package = broker_db
    event = add_event(db, device, "denied")
    installation.authority_mode = mode
    db.commit()
    monkeypatch.setattr(
        "backend.services.application_events.invoke_application",
        lambda *_args, **_kwargs: pytest.fail("unsupported event grant must deny"),
    )
    enqueue_application_event(db, event, ApplicationRuntimeSettings())
    assert db.scalar(select(ApplicationEventDelivery)) is None
    assert db.scalar(select(ApplicationEventCursor)) is None


@pytest.mark.parametrize("change", ["mode", "device"])
def test_enqueue_does_not_trust_a_cached_authority_snapshot(
    monkeypatch, broker_db, change,
):
    db, device, installation, _package = broker_db
    db.expire_on_commit = False
    event = add_event(db, device, "cached")
    assert installation.authority_mode == "compatibility" and device.revoked_at is None
    with Session(db.get_bind()) as writer:
        if change == "mode":
            writer.execute(update(ApplicationExtensionInstallation)
                .where(ApplicationExtensionInstallation.id == installation.id)
                .values(authority_mode="review_required"))
        else:
            writer.execute(update(Device).where(Device.id == device.id)
                .values(revoked_at=datetime.now(UTC)))
        writer.commit()
    monkeypatch.setattr("backend.services.application_events.invoke_application",
        lambda *_args, **_kwargs: pytest.fail("cached authority must not admit data"))
    enqueue_application_event(db, event, ApplicationRuntimeSettings())
    assert db.scalar(select(ApplicationEventDelivery)) is None


@pytest.mark.parametrize("change", [
    "enforced", "review_required", "device_binding", "permission", "capability",
    "event_type", "event_capability", "revoked_device", "artifact",
])
def test_retry_rechecks_current_authority_and_retains_terminal_evidence(
    monkeypatch, broker_db, change,
):
    db, device, installation, package = broker_db
    event = add_event(db, device, "pending")

    def fail(*_args, **_kwargs):
        raise ApplicationGatewayError("temporarily unavailable")

    monkeypatch.setattr("backend.services.application_events.invoke_application", fail)
    enqueue_application_event(db, event, ApplicationRuntimeSettings())
    delivery = db.scalar(select(ApplicationEventDelivery))
    assert delivery.status == "pending" and delivery.attempts == 1
    if change in {"enforced", "review_required"}:
        installation.authority_mode = change
    elif change == "device_binding":
        installation.configuration = {"READER_DEVICE_ID": "dev_" + "f" * 32}
    elif change == "permission":
        package.manifest = {**package.manifest, "permissions": []}
    elif change == "capability":
        package.manifest = {**package.manifest, "capabilities": {"consumes": []}}
    elif change == "event_type":
        event.event_type = "another.event.v1"
    elif change == "event_capability":
        event.payload = {**event.payload, "capability_id": "another.capability.v1"}
    elif change == "revoked_device":
        device.revoked_at = datetime.now(UTC)
    elif change == "artifact":
        installation.active_version = "2.0.0"
    db.commit()
    monkeypatch.setattr(
        "backend.services.application_events.invoke_application",
        lambda *_args, **_kwargs: pytest.fail("stale backlog must not reach the handler"),
    )
    retry_application_events(db, ApplicationRuntimeSettings())
    retry_application_events(db, ApplicationRuntimeSettings())
    db.refresh(delivery)
    assert delivery.status == "dead_letter" and delivery.attempts == 1
    assert delivery.last_error == "Event subscription authority is unavailable or changed"
    cursor = db.scalar(select(ApplicationEventCursor))
    assert cursor.dead_letter_count == 1 and cursor.acknowledged_count == 0
    assert cursor.last_event_id == event.event_id
    assert application_event_status(db)[0]["backlog"] == 0
    assert db.get(DeviceEvent, event.id) is not None
    # Restoring a binding/mode cannot silently replay denied historical data.
    installation.authority_mode = "compatibility"
    installation.configuration = {}
    db.commit()
    retry_application_events(db, ApplicationRuntimeSettings())
    assert db.scalar(select(ApplicationEventCursor)).dead_letter_count == 1


def test_resolved_configuration_does_not_mutate_shared_package_defaults(
    monkeypatch, broker_db,
):
    db, device, installation, package = broker_db
    other = Device(device_id="dev_" + "e" * 32, role="node", protocol_version="1.0",
        approved_at=datetime.now(UTC))
    db.add(other)
    installation.configuration = {"READER_DEVICE_ID": other.device_id}
    db.commit()
    calls = []
    monkeypatch.setattr("backend.services.application_events.invoke_application",
        lambda *args, **kwargs: admitted_call(calls, *args, **kwargs))
    enqueue_application_event(db, add_event(db, other, "override"), ApplicationRuntimeSettings())
    assert package.manifest["configuration_defaults"]["READER_DEVICE_ID"] == DEVICE_ID
    installation.configuration = {}
    db.commit()
    enqueue_application_event(db, add_event(db, device, "default"), ApplicationRuntimeSettings())
    assert len(calls) == 2


def gateway_settings(monkeypatch, tmp_path, installation):
    from backend.services import application_extensions
    monkeypatch.setattr(application_extensions, "load_application_definition",
        lambda _package: application_definition())
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / f"{installation.instance_id}.key").write_bytes(b"s" * 32)
    return ApplicationRuntimeSettings(key_root=keys)


@pytest.mark.parametrize("change", [
    "enforced", "review_required", "disable", "epoch", "configuration", "device_revoke",
])
def test_real_gateway_denies_change_between_preflight_and_dispatch(
    monkeypatch, broker_db, tmp_path, change,
):
    from backend.services import application_extensions
    from backend.db.authority import new_authority_generation
    db, device, installation, package = broker_db
    settings = gateway_settings(monkeypatch, tmp_path, installation)
    installation_id, device_id = installation.id, device.id
    event = add_event(db, device, "race")

    def preflight(_package):
        # A separate real DB writer, after matching and before actual admission.
        with Session(db.get_bind()) as writer:
            if change == "device_revoke":
                writer.execute(update(Device).where(Device.id == device_id)
                    .values(revoked_at=datetime.now(UTC)))
            else:
                values = {
                    "enforced": {"authority_mode": "enforced"},
                    "review_required": {"authority_mode": "review_required"},
                    "disable": {"enabled": False, "status": "disabled"},
                    "epoch": {"authority_epoch": new_authority_generation()},
                    "configuration": {"configuration": {"READER_DEVICE_ID": "dev_" + "f" * 32}},
                }[change]
                writer.execute(update(ApplicationExtensionInstallation)
                    .where(ApplicationExtensionInstallation.id == installation_id).values(**values))
            writer.commit()
        return application_definition()

    monkeypatch.setattr(application_extensions, "load_application_definition", preflight)
    monkeypatch.setattr(application_extensions, "ApplicationServiceClient",
        lambda *_args: pytest.fail("revoked event must not be dispatched"))
    enqueue_application_event(db, event, settings)
    delivery = db.scalar(select(ApplicationEventDelivery))
    assert delivery.status == "dead_letter" and delivery.attempts == 0
    assert delivery.last_error == "Event subscription authority is unavailable or changed"
    assert db.scalar(select(ApplicationEventCursor)).dead_letter_count == 1


def test_gateway_commits_attempt_before_ipc_and_later_revocation_blocks_retry(
    monkeypatch, broker_db, tmp_path,
):
    from backend.services import application_extensions
    from three_mm_runtime.application_transport import ApplicationTransportError
    db, device, installation, _package = broker_db
    settings = gateway_settings(monkeypatch, tmp_path, installation)
    installation_id = installation.id
    event = add_event(db, device, "admitted")
    calls = []

    class Client:
        def __init__(self, socket_path, _secret, _timeout):
            assert str(socket_path) == "unused.sock"

        def invoke(self, operation_id, payload, context):
            # Admission left no DB transaction/lock open across service I/O.
            assert not db.in_transaction()
            with Session(db.get_bind()) as writer:
                pending = writer.scalar(select(ApplicationEventDelivery))
                assert pending.status == "pending" and pending.attempts == 1
                writer.execute(update(ApplicationExtensionInstallation)
                    .where(ApplicationExtensionInstallation.id == installation_id)
                    .values(authority_mode="review_required"))
                writer.commit()
            calls.append((operation_id, payload, context))
            raise ApplicationTransportError("response lost")

    monkeypatch.setattr(application_extensions, "ApplicationServiceClient", Client)
    enqueue_application_event(db, event, settings)
    assert len(calls) == 1
    assert calls[0][2]["idempotency_key"] == event.event_id
    delivery = db.scalar(select(ApplicationEventDelivery))
    assert delivery.status == "pending" and delivery.attempts == 1
    retry_application_events(db, settings)
    assert len(calls) == 1
    db.refresh(delivery)
    assert delivery.status == "dead_letter" and delivery.attempts == 1
