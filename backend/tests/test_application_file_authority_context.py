"""Pure storage review vectors, NOT signed permits or installed file grants."""

import copy
import json
import socket
import subprocess
from pathlib import Path

import pytest
import requests
from sqlalchemy.orm import Session

from backend.services.application_authority_context import (
    AuthorityPolicy,
    AuthorityReviewContextV1,
    AuthorityReviewContextV2,
    AuthorityReviewContextV3,
    AuthorityReviewContextV4,
    AuthoritySelectionV4,
    _parse,
    _parse_versioned,
    review_authority_context,
)
from backend.services.application_authority_policy import (
    CorePolicyEvidenceV4,
    PolicySubjectV4,
    evaluate_authority_policy,
)
from backend.tests.test_application_authority_context import context, replace_path
from backend.tests.test_application_authority_policy import inputs as command_inputs
from three_mm_protocol.tests.test_application_private_files import file_request


READ = "storage:private_files_read"
WRITE = "storage:private_files_write"


def inputs(mode="read_write"):
    subject, evidence = command_inputs()
    resources = [
        {
            "declaration": file_request(mode=mode),
            "owner": copy.deepcopy(subject["binding"]["principal"]),
            "package_artifact_sha256": subject["binding"]["candidate"]["sha256"],
            "operation": operation,
        }
        for operation in (("read", "write") if mode == "read_write" else ("read",))
    ]
    subject.update(
        subject_version=4, events=[], publications=[], private_files=resources
    )
    evidence.update(
        evidence_version=4,
        events=[],
        publications=[],
        private_files=copy.deepcopy(resources),
        required_scopes=["command:pulse", READ]
        + ([WRITE] if mode == "read_write" else []),
    )
    return subject, evidence


def resolved_context(subject, evidence):
    result = evaluate_authority_policy(subject, evidence)
    assert result.policy_resolved
    current = context()
    current.update(
        context_version=4,
        policy=result.policy.model_dump(mode="json"),
        events=copy.deepcopy(subject["events"]),
        publications=copy.deepcopy(subject["publications"]),
        private_files=copy.deepcopy(subject["private_files"]),
    )
    return current


def selected(*scopes):
    return {"selection_version": 4, "scopes": list(scopes)}


def reasons(result):
    return {issue.reason for issue in result.issues}


@pytest.mark.parametrize("mode", ["read", "read_write"])
def test_exact_owned_storage_joins_one_existing_policy_and_review_contract(mode):
    subject, evidence = inputs(mode)
    before = copy.deepcopy((subject, evidence))
    policy = evaluate_authority_policy(subject, evidence)
    assert policy.policy.adapter_revision == 4
    assert policy.policy.allowed_scopes == tuple(
        sorted(
            ["command:pulse", "connector:business_api", READ]
            + ([WRITE] if mode == "read_write" else [])
        )
    )
    current = resolved_context(subject, evidence)
    result = review_authority_context(
        current, selected(*policy.policy.allowed_scopes), now_ms=150_000
    )
    assert result.reviewable and result.context_fingerprint
    assert policy.permission_approval == result.permission_approval == "not_evaluated"
    assert not policy.reviewable
    assert "approval_persistence_and_effect_enforcement" in result.not_checked
    assert (subject, evidence) == before
    assert (
        _parse(PolicySubjectV4, subject).private_files[0].owner
        == _parse(AuthorityReviewContextV4, current).principal
    )
    assert "path" not in json.dumps(subject["private_files"])


def test_read_policy_is_not_write_authority_even_for_read_write_declaration():
    subject, evidence = inputs()
    evidence["private_files"] = evidence["private_files"][:1]
    evidence["required_scopes"].remove(WRITE)
    current = resolved_context(subject, evidence)
    assert WRITE not in current["policy"]["allowed_scopes"]
    assert review_authority_context(
        current, selected("command:pulse", READ), now_ms=150_000
    ).reviewable
    denied = review_authority_context(
        current, selected("command:pulse", READ, WRITE), now_ms=150_000
    )
    assert reasons(denied) == {"scope_not_allowed"}
    assert denied.issues[0].scope == WRITE


def test_write_rule_does_not_implicitly_grant_read_and_empty_rules_grant_neither():
    subject, evidence = inputs()
    evidence["private_files"] = evidence["private_files"][1:]
    evidence["required_scopes"].remove(READ)
    current = resolved_context(subject, evidence)
    assert READ not in current["policy"]["allowed_scopes"]
    assert reasons(
        review_authority_context(
            current, selected("command:pulse", READ, WRITE), now_ms=150_000
        )
    ) == {"scope_not_allowed"}
    evidence.update(private_files=[], required_scopes=["command:pulse"])
    current = resolved_context(subject, evidence)
    assert review_authority_context(
        current, selected("command:pulse"), now_ms=150_000
    ).reviewable
    assert reasons(
        review_authority_context(
            current, selected("command:pulse", READ, WRITE), now_ms=150_000
        )
    ) == {"scope_not_allowed"}


