"""M20 provider/runtime writers: atomic authority changes, not telemetry grants."""

from datetime import UTC, datetime, timedelta
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from backend.db.authority import CoreAuthorityGuard
from backend.db.base import Base
from backend.db.device import (
    Device, DeviceCapabilityProvider, DeviceCapabilityState, DeviceCommand,
    DeviceCredential, DevicePlatformState, DeviceState,
)
from backend.routes.device_capabilities import router as provider_router
from backend.routes.device_runtime_features import router as runtime_router
from backend.services.authority_metadata import (
    AuthorityMetadataError, read_authority_guard, read_device_control,
)
from backend.services.device_capability_registry import (
    CapabilityRegistryError, configure_provider, registered_capabilities,
    replace_provider, report_availability, set_provider_enabled,
)
from backend.services.device_pairing import credential_secret_hash
from backend.services.device_protocol import DeviceOperations, authenticate_device
from backend.services.device_runtime_features import replace_runtime_features
from backend.tests.test_device_pairing_authority import db, DEVICE_ID  # noqa: F401
from backend.utils.db_utils import get_db
from three_mm_protocol.capability_availability import (
    CapabilityAvailabilityReportV1, CapabilityConfigurationV1, declaration_digest,
)
from three_mm_protocol.device_capabilities import (
    CapabilityProviderReportV1, CapabilityProviderReportV2,
)
from three_mm_protocol.node_features import (
    DeviceRuntimeFeaturesReportV1, MANDATORY_NODE_FEATURES,
)
from three_mm_protocol.transport import DeviceProtocolError


PROVIDER = "example.runtime"
CAPABILITY = "example.control"
SECRET = "reference-test-only-secret"
WRITERS = ("provider", "configuration", "enabled", "runtime")


@pytest.fixture
def node(db):
    device = Device(device_id=DEVICE_ID, role="node", protocol_version="1.0",
                    approved_at=datetime.now(UTC))
    db.add(device)
    db.flush()
    credential = DeviceCredential(device_id=device.id, credential_id="cred_" + "b" * 32,
                                  secret_hash=credential_secret_hash(SECRET))
    db.add_all([credential, DevicePlatformState(device_id=device.id)])
    db.commit()
    return device, credential


def provider_report(revision=0, *, version="1", capabilities=(CAPABILITY,), explicit=False):
    model = CapabilityProviderReportV2 if explicit else CapabilityProviderReportV1
    return model(schema_version=2 if explicit else 1, device_id=DEVICE_ID,
                 provider_type="native", provider_id=PROVIDER, provider_version=version,
                 expected_revision=revision,
                 capabilities=[{"capability_id": value} for value in capabilities])


def runtime_report(revision=0, *, version="1", extra=()):
    return DeviceRuntimeFeaturesReportV1(
        device_id=DEVICE_ID, runtime_name="reference", runtime_version=version,
        expected_revision=revision, features=sorted(MANDATORY_NODE_FEATURES | set(extra)),
        command_types=("capability.invoke",),
    )


def authority(db, device):
    return read_device_control(db, device.id), read_authority_guard(db)


def snapshot(db):
    return {
        name: db.execute(select(Base.metadata.tables[name]).order_by(
            *Base.metadata.tables[name].primary_key.columns
        )).fetchall()
        for name in (
            "core_authority_guard", "devices", "device_platform_states",
            "device_credentials", "device_capability_providers", "device_runtime_features",
            "device_capability_states", "device_states", "device_commands",
            "audit_logs", "device_events",
        )
    }


def configure(db, device, revision, ids):
    return configure_provider(db, device, "native", PROVIDER,
                              CapabilityConfigurationV1(expected_revision=revision, capability_ids=ids),
                              actor_user_id=1)


def enable(db, device, revision, enabled):
    return set_provider_enabled(db, device, "native", PROVIDER, expected_revision=revision,
                                enabled=enabled, actor_user_id=1)


