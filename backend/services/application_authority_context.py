"""Internal, pure review-context validation; never executable authority.

Only trusted Core adapters may supply these inputs. This module remains pure;
application_authority_management authenticates sealed records and current sources
before using it. A fingerprint is neither a signature nor a grant, and does not
prove resource/proof/clock freshness.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from three_mm_protocol.application_commands import ApplicationCommandBindingV1
from three_mm_protocol.application_event_publication import ApplicationEventPublicationV1
from three_mm_protocol.application_extension import (
    ApplicationConnectorV1, ApplicationEventSubscriptionV1, ApplicationOperationV1,
    ApplicationPrivateFilesV1, ApplicationRelationalStorageV1, SERVICE_ENTRYPOINT_PATTERN,
)
from three_mm_protocol.module_manifest import MODULE_ID_PATTERN, SEMVER_PATTERN

from backend.services.application_connectors import validate_destination_origin


MAX_CONTEXT_BYTES = 128 * 1024
MAX_JSON_DEPTH = 16
MAX_JSON_NODES = 16_384
MAX_INTEGER = 2**53 - 1
FINGERPRINT_DOMAIN = b"3mm:m20:authority-context:v1\x00"

Identity = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
DeviceId = Annotated[str, Field(pattern=r"^dev_[0-9a-f]{32}$")]
SecretRef = Annotated[str, Field(pattern=r"^secret_[0-9a-f]{32}$")]
ScopeKey = Annotated[str, Field(pattern=r"^(command|connector):[a-z][a-z0-9_]{0,95}$")]
ResourceScopeKey = Annotated[str, Field(pattern=r"^(command|connector|event):[a-z][a-z0-9_]{0,95}$")]
PublicationScopeKey = Annotated[str, Field(pattern=r"^(command|connector|event|publication):[a-z][a-z0-9_]{0,95}$")]
StorageScopeKey = Annotated[str, Field(
    pattern=r"^(?:(?:command|connector|event|publication):[a-z][a-z0-9_]{0,95}|storage:private_files_(?:read|write))$"
)]
RelationalScopeKey = Annotated[str, Field(
    pattern=r"^(?:(?:command|connector|event|publication):[a-z][a-z0-9_]{0,95}|storage:(?:private_files|relational)_(?:read|write))$"
)]
Revision = Annotated[int, Field(ge=1, le=MAX_INTEGER)]
Timestamp = Annotated[int, Field(ge=0, le=MAX_INTEGER)]
Blocker = Literal[
    "configuration_unresolved",
    "unsupported_scope_family",
    "peer_authority_unresolved",
    "frontend_authority_unresolved",
    "isolation_proof_missing",
    "dependency_resolution_missing",
]


class ContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @field_validator(
        "context_version", "selection_version", mode="before", check_fields=False
    )
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("Internal model version must be an integer")
        return value


class AuthorityPrincipal(ContextModel):
    core_installation_id: Identity
    application_installation_id: Identity
    incarnation: Identity
    module_id: str = Field(pattern=MODULE_ID_PATTERN, max_length=160)


class AuthorityArtifact(ContextModel):
    version: str = Field(pattern=SEMVER_PATTERN, max_length=96)
    sha256: Digest
    built_ui_sha256: Digest | None = None


class AuthorityBaseline(ContextModel):
    artifact: AuthorityArtifact | None
    authority_epoch: Identity
    grant_revision: Revision | None
    enforcement_mode: Literal["review_required", "compatibility", "enforced"]

    @model_validator(mode="after")
    def coherent_baseline(self):
        if self.enforcement_mode == "enforced" and (
            self.artifact is None or self.grant_revision is None
        ):
            raise ValueError("Enforced baseline requires artifact and grant revision")
        if self.artifact is None and self.grant_revision is not None:
            raise ValueError("Absent artifact cannot have a grant revision")
        return self


class ConfigurationIdentity(ContextModel):
    # Computed by Core with an installation-local key, not from package input.
    key_id: Identity
    keyed_sha256: Digest


class AuthorityPolicy(ContextModel):
    policy_revision: Identity
    adapter_revision: Revision
    trust_revision: Identity
    execution_profile: Identity
    execution_class: Literal["reviewed_native", "proven_isolated"]
    isolation_proof_revision: Identity | None = None
    allowed_scopes: tuple[PublicationScopeKey, ...] = Field(max_length=128)
    required_scopes: tuple[PublicationScopeKey, ...] = Field(max_length=128)
    blockers: tuple[Blocker, ...] = Field(max_length=6)

    @model_validator(mode="after")
    def unique_sets(self):
        for values in (self.allowed_scopes, self.required_scopes, self.blockers):
            if len(values) != len(set(values)):
                raise ValueError("Policy sets must be unique")
        return self


class AuthorityPolicyV4(AuthorityPolicy):
    # Internal policy/context v4 only. Old models retain their exact vocabulary.
    allowed_scopes: tuple[StorageScopeKey, ...] = Field(max_length=130)
    required_scopes: tuple[StorageScopeKey, ...] = Field(max_length=130)


class AuthorityPolicyV5(AuthorityPolicy):
    allowed_scopes: tuple[RelationalScopeKey, ...] = Field(max_length=132)
    required_scopes: tuple[RelationalScopeKey, ...] = Field(max_length=132)


class ResolvedRelationalScope(ContextModel):
    """Core-owned SQLite request identity; no path or runtime admission permit."""

    declaration: ApplicationRelationalStorageV1
    owner: AuthorityPrincipal
    package_artifact_sha256: Digest
    service_artifact_sha256: Digest
    schema_revision: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")
    migration_entrypoint: str = Field(pattern=SERVICE_ENTRYPOINT_PATTERN)
    resource_profile: Literal["owned_sqlite_request_v1"] = "owned_sqlite_request_v1"
    operation: Literal["read", "write"]

    @model_validator(mode="after")
    def declared_operation(self):
        if self.operation == "write" and self.declaration.mode != "read_write":
            raise ValueError("Read-only database cannot request write authority")
        return self


def _validate_relational_scopes(scopes, principal, artifact_sha256, *, complete):
    if not scopes:
        if complete:
            raise ValueError("Relational context requires its complete request")
        return
    first = scopes[0]
    identity = first.model_dump(exclude={"operation"})
    operations = set()
    for scope in scopes:
        if (scope.owner != principal or scope.package_artifact_sha256 != artifact_sha256
                or scope.model_dump(exclude={"operation"}) != identity
                or scope.operation in operations):
            raise ValueError("Relational scopes need one exact owned artifact request")
        operations.add(scope.operation)
    expected = {"read", "write"} if first.declaration.mode == "read_write" else {"read"}
    # Unlike file rules, a database profile cannot be narrowed to one half of
    # read_write. Empty evidence can deny it; nonempty rules must be complete.
    if operations != expected:
        raise ValueError("Relational profile requires every declared operation")


class ResolvedPrivateFileScope(ContextModel):
    """Exact Core-resolved request, not a path, signed permit or executable grant."""

    declaration: ApplicationPrivateFilesV1
    owner: AuthorityPrincipal
    package_artifact_sha256: Digest
    operation: Literal["read", "write"]

    @model_validator(mode="after")
    def declared_operation(self):
        if self.operation == "write" and self.declaration.mode != "read_write":
            raise ValueError("Read-only files cannot request write authority")
        return self


def _validate_private_file_scopes(scopes, principal, artifact_sha256, *, complete):
    """One installation/namespace/declaration; policy may select a strict subset."""
    if not scopes:
        if complete:
            raise ValueError("Storage context requires its complete file request")
        return
    declaration = scopes[0].declaration
    operations = set()
    for scope in scopes:
        if (
            scope.owner != principal
            or scope.package_artifact_sha256 != artifact_sha256
            or scope.declaration != declaration
            or scope.operation in operations
        ):
            raise ValueError("Private file scopes need one exact owned artifact request")
        operations.add(scope.operation)
    expected = {"read", "write"} if declaration.mode == "read_write" else {"read"}
    if complete and operations != expected:
        raise ValueError("Storage context requires every declared file operation")


class ResolvedCommandScope(ContextModel):
    declaration: ApplicationCommandBindingV1
    target_device_id: DeviceId
    control_revision: Identity
    sensor_device_id: DeviceId | None = None
    sensor_control_revision: Identity | None = None

    @model_validator(mode="after")
    def coherent_sensor(self):
        expected = self.declaration.sensor_id is not None
        if expected != (self.sensor_device_id is not None) or expected != (
            self.sensor_control_revision is not None
        ):
            raise ValueError("Sensor binding requires exact device and revision")
        return self


class ResolvedCredential(ContextModel):
    owner: AuthorityPrincipal
    secret_ref: SecretRef
    version: Revision
    credential_kind: Literal["basic", "bearer", "api_key"]
    revoked: bool


class StoredConnectorScope(ContextModel):
    owner: AuthorityPrincipal
    binding_revision: Identity
    destination_origin: str = Field(min_length=1, max_length=2048)
    enabled: bool
    credential: ResolvedCredential | None


class ResolvedConnectorScope(ContextModel):
    declaration: ApplicationConnectorV1
    configured_origin: str = Field(min_length=1, max_length=2048)
    configured_secret_ref: SecretRef | None
    stored: StoredConnectorScope


class ResolvedEventScope(ContextModel):
    declaration: ApplicationEventSubscriptionV1
    source_device_id: DeviceId
    source_revision: Identity
    handler: ApplicationOperationV1

    @model_validator(mode="after")
    def exact_handler(self):
        if (self.handler.operation_id != self.declaration.handler_operation_id
                or self.handler.kind != "command" or self.handler.audiences != ("internal",)
                or self.handler.idempotency != "required" or self.handler.emitted_events):
            raise ValueError("Event scope needs an exact non-publishing internal handler")
        return self


class AuthorityReviewContextV1(ContextModel):
    context_version: Literal[1]
    principal: AuthorityPrincipal
    candidate: AuthorityArtifact
    baseline: AuthorityBaseline
    configuration: ConfigurationIdentity
    policy: AuthorityPolicy
    issued_at_ms: Timestamp
    expires_at_ms: Timestamp
    commands: tuple[ResolvedCommandScope, ...] = Field(max_length=64)
    connectors: tuple[ResolvedConnectorScope, ...] = Field(max_length=32)

    @model_validator(mode="after")
    def bounded_context(self):
        if not 0 < self.expires_at_ms - self.issued_at_ms <= 3_600_000:
            raise ValueError("Review lifetime must be positive and at most one hour")
        keys = [f"command:{s.declaration.binding_id}" for s in self.commands] + [
            f"connector:{s.declaration.connector_id}" for s in self.connectors
        ] + [f"event:{s.declaration.subscription_id}" for s in getattr(self, "events", ())]
        keys += [f"publication:{s.declaration.publication_id}" for s in getattr(self, "publications", ())]
        keys += [f"storage:private_files_{s.operation}" for s in getattr(self, "private_files", ())]
        keys += [f"storage:relational_{s.operation}" for s in getattr(self, "relational", ())]
        if len(keys) != len(set(keys)):
            raise ValueError("Scope identities must be unique")
        if (set(self.policy.allowed_scopes) | set(self.policy.required_scopes)) - set(
            keys
        ):
            raise ValueError("Policy cannot refer to undeclared scopes")
        return self


class AuthorityReviewContextV2(AuthorityReviewContextV1):
    context_version: Literal[2]
    events: tuple[ResolvedEventScope, ...] = Field(max_length=32)


class ResolvedPublicationScope(ContextModel):
    declaration: ApplicationEventPublicationV1
    operation: ApplicationOperationV1
    service_artifact_sha256: Digest

    @model_validator(mode="after")
    def exact_operation(self):
        if (self.operation.operation_id != self.declaration.operation_id
                or self.operation.kind not in {"command", "job"}
                or self.operation.idempotency != "required"
                or self.declaration.event_type not in self.operation.emitted_events):
            raise ValueError("Publication requires its exact declaring command/job")
        return self


class AuthorityReviewContextV3(AuthorityReviewContextV2):
    context_version: Literal[3]
    publications: tuple[ResolvedPublicationScope, ...] = Field(max_length=32)


class AuthorityReviewContextV4(AuthorityReviewContextV3):
    context_version: Literal[4]
    policy: AuthorityPolicyV4
    private_files: tuple[ResolvedPrivateFileScope, ...] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def exact_storage_request(self):
        _validate_private_file_scopes(
            self.private_files, self.principal, self.candidate.sha256, complete=True
        )
        return self


class AuthorityReviewContextV5(AuthorityReviewContextV3):
    context_version: Literal[5]
    policy: AuthorityPolicyV5
    private_files: tuple[ResolvedPrivateFileScope, ...] = Field(max_length=2)
    relational: tuple[ResolvedRelationalScope, ...] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def exact_storage_requests(self):
        _validate_private_file_scopes(
            self.private_files, self.principal, self.candidate.sha256,
            complete=bool(self.private_files),
        )
        _validate_relational_scopes(
            self.relational, self.principal, self.candidate.sha256, complete=True,
        )
        expected = {f"storage:relational_{s.operation}" for s in self.relational}
        for values in (self.policy.allowed_scopes, self.policy.required_scopes):
            actual = {key for key in values if key.startswith("storage:relational_")}
            if actual and actual != expected:
                raise ValueError("Policy must select the whole relational profile")
        return self


class AuthoritySelectionV1(ContextModel):
    selection_version: Literal[1]
    # IDs only: no caller-supplied replacement scope, schema or target.
    scopes: tuple[ScopeKey, ...] = Field(max_length=96)

    @model_validator(mode="after")
    def unique_selection(self):
        if len(self.scopes) != len(set(self.scopes)):
            raise ValueError("Selection must be unique")
        return self


class AuthoritySelectionV2(AuthoritySelectionV1):
    selection_version: Literal[2]
    scopes: tuple[ResourceScopeKey, ...] = Field(max_length=96)


class AuthoritySelectionV3(AuthoritySelectionV1):
    selection_version: Literal[3]
    scopes: tuple[PublicationScopeKey, ...] = Field(max_length=128)


class AuthoritySelectionV4(AuthoritySelectionV1):
    selection_version: Literal[4]
    scopes: tuple[StorageScopeKey, ...] = Field(max_length=130)


class AuthoritySelectionV5(AuthoritySelectionV1):
    selection_version: Literal[5]
    scopes: tuple[RelationalScopeKey, ...] = Field(max_length=132)


class AuthorityContextIssue(ContextModel):
    scope: RelationalScopeKey | None = None
    reason: Literal[
        "invalid_context",
        "invalid_selection",
        "invalid_review_clock",
        "review_not_current",
        "unknown_selected_scope",
        "scope_not_allowed",
        "required_scope_omitted",
        "unsupported_command_contract",
        "connector_origin_invalid",
        "connector_origin_mismatch",
        "connector_path_unsupported",
        "connector_binding_unavailable",
        "connector_credential_unavailable",
        "connector_credential_mismatch",
        "configuration_unresolved",
        "unsupported_scope_family",
        "peer_authority_unresolved",
        "frontend_authority_unresolved",
        "isolation_proof_missing",
        "dependency_resolution_missing",
    ]


class AuthorityContextReview(ContextModel):
    reviewable: bool
    issues: tuple[AuthorityContextIssue, ...]
    context_fingerprint: Digest | None = None
    permission_approval: Literal["not_evaluated"] = "not_evaluated"
    not_checked: tuple[str, ...] = (
        "trusted_resolver_and_artifact_completeness",
        "current_actor_permission",
        "live_resources_and_revision_freshness",
        "proof_and_configuration_key_authenticity",
        "durable_clock_and_concurrent_invalidation",
        "approval_persistence_and_effect_enforcement",
    )


def _bounded_json(value, depth=0, budget=None):
    """Copy plain JSON only, before model parsing or canonicalization."""
    if budget is None:
        budget = [MAX_JSON_NODES, MAX_CONTEXT_BYTES]
    budget[0] -= 1
    if budget[0] < 0 or depth > MAX_JSON_DEPTH:
        raise ValueError("Context structure exceeds limits")
    if type(value) in (list, tuple, dict) and len(value) <= MAX_JSON_NODES:
        budget[1] -= (
            2 + max(0, len(value) - 1) + (len(value) if type(value) is dict else 0)
        )
        if budget[1] < 0:
            raise ValueError("Context exceeds limits")
        if type(value) is not dict:
            return [_bounded_json(v, depth + 1, budget) for v in value]
        result = {}
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("Context keys must be strings")
            result[_bounded_json(key, depth + 1, budget)] = _bounded_json(
                item, depth + 1, budget
            )
        return result
    if value is None or type(value) is bool:
        pass
    elif type(value) in (int, float):
        if abs(value) > MAX_INTEGER or (
            type(value) is float and not math.isfinite(value)
        ):
            raise ValueError("Context number exceeds limits or is not finite")
    elif type(value) is str:
        if len(value) > 4096 or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError("Context string exceeds limits or is invalid Unicode")
    else:
        raise ValueError("Context contains an unsupported value")
    budget[1] -= len(json.dumps(value, ensure_ascii=True, allow_nan=False))
    if budget[1] < 0:
        raise ValueError("Context exceeds limits")
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _parse(model, value):
    if isinstance(value, model):
        value = value.model_dump(mode="python")  # Revalidate even constructed models.
    if type(value) is str:
        if len(value.encode("utf-8")) > MAX_CONTEXT_BYTES:
            raise ValueError("Context exceeds limits")
        value = json.loads(value, object_pairs_hook=_unique_object)
    value = _bounded_json(value)
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    if len(encoded.encode("ascii")) > MAX_CONTEXT_BYTES:
        raise ValueError("Context exceeds limits")
    # JSON-mode allows JSON arrays for tuples, but no bool/int/string coercion.
    return model.model_validate_json(encoded, strict=True)


def _canonical_bytes(value) -> bytes:
    """Internal v1 typed encoding; not RFC 8785 or a public signing format.

    Object keys sort by Unicode code point. Arrays retain order. Integers use
    decimal text; floats use exact Python binary64 hex (including signed zero).
    Type tags avoid int/float/bool/string collisions. Unicode is not normalized.
    """
    value = _bounded_json(value)

    def tagged(item):
        if item is None:
            return ["null"]
        if type(item) is bool:
            return ["bool", item]
        if type(item) is int:
            return ["int", str(item)]
        if type(item) is float:
            return ["float", item.hex()]
        if type(item) is str:
            return ["str", item]
        if type(item) is list:
            return ["array", [tagged(v) for v in item]]
        return ["object", [[k, tagged(item[k])] for k in sorted(item)]]

    encoded = json.dumps(tagged(value), ensure_ascii=True, separators=(",", ":"))
    if len(encoded) > 4 * MAX_CONTEXT_BYTES:
        raise ValueError("Canonical context exceeds limits")
    return encoded.encode("ascii")


def _parse_versioned(v1, v2, value, field, v3=None, v4=None, v5=None):
    # Existing records retain their exact canonical shape/fingerprint. Callers
    # must explicitly opt into each new version; none silently gain authority.
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if type(value) is str:
        if len(value.encode("utf-8")) > MAX_CONTEXT_BYTES:
            raise ValueError("Context exceeds limits")
        value = json.loads(value, object_pairs_hook=_unique_object)
    value = _bounded_json(value)
    version = value.get(field) if type(value) is dict else None
    models = {1: v1, 2: v2}
    if v3 is not None:
        models[3] = v3
    if v4 is not None:
        models[4] = v4
    if v5 is not None:
        models[5] = v5
    if type(version) is not int or version not in models:
        raise ValueError("Unsupported internal authority version")
    return _parse(models[version], value)


def _context_fingerprint(context, selection):
    data = context.model_dump(mode="json")
    for key in ("allowed_scopes", "required_scopes", "blockers"):
        data["policy"][key].sort()
    data["commands"].sort(key=lambda s: s["declaration"]["binding_id"])
    data["connectors"].sort(key=lambda s: s["declaration"]["connector_id"])
    for command in data["commands"]:
        schema = command["declaration"]["arguments_schema"]
        schema["required"] = sorted(schema.get("required", []))
        for prop in schema["properties"].values():
            if "enum" in prop:
                values = sorted(_canonical_bytes(v) for v in prop["enum"])
                if len(values) != len(set(values)):
                    raise ValueError("Duplicate command enum value")
                prop["enum"].sort(key=_canonical_bytes)
    for connector in data["connectors"]:
        connector["declaration"]["allowed_schemes"].sort()
    if "events" in data:
        data["events"].sort(key=lambda s: s["declaration"]["subscription_id"])
    if "publications" in data:
        data["publications"].sort(key=lambda s: s["declaration"]["publication_id"])
    if "private_files" in data:
        data["private_files"].sort(key=lambda s: s["operation"])
    if "relational" in data:
        data["relational"].sort(key=lambda s: s["operation"])
    encoded = _canonical_bytes(
        {
            "context": data,
            "selection": {"selection_version": selection.selection_version, "scopes": sorted(selection.scopes)},
        }
    )
    return hashlib.sha256(FINGERPRINT_DOMAIN + encoded).hexdigest()


def review_authority_context(
    context, selection, *, now_ms: int
) -> AuthorityContextReview:
    """Evaluate trusted resolved snapshots only; never consult or mutate live state.

    Complete declarations/resources/proof inputs must come from a future Core
    resolver. Fabricating them can fabricate reviewability, NOT actual authority.
    All supplied resource scopes must resolve, even if omitted from selection.
    """
    failures = (ValueError, TypeError, RecursionError, OverflowError)
    try:
        context = _parse_versioned(
            AuthorityReviewContextV1, AuthorityReviewContextV2, context,
            "context_version", AuthorityReviewContextV3, AuthorityReviewContextV4,
            AuthorityReviewContextV5,
        )
    except failures:
        return AuthorityContextReview(
            reviewable=False, issues=(AuthorityContextIssue(reason="invalid_context"),)
        )
    try:
        selection = _parse_versioned(
            AuthoritySelectionV1, AuthoritySelectionV2, selection,
            "selection_version", AuthoritySelectionV3, AuthoritySelectionV4,
            AuthoritySelectionV5,
        )
        if context.context_version != selection.selection_version:
            raise ValueError("Authority versions must match")
    except failures:
        return AuthorityContextReview(
            reviewable=False,
            issues=(AuthorityContextIssue(reason="invalid_selection"),),
        )
    issues = set()

    def issue(reason, scope=None):
        issues.add((scope, reason))

    if type(now_ms) is not int or not 0 <= now_ms <= MAX_INTEGER:
        issue("invalid_review_clock")
    elif not context.issued_at_ms <= now_ms < context.expires_at_ms:
        issue("review_not_current")
    for reason in context.policy.blockers:
        issue(reason)
    if context.policy.execution_class == "proven_isolated" and (
        context.policy.isolation_proof_revision is None
    ):
        issue("isolation_proof_missing")
    known = {f"command:{s.declaration.binding_id}" for s in context.commands} | {
        f"connector:{s.declaration.connector_id}" for s in context.connectors
    } | {f"event:{s.declaration.subscription_id}" for s in getattr(context, "events", ())}
    known |= {f"publication:{s.declaration.publication_id}" for s in getattr(context, "publications", ())}
    known |= {f"storage:private_files_{s.operation}" for s in getattr(context, "private_files", ())}
    relational_keys = {f"storage:relational_{s.operation}" for s in getattr(context, "relational", ())}
    known |= relational_keys
    selected = set(selection.scopes)
    if selected & relational_keys and selected & relational_keys != relational_keys:
        for scope in relational_keys - selected:
            issue("required_scope_omitted", scope)
    for scope in selected - known:
        issue("unknown_selected_scope", scope)
    for scope in (selected & known) - set(context.policy.allowed_scopes):
        issue("scope_not_allowed", scope)
    for scope in set(context.policy.required_scopes) - selected:
        issue("required_scope_omitted", scope)
    for command in context.commands:
        if command.declaration.contract_version is None:
            issue(
                "unsupported_command_contract",
                f"command:{command.declaration.binding_id}",
            )
    for connector in context.connectors:
        declaration, stored = connector.declaration, connector.stored
        scope = f"connector:{declaration.connector_id}"
        try:
            configured = validate_destination_origin(
                connector.configured_origin, declaration.allowed_schemes
            )
            actual = validate_destination_origin(
                stored.destination_origin, declaration.allowed_schemes
            )
            # Require canonical broker origins; no hidden URL/whitespace rewrite.
            if (
                configured != connector.configured_origin
                or actual != stored.destination_origin
            ):
                issue("connector_origin_invalid", scope)
            elif configured != actual:
                issue("connector_origin_mismatch", scope)
        except (ValueError, RuntimeError):
            issue("connector_origin_invalid", scope)
        path = declaration.path_prefix
        if (
            any(c in path for c in ("\\", "%", "?", "#", "*"))
            or any(ord(c) < 33 for c in path)
            or any(p in {".", ".."} for p in path.split("/"))
            or "//" in path
        ):
            issue("connector_path_unsupported", scope)
        if not stored.enabled or stored.owner != context.principal:
            issue("connector_binding_unavailable", scope)
        credential = stored.credential
        if declaration.authentication == "none":
            if credential is not None or connector.configured_secret_ref is not None:
                issue("connector_credential_mismatch", scope)
        elif (
            credential is None
            or credential.revoked
            or credential.owner != context.principal
        ):
            issue("connector_credential_unavailable", scope)
        elif credential.credential_kind != declaration.authentication or (
            credential.secret_ref != connector.configured_secret_ref
        ):
            issue("connector_credential_mismatch", scope)
    fingerprint = None
    if not issues:
        try:
            fingerprint = _context_fingerprint(context, selection)
        except failures:
            issue("invalid_context")
    return AuthorityContextReview(
        reviewable=not issues,
        issues=tuple(
            AuthorityContextIssue(scope=scope, reason=reason)
            for scope, reason in sorted(
                issues, key=lambda item: (item[0] or "", item[1])
            )
        ),
        context_fingerprint=fingerprint,
    )
