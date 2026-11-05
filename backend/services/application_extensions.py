"""Generic Core gateway for active supervised application extensions."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import object_session

from backend.config import ApplicationRuntimeSettings
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.services.module_packages import ModulePackageError
from backend.services.application_code_scope import load_verified_package
from three_mm_protocol import ApplicationExtensionV1, ApplicationOperationV1
from three_mm_runtime.application_transport import ApplicationServiceClient
from three_mm_runtime.application_transport import ApplicationTransportError, DispatchPhase
from three_mm_protocol.diagnostics import REASONS as DIAGNOSTIC_REASONS


class ApplicationGatewayError(RuntimeError):
    def __init__(self, message, *, phase=DispatchPhase.EXECUTION_UNCONFIRMED, retryable=False,
                 diagnostic_reason='operation_failed'):
        super().__init__(message)
        self.phase = DispatchPhase(phase)
        self.retryable = retryable
        self.diagnostic_reason = (diagnostic_reason if type(diagnostic_reason) is str
            and diagnostic_reason in DIAGNOSTIC_REASONS else 'operation_failed')


def load_application_package(package: ModulePackage):
    try:
        validated = load_verified_package(package.file_path)
    except ModulePackageError as exc:
        raise ApplicationGatewayError(f"Application package is no longer valid: {exc}") from exc
    except OSError as exc:
        raise ApplicationGatewayError("Application package is no longer valid") from exc
    if validated.sha256 != package.sha256 or validated.application_extension is None:
        raise ApplicationGatewayError("Application package identity is invalid")
    return validated


def load_application_definition(package: ModulePackage) -> ApplicationExtensionV1:
    return load_application_package(package).application_extension


def find_operation(
    definition: ApplicationExtensionV1, operation_id: str
) -> ApplicationOperationV1:
    operation = next(
        (item for item in definition.operations if item.operation_id == operation_id),
        None,
    )
    if operation is None:
        raise ApplicationGatewayError("Application operation was not found")
    return operation


def _matches_type(value: object, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def validate_operation_payload(value: dict[str, object], schema: dict) -> None:
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    if required - set(value):
        raise ApplicationGatewayError("Application operation payload is incomplete")
    if schema.get("additionalProperties") is False and set(value) - set(properties):
        raise ApplicationGatewayError("Application operation payload has unknown fields")
    for key, item in value.items():
        field = properties.get(key)
        if not isinstance(field, dict):
            continue
        expected = field.get("type")
        if isinstance(expected, str) and not _matches_type(item, expected):
            raise ApplicationGatewayError(
                f"Application operation field '{key}' has an invalid type"
            )
        if isinstance(field.get("enum"), list) and item not in field["enum"]:
            raise ApplicationGatewayError(
                f"Application operation field '{key}' has an invalid value"
            )


@dataclass(frozen=True)
class PreparedApplicationInvocation:
    socket_path: Path
    secret: bytes
    timeout_seconds: float
    operation_id: str
    payload: dict
    context: dict
    relational_invocation: dict | None
    output_schema: dict
    expected_peer: tuple[int, int, str] | None = None
    needs_relational_invocation: bool = False


def invoke_application(installation, package, settings, operation_id, payload, context,
                       *, required_audience, before_dispatch=None):
    prepared = prepare_application_invocation(
        installation, package, settings, operation_id, payload, context,
        required_audience=required_audience, before_dispatch=before_dispatch)
    try:
        result = ApplicationServiceClient(prepared.socket_path, prepared.secret, prepared.timeout_seconds).invoke(
            prepared.operation_id, prepared.payload, prepared.context,
            **({'relational_invocation': prepared.relational_invocation}
               if prepared.relational_invocation is not None else {}))
    except ApplicationTransportError as exc:
        raise ApplicationGatewayError(str(exc), phase=exc.phase, retryable=exc.retryable) from exc
    validate_operation_payload(result, prepared.output_schema)
    if len(json.dumps(result, ensure_ascii=False)) > 1024 * 1024:
        raise ApplicationGatewayError('Application operation result is too large')
    return result


def prepare_application_invocation(
    installation: ApplicationExtensionInstallation,
    package: ModulePackage,
    settings: ApplicationRuntimeSettings,
    operation_id: str,
    payload: dict[str, object],
    context: dict[str, object],
    *,
    required_audience: str,
    before_dispatch=None,
    defer_relational=False,
    reviewed_public_http=False,
) -> PreparedApplicationInvocation:
    if not installation.enabled or installation.status != "active":
        raise ApplicationGatewayError("Application extension is not active")
    validated = load_application_package(package)
    definition = validated.application_extension
    operation = find_operation(definition, operation_id)
    if operation.kind == "job":
        raise ApplicationGatewayError("Scheduled application jobs are retired",
                                      phase=DispatchPhase.NOT_DISPATCHED)
    form_route = next((route for route in definition.public_http_routes if route.form_operation_id is not None
                       and operation_id in (route.handler_operation_id, route.form_operation_id)), None)
    is_form = form_route is not None and operation_id == form_route.form_operation_id
    public_context_fields = {'audience', 'correlation_id'} | ({'idempotency_key'} if is_form else set())
    if form_route is not None and form_route.guest_session:
        public_context_fields.add('public_guest')
    elif 'public_guest' in context:
        raise ApplicationGatewayError('Public guest context is reserved for reviewed forms',
                                      phase=DispatchPhase.NOT_DISPATCHED)
    if reviewed_public_http != (form_route is not None) or (form_route is not None and (
            required_audience != 'public' or context.get('audience') != 'public'
            or set(context) != public_context_fields)):
        raise ApplicationGatewayError('Public form command requires dedicated ingress',
                                      phase=DispatchPhase.NOT_DISPATCHED)
    if operation.kind == "task":
        from three_mm_protocol.application_tasks import TaskExecutionV1
        try:
            execution = TaskExecutionV1.model_validate(context.get("task_execution"))
            declaration = next(item for item in definition.tasks if item.task_id == execution.task_id)
            if (declaration.handler_operation_id != operation_id or context.get("audience") != "internal"
                    or context.get("idempotency_key") != execution.task_run_id):
                raise ValueError("Task handler changed")
        except (ValueError, StopIteration):
            raise ApplicationGatewayError("Task operations require a current execution context",
                phase=DispatchPhase.NOT_DISPATCHED) from None
    elif context.get("task_execution") is not None:
        raise ApplicationGatewayError("Task context is reserved for dedicated handlers", phase=DispatchPhase.NOT_DISPATCHED)
    if form_route is not None or any(
        route.handler_operation_id == operation_id
        for route in definition.public_http_routes
    ):
        # The reviewed profile has a dedicated ingress. Old public reads keep
        # the existing compatibility gate; an ORM cache cannot grant access.
        db = object_session(installation)
        mode = (
            db.scalar(
                select(ApplicationExtensionInstallation.authority_mode).where(
                    ApplicationExtensionInstallation.id == installation.id
                )
            )
            if db is not None
            else installation.authority_mode
        )
        if mode != ('enforced' if reviewed_public_http else 'compatibility'):
            raise ApplicationGatewayError(
                "Operation has no supported scoped resource grant",
                phase=DispatchPhase.NOT_DISPATCHED,
            )
    if required_audience not in operation.audiences:
        raise ApplicationGatewayError("Application operation is not available here")
    if required_audience == "public" and definition.storage.relational is not None:
        # Public routes have no scoped relational adapter. Refuse before any
        # host-metadata IPC; compatibility cannot obtain a relational grant.
        raise ApplicationGatewayError("Public HTTP has no supported relational grant",
                                      phase=DispatchPhase.NOT_DISPATCHED)
    if validated.compiled_ui is not None:
        from backend.services.compiled_ui import application_ui_artifact, CompiledUiBuildError
        db = object_session(installation)
        # Refuse unsupported entry paths above without UI filesystem/key I/O.
        # Compatibility keeps its legacy gateway, including old build outputs.
        mode = db.scalar(select(ApplicationExtensionInstallation.authority_mode).where(
            ApplicationExtensionInstallation.id == installation.id)) if db is not None else installation.authority_mode
        if mode != 'compatibility':
            try:
                application_ui_artifact(db, installation, validated)
            except CompiledUiBuildError as exc:
                raise ApplicationGatewayError(str(exc), phase=DispatchPhase.NOT_DISPATCHED) from exc
    idempotency_key = context.get("idempotency_key")
    if operation.idempotency == "required" and not isinstance(idempotency_key, str):
        raise ApplicationGatewayError("Application command requires an idempotency key")
    if operation.idempotency == "forbidden" and idempotency_key is not None:
        raise ApplicationGatewayError("Application query forbids an idempotency key")
    validate_operation_payload(payload, operation.input_schema)
    key_path = settings.key_root / f"{installation.instance_id}.key"
    try:
        secret = key_path.read_bytes()
    except OSError as exc:
        raise ApplicationGatewayError("Application transport key is unavailable",
            phase=DispatchPhase.NOT_DISPATCHED, retryable=True) from exc
    if len(secret) != 32:
        raise ApplicationGatewayError("Application transport key is invalid")
    # A durable admission callback may commit/expire ORM state. Keep the IPC
    # target paired with this key; do not lazily reload a changed installation
    # or hold a newly opened DB transaction across the service invocation.
    socket_path = Path(installation.socket_path)
    if before_dispatch is not None and not before_dispatch():
        raise ApplicationGatewayError('Application lifecycle changed', phase=DispatchPhase.NOT_DISPATCHED)
    needs_relational = False
    if definition.storage.relational is not None:
        if (
            context.get("audience") != required_audience
            or "relational_invocation" in context
        ):
            raise ApplicationGatewayError(
                "Relational operation context is invalid",
                phase=DispatchPhase.NOT_DISPATCHED,
            )
        needs_relational = operation_id != definition.service.health_operation_id
    prepared = PreparedApplicationInvocation(socket_path, secret, operation.timeout_seconds,
        operation_id, payload, context, None, operation.output_schema,
        needs_relational_invocation=needs_relational)
    if defer_relational or not needs_relational:
        return prepared
    return complete_application_preparation(object_session(installation), installation.id,
        prepared, required_audience=required_audience)


def complete_application_preparation(db, installation_id, prepared, *, required_audience):
    """Bounded metadata IPC, outside the UI key lease and caller DB snapshot.

    The host-metadata adapter independently checks its current resource grant.
    The relay rechecks human/code/lifecycle policy after this exchange, before
    dispatch. A ticket is not a SQL execution permit or cached authorization.
    """
    if not prepared.needs_relational_invocation:
        return prepared
    if db is None:
        raise ApplicationGatewayError('Relational invocation requires the Core authority session',
            phase=DispatchPhase.NOT_DISPATCHED)
    from backend.services.application_relational import RelationalAuthorityError, prepare_host_invocation
    try:
        ticket = prepare_host_invocation(db, installation_id, prepared.operation_id,
            required_audience=required_audience, transport_secret=prepared.secret)
    except RelationalAuthorityError as exc:
        raise ApplicationGatewayError(str(exc), phase=DispatchPhase.NOT_DISPATCHED) from exc
    return replace(prepared, relational_invocation=ticket, needs_relational_invocation=False)
