"""Owned schedule admission/cursor journal. Calendar polling runs in the worker."""
from datetime import timedelta
import hashlib
import json
import uuid

from sqlalchemy import select, func, distinct, delete
from sqlalchemy.orm import Session
from backend.db.application_task import ApplicationTaskSchedule as Schedule, ApplicationTaskRun as Run
from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services.application_authority_management import effect_admission
from backend.services import application_tasks as tasks
from backend.services.application_configuration import _validate_value
from three_mm_protocol.application_tasks import TaskScheduleCreateV1, TaskScheduleLookupV1
from three_mm_platform_wire.task_time import latest_occurrence, occurrence_count


def _state(db, row):
    if row.state != "active":
        return row.state, row.error_code
    app = db.get(Installation, row.installation_id, populate_existing=True)
    grant = db.get(Grant, row.installation_id, populate_existing=True)
    if (app is None or not app.enabled or app.status != "active" or app.module_package_id != row.package_id
            or app.authority_incarnation != row.incarnation or app.authority_epoch != row.authority_epoch
            or grant is None or grant.revision != row.grant_revision):
        return "cancelled", "authority_changed"
    if tasks.now() >= tasks.utc(row.end_at) or row.admitted >= row.max_occurrences:
        return "exhausted", None
    return "active", None


def _snapshot(db, row, *, task_id=None, request_id=None):
    if row is None:
        return {"task_id": task_id, "request_id": request_id, "schedule_id": None, "status": "not_found",
            "admitted": 0, "skipped": 0, "last_request_id": None, "last_due_at": None, "error_code": None}
    state, error = _state(db, row)
    return {"task_id": row.task_id, "request_id": row.request_id, "schedule_id": row.schedule_id,
        "status": state, "admitted": row.admitted, "skipped": row.skipped,
        "last_request_id": row.last_request_id,
        "last_due_at": tasks.utc(row.cursor_at).isoformat() if row.cursor_at else None, "error_code": error}


def _owned(db, app, request):
    return db.scalar(select(Schedule).where(Schedule.installation_id == app.id,
        Schedule.incarnation == app.authority_incarnation, Schedule.task_id == request.task_id,
        Schedule.request_id == request.request_id))


def lookup_schedule(db, installation, payload):
    request = TaskScheduleLookupV1.model_validate(payload)
    return _snapshot(db, _owned(db, installation, request), task_id=request.task_id, request_id=request.request_id)


def create_schedule(db, installation, payload):
    request = TaskScheduleCreateV1.model_validate(payload)
    identifier = installation.id
    if installation.authority_mode != "enforced":
        raise ValueError("Schedules require explicit current task authority")
    canonical = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(canonical.encode()) > 8192:
        raise ValueError("Schedule request exceeds its budget")
    fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
    db.rollback()
    with effect_admission(db, identifier, "task:" + request.task_id) as admission:
        task, operation = tasks._definition(admission.definition, request.task_id)
        if task.profile != "bounded_task_v1":
            raise ValueError("Periodic work requires the declared bounded task profile")
        app = db.get(Installation, identifier, populate_existing=True)
        previous = _owned(db, app, request)
        if previous is not None:
            if previous.request_hash != fingerprint:
                raise ValueError("Schedule request ID belongs to different input or rules")
            return _snapshot(db, previous)
        if request.end_at <= tasks.now() or request.start_at > tasks.now() + timedelta(seconds=task.max_delay_seconds):
            raise ValueError("Schedule horizon is outside the current declaration")
        _validate_value(request.payload, operation.input_schema, "task input")
        owned = (Schedule.installation_id == identifier, Schedule.incarnation == app.authority_incarnation)
        count = db.scalar(select(func.count()).select_from(Schedule).where(*owned))
        active = db.scalar(select(func.count()).select_from(Schedule).where(*owned, Schedule.state.in_({"active", "blocked"})))
        owners = db.scalar(select(func.count(distinct(Schedule.installation_id))).where(Schedule.state.in_({"active", "blocked"})))
        if count >= 128 or active >= 8 or not active and owners >= 32:
            raise ValueError("Schedule admission budget is full")
        row = Schedule(schedule_id="schedule_" + uuid.uuid4().hex, installation_id=identifier,
            package_id=app.module_package_id, incarnation=app.authority_incarnation, authority_epoch=app.authority_epoch,
            grant_revision=db.get(Grant, identifier).revision, task_id=request.task_id, request_id=request.request_id,
            request_hash=fingerprint, state="active", payload=request.payload, rule=request.rule.model_dump(mode="json"),
            start_at=request.start_at, end_at=request.end_at, start_window_seconds=request.start_window_seconds,
            max_occurrences=request.max_occurrences, history_limit=request.history_limit,
            checked_at=tasks.now(), admitted=0, skipped=0)
        db.add(row); db.flush()
        result = _snapshot(db, row)
        db.commit(); admission()
        return result


def cancel_schedule(db, installation, payload):
    """Monotone desired-state cancellation; never recalls an issued start/effect."""
    request = TaskScheduleLookupV1.model_validate(payload)
    owner, incarnation = installation.id, installation.authority_incarnation
    with tasks._write(db):
        app = db.get(Installation, owner, populate_existing=True)
        if app is None or app.authority_incarnation != incarnation:
            raise ValueError("Schedule owner changed")
        row = _owned(db, app, request)
        if row is not None and row.state in {"active", "blocked", "exhausted"}:
            row.state, row.error_code = "cancelled", None
            for run in db.scalars(select(Run).where(Run.schedule_id == row.schedule_id, Run.state == "queued")):
                run.state = "cancelled"
        return _snapshot(db, row, task_id=request.task_id, request_id=request.request_id)


