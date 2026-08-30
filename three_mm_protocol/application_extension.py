"""Strict contract for supervised business application extensions."""

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from three_mm_protocol.module_manifest import MODULE_ID_PATTERN, SEMVER_PATTERN
from three_mm_protocol.runtime_extension import IDENTIFIER_PATTERN, LocalizedTextV1


APPLICATION_EVENT_PATTERN = (
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
)
SHA256_PATTERN = r"^[0-9a-f]{64}$"
CONFIG_KEY_PATTERN = r"^[A-Z][A-Z0-9_]{1,63}$"
SERVICE_ENTRYPOINT_PATTERN = (
    r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$"
)

ApplicationAudience = Literal[
    "public",
    "kiosk",
    "operator",
    "administrator",
    "internal",
]


class StrictApplicationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _empty_object_schema() -> dict:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }


def _validate_object_schema(schema: dict, label: str) -> None:
    if len(json.dumps(schema, sort_keys=True)) > 64 * 1024:
        raise ValueError(f"{label} schema is too large")
    if schema.get("type") != "object":
        raise ValueError(f"{label} schema root must be an object")
    if schema.get("additionalProperties") is not False:
        raise ValueError(f"{label} schema must forbid additional properties")
    properties = schema.get("properties")
    required = schema.get("required", [])
    if not isinstance(properties, dict) or not isinstance(required, list):
        raise ValueError(f"{label} schema properties or required list is invalid")
    if len(required) != len(set(required)) or set(required) - set(properties):
        raise ValueError(f"{label} schema required fields are invalid")


class ApplicationServiceV1(StrictApplicationModel):
    artifact: str = Field(min_length=1, max_length=240)
    artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    entrypoint: str = Field(pattern=SERVICE_ENTRYPOINT_PATTERN, max_length=240)
    sdk_version: Literal["1.0"] = "1.0"
    health_operation_id: str = Field(pattern=IDENTIFIER_PATTERN)
    startup_timeout_seconds: int = Field(default=30, ge=1, le=120)
    shutdown_timeout_seconds: int = Field(default=15, ge=1, le=60)

    @model_validator(mode="after")
    def validate_artifact_path(self):
        normalized = self.artifact.replace("\\", "/")
        parts = normalized.split("/")
        if (
            normalized.startswith("/")
            or ".." in parts
            or not normalized.startswith("service/")
            or not normalized.endswith(".whl")
        ):
            raise ValueError(
                "application service artifact must be a safe wheel under service/"
            )
        return self


class ApplicationPermissionV1(StrictApplicationModel):
    permission_id: str = Field(pattern=IDENTIFIER_PATTERN)
    label: LocalizedTextV1
    description: LocalizedTextV1


class ApplicationOperationV1(StrictApplicationModel):
    operation_id: str = Field(pattern=IDENTIFIER_PATTERN)
    kind: Literal["query", "command", "job"]
    audiences: tuple[ApplicationAudience, ...] = Field(min_length=1, max_length=5)
    required_permission: str | None = Field(
        default=None,
        pattern=IDENTIFIER_PATTERN,
    )
    idempotency: Literal["forbidden", "required"]
    input_schema: dict = Field(default_factory=_empty_object_schema)
    output_schema: dict = Field(default_factory=_empty_object_schema)
    timeout_seconds: int = Field(default=10, ge=1, le=30)
    audit: Literal["metadata", "redacted"] = "metadata"
    emitted_events: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_operation_semantics(self):
        if len(self.audiences) != len(set(self.audiences)):
            raise ValueError("operation audiences must be unique")
        if "internal" in self.audiences and len(self.audiences) != 1:
            raise ValueError("internal operations cannot have another audience")
        if self.kind == "query" and self.idempotency != "forbidden":
            raise ValueError("query operations forbid idempotency keys")
        if self.kind in {"command", "job"} and self.idempotency != "required":
            raise ValueError("command and job operations require idempotency keys")
        if self.kind == "job" and self.audiences != ("internal",):
            raise ValueError("job operations must be internal")
        if "operator" in self.audiences and self.required_permission is None:
            raise ValueError("operator operations require an extension permission")
        if len(self.emitted_events) != len(set(self.emitted_events)):
            raise ValueError("emitted event types must be unique")
        _validate_object_schema(self.input_schema, "operation input")
        _validate_object_schema(self.output_schema, "operation output")
        for event_type in self.emitted_events:
            if not re.fullmatch(APPLICATION_EVENT_PATTERN, event_type):
                raise ValueError("emitted event type is invalid")
        return self


