"""M20 lifecycle writers: guard-first mutation, revocation and preserved evidence."""

from datetime import UTC, datetime, timedelta
import threading

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from backend.db.authority import CoreAuthorityGuard
from backend.db.base import Base
from backend.db.device import (
    Device, DeviceCommand, DeviceCredential, DeviceEvent, DevicePairingRequest,
    DevicePlatformState, DeviceState,
)
from backend.services.authority_metadata import AuthorityMetadataError, read_device_control
from backend.services import device_platform
from backend.services.device_pairing import (
    issue_replacement_device_credential, revoke_device_credential,
)
from backend.services.device_protocol import authenticate_device
from backend.services.installation_identity import installation_identity
from backend.tests.test_device_pairing_authority import db, paired, DEVICE_ID  # noqa: F401
from backend.tests.test_device_platform import core, paired as http_paired  # noqa: F401
from three_mm_protocol.device_platform import LifecycleReportV1
from three_mm_protocol.transport import DeviceProtocolError


@pytest.fixture
def node(db, monkeypatch):
    monkeypatch.setenv("AI_SETTINGS_MASTER_KEY", Fernet.generate_key().decode())
    installation_identity(db)
    _, credential = paired(db)
    device = db.scalar(select(Device).where(Device.device_id == DEVICE_ID))
    return device, credential


def authority(db, device):
    return read_device_control(db, device.id), db.get(CoreAuthorityGuard, 1, populate_existing=True).revision


def snapshot(db):
    return {
        name: db.execute(select(Base.metadata.tables[name]).order_by(
            *Base.metadata.tables[name].primary_key.columns,
        )).fetchall()
        for name in (
            "core_authority_guard", "core_installation_identity", "devices",
            "device_platform_states", "device_credentials", "device_commands",
            "device_pairing_requests", "device_events", "device_states",
        )
    }


def report(db, node, lifecycle="recovery", revision=0, reason="runtime.unavailable"):
    device, credential = node
    return device_platform.report_lifecycle(db, device, LifecycleReportV1(
        device_id=DEVICE_ID, lifecycle=lifecycle, expected_revision=revision, reason=reason,
    ), credential_id=credential.credential_id)


def release(db, device, revision=0):
    return device_platform.release_authority(db, device, expected_revision=revision,
        confirmed_device_id=DEVICE_ID, actor_id=1)


def prepare(db, device, revision=1):
    return device_platform.prepare_reenrollment(db, device, expected_revision=revision,
        confirmed_device_id=DEVICE_ID, actor_id=1)


def seed_evidence(db, device):
    now = datetime.now(UTC)
    db.add(DeviceState(device_id=device.id, desired_revision=9, desired_state={"keep": True}))
    for index, (status, attempts, dispatched) in enumerate((
        ("queued", 0, False), ("delivered", 1, True), ("unknown", 1, True),
        ("queued", 1, False),
    )):
        db.add(DeviceCommand(device_id=device.id, command_id=f"cmd_evidence_{index}",
            command_type="agent.ping", payload={}, idempotency_key=f"once_{index}",
            status=status, delivery_attempts=attempts, delivered_at=now if dispatched else None,
            expires_at=now + timedelta(minutes=5),
            result={"execution_state": "unknown"} if status == "unknown" else None))
    db.commit()


def test_lifecycle_aba_changes_control_but_reason_and_exact_retry_do_not(db, node):
    device, _ = node
    initial, revision = authority(db, device)
    assert report(db, node).revision == 1
    recovery, next_revision = authority(db, device)
    assert recovery.generation != initial.generation and next_revision == revision + 1
    before = snapshot(db)
    assert report(db, node).revision == 1  # Lost-response retry using revision 0.
    assert snapshot(db) == before
    assert report(db, node, revision=1, reason="runtime.still_unavailable").revision == 2
    assert authority(db, device) == (recovery, next_revision)
    assert report(db, node, lifecycle="active", revision=2, reason=None).revision == 3
    active, final_revision = authority(db, device)
    assert len({initial.generation, recovery.generation, active.generation}) == 3
    assert final_revision == next_revision + 1
    assert not db.new and not db.dirty


