"""Real package validators feed an advisory comparison; nothing is installed."""

import copy
import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest
import requests
from sqlalchemy.orm import Session

from backend.services.application_authority_review import review_application_authority
from backend.services.module_packages import validate_module_package
from backend.tests.test_module_packages import (
    APPLICATION_WHEEL,
    application_definition,
    application_manifest,
    application_package,
    package,
)


CONFIG = {
    "READER_DEVICE_ID": "dev_" + "1" * 32,
    "BUSINESS_API_URL": "https://api.example.test",
    "BUSINESS_API_CREDENTIAL": "secret_" + "2" * 32,
}


def validated(*, definition=None, manifest=None):
    return validate_module_package(
        application_package(
            definition=definition,
            manifest_value=manifest,
        )
    )


def review(candidate, previous=None, **kwargs):
    return review_application_authority(
        candidate,
        previous=previous,
        candidate_configuration=kwargs.pop("candidate_configuration", CONFIG),
        previous_configuration=kwargs.pop(
            "previous_configuration", CONFIG if previous else None
        ),
        **kwargs,
    )


def changes(result):
    return {item.scope: item for item in result.changes}


def with_commands(*, maximum=250, ttl=5, enum=None, sensor=False):
    manifest = application_manifest()
    manifest["permissions"].append("capabilities.invoke")
    manifest["capabilities"]["consumes"].append("gpio.digital.control")
    properties = manifest["configuration_schema"]["properties"]
    properties["TARGET_DEVICE_ID"] = {"type": "string"}
    definition = application_definition()
    command = {
        "binding_id": "pulse",
        "target_device_config_key": "TARGET_DEVICE_ID",
        "capability_id": "gpio.digital.control",
        "contract_version": "1.0",
        "action": "pulse",
        "max_ttl_seconds": ttl,
        "arguments_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "channel": {
                    "type": "string",
                    "maxLength": 32,
                    "enum": enum or ["output.1"],
                },
                "duration_ms": {"type": "integer", "minimum": 1, "maximum": maximum},
            },
            "required": ["channel", "duration_ms"],
        },
    }
    configuration = {**CONFIG, "TARGET_DEVICE_ID": "dev_" + "3" * 32}
    if sensor:
        properties["SENSOR_DEVICE_ID"] = {"type": "string"}
        command.update(
            sensor_device_config_key="SENSOR_DEVICE_ID", sensor_id="passage.1"
        )
        configuration["SENSOR_DEVICE_ID"] = "dev_" + "4" * 32
    definition["command_bindings"] = [command]
    return validated(definition=definition, manifest=manifest), configuration


def test_first_install_lists_requests_without_approval_or_grant_baseline():
    result = review(validated())
    assert result.baseline == "no_previous_package"
    assert result.previous_sha256 is None and result.previous_version is None
    assert result.candidate_version == "1.0.0"
    assert result.permission_approval == "not_evaluated"
    assert result.declaration_review_required and result.artifact_changed
    assert all(
        item.change == "added" and item.potential_expansion for item in result.changes
    )
    assert "approved_grants" in result.not_checked
    assert "stored_connector_bindings_and_secret_generations" in result.not_checked
    assert any(
        item.reason == "executable_frontend_effects_not_inferred"
        for item in result.unresolved
    )


def test_exact_package_and_config_still_do_not_assert_permission_approval():
    current = validated()
    result = review(current, current)
    assert result.baseline == "previous_declarations"
    assert result.changes == () and not result.artifact_changed
    assert result.permission_approval == "not_evaluated"
    # Same-origin compiled code is not a provable manifest-only authority set.
    assert result.declaration_review_required


def test_headless_empty_diff_is_not_an_approval():
    definition = application_definition(routes=[])
    manifest = application_manifest(
        runtimes=["core"], entrypoints={"core": "application-extension.json"}
    )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("application-extension.json", json.dumps(definition))
        archive.writestr(definition["service"]["artifact"], APPLICATION_WHEEL)
    current = validate_module_package(stream.getvalue())
    result = review(current, current)
    assert not result.declaration_review_required
    assert result.changes == () and result.unresolved == ()
    assert result.permission_approval == "not_evaluated"
    assert "os_and_browser_isolation" in result.not_checked


def test_new_artifact_with_only_cosmetic_changes_still_needs_review():
    definition = application_definition()
    definition["permissions"][0]["label"] = {"en": "New label"}
    definition["routes"][0].update(navigation=False, order=5)
    candidate = validated(
        definition=definition, manifest=application_manifest(name="New display name")
    )
    result = review(candidate, validated())
    assert result.artifact_changed and result.declaration_review_required
    assert result.changes == ()


