"""Strict contract for supervised business application extensions."""

import base64
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from three_mm_protocol.module_manifest import MODULE_ID_PATTERN, SEMVER_PATTERN
from three_mm_protocol.runtime_extension import IDENTIFIER_PATTERN, LocalizedTextV1
from three_mm_protocol.application_commands import ApplicationCommandBindingV1


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
    "installation_bootstrap",
    "installation_peer",
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
    sdk_version: Literal["1.0", "1.1", "1.2", "1.3"] = "1.0"
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
    audiences: tuple[ApplicationAudience, ...] = Field(min_length=1, max_length=7)
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
        if {"installation_bootstrap", "installation_peer"} & set(self.audiences):
            if len(self.audiences) != 1 or self.kind != "command" or self.required_permission is not None or self.emitted_events:
                raise ValueError("Peer operations must be isolated commands without human permissions or events")
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



PUBLIC_HTTP_TEXT_CONTENT_TYPES = (
    "text/html; charset=utf-8",
    "text/plain; charset=utf-8",
    "text/css; charset=utf-8",
    "application/javascript; charset=utf-8",
    "application/json",
    "application/manifest+json",
    "application/xml",
    "text/xml; charset=utf-8",
    "application/rss+xml",
    "application/atom+xml",
)
PUBLIC_HTTP_BINARY_CONTENT_TYPES = (
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/avif",
    "image/gif",
    "image/svg+xml",
    "image/x-icon",
    "font/woff",
    "font/woff2",
    "application/pdf",
)
PUBLIC_HTTP_CONTENT_TYPES = PUBLIC_HTTP_TEXT_CONTENT_TYPES + PUBLIC_HTTP_BINARY_CONTENT_TYPES
PUBLIC_HTTP_MAX_BODY_BYTES = 512 * 1024
PUBLIC_HTTP_RESPONSE_HEADERS = frozenset({
    "cache-control",
    "content-language",
    "etag",
    "last-modified",
    "link",
    "vary",
})


def public_http_request_schema_v1() -> dict:
    return {
        "type": "object",
        "properties": {
            "method": {"type": "string", "enum": ["GET", "HEAD"]},
            "path": {"type": "string"},
            "path_params": {"type": "object"},
            "query": {"type": "object"},
            "headers": {"type": "object"},
        },
        "required": ["method", "path", "path_params", "query", "headers"],
        "additionalProperties": False,
    }


def public_http_response_schema_v1() -> dict:
    return {
        "type": "object",
        "properties": {
            "status": {
                "type": "integer",
                "enum": [200, 204, 304, 301, 302, 307, 308, 400, 403, 404, 405, 410, 429, 500, 503],
            },
            "content_type": {"type": "string", "enum": list(PUBLIC_HTTP_CONTENT_TYPES)},
            "headers": {"type": "object"},
            "body": {"type": "string"},
            "body_base64": {"type": "string"},
            "location": {"type": "string"},
        },
        "required": ["status", "headers"],
        "additionalProperties": False,
    }


class ApplicationPublicHttpRequestV1(StrictApplicationModel):
    method: Literal["GET", "HEAD"]
    path: str = Field(min_length=1, max_length=2048)
    path_params: dict[str, str] = Field(default_factory=dict, max_length=32)
    query: dict[str, tuple[str, ...]] = Field(default_factory=dict, max_length=64)
    headers: dict[str, str] = Field(default_factory=dict, max_length=8)

    @model_validator(mode="after")
    def validate_request_bounds(self):
        if not self.path.startswith("/") or any(char in self.path for char in ("\r", "\n", "\x00")):
            raise ValueError("public HTTP request path is invalid")
        for name, value in self.path_params.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name) or len(value) > 2048:
                raise ValueError("public HTTP path parameter is invalid")
        for name, values in self.query.items():
            if not name or len(name) > 128 or len(values) > 32:
                raise ValueError("public HTTP query is too large")
            if any(len(value) > 4096 for value in values):
                raise ValueError("public HTTP query value is too large")
        allowed_headers = {"accept", "accept-language", "if-none-match", "if-modified-since"}
        if set(self.headers) - allowed_headers:
            raise ValueError("public HTTP request contains an undeclared forwarded header")
        if any(len(value) > 4096 or "\r" in value or "\n" in value for value in self.headers.values()):
            raise ValueError("public HTTP request header is invalid")
        return self


