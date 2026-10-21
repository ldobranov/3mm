"""Pure v10 vectors, separate from real sealed M20 acceptance tests."""

import copy

import pytest

from backend.services.application_authority_context import (
    AuthorityReviewContextV10,
    _parse,
    review_authority_context,
)
from backend.services.application_authority_policy import evaluate_authority_policy
from backend.tests.test_application_authority_policy import inputs
from three_mm_protocol.tests.test_application_sessions import binding


def session_inputs():
    subject, evidence = inputs()
    resource = {
        "declaration": binding(),
        "owner": copy.deepcopy(subject["binding"]["principal"]),
        "package_artifact_sha256": subject["binding"]["candidate"]["sha256"],
        "target_device_id": "dev_" + "1" * 32,
        "control_revision": "d" * 64,
        "provider_version": "1.0.0",
        "contract": {
            "contract_version": 1,
            "access_modes": ["read", "write"],
            "control_actions": ["resize"],
        },
    }
    subject["subject_version"] = evidence["evidence_version"] = 10
    for field in (
        "events",
        "publications",
        "private_files",
        "relational",
        "checkpoints",
        "identities",
        "status_projections",
        "peer_reads",
    ):
        subject[field] = []
        evidence[field] = []
    subject["sessions"] = [resource]
    evidence["sessions"] = copy.deepcopy(subject["sessions"])
    return subject, evidence


def context_and_selection():
    subject, evidence = session_inputs()
    evaluated = evaluate_authority_policy(subject, evidence)
    assert evaluated.policy_resolved, evaluated
    value = {
        "context_version": 10,
        **{
            key: value
            for key, value in subject["binding"].items()
            if key != "recovery_generation"
        },
        "policy": evaluated.policy.model_dump(mode="json"),
        "issued_at_ms": 100_000,
        "expires_at_ms": 200_000,
        **{
            key: value
            for key, value in subject.items()
            if key
            not in {"binding", "blockers", "subject_version", "has_executable_frontend"}
        },
    }
    return value, {
        "selection_version": 10,
        "scopes": ["command:pulse", "session:console:open"],
    }


def test_session_context_needs_current_policy_and_is_not_itself_a_grant():
    subject, evidence = session_inputs()
    assert not evaluate_authority_policy(subject).policy_resolved
    result = evaluate_authority_policy(subject, evidence)
    assert result.policy_resolved and not result.reviewable
    assert result.permission_approval == "not_evaluated"
    assert "session:console:open" in result.policy.allowed_scopes
    context, selection = context_and_selection()
    reviewed = review_authority_context(context, selection, now_ms=150_000)
    assert reviewed.reviewable and reviewed.context_fingerprint
    assert reviewed.permission_approval == "not_evaluated"


@pytest.mark.parametrize(
    "change", ["owner", "artifact", "target", "controls", "duplicate", "version"]
)
def test_foreign_or_invalid_session_resources_never_form_a_context(change):
    context, _ = context_and_selection()
    resource = context["sessions"][0]
    if change == "owner":
        resource["owner"]["application_installation_id"] = "foreign"
    elif change == "artifact":
        resource["package_artifact_sha256"] = "f" * 64
    elif change == "target":
        resource["target_device_id"] = "dev_foreign"
    elif change == "controls":
        resource["declaration"]["control_actions"] = ["execute"]
    elif change == "duplicate":
        context["sessions"].append(copy.deepcopy(resource))
    else:
        resource["contract"]["contract_version"] = True
    with pytest.raises(ValueError):
        _parse(AuthorityReviewContextV10, context)


@pytest.mark.parametrize(
    "change", ["control_revision", "provider_version", "target_device_id"]
)
def test_policy_detects_changes_to_each_resolved_provider_pin(change):
    subject, evidence = session_inputs()
    subject["sessions"][0][change] = {
        "control_revision": "e" * 64,
        "provider_version": "2.0.0",
        "target_device_id": "dev_" + "f" * 32,
    }[change]
    result = evaluate_authority_policy(subject, evidence)
    assert not result.policy_resolved
    assert any(
        issue.reason == "policy_scope_changed" and issue.scope == "session:console:open"
        for issue in result.issues
    )


def test_unknown_selection_expired_review_and_old_context_do_not_admit_sessions():
    context, selection = context_and_selection()
    assert not review_authority_context(context, selection, now_ms=200_000).reviewable
    selection["scopes"].append("session:foreign:open")
    assert not review_authority_context(context, selection, now_ms=150_000).reviewable
    context["context_version"] = selection["selection_version"] = 9
    assert not review_authority_context(context, selection, now_ms=150_000).reviewable
