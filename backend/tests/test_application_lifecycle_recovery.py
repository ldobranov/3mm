"""Explicit admin reconciliation; quiescence is not activation or job replay."""

import pytest
from pathlib import Path
from datetime import UTC, datetime
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session

from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationEventCursor, ApplicationExtensionInstallation, ApplicationJobState, ModulePackage
from backend.routes import application_extensions as routes
from backend.services.authority_metadata import read_application_authority, read_authority_guard
from backend.tests.test_application_lifecycle_authority import lifecycle, request, snapshot  # noqa: F401
from backend.utils.jwt_utils import create_access_token
from three_mm_runtime.update_helper_client import UpdateHelperError


CONFIRMED = {"confirmed_external_outcome_reviewed": True}


def pending(s, status="recovery_required"):
    with Session(s.engine) as db, db.begin():
        db.execute(update(ApplicationExtensionInstallation).values(status=status, enabled=False))


def recovery_helper(s, monkeypatch, *, result=None, fail=False):
    def recover(_self, instance_id, actor_id, context):
        assert not s.sessions[-1].in_transaction()
        assert instance_id == "a" * 24 and actor_id == 1
        s.calls.append("recovering")
        with Session(s.engine) as db:
            app = db.get(ApplicationExtensionInstallation, 1)
            owner = read_application_authority(db, 1)
            assert app.status == "recovering" and not app.enabled
            assert context == dict(installation_id=1, module_id=s.module_id,
                instance_id=instance_id, incarnation=owner.incarnation, epoch=owner.epoch,
                guard_generation=read_authority_guard(db).generation)
        if fail:
            raise UpdateHelperError("private-runtime-diagnostic")
        return (result if result is not None else
                dict(status="disabled", instance_id=instance_id, lifecycle=context, quiescent=True))
    monkeypatch.setattr(routes.UpdateHelperClient, "recover_application_extension", recover)


def recover(s, *, body=CONFIRMED, headers=None):
    return s.client.post(s.base + "/lifecycle/recover", headers=s.auth if headers is None else headers, json=body)


@pytest.mark.parametrize("status", ["activating", "disabling", "uninstalling", "recovering", "recovery_required"])
def test_recovery_commits_disabled_without_claiming_package_or_data_rollback(lifecycle, monkeypatch, status):
    s = lifecycle
    pending(s, status)
    with Session(s.engine) as db, db.begin():
        db.add(ApplicationJobState(application_installation_id=1, job_id="unknown-job",
            next_run_at=datetime.now(UTC),
            lease_token="f" * 32, last_outcome="unknown", last_error="execution_unconfirmed"))
    before = snapshot(s)
    recovery_helper(s, monkeypatch)
    response = recover(s)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "disabled" and not response.json()["enabled"]
    assert response.json()["active_version"] is None
    after = snapshot(s)
    assert after[0].revision == before[0].revision + 2
    assert after[1].incarnation == before[1].incarnation and after[1].epoch != before[1].epoch
    assert after[6] == before[6]  # No peer un-revocation or credential replacement.
    with Session(s.engine) as db:
        app = db.get(ApplicationExtensionInstallation, 1)
        assert app.module_package_id == 1 and app.configuration == s.body["configuration"]
        assert app.error is None and app.health_checked_at is None
        job = db.scalar(select(ApplicationJobState))
        assert job.lease_token == "f" * 32 and job.last_outcome == "unknown"
        assert db.scalar(select(ApplicationEventCursor.last_event_id)) == "event-keep"
        audit = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()))
        assert audit.action == "APPLICATION_EXTENSION_LIFECYCLE_RECOVERED"
        assert audit.changes["outcome"] == "stopped_disabled"
        assert "incarnation" not in str(audit.changes) and "configuration" not in str(audit.changes)
    # Once reconciled, another recovery is not a runtime retry.
    assert recover(s).status_code == 409 and snapshot(s) == after
    assert s.calls == ["recovering"]
    # Unknown jobs still prevent uninstall; no evidence gets silently erased.
    assert request(s, "uninstalling").status_code == 409