def write(db, device, operation):
    if operation == "provider":
        return replace_provider(db, device, provider_report(1, version="2", explicit=True))
    if operation == "configuration":
        return configure(db, device, 1, (CAPABILITY,))
    if operation == "enabled":
        return enable(db, device, 1, False)
    return replace_runtime_features(db, device, runtime_report())


def test_provider_aba_withdrawal_and_retry_preserve_other_device_evidence(db, node):
    device, _ = node
    now = datetime.now(UTC)
    db.add_all([
        DeviceState(device_id=device.id, desired_revision=7, desired_state={"keep": True}),
        DeviceCommand(device_id=device.id, command_id="cmd_uncertain", command_type="capability.invoke",
                      payload={}, idempotency_key="once", status="unknown", delivery_attempts=1,
                      expires_at=now + timedelta(minutes=1), result={"execution_state": "unknown"}),
    ])
    db.commit()
    evidence = snapshot(db)
    controls = [authority(db, device)]
    for revision, version, caps in ((0, "1", (CAPABILITY,)), (1, "2", (CAPABILITY,)),
                                    (2, "1", (CAPABILITY,)), (3, "1", ()), (4, "1", (CAPABILITY,))):
        row = replace_provider(db, device, provider_report(revision, version=version, capabilities=caps))
        assert row.revision == revision + 1
        controls.append(authority(db, device))
    before = snapshot(db)
    replace_provider(db, device, provider_report(4))  # lost acknowledgement
    replace_provider(db, device, provider_report(5))  # unchanged current revision
    with pytest.raises(CapabilityRegistryError, match="revision"):
        replace_provider(db, device, provider_report(0, version="2"))
    assert snapshot(db) == before
    assert len({control.generation for control, _ in controls}) == 6
    assert [guard.revision for _, guard in controls] == list(range(1, 7))
    assert db.get(DevicePlatformState, device.id).revision == 0
    assert before["device_states"] == evidence["device_states"]
    assert before["device_commands"] == evidence["device_commands"]


def test_core_selection_and_enabled_aba_are_fenced_and_not_overwritten_by_reports(db, node):
    device, _ = node
    controls = [authority(db, device)]
    row = replace_provider(db, device, provider_report(explicit=True))
    assert row.configured_capability_ids == [] and registered_capabilities(db, device) == []
    controls.append(authority(db, device))
    for revision, ids in ((1, (CAPABILITY,)), (2, ()), (3, (CAPABILITY,))):
        configure(db, device, revision, ids)
        controls.append(authority(db, device))
    enable(db, device, 4, False)
    controls.append(authority(db, device))
    row = replace_provider(db, device, provider_report(5, version="2", explicit=True))
    controls.append(authority(db, device))
    assert row.enabled is False and row.configured_capability_ids == [CAPABILITY]
    assert registered_capabilities(db, device) == []
    enable(db, device, 6, True)
    controls.append(authority(db, device))
    before = snapshot(db)
    configure(db, device, 7, (CAPABILITY,))
    enable(db, device, 7, True)
    with pytest.raises(CapabilityRegistryError, match="current provider offers"):
        configure(db, device, 7, ("foreign.offer",))
    assert snapshot(db) == before
    assert len({control.generation for control, _ in controls}) == 8
    assert [guard.revision for _, guard in controls] == list(range(1, 9))
    assert registered_capabilities(db, device)[0]["capability_id"] == CAPABILITY


def test_runtime_aba_and_feature_withdrawal_change_control_not_lifecycle_or_capabilities(db, node):
    device, _ = node
    controls = [authority(db, device)]
    for revision, version, extra in ((0, "1", ()), (1, "2", ()), (2, "1", ()),
                                     (3, "1", ("reference.optional",)), (4, "1", ())):
        result = replace_runtime_features(db, device, runtime_report(revision, version=version, extra=extra))
        assert result.revision == revision + 1
        controls.append(authority(db, device))
    before = snapshot(db)
    replace_runtime_features(db, device, runtime_report(4))
    replace_runtime_features(db, device, runtime_report(5))
    with pytest.raises(ValueError, match="revision"):
        replace_runtime_features(db, device, runtime_report(0, version="2"))
    assert snapshot(db) == before
    assert len({control.generation for control, _ in controls}) == 6
    assert [guard.revision for _, guard in controls] == list(range(1, 7))
    assert db.get(DevicePlatformState, device.id).revision == 0
    assert registered_capabilities(db, device) == []


