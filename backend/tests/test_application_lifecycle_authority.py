"""M20 lifecycle fences: actual HTTP, durable phases and independent DB sessions."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import threading

import backend.database  # noqa: F401
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.orm import Session

from backend.db.application_command import ApplicationCommandEpoch, ApplicationCommandRequest
from backend.db.audit_log import AuditLog
from backend.db.authority import CoreAuthorityGuard
from backend.db.base import Base
from backend.db.device import Device, DeviceCommand
from backend.db.installation_peer import InstallationPeerOutbound
from backend.db.module import (
    ApplicationEventCursor, ApplicationExtensionInstallation, ApplicationJobState,
    ModulePackage,
)
from backend.db.user import User
from backend.routes import application_extensions as routes
from backend.routes.application_operations import router as operations_router
from backend.services.authority_metadata import (
    AuthorityMetadataError, authority_transaction, read_application_authority,
    read_authority_guard,
)
from backend.services.application_secrets import create_secret_reference
from backend.services.module_packages import validate_module_package
from backend.tests.test_module_packages import application_package
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token
from three_mm_runtime.update_helper_client import UpdateHelperError


@pytest.fixture
def lifecycle(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'lifecycle.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 3},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    blob = application_package()
    validated = validate_module_package(blob)
    archive = tmp_path / "package.zip"
    archive.write_bytes(blob)
    module_id = validated.manifest.module_id
    device_id = "dev_" + "1" * 32
    now = datetime.now(UTC)
    with Session(engine) as db, db.begin():
        db.add_all([
            CoreAuthorityGuard(singleton_id=1),
            User(id=1, username="admin", email="admin@example.test", hashed_password="x", role="admin"),
            User(id=2, username="operator", email="operator@example.test", hashed_password="x", role="user"),
            ModulePackage(
                id=1, module_id=module_id, version="1.0.0", sha256=validated.sha256,
                manifest=validated.manifest.model_dump(mode="json"), size_bytes=len(blob),
                file_path=str(archive),
            ),
            Device(id=1, device_id=device_id, display_name="Reader", role="node", protocol_version="1.0", approved_at=now),
        ])
        db.flush()
        db.add(ApplicationExtensionInstallation(
            id=1, module_id=module_id, module_package_id=1,
            instance_id="a" * 24, socket_path="service.sock", active_version="1.0.0",
            status="active", enabled=True, configuration={"READER_DEVICE_ID": device_id},
        ))
        db.flush()
        db.add(ApplicationCommandEpoch(installation_id=1, generation="c" * 32))
        for index, status in enumerate(("queued", "delivered", "succeeded"), 1):
            command_id = f"cmd_{index}"
            db.add(DeviceCommand(
                command_id=command_id, device_id=1, command_type="application.capability.invoke",
                payload={}, idempotency_key=command_id, status=status,
                expires_at=now + timedelta(minutes=5),
            ))
            db.flush()
            db.add(ApplicationCommandRequest(
                command_id=command_id, installation_id=1, package_id=1,
                generation="c" * 32, claimed=status != "queued",
            ))
        db.add(ApplicationEventCursor(application_installation_id=1, subscription_id="identifier_scans", last_event_id="event-keep"))
        db.add(InstallationPeerOutbound(
            link_id="peer-keep", module_id=module_id, application_instance_id="a" * 24,
            sender_identity={}, receiver_identity={}, origin="https://example.test",
            target_module_id="org.example.remote", consent={}, state="active",
            credential={"private": "do-not-audit"}, created_at=now, updated_at=now,
        ))
    app = FastAPI()
    app.include_router(routes.router)
    app.include_router(operations_router)
    sessions, calls = [], []

    def database():
        with Session(engine) as db:
            sessions.append(db)
            yield db

    app.dependency_overrides[get_db] = database
    settings = SimpleNamespace(applications=SimpleNamespace(helper_socket=tmp_path / "helper.sock"))
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    result = dict(module_id=module_id, version="1.0.0", sha256=validated.sha256,
                  instance_id="a" * 24, socket_path="service.sock")
    fixture = SimpleNamespace(
        engine=engine, sessions=sessions, calls=calls, result=result,
        base=f"/api/v1/application-extensions/{module_id}",
        activate=f"/api/v1/application-extensions/packages/{validated.sha256}/activate",
        body={"configuration": {"READER_DEVICE_ID": device_id}}, module_id=module_id,
        auth={"Authorization": f"Bearer {create_access_token('1', {'role': 'admin'})}"},
    )

    def helper(operation):
        def invoke(_self, *_args):
            assert not sessions[-1].in_transaction()
            calls.append(operation)
            # Committed fence is visible before any runtime I/O.
            with Session(engine) as db:
                installation = db.get(ApplicationExtensionInstallation, 1)
                assert installation.status == operation and not installation.enabled
                assert db.get(ApplicationCommandEpoch, 1).generation != "c" * 32
                assert db.get(DeviceCommand, 1).status == "failed"
                assert db.scalar(select(AuditLog.action)) == "APPLICATION_EXTENSION_LIFECYCLE_STARTED"
            return dict(result) if operation == "activating" else None
        return invoke

    fixture.helper = helper
    for operation, method in (
        ("activating", "activate_application_extension"),
        ("disabling", "disable_application_extension"),
        ("uninstalling", "uninstall_application_extension"),
    ):
        monkeypatch.setattr(routes.UpdateHelperClient, method, helper(operation))
    with TestClient(app, raise_server_exceptions=False) as client:
        fixture.client = client
        yield fixture
    engine.dispose()


def request(s, operation):
    if operation == "activating":
        return s.client.post(s.activate, headers=s.auth, json=s.body)
    if operation == "disabling":
        return s.client.post(s.base + "/disable", headers=s.auth)
    return s.client.delete(s.base, headers=s.auth)


def snapshot(s):
    with Session(s.engine) as db:
        return (
            read_authority_guard(db), read_application_authority(db, 1),
            tuple(db.execute(select(*ApplicationExtensionInstallation.__table__.c)).one()),
            db.get(ApplicationCommandEpoch, 1).generation,
            tuple(db.execute(select(DeviceCommand.command_id, DeviceCommand.status, DeviceCommand.result).order_by(DeviceCommand.id))),
            tuple(db.scalars(select(AuditLog.action).order_by(AuditLog.id))),
            tuple(db.execute(select(InstallationPeerOutbound.state, InstallationPeerOutbound.consent_revision)).one()),
        )


@pytest.mark.parametrize("operation", ["activating", "disabling", "uninstalling"])
def test_success_fences_before_io_and_commits_terminal_audit(lifecycle, operation):
    s = lifecycle
    before = snapshot(s)
    response = request(s, operation)
    assert response.status_code == 200, response.text
    assert s.calls == [operation]
    assert "authority" not in response.text and "do-not-audit" not in response.text
    with Session(s.engine) as db:
        assert read_authority_guard(db).revision == before[0].revision + 2
        assert [r.status for r in db.scalars(select(DeviceCommand).order_by(DeviceCommand.id))] == ["failed", "failed", "succeeded"]
        if operation == "uninstalling":
            assert db.get(ApplicationExtensionInstallation, 1) is None
            assert db.get(ModulePackage, 1) is not None
            assert db.get(InstallationPeerOutbound, "peer-keep").state == "revoked"
            assert db.get(ApplicationCommandEpoch, 1) is None
        else:
            current = read_application_authority(db, 1)
            assert current.incarnation == before[1].incarnation
            assert current.epoch != before[1].epoch
            assert db.scalar(select(ApplicationEventCursor.last_event_id)) == "event-keep"
        assert db.scalar(select(AuditLog.action).order_by(AuditLog.id.desc())) == {
            "activating": "APPLICATION_EXTENSION_ACTIVATED",
            "disabling": "APPLICATION_EXTENSION_DISABLED",
            "uninstalling": "APPLICATION_EXTENSION_UNINSTALLED",
        }[operation]


@pytest.mark.parametrize("operation", ["activating", "disabling", "uninstalling"])
def test_helper_failure_is_quarantined_without_restoring_authority(lifecycle, monkeypatch, operation):
    s = lifecycle
    before = snapshot(s)

    def fail(_self, *_args):
        s.helper(operation)(_self)
        raise UpdateHelperError("private helper diagnostics")

    monkeypatch.setattr(routes.UpdateHelperClient, {
        "activating": "activate_application_extension", "disabling": "disable_application_extension",
        "uninstalling": "uninstall_application_extension",
    }[operation], fail)
    assert request(s, operation).status_code == 409
    after = snapshot(s)
    assert after[0].revision == before[0].revision + 2
    assert after[1].epoch != before[1].epoch and after[1].incarnation == before[1].incarnation
    with Session(s.engine) as db:
        installation = db.get(ApplicationExtensionInstallation, 1)
        assert installation.status == "recovery_required" and not installation.enabled
        assert "private" not in installation.error
    # No automatic retries or bypass through a different lifecycle action.
    for action in ("activating", "disabling", "uninstalling"):
        assert request(s, action).status_code == 409
    assert s.calls == [operation]
    assert snapshot(s) == after


@pytest.mark.parametrize("phase", ["start", "completion"])
@pytest.mark.parametrize("operation", ["activating", "disabling", "uninstalling"])
def test_audit_failure_rolls_back_its_entire_phase(lifecycle, operation, phase):
    s = lifecycle
    before = snapshot(s)

    def reject(_conn, _cursor, statement, parameters, _context, _many):
        if statement.startswith("INSERT INTO audit_logs"):
            is_start = "APPLICATION_EXTENSION_LIFECYCLE_STARTED" in parameters
            if is_start == (phase == "start"):
                raise RuntimeError("audit unavailable")

    event.listen(s.engine, "before_cursor_execute", reject)
    try:
        assert request(s, operation).status_code == 500
    finally:
        event.remove(s.engine, "before_cursor_execute", reject)
    after = snapshot(s)
    if phase == "start":
        assert after == before and s.calls == []
    else:
        assert s.calls == [operation]
        assert after[0].revision == before[0].revision + 1
        with Session(s.engine) as db:
            assert db.get(ApplicationExtensionInstallation, 1).status == operation
            assert not db.get(ApplicationExtensionInstallation, 1).enabled
            assert db.scalar(select(AuditLog.action)) == "APPLICATION_EXTENSION_LIFECYCLE_STARTED"


@pytest.mark.parametrize("change", ["epoch", "incarnation", "package", "configuration"])
def test_late_helper_completion_cannot_overwrite_changed_identity(lifecycle, monkeypatch, change):
    s = lifecycle
    changed = []

    def late(_self, *_args):
        s.helper("activating")(_self)
        with Session(s.engine) as db, db.begin():
            values = {"epoch": {"authority_epoch": "d" * 32},
                      "incarnation": {"authority_incarnation": "e" * 32},
                      "package": {"previous_package_id": None},
                      "configuration": {"configuration": {"READER_DEVICE_ID": "changed"}}}[change]
            db.execute(update(ApplicationExtensionInstallation).where(
                ApplicationExtensionInstallation.id == 1
            ).values(**values))
        changed.append(snapshot(s))
        return dict(s.result)

    monkeypatch.setattr(routes.UpdateHelperClient, "activate_application_extension", late)
    assert request(s, "activating").status_code == 409
    assert snapshot(s) == changed[0]


def test_uninstall_cannot_erase_unresolved_job_claim(lifecycle):
    s = lifecycle
    with Session(s.engine) as db, db.begin():
        db.add(ApplicationJobState(
            application_installation_id=1, job_id="sync", next_run_at=datetime.now(UTC),
            lease_token="f" * 32, last_outcome="unknown", last_error="execution_unconfirmed",
        ))
    before = snapshot(s)
    assert request(s, "uninstalling").status_code == 409
    assert snapshot(s) == before and not s.calls
    assert request(s, "disabling").status_code == 200
    with Session(s.engine) as db:
        state = db.scalar(select(ApplicationJobState))
        assert state.lease_token == "f" * 32 and state.last_outcome == "unknown"


def test_missing_guard_and_non_admin_never_call_helper(lifecycle):
    s = lifecycle
    user = {"Authorization": f"Bearer {create_access_token('2', {'role': 'user'})}"}
    assert s.client.post(s.base + "/disable", headers=user).status_code == 403
    assert s.client.delete(s.base).status_code == 401
    with Session(s.engine) as db, db.begin():
        db.execute(CoreAuthorityGuard.__table__.delete())
    for operation in ("activating", "disabling", "uninstalling"):
        assert request(s, operation).status_code == 409
    assert not s.calls


def test_package_validation_precedes_first_guard_write(lifecycle, monkeypatch):
    s = lifecycle
    writes = []
    original = routes._definition

    def load(package):
        assert not writes
        return original(package)

    def capture(_conn, _cursor, statement, *_args):
        if statement.startswith(("UPDATE", "INSERT", "DELETE")):
            writes.append(statement)

    monkeypatch.setattr(routes, "_definition", load)
    event.listen(s.engine, "before_cursor_execute", capture)
    try:
        assert request(s, "activating").status_code == 200
    finally:
        event.remove(s.engine, "before_cursor_execute", capture)
    assert writes[0].startswith("UPDATE core_authority_guard")


def test_management_writer_and_other_lifecycle_are_blocked_during_helper(lifecycle, monkeypatch):
    s = lifecycle

    def helper(_self, *_args):
        s.helper("activating")(_self)
        with Session(s.engine) as db:
            expected = read_application_authority(db, 1)
        with Session(s.engine) as db:
            with pytest.raises(AuthorityMetadataError):
                with authority_transaction(db) as authority:
                    create_secret_reference(db, application=expected, label="Unused",
                        credential_kind="bearer", value={"token": "secret"}, authority=authority)
        assert s.client.post(s.base + "/disable", headers=s.auth).status_code == 409
        assert s.client.delete(s.base, headers=s.auth).status_code == 409
        return dict(s.result)

    monkeypatch.setattr(routes.UpdateHelperClient, "activate_application_extension", helper)
    assert request(s, "activating").status_code == 200
    assert s.calls == ["activating"]


def test_reinstall_gets_fresh_incarnation_even_with_same_runtime_locator(lifecycle, monkeypatch):
    s = lifecycle
    before = snapshot(s)[1]
    assert request(s, "uninstalling").status_code == 200
    monkeypatch.setattr(routes.UpdateHelperClient, "activate_application_extension", lambda *_args: dict(s.result))
    assert request(s, "activating").status_code == 200
    with Session(s.engine) as db:
        installation = db.scalar(select(ApplicationExtensionInstallation))
        after = read_application_authority(db, installation.id)
        assert after.incarnation != before.incarnation and after.epoch != before.epoch
        assert installation.instance_id == "a" * 24
        assert db.get(InstallationPeerOutbound, "peer-keep").state == "revoked"


def test_interrupted_transition_is_not_implicitly_retried(lifecycle):
    s = lifecycle
    with Session(s.engine) as db, db.begin():
        db.execute(update(ApplicationExtensionInstallation).values(status="activating", enabled=False))
    before = snapshot(s)
    for operation in ("activating", "disabling", "uninstalling"):
        assert request(s, operation).status_code == 409
    assert snapshot(s) == before and not s.calls


def test_endpoint_scope_rejects_pending_work(lifecycle):
    with Session(lifecycle.engine) as db:
        user = db.get(User, 1)
        user.username = "pending"
        with pytest.raises(HTTPException) as error:
            with routes._lifecycle_write(db):
                pytest.fail("pending work discarded")
        assert error.value.status_code == 409 and user in db.dirty


@pytest.mark.parametrize("result", [None, {"sha256": "f" * 64}, {"instance_id": "invalid"}])
def test_invalid_helper_response_never_activates(lifecycle, monkeypatch, result):
    s = lifecycle
    response = dict(s.result, **result) if result is not None else None
    monkeypatch.setattr(routes.UpdateHelperClient, "activate_application_extension", lambda *_args: response)
    assert request(s, "activating").status_code == 409
    with Session(s.engine) as db:
        installation = db.get(ApplicationExtensionInstallation, 1)
        assert installation.status == "recovery_required" and not installation.enabled


def test_pending_candidate_reserves_routes_but_is_not_publicly_dispatched(lifecycle, monkeypatch):
    from backend.services import application_public_web as public_web
    from backend.tests.test_application_public_web import definition

    s = lifecycle
    with Session(s.engine) as db:
        installation = db.get(ApplicationExtensionInstallation, 1)
        installation.status, installation.enabled = "activating", False
        installation.active_version = "0.9.0"  # Pending package is the new version.
        candidate = ModulePackage(module_id="org.example.candidate", version="1.0.0",
            manifest={}, sha256="f" * 64, size_bytes=1, file_path="unused")
        db.add(candidate)
        db.commit()
        monkeypatch.setattr(public_web, "load_application_definition",
                            lambda package: definition(package.module_id, "/site/{slug}"))
        assert public_web.build_public_route_registry(db) == ()
        with pytest.raises(public_web.ApplicationPublicWebError, match="conflict"):
            public_web.validate_public_http_candidate(db, candidate, definition(candidate.module_id, "/site/home"))


def test_lifecycle_waiter_rejects_changed_guard_after_other_connection_commits(lifecycle):
    s = lifecycle
    attempted, done = threading.Event(), threading.Event()
    result = []

    def capture(_conn, _cursor, statement, *_args):
        if statement.startswith("UPDATE core_authority_guard") and threading.current_thread().name != "MainThread":
            attempted.set()

    def disable():
        try:
            result.append(request(s, "disabling").status_code)
        except BaseException as exc:
            result.append(exc)
        finally:
            done.set()

    thread = threading.Thread(target=disable, name="lifecycle-waiter")
    event.listen(s.engine, "before_cursor_execute", capture)
    try:
        with Session(s.engine) as db:
            expected = read_application_authority(db, 1)
            db.rollback()
            with authority_transaction(db) as authority:
                authority.advance_application_epoch(expected)
                thread.start()
                assert attempted.wait(2) and not done.wait(0.05)
            assert done.wait(4)
    finally:
        if thread.ident is not None:
            thread.join(4)
        event.remove(s.engine, "before_cursor_execute", capture)
    assert result == [409] and not s.calls
