"""Synthetic trusted-input vectors, not production policy/evidence acceptance."""

import copy
import json
import socket
import subprocess
from pathlib import Path

import pytest
import requests
from sqlalchemy.orm import Session

from backend.services.application_authority_context import (
    _parse,
    review_authority_context,
)
from backend.services.application_authority_policy import (
    CorePolicyEvidenceV1,
    PolicySubjectV1,
    evaluate_authority_policy,
)
from backend.tests.test_application_authority_context import (
    context,
    replace_path,
    selection,
)


def inputs():
    current = context()
    subject = {
        "subject_version": 1,
        "binding": {
            key: current[key]
            for key in ("principal", "candidate", "baseline", "configuration")
        },
        "commands": current["commands"],
        "connectors": current["connectors"],
        "has_executable_frontend": False,
        "blockers": [],
    }
    subject["binding"]["recovery_generation"] = "1" * 32
    evidence = {
        "evidence_version": 1,
        "binding": copy.deepcopy(subject["binding"]),
        "policy_revision": "local_policy_revision_1",
        "trust_revision": "local_trust_revision_1",
        "trust_class": "reviewed_local_artifact",
        "execution_class": "reviewed_native",
        "execution_profile": "supervised_reviewed_native_v1",
        "profile_revision": "profile_revision_1",
        "native_review_revision": "synthetic_native_review_1",
        "isolation_proof_revision": None,
        "commands": copy.deepcopy(subject["commands"]),
        "connectors": copy.deepcopy(subject["connectors"]),
        "required_scopes": ["command:pulse"],
    }
    return subject, evidence


def reasons(result):
    assert not result.policy_resolved and result.policy is None
    assert not result.reviewable
    assert result.permission_approval == "not_evaluated"
    return {issue.reason for issue in result.issues}


def test_no_policy_is_inferred_from_valid_package_or_resolved_resources():
    subject, _ = inputs()
    assert reasons(evaluate_authority_policy(subject)) == {"trusted_policy_unavailable"}


def test_exact_native_policy_is_only_a_context_input_not_review_or_approval():
    subject, evidence = inputs()
    before = copy.deepcopy((subject, evidence))
    result = evaluate_authority_policy(subject, evidence)
    assert result.policy_resolved and result.issues == ()
    assert not result.reviewable and result.permission_approval == "not_evaluated"
    assert result.policy.allowed_scopes == ("command:pulse", "connector:business_api")
    assert result.policy.required_scopes == ("command:pulse",)
    assert result.policy.execution_class == "reviewed_native"
    assert result.policy.isolation_proof_revision is None
    assert result.policy.adapter_revision == 1
    # Fixed internal vector; neither a signed policy nor an approved grant.
    assert result.policy.policy_revision == (
        "policy_c019c218c58bb994457092c8c60a4f3520db9ed1350494f35952d0be2e940171"
    )
    assert "trusted_policy_store_and_evidence_authenticity" in result.not_checked
    assert "os_browser_isolation_and_resource_limits" in result.not_checked
    assert (subject, evidence) == before


@pytest.mark.parametrize(
    "path,value",
    [
        (("principal", "core_installation_id"), "foreign_core"),
        (("principal", "application_installation_id"), "foreign_application"),
        (("principal", "incarnation"), "reinstalled_incarnation"),
        (("principal", "module_id"), "org.example.other"),
        (("candidate", "version"), "1.0.1"),
        (("candidate", "sha256"), "c" * 64),
        (("baseline", "authority_epoch"), "new_epoch"),
        (("baseline", "enforcement_mode"), "compatibility"),
        (("configuration", "key_id"), "rotated_key"),
        (("configuration", "keyed_sha256"), "d" * 64),
        (("recovery_generation",), "2" * 32),
    ],
)
def test_foreign_recovered_reinstalled_or_changed_context_cannot_reuse_policy(path, value):
    subject, evidence = inputs()
    replace_path(subject["binding"], path, value)
    assert reasons(evaluate_authority_policy(subject, evidence)) == {"policy_binding_changed"}