class ApplicationPublicHttpResponseV1(StrictApplicationModel):
    status: Literal[200, 204, 304, 301, 302, 307, 308, 400, 403, 404, 405, 410, 429, 500, 503]
    content_type: Literal[
        "text/html; charset=utf-8",
        "text/plain; charset=utf-8",
        "text/css; charset=utf-8",
        "application/javascript; charset=utf-8",
        "application/json",
        "application/manifest+json",
        "application/xml",
        "text/xml; charset=utf-8",
        "application/rss+xml",
        "application/atom+xml",
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/avif",
        "image/gif",
        "image/svg+xml",
        "image/x-icon",
        "font/woff",
        "font/woff2",
        "application/pdf",
    ] | None = None
    headers: dict[str, str] = Field(default_factory=dict, max_length=16)
    body: str | None = Field(default=None, max_length=PUBLIC_HTTP_MAX_BODY_BYTES)
    body_base64: str | None = Field(default=None, max_length=700 * 1024)
    location: str | None = Field(default=None, max_length=2048)

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value):
        normalized: dict[str, str] = {}
        for name, item in value.items():
            key = name.lower()
            if key not in PUBLIC_HTTP_RESPONSE_HEADERS:
                raise ValueError("public HTTP response header is not allowed")
            if len(item) > 4096 or "\r" in item or "\n" in item:
                raise ValueError("public HTTP response header is invalid")
            if key in normalized:
                raise ValueError("public HTTP response headers must be unique")
            normalized[key] = item
        return normalized

    @model_validator(mode="after")
    def validate_response_semantics(self):
        redirects = {301, 302, 307, 308}
        payload_count = int(self.body is not None) + int(self.body_base64 is not None)
        if self.status in redirects:
            if self.location is None or payload_count or self.content_type is not None:
                raise ValueError("public HTTP redirects require only a location")
        elif self.location is not None:
            raise ValueError("public HTTP location is reserved for redirects")
        if self.status in {204, 304} and (payload_count or self.content_type is not None):
            raise ValueError("public HTTP no-body responses cannot contain content")
        if payload_count > 1:
            raise ValueError("public HTTP response must use one body encoding")
        if payload_count == 0 and self.content_type is not None:
            raise ValueError("public HTTP content type requires a body")
        if payload_count == 1 and self.content_type is None:
            raise ValueError("public HTTP body requires a content type")
        if self.body is not None:
            if self.content_type not in PUBLIC_HTTP_TEXT_CONTENT_TYPES:
                raise ValueError("public HTTP text body requires a text content type")
            if len(self.body.encode("utf-8")) > PUBLIC_HTTP_MAX_BODY_BYTES:
                raise ValueError("public HTTP response body is too large")
        if self.body_base64 is not None:
            if self.content_type not in PUBLIC_HTTP_BINARY_CONTENT_TYPES:
                raise ValueError("public HTTP binary body requires a binary content type")
            try:
                decoded = base64.b64decode(self.body_base64, validate=True)
            except (ValueError, TypeError) as exc:
                raise ValueError("public HTTP binary body is invalid") from exc
            if len(decoded) > PUBLIC_HTTP_MAX_BODY_BYTES:
                raise ValueError("public HTTP response body is too large")
        if self.location is not None and ("\r" in self.location or "\n" in self.location):
            raise ValueError("public HTTP redirect location is invalid")
        return self