@pytest.mark.parametrize("status", ["active", "disabled", "staged"])
def test_recovery_does_not_replace_normal_lifecycle(lifecycle, monkeypatch, status):
    s = lifecycle
    pending(s, status)
    recovery_helper(s, monkeypatch)
    before = snapshot(s)
    assert recover(s).status_code == 409
    assert snapshot(s) == before and not s.calls


def test_recovery_requires_admin_and_explicit_review_confirmation(lifecycle, monkeypatch):
    s = lifecycle
    pending(s)
    recovery_helper(s, monkeypatch)
    before = snapshot(s)
    assert recover(s, headers={}).status_code == 401
    user = {"Authorization": f"Bearer {create_access_token('2', {'role': 'user'})}"}
    assert recover(s, headers=user).status_code == 403
    for body in ({}, {"confirmed_external_outcome_reviewed": False}, dict(CONFIRMED, enabled=True)):
        assert recover(s, body=body).status_code == 422
    assert snapshot(s) == before and not s.calls


@pytest.mark.parametrize("fail", [True, False])
def test_failure_or_unbound_runtime_evidence_remains_quarantined(lifecycle, monkeypatch, fail):
    s = lifecycle
    pending(s)
    recovery_helper(s, monkeypatch, fail=fail,
                    result=dict(status="disabled", instance_id="a" * 24, quiescent=True, lifecycle={}))
    assert recover(s).status_code == 409
    with Session(s.engine) as db:
        app = db.get(ApplicationExtensionInstallation, 1)
        assert app.status == "recovery_required" and not app.enabled
        assert "private" not in app.error
        assert db.scalar(select(AuditLog.action).order_by(AuditLog.id.desc())) == "APPLICATION_EXTENSION_LIFECYCLE_FAILED"
    assert s.calls == ["recovering"]


@pytest.mark.parametrize("phase", ["start", "completion"])
def test_recovery_audit_failure_never_partially_commits(lifecycle, monkeypatch, phase):
    s = lifecycle
    pending(s)
    recovery_helper(s, monkeypatch)
    before = snapshot(s)

    def reject(_conn, _cursor, statement, parameters, _context, _many):
        if statement.startswith("INSERT INTO audit_logs"):
            is_start = "APPLICATION_EXTENSION_LIFECYCLE_STARTED" in parameters
            if is_start == (phase == "start"):
                raise RuntimeError("audit unavailable")

    event.listen(s.engine, "before_cursor_execute", reject)
    try:
        assert recover(s).status_code == 500
    finally:
        event.remove(s.engine, "before_cursor_execute", reject)
    if phase == "start":
        assert snapshot(s) == before and not s.calls
    else:
        assert s.calls == ["recovering"]
        with Session(s.engine) as db:
            app = db.get(ApplicationExtensionInstallation, 1)
            assert app.status == "recovering" and not app.enabled


def test_old_activation_completion_cannot_overwrite_explicit_recovery(lifecycle, monkeypatch):
    s = lifecycle
    recovery_helper(s, monkeypatch)
    recovered = []

    def late(_self, *_args):
        s.helper("activating")(_self)
        assert recover(s).status_code == 200
        recovered.append(snapshot(s))
        return dict(s.result)

    monkeypatch.setattr(routes.UpdateHelperClient, "activate_application_extension", late)
    assert request(s, "activating").status_code == 409
    assert snapshot(s) == recovered[0]


def test_recovery_completion_cannot_overwrite_replaced_incarnation(lifecycle, monkeypatch):
    s = lifecycle
    pending(s)
    changed = []

    def late(_self, instance_id, actor_id, context):
        with Session(s.engine) as db, db.begin():
            db.execute(update(ApplicationExtensionInstallation).values(authority_incarnation="e" * 32))
        changed.append(snapshot(s))
        return dict(status="disabled", instance_id=instance_id, lifecycle=context, quiescent=True)

    monkeypatch.setattr(routes.UpdateHelperClient, "recover_application_extension", late)
    assert recover(s).status_code == 409
    assert snapshot(s) == changed[0]