def test_active_baseline_artifact_and_existing_grant_revision_are_bound():
    subject, evidence = inputs()
    for value in (subject, evidence):
        value["binding"]["baseline"].update(
            artifact={"version": "0.9.0", "sha256": "e" * 64},
            grant_revision=1,
            enforcement_mode="enforced",
        )
    assert evaluate_authority_policy(subject, evidence).policy_resolved
    subject["binding"]["baseline"]["grant_revision"] = 2
    assert reasons(evaluate_authority_policy(subject, evidence)) == {"policy_binding_changed"}
    subject["binding"]["baseline"]["grant_revision"] = 1
    subject["binding"]["baseline"]["artifact"]["sha256"] = "f" * 64
    assert reasons(evaluate_authority_policy(subject, evidence)) == {"policy_binding_changed"}


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("trust_class", "unknown", "artifact_trust_unavailable"),
        ("trust_class", "revoked", "artifact_trust_revoked"),
        ("native_review_revision", None, "native_review_missing"),
        ("execution_profile", "package_selected_profile", "execution_profile_unsupported"),
        ("execution_class", "proven_isolated", "isolation_adapter_unavailable"),
        ("isolation_proof_revision", "pretend_proof", "unexpected_isolation_evidence"),
    ],
)
def test_classification_is_not_approval_and_unknown_or_fabricated_proof_is_not_fallback(
    field, value, expected
):
    subject, evidence = inputs()
    evidence[field] = value
    assert reasons(evaluate_authority_policy(subject, evidence)) == {expected}


def test_nonempty_isolation_revision_still_cannot_claim_a_verified_runtime():
    subject, evidence = inputs()
    evidence.update(execution_class="proven_isolated", isolation_proof_revision="fake")
    assert reasons(evaluate_authority_policy(subject, evidence)) == {"isolation_adapter_unavailable"}


@pytest.mark.parametrize("marker", ["source_flag", "built_ui_artifact"])
def test_native_classification_does_not_clear_executable_frontend_gate(marker):
    subject, evidence = inputs()
    if marker == "source_flag":
        subject["has_executable_frontend"] = True
    else:
        subject["binding"]["candidate"]["built_ui_sha256"] = "f" * 64
        evidence["binding"] = copy.deepcopy(subject["binding"])
    assert reasons(evaluate_authority_policy(subject, evidence)) == {"frontend_authority_unresolved"}


@pytest.mark.parametrize(
    "blocker",
    [
        "configuration_unresolved", "unsupported_scope_family", "peer_authority_unresolved",
        "frontend_authority_unresolved", "isolation_proof_missing", "dependency_resolution_missing",
    ],
)
def test_source_blockers_cannot_be_cleared_by_a_matching_native_policy(blocker):
    subject, evidence = inputs()
    subject["blockers"] = [blocker]
    assert reasons(evaluate_authority_policy(subject, evidence)) == {blocker}
    assert blocker in reasons(evaluate_authority_policy(subject))


@pytest.mark.parametrize(
    "path,value",
    [
        (("target_device_id",), "dev_" + "9" * 32),
        (("control_revision",), "changed_control"),
        (("declaration", "contract_version"), "1.1"),
        (("declaration", "action"), "set"),
        (("declaration", "max_ttl_seconds"), 10),
        (("declaration", "arguments_schema", "properties", "duration_ms", "maximum"), 500),
        (("declaration", "arguments_schema", "properties", "duration_ms", "minimum"), 1.0),
    ],
)
def test_exact_command_rules_reject_changed_targets_contracts_ttl_and_typed_bounds(path, value):
    subject, evidence = inputs()
    replace_path(subject["commands"][0], path, value)
    result = evaluate_authority_policy(subject, evidence)
    assert reasons(result) == {"policy_scope_changed"}
    assert result.issues[0].scope == "command:pulse"