class ApplicationPublicHttpRouteV1(StrictApplicationModel):
    route_id: str = Field(pattern=IDENTIFIER_PATTERN)
    path: str = Field(min_length=1, max_length=240)
    methods: tuple[Literal["GET", "HEAD"], ...] = ("GET", "HEAD")
    handler_operation_id: str = Field(pattern=IDENTIFIER_PATTERN)
    content_types: tuple[Literal[
        "text/html; charset=utf-8",
        "text/plain; charset=utf-8",
        "text/css; charset=utf-8",
        "application/javascript; charset=utf-8",
        "application/json",
        "application/manifest+json",
        "application/xml",
        "text/xml; charset=utf-8",
        "application/rss+xml",
        "application/atom+xml",
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/avif",
        "image/gif",
        "image/svg+xml",
        "image/x-icon",
        "font/woff",
        "font/woff2",
        "application/pdf",
    ], ...] = Field(min_length=1, max_length=20)
    max_response_bytes: int = Field(default=256 * 1024, ge=1024, le=PUBLIC_HTTP_MAX_BODY_BYTES)

    @field_validator("path")
    @classmethod
    def validate_path_template(cls, value):
        if not value.startswith("/") or "//" in value or "\\" in value or "%" in value or "?" in value or "#" in value:
            raise ValueError("public HTTP route path is invalid")
        if value == "/":
            return value
        if value.endswith("/"):
            raise ValueError("public HTTP route path cannot end with a slash")
        parameters: list[str] = []
        for segment in value.split("/")[1:]:
            if segment in {"", ".", ".."}:
                raise ValueError("public HTTP route path contains an invalid segment")
            match = re.fullmatch(r"\{([a-z][a-z0-9_]{0,63})\}", segment)
            if match:
                parameters.append(match.group(1))
            elif "{" in segment or "}" in segment or any(ord(char) < 32 or char.isspace() for char in segment):
                raise ValueError("public HTTP route path contains an invalid segment")
        if len(parameters) != len(set(parameters)):
            raise ValueError("public HTTP route parameters must be unique")
        return value

    @model_validator(mode="after")
    def validate_route_semantics(self):
        if not self.methods or "GET" not in self.methods or len(self.methods) != len(set(self.methods)):
            raise ValueError("public HTTP routes require one GET method and unique methods")
        if len(self.content_types) != len(set(self.content_types)):
            raise ValueError("public HTTP route content types must be unique")
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


class ApplicationPeerReceiverV1(StrictApplicationModel):
    peer_version: Literal[1, 2] = 1
    bootstrap_operation_id: str = Field(pattern=IDENTIFIER_PATTERN)
    report_operation_id: str = Field(pattern=IDENTIFIER_PATTERN)

    @field_validator("peer_version", mode="before")
    @classmethod
    def integer_peer_version(cls, value):
        if type(value) is not int:
            raise ValueError("Peer version must be an integer")
        return value