def test_manifest_and_platform_permission_addition_and_removal_are_separate():
    definition = application_definition(
        platform_permissions=["installation.identity.read"]
    )
    definition["service"]["sdk_version"] = "1.3"
    manifest = application_manifest()
    manifest["permissions"].append("installation.identity.read")
    elevated = validated(definition=definition, manifest=manifest)
    normal = validated()
    added = changes(review(elevated, normal))
    assert added["platform:installation.identity.read"].change == "added"
    assert added["permission:installation.identity.read"].potential_expansion
    removed = changes(review(normal, elevated))
    assert removed["platform:installation.identity.read"].change == "removed"
    assert not removed["permission:installation.identity.read"].potential_expansion
    assert "runtime" in removed  # SDK/runtime changes are not silently hidden.


def test_same_config_key_different_device_changes_event_and_command_scopes():
    current, configuration = with_commands()
    result = review(
        current,
        current,
        previous_configuration=configuration,
        candidate_configuration={
            **configuration,
            "TARGET_DEVICE_ID": "dev_" + "5" * 32,
            "READER_DEVICE_ID": "dev_" + "6" * 32,
        },
    )
    diff = changes(result)
    assert not result.artifact_changed
    assert set(diff) == {"command:pulse", "event:identifier_scans"}
    assert (
        diff["command:pulse"].before["target_device_id"]
        == configuration["TARGET_DEVICE_ID"]
    )
    assert diff["command:pulse"].after["target_device_id"] == "dev_" + "5" * 32
    assert diff["event:identifier_scans"].potential_expansion


@pytest.mark.parametrize(
    "updates",
    [
        {"maximum": 1000},
        {"ttl": 10},
        {"enum": ["output.1", "output.2"]},
    ],
)
def test_command_bounds_ttl_and_channels_cannot_hide_potential_expansion(updates):
    previous, configuration = with_commands()
    candidate, _ = with_commands(**updates)
    item = changes(
        review(
            candidate,
            previous,
            previous_configuration=configuration,
            candidate_configuration=configuration,
        )
    )["command:pulse"]
    assert item.change == "changed" and item.potential_expansion
    assert item.before != item.after


def test_sensor_target_change_is_reviewable_even_when_command_target_stays_same():
    current, configuration = with_commands(sensor=True)
    item = changes(
        review(
            current,
            current,
            previous_configuration=configuration,
            candidate_configuration={
                **configuration,
                "SENSOR_DEVICE_ID": "dev_" + "7" * 32,
            },
        )
    )["command:pulse"]
    assert item.before["target_device_id"] == item.after["target_device_id"]
    assert item.before["sensor_device_id"] != item.after["sensor_device_id"]


def test_connector_origin_reference_and_mutation_changes_require_review():
    current = validated()
    result = review(
        current,
        current,
        candidate_configuration={
            **CONFIG,
            "BUSINESS_API_URL": "https://other.example.test",
            "BUSINESS_API_CREDENTIAL": "secret_" + "8" * 32,
        },
    )
    item = changes(result)["connector:business_api"]
    assert item.after["configured_origin"] == "https://other.example.test"
    assert item.before["credential_reference"] != item.after["credential_reference"]
    definition = application_definition()
    definition["connectors"][0]["supports_mutations"] = False
    # Conservatively changed, NOT a claimed proof of semantic narrowing.
    item = changes(review(validated(definition=definition), current))[
        "connector:business_api"
    ]
    assert item.change == "changed" and item.potential_expansion


def test_human_route_and_operation_access_changes_are_not_service_grants():
    definition = application_definition()
    definition["routes"][1].update(audience="administrator", required_permissions=[])
    definition["operations"][2].update(audiences=["public"], required_permission=None)
    diff = changes(review(validated(definition=definition), validated()))
    assert diff["route:operations"].potential_expansion
    assert diff["operation:approve"].after["audiences"] == ["public"]
    assert diff["operation:approve"].after["required_permission"] is None


def test_order_does_not_change_command_or_permission_declarations():
    previous, configuration = with_commands(enum=["output.1", "output.2"])
    definition = previous.application_extension.model_dump(mode="json")
    definition["operations"].reverse()
    definition["routes"][1]["required_permissions"].reverse()
    command = definition["command_bindings"][0]["arguments_schema"]
    command["required"].reverse()
    command["properties"]["channel"]["enum"].reverse()
    manifest = previous.manifest.model_dump(mode="json")
    manifest["permissions"].reverse()
    manifest["configuration_schema"]["properties"] = dict(
        reversed(list(manifest["configuration_schema"]["properties"].items()))
    )
    result = review(
        validated(definition=definition, manifest=manifest),
        previous,
        previous_configuration=configuration,
        candidate_configuration=dict(reversed(list(configuration.items()))),
    )
    assert result.changes == ()


