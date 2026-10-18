"""Pure exact checkpoint review vectors, never signed grants or stored values."""

import copy

import pytest

from backend.services.application_authority_context import (
    AuthorityReviewContextV6,
    AuthoritySelectionV5,
    AuthoritySelectionV6,
    _parse,
    review_authority_context,
)
from backend.services.application_authority_policy import evaluate_authority_policy
from backend.tests.test_application_authority_context import context, replace_path
from backend.tests.test_application_authority_policy import inputs as command_inputs
from backend.tests.test_application_relational_authority_context import inputs as relational_inputs


READ = "checkpoint:progress:read"
WRITE = "checkpoint:progress:write"


def inputs(mode="read_write", mixed=False):
    subject, evidence = relational_inputs(files=True) if mixed else command_inputs()
    resources = [
        {
            "declaration": {
                "contract_version": 1, "checkpoint_id": "progress", "mode": mode,
                "max_value_bytes": 1024,
            },
            "owner": copy.deepcopy(subject["binding"]["principal"]),
            "package_artifact_sha256": subject["binding"]["candidate"]["sha256"],
            "operation": operation,
        }
        for operation in (("read", "write") if mode == "read_write" else ("read",))
    ]
    subject.update(subject_version=6, events=subject.get("events", []),
        publications=subject.get("publications", []), private_files=subject.get("private_files", []),
        relational=subject.get("relational", []), checkpoints=resources)
    evidence.update(evidence_version=6, events=evidence.get("events", []),
        publications=evidence.get("publications", []), private_files=evidence.get("private_files", []),
        relational=evidence.get("relational", []), checkpoints=copy.deepcopy(resources))
    evidence["required_scopes"] += [READ] + ([WRITE] if mode == "read_write" else [])
    return subject, evidence


def resolved_context(subject, evidence):
    result = evaluate_authority_policy(subject, evidence)
    assert result.policy_resolved, result.issues
    current = context()
    current.update(context_version=6, policy=result.policy.model_dump(mode="json"),
        **{name: copy.deepcopy(subject[name]) for name in
           ("events", "publications", "private_files", "relational", "checkpoints")})
    return current


def selected(*scopes):
    return {"selection_version": 6, "scopes": list(scopes)}


@pytest.mark.parametrize("mode", ["read", "read_write"])
@pytest.mark.parametrize("mixed", [False, True])
def test_exact_owned_checkpoints_join_old_resource_families_without_approval(mode, mixed):
    subject, evidence = inputs(mode, mixed)
    before = copy.deepcopy((subject, evidence))
    policy = evaluate_authority_policy(subject, evidence)
    assert policy.policy.adapter_revision == 6
    current = resolved_context(subject, evidence)
    result = review_authority_context(current, selected(*policy.policy.allowed_scopes), now_ms=150_000)
    assert result.reviewable and result.context_fingerprint
    assert result.permission_approval == policy.permission_approval == "not_evaluated"
    assert not policy.reviewable
    assert _parse(AuthorityReviewContextV6, current).checkpoints[0].owner == _parse(
        AuthorityReviewContextV6, current).principal
    assert (subject, evidence) == before


@pytest.mark.parametrize("operation", ["read", "write"])
def test_policy_can_select_one_checkpoint_operation_without_granting_the_other(operation):
    subject, evidence = inputs()
    chosen = f"checkpoint:progress:{operation}"
    other = WRITE if operation == "read" else READ
    evidence["checkpoints"] = [item for item in evidence["checkpoints"] if item["operation"] == operation]
    evidence["required_scopes"] = ["command:pulse", chosen]
    current = resolved_context(subject, evidence)
    assert review_authority_context(current, selected("command:pulse", chosen), now_ms=150_000).reviewable
    rejected = review_authority_context(current, selected("command:pulse", chosen, other), now_ms=150_000)
    assert {item.reason for item in rejected.issues} == {"scope_not_allowed"}
    evidence.update(checkpoints=[], required_scopes=["command:pulse"])
    current = resolved_context(subject, evidence)
    assert review_authority_context(current, selected("command:pulse"), now_ms=150_000).reviewable