def test_reconciled_app_can_be_explicitly_activated(lifecycle, monkeypatch):
    s = lifecycle
    pending(s)
    recovery_helper(s, monkeypatch)
    assert recover(s).status_code == 200
    monkeypatch.setattr(routes.UpdateHelperClient, "activate_application_extension", lambda *_args: dict(s.result))
    assert request(s, "activating").status_code == 200


def test_recovery_does_not_need_healthy_package_ui_or_application_transport(lifecycle, monkeypatch):
    s = lifecycle
    pending(s)
    with Session(s.engine) as db:
        archive = Path(db.get(ModulePackage, 1).file_path)
    archive.write_bytes(b'corrupt optional package')
    monkeypatch.setattr(routes, '_definition', lambda *_args: pytest.fail('Recovery loaded application code metadata'))
    recovery_helper(s, monkeypatch)
    response = recover(s)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'disabled'
    assert archive.read_bytes() == b'corrupt optional package'
    assert s.calls == ['recovering']


@pytest.mark.parametrize("status", ["activating", "disabling", "uninstalling", "recovering", "recovery_required"])
def test_remove_interrupted_first_install_quiesces_before_uninstall(lifecycle, monkeypatch, status):
    s = lifecycle
    pending(s, status)
    with Session(s.engine) as db, db.begin():
        db.execute(update(ApplicationExtensionInstallation).values(active_version=None, socket_path="pending"))
        package_path = db.get(ModulePackage, 1).file_path
    recovery_helper(s, monkeypatch)
    uninstall = s.helper("uninstalling")

    def remove(_self, instance_id, actor_id, context):
        assert s.calls == ["recovering"]
        assert instance_id == "a" * 24 and actor_id == 1
        with Session(s.engine) as db:
            app = db.get(ApplicationExtensionInstallation, 1)
            current = read_application_authority(db, 1)
            assert app.active_version is None and app.status == "uninstalling"
            assert context["epoch"] == current.epoch and context["incarnation"] == current.incarnation
            recovered = db.scalar(select(AuditLog).where(
                AuditLog.action == "APPLICATION_EXTENSION_LIFECYCLE_RECOVERED"))
            assert recovered.changes["requested_action"] == "uninstall"
            assert recovered.changes["external_outcome_reviewed"] is False
            assert recovered.changes["outcome"] == "stopped_for_removal"
            assert recovered.changes["data_preserved"] is True
        return uninstall(_self)

    monkeypatch.setattr(routes.UpdateHelperClient, "uninstall_application_extension", remove)
    response = request(s, "uninstalling")
    assert response.status_code == 200, response.text
    assert response.json() == dict(status="uninstalled", module_id=s.module_id,
                                   version=None, data_preserved=True)
    assert s.calls == ["recovering", "uninstalling"]  # Never activate or retry the failed package.
    with Session(s.engine) as db:
        assert db.get(ApplicationExtensionInstallation, 1) is None
        package = db.get(ModulePackage, 1)
        assert package is not None and package.file_path == package_path
        assert Path(package_path).is_file()
        audit = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()))
        assert audit.action == "APPLICATION_EXTENSION_UNINSTALLED" and audit.changes["data_preserved"] is True


@pytest.mark.parametrize("fault", ["failed", "wrong_instance", "wrong_ticket", "not_quiescent"])
def test_remove_interrupted_install_requires_bound_quiescence(lifecycle, monkeypatch, fault):
    s = lifecycle
    pending(s)
    with Session(s.engine) as db, db.begin():
        db.execute(update(ApplicationExtensionInstallation).values(active_version=None))

    def quiesce(_self, instance_id, actor_id, context):
        assert not s.sessions[-1].in_transaction()
        s.calls.append("recovering")
        if fault == "failed":
            raise UpdateHelperError("private-stop-diagnostic")
        result = dict(status="disabled", instance_id=instance_id, lifecycle=context, quiescent=True)
        if fault == "wrong_instance":
            result["instance_id"] = "b" * 24
        elif fault == "wrong_ticket":
            result["lifecycle"] = {}
        else:
            result["quiescent"] = False
        return result

    monkeypatch.setattr(routes.UpdateHelperClient, "recover_application_extension", quiesce)
    response = request(s, "uninstalling")
    assert response.status_code == 409 and "private" not in response.text
    assert s.calls == ["recovering"]
    with Session(s.engine) as db:
        app = db.get(ApplicationExtensionInstallation, 1)
        assert app.status == "recovery_required" and not app.enabled and app.active_version is None
        assert db.get(ModulePackage, 1) is not None
        assert db.scalar(select(AuditLog.action).order_by(AuditLog.id.desc())) == "APPLICATION_EXTENSION_LIFECYCLE_FAILED"


