"""Bounded task admission, leases and durable outcomes.

No timer, application execution, network wait or mutation retry runs in Core.
Every writer uses the existing authority guard. Claims are never dispatched twice.
"""
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import secrets
import time
import uuid

from sqlalchemy import select, func, distinct
from sqlalchemy.orm import Session
from backend.db.application_task import ApplicationTaskRun as Run
from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.services.authority_metadata import authority_transaction
from backend.services.application_authority_management import effect_admission, _clock
from backend.services.application_configuration import _validate_value
from backend.services.application_extensions import prepare_application_invocation, validate_operation_payload, ApplicationGatewayError
from three_mm_protocol.application_tasks import TaskSubmitV1, TaskLookupV1, TaskProgressV1, TaskExecutionV1
from three_mm_runtime.application_transport import sign_message, verify_message

LIVE = {"queued", "running", "unknown"}
MAX_RECORDS = 1024


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def now():
    return datetime.now(UTC)


def boot_id():
    return _clock()[0]


def lease_clock():
    return _clock()[1] / 1000  # Linux boot-monotonic clock includes suspend.


def _remaining(row):
    return min((utc(row.lease_until) - now()).total_seconds(), row.lease_monotonic - lease_clock())


def _definition(definition, task_id):
    declaration = next((item for item in definition.tasks if item.task_id == task_id), None)
    if declaration is None:
        raise ValueError("Task is not declared")
    operation = next(item for item in definition.operations if item.operation_id == declaration.handler_operation_id)
    return declaration, operation


def _derived(db, row, instant):
    if row.state not in {"queued", "running"}:
        return row.state, row.error_code
    app = db.get(Installation, row.installation_id, populate_existing=True)
    grant = db.get(Grant, row.installation_id, populate_existing=True)
    retired = (app is None or not app.enabled or app.status != "active"
        or app.module_package_id != row.package_id or app.authority_incarnation != row.incarnation
        or app.authority_epoch != row.authority_epoch or grant is None
        or grant.revision != row.grant_revision)
    if retired:
        return ("cancelled" if row.state == "queued" else "unknown" if row.dispatched else "failed"), "authority_changed"
    if row.state == "running" and (row.boot_id != boot_id() or row.lease_monotonic is None
            or lease_clock() >= row.lease_monotonic or utc(row.lease_until) <= instant):
        return ("unknown", "execution_unconfirmed") if row.dispatched else ("failed", "not_dispatched")
    if utc(row.not_after) <= instant:
        return ("expired" if row.state == "queued" else "unknown" if row.dispatched else "failed"), "deadline_exceeded"
    return row.state, row.error_code


def _snapshot(db, row, *, task_id=None, request_id=None):
    if row is None:
        return {"task_id": task_id, "request_id": request_id, "task_run_id": None,
            "status": "not_found", "progress": 0, "result": None, "error_code": None}
    state, error = _derived(db, row, now())
    return {"task_id": row.task_id, "request_id": row.request_id, "task_run_id": row.task_run_id,
        "status": state, "progress": row.progress, "result": row.result if state == "succeeded" else None, "error_code": error}


def _sweep(db, installation_id):
    for row in db.scalars(select(Run).where(Run.installation_id == installation_id, Run.state.in_({"queued", "running"}))):
        row.state, row.error_code = _derived(db, row, now())
    db.flush()


def require_quiescent_task_journal(db, installation_id):
    _sweep(db, installation_id)
    if db.scalar(select(Run.task_run_id).where(Run.installation_id==installation_id,
            Run.state.in_({"running","unknown"})).limit(1)) is not None:
        raise ValueError("Stop the application and resolve its outstanding task executions first")


@contextmanager
def _write(db):
    if db.new or db.dirty or db.deleted:
        raise ValueError("Task mutation requires a clean session")
    db.rollback()
    with authority_transaction(db):
        yield


