"""Retired execution stays unavailable; historical outcomes remain reviewable."""
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from backend.db.module import ApplicationJobState as State
from backend.services.module_packages import ModulePackageError, validate_module_package
from backend.services import application_extensions as gateway
from backend.tests.test_module_packages import application_definition, application_package
from three_mm_runtime.application_transport import DispatchPhase


@pytest.mark.parametrize("scheduled", [False, True])
def test_current_package_refuses_job_operations_even_without_schedule(scheduled):
    definition = application_definition()
    definition["operations"].append({"operation_id": "sync", "kind": "job",
        "audiences": ["internal"], "idempotency": "required"})
    if scheduled:
        definition["jobs"] = [{"job_id": "sync", "handler_operation_id": "sync", "interval_seconds": 60}]
    with pytest.raises(ModulePackageError, match="jobs are retired"):
        validate_module_package(application_package(definition=definition))


@pytest.mark.parametrize("mode", ["compatibility", "review_required", "enforced"])
def test_direct_gateway_cannot_dispatch_historical_job(monkeypatch, mode):
    definition = SimpleNamespace(operations=[SimpleNamespace(operation_id="sync",kind="job")])
    monkeypatch.setattr(gateway,"load_application_package",lambda package:SimpleNamespace(application_extension=definition))
    monkeypatch.setattr(gateway,"ApplicationServiceClient",lambda *a:pytest.fail("retired job reached service transport"))
    app=SimpleNamespace(enabled=True,status="active",authority_mode=mode)
    with pytest.raises(gateway.ApplicationGatewayError,match="jobs are retired") as error:
        gateway.invoke_application(app,object(),object(),"sync",{}, {},required_audience="internal")
    assert error.value.phase == DispatchPhase.NOT_DISPATCHED and not error.value.retryable


def test_resolution_requires_admin_confirmation_and_stopped_application(monkeypatch, tmp_path):
    from backend.tests.test_application_access import environment as access_environment, headers
    from backend.routes.application_operations import router
    from backend.db.audit_log import AuditLog
    client, db, engine, admin, operator, app, package, admin_token, user_token = access_environment(monkeypatch, tmp_path)
    client.app.include_router(router)
    state = State(application_installation_id=app.id, job_id='sync', next_run_at=datetime.now(UTC),
        lease_token='a'*32, last_outcome='unknown')
    db.add(state); db.commit()
    path = f'/api/v1/application-extensions/{app.module_id}/jobs/sync/resolve'
    body = {'confirmed_external_outcome_reviewed': True}
    try:
        assert client.post(path, json=body, headers=headers(user_token)).status_code == 403
        assert client.post(path, json=body, headers=headers(admin_token)).status_code == 409
        app.enabled = False; app.status = 'disabled'; db.commit()
        assert client.post(path, json={}, headers=headers(admin_token)).status_code == 422
        assert client.post(path, json=body, headers=headers(admin_token)).status_code == 200
        db.refresh(state)
        assert state.lease_token is None and state.last_outcome == 'resolved'
        assert db.scalar(select(AuditLog).where(AuditLog.action == 'APPLICATION_JOB_RESOLVED')) is not None
    finally:
        client.close(); db.close(); engine.dispose()
