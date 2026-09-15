import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import UTC, datetime, timedelta
import threading
import time

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
import backend.database
from backend.config import ApplicationRuntimeSettings
from backend.db.base import Base
from backend.db.module import ApplicationExtensionInstallation as Installation, ApplicationJobState as State, ModulePackage
from backend.services import application_jobs as jobs
from backend.tests.test_application_jobs import job_definition


@pytest.fixture
def environment(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'jobs.db').as_posix()}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    definition = job_definition()
    definition = definition.model_copy(update={'jobs': (definition.jobs[0].model_copy(update={'interval_seconds': 5}),)})
    monkeypatch.setattr(jobs, 'load_application_definition', lambda package: definition)
    records = []
    with sessions() as db:
        for digit in ('1', '2'):
            package = ModulePackage(module_id=f'org.example.app{digit}', version='1.0.0', manifest={}, sha256=digit*64, size_bytes=1, file_path='unused', registrations=[])
            db.add(package); db.flush()
            app = Installation(module_id=package.module_id, module_package_id=package.id,
                instance_id=digit*24, active_version='1.0.0', enabled=True, status='active', socket_path='unused')
            db.add(app); db.flush()
            records.append((app.id, package.id, app.instance_id))
        db.commit()
    yield sessions, records, definition.jobs[0]
    engine.dispose()


def test_two_concurrent_claimers_and_long_running_lease(environment):
    sessions, records, job = environment
    barrier = threading.Barrier(2)
    def attempt():
        with sessions() as db:
            barrier.wait()
            return jobs.claim_job(db, *records[0], job)
    with ThreadPoolExecutor(2) as pool:
        first, second = pool.submit(attempt), pool.submit(attempt)
        claims = [c for c in (first.result(), second.result()) if c]
    assert len(claims) == 1
    with sessions() as db:
        assert jobs.claim_job(db, *records[0], job, now=datetime.now(UTC)+timedelta(seconds=7)) is None
        state = db.get(State, claims[0].state_id)
        assert state.last_outcome == 'running'
        assert jobs.claim_job(db, *records[0], job, now=datetime.now(UTC)+timedelta(seconds=61)) is None
        assert db.get(State, claims[0].state_id).last_outcome == 'unknown'
    # Another process/restart also cannot replay the expired claim.
    with sessions() as db:
        assert jobs.claim_job(db, *records[0], job) is None


@pytest.mark.parametrize('change', ['disable', 'upgrade', 'shutdown'])
def test_lifecycle_between_claim_and_execution_never_calls(environment, monkeypatch, change):
    sessions, records, job = environment
    calls = []
    monkeypatch.setattr(jobs, 'invoke_application', lambda *a, **k: calls.append(a))
    stop = threading.Event()
    with sessions() as db:
        claim = jobs.claim_job(db, *records[0], job)
        app = db.get(Installation, records[0][0])
        if change == 'disable': app.enabled = False
        if change == 'upgrade': app.module_package_id = records[1][1]
        if change == 'shutdown': stop.set()
        db.commit()
    with sessions() as db:
        jobs.execute_job(db, ApplicationRuntimeSettings(), claim, stop=stop)
        assert db.get(State, claim.state_id).last_outcome == 'cancelled'
    assert not calls


@pytest.mark.parametrize('policy', ['once', 'skip'])
def test_catchup_is_bounded_and_uses_stable_schedule(environment, monkeypatch, policy):
    sessions, records, job = environment
    job = job.model_copy(update={'catch_up': policy})
    now = datetime.now(UTC)
    scheduled = now - timedelta(days=1)
    calls = []
    monkeypatch.setattr(jobs, 'invoke_application', lambda *a, **k: calls.append(a) or {})
    with sessions() as db:
        db.add(State(application_installation_id=records[0][0], job_id=job.job_id, next_run_at=scheduled))
        db.commit()
        claim = jobs.claim_job(db, *records[0], job, now=now)
        if policy == 'skip':
            assert claim is None
        else:
            assert claim.scheduled_at == scheduled
            jobs.execute_job(db, ApplicationRuntimeSettings(), claim, now=now)
            assert scheduled.isoformat() in calls[0][5]['idempotency_key']
        assert jobs.claim_job(db, *records[0], job, now=now) is None


