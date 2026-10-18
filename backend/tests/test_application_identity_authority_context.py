"""Pure public-identity read vectors; no possession proof or live grant."""

import base64
import copy
import hashlib

import pytest

from backend.services.application_authority_context import (
    AuthorityReviewContextV7, AuthoritySelectionV6, AuthoritySelectionV7, ResolvedIdentityScope,
    _parse, review_authority_context,
)
from backend.services.application_authority_policy import PolicySubjectV7, evaluate_authority_policy
from backend.tests.test_application_authority_context import context, replace_path
from backend.tests.test_application_authority_policy import inputs as command_inputs
from backend.tests.test_application_checkpoint_authority_context import inputs as checkpoint_inputs


READ = "platform:installation.identity.read"
CORE = "inst_" + "7" * 32


def inputs(mixed=False):
    subject, evidence = checkpoint_inputs(mixed=True) if mixed else command_inputs()
    for value in (subject, evidence):
        value["binding"]["principal"]["core_installation_id"] = CORE
        for connector in value["connectors"]:
            connector["stored"]["owner"]["core_installation_id"] = CORE
            if connector["stored"]["credential"]:
                connector["stored"]["credential"]["owner"]["core_installation_id"] = CORE
        for family in ("private_files", "relational", "checkpoints"):
            for resource in value.get(family, []):
                resource["owner"]["core_installation_id"] = CORE
    raw = b"a" * 32
    resources = [{
        "owner": copy.deepcopy(subject["binding"]["principal"]),
        "package_artifact_sha256": subject["binding"]["candidate"]["sha256"],
        "operation": "installation.identity.read",
        "identity": {"identity_version": 1, "algorithm": "ed25519", "installation_id": CORE,
            "key_id": hashlib.sha256(raw).hexdigest(), "public_key": base64.b64encode(raw).decode(),
            "key_generation": 1, "created_at": "2026-01-01T00:00:00Z"},
    }]
    subject.update(subject_version=7, identities=resources)
    evidence.update(evidence_version=7, identities=copy.deepcopy(resources))
    for value in (subject, evidence):
        for family in ("events", "publications", "private_files", "relational", "checkpoints"):
            value.setdefault(family, [])
    evidence["required_scopes"].append(READ)
    return subject, evidence


def resolved_context(subject, evidence):
    result = evaluate_authority_policy(subject, evidence)
    assert result.policy_resolved, result.issues
    current = context()
    current.update(context_version=7, policy=result.policy.model_dump(mode="json"),
        **{key: copy.deepcopy(subject["binding"][key]) for key in ("principal", "candidate", "baseline", "configuration")},
        **{family: copy.deepcopy(subject[family]) for family in
            ("commands", "connectors", "events", "publications", "private_files", "relational", "checkpoints", "identities")})
    return current


def selected(*scopes):
    return {"selection_version": 7, "scopes": list(scopes)}


@pytest.mark.parametrize("mixed", [False, True])
def test_exact_identity_read_context_mixes_with_existing_families_without_approval(mixed):
    subject, evidence = inputs(mixed)
    before = copy.deepcopy((subject, evidence))
    policy = evaluate_authority_policy(subject, evidence)
    assert policy.policy.adapter_revision == 7
    current = resolved_context(subject, evidence)
    result = review_authority_context(current, selected(*policy.policy.allowed_scopes), now_ms=150_000)
    assert result.reviewable and result.context_fingerprint
    assert result.permission_approval == policy.permission_approval == "not_evaluated"
    assert not policy.reviewable and (subject, evidence) == before
    assert _parse(AuthorityReviewContextV7, current).identities[0].identity.installation_id == CORE