def lookup_task(db, installation, payload):
    request = TaskLookupV1.model_validate(payload)
    row = db.scalar(select(Run).where(Run.installation_id == installation.id,
        Run.incarnation == installation.authority_incarnation, Run.task_id == request.task_id, Run.request_id == request.request_id))
    return _snapshot(db, row, task_id=request.task_id, request_id=request.request_id)


def submit_task(db, installation, payload):
    request = TaskSubmitV1.model_validate(payload)
    identifier = installation.id
    # Older native compatibility is not an admission route for this new profile.
    mode = db.scalar(select(Installation.authority_mode).where(Installation.id == identifier))
    if mode != "enforced":
        raise ValueError("Tasks require explicit current task consent")
    canonical = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(canonical.encode()) > 8192:
        raise ValueError("Task request exceeds its budget")
    fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
    db.rollback()
    with effect_admission(db, identifier, "task:" + request.task_id) as admission:
        task, operation = _definition(admission.definition, request.task_id)
        app = db.get(Installation, identifier, populate_existing=True)
        previous = db.scalar(select(Run).where(Run.installation_id == identifier,
            Run.incarnation == app.authority_incarnation, Run.task_id == request.task_id, Run.request_id == request.request_id))
        if previous is not None:
            if previous.request_hash != fingerprint:
                raise ValueError("Task request ID belongs to different input or timing")
            return _snapshot(db, previous)
        instant = now()
        if (request.due_at > instant + timedelta(seconds=task.max_delay_seconds)
                or request.not_after <= instant or request.not_after < request.due_at + timedelta(seconds=task.max_runtime_seconds)
                or request.not_after > request.due_at + timedelta(seconds=30)):
            raise ValueError("Task timing is outside the declared window")
        row = enqueue_task(db, app, task, operation, request_id=request.request_id,
            fingerprint=fingerprint, payload=request.payload, due_at=request.due_at, not_after=request.not_after)
        result = _snapshot(db, row)
        db.commit(); admission()
        return result


def enqueue_task(db, app, task, operation, *, request_id, fingerprint, payload, due_at, not_after, schedule_id=None):
    """One shared durable queue path, inside the caller's current authority lease."""
    _validate_value(payload, operation.input_schema, "task input")
    _sweep(db, app.id)
    owned = (Run.installation_id == app.id, Run.incarnation == app.authority_incarnation)
    count = db.scalar(select(func.count()).select_from(Run).where(*owned))
    pending = db.scalar(select(func.count()).select_from(Run).where(*owned, Run.task_id == task.task_id, Run.state.in_(LIVE)))
    owner_pending = db.scalar(select(func.count()).select_from(Run).where(*owned, Run.state.in_(LIVE)))
    if count >= MAX_RECORDS or pending >= task.max_pending or owner_pending >= 8:
        raise ValueError("Task journal or pending budget is full")
    live_owners = db.scalar(select(func.count(distinct(Run.installation_id))).where(Run.state.in_(LIVE)))
    own_live = db.scalar(select(Run.task_run_id).where(Run.installation_id == app.id, Run.state.in_(LIVE)).limit(1))
    if own_live is None and live_owners >= 32:
        raise ValueError("Task executor owner budget is full")
    grant = db.get(Grant, app.id)
    row = Run(task_run_id="task_" + uuid.uuid4().hex, installation_id=app.id,
        package_id=app.module_package_id, incarnation=app.authority_incarnation, authority_epoch=app.authority_epoch,
        grant_revision=grant.revision, task_id=task.task_id, request_id=request_id,
        request_hash=fingerprint, state="queued", payload=payload, due_at=due_at, not_after=not_after,
        progress=0, schedule_id=schedule_id)
    db.add(row); db.flush()
    return row


