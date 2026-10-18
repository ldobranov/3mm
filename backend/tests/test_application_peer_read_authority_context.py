"""Pure internal v9 vectors. Exact matching is not authenticated approval."""

import base64
import copy
import hashlib
import json
import socket
import subprocess
from pathlib import Path

import pytest
import requests
from sqlalchemy.orm import Session

from backend.services.application_authority_context import (
    AuthorityReviewContextV8,
    AuthorityReviewContextV9,
    AuthoritySelectionV8,
    AuthoritySelectionV9,
    ResolvedPeerReadScope,
    _parse,
    _parse_versioned,
    review_authority_context,
)
from backend.services.application_authority_policy import (
    CorePolicyEvidenceV9,
    PolicySubjectV9,
    evaluate_authority_policy,
)
from backend.tests.test_application_authority_context import context, replace_path
from backend.tests.test_application_status_authority_context import (
    inputs as status_inputs,
)
from backend.tests.test_application_authority_policy import inputs as first_inputs
from backend.tests.test_application_file_authority_context import inputs as file_inputs
from backend.tests.test_application_relational_authority_context import (
    inputs as sql_inputs,
)
from backend.tests.test_application_checkpoint_authority_context import (
    inputs as checkpoint_inputs,
)
from backend.tests.test_application_identity_authority_context import (
    inputs as identity_inputs,
)
from backend.tests.test_installation_peer_read_sources import (
    current_peers,
    pair,
    pair_v2,
    read as read_source,
)
from three_mm_protocol.installation_peer_v2 import enrollment_metadata


READ = "peer:receiver:read"
FAMILIES = (
    "commands",
    "connectors",
    "events",
    "publications",
    "private_files",
    "relational",
    "checkpoints",
    "identities",
    "status_projections",
    "peer_reads",
)


def inputs(direction="outbound", wire=1, *, mixed=False):
    subject, evidence = status_inputs(mixed=mixed, with_identity=mixed)
    status = subject["status_projections"][0]
    resource = {
        "declaration": {
            "contract_version": 1,
            "binding_id": "receiver",
            "direction": direction,
            "peer_id_config_key": "RECEIVER_PEER_ID",
            "operations": ["read"],
        },
        **{
            name: copy.deepcopy(status[name])
            for name in (
                "owner",
                "package_artifact_sha256",
                "application_instance_id",
                "sender_identity",
                "receiver_identity",
                "origin",
                "target_module_id",
                "consent_revision",
                "consent",
            )
        },
        "service_artifact_sha256": "f" * 64,
        "peer_id": status["link_id"],
        "peer_version": wire,
        "enrollment_metadata": None,
    }
    if direction == "inbound":
        resource["sender_identity"], resource["receiver_identity"] = (
            resource["receiver_identity"],
            resource["sender_identity"],
        )
        resource["target_module_id"] = resource["owner"]["module_id"]
        if wire == 1:
            resource.update(consent=None, consent_revision=None)
    if wire == 2:
        metadata = enrollment_metadata("opaque_intent", resource["consent"], 1)
        resource.update(
            consent=metadata.consent.model_dump(mode="json"),
            enrollment_metadata=metadata.model_dump(mode="json"),
        )
    for value in (subject, evidence):
        value["peer_reads"] = [copy.deepcopy(resource)]
        if not mixed:
            for family in FAMILIES[:-1]:
                value[family] = []
    subject["subject_version"] = 9
    evidence["evidence_version"] = 9
    evidence["required_scopes"] = (
        [*evidence["required_scopes"], READ] if mixed else [READ]
    )
    return subject, evidence


def resolved_context(subject, evidence):
    result = evaluate_authority_policy(subject, evidence)
    assert result.policy_resolved, result.issues
    value = context()
    value.update(
        context_version=9,
        policy=result.policy.model_dump(mode="json"),
        **{
            name: copy.deepcopy(subject["binding"][name])
            for name in (
                "principal",
                "candidate",
                "baseline",
                "configuration",
            )
        },
        **{name: copy.deepcopy(subject[name]) for name in FAMILIES},
    )
    return value


