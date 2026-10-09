"""Pure internal contract vectors; no approval, live resolver or enforcement."""

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
    FINGERPRINT_DOMAIN,
    MAX_CONTEXT_BYTES,
    AuthorityReviewContextV1,
    _canonical_bytes,
    _parse,
    review_authority_context,
)


def context():
    owner = {
        "core_installation_id": "core_local",
        "application_installation_id": "app_local",
        "incarnation": "incarnation_1",
        "module_id": "org.example.reference",
    }
    return {
        "context_version": 1,
        "principal": owner,
        "candidate": {"version": "1.0.0", "sha256": "a" * 64},
        "baseline": {
            "artifact": None,
            "authority_epoch": "epoch_1",
            "grant_revision": None,
            "enforcement_mode": "review_required",
        },
        "configuration": {"key_id": "key_1", "keyed_sha256": "b" * 64},
        "policy": {
            "policy_revision": "policy_1",
            "adapter_revision": 1,
            "trust_revision": "trust_1",
            "execution_profile": "reference_profile",
            "execution_class": "proven_isolated",
            "isolation_proof_revision": "test_evidence_only",
            "allowed_scopes": ["command:pulse", "connector:business_api"],
            "required_scopes": ["command:pulse"],
            "blockers": [],
        },
        "issued_at_ms": 100_000,
        "expires_at_ms": 200_000,
        "commands": [
            {
                "declaration": {
                    "binding_id": "pulse",
                    "target_device_config_key": "TARGET_DEVICE_ID",
                    "capability_id": "gpio.digital.control",
                    "contract_version": "1.0",
                    "action": "pulse",
                    "max_ttl_seconds": 5,
                    "arguments_schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "channel": {
                                "type": "string",
                                "maxLength": 32,
                                "enum": ["output.1", "output.2"],
                            },
                            "duration_ms": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 250,
                            },
                        },
                        "required": ["channel", "duration_ms"],
                    },
                },
                "target_device_id": "dev_" + "1" * 32,
                "control_revision": "control_1",
            }
        ],
        "connectors": [
            {
                "declaration": {
                    "connector_id": "business_api",
                    "destination_config_key": "BUSINESS_API_URL",
                    "allowed_schemes": ["http", "https"],
                    "path_prefix": "/api/",
                    "authentication": "bearer",
                    "credential_ref_config_key": "BUSINESS_API_CREDENTIAL",
                    "supports_mutations": True,
                },
                "configured_origin": "https://api.example.test",
                "configured_secret_ref": "secret_" + "2" * 32,
                "stored": {
                    "owner": copy.deepcopy(owner),
                    "binding_revision": "binding_1",
                    "destination_origin": "https://api.example.test",
                    "enabled": True,
                    "credential": {
                        "owner": copy.deepcopy(owner),
                        "secret_ref": "secret_" + "2" * 32,
                        "version": 1,
                        "credential_kind": "bearer",
                        "revoked": False,
                    },
                },
            }
        ],
    }


def selection(*scopes):
    return {
        "selection_version": 1,
        "scopes": list(scopes or ("command:pulse", "connector:business_api")),
    }


def review(value=None, chosen=None, now_ms=150_000):
    return review_authority_context(
        context() if value is None else value,
        selection() if chosen is None else chosen,
        now_ms=now_ms,
    )


def reasons(result):
    assert not result.reviewable
    assert result.context_fingerprint is None
    assert result.permission_approval == "not_evaluated"
    return {i.reason for i in result.issues}


def replace_path(value, path, replacement):
    target = value
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = replacement