@pytest.mark.parametrize("operation", WRITERS)
def test_audit_failure_rolls_back_all_resource_state_and_authority(db, node, operation):
    device, _ = node
    replace_provider(db, device, provider_report(explicit=True))
    db.add(DeviceCapabilityState(device_id=device.id, capability_id=CAPABILITY,
                                observed_at=datetime.now(UTC), values={"old": True}))
    db.commit()
    before = snapshot(db)
    table = "device_events" if operation in {"provider", "runtime"} else "audit_logs"

    def fail_audit(_conn, _cursor, sql, _params, _context, _many):
        if sql.startswith("INSERT INTO " + table):
            raise RuntimeError("audit unavailable")

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="audit unavailable"):
            write(db, device, operation)
    finally:
        event.remove(engine, "before_cursor_execute", fail_audit)
    assert snapshot(db) == before


@pytest.mark.parametrize("operation", WRITERS)
@pytest.mark.parametrize("missing", ["guard", "device_control"])
def test_missing_metadata_fails_closed_without_lazy_repair(db, node, operation, missing):
    device, _ = node
    replace_provider(db, device, provider_report(explicit=True))
    db.delete(db.get(CoreAuthorityGuard, 1) if missing == "guard"
              else db.get(DevicePlatformState, device.id))
    db.commit()
    before = snapshot(db)
    with pytest.raises(AuthorityMetadataError):
        write(db, device, operation)
    assert snapshot(db) == before


@pytest.mark.parametrize("operation", WRITERS)
def test_writers_reject_pending_work_explicit_transactions_and_savepoints(db, node, operation):
    device, _ = node
    replace_provider(db, device, provider_report(explicit=True))
    device.display_name = "pending caller work"
    with pytest.raises(AuthorityMetadataError):
        write(db, device, operation)
    assert device in db.dirty and device.display_name == "pending caller work"
    db.rollback()
    with db.begin():
        with pytest.raises(AuthorityMetadataError):
            write(db, device, operation)
        assert db.in_transaction()
        with db.begin_nested():
            with pytest.raises(AuthorityMetadataError):
                write(db, device, operation)
            assert db.in_nested_transaction()


@pytest.mark.parametrize("operation", ["provider", "features"])
def test_http_rechecks_exact_authenticated_key_after_revocation_with_another_active_key(db, node, monkeypatch, operation):
    device, credential = node
    device_pk, credential_pk = device.id, credential.id
    credential_id = credential.credential_id
    db.add(DeviceCredential(device_id=device_pk, credential_id="cred_" + "c" * 32,
                            secret_hash=credential_secret_hash("another secret")))
    db.commit()
    before_authority = authority(db, device)
    app = FastAPI()
    app.include_router(provider_router)
    app.include_router(runtime_router)
    app.dependency_overrides[get_db] = lambda: db
    original = getattr(DeviceOperations, operation)

    def revoke_after_auth(operations, report):
        assert operations.credential_id == credential_id
        # A separate connection commits a revocation after request authentication.
        operations.db.rollback()
        with Session(db.get_bind()) as other:
            other.get(DeviceCredential, credential_pk).revoked_at = datetime.now(UTC)
            other.commit()
        return original(operations, report)

    monkeypatch.setattr(DeviceOperations, operation, revoke_after_auth)
    if operation == "provider":
        path = f"/api/v1/devices/{DEVICE_ID}/capability-providers/native/{PROVIDER}"
        report, method = provider_report(), "put"
    else:
        path = f"/api/v1/devices/{DEVICE_ID}/runtime-features"
        report, method = runtime_report(), "put"
    with TestClient(app) as client:
        response = getattr(client, method)(path, json=report.model_dump(mode="json"),
                                           headers={"Authorization": f"Device {credential_id}:{SECRET}"})
    assert response.status_code == 401, response.text
    assert authority(db, device) == before_authority
    assert not db.scalars(select(DeviceCapabilityProvider)).all()