class ApplicationRouteV1(StrictApplicationModel):
    route_id: str = Field(pattern=IDENTIFIER_PATTERN)
    entrypoint_id: str = Field(pattern=IDENTIFIER_PATTERN)
    audience: Literal["public", "kiosk", "operator", "administrator"]
    required_permissions: tuple[str, ...] = ()
    layout: Literal["application", "kiosk"] = "application"
    navigation: bool = True
    order: int = Field(default=100, ge=0, le=10_000)

    @model_validator(mode="after")
    def validate_route_semantics(self):
        if len(self.required_permissions) != len(set(self.required_permissions)):
            raise ValueError("route permissions must be unique")
        if (self.layout == "kiosk") != (self.audience == "kiosk"):
            raise ValueError("kiosk layout is reserved for kiosk routes")
        if self.audience == "operator" and not self.required_permissions:
            raise ValueError("operator routes require an extension permission")
        return self


class ApplicationEventSubscriptionV1(StrictApplicationModel):
    subscription_id: str = Field(pattern=IDENTIFIER_PATTERN)
    event_type: str = Field(pattern=APPLICATION_EVENT_PATTERN, max_length=160)
    capability_id: str = Field(pattern=APPLICATION_EVENT_PATTERN, max_length=160)
    handler_operation_id: str = Field(pattern=IDENTIFIER_PATTERN)
    device_scope_config_key: str = Field(pattern=CONFIG_KEY_PATTERN)
    acknowledgement: Literal["after_commit"] = "after_commit"
    max_backlog: int = Field(default=1000, ge=1, le=100_000)


class ApplicationConnectorV1(StrictApplicationModel):
    connector_id: str = Field(pattern=IDENTIFIER_PATTERN)
    destination_config_key: str = Field(pattern=CONFIG_KEY_PATTERN)
    allowed_schemes: tuple[Literal["http", "https"], ...] = ("https",)
    path_prefix: str = Field(default="/", pattern=r"^/", max_length=160)
    authentication: Literal["none", "basic", "bearer", "api_key"] = "none"
    credential_ref_config_key: str | None = Field(
        default=None,
        pattern=CONFIG_KEY_PATTERN,
    )
    supports_mutations: bool = False
    timeout_seconds: int = Field(default=10, ge=1, le=30)
    max_request_bytes: int = Field(default=256 * 1024, ge=1024, le=4 * 1024 * 1024)
    max_response_bytes: int = Field(default=1024 * 1024, ge=1024, le=8 * 1024 * 1024)

    @model_validator(mode="after")
    def validate_connector_semantics(self):
        if len(self.allowed_schemes) != len(set(self.allowed_schemes)):
            raise ValueError("connector schemes must be unique")
        has_secret = self.credential_ref_config_key is not None
        if (self.authentication == "none") == has_secret:
            raise ValueError(
                "connector credentials are required exactly when authentication is enabled"
            )
        return self


class ApplicationJobV1(StrictApplicationModel):
    job_id: str = Field(pattern=IDENTIFIER_PATTERN)
    handler_operation_id: str = Field(pattern=IDENTIFIER_PATTERN)
    interval_seconds: int = Field(ge=5, le=31_536_000)
    catch_up: Literal["skip", "once"] = "once"
    singleton: Literal[True] = True


class ApplicationStorageV1(StrictApplicationModel):
    engine: Literal["sqlite"] = "sqlite"
    schema_revision: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")
    migration_entrypoint: str = Field(pattern=SERVICE_ENTRYPOINT_PATTERN, max_length=240)
    classifications: tuple[Literal["private", "secret"], ...] = ("private",)
    contains_personal_data: bool = False
    retention_operation_id: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    export_operation_id: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    erasure_operation_id: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    backup_required: Literal[True] = True

    @model_validator(mode="after")
    def validate_data_lifecycle(self):
        if len(self.classifications) != len(set(self.classifications)):
            raise ValueError("storage classifications must be unique")
        lifecycle = (
            self.retention_operation_id,
            self.export_operation_id,
            self.erasure_operation_id,
        )
        if self.contains_personal_data and any(item is None for item in lifecycle):
            raise ValueError(
                "personal data requires retention, export and erasure operations"
            )
        return self


