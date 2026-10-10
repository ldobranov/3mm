"""Core-reconstructed installed subjects, NOT native trust, policy or approval.

No caller manifest, configuration, principal, scopes or evidence is accepted.
Actual package bytes, DB resources and the existing protected key are composed
read-only. The result cannot mint permissions or clear missing policy evidence.
"""

import hashlib
from pathlib import Path
from typing import Literal

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from backend.services import application_authority_sources as sources
from backend.services.application_authority_context import (
    ContextModel, ResolvedCommandScope, _bounded_json, _canonical_bytes, _parse,
)
from backend.services.application_authority_keys import AuthorityReviewKeyError, CoreReviewKeyStore
from backend.services.application_authority_policy import PolicyBinding, PolicySubjectV1, PolicySubjectV2, PolicySubjectV3, PolicySubjectV4, PolicySubjectV5
from backend.services.authority_metadata import AuthorityGuardSnapshot


CONTROL_DOMAIN = b"3mm:m20:resolved-command-control:v1\x00"
SOURCE_BLOCKERS = frozenset({
    "configuration_unresolved", "unsupported_scope_family", "peer_authority_unresolved",
    "frontend_authority_unresolved", "isolation_proof_missing", "dependency_resolution_missing",
})


class InstalledPolicySubject(ContextModel):
    subject_scope: Literal["installed_artifact_only"] = "installed_artifact_only"
    subject: PolicySubjectV1 | PolicySubjectV2 | PolicySubjectV3 | PolicySubjectV4 | PolicySubjectV5 | None = None
    guard: AuthorityGuardSnapshot | None = None
    issues: tuple[sources.SourceIssue, ...]
    reviewable: Literal[False] = False
    permission_approval: Literal["not_evaluated"] = "not_evaluated"
    not_checked: tuple[str, ...] = (
        "native_provenance_and_positive_policy", "staged_candidates_and_approved_grants",
        "current_actor_and_restart_safe_review_clock", "apply_key_coordination_and_effect_enforcement",
        "os_browser_isolation_and_resource_limits",
    )


def _schema_bytes(schema):
    # Equality of this bounded dialect ONLY, never general schema containment.
    data = _bounded_json(schema)
    data["required"] = sorted(data.get("required", []))
    for prop in data["properties"].values():
        if "enum" in prop:
            encoded = [_canonical_bytes(value) for value in prop["enum"]]
            if len(set(encoded)) != len(encoded):
                raise ValueError("Duplicate command enum")
            prop["enum"].sort(key=_canonical_bytes)
    return _canonical_bytes(data)


def _commands(package, resolved):
    by_scope = {command.scope: command for command in resolved.commands}
    commands = []
    for binding in package.application_extension.command_bindings:
        source = by_scope[f"command:{binding.binding_id}"]
        if (_schema_bytes(binding.arguments_schema) != _schema_bytes(source.action_arguments_schema)):
            raise sources._Unavailable("command_schema_containment_not_evaluated", source.scope)
        if source.sensor is not None:
            # Merely resolving the sensor device is not its passage contract.
            raise sources._Unavailable("sensor_contract_unresolved", source.scope)
        # Bind every actual provider/module/contract/runtime/credential/control
        # pin, not just a reusable device ID or an unverified declaration.
        identity = "control_" + hashlib.sha256(
            CONTROL_DOMAIN + _canonical_bytes(source.model_dump(mode="json"))).hexdigest()
        commands.append(ResolvedCommandScope(declaration=binding,
            target_device_id=source.target.device_id, control_revision=identity))
    if len(commands) != len(by_scope):
        raise sources._Unavailable("command_contract_unresolved")
    return tuple(commands)


def _compose(db, installation_id, pin, package, keys):
    resolved = sources._resolve(db, installation_id, pin, package)
    configuration = sources._configuration(db, installation_id, package)
    commands = _commands(package, resolved)
    # All three use the same real DB read transaction. No external Session cache
    # or independent key-store DB snapshot may substitute for these sources.
    identity = keys._fingerprint_in_snapshot(db, resolved.principal, configuration)
    blockers = tuple(sorted({issue.reason for issue in resolved.issues
        if issue.reason in SOURCE_BLOCKERS}))
    unexpected = {issue.reason for issue in resolved.issues} - SOURCE_BLOCKERS - {
        "configuration_key_unavailable", "policy_evidence_unavailable", "candidate_staging_not_implemented",
        "command_schema_containment_not_evaluated",
    }
    if unexpected:
        raise sources._Unavailable("source_unavailable")
    version = 5 if resolved.relational else 4 if resolved.private_files else 3 if resolved.publications else 2 if resolved.events else 1
    model = {1: PolicySubjectV1, 2: PolicySubjectV2, 3: PolicySubjectV3, 4: PolicySubjectV4, 5: PolicySubjectV5}[version]
    subject = _parse(model, model(subject_version=version,
        binding=PolicyBinding(principal=resolved.principal, candidate=resolved.baseline.artifact,
            baseline=resolved.baseline, configuration=identity, recovery_generation=resolved.guard.generation),
        commands=commands, connectors=resolved.connectors,
        has_executable_frontend=package.compiled_ui is not None, blockers=blockers,
        **({"events": resolved.events} if version >= 2 else {}),
        **({"publications": resolved.publications} if version >= 3 else {}),
        **({"private_files": resolved.private_files} if version >= 4 else {}),
        **({"relational": resolved.relational} if version == 5 else {})))
    return InstalledPolicySubject(subject=subject, guard=resolved.guard,
        issues=tuple(sources.SourceIssue(reason=reason) for reason in (
            "policy_evidence_unavailable", *blockers)))


def resolve_installed_policy_subject(engine: Engine, installation_id: int, *,
        uploads_root: Path, core_version: str, review_key_directory: Path) -> InstalledPolicySubject:
    """Internal Core reader. Paths/version come from trusted host configuration.

    Artifact validation precedes the final read transaction. Missing/foreign/
    corrupt keys, resources or metadata produce no partial subject. Unsupported
    declarations remain blockers; exact command-schema equality is supported,
    narrower/wider schemas and sensor contracts are not inferred. No API or
    production caller is added; positive policy/approval gates remain unsatisfied.
    """
    try:
        pin, package = sources._prepare_installed_package(engine, installation_id, uploads_root, core_version)
        keys = CoreReviewKeyStore(engine, review_key_directory)
        with sources._read_snapshot(engine) as db:
            result = _compose(db, installation_id, pin, package, keys)
            _bounded_json(result.model_dump(mode="json"))
            return result
    except AuthorityReviewKeyError:
        return InstalledPolicySubject(issues=(sources.SourceIssue(reason="configuration_key_unavailable"),))
    except sources._Unavailable as exc:
        return InstalledPolicySubject(issues=(exc.issue,))
    except (SQLAlchemyError, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
        return InstalledPolicySubject(issues=(sources.SourceIssue(reason="source_unavailable"),))
