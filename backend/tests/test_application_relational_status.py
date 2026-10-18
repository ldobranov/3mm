"""Read-only authority status through actual sealed grants and signed host IPC."""

import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session

from backend import config
from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.application_authority_grant import ApplicationNativeReview as Native
from backend.db.audit_log import AuditLog
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import ModulePackage
from backend.routes.application_authority import router
from backend.services import application_relational as core
from backend.tests.test_application_authority_management import (
    identity, installed as managed_installed,
)
from backend.tests.test_application_authority_subjects import (
    installed as source_subject, source_installed,
)
from backend.tests.test_application_relational_admission import SECRET, admitted
from backend.tests.test_application_relational_host import host_state
from backend.utils.db_utils import get_db
from three_mm_application_sdk.relational_wire import sign_metadata


pytestmark = pytest.mark.skipif(os.name != "posix", reason="Real POSIX keys/Unix IPC")


@pytest.fixture(autouse=True)
def status_settings(tmp_path, monkeypatch):
    settings = config.get_settings()
    runtime = settings.applications.model_copy(update={"key_root": tmp_path / "keys"})
    monkeypatch.setattr(config, "get_settings", lambda: settings.model_copy(
        update={"applications": runtime}))
    return runtime


@pytest.fixture
def ready(host_state, status_settings):
    state = host_state
    status_settings.key_root.mkdir()
    state.status_key = status_settings.key_root / (state.host_root.name + ".key")
    state.status_key.write_bytes(SECRET)
    state.status_key.chmod(0o640)
    return state


def blocked(state):
    status = state.manager.inspect(1)
    assert status["grant_effective"] is False
    assert status["runtime_blockers"] == ["relational_runtime_unavailable"]
    return status


def test_real_prepared_host_and_current_grants_report_effective(ready):
    status = ready.manager.inspect(1)
    assert status["grant_effective"] is True
    assert not status.get("runtime_blockers")
    assert status["grant_state"] == "active" and status["mode"] == "enforced"


def test_refresh_is_metadata_only_without_journal_grant_or_business_writes(ready):
    def snapshot():
        with Session(ready.engine) as db:
            guard = db.get(CoreAuthorityGuard, 1)
            grant = db.get(Grant, 1)
            return (guard.revision, guard.generation, grant.payload, grant.seal,
                tuple(db.scalars(select(Action.request_id))),
                tuple(db.scalars(select(AuditLog.id))))

    before = snapshot()
    database = ready.host_root / "data/state.sqlite3"
    data_before, key_before = database.read_bytes(), ready.status_key.read_bytes()

    def no_write(_connection, _cursor, statement, *_args):
        assert statement.lstrip().split()[0].upper() not in {
            "INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP", "ALTER"}

    event.listen(ready.engine, "before_cursor_execute", no_write)
    try:
        for _ in range(2):
            assert ready.manager.inspect(1)["grant_effective"] is True
    finally:
        event.remove(ready.engine, "before_cursor_execute", no_write)
    assert snapshot() == before
    assert database.read_bytes() == data_before and ready.status_key.read_bytes() == key_before