@pytest.mark.parametrize("path,value", [
    (("owner", "core_installation_id"), "inst_" + "8" * 32),
    (("owner", "application_installation_id"), "foreign_app"),
    (("owner", "incarnation"), "reinstalled"),
    (("owner", "module_id"), "org.example.foreign"),
    (("package_artifact_sha256",), "f" * 64),
    (("operation",), "installation.identity.prove"),
    (("operation",), "installation.peers.receive"),
    (("path",), "/var/lib/3mm/identity"),
    (("private_key",), "never"),
    (("identity", "installation_id"), "inst_" + "8" * 32),
    (("identity", "key_id"), "f" * 64),
    (("identity", "public_key"), "not_base64"),
    (("identity", "identity_version"), True),
    (("identity", "identity_version"), 1.0),
    (("identity", "key_generation"), 1.0),
    (("identity", "key_generation"), 2),
    (("identity", "algorithm"), "rsa"),
    (("identity", "created_at"), "not-a-timestamp"),
    (("identity", "created_at"), "2026-01-01T00:00:00"),
    (("identity", "encrypted_private_key"), "never"),
])
def test_wrong_owner_identity_or_extra_authority_never_becomes_a_context(path, value):
    subject, evidence = inputs()
    replace_path(subject["identities"][0], path, value)
    assert not evaluate_authority_policy(subject, evidence).policy_resolved


def test_policy_without_identity_rule_never_supplies_read_or_proof_authority():
    subject, evidence = inputs()
    evidence.update(identities=[], required_scopes=["command:pulse"])
    current = resolved_context(subject, evidence)
    assert review_authority_context(current, selected("command:pulse"), now_ms=150_000).reviewable
    denied = review_authority_context(current, selected("command:pulse", READ), now_ms=150_000)
    assert {item.reason for item in denied.issues} == {"scope_not_allowed"}
    for scope in ("platform:installation.identity.prove", "platform:installation.peers.receive", "platform:installation.status.read", "platform:*"):
        with pytest.raises(ValueError):
            _parse(AuthoritySelectionV7, selected(scope))
    with pytest.raises(ValueError):
        _parse(AuthoritySelectionV6, {"selection_version": 6, "scopes": [READ]})


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "changed_time", "changed_key"])
def test_identity_pin_count_or_content_change_invalidates_exact_policy(mutation):
    subject, evidence = inputs()
    if mutation == "missing":
        subject["identities"] = []
    elif mutation == "duplicate":
        subject["identities"].append(copy.deepcopy(subject["identities"][0]))
    elif mutation == "changed_time":
        subject["identities"][0]["identity"]["created_at"] = "2026-01-02T00:00:00Z"
    else:
        raw = b"b" * 32
        subject["identities"][0]["identity"].update(
            public_key=base64.b64encode(raw).decode(), key_id=hashlib.sha256(raw).hexdigest())
    assert not evaluate_authority_policy(subject, evidence).policy_resolved


def test_fresh_identity_pin_has_a_new_fingerprint_but_not_a_permission():
    subject, evidence = inputs()
    current = resolved_context(subject, evidence)
    old = review_authority_context(current, selected("command:pulse", READ), now_ms=150_000)
    for value in (subject, evidence):
        value["identities"][0]["identity"]["created_at"] = "2026-01-02T00:00:00Z"
    changed = resolved_context(subject, evidence)
    new = review_authority_context(changed, selected("command:pulse", READ), now_ms=150_000)
    assert old.context_fingerprint != new.context_fingerprint and new.reviewable
    assert not evaluate_authority_policy(subject).policy_resolved
    assert not review_authority_context(changed, selected("command:pulse", READ), now_ms=changed["expires_at_ms"]).reviewable
    for version in (True, 7.0, "7", 6):
        assert not review_authority_context({**changed, "context_version": version}, selected(READ), now_ms=150_000).reviewable


def test_typed_identity_subject_context_and_resource_roundtrip_revalidates_public_datetime():
    subject, evidence = inputs(mixed=True)
    typed = _parse(PolicySubjectV7, subject)
    assert _parse(PolicySubjectV7, typed) == typed
    resource = typed.identities[0]
    assert _parse(ResolvedIdentityScope, resource) == resource
    assert evaluate_authority_policy(typed, evidence).policy_resolved
    current = _parse(AuthorityReviewContextV7, resolved_context(subject, evidence))
    chosen = selected(*current.policy.allowed_scopes)
    assert review_authority_context(current, chosen, now_ms=150_000).reviewable
