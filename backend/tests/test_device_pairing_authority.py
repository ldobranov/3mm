"""M20 pairing/credential authority: atomic audit, recovery and actual races."""

from datetime import UTC, datetime, timedelta
import json
import threading

import backend.database  # noqa: F401 - complete model metadata
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from backend.db.authority import CoreAuthorityGuard
from backend.db.audit_log import AuditLog
from backend.db.base import Base
from backend.db.device import (
    Device, DeviceCredential, DevicePlatformState, DevicePairingRequest,
    DeviceState, DeviceCapabilityProvider, DeviceCommand, DeviceEvent,
)
from backend.db.user import User
from backend.services.authority_metadata import AuthorityMetadataError, read_device_control
from backend.services.device_pairing import (
    PairingCompletionError, DeviceCredentialRevocationError,
    approve_pairing_request, claim_pairing_code, complete_pairing_request,
    issue_pairing_code, issue_replacement_device_credential,
    revoke_device_credential, recover_device_credential,
)
from backend.services.node_enrollment import enroll_node
from three_mm_protocol.fleet_pairing import NodeEnrollmentRequest


DEVICE_ID = "dev_" + "a" * 32


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'pairing.db').as_posix()}",
                           connect_args={"timeout": 3})

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            CoreAuthorityGuard(singleton_id=1),
            User(id=1, username="owner", email="owner@example.test",
                 hashed_password="unused", role="admin"),
        ])
        session.commit()
        yield session
    engine.dispose()


def pending(db, device_id=DEVICE_ID):
    issued = issue_pairing_code(db, created_by_user_id=1)
    claim_pairing_code(db, code=issued.code, requested_device_id=device_id,
                      public_key="test-only-public-key", requested_metadata={
                          "display_name": "Neutral node", "role": "node", "protocol_version": "1.0",
                      })
    return issued


def paired(db):
    issued = pending(db)
    approve_pairing_request(db, request_id=issued.request_id, approved_by_user_id=1)
    credential = complete_pairing_request(db, code=issued.code, requested_device_id=DEVICE_ID)
    return issued, credential


def identity(db):
    device_id = db.scalar(select(Device.id).where(Device.device_id == DEVICE_ID))
    return read_device_control(db, device_id), db.get(CoreAuthorityGuard, 1).revision


def snapshot(db):
    return {
        name: db.execute(select(Base.metadata.tables[name]).order_by(
            *Base.metadata.tables[name].primary_key.columns
        )).fetchall()
        for name in (
            "core_authority_guard", "devices", "device_platform_states",
            "device_pairing_requests", "device_credentials", "audit_logs", "device_events",
        )
    }


def test_pair_and_completion_have_distinct_control_generations_and_atomic_audit(db):
    issued = pending(db)
    assert db.get(CoreAuthorityGuard, 1).revision == 1
    approve_pairing_request(db, request_id=issued.request_id, approved_by_user_id=1)
    approved, revision = identity(db)
    assert revision == 2
    assert db.get(DevicePlatformState, approved.device_db_id).revision == 0
    credential = complete_pairing_request(db, code=issued.code, requested_device_id=DEVICE_ID)
    completed, revision = identity(db)
    assert completed.generation != approved.generation and revision == 3
    assert completed.device_id == approved.device_id
    assert db.get(DevicePlatformState, approved.device_db_id).revision == 0
    assert [row.action for row in db.scalars(select(AuditLog).order_by(AuditLog.id))] == [
        "DEVICE_PAIRING_APPROVED", "DEVICE_CREDENTIAL_ISSUED",
    ]
    evidence = json.dumps([row.changes for row in db.scalars(select(AuditLog))])
    evidence += json.dumps([row.payload for row in db.scalars(select(DeviceEvent))])
    assert credential.secret not in evidence
    assert issued.code not in evidence
    before = snapshot(db)
    with pytest.raises(PairingCompletionError):
        complete_pairing_request(db, code=issued.code, requested_device_id=DEVICE_ID)
    assert snapshot(db) == before


def test_replacement_and_revocation_do_not_reuse_authority_or_erase_history(db):
    _, old = paired(db)
    control, _ = identity(db)
    now = datetime.now(UTC)
    db.add_all([
        DeviceState(device_id=control.device_db_id, desired_revision=9, desired_state={"keep": True}),
        DeviceCapabilityProvider(device_id=control.device_db_id, provider_type="native",
                                 provider_id="example", provider_version="1", revision=4,
                                 capabilities=[{"capability_id": "example.control"}], reported_at=now),
        DeviceCommand(device_id=control.device_db_id, command_id="cmd_uncertain", command_type="capability.invoke",
                      payload={}, idempotency_key="once", status="unknown", delivery_attempts=1,
                      expires_at=now + timedelta(minutes=1), result={"execution_state": "unknown"}),
    ])
    db.commit()
    tables = (DeviceState.__table__, DeviceCapabilityProvider.__table__, DeviceCommand.__table__)
    history = [db.execute(select(table)).fetchall() for table in tables]
    generations = [identity(db)[0].generation]
    new = issue_replacement_device_credential(db, device_id=DEVICE_ID, actor_id=1)
    generations.append(identity(db)[0].generation)
    # Preserve the existing replacement API: it does not revoke every other key.
    assert db.scalar(select(DeviceCredential).where(DeviceCredential.credential_id == old.credential_id)).revoked_at is None
    revoke_device_credential(db, device_id=DEVICE_ID, credential_id=new.credential_id, actor_id=1)
    generations.append(identity(db)[0].generation)
    before = snapshot(db)
    with pytest.raises(DeviceCredentialRevocationError):
        revoke_device_credential(db, device_id=DEVICE_ID, credential_id=new.credential_id, actor_id=1)
    assert snapshot(db) == before
    issue_replacement_device_credential(db, device_id=DEVICE_ID, actor_id=1)
    generations.append(identity(db)[0].generation)
    assert len(set(generations)) == 4
    assert [db.execute(select(table)).fetchall() for table in tables] == history
    assert db.get(DevicePlatformState, control.device_db_id).revision == 0


