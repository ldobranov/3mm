"""Explicit admin reconciliation; quiescence is not activation or job replay."""

import pytest
from datetime import UTC, datetime
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session

from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationEventCursor, ApplicationExtensionInstallation, ApplicationJobState
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
