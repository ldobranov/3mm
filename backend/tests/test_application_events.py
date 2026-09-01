from datetime import UTC, datetime

import backend.database  # noqa: F401 - register all model metadata
import pytest
from sqlalchemy import create_engine, select
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
from backend.services.application_events import enqueue_application_event
from backend.services.application_extensions import ApplicationGatewayError
from three_mm_protocol import ApplicationExtensionV1


DEVICE_ID = "dev_0123456789abcdef0123456789abcdef"


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
def broker_db(monkeypatch):
    engine = create_engine("sqlite://")
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
        lambda *args, **kwargs: calls.append((args, kwargs)) or {},
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
        lambda *args, **kwargs: calls.append((args, kwargs)) or {},
    )

    enqueue_application_event(db, event, ApplicationRuntimeSettings())

    assert db.scalar(select(ApplicationEventDelivery)).status == "acknowledged"
    assert len(calls) == 1
