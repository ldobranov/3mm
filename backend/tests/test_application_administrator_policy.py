"""Truthful administrator-native evidence is distinct from manual audit/isolation."""
from copy import deepcopy
import pytest
from backend.tests.test_application_authority_policy import inputs
from backend.services.application_authority_policy import evaluate_authority_policy


def administrator_inputs():
    subject, evidence = inputs()
    evidence.update(trust_class="administrator_approved_artifact",
        execution_class="administrator_approved_native",
        execution_profile="supervised_administrator_approved_native_v1",
        required_scopes=[])
    return subject, evidence


def test_exact_administrator_policy_retains_its_class_without_claiming_manual_audit():
    subject, evidence = administrator_inputs()
    result = evaluate_authority_policy(subject, evidence)
    assert result.policy_resolved and not result.reviewable
    assert result.permission_approval == "not_evaluated"
    assert result.policy.execution_class == "administrator_approved_native"
    assert result.policy.required_scopes == ()
    assert result.policy.allowed_scopes
    assert result.policy.isolation_proof_revision is None


@pytest.mark.parametrize("change", [
    {"trust_class": "reviewed_local_artifact"},
    {"execution_class": "reviewed_native"},
    {"execution_profile": "supervised_reviewed_native_v1"},
    {"native_review_revision": None},
    {"isolation_proof_revision": "unverified-isolation"},
    {"execution_class": "proven_isolated"},
])
def test_administrator_consent_cannot_masquerade_as_manual_audit_or_isolation(change):
    subject, evidence = administrator_inputs()
    evidence.update(change)
    result = evaluate_authority_policy(subject, evidence)
    assert not result.policy_resolved and result.policy is None


def test_administrator_native_ui_uses_the_exact_ui_build_and_profile():
    subject, evidence = administrator_inputs()
    subject["has_executable_frontend"] = True
    subject["binding"]["candidate"]["built_ui_sha256"] = "a" * 64
    evidence["binding"] = deepcopy(subject["binding"])
    assert not evaluate_authority_policy(subject, evidence).policy_resolved
    evidence["execution_profile"] = "supervised_administrator_approved_native_ui_v1"
    assert evaluate_authority_policy(subject, evidence).policy_resolved
    evidence["binding"]["candidate"]["built_ui_sha256"] = "b" * 64
    assert not evaluate_authority_policy(subject, evidence).policy_resolved