def review(subject, evidence, scopes=None):
    value = resolved_context(subject, evidence)
    return review_authority_context(
        value,
        {
            "selection_version": 9,
            "scopes": value["policy"]["allowed_scopes"] if scopes is None else scopes,
        },
        now_ms=150_000,
    )


@pytest.mark.parametrize("direction", ["inbound", "outbound"])
@pytest.mark.parametrize("wire", [1, 2])
@pytest.mark.parametrize("mixed", [False, True])
def test_read_only_public_peer_context_roundtrips_without_approval(
    direction, wire, mixed
):
    subject, evidence = inputs(direction, wire, mixed=mixed)
    before = copy.deepcopy((subject, evidence))
    result = review(subject, evidence)
    assert result.reviewable and result.context_fingerprint
    assert result.permission_approval == "not_evaluated"
    typed = _parse(PolicySubjectV9, subject)
    assert _parse(PolicySubjectV9, typed) == typed
    assert _parse(ResolvedPeerReadScope, typed.peer_reads[0]) == typed.peer_reads[0]
    proof = _parse(CorePolicyEvidenceV9, evidence)
    assert _parse(CorePolicyEvidenceV9, proof) == proof
    policy = evaluate_authority_policy(typed, proof)
    assert policy.policy.adapter_revision == 9
    assert not policy.reviewable and policy.permission_approval == "not_evaluated"
    value = _parse(AuthorityReviewContextV9, resolved_context(subject, evidence))
    assert review_authority_context(
        value,
        {
            "selection_version": 9,
            "scopes": list(value.policy.allowed_scopes),
        },
        now_ms=150_000,
    ).reviewable
    assert (subject, evidence) == before


@pytest.mark.parametrize(
    "path,value",
    [
        (("owner", "core_installation_id"), "inst_" + "9" * 32),
        (("owner", "application_installation_id"), "foreign"),
        (("owner", "incarnation"), "reinstalled"),
        (("owner", "module_id"), "org.example.foreign"),
        (("package_artifact_sha256",), "e" * 64),
        (("service_artifact_sha256",), "not_a_digest"),
        (("application_instance_id",), "foreign"),
        (("peer_id",), "peer_*"),
        (("peer_id",), "peer_" + "A" * 32),
        (("peer_version",), True),
        (("peer_version",), 1.0),
        (("peer_version",), "1"),
        (("peer_version",), 3),
        (("declaration", "contract_version"), True),
        (("declaration", "operations"), ["read", "report"]),
        (("declaration", "operations"), ["read", "revoke"]),
        (("declaration", "operations"), ["enroll"]),
        (("declaration", "binding_id"), "*"),
        (("declaration", "peer_id_config_key"), "not_a_config_key"),
        (("origin",), "http://receiver.example"),
        (("origin",), "https://receiver.example/path"),
        (("origin",), "https://receiver.example:443"),
        (("target_module_id",), "invalid"),
        (("consent_revision",), True),
        (("consent_revision",), 1.0),
        (("consent_revision",), 0),
        (("consent_revision",), 2**53),
        (("consent_revision",), None),
        (("consent",), None),
        (("consent", "node_ids"), []),
        (("consent", "consent_version"), 1.0),
        (("consent", "consent_version"), True),
        (("consent", "node_fields"), ["credential"]),
        (("consent", "summary_fields"), "sdk_version"),
        (("sender_identity", "installation_id"), "inst_" + "9" * 32),
        (("receiver_identity", "key_id"), "0" * 64),
        (("receiver_identity", "key_generation"), 1.0),
        (("receiver_identity", "created_at"), "2026-01-01T00:00:00"),
        (("receiver_identity", "encrypted_private_key"), "PRIVATE"),
        (("credential",), "PRIVATE"),
        (("generation",), 1),
        (("state",), "active"),
        (("approval_expires_at",), "2099-01-01T00:00:00Z"),
        (("remote_binding_id",), "peer_" + "d" * 32),
        (("permission_approval",), "approved"),
        (("operation",), "installation.identity.prove"),
    ],
)
def test_invalid_or_widened_resource_cannot_be_a_pure_policy_subject(path, value):
    subject, evidence = inputs()
    replace_path(subject["peer_reads"][0], path, value)
    result = evaluate_authority_policy(subject, evidence)
    assert not result.policy_resolved and result.policy is None
    assert "PRIVATE" not in result.model_dump_json()


