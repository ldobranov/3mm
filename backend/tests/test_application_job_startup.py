from datetime import UTC, datetime, timedelta
import pytest
from sqlalchemy import select

from backend.tests.test_application_job_scheduler import environment
from backend.services import application_jobs as jobs
from backend.services.application_extensions import ApplicationGatewayError
from backend.db.module import ApplicationJobState as State, ApplicationExtensionInstallation as Installation
from backend.config import ApplicationRuntimeSettings
from three_mm_runtime.application_transport import DispatchPhase


def test_waiting_service_backoff_restart_and_original_identity(environment, monkeypatch):
    sessions, records, job = environment
    now = datetime.now(UTC)
    keys = []
    ready = False
    def invoke(*args, **kwargs):
        keys.append(args[5]['idempotency_key'])
        if not ready:
            raise ApplicationGatewayError('service unavailable', phase=DispatchPhase.NOT_DISPATCHED, retryable=True)
        return {}
    monkeypatch.setattr(jobs, 'invoke_application', invoke)
    first = None
    for expected_delay in (5, 10, 20, 30, 30):
        # A fresh DB session models restart; no in-memory retry counters are needed.
        with sessions() as db:
            claim = jobs.claim_job(db, *records[0], job, now=now)
            if first is None: first = claim
            assert claim.scheduled_at == first.scheduled_at
            jobs.execute_job(db, ApplicationRuntimeSettings(), claim, now=now)
            state = db.get(State, claim.state_id)
            assert state.last_outcome == 'waiting_service'
            assert state.last_error == 'not_dispatched' and state.lease_token is None
            assert jobs._aware(state.next_run_at) == now + timedelta(seconds=expected_delay)
            assert jobs.claim_job(db, *records[0], job, now=now) is None
        now += timedelta(seconds=expected_delay)
    ready = True
    with sessions() as db:
        claim = jobs.claim_job(db, *records[0], job, now=now)
        jobs.execute_job(db, ApplicationRuntimeSettings(), claim, now=now)
        assert db.get(State, claim.state_id).run_count == 1
    assert len(set(keys)) == 1


def test_not_dispatched_completion_does_not_release_foreign_claim(environment, monkeypatch):
    sessions, records, job = environment
    def invoke(*args, **kwargs):
        with sessions() as other:
            state = other.scalar(select(State))
            state.lease_token = 'f'*32
            other.commit()
        raise ApplicationGatewayError('not sent', phase=DispatchPhase.NOT_DISPATCHED, retryable=True)
    monkeypatch.setattr(jobs, 'invoke_application', invoke)
    with sessions() as db:
        claim = jobs.claim_job(db, *records[0], job)
        jobs.execute_job(db, ApplicationRuntimeSettings(), claim)
        state = db.get(State, claim.state_id)
        assert state.lease_token == 'f'*32 and state.last_outcome == 'running'


def test_untyped_failure_and_old_unknown_remain_quarantined(environment, monkeypatch):
    sessions, records, job = environment
    def invoke(*a, **k): raise ApplicationGatewayError('not_dispatched')
    monkeypatch.setattr(jobs, 'invoke_application', invoke)
    with sessions() as db:
        claim = jobs.claim_job(db, *records[0], job)
        jobs.execute_job(db, ApplicationRuntimeSettings(), claim)
        state = db.get(State, claim.state_id)
        assert state.last_outcome == 'unknown'
        assert jobs.claim_job(db, *records[0], job, now=datetime.now(UTC)+timedelta(days=2)) is None


@pytest.mark.parametrize('change', ['disabled', 'upgrade', 'stop'])
def test_readiness_callback_rechecks_lifecycle(environment, monkeypatch, change):
    import threading
    sessions, records, job = environment
    stop = threading.Event()
    def invoke(*a, **kwargs):
        with sessions() as other:
            app = other.get(Installation, records[0][0])
            if change == 'disabled': app.enabled = False
            if change == 'upgrade': app.module_package_id = records[1][1]
            if change == 'stop': stop.set()
            other.commit()
        assert not kwargs['before_dispatch']()
        raise ApplicationGatewayError('lifecycle changed', phase=DispatchPhase.NOT_DISPATCHED)
    monkeypatch.setattr(jobs, 'invoke_application', invoke)
    with sessions() as db:
        claim = jobs.claim_job(db, *records[0], job)
        jobs.execute_job(db, ApplicationRuntimeSettings(), claim, stop=stop)
        assert db.get(State, claim.state_id).last_outcome == 'cancelled'