def test_timeout_is_redacted_and_never_automatically_retried(environment, monkeypatch):
    sessions, records, job = environment
    def fail(*a, **k): raise TimeoutError('private credential and payload')
    monkeypatch.setattr(jobs, 'invoke_application', fail)
    with sessions() as db:
        claim = jobs.claim_job(db, *records[0], job)
        jobs.execute_job(db, ApplicationRuntimeSettings(), claim)
        state = db.get(State, claim.state_id)
        assert state.last_outcome == 'unknown'
        assert state.last_error == 'execution_unconfirmed'
        assert state.last_duration_ms is not None
        assert jobs.claim_job(db, *records[0], job, now=datetime.now(UTC)+timedelta(hours=1)) is None


def test_sibling_jobs_serialize_and_new_package_does_not_inherit_old_delay(environment, monkeypatch):
    sessions, records, job = environment
    monkeypatch.setattr(jobs, 'invoke_application', lambda *a, **k: {})
    with sessions() as db:
        claim = jobs.claim_job(db, *records[0], job)
        assert jobs.claim_job(db, *records[0], job.model_copy(update={'job_id': 'other'})) is None
        jobs.execute_job(db, ApplicationRuntimeSettings(), claim)
        state = db.get(State, claim.state_id)
        state.next_run_at = datetime.now(UTC) + timedelta(days=1)
        app = db.get(Installation, records[0][0])
        app.module_package_id = records[1][1]
        db.commit()
        candidates = jobs.discover_jobs(db)
        due, installation_id, package_id, instance_id, discovered_job = next(c for c in candidates if c[1] == app.id)
        assert due <= datetime.now(UTC)
        assert jobs.claim_job(db, installation_id, package_id, instance_id, discovered_job) is not None


def test_real_main_worker_five_second_schedule_and_slow_app_isolation(environment, monkeypatch):
    import backend.main as main
    sessions, records, job = environment
    slow_started, release = threading.Event(), threading.Event()
    starts = []
    def invoke(app, *a, **k):
        if app.id == records[0][0]:
            slow_started.set()
            if not release.wait(9): raise RuntimeError('test release missing')
        else:
            starts.append(time.monotonic())
        return {}
    monkeypatch.setattr(jobs, 'invoke_application', invoke)
    scheduler = jobs.ApplicationJobScheduler(ApplicationRuntimeSettings(), sessions)
    monkeypatch.setattr(main, 'ApplicationJobScheduler', lambda settings: scheduler)
    async def scenario():
        worker = asyncio.create_task(main.run_application_job_worker())
        try:
            deadline = time.monotonic() + 7
            while len(starts) < 2 and time.monotonic() < deadline:
                await asyncio.sleep(0.05)
            assert slow_started.is_set()
            assert len(starts) == 2
            assert 4.5 <= starts[1] - starts[0] <= 6.1
            with sessions() as db:
                assert len(list(db.scalars(select(State).where(State.last_outcome == 'running')))) == 1
            scheduler.renewed -= 21
            await asyncio.to_thread(scheduler.tick)
        finally:
            release.set()
            worker.cancel()
            with suppress(asyncio.CancelledError): await worker
        assert scheduler.stop.is_set()
    asyncio.run(scenario())


def test_restore_invalidates_inflight_token_without_replay(environment, monkeypatch):
    from deployment import restore_application_extensions as restore
    sessions, records, job = environment
    with sessions() as db:
        claim = jobs.claim_job(db, *records[0], job)
        for app in db.scalars(select(Installation)):
            app.enabled = False
        db.commit()
        database = db.get_bind().url.database
    from pathlib import Path
    monkeypatch.setattr(restore, 'WANTS_ROOT', Path(database).parent / 'missing')
    restore.restore_application_extensions(Path(database), service_ids=(1, 1))
    with sessions() as db:
        state = db.get(State, claim.state_id)
        assert state.lease_token != claim.token
        assert state.last_error == 'restore_unconfirmed'
        app = db.get(Installation, records[0][0]); app.enabled = True; db.commit()
        assert jobs.claim_job(db, *records[0], job) is None


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