@pytest.mark.parametrize("status", ["activating", "disabling", "uninstalling", "recovering", "recovery_required"])
def test_remove_interrupted_install_preserves_unknown_job_claims_before_any_helper(lifecycle, monkeypatch, status):
    s = lifecycle
    pending(s, status)
    with Session(s.engine) as db, db.begin():
        db.add(ApplicationJobState(application_installation_id=1, job_id="uncertain-work",
            next_run_at=datetime.now(UTC), lease_token="e" * 32,
            last_outcome="unknown", last_error="execution_unconfirmed"))
    recovery_helper(s, monkeypatch)
    before = snapshot(s)
    response = request(s, "uninstalling")
    assert response.status_code == 409 and "job claims" in response.json()["detail"]
    assert not s.calls and snapshot(s) == before
    with Session(s.engine) as db:
        job = db.scalar(select(ApplicationJobState))
        assert job.lease_token == "e" * 32 and job.last_outcome == "unknown"
        assert db.get(ApplicationExtensionInstallation, 1) is not None


def test_remove_interrupted_install_requires_admin_before_quiescing(lifecycle, monkeypatch):
    s = lifecycle
    pending(s)
    recovery_helper(s, monkeypatch)
    before = snapshot(s)
    assert s.client.delete(s.base).status_code == 401
    headers = {"Authorization": f"Bearer {create_access_token('2', {'role': 'user'})}"}
    assert s.client.delete(s.base, headers=headers).status_code == 403
    assert not s.calls and snapshot(s) == before


def test_removal_recovery_cannot_delete_replaced_incarnation(lifecycle, monkeypatch):
    s = lifecycle
    pending(s)
    changed = []

    def replaced(_self, instance_id, actor_id, context):
        s.calls.append("recovering")
        with Session(s.engine) as db, db.begin():
            db.execute(update(ApplicationExtensionInstallation).values(authority_incarnation="d" * 32))
        changed.append(snapshot(s))
        return dict(status="disabled", instance_id=instance_id, lifecycle=context, quiescent=True)

    monkeypatch.setattr(routes.UpdateHelperClient, "recover_application_extension", replaced)
    assert request(s, "uninstalling").status_code == 409
    assert s.calls == ["recovering"] and snapshot(s) == changed[0]
    with Session(s.engine) as db:
        assert db.get(ApplicationExtensionInstallation, 1).authority_incarnation == "d" * 32


def test_delayed_activation_cannot_resurrect_explicitly_removed_installation(lifecycle, monkeypatch):
    s = lifecycle
    recovery_helper(s, monkeypatch)
    activation = s.helper("activating")

    def late(_self, *_args):
        activation(_self)
        response = request(s, "uninstalling")
        assert response.status_code == 200, response.text
        return dict(s.result)

    monkeypatch.setattr(routes.UpdateHelperClient, "activate_application_extension", late)
    response = request(s, "activating")
    assert response.status_code == 409
    assert s.calls == ["activating", "recovering", "uninstalling"]
    with Session(s.engine) as db:
        assert db.get(ApplicationExtensionInstallation, 1) is None
        assert db.get(ModulePackage, 1) is not None
        actions = list(db.scalars(select(AuditLog.action).order_by(AuditLog.id)))
        assert actions[-1] == "APPLICATION_EXTENSION_UNINSTALLED"
        assert "APPLICATION_EXTENSION_ACTIVATED" not in actions