def test_release_and_prepare_preserve_identity_uncertain_commands_and_history(db, node):
    device, credential = node
    seed_evidence(db, device)
    now = datetime.now(UTC)
    pending = DevicePairingRequest(code_hash="historical-enrollment", requested_device_id=DEVICE_ID,
        created_by_user_id=None, device_id=device.id, requested_metadata={"keep": "evidence"},
        expires_at=now + timedelta(minutes=5), claimed_at=now, approved_at=now, completed_at=now)
    db.add(pending)
    db.commit()
    old_control, revision = authority(db, device)
    old_id = device.id
    assert release(db, device).revision == 1
    released, release_revision = authority(db, device)
    assert released.generation != old_control.generation and release_revision == revision + 1
    before = snapshot(db)
    assert release(db, device).revision == 1
    assert snapshot(db) == before
    commands = list(db.scalars(select(DeviceCommand).order_by(DeviceCommand.id)))
    assert commands[0].status == "failed" and commands[0].result == {"execution_state": "not_dispatched"}
    assert [row.status for row in commands[1:]] == ["delivered", "unknown", "queued"]
    assert commands[2].result == {"execution_state": "unknown"}
    assert prepare(db, device).revision == 2
    prepared, prepare_revision = authority(db, device)
    assert prepared.generation not in {old_control.generation, released.generation}
    assert prepare_revision == release_revision + 1
    assert device.id == old_id and device.device_id == DEVICE_ID
    db.refresh(pending)
    assert pending.requested_device_id is None and pending.device_id == old_id
    assert pending.approved_at is not None and pending.completed_at is not None
    assert pending.requested_metadata == {"keep": "evidence", "archived_device_id": DEVICE_ID}
    assert db.scalar(select(DeviceState)).desired_state == {"keep": True}
    assert db.scalar(select(DeviceCredential).where(
        DeviceCredential.credential_id == credential.credential_id)).revoked_at is not None
    assert [row.event_type for row in db.scalars(select(DeviceEvent).where(
        DeviceEvent.event_type.in_(("device.authority.released", "device.authority.enrollment_prepared")),
    ).order_by(DeviceEvent.id))] == ["device.authority.released", "device.authority.enrollment_prepared"]