@pytest.mark.parametrize(
    "change",
    [
        "peer_id",
        "binding_id",
        "config_key",
        "direction",
        "service",
        "origin",
        "target",
        "consent_revision",
        "consent_selection",
        "instance",
        "remote_key",
    ],
)
def test_changed_valid_binding_is_not_an_old_exact_policy_rule(change):
    subject, evidence = inputs()
    resource = subject["peer_reads"][0]
    if change == "peer_id":
        resource["peer_id"] = "peer_" + "b" * 32
    elif change == "binding_id":
        resource["declaration"]["binding_id"] = "other"
    elif change == "config_key":
        resource["declaration"]["peer_id_config_key"] = "OTHER_PEER_ID"
    elif change == "direction":
        resource["declaration"]["direction"] = "inbound"
        resource["sender_identity"], resource["receiver_identity"] = (
            resource["receiver_identity"],
            resource["sender_identity"],
        )
        resource.update(
            target_module_id=resource["owner"]["module_id"],
            consent=None,
            consent_revision=None,
        )
    elif change == "service":
        resource["service_artifact_sha256"] = "e" * 64
    elif change == "origin":
        resource["origin"] = "https://changed.example"
    elif change == "target":
        resource["target_module_id"] = "org.example.changed"
    elif change == "consent_revision":
        resource["consent_revision"] = 2
    elif change == "consent_selection":
        resource["consent"]["node_fields"].remove("online")
    elif change == "instance":
        resource["application_instance_id"] = "b" * 24
    else:
        raw = b"c" * 32
        resource["receiver_identity"].update(
            public_key=base64.b64encode(raw).decode(),
            key_id=hashlib.sha256(raw).hexdigest(),
        )
    result = evaluate_authority_policy(subject, evidence)
    assert not result.policy_resolved
    assert {issue.reason for issue in result.issues} <= {
        "policy_scope_changed",
        "policy_scope_unavailable",
    }


@pytest.mark.parametrize(
    "path,value",
    [
        (("enrollment_metadata",), None),
        (("enrollment_metadata", "metadata_version"), True),
        (("enrollment_metadata", "metadata_version"), 2.0),
        (("enrollment_metadata", "consent_revision"), True),
        (("enrollment_metadata", "consent_revision"), 1.0),
        (("enrollment_metadata", "consent_revision"), 2**53),
        (("enrollment_metadata", "application_intent"), "changed"),
        (("enrollment_metadata", "metadata_hash"), "0" * 64),
        (("enrollment_metadata", "credential"), "PRIVATE"),
        (("enrollment_metadata", "consent", "consent_version"), 1.0),
        (("enrollment_metadata", "consent", "unknown"), []),
        (("enrollment_metadata", "consent", "node_ids"), []),
        (("consent_revision",), 2),
        (("consent", "node_fields"), ["online"]),
    ],
)
def test_v2_metadata_is_exact_typed_and_hash_bound(path, value):
    subject, evidence = inputs(wire=2)
    replace_path(subject["peer_reads"][0], path, value)
    assert not evaluate_authority_policy(subject, evidence).policy_resolved


def test_signed_metadata_is_not_silently_reordered_or_rehashed():
    subject, evidence = inputs(wire=2)
    subject["peer_reads"][0]["enrollment_metadata"]["consent"][
        "summary_fields"
    ].reverse()
    assert not evaluate_authority_policy(subject, evidence).policy_resolved


