"""Unsupported scoped entry paths must not reach legacy execution."""

import pytest
from datetime import UTC, datetime, timedelta
from sqlalchemy import select, update

from backend.config import ApplicationRuntimeSettings
from backend.db.module import (
    ApplicationExtensionInstallation as Installation,
    ApplicationJobState as State,
)
from backend.services import application_extensions as gateway
from backend.services import application_jobs as jobs
from backend.services import application_public_web as public_web
from backend.services.application_extensions import ApplicationGatewayError
from backend.tests.test_application_access import environment as access_environment
from backend.tests.test_application_job_scheduler import environment
from backend.tests.test_application_public_web import registry
from backend.tests.test_module_packages import application_package
from backend.tests.test_application_public_web import definition as public_definition
from three_mm_runtime.application_transport import DispatchPhase


@pytest.mark.parametrize("mode", ["enforced", "review_required"])
def test_scheduler_discovery_and_claim_refuse_unsupported_mode(environment, mode):
    sessions, records, job = environment
    with sessions() as db:
        # Leave a separate compatibility installation usable.
        db.execute(
            update(Installation)
            .where(Installation.id == records[0][0])
            .values(authority_mode=mode)
        )
        db.commit()
        assert [item[1] for item in jobs.discover_jobs(db)] == [records[1][0]]
        assert jobs.claim_job(db, *records[0], job) is None
        assert list(db.scalars(select(State))) == []


@pytest.mark.parametrize("mode", ["enforced", "review_required"])
def test_mode_change_after_claim_cancels_before_service_io(
    environment, monkeypatch, mode
):
    sessions, records, job = environment
    calls = []
    monkeypatch.setattr(jobs, "invoke_application", lambda *a, **k: calls.append(a))
    with sessions() as db:
        claim = jobs.claim_job(db, *records[0], job)
        db.execute(
            update(Installation)
            .where(Installation.id == records[0][0])
            .values(authority_mode=mode)
        )
        db.commit()
    with sessions() as db:
        jobs.execute_job(db, ApplicationRuntimeSettings(), claim)
        state = db.get(State, claim.state_id)
        assert state.last_outcome == "cancelled" and state.run_count == 0
        assert state.lease_token is None
    assert calls == []


def test_mode_change_during_readiness_is_fenced_by_existing_callback(
    environment, monkeypatch
):
    sessions, records, job = environment

    def invoke(*_args, **kwargs):
        with sessions() as other:
            other.execute(
                update(Installation)
                .where(Installation.id == records[0][0])
                .values(authority_mode="enforced")
            )
            other.commit()
        assert kwargs["before_dispatch"]() is False
        raise ApplicationGatewayError(
            "mode changed", phase=DispatchPhase.NOT_DISPATCHED
        )

    monkeypatch.setattr(jobs, "invoke_application", invoke)
    with sessions() as db:
        claim = jobs.claim_job(db, *records[0], job)
        jobs.execute_job(db, ApplicationRuntimeSettings(), claim)
        assert db.get(State, claim.state_id).last_outcome == "cancelled"


@pytest.mark.parametrize("outcome", ["unknown", "expired"])
def test_scoped_mode_change_cannot_release_uncertain_claim(
    environment, monkeypatch, outcome
):
    sessions, records, job = environment
    monkeypatch.setattr(
        jobs,
        "invoke_application",
        lambda *_a, **_k: pytest.fail("Uncertain job must not be invoked"),
    )
    with sessions() as db:
        claim = jobs.claim_job(db, *records[0], job)
        state = db.get(State, claim.state_id)
        if outcome == "unknown":
            state.last_outcome, state.last_error = "unknown", "execution_unconfirmed"
        else:
            state.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        db.execute(
            update(Installation)
            .where(Installation.id == records[0][0])
            .values(authority_mode="enforced")
        )
        db.commit()
    with sessions() as db:
        jobs.execute_job(db, ApplicationRuntimeSettings(), claim)
        state = db.get(State, claim.state_id)
        assert state.last_outcome == "unknown"
        assert state.lease_token == claim.token
        assert state.last_error == (
            "execution_unconfirmed" if outcome == "unknown" else "lease_expired"
        )
        # Even a later compatibility restart is not authority to replay it.
        db.execute(
            update(Installation)
            .where(Installation.id == records[0][0])
            .values(authority_mode="compatibility")
        )
        db.commit()
        assert jobs.claim_job(db, *records[0], job) is None


