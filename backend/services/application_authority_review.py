"""Read-only declaration comparison, never a grant or an activation decision.

Inputs are already validated packages and Core-supplied effective configuration.
This internal projection is deliberately not a public approval/plan wire format.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.services.application_configuration import (
    ApplicationConfigurationError,
    resolve_application_configuration,
)
from backend.services.application_connectors import (
    ApplicationConnectorError,
    validate_destination_origin,
)
from backend.services.module_packages import ValidatedModulePackage


class ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AuthorityDeclarationChange(ReviewModel):
    scope: str
    change: Literal["added", "removed", "changed"]
    before: dict | None
    after: dict | None
    potential_expansion: bool


class UnresolvedAuthority(ReviewModel):
    side: Literal["previous", "candidate"]
    scope: str
    reason: str


class ApplicationAuthorityReview(ReviewModel):
    module_id: str
    previous_version: str | None
    candidate_version: str
    previous_sha256: str | None
    candidate_sha256: str
    baseline: Literal["no_previous_package", "previous_declarations"]
    artifact_changed: bool
    changes: tuple[AuthorityDeclarationChange, ...]
    unresolved: tuple[UnresolvedAuthority, ...]
    declaration_review_required: bool
    permission_approval: Literal["not_evaluated"] = "not_evaluated"
    not_checked: tuple[str, ...] = (
        "approved_grants",
        "device_availability_and_contracts",
        "stored_connector_bindings_and_secret_generations",
        "publisher_and_signature_trust",
        "dependency_resolution",
        "os_and_browser_isolation",
    )


def _fingerprint(value: dict) -> str:
    """Redacted change marker only, NOT a signed/approved plan hash."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _command_schema(schema: dict) -> dict:
    # Only these list fields are unordered in the bounded command schema.
    result = {**schema, "required": sorted(schema.get("required", []))}
    result["properties"] = {
        name: {
            **field,
            **(
                {"enum": sorted(field["enum"], key=lambda x: json.dumps(x))}
                if "enum" in field
                else {}
            ),
        }
        for name, field in schema["properties"].items()
    }
    return result


def _declarations(
    package: ValidatedModulePackage,
    configuration: dict | None,
    side: Literal["previous", "candidate"],
) -> tuple[dict[str, dict], list[UnresolvedAuthority]]:
    app = package.application_extension
    if app is None:
        raise ValueError(
            "Authority review currently supports validated application packages only"
        )

    scopes: dict[str, dict] = {}
    unresolved: list[UnresolvedAuthority] = []

    def issue(scope: str, reason: str) -> None:
        unresolved.append(UnresolvedAuthority(side=side, scope=scope, reason=reason))

    resolved = None
    if configuration is None:
        issue("configuration", "effective_configuration_not_supplied")
    else:
        try:
            # Do not assume candidate defaults are the installation's effective values.
            resolved = resolve_application_configuration(
                package.manifest.configuration_schema,
                {},
                app,
                existing=configuration,
            )
        except (ApplicationConfigurationError, TypeError, ValueError):
            # Never echo untrusted configuration or validation errors containing it.
            issue("configuration", "effective_configuration_invalid_or_incomplete")

    def binding(scope: str, key: str, pattern: str) -> str | None:
        value = resolved.get(key) if resolved is not None else None
        if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
            issue(scope, f"unresolved_configuration_binding:{key}")
            return None
        return value

    scopes["runtime"] = {
        "runtimes": sorted(package.manifest.runtimes),
        "entrypoints": dict(package.manifest.entrypoints),
        "service_entrypoint": app.service.entrypoint,
        "sdk_version": app.service.sdk_version,
        "compiled_ui": package.compiled_ui is not None,
    }
    scopes["configuration_contract"] = {
        "schema_fingerprint": _fingerprint(package.manifest.configuration_schema),
    }
    for permission in package.manifest.permissions:
        scopes[f"permission:{permission}"] = {}
    for direction in ("provides", "consumes"):
        for capability in getattr(package.manifest.capabilities, direction):
            scopes[f"capability.{direction}:{capability}"] = {}
    for permission in app.platform_permissions:
        scopes[f"platform:{permission}"] = {}
    if app.peer_receiver is not None:
        scopes["peer_receiver"] = app.peer_receiver.model_dump(mode="json")
        issue("peer_receiver", "approved_peer_scope_not_supplied")
    for permission in app.permissions:
        scopes[f"human_permission:{permission.permission_id}"] = {}

    for operation in app.operations:
        scope = operation.model_dump(
            mode="json", exclude={"input_schema", "output_schema"}
        )
        scope["audiences"] = sorted(operation.audiences)
        scope["emitted_events"] = sorted(operation.emitted_events)
        scope["input_schema_fingerprint"] = _fingerprint(operation.input_schema)
        scope["output_schema_fingerprint"] = _fingerprint(operation.output_schema)
        scopes[f"operation:{operation.operation_id}"] = scope
    for route in app.routes:
        scope = route.model_dump(mode="json", exclude={"navigation", "order"})
        scope["required_permissions"] = sorted(route.required_permissions)
        scopes[f"route:{route.route_id}"] = scope
    for route in app.public_http_routes:
        scope = route.model_dump(mode="json")
        scope["methods"] = sorted(route.methods)
        scope["content_types"] = sorted(route.content_types)
        scopes[f"public_http:{route.route_id}"] = scope

    for command in app.command_bindings:
        key = f"command:{command.binding_id}"
        scope = command.model_dump(mode="json")
        scope["arguments_schema"] = _command_schema(command.arguments_schema)
        scope["target_device_id"] = binding(
            key, command.target_device_config_key, r"dev_[0-9a-f]{32}"
        )
        if command.sensor_device_config_key is not None:
            scope["sensor_device_id"] = binding(
                key, command.sensor_device_config_key, r"dev_[0-9a-f]{32}"
            )
        scopes[key] = scope
    for subscription in app.event_subscriptions:
        key = f"event:{subscription.subscription_id}"
        scopes[key] = {
            **subscription.model_dump(mode="json"),
            "device_id": binding(
                key, subscription.device_scope_config_key, r"dev_[0-9a-f]{32}"
            ),
        }
    if package.application_publications is not None:
        for publication in package.application_publications.publications:
            scopes[f"publication:{publication.publication_id}"] = publication.model_dump(mode="json")
    for connector in app.connectors:
        key = f"connector:{connector.connector_id}"
        scope = connector.model_dump(mode="json")
        scope["allowed_schemes"] = sorted(connector.allowed_schemes)
        value = (
            resolved.get(connector.destination_config_key)
            if resolved is not None
            else None
        )
        origin = None
        try:
            if not isinstance(value, str):
                raise ApplicationConnectorError("Missing configured origin")
            origin = validate_destination_origin(value, connector.allowed_schemes)
        except (ApplicationConnectorError, ValueError):
            issue(
                key,
                f"unresolved_configuration_binding:{connector.destination_config_key}",
            )
        scope["configured_origin"] = origin
        if connector.credential_ref_config_key is not None:
            # UUID references are not credential values. Reject everything else,
            # including accidentally supplied passwords/tokens; never echo it.
            scope["credential_reference"] = binding(
                key,
                connector.credential_ref_config_key,
                r"secret_[0-9a-f]{32}",
            )
        scopes[key] = scope

    for job in app.jobs:
        scopes[f"job:{job.job_id}"] = job.model_dump(mode="json")
    # Keep legacy own_storage bytes stable. Each optional storage contract is an
    # explicit request, not an inferred grant for the other storage family.
    storage = app.storage.model_dump(mode="json", exclude={"private_files", "relational"})
    storage["classifications"] = sorted(app.storage.classifications)
    scopes["own_storage"] = storage
    if app.storage.private_files is not None:
        scopes["storage:private_files"] = app.storage.private_files.model_dump(mode="json")
        issue("storage:private_files", "private_file_grant_not_evaluated")
    if app.storage.relational is not None:
        scopes["storage:relational"] = app.storage.relational.model_dump(mode="json")
        issue("storage:relational", "relational_storage_grant_not_evaluated")
    scopes["lifecycle"] = app.lifecycle.model_dump(mode="json")
    if package.compiled_ui is not None:
        # This is native, same-origin integration, not a sandboxed authority set.
        issue("compiled_ui", "executable_frontend_effects_not_inferred")
        for entrypoint in package.compiled_ui.entrypoints:
            scopes[f"ui:{entrypoint.entrypoint_id}"] = entrypoint.model_dump(
                mode="json", exclude={"label"}
            )
        if package.compiled_ui.capability_plan is not None:
            scopes["ui_capability_plan"] = {
                "fingerprint": _fingerprint(
                    package.compiled_ui.capability_plan.model_dump(mode="json")
                ),
            }
            issue(
                "ui_capability_plan", "frontend_capability_plan_authority_not_resolved"
            )
    return scopes, unresolved