def test_admin_http_status_exposes_only_verified_public_result(ready):
    app = FastAPI()
    app.include_router(router)

    def database():
        with Session(ready.engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    path = "/api/v1/application-extensions/" + ready.validated.manifest.module_id + "/authority"
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer " + ready.user_token}).status_code == 403
        response = client.get(path, headers={"Authorization": "Bearer " + ready.token})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["grant_effective"] is True
    assert str(ready.host_root) not in response.text
    assert ready.token not in response.text and SECRET.decode() not in response.text


@pytest.mark.parametrize("problem", ["missing", "wrong", "short", "large", "symlink"])
def test_missing_invalid_or_replaced_transport_key_never_claims_ready(ready, problem):
    if problem == "missing":
        ready.status_key.unlink()
    elif problem == "symlink":
        saved = ready.status_key.with_suffix(".saved")
        ready.status_key.rename(saved)
        ready.status_key.symlink_to(saved)
    else:
        ready.status_key.write_bytes({"wrong": b"x" * 32, "short": SECRET[:-1],
            "large": SECRET + b"x"}[problem])
    blocked(ready)


def test_unavailable_host_never_claims_effective(ready):
    ready.host.path.unlink()
    blocked(ready)


@pytest.mark.parametrize("change", ["disabled", "revoked", "missing_grant", "native_revoked", "review_key"])
def test_no_current_rights_or_disabled_app_does_not_contact_host(ready, monkeypatch, change):
    if change == "disabled":
        with ready.engine.begin() as db:
            db.execute(update(Installation).values(enabled=False, status="disabled"))
    elif change == "missing_grant":
        with Session(ready.engine) as db, db.begin():
            db.delete(db.get(Grant, 1))
    elif change == "review_key":
        ready.keys.rotate(expected_key_id=ready.keys.identity().key_id)
    else:
        with Session(ready.engine) as db:
            grant = json.loads(db.get(Grant, 1).payload)
            if change == "revoked":
                revision = grant["revision"]
            else:
                native_id = grant["data"]["native_review_id"]
                revision = json.loads(db.get(Native, native_id).payload)["revision"]
        if change == "revoked":
            ready.manager.revoke(1, actor_token=ready.token, request_id=identity(), expected_revision=revision)
        else:
            ready.manager.revoke_native_review(1, actor_token=ready.token, request_id=identity(),
                native_review_id=native_id, expected_revision=revision)
    monkeypatch.setattr(core, "_call_host_metadata", lambda *_args: pytest.fail("Unreviewed/stopped app contacted host"))
    if change == "missing_grant":
        # An enforced installation with a missing sealed grant is status-only,
        # not a reviewable runtime failure. Preserve that existing closed DTO.
        current = ready.manager.inspect(1)
        assert current["grant_effective"] is False and current["review_available"] is False
        assert current["grant_record_revision"] is None and current["review_blockers"]
    else:
        blocked(ready)


@pytest.mark.parametrize("change", ["past", "future", "boot"])
def test_signed_but_expired_future_or_other_boot_metadata_is_not_readiness(ready, monkeypatch, change):
    original = ready.host._context

    def context(action, payload):
        value = original(action, payload)
        if change == "boot":
            value["boot_id"] = "00000000-0000-0000-0000-000000000000"
        else:
            value["clock_ms"] += -2001 if change == "past" else 2001
        return value

    monkeypatch.setattr(ready.host, "_context", context)
    blocked(ready)


@pytest.mark.parametrize("field", ["package_sha256", "service_sha256", "schema_revision",
    "owner_sha256", "configuration_sha256", "profile_sha256", "recovery_generation"])
def test_authentic_but_stale_or_foreign_host_metadata_is_refused(ready, field):
    record = dict(ready.host._record)
    record[field] = "0009" if field == "schema_revision" else "0" * len(record[field])
    ready.host._record = sign_metadata(SECRET, "lifecycle", record)
    blocked(ready)


def test_invalid_lifecycle_signature_is_refused(ready):
    ready.host._record = {**ready.host._record, "signature": "0" * 64}
    blocked(ready)


@pytest.mark.parametrize("change", ["revoke", "disable", "epoch", "configuration",
    "recovery", "artifact", "socket", "key"])
def test_change_during_host_ipc_cannot_return_effective_or_stale_revocation(ready, monkeypatch, change):
    original = core._call_host_metadata

    def changed(path, secret):
        hello = original(path, secret)
        if change == "revoke":
            with Session(ready.engine) as db:
                revision = json.loads(db.get(Grant, 1).payload)["revision"]
            ready.manager.revoke(1, actor_token=ready.token, request_id=identity(),
                expected_revision=revision)
        elif change == "key":
            ready.status_key.write_bytes(b"x" * 32)
        else:
            with ready.engine.begin() as db:
                if change == "recovery":
                    db.execute(update(CoreAuthorityGuard).values(generation=identity()))
                elif change == "artifact":
                    db.execute(update(ModulePackage).values(sha256="f" * 64))
                else:
                    db.execute(update(Installation).values(**{
                        "disable": {"enabled": False, "status": "disabled"},
                        "epoch": {"authority_epoch": identity()},
                        "configuration": {"configuration": {**ready.configuration, "PRIVATE_NOTE": "changed"}},
                        "socket": {"socket_path": str(ready.host_root / "other/run/service.sock")},
                    }[change]))
        return hello

    monkeypatch.setattr(core, "_call_host_metadata", changed)
    # An invalid new artifact may make the whole status unavailable; never green.
    try:
        status = ready.manager.inspect(1)
    except core.authority.AuthorityManagementError:
        assert change == "artifact"
    else:
        assert status["grant_effective"] is False
        if change == "revoke":
            assert status["grant_state"] == "revoked" and status["mode"] == "review_required"


def test_host_ipc_holds_no_core_snapshot_or_review_key_lease(ready, monkeypatch):
    original = core._call_host_metadata

    def observed(path, secret):
        with ready.manager.keys.locked(), ready.engine.begin() as db:
            db.execute(update(Installation).values(error="status-observer"))
        return original(path, secret)

    monkeypatch.setattr(core, "_call_host_metadata", observed)
    assert ready.manager.inspect(1)["grant_effective"] is True
