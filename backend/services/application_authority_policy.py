"""Pure Core-policy evaluation over trusted snapshots, not an evidence verifier.

No route, store or grant is introduced by this pure module. The installed-only
authority coordinator verifies a sealed local manual native-review attestation
before constructing its evidence. Package declarations, inspection results and
an HTTP/admin checkbox are NOT that adapter. Other unresolved trust classes stay
blocked; this comparison alone cannot authenticate evidence or prove isolation.
"""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from backend.services.application_authority_context import (
    AuthorityArtifact,
    AuthorityBaseline,
    AuthorityPolicy,
    AuthorityPolicyV4,
    AuthorityPolicyV5,
    AuthorityPrincipal,
    Blocker,
    ConfigurationIdentity,
    ContextModel,
    Identity,
    ResolvedCommandScope,
    ResolvedConnectorScope,
    ResolvedEventScope,
    ResolvedPublicationScope,
    ResolvedPrivateFileScope,
    ResolvedRelationalScope,
    RelationalScopeKey,
    PublicationScopeKey,
    ResourceScopeKey,
    ScopeKey,
    StorageScopeKey,
    _canonical_bytes,
    _parse,
    _parse_versioned,
    _validate_private_file_scopes,
    _validate_relational_scopes,
)


# Actual version of THIS evaluator's semantics, not invented live-state evidence.
POLICY_ADAPTER_REVISION = 1
EVENT_POLICY_ADAPTER_REVISION = 2
PUBLICATION_POLICY_ADAPTER_REVISION = 3
STORAGE_POLICY_ADAPTER_REVISION = 4
RELATIONAL_POLICY_ADAPTER_REVISION = 5
POLICY_DOMAIN = b"3mm:m20:core-policy-evaluation:v1\x00"
Generation = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]


class PolicyBinding(ContextModel):
    principal: AuthorityPrincipal
    candidate: AuthorityArtifact
    baseline: AuthorityBaseline
    configuration: ConfigurationIdentity
    recovery_generation: Generation


class PolicyModel(ContextModel):
    @field_validator("subject_version", "evidence_version", mode="before", check_fields=False)
    @classmethod
    def integer_policy_version(cls, value):
        if type(value) is not int:
            raise ValueError("Internal policy version must be an integer")
        return value


class PolicySubjectV1(PolicyModel):
    subject_version: Literal[1]
    binding: PolicyBinding
    commands: tuple[ResolvedCommandScope, ...] = Field(max_length=64)
    connectors: tuple[ResolvedConnectorScope, ...] = Field(max_length=32)
    has_executable_frontend: bool
    blockers: tuple[Blocker, ...] = Field(max_length=6)

    @model_validator(mode="after")
    def unique_subject(self):
        _scopes(self.commands, self.connectors, getattr(self, "events", ()), getattr(self, "publications", ()), getattr(self, "private_files", ()), getattr(self, "relational", ()))
        if len(self.blockers) != len(set(self.blockers)):
            raise ValueError("Source blockers must be unique")
        return self


class PolicySubjectV2(PolicySubjectV1):
    subject_version: Literal[2]
    events: tuple[ResolvedEventScope, ...] = Field(max_length=32)


class PolicySubjectV3(PolicySubjectV2):
    subject_version: Literal[3]
    publications: tuple[ResolvedPublicationScope, ...] = Field(max_length=32)


class PolicySubjectV4(PolicySubjectV3):
    subject_version: Literal[4]
    private_files: tuple[ResolvedPrivateFileScope, ...] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def exact_storage_request(self):
        _validate_private_file_scopes(
            self.private_files, self.binding.principal, self.binding.candidate.sha256,
            complete=True,
        )
        return self


class PolicySubjectV5(PolicySubjectV3):
    subject_version: Literal[5]
    private_files: tuple[ResolvedPrivateFileScope, ...] = Field(max_length=2)
    relational: tuple[ResolvedRelationalScope, ...] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def exact_storage_requests(self):
        _validate_private_file_scopes(
            self.private_files, self.binding.principal, self.binding.candidate.sha256,
            complete=bool(self.private_files),
        )
        _validate_relational_scopes(
            self.relational, self.binding.principal, self.binding.candidate.sha256,
            complete=True,
        )
        return self