def require_task_effect(db, installation_id, execution, admission):
    """Check both sealed scopes and the live task immediately before an effect."""
    execution = TaskExecutionV1.model_validate(execution)
    row = db.get(Run, execution.task_run_id, populate_existing=True)
    task, _ = _definition(admission.definition, execution.task_id)
    if (task.profile != "bounded_task_v1" or "task:" + execution.task_id not in admission.approved_scopes
            or row is None or not row.started or not row.dispatched or row.installation_id != installation_id
            or row.task_id != execution.task_id or row.lease_token != execution.lease_token
            or _derived(db, row, now())[0] != "running"):
        raise ValueError("Task effect requires its current exact execution lease and task grant")
    return row


def require_task_command_permit(db, installation_id, run_id, admission):
    row = db.get(Run, run_id, populate_existing=True)
    if row is None:
        raise ValueError("Original task execution is unavailable")
    require_task_effect(db, installation_id, {"task_run_id": run_id,
        "task_id": row.task_id, "lease_token": row.lease_token}, admission)


def cancel_task(db, installation, payload):
    request = TaskLookupV1.model_validate(payload)
    identifier = installation.id
    incarnation = installation.authority_incarnation
    with _write(db):
        _sweep(db, identifier)
        row = db.scalar(select(Run).where(Run.installation_id == identifier,
            Run.incarnation == incarnation, Run.task_id == request.task_id, Run.request_id == request.request_id))
        if row is not None and row.state == "queued":
            row.state = "cancelled"
        return _snapshot(db, row, task_id=request.task_id, request_id=request.request_id)


def progress_task(db, installation, payload):
    request = TaskProgressV1.model_validate(payload)
    identifier = installation.id
    if db.scalar(select(Installation.authority_mode).where(Installation.id == identifier)) != "enforced":
        raise ValueError("Task progress requires current task consent")
    db.rollback()
    with effect_admission(db, identifier, "task:" + request.execution.task_id) as admission:
        row = db.get(Run, request.execution.task_run_id, populate_existing=True)
        if (row is None or not row.started or row.installation_id != identifier or row.task_id != request.execution.task_id
                or row.lease_token != request.execution.lease_token or _derived(db, row, now())[0] != "running"
                or request.progress < row.progress):
            raise ValueError("Task execution lease is not current")
        row.progress = request.progress
        result = _snapshot(db, row)
        db.commit(); admission()
        return result


def start_task(db, installation, payload):
    execution = TaskExecutionV1.model_validate(payload)
    owner = installation.id
    if db.scalar(select(Installation.authority_mode).where(Installation.id == owner)) != "enforced":
        raise ValueError("Task start requires current task consent")
    db.rollback()
    with effect_admission(db, owner, "task:" + execution.task_id) as admission:
        row = db.get(Run, execution.task_run_id, populate_existing=True)
        if (row is None or row.installation_id != owner or row.task_id != execution.task_id
                or not row.dispatched or row.started or row.lease_token != execution.lease_token
                or _derived(db, row, now())[0] != "running"):
            raise ValueError("Task start permit is expired, consumed or foreign")
        row.started = True
        receipt = {"task_run_id": row.task_run_id, "task_id": row.task_id, "lease_until": utc(row.lease_until).isoformat(),
            "lease_remaining_seconds": max(.000001, _remaining(row))}
        db.commit(); admission()
        return receipt


