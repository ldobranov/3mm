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
from three_mm_protocol.application_resources import ResourceScope

from backend.services.application_authority_context import (
    AuthorityArtifact,
    AuthorityBaseline,
    AuthorityPolicy,
    AuthorityPolicyV4,
    AuthorityPolicyV5,
    AuthorityPolicyV6,
    AuthorityPolicyV7,
    AuthorityPolicyV8,
    AuthorityPolicyV9,
    AuthorityPolicyV10, AuthorityTaskPolicyV11, TaskScopeKey,
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
    ResolvedCheckpointScope,
    ResolvedIdentityScope,
    ResolvedStatusScope,
    ResolvedPeerReadScope,
    PeerScopeKey,
    SessionScopeKey,
    ResolvedSessionScope,
    StatusScopeKey,
    IdentityScopeKey,
    CheckpointScopeKey,
    RelationalScopeKey,
    PublicationScopeKey,
    ResourceScopeKey,
    ScopeKey,
    StorageScopeKey,
    _canonical_bytes,
    _command_schema_data,
    _parse,
    _parse_versioned,
    _validate_private_file_scopes,
    _validate_relational_scopes,
    _validate_checkpoint_scopes,
    _validate_identity_scopes,
    _validate_status_scopes,
    _validate_peer_read_scopes,
    _validate_session_bundle,
    _validate_session_scopes,
)