def test_valid_snapshot_is_reviewable_not_approved_and_has_no_execution_token():
    result = review()
    assert result.reviewable and result.issues == ()
    # Pinned full-context vector: changes require an intentional internal format
    # decision. This is not a supported public plan or signature fixture.
    assert result.context_fingerprint == (
        "cd88d66bdd44cdbba482e40d19f1d8d39bef5014a6452ad9e65e5681037b8c59"
    )
    assert result.permission_approval == "not_evaluated"
    assert "current_actor_permission" in result.not_checked
    assert "approval_persistence_and_effect_enforcement" in result.not_checked
    assert set(result.model_dump()) == {
        "reviewable",
        "issues",
        "context_fingerprint",
        "permission_approval",
        "not_checked",
    }


def test_whole_binding_subset_or_explicit_empty_selection_never_means_wildcard():
    whole = review()
    subset = review(chosen=selection("command:pulse"))
    assert subset.reviewable
    assert subset.context_fingerprint != whole.context_fingerprint
    value = context()
    value["policy"]["required_scopes"] = []
    empty = review(value, {"selection_version": 1, "scopes": []})
    assert empty.reviewable and empty.context_fingerprint != whole.context_fingerprint
    assert "required_scope_omitted" in reasons(
        review(chosen=selection("connector:business_api"))
    )


def test_selection_cannot_forge_or_narrow_a_scope_or_use_unsupported_families():
    assert "unknown_selected_scope" in reasons(
        review(chosen=selection("command:foreign"))
    )
    value = context()
    value["policy"]["allowed_scopes"] = ["connector:business_api"]
    assert "scope_not_allowed" in reasons(review(value))
    for chosen in (
        {"selection_version": 1},
        selection("command:*"),
        selection("event:scans"),
        selection("command:pulse", "command:pulse"),
        {**selection(), "target_device_id": "dev_" + "9" * 32},
        {**selection(), "scopes": [{"binding_id": "pulse", "max_ttl_seconds": 10}]},
        {**selection(), "selection_version": 2},
        {**selection(), "selection_version": True},
    ):
        assert reasons(review(chosen=chosen)) == {"invalid_selection"}


@pytest.mark.parametrize(
    "path,new",
    [
        (("context_version",), 2),
        (("context_version",), True),
        (("issued_at_ms",), "100000"),
        (("issued_at_ms",), True),
        (("expires_at_ms",), 100_000),
        (("expires_at_ms",), 3_700_001),
        (("policy", "adapter_revision"), 1.0),
        (("policy", "blockers"), ["unknown"]),
        (("policy", "required_scopes"), ["command:foreign"]),
        (("baseline", "enforcement_mode"), "enforced"),
        (("baseline", "grant_revision"), 1),
        (("commands", 0, "target_device_id"), "any-device"),
        (("commands", 0, "declaration", "max_ttl_seconds"), True),
        (("connectors", 0, "stored", "credential", "version"), 0),
        (("connectors", 0, "stored", "credential", "version"), True),
        (("connectors", 0, "stored", "enabled"), "true"),
    ],
)
def test_closed_strict_model_rejects_invalid_versions_types_and_bounds(path, new):
    value = context()
    replace_path(value, path, new)
    assert reasons(review(value)) == {"invalid_context"}


def test_duplicate_scopes_sets_and_command_enums_are_rejected():
    for field in ("commands", "connectors"):
        value = context()
        value[field].append(copy.deepcopy(value[field][0]))
        assert reasons(review(value)) == {"invalid_context"}
    value = context()
    value["policy"]["allowed_scopes"].append("command:pulse")
    assert reasons(review(value)) == {"invalid_context"}
    value = context()
    value["commands"][0]["declaration"]["arguments_schema"]["properties"]["channel"][
        "enum"
    ] *= 2
    assert reasons(review(value)) == {"invalid_context"}


@pytest.mark.parametrize(
    "now,reason",
    [
        (True, "invalid_review_clock"),
        (150_000.0, "invalid_review_clock"),
        (-1, "invalid_review_clock"),
        (99_999, "review_not_current"),
        (200_000, "review_not_current"),
    ],
)
def test_clock_is_explicit_bounded_and_expiry_is_exclusive(now, reason):
    assert reasons(review(now_ms=now)) == {reason}
    assert review(now_ms=100_000).reviewable
    assert review(now_ms=199_999).reviewable