@pytest.mark.parametrize("direction", ["inbound", "outbound"])
def test_v1_cannot_invent_v2_metadata_or_reverse_its_local_role(direction):
    subject, evidence = inputs(direction)
    if direction == "inbound":
        subject["peer_reads"][0]["consent_revision"] = 1
    else:
        subject["peer_reads"][0]["enrollment_metadata"] = inputs(wire=2)[0][
            "peer_reads"
        ][0]["enrollment_metadata"]
    assert not evaluate_authority_policy(subject, evidence).policy_resolved
    subject, evidence = inputs(direction)
    resource = subject["peer_reads"][0]
    resource["receiver_identity"] = copy.deepcopy(resource["sender_identity"])
    assert not evaluate_authority_policy(subject, evidence).policy_resolved


def add_binding(value, index):
    resource = copy.deepcopy(value["peer_reads"][0])
    resource["declaration"].update(
        binding_id=f"peer_{index}", peer_id_config_key=f"PEER_{index}"
    )
    resource["peer_id"] = "peer_" + f"{index:032x}"
    value["peer_reads"].append(resource)
    return resource


@pytest.mark.parametrize(
    "change", ["alias", "reference", "logical", "instance", "service", "local_identity"]
)
def test_complete_family_cannot_mix_aliases_instances_service_or_local_identity(change):
    subject, evidence = inputs()
    for value in (subject, evidence):
        first = value["peer_reads"][0]
        second = add_binding(value, 2)
        if change == "alias":
            second["peer_id"] = first["peer_id"]
        elif change == "reference":
            second["declaration"]["peer_id_config_key"] = first["declaration"][
                "peer_id_config_key"
            ]
        elif change == "logical":
            second["declaration"]["binding_id"] = first["declaration"]["binding_id"]
        elif change == "instance":
            second["application_instance_id"] = "b" * 24
        elif change == "service":
            second["service_artifact_sha256"] = "e" * 64
        else:
            second["sender_identity"]["created_at"] = "2026-01-02T00:00:00Z"
    assert not evaluate_authority_policy(subject, evidence).policy_resolved


@pytest.mark.parametrize(
    "change",
    [
        "identity",
        "status_identity",
        "status_instance",
        "status_consent",
        "status_remote",
        "status_origin",
    ],
)
def test_mixed_identity_status_and_peer_resources_must_agree(change):
    subject, evidence = inputs(mixed=True)
    for value in (subject, evidence):
        if change == "identity":
            value["identities"][0]["identity"]["created_at"] = "2026-01-02T00:00:00Z"
        elif change == "status_identity":
            value["status_projections"][0]["sender_identity"][
                "created_at"
            ] = "2026-01-02T00:00:00Z"
        elif change == "status_instance":
            value["status_projections"][0]["application_instance_id"] = "b" * 24
        elif change == "status_consent":
            value["status_projections"][0]["consent_revision"] += 1
        elif change == "status_remote":
            value["status_projections"][0]["receiver_identity"]["installation_id"] = (
                "inst_" + "9" * 32
            )
        else:
            value["status_projections"][0]["origin"] = "https://changed.example"
    assert not evaluate_authority_policy(subject, evidence).policy_resolved


def test_canonical_sets_ignore_order_but_exact_binding_changes_fingerprint():
    subject, evidence = inputs()
    for value in (subject, evidence):
        add_binding(value, 2)
    old = review(subject, evidence).context_fingerprint
    for value in (subject, evidence):
        value["peer_reads"].reverse()
        value["peer_reads"][0]["consent"]["node_fields"].reverse()
        value["peer_reads"][0]["consent"]["summary_fields"].reverse()
    assert review(subject, evidence).context_fingerprint == old
    for value in (subject, evidence):
        value["peer_reads"][0]["consent_revision"] += 1
    assert review(subject, evidence).context_fingerprint != old


def test_empty_or_subset_policy_rules_never_mean_all_peers():
    subject, evidence = inputs()
    for value in (subject, evidence):
        add_binding(value, 2)
    evidence["required_scopes"] = []
    evidence["peer_reads"] = evidence["peer_reads"][:1]
    assert review(subject, evidence, [READ]).reviewable
    assert not review(subject, evidence, ["peer:peer_2:read"]).reviewable
    evidence["peer_reads"] = []
    assert review(subject, evidence, []).reviewable
    assert not review(subject, evidence, [READ]).reviewable
    assert not evaluate_authority_policy(subject).policy_resolved


