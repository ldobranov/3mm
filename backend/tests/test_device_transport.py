"""C10 proof: real Core persistence/services, protocol objects, no HTTP at all."""

import ast
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import backend.database  # register model metadata
from backend.db.base import Base
from backend.db.authority import CoreAuthorityGuard
from backend.db.device import (
    Device,
    DeviceCredential as StoredCredential,
    DevicePairingRequest,
    DeviceState,
    DeviceEvent,
)
from backend.db.user import User
from backend.services.device_pairing import approve_pairing_request
from backend.services.device_protocol import (
    authenticate_device,
    enroll,
    DeviceOperations,
)
from backend.services.device_commands import queue_command, commit_queued_command
from backend.services.device_capability_registry import has_registered_capability
from agent.core_client import (
    CorePublisher,
    DeviceCredential,
    CommandJournal,
    OutboxStore,
    ReconciliationStore,
)
from three_mm_protocol import (
    AgentHeartbeat,
    AgentCommandResult,
    AgentReportedState,
    CapabilityProviderReportV1,
    CapabilityStateReportV1,
    DeviceEventV1,
    DeviceInventoryV2,
)
from three_mm_protocol.fleet_pairing import NodeEnrollmentRequest
from three_mm_protocol.transport import DeviceProtocolError, DeviceTransportError


class MemoryTransport:
    """Test-only adapter. Every message goes through normal credential validation."""

    def __init__(self, db, credential):
        self.db, self.credential = db, credential
        self.device_id = credential.device_id
        self.offline = False
        self.lose_reply = False
        self.lose_reply_type = None

    def operations(self):
        if self.offline:
            raise DeviceTransportError("disconnected")
        return DeviceOperations(
            self.db,
            authenticate_device(
                self.db,
                self.credential.credential_id,
                self.credential.credential_secret,
            ),
            credential_id=self.credential.credential_id,
        )

    def enroll(self, request):
        return enroll(self.db, request)

    def publish(self, report):
        operations = self.operations()
        method = {
            AgentHeartbeat: "heartbeat",
            DeviceInventoryV2: "inventory",
            AgentCommandResult: "command_result",
            AgentReportedState: "reported_state",
            CapabilityProviderReportV1: "provider",
            CapabilityStateReportV1: "capability_state",
            DeviceEventV1: "event",
        }[type(report)]
        result = getattr(operations, method)(report)
        if self.lose_reply and (
            self.lose_reply_type is None or isinstance(report, self.lose_reply_type)
        ):
            self.lose_reply = False
            raise DeviceTransportError("lost acknowledgement AFTER Core commit")
        return result

    def receive_command(self, *, timeout_seconds=0):
        return self.operations().next_command()

    def desired_state(self):
        return self.operations().desired_state()

    def protocol(self):
        return self.operations().protocol()

    def report_features(self, report):
        return self.operations().features(report)

    def authorize_execution(self, command_id):
        return self.operations().authorize_execution(command_id)


@pytest.fixture
def node(monkeypatch):
    def no_http(*args, **kwargs):
        pytest.fail("The memory adapter must never call HTTP")

    for verb in ("get", "post", "put", "request"):
        monkeypatch.setattr("requests." + verb, no_http)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        admin = User(
            username="admin",
            email="test@example.com",
            role="admin",
            hashed_password="not-used",
        )
        db.add_all([admin, CoreAuthorityGuard(singleton_id=1)])
        db.commit()
        credential = DeviceCredential(
            device_id="dev_" + "a" * 32,
            credential_id="cred_" + "b" * 32,
            credential_secret="test-only-" + "s" * 40,
        )
        transport = MemoryTransport(db, credential)
        request = NodeEnrollmentRequest(
            device_id=credential.device_id,
            credential_id=credential.credential_id,
            display_name="Neutral transport",
            request_token="c" * 64,
            credential_secret_hash=hashlib.sha256(
                credential.credential_secret.encode()
            ).hexdigest(),
        )
        assert transport.enroll(request).status == "pending_approval"
        with pytest.raises(DeviceProtocolError):
            transport.operations()
        pending = db.scalar(select(DevicePairingRequest))
        approve_pairing_request(db, request_id=pending.id, approved_by_user_id=admin.id)
        assert transport.enroll(request).status == "approved"
        yield transport, db, credential
    engine.dispose()


def inventory(device_id):
    return DeviceInventoryV2(
        schema_version=2,
        device_id=device_id,
        collected_at=datetime.now(UTC),
        platform={"family": "embedded", "system": "memory-reference"},
        runtime={"name": "test-runtime", "version": "1.0"},
    )