@pytest.mark.parametrize(
    "blocker",
    [
        "configuration_unresolved",
        "unsupported_scope_family",
        "peer_authority_unresolved",
        "frontend_authority_unresolved",
        "isolation_proof_missing",
        "dependency_resolution_missing",
    ],
)
def test_missing_core_proof_is_not_cleared_by_valid_selected_bindings(blocker):
    value = context()
    value["policy"]["blockers"] = [blocker]
    assert reasons(review(value)) == {blocker}


def test_missing_isolation_revision_and_missing_command_contract_remain_unresolved():
    value = context()
    value["policy"]["isolation_proof_revision"] = None
    assert reasons(review(value)) == {"isolation_proof_missing"}
    value["policy"]["execution_class"] = "reviewed_native"
    assert review(
        value
    ).reviewable  # Core policy input, not a package-selected fallback.
    value["commands"][0]["declaration"].pop("contract_version")
    assert reasons(review(value)) == {"unsupported_command_contract"}


@pytest.mark.parametrize(
    "path,new,reason",
    [
        (
            ("configured_origin",),
            "https://other.example.test",
            "connector_origin_mismatch",
        ),
        (
            ("configured_origin",),
            "https://user:PRIVATE@api.example.test",
            "connector_origin_invalid",
        ),
        (
            ("stored", "destination_origin"),
            "https://api.example.test/?PRIVATE",
            "connector_origin_invalid",
        ),
        (
            ("stored", "destination_origin"),
            " https://api.example.test",
            "connector_origin_invalid",
        ),
        (("stored", "enabled"), False, "connector_binding_unavailable"),
        (
            ("stored", "owner", "core_installation_id"),
            "core_foreign",
            "connector_binding_unavailable",
        ),
        (
            ("stored", "owner", "incarnation"),
            "old_incarnation",
            "connector_binding_unavailable",
        ),
        (("stored", "credential"), None, "connector_credential_unavailable"),
        (
            ("stored", "credential", "owner", "application_installation_id"),
            "app_foreign",
            "connector_credential_unavailable",
        ),
        (("stored", "credential", "revoked"), True, "connector_credential_unavailable"),
        (
            ("stored", "credential", "credential_kind"),
            "basic",
            "connector_credential_mismatch",
        ),
        (
            ("configured_secret_ref",),
            "secret_" + "9" * 32,
            "connector_credential_mismatch",
        ),
        (("declaration", "path_prefix"), "/api/../admin", "connector_path_unsupported"),
        (("declaration", "path_prefix"), "/api/%2e%2e/", "connector_path_unsupported"),
    ],
)
def test_stored_connector_and_owned_credential_are_not_inferred_from_configuration(
    path, new, reason
):
    value = context()
    replace_path(value["connectors"][0], path, new)
    result = review(value)
    assert reasons(result) == {reason}
    assert "PRIVATE" not in result.model_dump_json()


def test_unauthenticated_connector_requires_no_reference_or_stored_credential():
    value = context()
    connector = value["connectors"][0]
    connector["declaration"].update(
        authentication="none", credential_ref_config_key=None
    )
    assert reasons(review(value)) == {"connector_credential_mismatch"}
    connector["configured_secret_ref"] = None
    connector["stored"]["credential"] = None
    assert review(value).reviewable


def test_sensor_binding_requires_exact_device_and_control_revision():
    value = context()
    command = value["commands"][0]
    command["declaration"].update(
        sensor_device_config_key="SENSOR_DEVICE_ID", sensor_id="passage.1"
    )
    assert reasons(review(value)) == {"invalid_context"}
    command.update(
        sensor_device_id="dev_" + "3" * 32, sensor_control_revision="sensor_1"
    )
    first = review(value)
    assert first.reviewable
    command["sensor_device_id"] = "dev_" + "4" * 32
    assert review(value).context_fingerprint != first.context_fingerprint