@pytest.mark.parametrize("version", [True, 9.0, "9", 8])
def test_internal_version_is_not_an_upgrade_hint(version):
    subject, evidence = inputs()
    assert not evaluate_authority_policy(
        {**subject, "subject_version": version}, evidence
    ).policy_resolved
    assert not evaluate_authority_policy(
        subject, {**evidence, "evidence_version": version}
    ).policy_resolved
    value = resolved_context(subject, evidence)
    assert not review_authority_context(
        {**value, "context_version": version},
        {
            "selection_version": 9,
            "scopes": [READ],
        },
        now_ms=150_000,
    ).reviewable


@pytest.mark.parametrize(
    "scope",
    [
        "peer:*:read",
        "peer:receiver:write",
        "peer:receiver:enroll",
        "peer:receiver:rotate",
        "peer:receiver:report",
        "peer:receiver:approve",
        "peer:receiver:revoke",
        "platform:installation.peers.enroll",
        "platform:installation.identity.prove",
        "peer:receiver",
        "peer:receiver:read:extra",
    ],
)
def test_read_scope_vocabulary_cannot_sign_mutate_discover_or_use_a_wildcard(scope):
    with pytest.raises(ValueError):
        _parse(AuthoritySelectionV9, {"selection_version": 9, "scopes": [scope]})


def test_old_context_and_selection_do_not_inherit_peer_read_authority():
    with pytest.raises(ValueError):
        _parse(AuthoritySelectionV8, {"selection_version": 8, "scopes": [READ]})
    subject, evidence = inputs(mixed=True)
    value = resolved_context(subject, evidence)
    value["context_version"] = 8
    with pytest.raises(ValueError):
        _parse(AuthorityReviewContextV8, value)
    # Existing manager/sealed-grant consumers must opt in to v9 explicitly.
    # Merely adding a pure evaluator version cannot widen those entry points.
    with pytest.raises(ValueError):
        _parse_versioned(
            None,
            None,
            {"selection_version": 9, "scopes": [READ]},
            "selection_version",
            v8=AuthoritySelectionV8,
        )


@pytest.mark.parametrize("count", [0, 32, 33])
def test_family_limit_is_exact_without_truncation(count):
    subject, evidence = inputs()
    for value in (subject, evidence):
        for index in range(1, count):
            add_binding(value, index)
        if not count:
            value["peer_reads"] = []
    assert evaluate_authority_policy(subject, evidence).policy_resolved is (count == 32)
    if count == 32:
        assert review(subject, evidence).reviewable


def test_constructed_models_cannot_smuggle_private_or_unsupported_fields():
    subject, evidence = inputs()
    typed = _parse(PolicySubjectV9, subject)
    widened = typed.peer_reads[0].declaration.model_copy(
        update={"operations": ("read", "revoke")}
    )
    unsafe = typed.model_copy(
        update={
            "peer_reads": (
                typed.peer_reads[0].model_copy(update={"declaration": widened}),
            )
        }
    )
    assert not evaluate_authority_policy(unsafe, evidence).policy_resolved
    forged = typed.peer_reads[0].receiver_identity.model_copy(
        update={"created_at": object()}
    )
    unsafe = typed.model_copy(
        update={
            "peer_reads": (
                typed.peer_reads[0].model_copy(update={"receiver_identity": forged}),
            )
        }
    )
    assert not evaluate_authority_policy(unsafe, evidence).policy_resolved