@pytest.mark.parametrize("path,value", [
    (("owner", "core_installation_id"), "foreign_core"),
    (("owner", "application_installation_id"), "foreign_app"),
    (("owner", "incarnation"), "reinstalled"),
    (("owner", "module_id"), "org.example.other"),
    (("package_artifact_sha256",), "f" * 64),
    (("path",), "/var/lib/3mm/core/3mm.db"),
    (("approved",), True),
    (("declaration", "max_value_bytes"), True),
    (("declaration", "max_value_bytes"), 262145),
    (("declaration", "max_value_bytes"), 0),
    (("declaration", "contract_version"), 1.0),
    (("declaration", "checkpoint_id"), "../other"),
    (("declaration", "checkpoint_id"), "*"),
])
def test_foreign_ownership_or_caller_authority_is_not_a_context(path, value):
    subject, evidence = inputs()
    for item in subject["checkpoints"]:
        replace_path(item, path, value)
    assert not evaluate_authority_policy(subject, evidence).policy_resolved


@pytest.mark.parametrize("field,value", [
    ("max_value_bytes", 2048), ("checkpoint_id", "other_progress"),
])
def test_exact_declaration_change_invalidates_policy_and_review_fingerprint(field, value):
    subject, evidence = inputs()
    original = resolved_context(subject, evidence)
    old = review_authority_context(original, selected("command:pulse", READ, WRITE), now_ms=150_000)
    for item in subject["checkpoints"]:
        item["declaration"][field] = value
    result = evaluate_authority_policy(subject, evidence)
    assert not result.policy_resolved
    evidence["checkpoints"] = copy.deepcopy(subject["checkpoints"])
    if field == "checkpoint_id":
        evidence["required_scopes"] = ["command:pulse", "checkpoint:other_progress:read", "checkpoint:other_progress:write"]
    changed = resolved_context(subject, evidence)
    assert changed["policy"]["policy_revision"] != original["policy"]["policy_revision"]
    current = review_authority_context(changed, selected(*changed["policy"]["required_scopes"]), now_ms=150_000)
    assert current.reviewable and current.context_fingerprint != old.context_fingerprint


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "mixed_declaration", "too_many_ids"])
def test_subject_and_context_require_complete_consistent_declared_operations(mutation):
    subject, evidence = inputs()
    if mutation == "missing":
        subject["checkpoints"] = subject["checkpoints"][:1]
    elif mutation == "duplicate":
        subject["checkpoints"].append(copy.deepcopy(subject["checkpoints"][0]))
    elif mutation == "mixed_declaration":
        subject["checkpoints"][0]["declaration"]["max_value_bytes"] = 512
    else:
        subject["checkpoints"] = []
        for index in range(33):
            item = copy.deepcopy(evidence["checkpoints"][0])
            item["declaration"].update(checkpoint_id=f"progress_{index}", mode="read")
            subject["checkpoints"].append(item)
    assert not evaluate_authority_policy(subject, evidence).policy_resolved


def test_scope_id_mode_old_versions_expiry_and_canonical_order_are_not_inferred():
    subject, evidence = inputs("read")
    current = resolved_context(subject, evidence)
    denied = review_authority_context(current, selected("command:pulse", READ, WRITE), now_ms=150_000)
    assert {item.reason for item in denied.issues} == {"unknown_selected_scope"}
    with pytest.raises(ValueError):
        _parse(AuthoritySelectionV5, {"selection_version": 5, "scopes": [READ]})
    assert _parse(AuthoritySelectionV6, selected(READ)).selection_version == 6
    for version in (True, 6.0, "6", 5):
        assert not review_authority_context({**current, "context_version": version}, selected(READ), now_ms=150_000).reviewable
    assert not review_authority_context(current, selected(READ), now_ms=current["expires_at_ms"]).reviewable
    subject, evidence = inputs()
    original = resolved_context(subject, evidence)
    before = review_authority_context(original, selected("command:pulse", READ, WRITE), now_ms=150_000)
    subject["checkpoints"].reverse()
    evidence["checkpoints"].reverse()
    reordered = resolved_context(subject, evidence)
    assert review_authority_context(reordered, selected(WRITE, READ, "command:pulse"), now_ms=150_000).context_fingerprint == before.context_fingerprint


def test_mixed_relational_profile_still_cannot_be_narrowed_to_one_half():
    subject, evidence = inputs(mixed=True)
    evidence["relational"] = evidence["relational"][:1]
    evidence["required_scopes"].remove("storage:relational_write")
    assert not evaluate_authority_policy(subject, evidence).policy_resolved