class ApplicationLifecycleV1(StrictApplicationModel):
    disable_preserves_data: Literal[True] = True
    uninstall_requires_data_confirmation: Literal[True] = True
    rollback: Literal["transactional"] = "transactional"


class ApplicationExtensionV1(StrictApplicationModel):
    application_extension_version: Literal[1]
    module_id: str = Field(pattern=MODULE_ID_PATTERN)
    version: str = Field(pattern=SEMVER_PATTERN)
    service: ApplicationServiceV1
    permissions: tuple[ApplicationPermissionV1, ...] = Field(
        default=(),
        max_length=128,
    )
    operations: tuple[ApplicationOperationV1, ...] = Field(
        min_length=1,
        max_length=128,
    )
    routes: tuple[ApplicationRouteV1, ...] = Field(default=(), max_length=64)
    event_subscriptions: tuple[ApplicationEventSubscriptionV1, ...] = Field(
        default=(),
        max_length=64,
    )
    connectors: tuple[ApplicationConnectorV1, ...] = Field(
        default=(),
        max_length=32,
    )
    jobs: tuple[ApplicationJobV1, ...] = Field(default=(), max_length=64)
    storage: ApplicationStorageV1
    lifecycle: ApplicationLifecycleV1 = Field(default_factory=ApplicationLifecycleV1)

    @model_validator(mode="after")
    def validate_references(self):
        permission_ids = [item.permission_id for item in self.permissions]
        operation_ids = [item.operation_id for item in self.operations]
        route_ids = [item.route_id for item in self.routes]
        route_entrypoints = [item.entrypoint_id for item in self.routes]
        subscription_ids = [item.subscription_id for item in self.event_subscriptions]
        connector_ids = [item.connector_id for item in self.connectors]
        job_ids = [item.job_id for item in self.jobs]
        for label, values in (
            ("permission IDs", permission_ids),
            ("operation IDs", operation_ids),
            ("route IDs", route_ids),
            ("route entrypoints", route_entrypoints),
            ("subscription IDs", subscription_ids),
            ("connector IDs", connector_ids),
            ("job IDs", job_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")

        known_permissions = set(permission_ids)
        operations = {item.operation_id: item for item in self.operations}
        for operation in self.operations:
            if (
                operation.required_permission is not None
                and operation.required_permission not in known_permissions
            ):
                raise ValueError("operation references an unknown permission")
        for route in self.routes:
            if set(route.required_permissions) - known_permissions:
                raise ValueError("route references an unknown permission")

        health = operations.get(self.service.health_operation_id)
        if health is None or health.kind != "query" or health.audiences != ("internal",):
            raise ValueError("service health operation must be an internal query")
        health_status = health.output_schema.get("properties", {}).get("status")
        health_values = (
            set(health_status.get("enum", []))
            if isinstance(health_status, dict)
            else set()
        )
        if (
            "status" not in health.output_schema.get("required", [])
            or not health_values
            or not health_values <= {"ok", "ready"}
        ):
            raise ValueError(
                "service health output must declare status enum 'ok' or 'ready'"
            )

        for subscription in self.event_subscriptions:
            handler = operations.get(subscription.handler_operation_id)
            if (
                handler is None
                or handler.kind != "command"
                or handler.audiences != ("internal",)
            ):
                raise ValueError(
                    "event subscription handler must be an internal command"
                )

        for job in self.jobs:
            handler = operations.get(job.handler_operation_id)
            if handler is None or handler.kind != "job":
                raise ValueError("scheduled job handler must reference a job operation")

        for operation_id in (
            self.storage.retention_operation_id,
            self.storage.export_operation_id,
            self.storage.erasure_operation_id,
        ):
            if operation_id is not None and operation_id not in operations:
                raise ValueError("storage lifecycle references an unknown operation")

        for operation_id in (
            self.storage.export_operation_id,
            self.storage.erasure_operation_id,
        ):
            if operation_id is None:
                continue
            operation = operations[operation_id]
            if operation.kind != "command" or "administrator" not in operation.audiences:
                raise ValueError(
                    "data export and erasure must be administrator commands"
                )
        if self.storage.retention_operation_id is not None:
            retention = operations[self.storage.retention_operation_id]
            if retention.kind != "job" or retention.audiences != ("internal",):
                raise ValueError("data retention must be an internal job")
        return self
