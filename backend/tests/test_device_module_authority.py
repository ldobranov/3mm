"""M20 Agent-module writers: atomic transitions and unchanged command evidence."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import threading

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from backend.db.authority import CoreAuthorityGuard
from backend.db.base import Base
from backend.db.device import Device, DeviceCommand, DeviceCredential, DeviceEvent, DevicePlatformState
from backend.db.module import ModuleInstallation
from backend.routes.device_commands import router as command_router
from backend.routes import modules
from backend.services.authority_metadata import AuthorityMetadataError, read_authority_guard, read_device_control
from backend.services.device_commands import DeviceCommandError, deliver_next_command, record_command_result
from backend.services.device_command_notifier import device_command_notifier
from backend.services.device_capability_registry import registered_capabilities
from backend.services.device_pairing import credential_secret_hash
from backend.services.device_protocol import DeviceOperations
from backend.services.device_runtime_features import replace_runtime_features
from backend.tests.test_module_lifecycle_idempotency import lifecycle, _request, DEVICE_ID, MODULE_ID  # noqa: F401
from backend.utils.db_utils import get_db
from three_mm_protocol import AgentCommandResult, DeviceEventV1
from three_mm_protocol.node_features import DeviceRuntimeFeaturesReportV1, MANDATORY_NODE_FEATURES
from three_mm_protocol.transport import DeviceProtocolError


def authority(ctx):
    return read_device_control(ctx.db, ctx.device.id), read_authority_guard(ctx.db)


def snapshot(db):
    return {name: db.execute(select(Base.metadata.tables[name]).order_by(
        *Base.metadata.tables[name].primary_key.columns)).fetchall() for name in (
            "core_authority_guard", "device_platform_states", "device_credentials",
            "device_commands", "module_installations", "device_events", "audit_logs",
        )}


def report(command_id, *, status="succeeded"):
    return AgentCommandResult(command_id=command_id, device_id=DEVICE_ID, status=status,
                              completed_at=datetime.now(UTC), output={"private": "do-not-audit"})


def prepare(ctx, operation):
    if operation == "install":
        return None
    command_id = _request(ctx, ctx.install)["command_id"]
    if operation == "disable":
        ctx.complete(command_id)
    elif operation == "result":
        ctx.db.scalar(select(DeviceCommand)).status = "delivered"
        ctx.db.commit()
    elif operation == "withdrawn":
        replace_runtime_features(ctx.db, ctx.device, DeviceRuntimeFeaturesReportV1(
            device_id=DEVICE_ID, runtime_name="reference", runtime_version="1", expected_revision=0,
            features=sorted(MANDATORY_NODE_FEATURES), command_types=("capability.invoke",),
        ))
    elif operation == "invalid":
        ctx.db.scalar(select(DeviceCommand)).idempotency_key = "x" * 129
        ctx.db.commit()
    return command_id


def write(ctx, operation, command_id):
    if operation in {"install", "disable"}:
        return ctx.client.post(getattr(ctx, operation))
    if operation == "result":
        return record_command_result(ctx.db, device=ctx.device, result=report(command_id))
    return deliver_next_command(ctx.db, device=ctx.device)


def test_requests_results_and_retries_advance_only_effective_module_authority(lifecycle):
    ctx = lifecycle
    ctx.package.registrations = [{"kind": "capability", "registration_id": "example.control"}]
    ctx.db.commit()
    generations, revisions = [], []
    for action in ("install", "disable", "install"):
        before, guard = authority(ctx)
        requested = _request(ctx, getattr(ctx, action))
        current, updated = authority(ctx)
        assert current.generation != before.generation and updated.revision == guard.revision + 1
        assert registered_capabilities(ctx.db, ctx.device) == []
        assert _request(ctx, getattr(ctx, action)) == requested
        assert authority(ctx) == (current, updated)
        delivered = deliver_next_command(ctx.db, device=ctx.device)
        assert delivered.command_id == requested["command_id"]
        assert authority(ctx) == (current, updated)  # Delivery evidence is not an authority change.
        completed = record_command_result(ctx.db, device=ctx.device, result=report(delivered.command_id))
        final, final_guard = authority(ctx)
        assert final.generation != current.generation and final_guard.revision == updated.revision + 1
        assert bool(registered_capabilities(ctx.db, ctx.device)) is (action == "install")
        record_command_result(ctx.db, device=ctx.device, result=report(completed.command_id, status="failed"))
        assert authority(ctx) == (final, final_guard)
        assert completed.status == "succeeded" and completed.result == {"private": "do-not-audit"}
        generations.extend([current.generation, final.generation])
        revisions.append(final_guard.revision)
    assert len(set(generations)) == 6 and revisions == [3, 5, 7]
    events = ctx.db.scalars(select(DeviceEvent)).all()
    assert len(events) == 6
    assert "do-not-audit" not in repr([item.payload for item in events])
    assert "package_base64" not in repr([item.payload for item in events])


@pytest.mark.parametrize("operation", ["install", "disable", "result", "withdrawn", "invalid"])
def test_audit_failure_rolls_back_command_installation_generation_and_notification(lifecycle, operation):
    ctx = lifecycle
    command_id = prepare(ctx, operation)
    before, revision = snapshot(ctx.db), device_command_notifier.revision(ctx.device.id)

    def fail_audit(_conn, _cursor, sql, _params, _context, _many):
        if sql.startswith("INSERT INTO device_events"):
            raise RuntimeError("audit unavailable")

    engine = ctx.db.get_bind()
    event.listen(engine, "before_cursor_execute", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="audit unavailable"):
            write(ctx, operation, command_id)
    finally:
        event.remove(engine, "before_cursor_execute", fail_audit)
    assert snapshot(ctx.db) == before
    assert device_command_notifier.revision(ctx.device.id) == revision


@pytest.mark.parametrize("missing", ["guard", "control"])
@pytest.mark.parametrize("operation", ["install", "disable", "result", "withdrawn"])
def test_missing_metadata_is_not_recreated_by_module_writers(lifecycle, missing, operation):
    ctx = lifecycle
    command_id = prepare(ctx, operation)
    ctx.db.delete(ctx.db.get(CoreAuthorityGuard, 1) if missing == "guard"
                  else ctx.db.get(DevicePlatformState, ctx.device.id))
    ctx.db.commit()
    before = snapshot(ctx.db)
    if operation in {"install", "disable"}:
        assert write(ctx, operation, command_id).status_code == 409
    else:
        with pytest.raises(AuthorityMetadataError):
            write(ctx, operation, command_id)
    assert snapshot(ctx.db) == before


def test_late_receipt_cannot_overwrite_a_newer_module_episode(lifecycle):
    ctx = lifecycle
    first = _request(ctx, ctx.install, "first")["command_id"]
    deliver_next_command(ctx.db, device=ctx.device)
    second = _request(ctx, ctx.install, "second")["command_id"]
    before = authority(ctx)
    record_command_result(ctx.db, device=ctx.device, result=report(first))
    assert authority(ctx) == before
    current = ctx.db.scalar(select(ModuleInstallation))
    assert (current.command_id, current.status, current.installed_version) == (second, "queued", None)


def test_legacy_two_commit_gap_reconciles_once_from_the_original_receipt(lifecycle):
    ctx = lifecycle
    command_id = _request(ctx, ctx.install)["command_id"]
    command = ctx.db.scalar(select(DeviceCommand))
    command.status, command.result = "succeeded", {"original": True}
    ctx.db.commit()  # Simulate old Core receipt committed before installation update.
    before, guard = authority(ctx)
    record_command_result(ctx.db, device=ctx.device, result=report(command_id, status="failed"))
    after, advanced = authority(ctx)
    assert after.generation != before.generation and advanced.revision == guard.revision + 1
    assert ctx.db.scalar(select(ModuleInstallation)).status == "succeeded"
    assert command.status == "succeeded" and command.result == {"original": True}
    record_command_result(ctx.db, device=ctx.device, result=report(command_id))
    assert authority(ctx) == (after, advanced)


@pytest.mark.parametrize("operation", ["withdrawn", "invalid"])
def test_proven_pre_dispatch_failure_commits_once_without_a_delivery_attempt(lifecycle, operation):
    ctx = lifecycle
    prepare(ctx, operation)
    _, guard = authority(ctx)
    if operation == "invalid":
        with pytest.raises(DeviceCommandError, match="requires recovery"):
            deliver_next_command(ctx.db, device=ctx.device)
    else:
        assert deliver_next_command(ctx.db, device=ctx.device) is None
    command = ctx.db.scalar(select(DeviceCommand))
    assert command.status == "failed" and command.result["execution_state"] == "not_dispatched"
    assert command.delivery_attempts == 0 and command.delivered_at is None
    assert ctx.db.scalar(select(ModuleInstallation)).status == "failed"
    assert authority(ctx)[1].revision == guard.revision + 1
    final = snapshot(ctx.db)
    assert deliver_next_command(ctx.db, device=ctx.device) is None
    assert snapshot(ctx.db) == final


def test_dispatched_invalid_work_keeps_its_uncertainty(lifecycle):
    ctx = lifecycle
    prepare(ctx, "result")
    command = ctx.db.scalar(select(DeviceCommand))
    command.delivered_at, command.delivery_attempts = datetime.now(UTC) - timedelta(seconds=40), 1
    command.idempotency_key = "x" * 129
    ctx.db.commit()
    before = snapshot(ctx.db)
    with pytest.raises(DeviceCommandError, match="requires recovery"):
        deliver_next_command(ctx.db, device=ctx.device)
    assert snapshot(ctx.db) == before


def test_device_cannot_forge_module_authority_audit(lifecycle):
    ctx = lifecycle
    before = snapshot(ctx.db)
    with pytest.raises(DeviceProtocolError) as error:
        DeviceOperations(ctx.db, ctx.device, credential_id="cred_lifecycle").event(DeviceEventV1(
            device_id=DEVICE_ID, event_id="evt_" + "f" * 32,
            event_type="device.module.lifecycle.updated", occurred_at=datetime.now(UTC), payload={"forged": True},
        ))
    assert error.value.kind == "forbidden" and snapshot(ctx.db) == before


def test_http_result_rechecks_exact_authenticated_key_after_revocation(lifecycle, monkeypatch):
    ctx = lifecycle
    command_id = prepare(ctx, "result")
    ctx.db.add(DeviceCredential(device_id=ctx.device.id, credential_id="cred_other",
                                secret_hash=credential_secret_hash("other")))
    ctx.db.commit()
    app = FastAPI()
    app.include_router(command_router)
    app.dependency_overrides[get_db] = lambda: ctx.db
    original = DeviceOperations.command_result

    def revoke_after_auth(operations, payload):
        assert operations.credential_id == "cred_lifecycle"
        operations.db.rollback()
        with Session(ctx.db.get_bind()) as other:
            other.scalar(select(DeviceCredential).where(DeviceCredential.credential_id == "cred_lifecycle")).revoked_at = datetime.now(UTC)
            other.commit()
        return original(operations, payload)

    monkeypatch.setattr(DeviceOperations, "command_result", revoke_after_auth)
    before = authority(ctx)
    with TestClient(app) as client:
        path = f"/api/v1/devices/{DEVICE_ID}/commands/{command_id}/result"
        response = client.post(path, json=report(command_id).model_dump(mode="json"),
                               headers={"Authorization": "Device cred_lifecycle:test-secret"})
    assert response.status_code == 401, response.text
    assert authority(ctx) == before
    assert ctx.db.scalar(select(DeviceCommand)).status == "delivered"
    monkeypatch.setattr(DeviceOperations, "command_result", original)
    with pytest.raises(DeviceProtocolError) as error:
        DeviceOperations(ctx.db, ctx.device).command_result(report(command_id))
    assert error.value.kind == "unauthorized"


@pytest.mark.parametrize("operation", ["install", "disable"])
def test_admin_audit_is_part_of_the_same_transaction(lifecycle, operation):
    ctx = lifecycle
    prepare(ctx, operation)
    before = snapshot(ctx.db)

    def fail_audit(_conn, _cursor, sql, _params, _context, _many):
        if sql.startswith("INSERT INTO audit_logs"):
            raise RuntimeError("admin audit unavailable")

    engine = ctx.db.get_bind()
    event.listen(engine, "before_cursor_execute", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="admin audit unavailable"):
            ctx.client.post(getattr(ctx, operation))
    finally:
        event.remove(engine, "before_cursor_execute", fail_audit)
    assert snapshot(ctx.db) == before


def test_catalog_digest_must_match_the_validated_bytes_before_queueing(lifecycle):
    ctx = lifecycle
    other = ctx.add_package("2.0.0")
    Path(ctx.package.file_path).write_bytes(Path(other.file_path).read_bytes())
    before = snapshot(ctx.db)
    response = ctx.client.post(ctx.install)
    assert response.status_code == 409, response.text
    assert snapshot(ctx.db) == before


def test_package_validation_and_agent_notification_are_outside_the_guard(lifecycle, monkeypatch):
    ctx = lifecycle
    original_read, original_notify = Path.read_bytes, device_command_notifier.notify
    original_boundary = modules.device_authority_write
    in_guard = False

    @contextmanager
    def boundary(*args, **kwargs):
        nonlocal in_guard
        with original_boundary(*args, **kwargs) as value:
            in_guard = True
            try:
                yield value
            finally:
                in_guard = False

    def read(path):
        assert not in_guard
        return original_read(path)

    def notify(device_pk):
        assert not in_guard
        with Session(ctx.db.get_bind()) as other:
            assert other.scalar(select(ModuleInstallation)).command_id is not None
            assert read_authority_guard(other).revision == 2
        return original_notify(device_pk)

    monkeypatch.setattr(modules, "device_authority_write", boundary)
    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(device_command_notifier, "notify", notify)
    _request(ctx, ctx.install)


@pytest.mark.parametrize("operation", ["install", "disable", "result", "dispatch"])
def test_module_writers_reject_pending_explicit_and_nested_caller_transactions(lifecycle, operation):
    ctx = lifecycle
    sha = ctx.package.sha256
    command_id = prepare(ctx, "result")

    def invoke():
        if operation == "install":
            return modules.install_module(sha, DEVICE_ID, _admin=ctx.admin, db=ctx.db, idempotency_key="pending")
        if operation == "disable":
            return modules.disable_module(MODULE_ID, DEVICE_ID, _admin=ctx.admin, db=ctx.db, idempotency_key="pending")
        if operation == "result":
            return record_command_result(ctx.db, device=ctx.device, result=report(command_id))
        return deliver_next_command(ctx.db, device=ctx.device)

    error = HTTPException if operation in {"install", "disable"} else AuthorityMetadataError
    ctx.device.display_name = "pending caller change"
    with pytest.raises(error):
        invoke()
    assert ctx.device in ctx.db.dirty and ctx.device.display_name == "pending caller change"
    ctx.db.rollback()
    with ctx.db.begin():
        with pytest.raises(error):
            invoke()
        assert ctx.db.in_transaction()
        with ctx.db.begin_nested():
            with pytest.raises(error):
                invoke()
            assert ctx.db.in_nested_transaction()


@pytest.mark.parametrize("change", ["package", "runtime"])
def test_preflight_is_rechecked_under_the_guard(lifecycle, monkeypatch, change):
    ctx = lifecycle
    original = modules.device_authority_write

    @contextmanager
    def changed(*args, **kwargs):
        if change == "package":
            ctx.package.version = "changed"
        else:
            ctx.device.protocol_version = "changed"
        ctx.db.commit()
        with original(*args, **kwargs) as value:
            yield value

    monkeypatch.setattr(modules, "device_authority_write", changed)
    before = authority(ctx)
    response = ctx.client.post(ctx.install)
    assert response.status_code == 409, response.text
    assert authority(ctx) == before
    assert ctx.db.scalar(select(DeviceCommand)) is None


def test_real_connections_serialize_duplicate_install_and_keep_guard_first(lifecycle):
    ctx = lifecycle
    package_sha = ctx.package.sha256
    ctx.db.rollback()
    engine = ctx.db.get_bind()
    held, attempted, release, done = (threading.Event() for _ in range(4))
    results, writes = [], []

    def capture(_conn, _cursor, sql, _params, _context, _many):
        name = threading.current_thread().name
        if name not in {"module-first", "module-retry"}:
            return
        if sql.startswith(("UPDATE", "INSERT", "DELETE")):
            writes.append((name, sql))
        if name == "module-retry" and sql.startswith("UPDATE core_authority_guard"):
            attempted.set()
        if name == "module-first" and sql.startswith("INSERT INTO device_events"):
            held.set()
            if not release.wait(3):
                raise RuntimeError("test synchronization timed out")

    def run():
        try:
            with Session(engine) as db:
                result = modules.install_module(package_sha, DEVICE_ID, _admin=SimpleNamespace(id=1),
                                                db=db, idempotency_key="same-request")
                results.append(result.command_id)
        except BaseException as error:
            results.append(error)
        finally:
            if threading.current_thread().name == "module-retry":
                done.set()

    first = threading.Thread(target=run, name="module-first")
    second = threading.Thread(target=run, name="module-retry")
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
    assert len(results) == 2 and isinstance(results[0], str) and results[0] == results[1]
    for name in ("module-first", "module-retry"):
        assert next(sql for writer, sql in writes if writer == name).startswith("UPDATE core_authority_guard")
    assert read_authority_guard(ctx.db).revision == 2
    assert len(ctx.db.scalars(select(DeviceCommand)).all()) == 1
