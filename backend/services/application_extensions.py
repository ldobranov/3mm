"""Generic Core gateway for active supervised application extensions."""

from __future__ import annotations

import json
from pathlib import Path

from backend.config import ApplicationRuntimeSettings
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.services.module_packages import ModulePackageError, validate_module_package
from three_mm_protocol import ApplicationExtensionV1, ApplicationOperationV1
from three_mm_runtime.application_transport import ApplicationServiceClient
from three_mm_runtime.application_transport import ApplicationTransportError


class ApplicationGatewayError(RuntimeError):
    pass


def load_application_definition(package: ModulePackage) -> ApplicationExtensionV1:
    try:
        validated = validate_module_package(Path(package.file_path).read_bytes())
    except (OSError, ModulePackageError) as exc:
        raise ApplicationGatewayError("Application package is no longer valid") from exc
    if validated.sha256 != package.sha256 or validated.application_extension is None:
        raise ApplicationGatewayError("Application package identity is invalid")
    return validated.application_extension


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


def invoke_application(
    installation: ApplicationExtensionInstallation,
    package: ModulePackage,
    settings: ApplicationRuntimeSettings,
    operation_id: str,
    payload: dict[str, object],
    context: dict[str, object],
    *,
    required_audience: str,
) -> dict[str, object]:
    if not installation.enabled or installation.status != "active":
        raise ApplicationGatewayError("Application extension is not active")
    definition = load_application_definition(package)
    operation = find_operation(definition, operation_id)
    if required_audience not in operation.audiences:
        raise ApplicationGatewayError("Application operation is not available here")
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
        raise ApplicationGatewayError("Application transport key is unavailable") from exc
    if len(secret) != 32:
        raise ApplicationGatewayError("Application transport key is invalid")
    try:
        result = ApplicationServiceClient(
            Path(installation.socket_path),
            secret,
            operation.timeout_seconds,
        ).invoke(operation_id, payload, context)
    except ApplicationTransportError as exc:
        raise ApplicationGatewayError(str(exc)) from exc
    validate_operation_payload(result, operation.output_schema)
    if len(json.dumps(result, ensure_ascii=False)) > 1024 * 1024:
        raise ApplicationGatewayError("Application operation result is too large")
    return result
