"""Live resource replacement with real seals, sessions, queue and SDK transport."""
from copy import deepcopy
from datetime import UTC, datetime
import json
import io
import os
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.base import Base
from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant, ApplicationAuthorityPlan as Plan
from backend.db.audit_log import AuditLog
from backend.db.device import Device, DeviceCommand, DeviceCapabilityProvider
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.db.session import UserSession
from backend.db.user import User
from backend.routes.application_authority import router
from backend.services import application_command_rebinding as rebind
from backend.services import application_commands as commands
from backend.services.application_authority_management import AuthorityManagementError
from backend.services.device_commands import deliver_next_command, record_command_result
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_command_discovery import (
    installed, source_subject, source_installed, identity, vertical, add_provider, execute,
)
from backend.tests.test_application_consent import preview as consent_preview, allow, read
from backend.utils.db_utils import get_db
from three_mm_application_sdk import ApplicationPlatformError
from three_mm_protocol import AgentCommandResult
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError
from three_mm_runtime import application_lifecycle as helper_fencing

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Real sealed POSIX authority")


@pytest.fixture
def state(installed):
    s = installed
    Base.metadata.create_all(s.engine)
    s.second_id, s.second = add_provider(s)
    allow(s, consent_preview(s), scopes=["command:pulse"])
    return s


def preview(s, **options):
    return rebind.preview(s.manager, 1, actor_token=options.pop("actor_token", s.token),
        request_id=identity(), binding_id="pulse", device_id=options.pop("device_id", s.second), **options)


def apply(s, plan, **options):
    return rebind.apply(s.manager, 1, actor_token=options.pop("actor_token", s.token),
        request_id=options.pop("request_id", identity()), preview_id=plan["preview_id"],
        expected_revision=plan["revision"], fingerprint=plan["fingerprint"], approve_change=True, **options)


def submit(s, request_id):
    with Session(s.engine) as db:
        return commands.submit_command(db, db.get(Installation, 1), {
            "binding_id": "pulse", "request_id": request_id, "ttl_seconds": 5,
            "arguments": {"channel": "output.1", "duration_ms": 50}})


def lookup(s, request_id):
    with Session(s.engine) as db:
        return commands.command_lookup(db, db.get(Installation, 1), {"binding_id": "pulse", "request_id": request_id})


def activation(s, monkeypatch, during=None):
    calls = []
    state_root = s.root / "helper-state"
    state_root.mkdir(exist_ok=True, mode=0o700)
    monkeypatch.setattr(helper_fencing, "RELEASE_MUTATION_LOCK", s.root / "release.lock")
    def activate(self, sha, actor, configuration, lifecycle):
        calls.append(deepcopy(lifecycle))
        payload = dict(action="activate_application_extension", sha256=sha,
            requested_by_user_id=actor, configuration=configuration, lifecycle=lifecycle)
        with helper_fencing.application_lifecycle_operation(payload,
                database=s.engine.url.database, state_root=state_root, enforce_permissions=False):
            return effect(sha, configuration, lifecycle)
    def effect(sha, configuration, lifecycle):
        with Session(s.engine) as db:
            app = db.get(Installation, 1)
            assert not app.enabled and app.status == "activating"
            assert app.configuration == configuration
            assert app.configuration["TARGET_DEVICE_ID"] == s.second
            assert app.authority_epoch == lifecycle["epoch"]
            assert app.authority_epoch != json.loads(db.get(Grant, 1).payload)["data"]["authority_epoch"]
        with pytest.raises((ValueError, AuthorityManagementError)):
            submit(s, "during-change")
        if during:
            during()
        return {"module_id": s.validated.manifest.module_id, "version": s.validated.manifest.version,
            "sha256": sha, "instance_id": lifecycle["instance_id"], "socket_path": "/run/application.sock"}
    monkeypatch.setattr(UpdateHelperClient, "activate_application_extension", activate)
    return calls


