"""Exact checkpoint requests are author declarations, never resource grants."""

import json

import pytest
from pydantic import ValidationError

from three_mm_protocol import ApplicationCheckpointV1, ApplicationExtensionV1
from three_mm_protocol.application_extension import parse_application_extension
from three_mm_protocol.extension_schemas import extension_schema_catalog
from three_mm_protocol.tests.test_application_extension import definition


def checkpoint_request(**changes):
    return {
        "contract_version": 1,
        "checkpoint_id": "catalog",
        "mode": "read_write",
        "max_value_bytes": 4096,
        **changes,
    }


def checkpoint_application(*requests, sdk="1.3"):
    value = definition(checkpoints=list(requests))
    value["service"]["sdk_version"] = sdk
    return value


@pytest.mark.parametrize("mode", ["read", "read_write"])
def test_exact_request_roundtrips_and_cannot_be_mutated(mode):
    value = checkpoint_request(mode=mode)
    request = ApplicationCheckpointV1.model_validate(value)
    assert request.model_dump(mode="json") == value
    assert ApplicationCheckpointV1.model_validate_json(request.model_dump_json()) == request
    with pytest.raises(ValidationError, match="frozen"):
        request.mode = "read"


@pytest.mark.parametrize("field", tuple(checkpoint_request()))
def test_every_identity_mode_and_bound_is_explicit(field):
    value = checkpoint_request()
    del value[field]
    with pytest.raises(ValidationError):
        ApplicationCheckpointV1.model_validate(value)


@pytest.mark.parametrize("version", [True, False, "1", 1.0, 0, 2, None])
def test_contract_version_refuses_coercion_and_unknown_versions(version):
    with pytest.raises(ValidationError):
        ApplicationCheckpointV1.model_validate(checkpoint_request(contract_version=version))


@pytest.mark.parametrize(
    "value", [True, False, 1.0, "4096", 0, -1, 262145, None, float("inf"), float("nan")]
)
def test_value_bound_is_a_strict_bounded_positive_integer(value):
    with pytest.raises(ValidationError):
        ApplicationCheckpointV1.model_validate(checkpoint_request(max_value_bytes=value))


@pytest.mark.parametrize("value", [1, 262144])
def test_value_bound_inclusive_extremes_are_not_clamped(value):
    assert (
        ApplicationCheckpointV1.model_validate(checkpoint_request(max_value_bytes=value))
        .max_value_bytes == value
    )


@pytest.mark.parametrize(
    "identifier",
    ["", "*", "catalog:*", "../catalog", "/catalog", "catalog.page", "a-b", "A", "1a",
     " catalog", "catalog\n", "a" * 97, 1, True, None],
)
def test_checkpoint_id_is_exact_and_cannot_select_paths_or_wildcards(identifier):
    with pytest.raises(ValidationError):
        ApplicationCheckpointV1.model_validate(checkpoint_request(checkpoint_id=identifier))


@pytest.mark.parametrize("identifier", ["a", "catalog_42", "a" * 96])
def test_checkpoint_ids_match_the_existing_broker_identity_bounds(identifier):
    assert (
        ApplicationCheckpointV1.model_validate(checkpoint_request(checkpoint_id=identifier))
        .checkpoint_id == identifier
    )


@pytest.mark.parametrize("mode", ["write", "*", "admin", "read_write ", ["read"], True, None])
def test_mode_is_closed_and_not_coerced(mode):
    with pytest.raises(ValidationError):
        ApplicationCheckpointV1.model_validate(checkpoint_request(mode=mode))


@pytest.mark.parametrize(
    "field", ["owner", "installation_id", "path", "grant", "approved", "revision", "unlimited"]
)
def test_package_cannot_supply_checkpoint_owner_authority_or_live_revision(field):
    with pytest.raises(ValidationError, match="Extra inputs"):
        ApplicationCheckpointV1.model_validate(checkpoint_request(**{field: "foreign"}))