class ApplicationExtensionV1(StrictApplicationModel):
    application_extension_version: Literal[1]
    module_id: str = Field(pattern=MODULE_ID_PATTERN)
    version: str = Field(pattern=SEMVER_PATTERN)
    service: ApplicationServiceV1
    platform_permissions: tuple[Literal[
        "installation.identity.read", "installation.identity.prove",
        "installation.peers.enroll", "installation.peers.receive",
        "installation.peers.report", "installation.status.read",
    ], ...] = Field(default=(), max_length=6)
    peer_receiver: ApplicationPeerReceiverV1 | None = None
    permissions: tuple[ApplicationPermissionV1, ...] = Field(
        default=(),
        max_length=128,
    )
    operations: tuple[ApplicationOperationV1, ...] = Field(
        min_length=1,
        max_length=128,
    )
    routes: tuple[ApplicationRouteV1, ...] = Field(default=(), max_length=64)
    public_http_routes: tuple[ApplicationPublicHttpRouteV1, ...] = Field(default=(), max_length=64)
    event_subscriptions: tuple[ApplicationEventSubscriptionV1, ...] = Field(
        default=(),
        max_length=64,
    )
    connectors: tuple[ApplicationConnectorV1, ...] = Field(
        default=(),
        max_length=32,
    )
    jobs: tuple[ApplicationJobV1, ...] = Field(default=(), max_length=64)
    command_bindings: tuple[ApplicationCommandBindingV1, ...] = Field(default=(), max_length=64)
    storage: ApplicationStorageV1
    lifecycle: ApplicationLifecycleV1 = Field(default_factory=ApplicationLifecycleV1)

    @model_validator(mode="after")
    def validate_references(self):
        if len(self.platform_permissions) != len(set(self.platform_permissions)):
            raise ValueError("platform permissions must be unique")
        if self.platform_permissions and self.service.sdk_version == "1.0":
            raise ValueError("installation identity permissions require SDK 1.1")
        peer_permissions = set(self.platform_permissions) - {"installation.identity.read", "installation.identity.prove"}
        peer_operations = [item for item in self.operations if {"installation_bootstrap", "installation_peer"} & set(item.audiences)]
        if (peer_permissions or self.peer_receiver or peer_operations) and self.service.sdk_version not in ("1.2", "1.3"):
            raise ValueError("Installation peer and projection contracts require SDK 1.2 or later")
        if self.peer_receiver and self.peer_receiver.peer_version == 2 and self.service.sdk_version != "1.3":
            raise ValueError("Proof-bound enrollment metadata requires SDK 1.3")
        permission_ids = [item.permission_id for item in self.permissions]
        operation_ids = [item.operation_id for item in self.operations]
        route_ids = [item.route_id for item in self.routes]
        public_http_route_ids = [item.route_id for item in self.public_http_routes]
        public_http_paths = [item.path for item in self.public_http_routes]
        route_entrypoints = [item.entrypoint_id for item in self.routes]
        subscription_ids = [item.subscription_id for item in self.event_subscriptions]
        connector_ids = [item.connector_id for item in self.connectors]
        job_ids = [item.job_id for item in self.jobs]
        for label, values in (
            ("permission IDs", permission_ids),
            ("operation IDs", operation_ids),
            ("route IDs", route_ids + public_http_route_ids),
            ("public HTTP paths", public_http_paths),
            ("route entrypoints", route_entrypoints),
            ("subscription IDs", subscription_ids),
            ("connector IDs", connector_ids),
            ("job IDs", job_ids),
            ("command bindings", [item.binding_id for item in self.command_bindings]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")

        known_permissions = set(permission_ids)
        operations = {item.operation_id: item for item in self.operations}
        for route in self.public_http_routes:
            operation = operations.get(route.handler_operation_id)
            if operation is None:
                raise ValueError("public HTTP route references an unknown operation")
            if operation.kind != "query" or operation.audiences != ("public",) or operation.idempotency != "forbidden":
                raise ValueError("public HTTP route handlers must be isolated public queries")
            if operation.input_schema != public_http_request_schema_v1():
                raise ValueError("public HTTP route handler must use the v1 request schema")
            if operation.output_schema != public_http_response_schema_v1():
                raise ValueError("public HTTP route handler must use the v1 response schema")
        if self.peer_receiver:
            if "installation.peers.receive" not in self.platform_permissions:
                raise ValueError("Peer receiver requires its platform permission")
            for operation_id, audience in (
                (self.peer_receiver.bootstrap_operation_id, "installation_bootstrap"),
                (self.peer_receiver.report_operation_id, "installation_peer"),
            ):
                operation = operations.get(operation_id)
                if operation is None or operation.audiences != (audience,):
                    raise ValueError("Peer receiver operations must declare their exact audience")
            if {item.operation_id for item in peer_operations} != {self.peer_receiver.bootstrap_operation_id, self.peer_receiver.report_operation_id}:
                raise ValueError("Only the two declared peer receiver operations are allowed")
            if self.peer_receiver.peer_version == 2:
                schema = operations[self.peer_receiver.bootstrap_operation_id].input_schema
                fields = {
                    "binding_id": "string", "installation_identity": "object",
                    "requested_scopes": "array", "enrollment_metadata": "object",
                }
                if (
                    not set(fields) <= set(schema.get("required", []))
                    or any(schema.get("properties", {}).get(name, {}).get("type") != kind
                           for name, kind in fields.items())
                ):
                    raise ValueError("Peer v2 bootstrap must declare verified enrollment metadata")
        elif peer_operations:
            raise ValueError("Peer operations require a receiver declaration")
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