@pytest.mark.parametrize("operation", ["report", "release", "prepare"])
def test_audit_failure_rolls_back_generation_resource_and_evidence(db, node, operation):
    device, _ = node
    seed_evidence(db, device)
    if operation == "prepare":
        release(db, device)
        db.add(DevicePairingRequest(code_hash="pending", requested_device_id=DEVICE_ID,
            requested_metadata={"keep": True}, expires_at=datetime.now(UTC) + timedelta(minutes=1)))
        db.commit()
    before = snapshot(db)

    def fail(_conn, _cursor, sql, _params, _context, _many):
        if sql.startswith("INSERT INTO device_events"):
            raise RuntimeError("audit unavailable")

    event.listen(db.get_bind(), "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="audit unavailable"):
            {"report": lambda: report(db, node), "release": lambda: release(db, device),
             "prepare": lambda: prepare(db, device)}[operation]()
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", fail)
    assert snapshot(db) == before


@pytest.mark.parametrize("operation", ["report", "release", "prepare"])
@pytest.mark.parametrize("missing", ["guard", "platform"])
def test_missing_authority_fails_closed_without_repair(db, node, operation, missing):
    device, _ = node
    if operation == "prepare":
        release(db, device)
    db.delete(db.get(CoreAuthorityGuard, 1) if missing == "guard" else db.get(DevicePlatformState, device.id))
    db.commit()
    before = snapshot(db)
    with pytest.raises(AuthorityMetadataError):
        {"report": lambda: report(db, node), "release": lambda: release(db, device),
         "prepare": lambda: prepare(db, device)}[operation]()
    assert snapshot(db) == before


def test_authenticated_principal_cannot_report_after_its_key_is_revoked(db, node):
    device, credential = node
    other = issue_replacement_device_credential(db, device_id=DEVICE_ID, actor_id=1)
    authenticate_device(db, credential.credential_id, credential.secret)
    revoke_device_credential(db, device_id=DEVICE_ID, credential_id=credential.credential_id, actor_id=1)
    before = snapshot(db)
    with pytest.raises(DeviceProtocolError) as error:
        report(db, node)
    assert error.value.kind == "unauthorized" and snapshot(db) == before
    assert report(db, (device, other)).revision == 1


def test_http_lifecycle_rechecks_presented_key_after_authentication(core, monkeypatch):
    from backend.routes import device_platform as routes

    credential, device, _ = http_paired(core)
    client, db, _, viewer = core
    issue_replacement_device_credential(db, device_id=device.device_id, actor_id=1)
    url = f"/api/v1/devices/{device.device_id}/lifecycle"
    payload = {"device_id": device.device_id, "lifecycle": "recovery", "expected_revision": 0}
    assert client.put(url, json=payload).status_code == 401
    assert client.put(url, headers=viewer, json=payload).status_code == 401
    original = routes.report_lifecycle

    def revoked_between_auth_and_write(session, current, report, **kwargs):
        assert kwargs["credential_id"] == credential.credential_id
        revoke_device_credential(session, device_id=current.device_id,
            credential_id=credential.credential_id, actor_id=1)
        return original(session, current, report, **kwargs)

    monkeypatch.setattr(routes, "report_lifecycle", revoked_between_auth_and_write)
    response = client.put(url, json=payload, headers={
        "Authorization": f"Device {credential.credential_id}:{credential.credential_secret}",
    })
    assert response.status_code == 401
    assert db.get(DevicePlatformState, device.id).revision == 0
    assert db.query(DeviceEvent).filter(DeviceEvent.event_type == "device.lifecycle.updated").count() == 0


def test_http_missing_metadata_blocks_release_without_lazy_repair(core):
    credential, device, _ = http_paired(core)
    client, db, admin, _ = core
    db.delete(db.get(DevicePlatformState, device.id))
    db.commit()
    response = client.post(f"/api/v1/devices/{credential.device_id}/authority/release",
        headers=admin, json={"confirmed_device_id": credential.device_id, "expected_revision": 0})
    assert response.status_code == 503
    assert db.get(DevicePlatformState, device.id) is None
    db.refresh(device)
    assert device.revoked_at is None


def test_stale_revision_foreign_identity_and_pending_work_do_not_mutate(db, node):
    device, _ = node
    before = snapshot(db)
    with pytest.raises(DeviceProtocolError, match="revision changed"):
        report(db, node, revision=5)
    with pytest.raises(DeviceProtocolError, match="confirmation"):
        device_platform.release_authority(db, device, expected_revision=0,
            confirmed_device_id="dev_" + "f" * 32, actor_id=1)
    assert snapshot(db) == before
    device.display_name = "pending caller edit"
    with pytest.raises(AuthorityMetadataError):
        release(db, device)
    assert device in db.dirty and device.display_name == "pending caller edit"
    db.rollback()
    with db.begin():
        with pytest.raises(AuthorityMetadataError):
            release(db, device)
        assert db.in_transaction()


def test_real_connections_serialize_release_before_lifecycle_report(db, node):
    device, credential = node
    old_control, revision = authority(db, device)
    db.rollback()
    engine = db.get_bind()
    held, attempted, resume, done = (threading.Event() for _ in range(4))
    results, writes = [], []

    def capture(_conn, _cursor, sql, _params, _context, _many):
        name = threading.current_thread().name
        if name not in {"release-writer", "report-writer"}:
            return
        if sql.startswith(("UPDATE", "INSERT", "DELETE")):
            writes.append((name, sql))
        if name == "report-writer" and sql.startswith("UPDATE core_authority_guard"):
            attempted.set()
        if name == "release-writer" and sql.startswith("INSERT INTO device_events"):
            held.set()
            if not resume.wait(3):
                raise RuntimeError("test synchronization timed out")

    def write(operation):
        try:
            with Session(engine) as writer:
                current = writer.get(Device, old_control.device_db_id)
                if operation == "release":
                    results.append(release(writer, current))
                else:
                    results.append(report(writer, (current, credential)))
        except BaseException as exc:
            results.append(exc)
        finally:
            if operation == "report":
                done.set()

    first = threading.Thread(target=write, args=("release",), name="release-writer")
    second = threading.Thread(target=write, args=("report",), name="report-writer")
    event.listen(engine, "before_cursor_execute", capture)
    try:
        first.start()
        assert held.wait(3)
        second.start()
        assert attempted.wait(3)
        assert not done.wait(0.05)
        resume.set()
        first.join(4)
        second.join(4)
    finally:
        resume.set()
        for thread in (first, second):
            if thread.ident is not None:
                thread.join(4)
        event.remove(engine, "before_cursor_execute", capture)
    assert not first.is_alive() and not second.is_alive()
    assert sum(getattr(result, "lifecycle", None) == "unowned" for result in results) == 1
    assert sum(isinstance(result, DeviceProtocolError) and result.kind == "unauthorized" for result in results) == 1
    assert authority(db, device)[1] == revision + 1
    assert db.query(DeviceEvent).filter(DeviceEvent.event_type == "device.lifecycle.updated").count() == 0
    for name in ("release-writer", "report-writer"):
        assert next(sql for owner, sql in writes if owner == name).startswith("UPDATE core_authority_guard")
