"""Saved consent resumes only after exact confirmed lifecycle completion."""

from contextlib import contextmanager
from copy import deepcopy
import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant, ApplicationNativeReview as Native
from backend.db.audit_log import AuditLog
from backend.db.device import DeviceCapabilityProvider
from backend.db.module import ApplicationExtensionInstallation as Installation, ApplicationPermissionGrant, ApplicationSecretReference
from backend.routes.application_extensions import router
from backend.services import application_authority_management as management
from backend.services.application_commands import submit_command, command_lookup
from backend.tests.test_application_authority_management import (
    installed as managed_installed, source_subject, source_installed,
    activate_grant, command, identity,
)
from backend.tests.test_application_session_authority import (
    session_app, checkpoint_app, activate as activate_session, admit, check,
    SessionAuthorityError,
)
from backend.utils.db_utils import get_db
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError


pytestmark = pytest.mark.skipif(os.name != "posix", reason="Real POSIX sealed consent and key leases")
BASE = "/api/v1/application-extensions"


def stored(state):
    with Session(state.engine) as db:
        row = db.get(Grant, 1)
        return row.revision, json.loads(row.payload)


@contextmanager
def client(state, monkeypatch, hook=None):
    app = FastAPI()
    app.include_router(router)
    def database():
        with Session(state.engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    def helper(operation):
        def invoke(*args, **kwargs):
            # Stop/start never spans the consent key lock.
            with state.keys.locked():
                pass
            with Session(state.engine) as db:
                current = db.get(Installation, 1)
                assert current.status == operation and not current.enabled
                instance = current.instance_id
            if hook is not None:
                hook(operation)
            return {"module_id": state.validated.manifest.module_id,
                "version": "1.0.0", "sha256": state.validated.sha256,
                "instance_id": instance, "socket_path": "service.sock"}
        return invoke
    monkeypatch.setattr(UpdateHelperClient, "disable_application_extension", helper("disabling"))
    monkeypatch.setattr(UpdateHelperClient, "activate_application_extension", helper("activating"))
    with TestClient(app) as http:
        http.headers["Authorization"] = "Bearer " + state.token
        yield http


def stop(http, state):
    return http.post(BASE + "/" + state.validated.manifest.module_id + "/disable")


def start(http, state):
    return http.post(BASE + "/packages/" + state.validated.sha256 + "/activate", json={"configuration": {}})


def assert_same_consent(before, after):
    revision, original = deepcopy(before)
    new_revision, resumed = deepcopy(after)
    assert new_revision == revision
    assert resumed["revision"] != original["revision"]
    assert resumed["data"]["authority_epoch"] != original["data"]["authority_epoch"]
    resumed["revision"] = original["revision"]
    resumed["data"]["authority_epoch"] = original["data"]["authority_epoch"]
    assert resumed == original


def test_disable_enable_preserves_exact_saved_consent_and_invalidates_commands(managed_installed, monkeypatch):
    state = managed_installed
    activate_grant(state)
    before = stored(state)
    with Session(state.engine) as db:
        submit_command(db, db.get(Installation, 1), command("before-stop"))
    with client(state, monkeypatch) as http:
        response = stop(http, state)
        assert response.status_code == 200, response.text
        disabled = stored(state)
        assert_same_consent(before, disabled)
        status = state.manager.inspect(1)
        assert status["access_saved"] and not status["grant_effective"]
        with Session(state.engine) as db, pytest.raises(ValueError):
            submit_command(db, db.get(Installation, 1), command("while-stopped"))
        response = start(http, state)
        assert response.status_code == 200, response.text
    assert_same_consent(disabled, stored(state))
    assert state.manager.inspect(1)["grant_effective"]
    with Session(state.engine) as db:
        assert command_lookup(db, db.get(Installation, 1), {"binding_id": "pulse", "request_id": "before-stop"})["command"]["status"] == "invalidated"
        assert submit_command(db, db.get(Installation, 1), command("after-start"))["status"] == "queued"
        audits = list(db.scalars(select(AuditLog).where(AuditLog.action == "APPLICATION_CONSENT_RESUMED")))
        assert [row.changes["lifecycle_status"] for row in audits] == ["disabled", "active"]


@pytest.mark.parametrize("operation", ["disabling", "activating"])
def test_unknown_helper_outcome_cannot_resume_consent(managed_installed, monkeypatch, operation):
    state = managed_installed
    activate_grant(state)
    def failure(current):
        if current == operation:
            raise UpdateHelperError("Unconfirmed fixture outcome")
    with client(state, monkeypatch, failure) as http:
        if operation == "activating":
            assert stop(http, state).status_code == 200
        before = stored(state)
        response = stop(http, state) if operation == "disabling" else start(http, state)
        assert response.status_code == 409
    assert stored(state) == before
    with Session(state.engine) as db:
        app = db.get(Installation, 1)
        assert app.status == "recovery_required" and not app.enabled
        assert app.authority_epoch != before[1]["data"]["authority_epoch"]


@pytest.mark.parametrize("operation", ["disabling", "activating"])
@pytest.mark.parametrize("drift", ["provider", "credential", "native", "key", "grant", "grant_replaced", "artifact"])
def test_current_resource_trust_or_consent_drift_never_resumes(managed_installed, monkeypatch, operation, drift):
    state = managed_installed
    activate_grant(state)
    def change(current):
        if current != operation:
            return
        if drift == "key":
            state.keys.rotate(expected_key_id=state.keys.identity().key_id)
        elif drift == "artifact":
            state.archive.write_bytes(state.archive.read_bytes() + b"changed immutable artifact")
        elif drift in {"native", "grant", "grant_replaced"}:
            with state.keys.locked() as key, Session(state.engine) as db, db.begin():
                if drift == "native":
                    identifier = stored(state)[1]["data"]["native_review_id"]
                    row = db.get(Native, identifier)
                    value = management._load(db, key, "native", row, identifier)
                    kind = "native"
                else:
                    row = db.get(Grant, 1)
                    value = management._load(db, key, "grant", row, 1)
                    kind = "grant"
                value.update(state="active" if drift == "grant_replaced" else "revoked", revision=identity())
                management._save(db, key, kind, row, value)
        else:
            with state.engine.begin() as db:
                if drift == "provider":
                    db.execute(update(DeviceCapabilityProvider).values(revision=9))
                else:
                    db.execute(update(ApplicationSecretReference).values(version=10))
    with client(state, monkeypatch, change) as http:
        if operation == "activating":
            assert stop(http, state).status_code == 200
        before = stored(state)
        response = stop(http, state) if operation == "disabling" else start(http, state)
        assert response.status_code == 200, response.text
    after = stored(state)
    if drift in {"grant", "grant_replaced"}:
        assert after[1]["state"] == ("active" if drift == "grant_replaced" else "revoked")
        assert after[1]["data"]["authority_epoch"] == before[1]["data"]["authority_epoch"]
    else:
        assert after == before
    with Session(state.engine) as db:
        app = db.get(Installation, 1)
        assert app.authority_epoch != after[1]["data"]["authority_epoch"]
        if operation == "activating":
            with pytest.raises(ValueError):
                submit_command(db, app, command("must-deny"))


def test_revoke_while_disabled_and_arbitrary_stale_epoch_do_not_regain_access(managed_installed, monkeypatch):
    state = managed_installed
    activate_grant(state)
    with client(state, monkeypatch) as http:
        assert stop(http, state).status_code == 200
        state.manager.revoke(1, actor_token=state.token, request_id=identity(),
            expected_revision=stored(state)[1]["revision"])
        revoked = stored(state)
        response = start(http, state)
        assert response.status_code == 200, response.text
    assert stored(state) == revoked
    assert not state.manager.inspect(1)["access_saved"]


def test_old_stale_grant_is_not_made_current_by_stop_start(managed_installed, monkeypatch):
    state = managed_installed
    activate_grant(state)
    with state.engine.begin() as db:
        db.execute(update(Installation).values(authority_epoch=identity()))
    before = stored(state)
    with client(state, monkeypatch) as http:
        assert stop(http, state).status_code == 200
        assert start(http, state).status_code == 200
    assert stored(state) == before
    assert not state.manager.inspect(1)["access_saved"]


def test_missing_review_key_does_not_prevent_stopping(managed_installed, monkeypatch):
    state = managed_installed
    activate_grant(state)
    before = stored(state)
    def unavailable():
        raise management.AuthorityReviewKeyError()
    # The native service is still stoppable when its permission metadata fails.
    monkeypatch.setattr(state.manager.keys, "locked", unavailable)
    monkeypatch.setattr(UpdateHelperClient, "disable_application_extension", lambda *args: {})
    app = FastAPI()
    app.include_router(router)
    def database():
        with Session(state.engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    with TestClient(app) as http:
        response = http.post(BASE + "/" + state.validated.manifest.module_id + "/disable",
            headers={"Authorization": "Bearer " + state.token})
    assert response.status_code == 200, response.text
    assert stored(state) == before


def test_old_session_binding_and_removed_human_permission_do_not_return(session_app, monkeypatch):
    state = session_app
    activate_session(state)
    old = admit(state)
    with client(state, monkeypatch) as http:
        assert stop(http, state).status_code == 200
        assert start(http, state).status_code == 200
    assert admit(state).grant_revision != old.grant_revision
    with pytest.raises(SessionAuthorityError):
        check(state, old)
    with Session(state.engine) as db, db.begin():
        db.delete(db.scalar(select(ApplicationPermissionGrant)))
    with client(state, monkeypatch) as http:
        assert stop(http, state).status_code == 200
        assert start(http, state).status_code == 200
    with pytest.raises(SessionAuthorityError):
        admit(state)
    with Session(state.engine) as db:
        assert not list(db.scalars(select(ApplicationPermissionGrant)))