@pytest.mark.parametrize("mode", ["enforced", "review_required"])
def test_public_http_refuses_unsupported_mode_without_hiding_other_apps(
    registry, monkeypatch, mode
):
    db, add, _definitions = registry
    _, blocked, _ = add("org.example.scoped", "/scoped", 1)
    add("org.example.legacy", "/legacy", 2)
    blocked.authority_mode = mode
    db.commit()
    calls = []
    monkeypatch.setattr(
        public_web,
        "invoke_application",
        lambda *a, **k: calls.append(a)
        or {
            "status": 200,
            "content_type": "text/html; charset=utf-8",
            "body": "Legacy",
        },
    )
    with pytest.raises(public_web.ApplicationPublicWebError, match="scoped") as error:
        public_web.dispatch_public_http(
            db, ApplicationRuntimeSettings(), method="GET", path="/scoped"
        )
    assert error.value.status_code == 503
    assert calls == []
    assert (
        public_web.dispatch_public_http(
            db, ApplicationRuntimeSettings(), method="GET", path="/legacy"
        ).status
        == 200
    )
    assert len(calls) == 1


@pytest.mark.parametrize("mode", ["enforced", "review_required"])
@pytest.mark.parametrize("kind", ["job", "public_http"])
def test_direct_gateway_cannot_bypass_outer_gate(monkeypatch, tmp_path, mode, kind):
    blob = (
        application_package(
            definition=public_definition(
                "org.3mm.workflow-reference", "/scoped"
            ).model_dump(mode="json")
        )
        if kind == "public_http"
        else None
    )
    values = access_environment(monkeypatch, tmp_path, blob)
    client, db, engine, _, _, installation, package, *_ = values
    installation.authority_mode = mode
    db.commit()
    calls = []

    class Transport:
        def __init__(self, *_args):
            calls.append("constructed")

        def invoke(self, *_args, **_kwargs):
            calls.append("invoked")
            return {}

    monkeypatch.setattr(gateway, "ApplicationServiceClient", Transport)
    try:
        with pytest.raises(ApplicationGatewayError, match="scoped") as error:
            gateway.invoke_application(
                installation,
                package,
                gateway_settings(tmp_path),
                "sync_job" if kind == "job" else "render_public",
                {},
                {
                    "audience": "internal" if kind == "job" else "public",
                    "idempotency_key": "logical-job",
                },
                required_audience="internal" if kind == "job" else "public",
            )
        assert error.value.phase == DispatchPhase.NOT_DISPATCHED
        assert error.value.retryable is False
        assert calls == []
    finally:
        client.close()
        db.close()
        engine.dispose()


def gateway_settings(tmp_path):
    return ApplicationRuntimeSettings(key_root=tmp_path / "keys")


def test_direct_gateway_reloads_mode_not_cached_orm_state(monkeypatch, tmp_path):
    values = access_environment(monkeypatch, tmp_path)
    client, db, engine, _, _, installation, package, *_ = values
    db.expire_on_commit = False
    assert installation.authority_mode == "compatibility"
    db.execute(
        update(Installation)
        .values(authority_mode="enforced")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    assert installation.authority_mode == "compatibility"
    monkeypatch.setattr(
        gateway,
        "ApplicationServiceClient",
        lambda *_: pytest.fail("Transport must not be created"),
    )
    try:
        with pytest.raises(ApplicationGatewayError, match="scoped"):
            gateway.invoke_application(
                installation,
                package,
                gateway_settings(tmp_path),
                "sync_job",
                {},
                {"audience": "internal", "idempotency_key": "job-key"},
                required_audience="internal",
            )
    finally:
        client.close()
        db.close()
        engine.dispose()


def test_public_http_reloads_mode_after_route_resolution(registry, monkeypatch):
    db, add, _ = registry
    _, installation, _ = add("org.example.changed", "/changed", 1)
    db.expire_on_commit = False
    real_resolve = public_web.resolve_public_route

    def resolve_then_change(*args, **kwargs):
        result = real_resolve(*args, **kwargs)
        db.execute(
            update(Installation)
            .where(Installation.id == installation.id)
            .values(authority_mode="enforced")
            .execution_options(synchronize_session=False)
        )
        db.commit()
        assert installation.authority_mode == "compatibility"
        return result

    monkeypatch.setattr(public_web, "resolve_public_route", resolve_then_change)
    monkeypatch.setattr(
        public_web,
        "invoke_application",
        lambda *_a, **_k: pytest.fail("Public service must not be invoked"),
    )
    with pytest.raises(public_web.ApplicationPublicWebError, match="scoped"):
        public_web.dispatch_public_http(
            db, ApplicationRuntimeSettings(), method="GET", path="/changed"
        )