def test_missing_policy_and_source_blockers_are_not_cleared_by_file_declaration():
    subject, evidence = inputs()
    assert reasons(evaluate_authority_policy(subject)) == {"trusted_policy_unavailable"}
    subject["blockers"] = ["unsupported_scope_family"]
    assert reasons(evaluate_authority_policy(subject, evidence)) == {
        "unsupported_scope_family"
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_file_bytes", 2 * 1024 * 1024),
        ("max_total_bytes", 32 * 1024 * 1024),
        ("max_files", 257),
    ],
)
def test_changed_limits_require_new_exact_policy_and_review_fingerprint(field, value):
    subject, evidence = inputs()
    current = resolved_context(subject, evidence)
    selection = selected("command:pulse", READ, WRITE)
    previous = review_authority_context(current, selection, now_ms=150_000)
    for item in subject["private_files"]:
        item["declaration"][field] = value
    result = evaluate_authority_policy(subject, evidence)
    assert reasons(result) == {"policy_scope_changed"}
    assert {issue.scope for issue in result.issues} == {READ, WRITE}
    evidence["private_files"] = copy.deepcopy(subject["private_files"])
    changed = resolved_context(subject, evidence)
    assert changed["policy"]["policy_revision"] != current["policy"]["policy_revision"]
    assert (
        review_authority_context(changed, selection, now_ms=150_000).context_fingerprint
        != previous.context_fingerprint
    )


def test_changed_mode_cannot_reuse_read_write_rules_or_write_selection():
    subject, evidence = inputs()
    subject["private_files"] = subject["private_files"][:1]
    subject["private_files"][0]["declaration"]["mode"] = "read"
    result = evaluate_authority_policy(subject, evidence)
    assert reasons(result) == {"policy_scope_changed", "policy_scope_unavailable"}
    evidence.update(
        private_files=copy.deepcopy(subject["private_files"]), required_scopes=[READ]
    )
    current = resolved_context(subject, evidence)
    assert reasons(
        review_authority_context(current, selected(READ, WRITE), now_ms=150_000)
    ) == {"unknown_selected_scope"}


@pytest.mark.parametrize(
    "path,value",
    [
        (("owner", "core_installation_id"), "foreign_core"),
        (("owner", "application_installation_id"), "foreign_app"),
        (("owner", "incarnation"), "reinstalled_app"),
        (("owner", "module_id"), "org.example.other"),
        (("package_artifact_sha256",), "f" * 64),
        (("declaration", "path"), "/var/lib/3mm/other/data"),
        (("declaration", "namespace"), "foreign"),
        (("declaration", "max_files"), True),
        (("declaration", "max_total_bytes"), "16777216"),
        (("declaration", "file_contract_version"), 1.0),
        (("approved",), True),
        (("operation",), "delete"),
    ],
)
def test_foreign_unsafe_or_caller_approved_storage_is_never_a_valid_context(
    path, value
):
    subject, evidence = inputs()
    current = resolved_context(subject, evidence)
    for item in current["private_files"]:
        replace_path(item, path, value)
    result = review_authority_context(current, selected(READ, WRITE), now_ms=150_000)
    assert reasons(result) == {"invalid_context"}
    assert result.context_fingerprint is None
    for item in subject["private_files"]:
        replace_path(item, path, value)
    assert reasons(evaluate_authority_policy(subject, evidence)) == {
        "invalid_policy_subject"
    }
    subject, evidence = inputs()
    for item in evidence["private_files"]:
        replace_path(item, path, value)
    result = evaluate_authority_policy(subject, evidence)
    assert reasons(result) == {"invalid_trusted_policy"}
    assert "/var/lib" not in result.model_dump_json()


@pytest.mark.parametrize(
    "change", ["duplicate", "missing_write", "mixed_limits", "readonly_write"]
)
def test_complete_request_is_not_partial_duplicate_or_a_second_namespace(change):
    subject, evidence = inputs()
    current = resolved_context(subject, evidence)
    for value in (subject, current):
        if change == "duplicate":
            value["private_files"][1] = copy.deepcopy(value["private_files"][0])
        elif change == "missing_write":
            value["private_files"].pop()
        elif change == "mixed_limits":
            value["private_files"][1]["declaration"]["max_files"] = 257
        else:
            for item in value["private_files"]:
                item["declaration"]["mode"] = "read"
    assert reasons(evaluate_authority_policy(subject, evidence)) == {
        "invalid_policy_subject"
    }
    assert reasons(
        review_authority_context(current, selected(READ, WRITE), now_ms=150_000)
    ) == {"invalid_context"}


@pytest.mark.parametrize(
    "scopes,expected",
    [
        (["command:pulse", READ], "required_scope_omitted"),
        (["command:pulse", WRITE], "required_scope_omitted"),
        (["command:pulse", READ, WRITE, READ], "invalid_selection"),
        (["storage:private_files"], "invalid_selection"),
        (["storage:private_files_delete"], "invalid_selection"),
        (["storage:*"], "invalid_selection"),
        (["storage:foreign_read"], "invalid_selection"),
    ],
)
def test_exact_storage_scope_vocabulary_and_required_selection(scopes, expected):
    subject, evidence = inputs()
    current = resolved_context(subject, evidence)
    assert reasons(
        review_authority_context(current, selected(*scopes), now_ms=150_000)
    ) == {expected}