def test_preview_is_exact_but_has_no_effect_or_secret(state):
    s = state
    old = read(s, "grant", Grant, 1)
    plan = preview(s)
    assert plan["before"]["target_device_id"] != s.second
    assert plan["after"]["target_device_id"] == s.second
    assert plan["after_provider"]["provider_id"] == "org.example.second"
    assert plan["scopes"] == ["command:pulse"] and plan["restart_required"]
    assert read(s, "grant", Grant, 1) == old
    assert submit(s, "preview-only")["target_device_id"] == plan["before"]["target_device_id"]
    with Session(s.engine) as db:
        assert db.get(Installation, 1).enabled
        serialized = str([row.changes for row in db.scalars(select(AuditLog))]) + db.get(Plan, plan["preview_id"]).payload
        from backend.tests.test_application_authority_sources import PRIVATE
        assert PRIVATE not in serialized


def test_same_live_application_switches_provider_through_http_and_real_sdk(vertical, monkeypatch, tmp_path):
    s = vertical
    s.second_id, s.second = add_provider(s)
    allow(s, consent_preview(s), scopes=["command:pulse"])
    before = s.probe.observe()["selected_device_id"]
    s.probe.submit(request_id="before", arguments={"channel": "output.1", "duration_ms": 50})
    effects = []
    execute(s, tmp_path / "before", 1, effects)
    url = f"/api/v1/application-extensions/{s.validated.manifest.module_id}/authority/command-rebindings"
    response = s.http.post(url, headers=s.headers,
        json={"request_id": identity(), "binding_id": "pulse", "device_id": s.second})
    assert response.status_code == 200, response.text
    plan = response.json()
    calls = activation(s, monkeypatch)
    body = {"request_id": identity(), "expected_revision": plan["revision"],
        "fingerprint": plan["fingerprint"], "approve_change": True}
    response = s.http.post(url + f'/{plan["preview_id"]}/apply', headers=s.headers, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "completed"
    assert s.probe.observe()["selected_device_id"] == s.second
    assert s.probe.lookup("before")["command"]["target_device_id"] == before
    assert s.probe.lookup("before")["command"]["execution_status"] == "succeeded"
    with pytest.raises(ApplicationPlatformError):
        s.probe.submit(request_id="before", arguments={"channel": "output.1", "duration_ms": 50})
    s.probe.submit(request_id="after", arguments={"channel": "output.1", "duration_ms": 50})
    execute(s, tmp_path / "after", s.second_id, effects)
    s.server.stop()
    s.server.start()
    replay = s.http.post(url + f'/{plan["preview_id"]}/apply', headers=s.headers, json=body)
    assert replay.status_code == 200 and replay.json()["historical"]
    status = s.http.get(url + f'/{plan["preview_id"]}', headers=s.headers)
    assert status.json()["state"] == "completed" and status.headers["cache-control"] == "no-store"
    assert len(calls) == 1 and effects == [before, s.second]
    assert s.probe.observe()["selected_device_id"] == s.second
    assert s.probe.lookup("after")["command"]["execution_status"] == "succeeded"


@pytest.mark.parametrize("fault", ["provider", "configuration", "session", "role", "grant", "expired", "reboot"])
def test_preview_drift_never_starts_runtime_or_changes_binding(state, monkeypatch, fault):
    s = state
    plan = preview(s)
    calls = activation(s, monkeypatch)
    if fault in {"expired", "reboot"}:
        boot, now = rebind.authority._clock()
        monkeypatch.setattr(rebind.authority, "_clock", lambda: ("another-boot" if fault == "reboot" else boot,
            now + rebind.TTL_MS if fault == "expired" else now))
    else:
        with Session(s.engine) as db, db.begin():
            if fault == "provider":
                db.execute(update(DeviceCapabilityProvider).where(DeviceCapabilityProvider.device_id == s.second_id).values(revision=9))
            elif fault == "configuration":
                app = db.get(Installation, 1)
                app.configuration = {**app.configuration, "PRIVATE_NOTE": "changed"}
            elif fault == "session":
                db.get(UserSession, 1).is_active = False
            elif fault == "role":
                db.get(User, 1).role = "user"
            elif fault == "grant":
                db.get(Grant, 1).revision += 1
    with pytest.raises((AuthorityManagementError, ValueError)):
        apply(s, plan)
    assert not calls
    with Session(s.engine) as db:
        assert db.get(Installation, 1).enabled
        assert db.get(Installation, 1).configuration["TARGET_DEVICE_ID"] != s.second


@pytest.mark.parametrize("fault", ["provider", "session", "timeout", "bad_reply", "artifact"])
def test_uncertain_or_changed_completion_never_grants_new_resource(state, monkeypatch, fault):
    s = state
    plan = preview(s)
    def during():
        if fault == "timeout":
            raise UpdateHelperError("Simulated lost reply")
        if fault == "artifact":
            s.archive.write_bytes(b"changed")
        with Session(s.engine) as db, db.begin():
            if fault == "provider":
                db.execute(update(DeviceCapabilityProvider).where(DeviceCapabilityProvider.device_id == s.second_id).values(revision=9))
            if fault == "session":
                db.get(UserSession, 1).is_active = False
    calls = activation(s, monkeypatch, during)
    if fault == "bad_reply":
        monkeypatch.setattr(UpdateHelperClient, "activate_application_extension", lambda *a: {})
    with pytest.raises(AuthorityManagementError, match="recovery_required"):
        apply(s, plan)
    outcome = rebind.status(s.manager, 1, plan_id=plan["preview_id"])
    assert outcome["state"] == "recovery_required" and not outcome["installation_enabled"]
    with pytest.raises((AuthorityManagementError, ValueError)):
        submit(s, "must-not-run")
    with Session(s.engine) as db:
        assert db.get(Installation, 1).configuration["TARGET_DEVICE_ID"] == s.second
        assert not db.scalars(select(DeviceCommand)).all()


@pytest.mark.parametrize("phase", ["before_helper", "after_helper"])
def test_crash_requires_explicit_quiescence_then_fresh_consent(state, monkeypatch, phase):
    s = state
    plan = preview(s)
    calls = activation(s, monkeypatch)
    class Crash(BaseException):
        pass
    if phase == "before_helper":
        monkeypatch.setattr(UpdateHelperClient, "activate_application_extension", lambda *a: (_ for _ in ()).throw(Crash()))
    else:
        monkeypatch.setattr(rebind, "_refresh_artifact", lambda *a: (_ for _ in ()).throw(Crash()))
    request_id = identity()
    with pytest.raises(Crash):
        apply(s, plan, request_id=request_id)
    assert apply(s, plan, request_id=request_id)["historical"]
    pending = rebind.status(s.manager, 1, plan_id=plan["preview_id"])
    assert pending["state"] == "applying" and pending["recovery_required"]
    contexts = []
    def recover(self, instance_id, actor, context):
        contexts.append(context)
        payload = dict(action="recover_application_extension", instance_id=instance_id,
            requested_by_user_id=actor, lifecycle=context)
        with helper_fencing.application_lifecycle_operation(payload, database=s.engine.url.database,
                state_root=s.root / "helper-state", enforce_permissions=False):
            return {"status": "disabled", "instance_id": instance_id, "lifecycle": context, "quiescent": True}
    monkeypatch.setattr(UpdateHelperClient, "recover_application_extension", recover)
    result = rebind.recover(s.manager, 1, actor_token=s.token, preview_id=plan["preview_id"],
        expected_revision=pending["revision"], confirmed_external_outcome_reviewed=True)
    assert result["state"] == "recovered_disabled" and not result["installation_enabled"]
    if calls:
        assert contexts[0]["epoch"] != calls[0]["epoch"]
    with pytest.raises((AuthorityManagementError, ValueError)):
        submit(s, "after-recover")
    assert not s.manager.inspect(1)["grant_effective"]
    # Reconsent to the stopped exact artifact/resource; ordinary activation can
    # then resume that fresh consent. No automatic approval or activation here.
    reviewed = consent_preview(s)
    allowed = allow(s, reviewed, scopes=["command:pulse"])
    assert allowed["saved"] and not allowed["effective"]
    # The old pending activation cannot follow recovery, even after a helper
    # restart has discarded all in-memory state.
    if calls:
        with Session(s.engine) as db:
            configuration = deepcopy(db.get(Installation, 1).configuration)
        payload = dict(action="activate_application_extension", sha256=s.validated.sha256,
            requested_by_user_id=1, configuration=configuration, lifecycle=calls[0])
        with pytest.raises(helper_fencing.ApplicationLifecycleError):
            with helper_fencing.application_lifecycle_operation(payload, database=s.engine.url.database,
                    state_root=s.root / "helper-state", enforce_permissions=False):
                pytest.fail("Delayed activation passed the recovery fence")
    # Resume using the existing ordinary activation path and its consent lease.
    activation(s, monkeypatch)
    from backend.routes.application_extensions import activate_application_extension
    with Session(s.engine) as db:
        result = activate_application_extension(s.validated.sha256, admin=db.get(User, 1), db=db)
    assert result.enabled and s.manager.inspect(1)["grant_effective"]
    assert submit(s, "after-explicit-reactivation")["target_device_id"] == s.second
    assert len(contexts) == 1


def test_old_claimed_receipt_survives_and_old_request_cannot_target_new_device(state, monkeypatch):
    s = state
    queued = submit(s, "old-unknown")
    with Session(s.engine) as db:
        device = db.get(Device, 1)
        command = deliver_next_command(db, device=device)
        commands.authorize_execution(db, device, command.command_id)
        receipt = AgentCommandResult(command_id=command.command_id, device_id=device.device_id,
            status="succeeded", completed_at=datetime.now(UTC), output={"done": True})
    plan = preview(s)
    activation(s, monkeypatch)
    assert apply(s, plan)["state"] == "completed"
    found = lookup(s, "old-unknown")["command"]
    assert found["claimed"] and found["execution_status"] == "delivered"
    assert found["target_device_id"] != s.second
    with pytest.raises(ValueError):
        submit(s, "old-unknown")
    with Session(s.engine) as db:
        with pytest.raises((AuthorityManagementError, ValueError)):
            commands.authorize_execution(db, db.get(Device, 1), queued["command_id"])
    with Session(s.engine) as db:
        record_command_result(db, device=db.get(Device, 1), result=receipt)
    found = lookup(s, "old-unknown")["command"]
    assert found["status"] == "invalidated" and found["execution_status"] == "succeeded"
    assert found["result"] == {"done": True}
    with Session(s.engine) as db:
        assert len(db.scalars(select(DeviceCommand)).all()) == 1


def test_http_nonadmin_invalid_approval_and_cross_installation_denied(state, monkeypatch):
    s = state
    app = FastAPI()
    app.include_router(router)
    def database():
        with Session(s.engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    url = f"/api/v1/application-extensions/{s.validated.manifest.module_id}/authority/command-rebindings"
    calls = activation(s, monkeypatch)
    with TestClient(app) as http:
        body = {"request_id": identity(), "binding_id": "pulse", "device_id": s.second}
        assert http.post(url, json=body).status_code == 401
        assert http.post(url, headers={"Authorization": "Bearer " + s.user_token}, json=body).status_code == 403
        headers = {"Authorization": "Bearer " + s.token}
        plan = http.post(url, headers=headers, json=body).json()
        assert http.post(url + f'/{plan["preview_id"]}/apply', headers=headers, json={
            "request_id": identity(), "expected_revision": plan["revision"], "fingerprint": plan["fingerprint"],
            "approve_change": False}).status_code == 422
        with pytest.raises(AuthorityManagementError, match="record_unavailable"):
            rebind.status(s.manager, 2, plan_id=plan["preview_id"])
    assert not calls


@pytest.mark.parametrize("fault", ["incompatible", "revoked", "no_scope", "unchanged", "forged_plan", "other_actor"])
def test_resource_selection_and_consent_cannot_be_bypassed(state, monkeypatch, fault):
    s = state
    calls = activation(s, monkeypatch)
    if fault == "incompatible":
        _, s.second = add_provider(s, device_id="dev_" + "7" * 32, smaller=True)
    if fault == "revoked":
        with Session(s.engine) as db, db.begin():
            db.get(Device, s.second_id).revoked_at = datetime.now(UTC)
    if fault == "no_scope":
        allow(s, consent_preview(s), scopes=[])
    if fault == "unchanged":
        with Session(s.engine) as db:
            s.second = db.get(Installation, 1).configuration["TARGET_DEVICE_ID"]
    if fault in {"forged_plan", "other_actor"}:
        plan = preview(s)
        if fault == "forged_plan":
            with Session(s.engine) as db, db.begin():
                row = db.get(Plan, plan["preview_id"])
                value = json.loads(row.payload)
                value["data"]["device_id"] = "dev_" + "8" * 32
                row.payload = json.dumps(value)
        else:
            with Session(s.engine) as db, db.begin():
                db.get(User, 2).role = "admin"
        with pytest.raises((AuthorityManagementError, rebind.authority.AuthorityReviewKeyError)):
            apply(s, plan, actor_token=s.user_token if fault == "other_actor" else s.token)
    else:
        with pytest.raises((AuthorityManagementError, ValueError)):
            preview(s)
    assert not calls
    with Session(s.engine) as db:
        assert db.get(Installation, 1).enabled


def test_old_unclaimed_work_is_fenced_and_cannot_execute_after_switch(state, monkeypatch):
    s = state
    old = submit(s, "never-claimed")
    with Session(s.engine) as db:
        delivered = deliver_next_command(db, device=db.get(Device, 1))
        assert delivered.command_id == old["command_id"]
    plan = preview(s)
    activation(s, monkeypatch)
    apply(s, plan)
    with Session(s.engine) as db:
        with pytest.raises(ValueError):
            commands.authorize_execution(db, db.get(Device, 1), old["command_id"])
    found = lookup(s, "never-claimed")["command"]
    assert not found["claimed"] and found["status"] == "invalidated" and found["execution_status"] == "failed"
    with pytest.raises(ValueError):
        submit(s, "never-claimed")


def test_recovery_during_late_activation_prevents_completion_from_overwriting_it(state, monkeypatch):
    s = state
    plan = preview(s)
    contexts = []
    def quiesce(self, instance_id, actor, context):
        contexts.append(context)
        return {"status": "disabled", "instance_id": instance_id, "lifecycle": context, "quiescent": True}
    monkeypatch.setattr(UpdateHelperClient, "recover_application_extension", quiesce)
    def during():
        current = rebind.status(s.manager, 1, plan_id=plan["preview_id"])
        rebind.recover(s.manager, 1, actor_token=s.token, preview_id=plan["preview_id"],
            expected_revision=current["revision"], confirmed_external_outcome_reviewed=True)
    calls = activation(s, monkeypatch, during)
    with pytest.raises(AuthorityManagementError, match="recovery_required"):
        apply(s, plan)
    assert len(contexts) == len(calls) == 1 and contexts[0]["epoch"] != calls[0]["epoch"]
    assert rebind.status(s.manager, 1, plan_id=plan["preview_id"])["state"] == "recovered_disabled"
    assert not s.manager.inspect(1)["grant_effective"]


def test_unconfirmed_recovery_stays_fenced_and_never_retries_same_ticket(state, monkeypatch):
    s = state
    plan = preview(s)
    monkeypatch.setattr(UpdateHelperClient, "activate_application_extension", lambda *a: {})
    with pytest.raises(AuthorityManagementError):
        apply(s, plan)
    pending = rebind.status(s.manager, 1, plan_id=plan["preview_id"])
    calls = []
    monkeypatch.setattr(UpdateHelperClient, "recover_application_extension", lambda *args: calls.append(args) or {})
    for _ in range(2):
        with pytest.raises(AuthorityManagementError):
            rebind.recover(s.manager, 1, actor_token=s.token, preview_id=plan["preview_id"],
                expected_revision=pending["revision"], confirmed_external_outcome_reviewed=True)
    assert len(calls) == 1
    assert rebind.status(s.manager, 1, plan_id=plan["preview_id"])["state"] == "recovery_required"
    with pytest.raises((ValueError, AuthorityManagementError)):
        submit(s, "unknown-recovery")


def test_shared_configuration_key_cannot_silently_change_another_binding(installed):
    s = installed
    Base.metadata.create_all(s.engine)
    definition = s.validated.application_extension.model_dump(mode="json")
    definition["command_bindings"].append({**deepcopy(definition["command_bindings"][0]), "binding_id": "second_pulse"})
    manifest = s.validated.manifest.model_dump(mode="json")
    output = io.BytesIO()
    with zipfile.ZipFile(s.archive) as previous, zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("application-extension.json", json.dumps(definition))
        archive.writestr(definition["service"]["artifact"], previous.read(definition["service"]["artifact"]))
    package = validate_module_package(output.getvalue())
    path = s.root / "modules" / (package.sha256 + ".zip")
    path.write_bytes(output.getvalue())
    with Session(s.engine) as db, db.begin():
        db.execute(update(ModulePackage).values(sha256=package.sha256, file_path=str(path), size_bytes=len(output.getvalue())))
    s.second_id, s.second = add_provider(s)
    allow(s, consent_preview(s), scopes=["command:pulse"])
    with pytest.raises(AuthorityManagementError, match="binding_change_not_isolated"):
        preview(s)


def test_rebinding_is_only_a_restart_of_an_active_installation(state, monkeypatch):
    s = state
    with Session(s.engine) as db, db.begin():
        app = db.get(Installation, 1)
        app.status, app.enabled = "disabled", False
    calls = activation(s, monkeypatch)
    with pytest.raises(AuthorityManagementError, match="installation_inactive"):
        preview(s)
    assert not calls


def test_pending_change_can_be_found_after_restart_without_writes(state, monkeypatch):
    from sqlalchemy import event
    s = state
    plan = preview(s)
    assert rebind.pending(s.manager, 1) == {"pending": None}
    class Crash(BaseException):
        pass
    monkeypatch.setattr(UpdateHelperClient, "activate_application_extension", lambda *a: (_ for _ in ()).throw(Crash()))
    with pytest.raises(Crash):
        apply(s, plan)
    statements = []
    def trace(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.lstrip().split()[0].upper())
    event.listen(s.engine, "before_cursor_execute", trace)
    try:
        manager = type(s.manager)(s.engine, uploads_root=s.root, core_version="0.3.0", review_key_directory=s.key_directory)
        observation = rebind.pending(manager, 1)["pending"]
    finally:
        event.remove(s.engine, "before_cursor_execute", trace)
    assert observation["preview_id"] == plan["preview_id"]
    assert observation["state"] == "applying" and observation["module_id"] == s.validated.manifest.module_id
    assert not observation["installation_enabled"] and observation["access"] == "not_evaluated"
    assert statements and set(statements) <= {"PRAGMA", "BEGIN", "SELECT", "ROLLBACK"}
    # A restored/replaced epoch must never expose a stale plan as recoverable.
    with Session(s.engine) as db, db.begin():
        db.get(Installation, 1).authority_epoch = identity()
    assert rebind.pending(manager, 1) == {"pending": None}


def test_current_pending_reader_requires_admin_and_returns_no_store(state, monkeypatch):
    s = state
    app = FastAPI()
    app.include_router(router)
    def database():
        with Session(s.engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    url = f"/api/v1/application-extensions/{s.validated.manifest.module_id}/authority/command-rebindings"
    with TestClient(app) as http:
        assert http.get(url).status_code == 401
        assert http.get(url, headers={"Authorization": "Bearer " + s.user_token}).status_code == 403
        result = http.get(url, headers={"Authorization": "Bearer " + s.token})
        assert result.status_code == 200 and result.json() == {"pending": None}
        assert result.headers["cache-control"] == "no-store"


def test_configuration_exposes_only_declared_command_requirements(vertical):
    s = vertical
    url = f"/api/v1/application-extensions/packages/{s.validated.sha256}/configuration"
    response = s.http.get(url, headers=s.headers)
    assert response.status_code == 200
    assert response.json()["command_bindings"] == [{"binding_id": "pulse", "target_device_config_key": "TARGET_DEVICE_ID",
        "capability_id": "gpio.digital.control", "contract_version": "1.0", "action": "pulse"}]