def test_key_and_set_order_are_canonical_but_no_caller_input_is_mutated():
    value = context()
    original = copy.deepcopy(value)
    expected = review(value)
    value = dict(reversed(list(value.items())))
    for field in ("allowed_scopes", "required_scopes", "blockers"):
        value["policy"][field].reverse()
    schema = value["commands"][0]["declaration"]["arguments_schema"]
    schema["required"].reverse()
    schema["properties"]["channel"]["enum"].reverse()
    value["connectors"][0]["declaration"]["allowed_schemes"].reverse()
    chosen = selection("connector:business_api", "command:pulse")
    before = copy.deepcopy(value)
    assert review(value, chosen) == expected
    assert value == before
    assert original == context()
    assert review(json.dumps(value), json.dumps(chosen)) == expected
    assert review(_parse(AuthorityReviewContextV1, value), chosen) == expected


@pytest.mark.parametrize(
    "path,new",
    [
        (("candidate", "sha256"), "c" * 64),
        (("candidate", "built_ui_sha256"), "d" * 64),
        (("principal", "incarnation"), "incarnation_2"),
        (("baseline", "authority_epoch"), "epoch_2"),
        (("configuration", "key_id"), "key_2"),
        (("configuration", "keyed_sha256"), "e" * 64),
        (("policy", "trust_revision"), "trust_2"),
        (("policy", "adapter_revision"), 2),
        (("expires_at_ms",), 300_000),
        (("commands", 0, "target_device_id"), "dev_" + "9" * 32),
        (("commands", 0, "control_revision"), "control_2"),
        (("commands", 0, "declaration", "max_ttl_seconds"), 10),
        (("connectors", 0, "stored", "binding_revision"), "binding_2"),
        (("connectors", 0, "stored", "credential", "version"), 2),
        (("connectors", 0, "declaration", "supports_mutations"), False),
    ],
)
def test_authority_changes_behind_same_ids_change_internal_fingerprint(path, new):
    value = context()
    replace_path(value, path, new)
    if path[0] == "principal":
        # A coherent new principal must own its resources; foreign ownership has
        # separate denial vectors above.
        for connector in value["connectors"]:
            connector["stored"]["owner"] = copy.deepcopy(value["principal"])
            connector["stored"]["credential"]["owner"] = copy.deepcopy(
                value["principal"]
            )
    changed = review(value)
    assert changed.reviewable
    assert changed.context_fingerprint != review().context_fingerprint


def test_defaulted_absence_and_null_match_but_required_absence_is_invalid():
    value = context()
    value["candidate"]["built_ui_sha256"] = None
    value["commands"][0]["sensor_device_id"] = None
    assert review(value) == review()
    value["baseline"].pop("artifact")  # Required explicit absence, not "latest".
    assert reasons(review(value)) == {"invalid_context"}


def test_origin_and_reference_rebinding_changes_fingerprint_even_with_same_ids():
    value = context()
    connector = value["connectors"][0]
    connector["configured_origin"] = "https://other.example.test"
    connector["stored"]["destination_origin"] = connector["configured_origin"]
    changed_origin = review(value)
    assert changed_origin.reviewable
    assert changed_origin.context_fingerprint != review().context_fingerprint
    connector["configured_secret_ref"] = "secret_" + "8" * 32
    connector["stored"]["credential"]["secret_ref"] = connector["configured_secret_ref"]
    assert review(value).context_fingerprint != changed_origin.context_fingerprint


