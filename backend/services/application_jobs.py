"""Bounded discovery, database claims and per-installation job serialization."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
import threading
import time
import uuid

from sqlalchemy import select, update
from backend.db.module import ApplicationExtensionInstallation as Installation, ApplicationJobState as State, ModulePackage
from backend.services.application_extensions import ApplicationGatewayError, invoke_application, load_application_definition
from three_mm_runtime.application_transport import DispatchPhase

logger = logging.getLogger(__name__)
POLL_SECONDS = 1.0
LEASE_SECONDS = 60  # Above the maximum declared operation timeout (30 seconds).
MAX_WORKERS = 2


def _aware(value):
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


@dataclass(frozen=True)
class Claim:
    state_id: int
    installation_id: int
    package_id: int
    instance_id: str
    token: str
    scheduled_at: datetime
    job: object
    retry_delay: float = 5.0


def _active(claim):
    return (Installation.id == claim.installation_id, Installation.enabled.is_(True),
            Installation.status == 'active', Installation.module_package_id == claim.package_id,
            Installation.instance_id == claim.instance_id)


def discover_jobs(db, cache=None):
    cache = cache if cache is not None else {}
    rows = db.execute(select(Installation, ModulePackage).join(ModulePackage,
        ModulePackage.id == Installation.module_package_id).where(
        Installation.enabled.is_(True), Installation.status == 'active')).all()
    candidates = []
    states = {(s.application_installation_id, s.job_id): s for s in db.scalars(select(State))}
    for installation, package in rows:
        key = (package.id, package.sha256, package.file_path)
        try:
            if key not in cache:
                if len(cache) >= 128:
                    cache.clear()
                cache[key] = load_application_definition(package)
            definition = cache[key]
        except ApplicationGatewayError:
            continue
        for job in definition.jobs:
            state = states.get((installation.id, job.job_id))
            due = _aware(state.next_run_at) if state else datetime.min.replace(tzinfo=UTC)
            if state and state.lease_package_id is not None and state.lease_package_id != package.id:
                due = datetime.min.replace(tzinfo=UTC)
            candidates.append((due, installation.id, package.id, installation.instance_id, job))
    return sorted(candidates, key=lambda item: (item[0], item[1], item[4].job_id))


def claim_job(db, installation_id, package_id, instance_id, job, *, now=None):
    """The installation UPDATE locks before inspecting sibling jobs, across processes."""
    locked = db.execute(update(Installation).where(Installation.id == installation_id,
        Installation.enabled.is_(True), Installation.status == 'active',
        Installation.module_package_id == package_id, Installation.instance_id == instance_id)
        .values(updated_at=Installation.updated_at).execution_options(synchronize_session=False)).rowcount
    if not locked:
        db.rollback()
        return None
    current = now or datetime.now(UTC)
    occupied = list(db.scalars(select(State).where(State.application_installation_id == installation_id,
        State.lease_token.is_not(None)).execution_options(populate_existing=True)))
    for state in occupied:
        if state.last_outcome == 'running' and (state.lease_until is None or _aware(state.lease_until) <= current):
            state.last_outcome, state.last_error = 'unknown', 'lease_expired'
    if occupied:
        db.commit()
        return None  # Lease expiry never proves an external action did not execute.
    state = db.scalar(select(State).where(State.application_installation_id == installation_id,
        State.job_id == job.job_id).execution_options(populate_existing=True))
    existed = state is not None
    if state is None:
        state = State(application_installation_id=installation_id, job_id=job.job_id, next_run_at=current)
        db.add(state)
        db.flush()
    waiting = state.last_outcome == 'waiting_service' and state.lease_package_id == package_id and state.lease_instance_id == instance_id
    retry_delay = 5.0
    if waiting and state.last_completed_at is not None:
        retry_delay = min(30.0, max(5.0, 2 * (_aware(state.next_run_at) - _aware(state.last_completed_at)).total_seconds()))
    if state.lease_package_id is not None and state.lease_package_id != package_id:
        state.next_run_at = current
        existed = False
    scheduled = _aware(state.next_run_at)
    if scheduled > current:
        db.commit()
        return None
    if existed and not waiting and job.catch_up == 'skip' and current - scheduled >= timedelta(seconds=job.interval_seconds):
        state.next_run_at = current + timedelta(seconds=job.interval_seconds)
        state.last_outcome = 'skipped'
        db.commit()
        return None
    if waiting and state.last_scheduled_at is not None:
        scheduled = _aware(state.last_scheduled_at)
    token = uuid.uuid4().hex
    state.lease_token, state.lease_instance_id, state.lease_package_id = token, instance_id, package_id
    state.lease_until = current + timedelta(seconds=LEASE_SECONDS)
    state.last_scheduled_at = scheduled
    state.last_started_at = None
    state.last_outcome, state.last_error = 'running', None
    state.last_duration_ms = state.last_lateness_ms = None
    db.commit()
    return Claim(state.id, installation_id, package_id, instance_id, token, scheduled, job, retry_delay)


def execute_job(db, settings, claim, *, stop=None, now=None):
    mark = time.monotonic()
    active = db.execute(update(Installation).where(*_active(claim))
        .values(updated_at=Installation.updated_at).execution_options(synchronize_session=False)).rowcount
    state = db.get(State, claim.state_id, populate_existing=True)
    started = now or datetime.now(UTC)
    if state is None or state.lease_token != claim.token:
        db.rollback()
        return
    if not active or (stop is not None and stop.is_set()):
        db.execute(update(State).where(State.id == claim.state_id, State.lease_token == claim.token)
            .values(lease_token=None, lease_until=None, last_outcome='cancelled', last_error='lifecycle_changed'))
        db.commit()
        return
    if state.last_outcome != 'running' or state.lease_until is None or _aware(state.lease_until) <= started:
        state.last_outcome, state.last_error = 'unknown', 'lease_expired'
        db.commit()
        return
    installation = db.get(Installation, claim.installation_id, populate_existing=True)
    package = db.get(ModulePackage, claim.package_id)
    # Freeze the validated target before releasing the lifecycle row lock.
    db.expunge(installation)
    db.expunge(package)
    state.last_started_at = started
    state.last_lateness_ms = max(0, int((started - claim.scheduled_at).total_seconds() * 1000))
    db.commit()
    outcome, error = 'succeeded', None
    def still_owned_and_active():
        # Use a fresh transaction after readiness, not the detached snapshot.
        db.rollback()
        return not (stop is not None and stop.is_set()) and db.scalar(select(State.id).where(
            State.id == claim.state_id, State.lease_token == claim.token,
            State.last_outcome == 'running', State.lease_until > datetime.now(UTC),
            select(Installation.id).where(*_active(claim)).exists())) is not None
    try:
        invoke_application(installation, package, settings, claim.job.handler_operation_id, {}, {
            'audience': 'internal', 'correlation_id': f'job:{claim.instance_id}:{claim.job.job_id}',
            'idempotency_key': f'job:{claim.instance_id}:{claim.job.job_id}:{claim.scheduled_at.isoformat()}',
        }, required_audience='internal', require_ready=True, before_dispatch=still_owned_and_active)
    except ApplicationGatewayError as exc:
        if exc.phase == DispatchPhase.NOT_DISPATCHED:
            outcome, error = ('waiting_service', 'not_dispatched') if exc.retryable else ('cancelled', 'lifecycle_changed')
        else:
            outcome, error = 'unknown', 'execution_unconfirmed'
    except Exception:
        outcome, error = 'unknown', 'execution_unconfirmed'
    completed = now or datetime.now(UTC)
    next_run = claim.scheduled_at + timedelta(seconds=claim.job.interval_seconds)
    if next_run <= completed:
        next_run = completed + timedelta(seconds=claim.job.interval_seconds)
    if outcome == 'waiting_service':
        next_run = completed + timedelta(seconds=claim.retry_delay)
    values = dict(last_outcome=outcome, last_error=error, last_completed_at=completed,
        last_duration_ms=max(0, int((time.monotonic()-mark)*1000)), next_run_at=next_run)
    if outcome == 'succeeded':
        values.update(lease_token=None, lease_until=None, run_count=State.run_count + 1)
    elif outcome in {'waiting_service', 'cancelled'}:
        values.update(lease_token=None, lease_until=None)
    db.execute(update(State).where(State.id == claim.state_id, State.lease_token == claim.token).values(**values))
    db.commit()


def run_application_jobs(db, settings, *, now=None):
    """Synchronous compatibility entry; production uses separate pooled DB sessions."""
    for _, installation_id, package_id, instance_id, job in discover_jobs(db):
        claim = claim_job(db, installation_id, package_id, instance_id, job, now=now)
        if claim:
            execute_job(db, settings, claim, now=now)


class ApplicationJobScheduler:
    def __init__(self, settings, sessions=None):
        if sessions is None:
            from backend.database import SessionLocal
            sessions = SessionLocal
        self.settings, self.sessions = settings, sessions
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix='3mm-job')
        self.pending = {}
        self.cache = {}
        self.renewed = time.monotonic()

    def _execute(self, claim):
        with self.sessions() as db:
            execute_job(db, self.settings, claim, stop=self.stop)

    def tick(self):
        with self.lock:
            if self.stop.is_set():
                return POLL_SECONDS
            for future in list(self.pending):
                if future.done():
                    try:
                        future.result()
                    except Exception:
                        logger.warning('Application job worker failed; durable claim retained')
                    del self.pending[future]
            if self.pending and time.monotonic() - self.renewed >= 20:
                with self.sessions() as db:
                    for claim in self.pending.values():
                        db.execute(update(State).where(State.id == claim.state_id,
                            State.lease_token == claim.token, State.last_outcome == 'running')
                            .values(lease_until=datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)))
                    db.commit()
                self.renewed = time.monotonic()
            delay = POLL_SECONDS
            if len(self.pending) < MAX_WORKERS:
                with self.sessions() as db:
                    for due, installation_id, package_id, instance_id, job in discover_jobs(db, self.cache):
                        if len(self.pending) >= MAX_WORKERS or self.stop.is_set():
                            break
                        remaining = (due - datetime.now(UTC)).total_seconds()
                        if remaining > 0:
                            delay = min(delay, remaining)
                            continue
                        claim = claim_job(db, installation_id, package_id, instance_id, job)
                        if claim:
                            self.pending[self.pool.submit(self._execute, claim)] = claim
            return max(0.05, delay)

    def close(self):
        self.stop.set()
        with self.lock:
            self.pool.shutdown(wait=True, cancel_futures=True)
            with self.sessions() as db:
                for future, claim in self.pending.items():
                    if future.cancelled():
                        db.execute(update(State).where(State.id == claim.state_id, State.lease_token == claim.token)
                            .values(lease_token=None, lease_until=None, last_outcome='cancelled', last_error='lifecycle_changed'))
                db.commit()