def review_application_authority(
    candidate: ValidatedModulePackage,
    *,
    previous: ValidatedModulePackage | None = None,
    candidate_configuration: dict | None = None,
    previous_configuration: dict | None = None,
) -> ApplicationAuthorityReview:
    """Compare declarations only. Callers must not treat the old package as a grant.

    A changed scope may expand authority; no general schema-subset proof is made.
    Even an empty diff says nothing about trust, approval or current availability.
    """
    if (
        previous is not None
        and previous.manifest.module_id != candidate.manifest.module_id
    ):
        raise ValueError("Authority comparison requires the same module identity")
    if previous is None and previous_configuration is not None:
        raise ValueError("Previous configuration requires a previous package")
    before: dict[str, dict] = {}
    unresolved: list[UnresolvedAuthority] = []
    if previous is not None:
        before, unresolved = _declarations(previous, previous_configuration, "previous")
    after, pending = _declarations(candidate, candidate_configuration, "candidate")
    unresolved.extend(pending)
    changes = []
    for key in sorted(before.keys() | after.keys()):
        if key in before and key in after and before[key] == after[key]:
            continue
        change = (
            "added"
            if key not in before
            else "removed" if key not in after else "changed"
        )
        changes.append(
            AuthorityDeclarationChange(
                scope=key,
                change=change,
                before=before.get(key),
                after=after.get(key),
                potential_expansion=change != "removed",
            )
        )
    artifact_changed = previous is None or previous.sha256 != candidate.sha256
    return ApplicationAuthorityReview(
        module_id=candidate.manifest.module_id,
        previous_version=previous.manifest.version if previous is not None else None,
        candidate_version=candidate.manifest.version,
        previous_sha256=previous.sha256 if previous is not None else None,
        candidate_sha256=candidate.sha256,
        baseline=(
            "previous_declarations" if previous is not None else "no_previous_package"
        ),
        artifact_changed=artifact_changed,
        changes=tuple(changes),
        unresolved=tuple(
            sorted(unresolved, key=lambda item: (item.side, item.scope, item.reason))
        ),
        declaration_review_required=artifact_changed
        or bool(changes)
        or bool(unresolved),
    )