def claim_task(engine, *, settings, worker_generation):
    """Prepare filesystem inputs outside the guard; commit one dispatch before IPC."""
    with Session(engine) as db:
        ranked = select(Run.task_run_id, Run.due_at, func.row_number().over(partition_by=Run.installation_id,
            order_by=(Run.due_at, Run.task_run_id)).label("position")).where(Run.state == "queued", Run.due_at <= now()).subquery()
        candidates = list(db.scalars(select(ranked.c.task_run_id).where(ranked.c.position == 1)
            .order_by(ranked.c.due_at, ranked.c.task_run_id).limit(32)))
    for run_id in candidates:
        with Session(engine) as db:
            row = db.get(Run, run_id)
            if row is None:
                continue
            owner, task_id = row.installation_id, row.task_id
            # Persist expired/retired work without requiring withdrawn authority.
            with _write(db):
                _sweep(db, owner)
            row = db.get(Run, run_id, populate_existing=True)
            if row.state != "queued":
                continue
            app = db.get(Installation, owner)
            package = db.get(ModulePackage, app.module_package_id)
            from backend.services.application_extensions import load_application_definition
            definition = load_application_definition(package)
            task, operation = _definition(definition, task_id)
            token, invocation = secrets.token_hex(32), uuid.uuid4().hex
            context = {"audience": "internal", "correlation_id": "task:" + run_id, "idempotency_key": run_id,
                "task_execution": {"task_run_id": run_id, "task_id": task_id, "lease_token": token}}
            try:
                prepared = prepare_application_invocation(app, package, settings, operation.operation_id,
                    row.payload, context, required_audience="internal")
            except ApplicationGatewayError:
                continue  # One unavailable optional host must not block other owners.
            snapshot = (app.module_package_id, app.authority_incarnation, app.authority_epoch)
            db.rollback()
            try:
                with effect_admission(db, owner, "task:" + task_id) as admission:
                    _sweep(db, owner)
                    row = db.get(Run, run_id, populate_existing=True)
                    app = db.get(Installation, owner, populate_existing=True)
                    if (row.state != "queued" or utc(row.due_at) > now()
                            or snapshot != (app.module_package_id, app.authority_incarnation, app.authority_epoch)
                            or db.scalar(select(Run.task_run_id).where(Run.installation_id == owner,
                                Run.incarnation == app.authority_incarnation, Run.state.in_({"running", "unknown"})).limit(1)) is not None):
                        continue
                    row.state = "running"
                    row.lease_until = min(utc(row.not_after), now() + timedelta(seconds=task.max_runtime_seconds))
                    row.lease_monotonic, row.boot_id = lease_clock() + task.max_runtime_seconds, boot_id()
                    row.lease_token, row.worker_generation, row.invocation_id = token, worker_generation, invocation
                    row.output_schema = prepared.output_schema
                    frame = sign_message({"version": 1, "request_id": "meta_" + invocation, "timestamp": int(time.time()),
                        "operation_id": "three_mm.task.info", "payload": {}, "context": {"audience": "internal"}}, prepared.secret)
                    result = {"task_run_id": run_id, "lease_token": token, "socket_path": str(prepared.socket_path),
                        "timeout_seconds": max(.001, _remaining(row)), "request": frame}
                    db.commit(); admission()
                    return result
            except ValueError:
                db.rollback()  # Current grant unavailable: never dispatch via a fallback.
    return None