@pytest.mark.parametrize("version", [1, 2, 3, True, 4.0, "4", 5])
def test_version_mismatch_never_downgrades_or_infers_storage(version):
    subject, evidence = inputs()
    current = resolved_context(subject, evidence)
    selection = selected("command:pulse", READ, WRITE)
    selection["selection_version"] = version
    assert reasons(review_authority_context(current, selection, now_ms=150_000)) == {
        "invalid_selection"
    }
    subject["subject_version"] = version
    assert reasons(evaluate_authority_policy(subject, evidence)) == {
        "invalid_policy_subject"
    }
    subject, evidence = inputs()
    evidence["evidence_version"] = version
    assert reasons(evaluate_authority_policy(subject, evidence)) == {
        "invalid_trusted_policy"
    }


def test_old_coordinator_parser_does_not_opt_into_v4_by_importing_pure_contracts():
    subject, evidence = inputs()
    current = resolved_context(subject, evidence)
    with pytest.raises(ValueError, match="Unsupported internal authority version"):
        _parse_versioned(
            AuthorityReviewContextV1,
            AuthorityReviewContextV2,
            current,
            "context_version",
            AuthorityReviewContextV3,
        )
    with pytest.raises(ValueError):
        _parse(AuthorityPolicy, current["policy"])
    with pytest.raises(ValueError):
        _parse(AuthoritySelectionV4, selected(READ, READ))


def test_order_is_not_authority_and_json_models_share_exact_v4_identity():
    subject, evidence = inputs()
    current = resolved_context(subject, evidence)
    selection = selected("command:pulse", READ, WRITE)
    expected = review_authority_context(current, selection, now_ms=150_000)
    # Fixed internal vectors, not signed policy/grant/permit material.
    assert current["policy"]["policy_revision"] == (
        "policy_b21eb3ff216925d68a7dcca0752a4129065c722e05ce06616b85a4d8857b7457"
    )
    assert expected.context_fingerprint == (
        "eb19d9a2e54350b4a9c1b42123443858bd662921cc867aeaab6fcc9559193542"
    )
    current["private_files"].reverse()
    selection["scopes"].reverse()
    assert review_authority_context(current, selection, now_ms=150_000) == expected
    original = evaluate_authority_policy(subject, evidence)
    subject["private_files"].reverse()
    evidence["private_files"].reverse()
    evidence["required_scopes"].reverse()
    assert (
        evaluate_authority_policy(json.dumps(subject), json.dumps(evidence)) == original
    )
    assert (
        evaluate_authority_policy(
            _parse(PolicySubjectV4, subject), _parse(CorePolicyEvidenceV4, evidence)
        )
        == original
    )
    assert (
        review_authority_context(
            _parse(AuthorityReviewContextV4, current),
            _parse(AuthoritySelectionV4, selection),
            now_ms=150_000,
        )
        == expected
    )


@pytest.mark.parametrize("now", [99_999, 200_000, True, "150000"])
def test_storage_review_expires_and_has_no_caller_clock_bypass(now):
    subject, evidence = inputs()
    result = review_authority_context(
        resolved_context(subject, evidence),
        selected("command:pulse", READ, WRITE),
        now_ms=now,
    )
    assert not result.reviewable and result.context_fingerprint is None
    assert reasons(result) == (
        {"invalid_review_clock"} if type(now) is not int else {"review_not_current"}
    )


def test_constructed_models_and_duplicate_json_are_still_revalidated():
    subject, evidence = inputs()
    malformed = PolicySubjectV4.model_construct(**{**subject, "subject_version": True})
    assert reasons(evaluate_authority_policy(malformed, evidence)) == {
        "invalid_policy_subject"
    }
    current = resolved_context(subject, evidence)
    malformed = AuthorityReviewContextV4.model_construct(
        **{**current, "context_version": 4.0}
    )
    assert reasons(
        review_authority_context(malformed, selected(READ), now_ms=150_000)
    ) == {"invalid_context"}
    duplicate = json.dumps(current).replace(
        '"context_version": 4', '"context_version": 4, "context_version": 4'
    )
    assert reasons(
        review_authority_context(duplicate, selected(READ), now_ms=150_000)
    ) == {"invalid_context"}


def test_successful_storage_comparison_performs_no_effect_or_live_io(monkeypatch):
    subject, evidence = inputs()
    current = resolved_context(subject, evidence)

    def forbidden(*_args, **_kwargs):
        pytest.fail(
            "Pure storage review cannot perform file/DB/network/process effects"
        )

    for name in ("read_bytes", "read_text", "write_bytes", "write_text", "mkdir"):
        monkeypatch.setattr(Path, name, forbidden)
    for name in ("execute", "get", "add", "flush", "commit", "delete"):
        monkeypatch.setattr(Session, name, forbidden)
    for name in ("run", "Popen"):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert evaluate_authority_policy(subject, evidence).policy_resolved
    assert review_authority_context(
        current, selected("command:pulse", READ, WRITE), now_ms=150_000
    ).reviewable
