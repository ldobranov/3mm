"""Exact owned SQLite review vectors; these are not runtime SQL permits."""

import copy

import pytest

from backend.services.application_authority_context import (
    AuthorityReviewContextV5,
    AuthoritySelectionV4,
    AuthoritySelectionV5,
    _parse,
    review_authority_context,
)
from backend.services.application_authority_policy import evaluate_authority_policy
from backend.tests.test_application_authority_context import context, replace_path
from backend.tests.test_application_authority_policy import inputs as command_inputs
from three_mm_protocol.tests.test_application_private_files import file_request
from three_mm_protocol.tests.test_application_relational_storage import (
    relational_request,
)

READ = "storage:relational_read"
WRITE = "storage:relational_write"


def inputs(mode="read_write", files=False):
    subject, evidence = command_inputs()
    resources = [
        {
            "declaration": relational_request(mode=mode),
            "owner": copy.deepcopy(subject["binding"]["principal"]),
            "package_artifact_sha256": subject["binding"]["candidate"]["sha256"],
            "service_artifact_sha256": "b" * 64,
            "schema_revision": "0001",
            "migration_entrypoint": "example_app:migrations",
            "operation": operation,
        }
        for operation in (("read", "write") if mode == "read_write" else ("read",))
    ]
    private_files = (
        [
            {
                "declaration": file_request(mode="read"),
                "owner": copy.deepcopy(subject["binding"]["principal"]),
                "package_artifact_sha256": subject["binding"]["candidate"]["sha256"],
                "operation": "read",
            }
        ]
        if files
        else []
    )
    subject.update(
        subject_version=5,
        events=[],
        publications=[],
        private_files=private_files,
        relational=resources,
    )
    evidence.update(
        evidence_version=5,
        events=[],
        publications=[],
        private_files=copy.deepcopy(private_files),
        relational=copy.deepcopy(resources),
        required_scopes=["command:pulse", READ]
        + ([WRITE] if mode == "read_write" else [])
        + (["storage:private_files_read"] if files else []),
    )
    return subject, evidence


def resolved_context(subject, evidence):
    result = evaluate_authority_policy(subject, evidence)
    assert result.policy_resolved, result.issues
    current = context()
    current.update(
        context_version=5,
        policy=result.policy.model_dump(mode="json"),
        events=subject["events"],
        publications=subject["publications"],
        private_files=subject["private_files"],
        relational=subject["relational"],
    )
    return current


def selected(*scopes):
    return {"selection_version": 5, "scopes": list(scopes)}


@pytest.mark.parametrize("mode", ["read", "read_write"])
@pytest.mark.parametrize("files", [False, True])
def test_whole_db_profile_and_files_have_separate_exact_scopes(mode, files):
    subject, evidence = inputs(mode, files)
    before = copy.deepcopy((subject, evidence))
    policy = evaluate_authority_policy(subject, evidence)
    assert policy.policy.adapter_revision == 5
    current = resolved_context(subject, evidence)
    result = review_authority_context(
        current, selected(*policy.policy.allowed_scopes), now_ms=150_000
    )
    assert result.reviewable and result.context_fingerprint
    assert result.permission_approval == policy.permission_approval == "not_evaluated"
    assert not policy.reviewable
    assert (
        _parse(AuthorityReviewContextV5, current).relational[0].owner
        == _parse(AuthorityReviewContextV5, current).principal
    )
    assert (subject, evidence) == before


@pytest.mark.parametrize("scope", [READ, WRITE])
def test_read_write_profile_cannot_be_half_policy_or_half_selection(scope):
    subject, evidence = inputs()
    current = resolved_context(subject, evidence)
    result = review_authority_context(
        current, selected("command:pulse", scope), now_ms=150_000
    )
    assert not result.reviewable
    assert "required_scope_omitted" in {item.reason for item in result.issues}
    evidence["relational"] = [
        item
        for item in evidence["relational"]
        if item["operation"] == scope.rsplit("_", 1)[1]
    ]
    evidence["required_scopes"] = ["command:pulse", scope]
    assert not evaluate_authority_policy(subject, evidence).policy_resolved


def test_no_db_rules_or_file_grants_never_supply_db_authority():
    subject, evidence = inputs(files=True)
    evidence.update(
        relational=[], required_scopes=["command:pulse", "storage:private_files_read"]
    )
    current = resolved_context(subject, evidence)
    assert review_authority_context(
        current, selected("command:pulse", "storage:private_files_read"), now_ms=150_000
    ).reviewable
    denied = review_authority_context(
        current,
        selected("command:pulse", "storage:private_files_read", READ, WRITE),
        now_ms=150_000,
    )
    assert {item.reason for item in denied.issues} == {"scope_not_allowed"}