def test_resource_collections_are_sets_and_omitted_resources_do_not_hide_failures():
    value = context()
    command = copy.deepcopy(value["commands"][0])
    command["declaration"]["binding_id"] = "pulse_other"
    value["commands"].append(command)
    connector = copy.deepcopy(value["connectors"][0])
    connector["declaration"]["connector_id"] = "business_other"
    value["connectors"].append(connector)
    expected = review(value)
    assert expected.reviewable
    value["commands"].reverse()
    value["connectors"].reverse()
    assert review(value) == expected
    value["connectors"][0]["stored"]["enabled"] = False
    assert reasons(review(value)) == {"connector_binding_unavailable"}


def test_oversize_mapping_and_raw_model_cannot_bypass_early_byte_limit():
    value = context()
    field = value["commands"][0]["declaration"]["arguments_schema"]["properties"][
        "channel"
    ]
    field["maxLength"] = 512
    field["enum"] = [str(i).rjust(512, "x") for i in range(300)]
    assert reasons(review(value)) == {"invalid_context"}


def test_canonical_byte_vector_preserves_sequence_types_unicode_and_negative_zero():
    expected = b'["object",[["a",["array",[["bool",true],["int","1"],["float","0x1.0000000000000p+0"],["float","-0x0.0p+0"],["null"]]]],["z",["str","\\u0431"]]]]'
    encoded = _canonical_bytes({"z": "б", "a": [True, 1, 1.0, -0.0, None]})
    assert encoded == expected
    assert _canonical_bytes([1, 2]) != _canonical_bytes([2, 1])
    assert _canonical_bytes(1) != _canonical_bytes(1.0) != _canonical_bytes(True)
    assert _canonical_bytes(0.0) != _canonical_bytes(-0.0)
    assert _canonical_bytes("é") != _canonical_bytes("e\u0301")
    assert (
        hashlib.sha256(FINGERPRINT_DOMAIN + encoded).hexdigest()
        != hashlib.sha256(encoded).hexdigest()
    )


@pytest.mark.parametrize(
    "invalid",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        2**53,
        "x" * (MAX_CONTEXT_BYTES + 1),
        {"unknown": "PRIVATE"},
        {"private_configuration": {"PASSWORD": "PRIVATE"}},
        {"context_version": 1, "context_version_PRIVATE": 1},
        '{"context_version":1,"context_version":1}',
        '{"owner":{"id":1,"id":2}}',
        '{"PRIVATE":NaN}',
        {1: "PRIVATE"},
        {"value": "\ud800"},
        b"PRIVATE",
    ],
    ids=[f"malformed-{index}" for index in range(14)],
)
def test_malformed_oversize_unknown_secret_and_duplicate_input_is_redacted(invalid):
    result = review(invalid)
    assert reasons(result) == {"invalid_context"}
    assert "PRIVATE" not in result.model_dump_json()


def test_cycles_depth_nodes_and_constructed_models_cannot_skip_validation():
    cycle = []
    cycle.append(cycle)
    assert reasons(review({"cycle": cycle})) == {"invalid_context"}
    deep = {}
    for _ in range(30):
        deep = {"next": deep}
    assert reasons(review(deep)) == {"invalid_context"}
    assert reasons(review({"nodes": [0] * 16_384})) == {"invalid_context"}
    unsafe = AuthorityReviewContextV1.model_construct(
        **{**context(), "context_version": 2}
    )
    assert reasons(review(unsafe)) == {"invalid_context"}


def test_context_review_has_no_file_database_process_network_or_implicit_clock_io(
    monkeypatch,
):
    value, chosen = context(), selection()
    before = copy.deepcopy(value)

    def forbidden(*_args, **_kwargs):
        pytest.fail(
            "Pure context review must not access live authority or perform effects"
        )

    for name in ("read_bytes", "read_text", "write_bytes", "write_text", "mkdir"):
        monkeypatch.setattr(Path, name, forbidden)
    for name in ("execute", "get", "add", "flush", "commit", "delete"):
        monkeypatch.setattr(Session, name, forbidden)
    for name in ("run", "Popen"):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    result = review(value, chosen)
    assert result.reviewable and result == review(value, chosen)
    assert value == before and chosen == selection()