def test_expiry_source_blockers_and_native_trust_are_not_bypassed_by_public_pins():
    subject, evidence = inputs()
    value = resolved_context(subject, evidence)
    assert not review_authority_context(
        value, {"selection_version": 9, "scopes": [READ]}, now_ms=value["expires_at_ms"]
    ).reviewable
    for blocker in (
        "peer_authority_unresolved",
        "unsupported_scope_family",
        "frontend_authority_unresolved",
    ):
        assert not evaluate_authority_policy(
            {**subject, "blockers": [blocker]}, evidence
        ).policy_resolved
    for field, content in (
        ("trust_class", "revoked"),
        ("native_review_revision", None),
        ("execution_class", "proven_isolated"),
    ):
        assert not evaluate_authority_policy(
            subject, {**evidence, field: content}
        ).policy_resolved


@pytest.mark.parametrize(
    "field,value",
    [
        ("recovery_generation", "2" * 32),
        ("configuration", {"key_id": "new_key", "keyed_sha256": "c" * 64}),
    ],
)
def test_changed_keyed_configuration_or_recovery_identity_cannot_reuse_evidence(
    field, value
):
    subject, evidence = inputs()
    subject["binding"][field] = value
    result = evaluate_authority_policy(subject, evidence)
    assert not result.policy_resolved
    assert "policy_binding_changed" in {issue.reason for issue in result.issues}


def test_v2_new_valid_intent_and_hash_require_a_new_exact_policy_and_fingerprint():
    subject, evidence = inputs(wire=2)
    old = review(subject, evidence).context_fingerprint
    resource = subject["peer_reads"][0]
    resource["enrollment_metadata"] = enrollment_metadata(
        "new_intent", resource["consent"], 1
    ).model_dump(mode="json")
    result = evaluate_authority_policy(subject, evidence)
    assert not result.policy_resolved
    assert "policy_scope_changed" in {issue.reason for issue in result.issues}
    evidence["peer_reads"] = copy.deepcopy(subject["peer_reads"])
    assert review(subject, evidence).context_fingerprint != old


def test_whole_context_byte_budget_refuses_legal_individual_resources_without_truncation():
    subject, evidence = inputs(wire=2)
    for value in (subject, evidence):
        for index in range(1, 32):
            add_binding(value, index)
        for resource in value["peer_reads"]:
            resource["consent"]["node_ids"] = [
                "dev_" + f"{index:032x}" for index in range(64)
            ]
            metadata = enrollment_metadata("opaque_intent", resource["consent"], 1)
            resource["consent"] = metadata.consent.model_dump(mode="json")
            resource["enrollment_metadata"] = metadata.model_dump(mode="json")
            assert _parse(ResolvedPeerReadScope, resource)
    assert not evaluate_authority_policy(subject, evidence).policy_resolved


def test_pure_peer_context_and_policy_perform_no_io_or_implicit_clock(monkeypatch):
    subject, evidence = inputs("inbound", 2, mixed=True)
    value = resolved_context(subject, evidence)

    def forbidden(*args, **kwargs):
        raise AssertionError("Pure peer authority cannot perform I/O")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Session, "execute", forbidden)
        patch.setattr(Session, "commit", forbidden)
        patch.setattr(socket, "socket", forbidden)
        patch.setattr(requests, "request", forbidden)
        patch.setattr(subprocess, "run", forbidden)
        assert evaluate_authority_policy(subject, evidence).policy_resolved
        assert review_authority_context(
            json.dumps(value),
            {
                "selection_version": 9,
                "scopes": value["policy"]["allowed_scopes"],
            },
            now_ms=150_000,
        ).reviewable


def test_real_signed_source_binding_is_the_same_strict_context_resource(current_peers):
    state = current_peers
    for core in (state.sender, state.receiver):
        source = read_source(core)[0]
        resource = source.binding
        assert isinstance(resource, ResolvedPeerReadScope)
        subject, evidence = inputs()
        subject["binding"].update(
            principal=resource.owner.model_dump(mode="json"),
            candidate={
                "version": core.prepared.manifest.version,
                "sha256": core.prepared.sha256,
            },
        )
        evidence["binding"] = copy.deepcopy(subject["binding"])
        scope = f"peer:{resource.declaration.binding_id}:read"
        for value in (subject, evidence):
            value["peer_reads"] = [resource.model_dump(mode="json")]
        evidence["required_scopes"] = [scope]
        result = review(subject, evidence)
        assert result.reviewable and result.permission_approval == "not_evaluated"
        assert (
            source.reviewable is False and source.permission_approval == "not_evaluated"
        )
        # Observation changes cannot be smuggled into permission identity.
        subject["peer_reads"][0]["observation"] = source.observation.model_dump(
            mode="json"
        )
        assert not evaluate_authority_policy(subject, evidence).policy_resolved