@pytest.mark.parametrize(
    "path,value",
    [
        (("owner", "core_installation_id"), "foreign_core"),
        (("owner", "application_installation_id"), "foreign_app"),
        (("owner", "incarnation"), "reinstalled"),
        (("owner", "module_id"), "org.example.foreign"),
        (("package_artifact_sha256",), "f" * 64),
        (("path",), "/var/lib/3mm/core/3mm.db"),
        (("resource_profile",), "unlimited"),
        (("approved",), True),
        (("declaration", "max_busy_ms"), True),
    ],
)
def test_foreign_owner_or_caller_authority_is_not_a_context(path, value):
    subject, evidence = inputs()
    for item in subject["relational"]:
        replace_path(item, path, value)
    assert not evaluate_authority_policy(subject, evidence).policy_resolved


@pytest.mark.parametrize(
    "path,value",
    [
        (("declaration", "max_database_bytes"), 128 * 1024 * 1024),
        (("declaration", "auxiliary_pause_bytes"), 1024 * 1024),
        (("declaration", "max_statement_bytes"), 8192),
        (("declaration", "max_value_bytes"), 131072),
        (("declaration", "max_result_bytes"), 524288),
        (("declaration", "max_result_rows"), 99),
        (("declaration", "max_transaction_ms"), 10000),
        (("declaration", "max_busy_ms"), 0),
        (("schema_revision",), "0002"),
        (("migration_entrypoint",), "example_app:other_migrations"),
        (("service_artifact_sha256",), "c" * 64),
    ],
)
def test_every_limit_schema_and_code_identity_invalidates_exact_policy(path, value):
    subject, evidence = inputs()
    original = resolved_context(subject, evidence)
    scopes = selected("command:pulse", READ, WRITE)
    old = review_authority_context(original, scopes, now_ms=150_000)
    for item in subject["relational"]:
        replace_path(item, path, value)
    result = evaluate_authority_policy(subject, evidence)
    assert {item.reason for item in result.issues} == {"policy_scope_changed"}
    assert {item.scope for item in result.issues} == {READ, WRITE}
    evidence["relational"] = copy.deepcopy(subject["relational"])
    changed = resolved_context(subject, evidence)
    assert changed["policy"]["policy_revision"] != original["policy"]["policy_revision"]
    assert (
        review_authority_context(changed, scopes, now_ms=150_000).context_fingerprint
        != old.context_fingerprint
    )


def test_read_only_cannot_upgrade_to_write_and_versions_do_not_upgrade_implicitly():
    subject, evidence = inputs("read")
    current = resolved_context(subject, evidence)
    denied = review_authority_context(
        current, selected("command:pulse", READ, WRITE), now_ms=150_000
    )
    assert {item.reason for item in denied.issues} == {"unknown_selected_scope"}
    with pytest.raises(ValueError):
        _parse(AuthoritySelectionV4, {"selection_version": 4, "scopes": [READ]})
    assert _parse(AuthoritySelectionV5, selected(READ)).selection_version == 5
    for version in (True, 5.0, "5", 4):
        value = {**current, "context_version": version}
        assert not review_authority_context(
            value, selected(READ), now_ms=150_000
        ).reviewable


def test_canonical_order_is_stable_and_mixed_profiles_are_refused():
    subject, evidence = inputs()
    original = resolved_context(subject, evidence)
    before = review_authority_context(
        original, selected("command:pulse", READ, WRITE), now_ms=150_000
    )
    subject["relational"].reverse()
    evidence["relational"].reverse()
    reordered = resolved_context(subject, evidence)
    assert (
        review_authority_context(
            reordered, selected(WRITE, READ, "command:pulse"), now_ms=150_000
        ).context_fingerprint
        == before.context_fingerprint
    )
    subject["relational"][0]["schema_revision"] = "0002"
    assert not evaluate_authority_policy(subject, evidence).policy_resolved


def test_fixed_v5_canonical_vector_is_metadata_not_a_signature_or_permit():
    subject, evidence = inputs()
    current = resolved_context(subject, evidence)
    assert current["policy"]["policy_revision"] == (
        "policy_f5d2ac9054b01a524d3fc16ad84d39df506b7631c3ffec1575a589594b5e6b43"
    )
    result = review_authority_context(
        current, selected("command:pulse", READ, WRITE), now_ms=150_000
    )
    assert result.context_fingerprint == (
        "61b93f55954f08a5dbdd5e3300a564384ee15826b30a2108393cd5729b5b1b67"
    )
    assert result.permission_approval == "not_evaluated"


def test_missing_trust_expiry_or_blockers_are_not_cleared_by_db_request():
    subject, evidence = inputs()
    assert not evaluate_authority_policy(subject).policy_resolved
    current = resolved_context(subject, evidence)
    assert not review_authority_context(
        current, selected("command:pulse", READ, WRITE), now_ms=current["expires_at_ms"]
    ).reviewable
    subject["blockers"] = ["unsupported_scope_family"]
    assert not evaluate_authority_policy(subject, evidence).policy_resolved
