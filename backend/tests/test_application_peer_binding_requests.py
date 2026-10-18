"""Real ZIP requests and redacted declaration diffs; no live peer authority."""

import json

import pytest

from backend.services.application_authority_review import review_application_authority
from backend.services.module_packages import ModulePackageError, validate_module_package
from backend.tests.test_application_authority_review import CONFIG
from backend.tests.test_application_authority_sources import (
    installed as source_state,
    replace_archive,
    resolve,
)
from backend.tests.test_installation_peers import peer_package
from backend.tests.test_module_packages import application_package
from three_mm_protocol.tests.test_application_peer_bindings import peer_request


LINK = "peer_" + "a" * 32


def peer_package_request(
    *, operations=None, direction="outbound", configuration_field=None
):
    _, definition, manifest = peer_package()
    definition["service"]["sdk_version"] = "1.3"
    definition["peer_bindings"] = [
        peer_request(
            direction=direction,
            operations=operations if operations is not None else ["read", "enroll"],
        )
    ]
    manifest["configuration_schema"]["properties"]["PEER_LINK"] = (
        configuration_field if configuration_field is not None else {"type": "string"}
    )
    return definition, manifest


def validated(*, operations=None, direction="outbound"):
    definition, manifest = peer_package_request(
        operations=operations, direction=direction
    )
    return validate_module_package(
        application_package(definition=definition, manifest_value=manifest)
    )


def peer_changes(result):
    return {
        change.scope: change
        for change in result.changes
        if change.scope.startswith("peer:")
    }


def test_zip_binds_exact_requests_and_existing_manifest_groups():
    package = validated()
    assert package.application_extension.peer_bindings[0].operations == (
        "read",
        "enroll",
    )
    definition, manifest = peer_package_request()
    manifest["permissions"].remove("installation.peers.enroll")
    with pytest.raises(ModulePackageError, match="permissions must match"):
        validate_module_package(
            application_package(definition=definition, manifest_value=manifest)
        )


def test_approval_request_requires_the_existing_receiver_contract_not_just_receive_permission():
    assert (
        validated(
            direction="inbound", operations=["approve"]
        ).application_extension.peer_receiver
        is not None
    )
    definition, manifest = peer_package_request(
        direction="inbound", operations=["approve"]
    )
    definition.pop("peer_receiver")
    with pytest.raises(ModulePackageError, match="require a receiver declaration"):
        validate_module_package(
            application_package(definition=definition, manifest_value=manifest)
        )


@pytest.mark.parametrize("kind", ["missing", "integer", "object", "null", "opaque"])
def test_peer_reference_must_exist_as_a_declared_string_not_an_arbitrary_object(kind):
    definition, manifest = peer_package_request()
    properties = manifest["configuration_schema"]["properties"]
    if kind == "missing":
        del properties["PEER_LINK"]
    else:
        properties["PEER_LINK"] = {"type": kind} if kind != "opaque" else {}
    with pytest.raises(ModulePackageError, match="undeclared keys|string fields"):
        validate_module_package(
            application_package(definition=definition, manifest_value=manifest)
        )


def test_diff_keeps_each_action_separate_and_is_never_approved_or_current_peer_evidence():
    candidate = validated()
    result = review_application_authority(
        candidate, candidate_configuration={**CONFIG, "PEER_LINK": LINK}
    )
    changes = peer_changes(result)
    assert set(changes) == {"peer:primary:read", "peer:primary:enroll"}
    for scope, change in changes.items():
        assert change.change == "added" and change.potential_expansion
        assert change.after == {
            "contract_version": 1,
            "binding_id": "primary",
            "direction": "outbound",
            "peer_id_config_key": "PEER_LINK",
            "peer_id": LINK,
            "operation": scope.split(":")[-1],
        }
    assert result.permission_approval == "not_evaluated"
    assert {
        item.scope
        for item in result.unresolved
        if item.reason == "peer_runtime_authority_not_implemented"
    } == set(changes)
    assert not any(
        "credential" in key or "grant" in key
        for change in changes.values()
        for key in change.after
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        "PASSWORD_MUST_NOT_LEAK",
        "peer_*",
        "peer_" + "b" * 33,
        {"key": "PRIVATE"},
        123,
    ],
)
def test_missing_or_invalid_saved_binding_never_echoes_values_or_resolves_a_wildcard(
    value,
):
    config = CONFIG if value is None else {**CONFIG, "PEER_LINK": value}
    result = review_application_authority(validated(), candidate_configuration=config)
    assert all(
        change.after["peer_id"] is None for change in peer_changes(result).values()
    )
    assert result.unresolved
    assert "PASSWORD_MUST_NOT_LEAK" not in result.model_dump_json()
    assert '"key"' not in result.model_dump_json()


def test_operation_reordering_has_no_semantic_diff_and_removed_actions_do_not_expand():
    previous = validated(operations=["read", "enroll", "rotate"])
    same = validated(operations=["rotate", "read", "enroll"])
    config = {**CONFIG, "PEER_LINK": LINK}
    result = review_application_authority(
        same,
        previous=previous,
        candidate_configuration=config,
        previous_configuration=config,
    )
    assert peer_changes(result) == {}
    reduced = review_application_authority(
        validated(operations=["read"]),
        previous=previous,
        candidate_configuration=config,
        previous_configuration=config,
    )
    assert set(peer_changes(reduced)) == {"peer:primary:enroll", "peer:primary:rotate"}
    assert all(
        change.change == "removed" and not change.potential_expansion
        for change in peer_changes(reduced).values()
    )


@pytest.mark.parametrize("change", ["peer", "direction"])
def test_saved_target_or_direction_changes_require_new_review(change):
    previous = validated(operations=["read"])
    candidate = validated(
        operations=["read"],
        direction="inbound" if change == "direction" else "outbound",
    )
    before = {**CONFIG, "PEER_LINK": LINK}
    after = {**before, "PEER_LINK": "peer_" + "b" * 32} if change == "peer" else before
    result = review_application_authority(
        candidate,
        previous=previous,
        candidate_configuration=after,
        previous_configuration=before,
    )
    action = peer_changes(result)["peer:primary:read"]
    assert action.change == "changed" and action.potential_expansion


def test_sources_keep_peer_blocker_even_with_resolvable_command_connector_requests(
    source_state,
):
    state = source_state
    definition = state.validated.application_extension.model_dump(mode="json")
    definition["service"]["sdk_version"] = "1.3"
    definition["platform_permissions"] = ["installation.peers.enroll"]
    definition["peer_bindings"] = [peer_request(operations=["read"])]
    manifest = state.validated.manifest.model_dump(mode="json")
    manifest["configuration_schema"]["properties"]["PEER_LINK"] = {"type": "string"}
    manifest["permissions"].append("installation.peers.enroll")
    replace_archive(
        state,
        definition=definition,
        manifest=manifest,
        configuration={**state.configuration, "PEER_LINK": LINK},
    )
    result = resolve(state)
    assert result.sources_resolved and result.commands and result.connectors
    assert "peer_authority_unresolved" in {issue.reason for issue in result.issues}
    assert not result.reviewable and result.permission_approval == "not_evaluated"
    assert "PRIVATE_MUST_NOT_APPEAR" not in json.dumps(result.model_dump(mode="json"))