class CorePolicyEvidenceV1(PolicyModel):
    """Input contract for a FUTURE trusted, durable Core policy/evidence source.

    Constructing/parsing this model proves nothing. The record's origin,
    verification, revision lifecycle and freshness are the adapter's obligation.
    Rules are whole exact resolved scopes, never IDs interpreted as wildcards.
    """

    evidence_version: Literal[1]
    binding: PolicyBinding
    policy_revision: Identity
    trust_revision: Identity
    trust_class: Literal["reviewed_local_artifact", "unknown", "revoked"]
    execution_class: Literal["reviewed_native", "proven_isolated"]
    execution_profile: Identity
    profile_revision: Identity
    native_review_revision: Identity | None
    isolation_proof_revision: Identity | None
    commands: tuple[ResolvedCommandScope, ...] = Field(max_length=64)
    connectors: tuple[ResolvedConnectorScope, ...] = Field(max_length=32)
    required_scopes: tuple[ScopeKey, ...] = Field(max_length=96)

    @model_validator(mode="after")
    def coherent_rules(self):
        known = _scopes(self.commands, self.connectors, getattr(self, "events", ()), getattr(self, "publications", ()), getattr(self, "private_files", ()), getattr(self, "relational", ()))
        if len(self.required_scopes) != len(set(self.required_scopes)):
            raise ValueError("Required policy scopes must be unique")
        if set(self.required_scopes) - known.keys():
            raise ValueError("Required scope needs an exact policy rule")
        return self


class CorePolicyEvidenceV2(CorePolicyEvidenceV1):
    evidence_version: Literal[2]
    events: tuple[ResolvedEventScope, ...] = Field(max_length=32)
    required_scopes: tuple[ResourceScopeKey, ...] = Field(max_length=96)


class CorePolicyEvidenceV3(CorePolicyEvidenceV2):
    evidence_version: Literal[3]
    publications: tuple[ResolvedPublicationScope, ...] = Field(max_length=32)
    required_scopes: tuple[PublicationScopeKey, ...] = Field(max_length=128)


class CorePolicyEvidenceV4(CorePolicyEvidenceV3):
    evidence_version: Literal[4]
    private_files: tuple[ResolvedPrivateFileScope, ...] = Field(max_length=2)
    required_scopes: tuple[StorageScopeKey, ...] = Field(max_length=130)

    @model_validator(mode="after")
    def exact_storage_rules(self):
        _validate_private_file_scopes(
            self.private_files, self.binding.principal, self.binding.candidate.sha256,
            complete=False,
        )
        return self


class CorePolicyEvidenceV5(CorePolicyEvidenceV3):
    evidence_version: Literal[5]
    private_files: tuple[ResolvedPrivateFileScope, ...] = Field(max_length=2)
    relational: tuple[ResolvedRelationalScope, ...] = Field(max_length=2)
    required_scopes: tuple[RelationalScopeKey, ...] = Field(max_length=132)

    @model_validator(mode="after")
    def exact_storage_rules(self):
        _validate_private_file_scopes(
            self.private_files, self.binding.principal, self.binding.candidate.sha256,
            complete=False,
        )
        _validate_relational_scopes(
            self.relational, self.binding.principal, self.binding.candidate.sha256,
            complete=False,
        )
        expected = {f"storage:relational_{s.operation}" for s in self.relational}
        required = {key for key in self.required_scopes if key.startswith("storage:relational_")}
        if required and required != expected:
            raise ValueError("Required policy must select the whole relational profile")
        return self


PolicyReason = Literal[
    "invalid_policy_subject",
    "trusted_policy_unavailable",
    "invalid_trusted_policy",
    "policy_binding_changed",
    "artifact_trust_unavailable",
    "artifact_trust_revoked",
    "native_review_missing",
    "execution_profile_unsupported",
    "isolation_adapter_unavailable",
    "unexpected_isolation_evidence",
    "policy_scope_unavailable",
    "policy_scope_changed",
    "configuration_unresolved",
    "unsupported_scope_family",
    "peer_authority_unresolved",
    "frontend_authority_unresolved",
    "isolation_proof_missing",
    "dependency_resolution_missing",
]