@pytest.mark.parametrize("sdk", ["1.0", "1.1", "1.2", "1.3"])
def test_optional_declaration_preserves_old_sdk_packages_and_requires_13(sdk):
    old = definition()
    old["service"]["sdk_version"] = sdk
    absent = parse_application_extension(json.dumps(old))
    assert absent.checkpoints == ()
    # An explicitly empty list creates no capability or platform permission.
    assert parse_application_extension(json.dumps({**old, "checkpoints": []})) == absent
    declared = checkpoint_application(checkpoint_request(), sdk=sdk)
    if sdk == "1.3":
        application = parse_application_extension(json.dumps(declared))
        assert application.checkpoints[0].checkpoint_id == "catalog"
        assert application.platform_permissions == ()
    else:
        with pytest.raises(ValidationError, match="require SDK 1.3"):
            parse_application_extension(json.dumps(declared))


def test_distinct_requests_are_bounded_and_duplicate_ids_are_refused():
    maximum = [checkpoint_request(checkpoint_id=f"item_{index}") for index in range(32)]
    assert len(ApplicationExtensionV1.model_validate(checkpoint_application(*maximum)).checkpoints) == 32
    with pytest.raises(ValidationError, match="at most 32"):
        ApplicationExtensionV1.model_validate(
            checkpoint_application(*maximum, checkpoint_request(checkpoint_id="overflow"))
        )
    with pytest.raises(ValidationError, match="checkpoint IDs must be unique"):
        ApplicationExtensionV1.model_validate(
            checkpoint_application(checkpoint_request(), checkpoint_request(mode="read"))
        )


@pytest.mark.parametrize("duplicate", ["checkpoint_id", "max_value_bytes", "checkpoints"])
def test_authoritative_raw_parser_refuses_duplicate_keys_and_hidden_opt_in(duplicate):
    raw = json.dumps(checkpoint_application(checkpoint_request()))
    if duplicate == "checkpoint_id":
        raw = raw.replace('"checkpoint_id": "catalog"', '"checkpoint_id": "other", "checkpoint_id": "catalog"')
    elif duplicate == "max_value_bytes":
        raw = raw.replace('"max_value_bytes": 4096', '"max_value_bytes": 262144, "max_value_bytes": 4096')
    else:
        raw = raw[:-1] + ', "checkpoints": []}'
    with pytest.raises(ValueError, match="duplicate JSON keys"):
        parse_application_extension(raw.encode("utf-8"))


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_raw_parser_does_not_coerce_non_json_limit_numbers(constant):
    raw = json.dumps(checkpoint_application(checkpoint_request()))
    raw = raw.replace('"max_value_bytes": 4096', '"max_value_bytes": ' + constant)
    with pytest.raises(ValueError, match="non-finite"):
        parse_application_extension(raw)


def test_public_schema_exposes_only_the_exact_bounded_declaration_not_approval():
    entry = extension_schema_catalog()["contracts"]["application-extension.v1"]
    schema = entry["schema"]
    declaration = schema["$defs"]["ApplicationCheckpointV1"]
    assert declaration["additionalProperties"] is False
    assert set(declaration["required"]) == set(checkpoint_request())
    assert declaration["properties"]["max_value_bytes"]["minimum"] == 1
    assert declaration["properties"]["max_value_bytes"]["maximum"] == 262144
    assert schema["properties"]["checkpoints"]["maxItems"] == 32
    assert "checkpoints" not in schema["required"]
    assert "approved" not in declaration["properties"]
    support = entry["declaration_support"]["checkpoints"]
    assert support["contract_version"] == 1 and support["sdk_version"] == "1.3"
    assert support["declaration_validation"] == "supported"
    assert support["runtime_authority"] == "reviewed_native_scoped_local"
    assert support["authority_administration"] == "core_admin_review_api"
    assert support["max_checkpoints"] == 32 and support["max_value_bytes"] == 262144