@pytest.mark.parametrize("change", ["incarnation", "reactivated"])
def test_removal_pins_recovered_owner_and_state_across_quiescence_gap(lifecycle, monkeypatch, change):
    s = lifecycle
    pending(s)
    recovery_helper(s, monkeypatch)
    original = routes._recover_lifecycle
    changed = []

    def after_quiescence(*args, **kwargs):
        result = original(*args, **kwargs)
        assert kwargs["removing"] is True and s.calls == ["recovering"]
        with Session(s.engine) as db, db.begin():
            values = ({"authority_incarnation": "b" * 32} if change == "incarnation"
                      else {"status": "active", "enabled": True, "active_version": "2.0.0"})
            db.execute(update(ApplicationExtensionInstallation).values(**values))
        changed.append(snapshot(s))
        return result

    monkeypatch.setattr(routes, "_recover_lifecycle", after_quiescence)
    response = request(s, "uninstalling")
    assert response.status_code == 409
    assert s.calls == ["recovering"] and snapshot(s) == changed[0]
    with Session(s.engine) as db:
        app = db.get(ApplicationExtensionInstallation, 1)
        assert app is not None
        if change == "incarnation":
            assert app.authority_incarnation == "b" * 32
        else:
            assert app.status == "active" and app.enabled and app.active_version == "2.0.0"



def test_removal_rechecks_job_claims_after_quiescence(lifecycle, monkeypatch):
    s = lifecycle
    pending(s)
    recovery_helper(s, monkeypatch)
    original = routes._recover_lifecycle

    def late_claim(*args, **kwargs):
        result = original(*args, **kwargs)
        with Session(s.engine) as db, db.begin():
            db.add(ApplicationJobState(application_installation_id=1, job_id="late-uncertain-work",
                next_run_at=datetime.now(UTC), lease_token="d" * 32,
                last_outcome="unknown", last_error="execution_unconfirmed"))
        return result

    monkeypatch.setattr(routes, "_recover_lifecycle", late_claim)
    response = request(s, "uninstalling")
    assert response.status_code == 409 and "job claims" in response.json()["detail"]
    assert s.calls == ["recovering"]
    with Session(s.engine) as db:
        app = db.get(ApplicationExtensionInstallation, 1)
        assert app.status == "recovering" and not app.enabled
        job = db.scalar(select(ApplicationJobState))
        assert job.lease_token == "d" * 32 and job.last_outcome == "unknown"
        assert db.get(ModulePackage, 1) is not None



def test_removal_quiescence_never_opens_reactivation_window_when_late_claim_blocks_delete(lifecycle, monkeypatch):
    s = lifecycle
    pending(s)
    recovery_helper(s, monkeypatch)
    original = routes._recover_lifecycle

    def during_gap(*args, **kwargs):
        result = original(*args, **kwargs)
        with Session(s.engine) as db:
            app = db.get(ApplicationExtensionInstallation, 1)
            assert app.status == "recovering" and not app.enabled and app.active_version is None
            audit = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()))
            assert audit.changes["outcome"] == "stopped_for_removal"
            assert audit.changes["external_outcome_reviewed"] is False
        # Successful OS quiescence for removal does not acknowledge external
        # work or grant another caller permission to activate/disable/retry.
        assert request(s, "activating").status_code == 409
        assert request(s, "disabling").status_code == 409
        assert s.calls == ["recovering"]
        with Session(s.engine) as db, db.begin():
            db.add(ApplicationJobState(application_installation_id=1, job_id="unreviewed-late-work",
                next_run_at=datetime.now(UTC), lease_token="c" * 32,
                last_outcome="unknown", last_error="execution_unconfirmed"))
        return result

    monkeypatch.setattr(routes, "_recover_lifecycle", during_gap)
    response = request(s, "uninstalling")
    assert response.status_code == 409 and "job claims" in response.json()["detail"]
    before = snapshot(s)
    assert request(s, "activating").status_code == 409
    assert request(s, "disabling").status_code == 409
    assert snapshot(s) == before and s.calls == ["recovering"]
    with Session(s.engine) as db:
        app = db.get(ApplicationExtensionInstallation, 1)
        assert app.status == "recovering" and not app.enabled and app.active_version is None
        assert db.scalar(select(ApplicationJobState.lease_token)) == "c" * 32
        assert db.get(ModulePackage, 1) is not None
