"""Internal v8 exact local projections; old canonical/context versions stay closed."""

import base64
import copy
import hashlib

import pytest

from backend.services.application_authority_context import (
    AuthorityReviewContextV8,
    AuthoritySelectionV7,
    AuthoritySelectionV8,
    ResolvedStatusScope,
    _parse,
    review_authority_context,
)
from backend.services.application_authority_policy import (
    PolicySubjectV8,
    evaluate_authority_policy,
)
from backend.tests.test_application_authority_context import context, replace_path
from backend.tests.test_application_identity_authority_context import (
    inputs as identity_inputs,
)


LINK = "peer_" + "a" * 32
READ = f"status:{LINK}:read"
NODE = "dev_" + "1" * 32


def inputs(mixed=False, with_identity=False):
    subject, evidence = identity_inputs(mixed)
    raw = b"r" * 32
    resource = {
        "owner": copy.deepcopy(subject["binding"]["principal"]),
        "package_artifact_sha256": subject["binding"]["candidate"]["sha256"],
        "operation": "installation.status.read",
        "link_id": LINK,
        "application_instance_id": "a" * 24,
        "sender_identity": copy.deepcopy(subject["identities"][0]["identity"]),
        "receiver_identity": {
            "identity_version": 1,
            "installation_id": "inst_" + "8" * 32,
            "algorithm": "ed25519",
            "key_id": hashlib.sha256(raw).hexdigest(),
            "public_key": base64.b64encode(raw).decode(),
            "key_generation": 1,
            "created_at": "2026-01-01T00:00:00Z",
        },
        "origin": "https://receiver.example",
        "target_module_id": "org.example.receiver",
        "consent_revision": 1,
        "consent": {
            "consent_version": 1,
            "summary_fields": ["sdk_version", "core_version"],
            "node_ids": [NODE],
            "node_fields": ["online", "display_name"],
        },
    }
    subject.update(subject_version=8, status_projections=[resource])
    evidence.update(evidence_version=8, status_projections=[copy.deepcopy(resource)])
    if not with_identity:
        subject["identities"] = evidence["identities"] = []
        evidence["required_scopes"].remove("platform:installation.identity.read")
    evidence["required_scopes"].append(READ)
    return subject, evidence


def resolved_context(subject, evidence):
    policy = evaluate_authority_policy(subject, evidence)
    assert policy.policy_resolved, policy.issues
    value = context()
    value.update(
        context_version=8,
        policy=policy.policy.model_dump(mode="json"),
        **{
            name: copy.deepcopy(subject["binding"][name])
            for name in ("principal", "candidate", "baseline", "configuration")
        },
        **{
            name: copy.deepcopy(subject[name])
            for name in (
                "commands",
                "connectors",
                "events",
                "publications",
                "private_files",
                "relational",
                "checkpoints",
                "identities",
                "status_projections",
            )
        },
    )
    return value


def review(subject, evidence):
    value = resolved_context(subject, evidence)
    return review_authority_context(
        value,
        {"selection_version": 8, "scopes": list(value["policy"]["allowed_scopes"])},
        now_ms=150_000,
    )


@pytest.mark.parametrize(
    "mixed,with_identity", [(False, False), (False, True), (True, True)]
)
def test_status_context_exact_public_bindings_and_typed_datetime_roundtrip(
    mixed, with_identity
):
    subject, evidence = inputs(mixed, with_identity)
    old = copy.deepcopy((subject, evidence))
    result = review(subject, evidence)
    assert result.reviewable and result.context_fingerprint
    assert result.permission_approval == "not_evaluated" and (subject, evidence) == old
    typed = _parse(PolicySubjectV8, subject)
    assert _parse(PolicySubjectV8, typed) == typed
    resource = typed.status_projections[0]
    assert _parse(ResolvedStatusScope, resource) == resource
    value = _parse(AuthorityReviewContextV8, resolved_context(subject, evidence))
    assert review_authority_context(
        value,
        {"selection_version": 8, "scopes": list(value.policy.allowed_scopes)},
        now_ms=150_000,
    ).reviewable
    assert value.policy.adapter_revision == 8