class PolicyIssue(ContextModel):
    reason: PolicyReason
    scope: RelationalScopeKey | None = None


class PolicyEvaluation(ContextModel):
    policy_resolved: bool
    policy: AuthorityPolicy | AuthorityPolicyV4 | AuthorityPolicyV5 | None = None
    issues: tuple[PolicyIssue, ...]
    # Even a successful pure policy evaluation is not a complete context review.
    reviewable: Literal[False] = False
    permission_approval: Literal["not_evaluated"] = "not_evaluated"
    not_checked: tuple[str, ...] = (
        "trusted_policy_store_and_evidence_authenticity",
        "source_completeness_and_live_freshness",
        "publisher_signature_and_namespace_verification",
        "resource_context_and_selection_validation",
        "current_actor_and_durable_approval",
        "os_browser_isolation_and_resource_limits",
        "concurrent_apply_and_effect_enforcement",
    )


def _scopes(commands, connectors, events=(), publications=(), private_files=(), relational=()):
    result = {}
    for prefix, scopes, name in (
        ("command", commands, "binding_id"),
        ("connector", connectors, "connector_id"),
        ("event", events, "subscription_id"),
        ("publication", publications, "publication_id"),
    ):
        for scope in scopes:
            key = f"{prefix}:{getattr(scope.declaration, name)}"
            if key in result:
                raise ValueError("Scope identities must be unique")
            result[key] = scope
    for scope in private_files:
        key = f"storage:private_files_{scope.operation}"
        if key in result:
            raise ValueError("Scope identities must be unique")
        result[key] = scope
    for scope in relational:
        key = f"storage:relational_{scope.operation}"
        if key in result:
            raise ValueError("Scope identities must be unique")
        result[key] = scope
    return result


def _scope_data(scope):
    """Match the context's typed/set semantics, not Python's 1 == 1.0 equality."""
    data = scope.model_dump(mode="json")
    declaration = data["declaration"]
    if isinstance(scope, ResolvedCommandScope):
        schema = declaration["arguments_schema"]
        schema["required"] = sorted(schema.get("required", []))
        for prop in schema["properties"].values():
            if "enum" in prop:
                encoded = [_canonical_bytes(item) for item in prop["enum"]]
                if len(encoded) != len(set(encoded)):
                    raise ValueError("Duplicate command enum value")
                prop["enum"].sort(key=_canonical_bytes)
    elif isinstance(scope, ResolvedConnectorScope):
        declaration["allowed_schemes"].sort()
    return data


def _adapter_revision(evidence):
    return {1: POLICY_ADAPTER_REVISION, 2: EVENT_POLICY_ADAPTER_REVISION,
        3: PUBLICATION_POLICY_ADAPTER_REVISION, 4: STORAGE_POLICY_ADAPTER_REVISION,
        5: RELATIONAL_POLICY_ADAPTER_REVISION}[evidence.evidence_version]


def _policy_identity(evidence):
    data = evidence.model_dump(mode="json")
    data["commands"] = [
        _scope_data(scope)
        for scope in sorted(evidence.commands, key=lambda s: s.declaration.binding_id)
    ]
    data["connectors"] = [
        _scope_data(scope)
        for scope in sorted(
            evidence.connectors, key=lambda s: s.declaration.connector_id
        )
    ]
    data["required_scopes"].sort()
    if hasattr(evidence, "events"):
        data["events"] = [_scope_data(scope) for scope in sorted(
            evidence.events, key=lambda s: s.declaration.subscription_id)]
    if hasattr(evidence, "publications"):
        data["publications"] = [_scope_data(scope) for scope in sorted(
            evidence.publications, key=lambda s: s.declaration.publication_id)]
    if hasattr(evidence, "private_files"):
        data["private_files"] = [_scope_data(scope) for scope in sorted(
            evidence.private_files, key=lambda s: s.operation)]
    if hasattr(evidence, "relational"):
        data["relational"] = [_scope_data(scope) for scope in sorted(
            evidence.relational, key=lambda s: s.operation)]
    return "policy_" + hashlib.sha256(
        POLICY_DOMAIN
        + _canonical_bytes(
            {"adapter_revision": _adapter_revision(evidence), "evidence": data}
        )
    ).hexdigest()