def dispatch_task(engine, *, settings, worker_generation, task_run_id, lease_token, response):
    """Validate the host proof outside the guard, then expose one signed invocation."""
    with Session(engine) as db:
        row = db.get(Run, task_run_id)
        if row is None:
            raise ValueError("Task is unavailable")
        owner, task_id = row.installation_id, row.task_id
        app = db.get(Installation, owner)
        if app is None:
            raise ValueError("Task owner is unavailable")
        package = db.get(ModulePackage, app.module_package_id)
        from backend.services.application_extensions import load_application_definition
        _, operation = _definition(load_application_definition(package), task_id)
        context = {"audience": "internal", "correlation_id": "task:" + task_run_id, "idempotency_key": task_run_id,
            "task_execution": {"task_run_id": task_run_id, "task_id": task_id, "lease_token": lease_token}}
        try:
            prepared = prepare_application_invocation(app, package, settings, operation.operation_id,
                row.payload, context, required_audience="internal")
        except ApplicationGatewayError:
            raise ValueError("Task artifact is unavailable") from None
        verify_message(response, prepared.secret, expected_request_id="meta_" + row.invocation_id)
        metadata = response.get("result")
        if (response.get("ok") is not True or not isinstance(metadata, dict)
                or type(metadata.get("task_execution_contract")) is not int or metadata["task_execution_contract"] != 1
                or metadata.get("instance_id") != app.instance_id or metadata.get("artifact_sha256") != package.sha256
                or metadata.get("module_id") != app.module_id
                or metadata.get("configuration_sha256") != hashlib.sha256(json.dumps(app.configuration or {},
                    sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()):
            raise ValueError("Application host does not support the live task start gate")
        snapshot = (app.module_package_id, app.authority_incarnation, app.authority_epoch)
        db.rollback()
        with effect_admission(db, owner, "task:" + task_id) as admission:
            row = db.get(Run, task_run_id, populate_existing=True)
            app = db.get(Installation, owner, populate_existing=True)
            if (row.worker_generation != worker_generation or row.lease_token != lease_token
                    or row.dispatched or _derived(db, row, now())[0] != "running"
                    or snapshot != (app.module_package_id, app.authority_incarnation, app.authority_epoch)):
                raise ValueError("Task dispatch is expired, consumed or foreign")
            row.dispatched = True
            frame = sign_message({"version": 1, "request_id": row.invocation_id, "timestamp": int(time.time()),
                "operation_id": prepared.operation_id, "payload": prepared.payload, "context": prepared.context}, prepared.secret)
            result = {"task_run_id": task_run_id, "lease_token": lease_token, "socket_path": str(prepared.socket_path),
                "timeout_seconds": max(.001, _remaining(row)), "request": frame}
            db.commit(); admission()
            return result


def finish_task(engine, *, key_root, worker_generation, task_run_id, lease_token, response=None):
    with Session(engine) as db, _write(db):
        row = db.get(Run, task_run_id, populate_existing=True)
        if (row is None or row.state != "running" or row.worker_generation != worker_generation
                or row.lease_token != lease_token):
            raise ValueError("Task receipt is stale or foreign")
        row.state, row.error_code = _derived(db, row, now())
        if row.state != "running":
            return _snapshot(db, row)
        row.state, row.error_code = ("unknown", "execution_unconfirmed") if row.dispatched else ("failed", "not_dispatched")
        if type(response) is dict:
            app = db.get(Installation, row.installation_id)
            secret = (Path(key_root) / (app.instance_id + ".key")).read_bytes()
            verify_message(response, secret)
            if (response.get("request_id") != row.invocation_id or type(response.get("ok")) is not bool
                    or type(response.get("version")) is not int or response["version"] != 1):
                raise ValueError("Task response identity is invalid")
            if response["ok"]:
                if not row.dispatched or not row.started:
                    raise ValueError("Task never consumed its start permit")
                value = response.get("result")
                if type(value) is not dict or len(json.dumps(value, allow_nan=False).encode()) > 8192:
                    raise ValueError("Task result is invalid")
                _validate_value(value, row.output_schema, "task result")
                validate_operation_payload(value, row.output_schema)
                row.result, row.progress, row.state, row.error_code = value, 100, "succeeded", None
            else:
                row.state, row.error_code = "failed", "handler_failed"
        # A signed handler reply cannot settle an already-issued physical effect.
        # Keep the owner blocked if its device result is still unconfirmed.
        from backend.db.application_command import ApplicationCommandRequest
        from backend.db.device import DeviceCommand
        commands = db.execute(select(ApplicationCommandRequest.claimed, DeviceCommand.status)
            .join(DeviceCommand, DeviceCommand.command_id == ApplicationCommandRequest.command_id)
            .where(ApplicationCommandRequest.task_run_id == row.task_run_id)).all()
        if any(claimed and status != "succeeded" for claimed, status in commands):
            row.state, row.result, row.error_code = "unknown", None, "execution_unconfirmed"
            row.progress = min(99, row.progress)
        elif commands and row.state == "succeeded" and any(status != "succeeded" for _, status in commands):
            row.state, row.result, row.error_code = "failed", None, "handler_failed"
            row.progress = min(99, row.progress)
        return _snapshot(db, row)