@pytest.mark.parametrize(
    "path,value",
    [
        (("owner", "core_installation_id"), "inst_" + "9" * 32),
        (("owner", "application_installation_id"), "foreign"),
        (("owner", "incarnation"), "reinstalled"),
        (("package_artifact_sha256",), "e" * 64),
        (("link_id",), "peer_*"),
        (("application_instance_id",), "foreign"),
        (("operation",), "installation.peers.report"),
        (("origin",), "http://receiver.example"),
        (("origin",), "https://receiver.example/path"),
        (("origin",), "https://receiver.example:443"),
        (("target_module_id",), "invalid"),
        (("consent_revision",), True),
        (("consent_revision",), 1.0),
        (("consent_revision",), 0),
        (("credential",), "never"),
        (("consent", "node_fields"), ["credential"]),
        (("consent", "node_ids"), [NODE, NODE]),
        (("consent", "consent_version"), True),
        (("consent", "consent_version"), 1.0),
        (("consent", "unknown"), []),
        (("consent", "node_ids"), []),
        (("consent", "summary_fields"), "core_version"),
        (("sender_identity", "installation_id"), "inst_" + "9" * 32),
        (("receiver_identity", "key_id"), "0" * 64),
        (("receiver_identity", "key_generation"), 1.0),
        (("receiver_identity", "encrypted_private_key"), "never"),
        (("receiver_identity", "created_at"), "2026-01-01T00:00:00"),
    ],
)
def test_foreign_unbounded_coerced_or_wider_status_context_fails_closed(path, value):
    subject, evidence = inputs()
    replace_path(subject["status_projections"][0], path, value)
    assert not evaluate_authority_policy(subject, evidence).policy_resolved


@pytest.mark.parametrize(
    "change", ["receiver", "origin", "revision", "selection", "instance"]
)
def test_valid_changed_pin_is_not_an_old_policy_rule(change):
    subject, evidence = inputs()
    resource = subject["status_projections"][0]
    if change == "receiver":
        resource["receiver_identity"]["installation_id"] = "inst_" + "9" * 32
    elif change == "origin":
        resource["origin"] = "https://new.example"
    elif change == "revision":
        resource["consent_revision"] += 1
    elif change == "instance":
        resource["application_instance_id"] = "b" * 24
    else:
        resource["consent"]["node_fields"].remove("online")
    result = evaluate_authority_policy(subject, evidence)
    assert not result.policy_resolved and "policy_scope_changed" in {
        issue.reason for issue in result.issues
    }


def test_status_consent_sets_are_order_independent_but_exact_content_changes_fingerprint():
    subject, evidence = inputs()
    old = review(subject, evidence).context_fingerprint
    for value in (subject, evidence):
        value["status_projections"][0]["consent"]["summary_fields"].reverse()
        value["status_projections"][0]["consent"]["node_fields"].reverse()
    assert review(subject, evidence).context_fingerprint == old
    for value in (subject, evidence):
        value["status_projections"][0]["consent_revision"] += 1
    assert review(subject, evidence).context_fingerprint != old


def test_status_bindings_require_one_sender_instance_and_no_self_receiver():
    subject, evidence = inputs(with_identity=True)
    for value in (subject, evidence):
        extra = copy.deepcopy(value["status_projections"][0])
        extra.update(link_id="peer_" + "b" * 32, application_instance_id="b" * 24)
        value["status_projections"].append(extra)
    assert not evaluate_authority_policy(subject, evidence).policy_resolved
    subject, evidence = inputs(with_identity=True)
    subject["status_projections"][0]["receiver_identity"] = copy.deepcopy(
        subject["status_projections"][0]["sender_identity"]
    )
    assert not evaluate_authority_policy(subject, evidence).policy_resolved
    subject, evidence = inputs(with_identity=True)
    subject["status_projections"][0]["sender_identity"][
        "created_at"
    ] = "2026-01-02T00:00:00Z"
    assert not evaluate_authority_policy(subject, evidence).policy_resolved


@pytest.mark.parametrize("count", [0, 33])
def test_status_binding_set_is_complete_unique_and_bounded(count):
    subject, evidence = inputs()
    template = subject["status_projections"][0]
    subject["status_projections"] = [
        {**copy.deepcopy(template), "link_id": "peer_" + f"{index:032x}"}
        for index in range(count)
    ]
    assert not evaluate_authority_policy(subject, evidence).policy_resolved


def test_old_versions_wildcards_and_reporting_are_not_status_authority():
    subject, evidence = inputs()
    for scope in (
        "platform:installation.status.read",
        "status:*:read",
        f"status:{LINK}:write",
        "platform:installation.peers.report",
    ):
        with pytest.raises(ValueError):
            _parse(AuthoritySelectionV8, {"selection_version": 8, "scopes": [scope]})
    with pytest.raises(ValueError):
        _parse(AuthoritySelectionV7, {"selection_version": 7, "scopes": [READ]})
    for version in (True, 8.0, "8", 7):
        changed = {**subject, "subject_version": version}
        assert not evaluate_authority_policy(changed, evidence).policy_resolved
    evidence.update(status_projections=[], required_scopes=["command:pulse"])
    value = resolved_context(subject, evidence)
    denied = review_authority_context(
        value, {"selection_version": 8, "scopes": [READ]}, now_ms=150_000
    )
    assert not denied.reviewable and "scope_not_allowed" in {
        issue.reason for issue in denied.issues
    }