def evaluate_authority_policy(subject, evidence=None) -> PolicyEvaluation:
    """Evaluate Core-sourced inputs only; never authenticate supplied evidence.

    Missing evidence denies. There is NO isolated-runtime/UI verifier currently;
    nonempty revision strings cannot bypass those gates. Exact locally reviewed
    native evidence is a separate policy classification, not a sandbox/grant.
    No caller is permitted to use this pure helper as an approval endpoint.
    """
    failures = (ValueError, TypeError, RecursionError, OverflowError)

    def failed(reason):
        return PolicyEvaluation(
            policy_resolved=False, issues=(PolicyIssue(reason=reason),)
        )

    try:
        subject = _parse_versioned(PolicySubjectV1, PolicySubjectV2, subject, "subject_version", PolicySubjectV3, PolicySubjectV4, PolicySubjectV5)
        actual = _scopes(subject.commands, subject.connectors, getattr(subject, "events", ()), getattr(subject, "publications", ()), getattr(subject, "private_files", ()), getattr(subject, "relational", ()))
        actual_bytes = {
            key: _canonical_bytes(_scope_data(scope))
            for key, scope in actual.items()
        }
    except failures:
        return failed("invalid_policy_subject")
    issues = {(None, reason) for reason in subject.blockers}
    if subject.has_executable_frontend or subject.binding.candidate.built_ui_sha256:
        issues.add((None, "frontend_authority_unresolved"))
    if evidence is None:
        issues.add((None, "trusted_policy_unavailable"))
    else:
        try:
            evidence = _parse_versioned(CorePolicyEvidenceV1, CorePolicyEvidenceV2, evidence, "evidence_version", CorePolicyEvidenceV3, CorePolicyEvidenceV4, CorePolicyEvidenceV5)
            if evidence.evidence_version != subject.subject_version:
                raise ValueError("Policy versions must match")
            rules = _scopes(evidence.commands, evidence.connectors, getattr(evidence, "events", ()), getattr(evidence, "publications", ()), getattr(evidence, "private_files", ()), getattr(evidence, "relational", ()))
            rule_bytes = {
                key: _canonical_bytes(_scope_data(scope))
                for key, scope in rules.items()
            }
            identity = _policy_identity(evidence)
        except failures:
            # Never echo validation inputs, configured origins or secret references.
            issues.add((None, "invalid_trusted_policy"))
        else:
            if evidence.binding != subject.binding:
                issues.add((None, "policy_binding_changed"))
            if evidence.trust_class == "unknown":
                issues.add((None, "artifact_trust_unavailable"))
            elif evidence.trust_class == "revoked":
                issues.add((None, "artifact_trust_revoked"))
            if evidence.execution_class == "proven_isolated":
                issues.add((None, "isolation_adapter_unavailable"))
            else:
                if evidence.native_review_revision is None:
                    issues.add((None, "native_review_missing"))
                if evidence.execution_profile != "supervised_reviewed_native_v1":
                    issues.add((None, "execution_profile_unsupported"))
                if evidence.isolation_proof_revision is not None:
                    issues.add((None, "unexpected_isolation_evidence"))
            for key, expected in rule_bytes.items():
                if key not in actual_bytes:
                    issues.add((key, "policy_scope_unavailable"))
                elif actual_bytes[key] != expected:
                    issues.add((key, "policy_scope_changed"))
            if not issues:
                return PolicyEvaluation(
                    policy_resolved=True,
                    policy=({4: AuthorityPolicyV4, 5: AuthorityPolicyV5}.get(evidence.evidence_version, AuthorityPolicy))(
                        policy_revision=identity,
                        adapter_revision=_adapter_revision(evidence),
                        trust_revision=evidence.trust_revision,
                        execution_profile=evidence.execution_profile,
                        execution_class="reviewed_native",
                        allowed_scopes=tuple(sorted(rules)),
                        required_scopes=tuple(sorted(evidence.required_scopes)),
                        blockers=(),
                    ),
                    issues=(),
                )
    return PolicyEvaluation(
        policy_resolved=False,
        issues=tuple(
            PolicyIssue(scope=scope, reason=reason)
            for scope, reason in sorted(issues, key=lambda i: (i[0] or "", i[1]))
        ),
    )