def test_object_transport_covers_device_operations_and_reconnect(node, tmp_path):
    transport, db, credential = node
    transport.publish(inventory(credential.device_id))
    transport.publish(
        AgentHeartbeat(
            device_id=credential.device_id, sent_at=datetime.now(UTC), uptime_seconds=1
        )
    )
    provider = CapabilityProviderReportV1(
        schema_version=1,
        device_id=credential.device_id,
        provider_type="embedded_firmware",
        provider_id="test-firmware",
        provider_version="1.0",
        expected_revision=0,
        capabilities=({"capability_id": "gpio.digital.control"},),
    )
    transport.publish(provider)
    device = db.scalar(select(Device))
    assert has_registered_capability(db, device, "gpio.digital.control")
    transport.publish(
        CapabilityStateReportV1(
            device_id=credential.device_id,
            capability_id="gpio.digital.control",
            values={"output": False},
            observed_at=datetime.now(UTC),
        )
    )
    event = DeviceEventV1(
        device_id=credential.device_id,
        event_id="evt_" + "d" * 32,
        event_type="test.changed",
        payload={"value": True},
        occurred_at=datetime.now(UTC),
    )
    transport.publish(event)
    assert transport.publish(event)[1] is True
    assert (
        db.query(DeviceEvent).filter(DeviceEvent.event_id == event.event_id).count()
        == 1
    )
    desired = transport.desired_state()
    transport.publish(
        AgentReportedState(
            device_id=credential.device_id,
            desired_revision=desired.revision,
            applied_revision=desired.revision,
            state=desired.state,
            reported_at=datetime.now(UTC),
        )
    )
    assert db.scalar(select(DeviceState)).reported_revision == desired.revision
    command = queue_command(
        db,
        device=device,
        command_type="capability.invoke",
        payload={
            "capability_id": "gpio.digital.control",
            "action": "set_output",
            "arguments": {"channel": "output", "value": True},
        },
        idempotency_key="logical-action",
        ttl_seconds=30,
    )
    commit_queued_command(db, device=device, command=command)
    received = transport.receive_command()
    assert received.command_id == command.command_id
    result = AgentCommandResult(
        device_id=credential.device_id,
        command_id=received.command_id,
        status="succeeded",
        completed_at=datetime.now(UTC),
        output={"simulated": True},
    )
    transport.lose_reply = True
    with pytest.raises(DeviceTransportError):
        transport.publish(result)
    assert transport.publish(result).status == "succeeded"
    transport.offline = True
    with pytest.raises(DeviceTransportError):
        transport.protocol()
    reconnected = MemoryTransport(db, credential)
    assert reconnected.protocol().device_id == credential.device_id
    assert has_registered_capability(db, device, "gpio.digital.control")
    assert reconnected.receive_command() is None


def test_linux_publisher_can_use_non_http_adapter_with_outbox(node, tmp_path):
    transport, db, credential = node
    publisher = CorePublisher(
        core_url="unused-by-memory-adapter",
        credential=credential,
        inventory_provider=lambda: inventory(credential.device_id),
        inventory_schema_version=2,
        command_journal=CommandJournal(tmp_path),
        reconciliation_store=ReconciliationStore(tmp_path),
        outbox=OutboxStore(tmp_path),
        started_monotonic=0,
        transport=transport,
        feature_negotiation=True,
    )
    publisher._publish_inventory()
    device = db.scalar(select(Device))
    command = queue_command(
        db,
        device=device,
        command_type="agent.refresh_inventory",
        payload={},
        idempotency_key="refresh",
        ttl_seconds=30,
    )
    commit_queued_command(db, device=device, command=command)
    transport.lose_reply = True
    transport.lose_reply_type = AgentCommandResult
    publisher._poll_command()
    assert len(publisher.outbox.load()) == 1
    publisher._flush_outbox()
    assert publisher.outbox.load() == []
    assert publisher.command_journal.get("refresh").status == "succeeded"
    # Offline heartbeat retains the SAME legacy disk record for rollback readers.
    transport.offline = True
    report = AgentHeartbeat(
        device_id=credential.device_id, sent_at=datetime.now(UTC), uptime_seconds=2
    )
    assert not publisher._send_or_queue(
        "heartbeat", report.model_dump(mode="json"), "heartbeat"
    )
    transport.offline = False
    publisher._flush_outbox()
    assert publisher.outbox.load() == []


def test_non_http_adapter_cannot_bypass_identity_or_revocation(node):
    transport, db, credential = node
    wrong = inventory("dev_" + "f" * 32)
    with pytest.raises(DeviceProtocolError) as mismatch:
        transport.publish(wrong)
    assert mismatch.value.kind == "forbidden"
    stored = db.scalar(select(StoredCredential))
    stored.revoked_at = datetime.now(UTC)
    db.commit()
    with pytest.raises(DeviceProtocolError) as revoked:
        transport.protocol()
    assert revoked.value.kind == "unauthorized"


def test_common_operations_and_protocol_port_have_no_http_dependencies():
    root = Path(__file__).resolve().parents[2]
    for file in (
        root / "backend/services/device_protocol.py",
        root / "three_mm_protocol/transport.py",
    ):
        source = file.read_text()
        for item in ast.walk(ast.parse(source)):
            if isinstance(item, ast.ImportFrom):
                assert not (item.module or "").startswith(
                    ("fastapi", "requests", "backend.routes")
                )
            if isinstance(item, ast.Import):
                assert not any(
                    alias.name.startswith(("fastapi", "requests"))
                    for alias in item.names
                )
        assert "/api/v1/" not in source