@pytest.mark.parametrize("operation", ["approve", "complete", "replace", "revoke", "recover"])
def test_audit_failure_rolls_back_resource_generation_and_pairing_reservation(db, operation):
    issued = pending(db)
    if operation != "approve":
        approve_pairing_request(db, request_id=issued.request_id, approved_by_user_id=1)
    credential = None
    if operation not in {"approve", "complete"}:
        credential = complete_pairing_request(db, code=issued.code, requested_device_id=DEVICE_ID)
    before = snapshot(db)
    engine = db.get_bind()

    def fail_audit(_conn, _cursor, sql, _params, _context, _many):
        if sql.startswith("INSERT INTO audit_logs"):
            raise RuntimeError("audit unavailable")

    event.listen(engine, "before_cursor_execute", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="audit unavailable"):
            if operation == "approve":
                approve_pairing_request(db, request_id=issued.request_id, approved_by_user_id=1)
            elif operation == "complete":
                complete_pairing_request(db, code=issued.code, requested_device_id=DEVICE_ID)
            elif operation == "replace":
                issue_replacement_device_credential(db, device_id=DEVICE_ID, actor_id=1)
            elif operation == "revoke":
                revoke_device_credential(db, device_id=DEVICE_ID, credential_id=credential.credential_id, actor_id=1)
            else:
                recover_device_credential(db, device_id=DEVICE_ID, actor_id=1)
    finally:
        event.remove(engine, "before_cursor_execute", fail_audit)
    assert snapshot(db) == before


def test_missing_guard_never_initializes_or_changes_pairing(db):
    issued = pending(db)
    db.delete(db.get(CoreAuthorityGuard, 1))
    db.commit()
    before = snapshot(db)
    with pytest.raises(AuthorityMetadataError):
        approve_pairing_request(db, request_id=issued.request_id, approved_by_user_id=1)
    assert snapshot(db) == before


def test_missing_device_metadata_never_silently_repairs_existing_authority(db):
    issued, credential = paired(db)
    control, _ = identity(db)
    db.delete(db.get(DevicePlatformState, control.device_db_id))
    db.commit()
    before = snapshot(db)
    with pytest.raises(AuthorityMetadataError):
        revoke_device_credential(db, device_id=DEVICE_ID, credential_id=credential.credential_id, actor_id=1)
    with pytest.raises(DeviceCredentialRevocationError):
        issue_replacement_device_credential(db, device_id=DEVICE_ID, actor_id=1)
    assert snapshot(db) == before


def test_foreign_credential_cannot_be_revoked_under_another_device(db):
    _, credential = paired(db)
    before = snapshot(db)
    with pytest.raises(DeviceCredentialRevocationError):
        revoke_device_credential(db, device_id="dev_" + "f" * 32,
                                 credential_id=credential.credential_id, actor_id=1)
    assert snapshot(db) == before


def test_pending_caller_work_and_explicit_transactions_are_not_discarded(db):
    paired(db)
    device = db.scalar(select(Device))
    device.display_name = "unsaved caller change"
    with pytest.raises(AuthorityMetadataError):
        issue_replacement_device_credential(db, device_id=DEVICE_ID)
    assert device in db.dirty and device.display_name == "unsaved caller change"
    db.rollback()
    with db.begin():
        with pytest.raises(AuthorityMetadataError):
            issue_replacement_device_credential(db, device_id=DEVICE_ID)
        assert db.in_transaction()


def test_trusted_recovery_requires_existing_active_or_explicitly_prepared_authority(db):
    _, old = paired(db)
    control, _ = identity(db)
    platform = db.get(DevicePlatformState, control.device_db_id)
    device = db.get(Device, control.device_db_id)
    device.revoked_at = datetime.now(UTC)
    platform.authority_status, platform.lifecycle, platform.reason = "released", "unowned", "authority.released"
    db.commit()
    before = snapshot(db)
    with pytest.raises(DeviceCredentialRevocationError):
        recover_device_credential(db, device_id=DEVICE_ID, actor_id=1)
    assert snapshot(db) == before
    platform.lifecycle, platform.reason = "enrollment_pending", "authority.enrollment_authorized"
    db.commit()
    recovered = recover_device_credential(db, device_id=DEVICE_ID, actor_id=1)
    assert recovered.credential_id != old.credential_id
    assert identity(db)[0].generation != control.generation
    db.refresh(platform)
    db.refresh(device)
    assert (platform.authority_status, platform.lifecycle, platform.revision) == ("bound", "active", 1)
    assert device.revoked_at is None
    assert db.scalar(select(DeviceCredential).where(DeviceCredential.credential_id == old.credential_id)).revoked_at is not None