@pytest.mark.parametrize("operation", ["provider", "features"])
def test_device_adapter_cannot_omit_authenticated_credential(db, node, operation):
    device, credential = node
    authenticate_device(db, credential.credential_id, SECRET)
    before = snapshot(db)
    report = provider_report() if operation == "provider" else runtime_report()
    with pytest.raises(DeviceProtocolError) as error:
        getattr(DeviceOperations(db, device), operation)(report)
    assert error.value.kind == "unauthorized"
    assert snapshot(db) == before


def test_health_reports_do_not_advance_authority_or_register_unselected_offers(db, node):
    device, _ = node
    row = replace_provider(db, device, provider_report(explicit=True))
    control = authority(db, device)
    report = CapabilityAvailabilityReportV1(
        device_id=DEVICE_ID, provider_type="native", provider_id=PROVIDER, provider_version="1",
        declaration_digest=declaration_digest("native", PROVIDER, "1", row.capabilities),
        observed_at=datetime.now(UTC), capabilities=[{"capability_id": CAPABILITY, "healthy": True}],
    )
    first = report_availability(db, device, report)
    expires = first.expires_at
    db.commit()
    second = report_availability(db, device, report)
    db.commit()
    assert second.expires_at.replace(tzinfo=UTC) == expires.replace(tzinfo=UTC)
    assert authority(db, device) == control
    assert registered_capabilities(db, device) == []


def test_real_connections_serialize_report_against_stale_administrator_control(db, node):
    device, _ = node
    replace_provider(db, device, provider_report(explicit=True))
    _, initial_guard = authority(db, device)
    db.rollback()
    engine = db.get_bind()
    held, attempted, release, done = (threading.Event() for _ in range(4))
    results, writes = [], []

    def capture(_conn, _cursor, sql, _params, _context, _many):
        name = threading.current_thread().name
        if name not in {"provider-report", "provider-control"}:
            return
        if sql.startswith(("UPDATE", "INSERT", "DELETE")):
            writes.append((name, sql))
        if name == "provider-control" and sql.startswith("UPDATE core_authority_guard"):
            attempted.set()
        if name == "provider-report" and sql.startswith("INSERT INTO device_events"):
            held.set()
            if not release.wait(3):
                raise RuntimeError("test synchronization timed out")

    def run(operation):
        try:
            with Session(engine) as writer:
                current = writer.scalar(select(Device).where(Device.device_id == DEVICE_ID))
                if operation == "report":
                    replace_provider(writer, current, provider_report(1, version="2", explicit=True))
                else:
                    enable(writer, current, 1, False)
            results.append(operation)
        except CapabilityRegistryError:
            results.append("stale")
        except BaseException as error:
            results.append(error)
        finally:
            if operation == "control":
                done.set()

    first = threading.Thread(target=run, args=("report",), name="provider-report")
    second = threading.Thread(target=run, args=("control",), name="provider-control")
    event.listen(engine, "before_cursor_execute", capture)
    try:
        first.start()
        assert held.wait(3)
        second.start()
        assert attempted.wait(3)
        assert not done.wait(0.05)
        release.set()
        first.join(4)
        second.join(4)
    finally:
        release.set()
        for thread in (first, second):
            if thread.ident is not None:
                thread.join(4)
        event.remove(engine, "before_cursor_execute", capture)
    assert not first.is_alive() and not second.is_alive()
    assert sorted(results) == ["report", "stale"]
    assert read_authority_guard(db).revision == initial_guard.revision + 1
    row = db.scalar(select(DeviceCapabilityProvider))
    assert row.enabled is True and row.revision == 2 and row.provider_version == "2"
    for name in ("provider-report", "provider-control"):
        assert next(sql for owner, sql in writes if owner == name).startswith("UPDATE core_authority_guard")