@pytest.mark.parametrize(
    "configuration,reason",
    [
        (None, "effective_configuration_not_supplied"),
        ({}, "effective_configuration_invalid_or_incomplete"),
        (
            {**CONFIG, "BUSINESS_API_URL": 42},
            "effective_configuration_invalid_or_incomplete",
        ),
        (
            {**CONFIG, "BUSINESS_API_URL": "x" * (32 * 1024)},
            "effective_configuration_invalid_or_incomplete",
        ),
    ],
)
def test_missing_or_invalid_configuration_stays_unresolved(configuration, reason):
    current = validated()
    result = review(current, current, candidate_configuration=configuration)
    assert any(
        item.side == "candidate" and item.reason == reason for item in result.unresolved
    )
    assert result.declaration_review_required
    event = changes(result)["event:identifier_scans"]
    assert event.after["device_id"] is None


def test_defaults_do_not_masquerade_as_effective_bindings():
    current = validated(
        manifest=application_manifest(
            configuration_defaults={"READER_DEVICE_ID": CONFIG["READER_DEVICE_ID"]}
        )
    )
    result = review_application_authority(current)
    assert changes(result)["event:identifier_scans"].after["device_id"] is None
    assert any(
        item.reason == "effective_configuration_not_supplied"
        for item in result.unresolved
    )


def test_passwords_tokens_and_unsafe_urls_are_not_returned_or_echoed():
    current = validated()
    configuration = {
        "READER_DEVICE_ID": "not-a-device-PRIVATE",
        "BUSINESS_API_URL": "https://user:PRIVATE_PASSWORD@api.example.test/?token=PRIVATE_TOKEN",
        "BUSINESS_API_CREDENTIAL": "PRIVATE_SECRET_VALUE",
    }
    result = review(current, current, candidate_configuration=configuration)
    rendered = result.model_dump_json()
    assert "PRIVATE" not in rendered
    assert changes(result)["connector:business_api"].after["configured_origin"] is None
    assert (
        changes(result)["connector:business_api"].after["credential_reference"] is None
    )
    assert len([item for item in result.unresolved if item.side == "candidate"]) == 4


def test_unrelated_configuration_and_schema_defaults_are_not_disclosed():
    manifest = application_manifest()
    manifest["configuration_schema"]["properties"]["PRIVATE_NOTE"] = {
        "type": "string",
        "default": "SCHEMA_PRIVATE_VALUE",
    }
    current = validated(manifest=manifest)
    configuration = {**CONFIG, "PRIVATE_NOTE": "UNRELATED_PRIVATE_VALUE"}
    result = review(current, candidate_configuration=configuration)
    assert "SCHEMA_PRIVATE_VALUE" not in result.model_dump_json()
    assert "UNRELATED_PRIVATE_VALUE" not in result.model_dump_json()


def test_unsupported_types_and_mismatched_baselines_are_rejected():
    with pytest.raises(ValueError, match="application packages only"):
        review_application_authority(validate_module_package(package()))
    with pytest.raises(ValueError, match="same module identity"):
        review(validated(), validate_module_package(package()))
    with pytest.raises(ValueError, match="Previous configuration"):
        review_application_authority(validated(), previous_configuration=CONFIG)


def test_review_has_no_io_and_does_not_mutate_any_input(monkeypatch):
    current = validated()
    configuration = copy.deepcopy(CONFIG)
    manifest = current.manifest.model_dump(mode="json")
    definition = current.application_extension.model_dump(mode="json")

    def forbidden(*_args, **_kwargs):
        pytest.fail(
            "read-only authority comparison must not access persistence, runtime or network"
        )

    for name in ("write_bytes", "write_text", "mkdir", "read_bytes", "read_text"):
        monkeypatch.setattr(Path, name, forbidden)
    for name in ("add", "execute", "get", "commit", "flush", "delete"):
        monkeypatch.setattr(Session, name, forbidden)
    for name in ("run", "Popen"):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(zipfile.ZipFile, "extractall", forbidden)
    first = review(
        current,
        current,
        candidate_configuration=configuration,
        previous_configuration=configuration,
    )
    second = review(
        current,
        current,
        candidate_configuration=configuration,
        previous_configuration=configuration,
    )
    assert first == second
    assert configuration == CONFIG
    assert current.manifest.model_dump(mode="json") == manifest
    assert current.application_extension.model_dump(mode="json") == definition