# Captured from the previous native source checkout BEFORE the internal-v9
# change. These are format stability vectors, not credentials or approvals.
LEGACY_VECTORS = (
    (
        "policy_c019c218c58bb994457092c8c60a4f3520db9ed1350494f35952d0be2e940171",
        "9262aed31fb2e8f1ca7d79531fcf7ba1207aed84d1798b8a3013952ea45727a9",
    ),
    (
        "policy_8575b6e0de40ffe4915a0c058f070b8b2b1696f9923f3b6fe9e2dee9da49efb3",
        "1f9f1d9c03c2a87ac2883754694b35ac7ac6102d859898fc63c5fb96469f1c3b",
    ),
    (
        "policy_10668b58cbf88e603dd95bf1a132c5db02d267b4a34b43fb07ac7a250ec7a4db",
        "016aa1a88636fba8070a9768dfd24262fa7177152d0afa99f6a97cce32228a7d",
    ),
    (
        "policy_b21eb3ff216925d68a7dcca0752a4129065c722e05ce06616b85a4d8857b7457",
        "914c277ca069af3a55e63e349bd06a0337b924cc25d26ce288c3e40eb23856e8",
    ),
    (
        "policy_f5d2ac9054b01a524d3fc16ad84d39df506b7631c3ffec1575a589594b5e6b43",
        "8550c4df94f00cef3afe4002e1b0223d8a79cffa002860af4c04178a6443c122",
    ),
    (
        "policy_a54773b4064c35f11b405868b4da8730e347f15a4020d697ed76b8ec94b78279",
        "55a5cd571472ff1a03846f1b5d3ad442bf06eed5299a726a8583f3270d9cd9a6",
    ),
    (
        "policy_cf5d1c68cd6c58e253fc0958a7d5ec340805bbbf61659cdb86f4b6a2c2c9f16f",
        "04813a8535cb8a931886159f41c21629049635b90a174072e1064013348bafec",
    ),
    (
        "policy_4d420dca219bf576555e0f19514cd36aafbe1ebb8dcc4f09a3ccabb215fb8fbf",
        "c33e013973bb5d612a8a7f54f6970a058b6e6b56023482e7c0f4583aa9110178",
    ),
)


@pytest.mark.parametrize("version", range(1, 9))
def test_versions_1_through_8_keep_their_existing_policy_and_context_bytes(version):
    if version < 4:
        subject, evidence = first_inputs()
        subject["subject_version"] = evidence["evidence_version"] = version
        if version > 1:
            subject["events"] = evidence["events"] = []
        if version > 2:
            subject["publications"] = evidence["publications"] = []
    else:
        subject, evidence = {
            4: file_inputs,
            5: sql_inputs,
            6: checkpoint_inputs,
            7: identity_inputs,
            8: status_inputs,
        }[version]()
    policy = evaluate_authority_policy(subject, evidence)
    assert policy.policy_resolved
    value = context()
    value.update(
        context_version=version,
        policy=policy.policy.model_dump(mode="json"),
        **{
            name: copy.deepcopy(subject["binding"][name])
            for name in (
                "principal",
                "candidate",
                "baseline",
                "configuration",
            )
        },
    )
    for name in FAMILIES[:-1]:
        if name in subject:
            value[name] = copy.deepcopy(subject[name])
    result = review_authority_context(
        value,
        {"selection_version": version, "scopes": list(policy.policy.allowed_scopes)},
        now_ms=150_000,
    )
    assert result.reviewable
    assert (
        policy.policy.policy_revision,
        result.context_fingerprint,
    ) == LEGACY_VECTORS[version - 1]