@pytest.mark.parametrize(
    "path,value",
    [
        (("configured_origin",), "https://other.example.test"),
        (("stored", "destination_origin"), "https://other.example.test"),
        (("stored", "binding_revision"), "rebound_binding"),
        (("stored", "owner", "incarnation"), "foreign_incarnation"),
        (("stored", "enabled"), False),
        (("stored", "credential", "version"), 2),
        (("stored", "credential", "revoked"), True),
        (("stored", "credential", "secret_ref"), "secret_" + "9" * 32),
        (("declaration", "path_prefix"), "/other/"),
        (("declaration", "supports_mutations"), False),
        (("declaration", "timeout_seconds"), 9),
    ],
)
def test_connector_policy_pins_owned_binding_and_actual_credential_version(path, value):
    subject, evidence = inputs()
    replace_path(subject["connectors"][0], path, value)
    result = evaluate_authority_policy(subject, evidence)
    assert reasons(result) == {"policy_scope_changed"}
    assert result.issues[0].scope == "connector:business_api"


def test_rule_disappearance_denies_and_unlisted_scope_is_never_implicitly_allowed():
    subject, evidence = inputs()
    subject["connectors"] = []
    assert reasons(evaluate_authority_policy(subject, evidence)) == {"policy_scope_unavailable"}
    subject, evidence = inputs()
    evidence["connectors"] = []
    result = evaluate_authority_policy(subject, evidence)
    assert result.policy_resolved
    assert result.policy.allowed_scopes == ("command:pulse",)
    current = context()
    current["policy"] = result.policy.model_dump(mode="json")
    reviewed = review_authority_context(current, selection(), now_ms=150_000)
    assert not reviewed.reviewable
    assert {issue.reason for issue in reviewed.issues} == {"scope_not_allowed"}
    assert review_authority_context(current, selection("command:pulse"), now_ms=150_000).reviewable


def test_empty_policy_is_an_explicit_empty_allow_set_not_manifest_permissions():
    subject, evidence = inputs()
    evidence.update(commands=[], connectors=[], required_scopes=[])
    result = evaluate_authority_policy(subject, evidence)
    assert result.policy_resolved
    assert result.policy.allowed_scopes == result.policy.required_scopes == ()


def test_following_context_validation_still_requires_the_required_selection():
    subject, evidence = inputs()
    current = context()
    current["policy"] = evaluate_authority_policy(subject, evidence).policy.model_dump(mode="json")
    result = review_authority_context(current, selection("connector:business_api"), now_ms=150_000)
    assert not result.reviewable
    assert {issue.reason for issue in result.issues} == {"required_scope_omitted"}


def test_sensor_identity_and_control_revision_are_part_of_whole_command_policy():
    subject, evidence = inputs()
    for source in (subject, evidence):
        command = source["commands"][0]
        command["declaration"].update(sensor_id="passage.1", sensor_device_config_key="SENSOR")
        command.update(sensor_device_id="dev_" + "3" * 32, sensor_control_revision="sensor_1")
    assert evaluate_authority_policy(subject, evidence).policy_resolved
    subject["commands"][0]["sensor_control_revision"] = "sensor_2"
    assert reasons(evaluate_authority_policy(subject, evidence)) == {"policy_scope_changed"}


def test_semantic_sets_are_canonical_and_inputs_are_not_changed():
    subject, evidence = inputs()
    expected = evaluate_authority_policy(subject, evidence)
    for value in (subject, evidence):
        schema = value["commands"][0]["declaration"]["arguments_schema"]
        schema["required"].reverse()
        schema["properties"]["channel"]["enum"].reverse()
        value["connectors"][0]["declaration"]["allowed_schemes"].reverse()
    before = copy.deepcopy((subject, evidence))
    assert evaluate_authority_policy(dict(reversed(list(subject.items()))), evidence) == expected
    assert (subject, evidence) == before
    assert evaluate_authority_policy(json.dumps(subject), json.dumps(evidence)) == expected
    assert evaluate_authority_policy(_parse(PolicySubjectV1, subject), _parse(CorePolicyEvidenceV1, evidence)) == expected


def test_policy_resource_collection_order_is_not_authority():
    subject, evidence = inputs()
    for value in (subject, evidence):
        extra = copy.deepcopy(value["commands"][0])
        extra["declaration"]["binding_id"] = "pulse_other"
        value["commands"].append(extra)
        extra = copy.deepcopy(value["connectors"][0])
        extra["declaration"]["connector_id"] = "business_other"
        value["connectors"].append(extra)
    evidence["required_scopes"].append("connector:business_other")
    original = evaluate_authority_policy(subject, evidence)
    assert original.policy_resolved
    evidence["required_scopes"].reverse()
    for value in (subject, evidence):
        value["commands"].reverse()
        value["connectors"].reverse()
    assert evaluate_authority_policy(subject, evidence) == original