# Actual version of THIS evaluator's semantics, not invented live-state evidence.
POLICY_ADAPTER_REVISION = 1
EVENT_POLICY_ADAPTER_REVISION = 2
PUBLICATION_POLICY_ADAPTER_REVISION = 3
STORAGE_POLICY_ADAPTER_REVISION = 4
RELATIONAL_POLICY_ADAPTER_REVISION = 5
CHECKPOINT_POLICY_ADAPTER_REVISION = 6
IDENTITY_POLICY_ADAPTER_REVISION = 7
STATUS_POLICY_ADAPTER_REVISION = 8
PEER_READ_POLICY_ADAPTER_REVISION = 9
SESSION_POLICY_ADAPTER_REVISION = 10
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
    optional_resources: tuple[ResourceScope, ...] = Field(default=(), max_length=16)
    commands: tuple[ResolvedCommandScope, ...] = Field(max_length=64)
    connectors: tuple[ResolvedConnectorScope, ...] = Field(max_length=32)
    has_executable_frontend: bool
    blockers: tuple[Blocker, ...] = Field(max_length=6)

    @model_validator(mode="after")
    def unique_subject(self):
        _scopes(self.commands, self.connectors, getattr(self, "events", ()), getattr(self, "publications", ()), getattr(self, "private_files", ()), getattr(self, "relational", ()), getattr(self, "checkpoints", ()), getattr(self, "identities", ()), getattr(self, "status_projections", ()), getattr(self, "peer_reads", ()), getattr(self, "sessions", ()), getattr(self, "tasks", ()))
        if len(self.optional_resources) != len(set(self.optional_resources)):
            raise ValueError('Optional resource scopes must be unique')
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
    private_files: tuple[ResolvedPrivateFileScope, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def exact_storage_request(self):
        _validate_private_file_scopes(
            self.private_files, self.binding.principal, self.binding.candidate.sha256,
            complete=True,
        )
        return self


class PolicySubjectV5(PolicySubjectV3):
    subject_version: Literal[5]
    private_files: tuple[ResolvedPrivateFileScope, ...] = Field(max_length=4)
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


class PolicySubjectV6(PolicySubjectV3):
    subject_version: Literal[6]
    private_files: tuple[ResolvedPrivateFileScope, ...] = Field(max_length=4)
    relational: tuple[ResolvedRelationalScope, ...] = Field(max_length=2)
    checkpoints: tuple[ResolvedCheckpointScope, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def exact_owned_requests(self):
        _validate_private_file_scopes(
            self.private_files, self.binding.principal, self.binding.candidate.sha256,
            complete=bool(self.private_files),
        )
        _validate_relational_scopes(
            self.relational, self.binding.principal, self.binding.candidate.sha256,
            complete=bool(self.relational),
        )
        _validate_checkpoint_scopes(
            self.checkpoints, self.binding.principal, self.binding.candidate.sha256,
            complete=True,
        )
        return self


class PolicySubjectV7(PolicySubjectV6):
    subject_version: Literal[7]
    checkpoints: tuple[ResolvedCheckpointScope, ...] = Field(max_length=64)
    identities: tuple[ResolvedIdentityScope, ...] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def exact_owned_requests(self):
        _validate_private_file_scopes(self.private_files, self.binding.principal,
            self.binding.candidate.sha256, complete=bool(self.private_files))
        _validate_relational_scopes(self.relational, self.binding.principal,
            self.binding.candidate.sha256, complete=bool(self.relational))
        _validate_checkpoint_scopes(self.checkpoints, self.binding.principal,
            self.binding.candidate.sha256, complete=bool(self.checkpoints))
        _validate_identity_scopes(self.identities, self.binding.principal,
            self.binding.candidate.sha256, complete=True)
        return self


class PolicySubjectV8(PolicySubjectV7):
    subject_version: Literal[8]
    identities: tuple[ResolvedIdentityScope, ...] = Field(max_length=1)
    status_projections: tuple[ResolvedStatusScope, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def exact_owned_requests(self):
        _validate_private_file_scopes(self.private_files, self.binding.principal,
            self.binding.candidate.sha256, complete=bool(self.private_files))
        _validate_relational_scopes(self.relational, self.binding.principal,
            self.binding.candidate.sha256, complete=bool(self.relational))
        _validate_checkpoint_scopes(self.checkpoints, self.binding.principal,
            self.binding.candidate.sha256, complete=bool(self.checkpoints))
        _validate_identity_scopes(self.identities, self.binding.principal,
            self.binding.candidate.sha256, complete=bool(self.identities))
        _validate_status_scopes(self.status_projections, self.binding.principal,
            self.binding.candidate.sha256, self.identities, complete=True)
        return self


class PolicySubjectV9(PolicySubjectV8):
    subject_version: Literal[9]
    status_projections: tuple[ResolvedStatusScope, ...] = Field(max_length=32)
    peer_reads: tuple[ResolvedPeerReadScope, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def exact_owned_requests(self):
        _validate_private_file_scopes(self.private_files, self.binding.principal,
            self.binding.candidate.sha256, complete=bool(self.private_files))
        _validate_relational_scopes(self.relational, self.binding.principal,
            self.binding.candidate.sha256, complete=bool(self.relational))
        _validate_checkpoint_scopes(self.checkpoints, self.binding.principal,
            self.binding.candidate.sha256, complete=bool(self.checkpoints))
        _validate_identity_scopes(self.identities, self.binding.principal,
            self.binding.candidate.sha256, complete=bool(self.identities))
        _validate_status_scopes(self.status_projections, self.binding.principal,
            self.binding.candidate.sha256, self.identities, complete=bool(self.status_projections))
        _validate_peer_read_scopes(self.peer_reads, self.binding.principal,
            self.binding.candidate.sha256, self.identities, self.status_projections, complete=True)
        return self


class PolicySubjectV10(PolicySubjectV9):
    subject_version: Literal[10]
    peer_reads: tuple[ResolvedPeerReadScope, ...] = Field(max_length=32)
    sessions: tuple[ResolvedSessionScope, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def exact_owned_requests(self):
        _validate_session_bundle(self, self.binding.principal, self.binding.candidate.sha256)
        return self


class CorePolicyEvidenceV1(PolicyModel):
    """Input contract for a FUTURE trusted, durable Core policy/evidence source.

    Constructing/parsing this model proves nothing. The record's origin,
    verification, revision lifecycle and freshness are the adapter's obligation.
    Rules are whole exact resolved scopes, never IDs interpreted as wildcards.
    """

    evidence_version: Literal[1]
    optional_resources: tuple[ResourceScope, ...] = Field(default=(), max_length=16)
    binding: PolicyBinding
    policy_revision: Identity
    trust_revision: Identity
    trust_class: Literal["reviewed_local_artifact", "administrator_approved_artifact", "unknown", "revoked"]
    execution_class: Literal["reviewed_native", "administrator_approved_native", "proven_isolated"]
    execution_profile: Identity
    profile_revision: Identity
    native_review_revision: Identity | None
    isolation_proof_revision: Identity | None
    commands: tuple[ResolvedCommandScope, ...] = Field(max_length=64)
    connectors: tuple[ResolvedConnectorScope, ...] = Field(max_length=32)
    required_scopes: tuple[ScopeKey, ...] = Field(max_length=96)

    @model_validator(mode="after")
    def coherent_rules(self):
        known = _scopes(self.commands, self.connectors, getattr(self, "events", ()), getattr(self, "publications", ()), getattr(self, "private_files", ()), getattr(self, "relational", ()), getattr(self, "checkpoints", ()), getattr(self, "identities", ()), getattr(self, "status_projections", ()), getattr(self, "peer_reads", ()), getattr(self, "sessions", ()), getattr(self, "tasks", ()))
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
    private_files: tuple[ResolvedPrivateFileScope, ...] = Field(max_length=4)
    required_scopes: tuple[StorageScopeKey, ...] = Field(max_length=132)

    @model_validator(mode="after")
    def exact_storage_rules(self):
        _validate_private_file_scopes(
            self.private_files, self.binding.principal, self.binding.candidate.sha256,
            complete=False,
        )
        return self


class CorePolicyEvidenceV5(CorePolicyEvidenceV3):
    evidence_version: Literal[5]
    private_files: tuple[ResolvedPrivateFileScope, ...] = Field(max_length=4)
    relational: tuple[ResolvedRelationalScope, ...] = Field(max_length=2)
    required_scopes: tuple[RelationalScopeKey, ...] = Field(max_length=134)

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


class CorePolicyEvidenceV6(CorePolicyEvidenceV3):
    evidence_version: Literal[6]
    private_files: tuple[ResolvedPrivateFileScope, ...] = Field(max_length=4)
    relational: tuple[ResolvedRelationalScope, ...] = Field(max_length=2)
    checkpoints: tuple[ResolvedCheckpointScope, ...] = Field(max_length=64)
    required_scopes: tuple[CheckpointScopeKey, ...] = Field(max_length=198)

    @model_validator(mode="after")
    def exact_owned_rules(self):
        _validate_private_file_scopes(
            self.private_files, self.binding.principal, self.binding.candidate.sha256,
            complete=False,
        )
        _validate_relational_scopes(
            self.relational, self.binding.principal, self.binding.candidate.sha256,
            complete=False,
        )
        _validate_checkpoint_scopes(
            self.checkpoints, self.binding.principal, self.binding.candidate.sha256,
            complete=False,
        )
        expected = {f"storage:relational_{s.operation}" for s in self.relational}
        required = {key for key in self.required_scopes if key.startswith("storage:relational_")}
        if required and required != expected:
            raise ValueError("Required policy must select the whole relational profile")
        return self


class CorePolicyEvidenceV7(CorePolicyEvidenceV6):
    evidence_version: Literal[7]
    identities: tuple[ResolvedIdentityScope, ...] = Field(max_length=1)
    required_scopes: tuple[IdentityScopeKey, ...] = Field(max_length=199)

    @model_validator(mode="after")
    def exact_identity_rules(self):
        _validate_identity_scopes(self.identities, self.binding.principal,
            self.binding.candidate.sha256, complete=False)
        return self


class CorePolicyEvidenceV8(CorePolicyEvidenceV7):
    evidence_version: Literal[8]
    status_projections: tuple[ResolvedStatusScope, ...] = Field(max_length=32)
    required_scopes: tuple[StatusScopeKey, ...] = Field(max_length=231)

    @model_validator(mode="after")
    def exact_status_rules(self):
        _validate_status_scopes(self.status_projections, self.binding.principal,
            self.binding.candidate.sha256, self.identities, complete=False)
        return self


class CorePolicyEvidenceV9(CorePolicyEvidenceV8):
    evidence_version: Literal[9]
    peer_reads: tuple[ResolvedPeerReadScope, ...] = Field(max_length=32)
    required_scopes: tuple[PeerScopeKey, ...] = Field(max_length=263)

    @model_validator(mode="after")
    def exact_peer_rules(self):
        _validate_peer_read_scopes(self.peer_reads, self.binding.principal,
            self.binding.candidate.sha256, self.identities, self.status_projections, complete=False)
        return self


class CorePolicyEvidenceV10(CorePolicyEvidenceV9):
    evidence_version: Literal[10]
    sessions: tuple[ResolvedSessionScope, ...] = Field(max_length=32)
    required_scopes: tuple[SessionScopeKey, ...] = Field(max_length=295)

    @model_validator(mode="after")
    def exact_session_rules(self):
        _validate_session_scopes(self.sessions, self.binding.principal,
            self.binding.candidate.sha256, complete=False)
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
    scope: SessionScopeKey | TaskScopeKey | None = None


class PolicyEvaluation(ContextModel):
    policy_resolved: bool
    policy: AuthorityPolicy | AuthorityPolicyV4 | AuthorityPolicyV5 | AuthorityPolicyV6 | AuthorityPolicyV7 | AuthorityPolicyV8 | AuthorityPolicyV9 | AuthorityPolicyV10 | AuthorityTaskPolicyV11 | None = None
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


def _scopes(commands, connectors, events=(), publications=(), private_files=(), relational=(), checkpoints=(), identities=(), status_projections=(), peer_reads=(), sessions=(), tasks=()):
    result = {}
    for prefix, scopes, name in (
        ("command", commands, "binding_id"),
        ("connector", connectors, "connector_id"),
        ("event", events, "subscription_id"),
        ("publication", publications, "publication_id"),
        ("task", tasks, "task_id"),
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
    for scope in checkpoints:
        key = f"checkpoint:{scope.declaration.checkpoint_id}:{scope.operation}"
        if key in result:
            raise ValueError("Scope identities must be unique")
        result[key] = scope
    for scope in identities:
        key = f"platform:{scope.operation}"
        if key in result:
            raise ValueError("Scope identities must be unique")
        result[key] = scope
    for scope in status_projections:
        key = f"status:{scope.link_id}:read"
        if key in result:
            raise ValueError("Scope identities must be unique")
        result[key] = scope
    for scope in peer_reads:
        key = f"peer:{scope.declaration.binding_id}:read"
        if key in result:
            raise ValueError("Scope identities must be unique")
        result[key] = scope
    for scope in sessions:
        key = f"session:{scope.declaration.binding_id}:open"
        if key in result:
            raise ValueError("Scope identities must be unique")
        result[key] = scope
    return result


def _scope_data(scope):
    """Match the context's typed/set semantics, not Python's 1 == 1.0 equality."""
    data = scope.model_dump(mode="json")
    declaration = data.get("declaration")
    if isinstance(scope, ResolvedCommandScope):
        declaration["arguments_schema"] = _command_schema_data(declaration["arguments_schema"])
    elif isinstance(scope, ResolvedConnectorScope):
        declaration["allowed_schemes"].sort()
    elif isinstance(scope, ResolvedStatusScope):
        for field in ("summary_fields", "node_ids", "node_fields"):
            data["consent"][field].sort()
    elif isinstance(scope, ResolvedSessionScope):
        declaration["control_actions"].sort()
        data["contract"]["access_modes"].sort()
        data["contract"]["control_actions"].sort()
    return data


def _adapter_revision(evidence):
    return {1: POLICY_ADAPTER_REVISION, 2: EVENT_POLICY_ADAPTER_REVISION,
        3: PUBLICATION_POLICY_ADAPTER_REVISION, 4: STORAGE_POLICY_ADAPTER_REVISION,
        5: RELATIONAL_POLICY_ADAPTER_REVISION, 6: CHECKPOINT_POLICY_ADAPTER_REVISION,
        7: IDENTITY_POLICY_ADAPTER_REVISION, 8: STATUS_POLICY_ADAPTER_REVISION,
        9: PEER_READ_POLICY_ADAPTER_REVISION, 10: SESSION_POLICY_ADAPTER_REVISION, 11: 11}[evidence.evidence_version]


def _policy_identity(evidence):
    data = evidence.model_dump(mode="json")
    if not data['optional_resources']: data.pop('optional_resources')
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
    if hasattr(evidence, "checkpoints"):
        data["checkpoints"] = [_scope_data(scope) for scope in sorted(
            evidence.checkpoints, key=lambda s: (s.declaration.checkpoint_id, s.operation))]
    if hasattr(evidence, "identities"):
        data["identities"] = [_scope_data(scope) for scope in sorted(
            evidence.identities, key=lambda s: s.operation)]
    if hasattr(evidence, "status_projections"):
        data["status_projections"] = [_scope_data(scope) for scope in sorted(
            evidence.status_projections, key=lambda s: s.link_id)]
    if hasattr(evidence, "peer_reads"):
        data["peer_reads"] = [_scope_data(scope) for scope in sorted(
            evidence.peer_reads, key=lambda s: s.declaration.binding_id)]
    if hasattr(evidence, "sessions"):
        data["sessions"] = [_scope_data(scope) for scope in sorted(
            evidence.sessions, key=lambda s: s.declaration.binding_id)]
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
    from backend.services.application_task_authority import TaskPolicySubjectV11, TaskPolicyEvidenceV11
    failures = (ValueError, TypeError, RecursionError, OverflowError)

    def failed(reason):
        return PolicyEvaluation(
            policy_resolved=False, issues=(PolicyIssue(reason=reason),)
        )

    try:
        subject = _parse_versioned(PolicySubjectV1, PolicySubjectV2, subject, "subject_version", PolicySubjectV3, PolicySubjectV4, PolicySubjectV5, PolicySubjectV6, PolicySubjectV7, PolicySubjectV8, PolicySubjectV9, PolicySubjectV10, TaskPolicySubjectV11)
        actual = _scopes(subject.commands, subject.connectors, getattr(subject, "events", ()), getattr(subject, "publications", ()), getattr(subject, "private_files", ()), getattr(subject, "relational", ()), getattr(subject, "checkpoints", ()), getattr(subject, "identities", ()), getattr(subject, "status_projections", ()), getattr(subject, "peer_reads", ()), getattr(subject, "sessions", ()), getattr(subject, "tasks", ()))
        actual_bytes = {
            key: _canonical_bytes(_scope_data(scope))
            for key, scope in actual.items()
        }
    except failures:
        return failed("invalid_policy_subject")
    issues = {(None, reason) for reason in subject.blockers}
    has_ui = subject.has_executable_frontend and bool(subject.binding.candidate.built_ui_sha256)
    if (subject.has_executable_frontend or subject.binding.candidate.built_ui_sha256) and not has_ui:
        issues.add((None, "frontend_authority_unresolved"))
    if evidence is None:
        issues.add((None, "trusted_policy_unavailable"))
    else:
        try:
            evidence = _parse_versioned(CorePolicyEvidenceV1, CorePolicyEvidenceV2, evidence, "evidence_version", CorePolicyEvidenceV3, CorePolicyEvidenceV4, CorePolicyEvidenceV5, CorePolicyEvidenceV6, CorePolicyEvidenceV7, CorePolicyEvidenceV8, CorePolicyEvidenceV9, CorePolicyEvidenceV10, TaskPolicyEvidenceV11)
            if evidence.evidence_version != subject.subject_version:
                raise ValueError("Policy versions must match")
            rules = _scopes(evidence.commands, evidence.connectors, getattr(evidence, "events", ()), getattr(evidence, "publications", ()), getattr(evidence, "private_files", ()), getattr(evidence, "relational", ()), getattr(evidence, "checkpoints", ()), getattr(evidence, "identities", ()), getattr(evidence, "status_projections", ()), getattr(evidence, "peer_reads", ()), getattr(evidence, "sessions", ()), getattr(evidence, "tasks", ()))
            rule_bytes = {
                key: _canonical_bytes(_scope_data(scope))
                for key, scope in rules.items()
            }
            identity = _policy_identity(evidence)
        except failures:
            # Never echo validation inputs, configured origins or secret references.
            issues.add((None, "invalid_trusted_policy"))
        else:
            if evidence.binding != subject.binding or evidence.optional_resources != subject.optional_resources:
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
                administrator_approved = evidence.execution_class == "administrator_approved_native"
                if (evidence.trust_class == "administrator_approved_artifact") != administrator_approved:
                    issues.add((None, "artifact_trust_unavailable"))
                prefix = "supervised_administrator_approved_native" if administrator_approved else "supervised_reviewed_native"
                expected_profile = prefix + ("_ui_v1" if has_ui else "_v1")
                if evidence.execution_profile != expected_profile:
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
                    policy=({4: AuthorityPolicyV4, 5: AuthorityPolicyV5, 6: AuthorityPolicyV6, 7: AuthorityPolicyV7, 8: AuthorityPolicyV8, 9: AuthorityPolicyV9, 10: AuthorityPolicyV10, 11: AuthorityTaskPolicyV11}.get(evidence.evidence_version, AuthorityPolicy))(
                        policy_revision=identity,
                        adapter_revision=_adapter_revision(evidence),
                        trust_revision=evidence.trust_revision,
                        execution_profile=evidence.execution_profile,
                        execution_class=evidence.execution_class,
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