def poll_schedules(engine):
    """Bounded metadata for an authenticated optional worker, never app code."""
    with Session(engine) as db:
        identifiers=list(db.scalars(select(Schedule.schedule_id).where(Schedule.state=="active")
            .order_by(Schedule.checked_at,Schedule.schedule_id).limit(32)))
        if not identifiers:
            return []
        with tasks._write(db):
            return _poll_selected(db,identifiers)


def _poll_selected(db,identifiers):
    result = []
    for row in db.scalars(select(Schedule).where(Schedule.state == "active",Schedule.schedule_id.in_(identifiers))
            .order_by(Schedule.checked_at, Schedule.schedule_id).limit(32)):
        row.state, row.error_code = _state(db, row)
        row.checked_at = tasks.now()
        if row.state != "active":
            continue
        result.append({"schedule_id": row.schedule_id, "request_hash": row.request_hash, "rule": row.rule,
            "start_at": tasks.utc(row.start_at).isoformat(), "end_at": tasks.utc(row.end_at).isoformat(),
            "cursor_at": tasks.utc(row.cursor_at).isoformat() if row.cursor_at else None})
    return result


def _prune(db, row):
    """Only explicitly retained periodic history; manual requests never pruned.

    Occurrence request IDs use a reserved namespace not accepted by submit_task.
    The schedule cursor survives pruning, so an old occurrence cannot run again.
    """
    terminal = {"succeeded", "failed", "expired", "cancelled", "resolved"}
    old = list(db.scalars(select(Run.task_run_id).where(Run.schedule_id == row.schedule_id, Run.state.in_(terminal))
        .order_by(Run.due_at.desc(), Run.task_run_id.desc()).offset(max(0, row.history_limit - 1))))
    if old:
        db.execute(delete(Run).where(Run.task_run_id.in_(old)))


def tick_schedule(engine, *, schedule_id, request_hash, due_at):
    # The worker computes the proposed occurrence. Core verifies it against the
    # immutable admitted rule and current time, then uses the SAME task journal.
    from three_mm_platform_wire.task_time import instant
    proposed = instant(due_at)
    with Session(engine) as db:
        row = db.get(Schedule, schedule_id)
        if row is None or row.request_hash != request_hash:
            raise ValueError("Schedule is unavailable or foreign")
        owner, task_id = row.installation_id, row.task_id
        db.rollback()
        with effect_admission(db, owner, "task:" + task_id) as admission:
            def finish():
                result = _snapshot(db, row)
                db.commit(); admission()
                return result
            row = db.get(Schedule, schedule_id, populate_existing=True)
            row.state, row.error_code = _state(db, row)
            if row.state != "active":
                return finish()
            candidate = latest_occurrence(row.rule, tasks.utc(row.start_at), tasks.utc(row.end_at), tasks.now())
            if candidate is None or proposed != candidate:
                raise ValueError("Worker occurrence is not the current admitted calendar instant")
            if row.cursor_at is not None and candidate <= tasks.utc(row.cursor_at):
                return finish()
            task, operation = tasks._definition(admission.definition, task_id)
            app = db.get(Installation, owner, populate_existing=True)
            tasks._sweep(db, owner)
            uncertain = db.scalar(select(Run.task_run_id).where(Run.installation_id == owner,
                Run.incarnation == app.authority_incarnation, Run.state == "unknown").limit(1))
            if uncertain is not None:
                row.state, row.error_code = "blocked", "execution_unconfirmed"
                return finish()
            total = occurrence_count(row.rule, tasks.utc(row.start_at),
                tasks.utc(row.cursor_at) if row.cursor_at else None, candidate)
            existing = db.scalar(select(Run.task_run_id).where(Run.schedule_id == schedule_id, Run.state.in_(tasks.LIVE)).limit(1))
            owner_pending = db.scalar(select(func.count()).select_from(Run).where(Run.installation_id == owner,
                Run.incarnation == app.authority_incarnation, Run.state.in_(tasks.LIVE)))
            late = tasks.now() - candidate > timedelta(seconds=row.start_window_seconds)
            deadline = min(candidate + timedelta(seconds=row.start_window_seconds + task.max_runtime_seconds), tasks.utc(row.end_at))
            row.cursor_at, row.checked_at = candidate, tasks.now()
            if late or existing is not None or owner_pending >= 8 or deadline < tasks.now() + timedelta(seconds=task.max_runtime_seconds):
                row.skipped += total
            else:
                _prune(db, row)
                count = db.scalar(select(func.count()).select_from(Run).where(Run.installation_id == owner,
                    Run.incarnation == app.authority_incarnation))
                if count >= tasks.MAX_RECORDS:
                    row.state, row.error_code = "blocked", "history_full"
                    row.skipped += total
                else:
                    request_id = "occ_" + uuid.uuid5(uuid.NAMESPACE_URL, schedule_id + ":" + candidate.isoformat()).hex
                    fingerprint = hashlib.sha256((row.request_hash + ":" + candidate.isoformat()).encode()).hexdigest()
                    tasks.enqueue_task(db, app, task, operation, request_id=request_id, fingerprint=fingerprint,
                        payload=row.payload, due_at=candidate, not_after=deadline, schedule_id=schedule_id)
                    row.admitted += 1; row.skipped += max(0, total - 1); row.last_request_id = request_id
                    if row.admitted >= row.max_occurrences:
                        row.state = "exhausted"
            return finish()