def test_implemented_adapter_semantics_version_is_part_of_policy_identity(monkeypatch):
    from backend.services import application_authority_policy as service

    subject, evidence = inputs()
    original = evaluate_authority_policy(subject, evidence).policy.policy_revision
    monkeypatch.setattr(service, "POLICY_ADAPTER_REVISION", 2)
    result = evaluate_authority_policy(subject, evidence)
    assert result.policy.adapter_revision == 2
    assert result.policy.policy_revision != original


@pytest.mark.parametrize(
    "field", ["policy_revision", "trust_revision", "profile_revision", "native_review_revision"]
)
def test_every_evidence_revision_changes_effective_policy_identity(field):
    subject, evidence = inputs()
    original = evaluate_authority_policy(subject, evidence).policy.policy_revision
    evidence[field] = "changed_revision"
    assert evaluate_authority_policy(subject, evidence).policy.policy_revision != original


@pytest.mark.parametrize("version", [True, 1.0, "1", 2])
def test_strict_independent_versions(version):
    subject, evidence = inputs()
    subject["subject_version"] = version
    assert reasons(evaluate_authority_policy(subject, evidence)) == {"invalid_policy_subject"}
    subject, evidence = inputs()
    evidence["evidence_version"] = version
    assert reasons(evaluate_authority_policy(subject, evidence)) == {"invalid_trusted_policy"}


@pytest.mark.parametrize("field", ["commands", "connectors", "required_scopes"])
def test_duplicate_policy_scopes_and_required_rules_are_rejected(field):
    subject, evidence = inputs()
    evidence[field] *= 2
    assert reasons(evaluate_authority_policy(subject, evidence)) == {"invalid_trusted_policy"}


def test_unknown_wildcard_missing_or_constructed_policy_input_fails_redacted():
    subject, evidence = inputs()
    for malformed in (
        {**evidence, "approved": True, "PRIVATE": "password"},
        {**evidence, "required_scopes": ["command:*"]},
        {**evidence, "required_scopes": ["command:missing"]},
        {**evidence, "commands": []},
        '{"evidence_version":1,"evidence_version":1,"PRIVATE":"password"}',
        CorePolicyEvidenceV1.model_construct(**{**evidence, "evidence_version": True}),
        "PRIVATE" * 30_000,
    ):
        result = evaluate_authority_policy(subject, malformed)
        assert reasons(result) == {"invalid_trusted_policy"}
        assert "PRIVATE" not in result.model_dump_json()


def test_invalid_subject_and_duplicate_enum_never_supply_partial_policy():
    subject, evidence = inputs()
    subject["commands"][0]["declaration"]["arguments_schema"]["properties"]["channel"]["enum"] *= 2
    assert reasons(evaluate_authority_policy(subject, evidence)) == {"invalid_policy_subject"}
    subject, evidence = inputs()
    subject["commands"] *= 2
    assert reasons(evaluate_authority_policy(subject, evidence)) == {"invalid_policy_subject"}
    unsafe = PolicySubjectV1.model_construct(**{**inputs()[0], "subject_version": True})
    assert reasons(evaluate_authority_policy(unsafe, evidence)) == {"invalid_policy_subject"}


def test_policy_evaluation_performs_no_file_database_process_or_network_io(monkeypatch):
    subject, evidence = inputs()

    def forbidden(*_args, **_kwargs):
        pytest.fail("Pure policy evaluation must not access live state or perform effects")

    for name in ("read_bytes", "read_text", "write_bytes", "write_text", "mkdir"):
        monkeypatch.setattr(Path, name, forbidden)
    for name in ("execute", "get", "add", "flush", "commit", "delete"):
        monkeypatch.setattr(Session, name, forbidden)
    for name in ("run", "Popen"):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert evaluate_authority_policy(subject, evidence).policy_resolved