def test_same_id_node_reenrollment_advances_existing_control_generation(db):
    paired(db)
    control, _ = identity(db)
    platform = db.get(DevicePlatformState, control.device_db_id)
    platform.authority_status, platform.lifecycle, platform.reason = "released", "enrollment_pending", "authority.enrollment_authorized"
    db.get(Device, control.device_db_id).revoked_at = datetime.now(UTC)
    for credential in db.scalars(select(DeviceCredential)):
        credential.revoked_at = datetime.now(UTC)
    db.commit()
    enroll_node(db, NodeEnrollmentRequest(
        device_id=DEVICE_ID, display_name="Same identity", request_token="b" * 64,
        credential_id="cred_" + "c" * 32, credential_secret_hash="d" * 64,
    ))
    request_id = db.scalar(select(DevicePairingRequest.id).where(DevicePairingRequest.created_by_user_id.is_(None)))
    device = approve_pairing_request(db, request_id=request_id, approved_by_user_id=1)
    assert device.id == control.device_db_id and device.device_id == control.device_id
    assert identity(db)[0].generation != control.generation
    assert db.query(Device).count() == 1 and db.query(DeviceCredential).count() == 2


def test_real_connections_serialize_duplicate_completion_before_any_resource_write(db):
    issued = pending(db)
    approve_pairing_request(db, request_id=issued.request_id, approved_by_user_id=1)
    _, revision = identity(db)
    db.rollback()
    engine = db.get_bind()
    held, attempted, release, done = (threading.Event() for _ in range(4))
    results, writes = [], []

    def capture(_conn, _cursor, sql, _params, _context, _many):
        name = threading.current_thread().name
        if name not in {"first-completion", "second-completion"}:
            return
        if sql.startswith(("UPDATE", "INSERT", "DELETE")):
            writes.append((name, sql))
        if name == "second-completion" and sql.startswith("UPDATE core_authority_guard"):
            attempted.set()
        if name == "first-completion" and sql.startswith("INSERT INTO audit_logs"):
            held.set()
            if not release.wait(3):
                raise RuntimeError("test synchronization timed out")

    def complete():
        try:
            with Session(engine) as writer:
                results.append(complete_pairing_request(writer, code=issued.code, requested_device_id=DEVICE_ID))
        except PairingCompletionError:
            results.append("not_ready")
        except BaseException as exc:
            results.append(exc)
        finally:
            if threading.current_thread().name == "second-completion":
                done.set()

    first = threading.Thread(target=complete, name="first-completion")
    second = threading.Thread(target=complete, name="second-completion")
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
    assert results.count("not_ready") == 1
    assert sum(hasattr(result, "credential_id") for result in results) == 1
    assert db.query(DeviceCredential).count() == 1
    assert identity(db)[1] == revision + 1
    for name in ("first-completion", "second-completion"):
        assert next(sql for owner, sql in writes if owner == name).startswith("UPDATE core_authority_guard")


def test_local_bootstrap_saves_credentials_after_committed_audit_and_guard(db, tmp_path, monkeypatch):
    from agent.core_client import DeviceCredentialStore
    from backend.tests.test_local_agent_pairing import _provision
    from deployment.local_agent_pairing import ensure_automatic_local_agent_pairing

    data, provisioning = tmp_path / "agent", tmp_path / "provisioning"
    _provision(provisioning)
    original_save = DeviceCredentialStore.save
    observed = []

    def save(store, credential):
        assert not db.in_transaction()
        with Session(db.get_bind()) as observer:
            stored = observer.scalar(select(DeviceCredential).where(
                DeviceCredential.credential_id == credential.credential_id,
            ))
            assert stored is not None
            assert observer.scalar(select(AuditLog).where(
                AuditLog.action.in_(("DEVICE_CREDENTIAL_ISSUED", "DEVICE_CREDENTIAL_REPLACED")),
            )) is not None
            observed.append(observer.get(CoreAuthorityGuard, 1).revision)
        original_save(store, credential)

    monkeypatch.setattr(DeviceCredentialStore, "save", save)

    def bootstrap():
        return ensure_automatic_local_agent_pairing(
            db, agent_data_dir=data, provisioning_data_dir=provisioning,
        )

    assert bootstrap().status == "paired"
    assert bootstrap().status == "already_paired"
    before = db.get(CoreAuthorityGuard, 1).revision
    (data / "core-credential.json").unlink()
    assert bootstrap().status == "repaired"
    assert observed == [3, before + 1]
    assert db.query(Device).count() == 1
    assert db.query(DeviceCredential).filter(DeviceCredential.revoked_at.is_(None)).count() == 1
