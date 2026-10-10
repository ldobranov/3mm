"""Own-SQLite author requests are strict declarations, never executable grants."""

import json

import pytest
from pydantic import ValidationError

from three_mm_protocol import ApplicationExtensionV1, ApplicationRelationalStorageV1
from three_mm_protocol.application_extension import parse_application_extension
from three_mm_protocol.extension_schemas import extension_schema_catalog
from three_mm_protocol.tests.test_application_extension import definition
from three_mm_protocol.tests.test_application_private_files import file_request


def relational_request(**changes):
    return {
        "contract_version": 1,
        "mode": "read_write",
        "limit_class": "cooperative_v1",
        "max_database_bytes": 64 * 1024 * 1024,
        "auxiliary_pause_bytes": 16 * 1024 * 1024,
        "max_statement_bytes": 65536,
        "max_value_bytes": 262144,
        "max_result_bytes": 1048576,
        "max_result_rows": 1000,
        "max_transaction_ms": 5000,
        "max_busy_ms": 1000,
        **changes,
    }


@pytest.mark.parametrize("mode", ["read", "read_write"])
def test_exact_profile_roundtrips_and_is_immutable_not_a_grant(mode):
    request = ApplicationRelationalStorageV1.model_validate(
        relational_request(mode=mode)
    )
    assert request.model_dump(mode="json") == relational_request(mode=mode)
    assert (
        ApplicationRelationalStorageV1.model_validate_json(request.model_dump_json())
        == request
    )
    with pytest.raises(ValidationError, match="frozen"):
        request.mode = "read"


@pytest.mark.parametrize("field", tuple(relational_request()))
def test_every_bound_and_policy_field_is_explicit(field):
    request = relational_request()
    del request[field]
    with pytest.raises(ValidationError):
        ApplicationRelationalStorageV1.model_validate(request)


@pytest.mark.parametrize("version", [True, False, 1.0, "1", 0, 2, None])
def test_version_is_an_exact_supported_integer(version):
    with pytest.raises(ValidationError):
        ApplicationRelationalStorageV1.model_validate(
            relational_request(contract_version=version)
        )


LIMITS = (
    ("max_database_bytes", 65536, 256 * 1024 * 1024),
    ("auxiliary_pause_bytes", 65536, 64 * 1024 * 1024),
    ("max_statement_bytes", 1, 65536),
    ("max_value_bytes", 1, 1048576),
    ("max_result_bytes", 1, 1048576),
    ("max_result_rows", 1, 1000),
    ("max_transaction_ms", 100, 30000),
    ("max_busy_ms", 0, 5000),
)


@pytest.mark.parametrize("field, minimum, maximum", LIMITS)
def test_limits_are_strict_and_bounded_without_coercion(field, minimum, maximum):
    for value in (True, False, 1.0, "100", None, minimum - 1, maximum + 1):
        with pytest.raises(ValidationError):
            ApplicationRelationalStorageV1.model_validate(
                relational_request(**{field: value})
            )
    schema = ApplicationRelationalStorageV1.model_json_schema()["properties"][field]
    assert schema["minimum"] == minimum and schema["maximum"] == maximum


@pytest.mark.parametrize(
    "changes",
    [
        dict(max_result_bytes=1),
        dict(max_database_bytes=65536),
        dict(max_transaction_ms=100),
    ],
)
def test_limits_must_be_coherent(changes):
    with pytest.raises(ValidationError, match="inconsistent"):
        ApplicationRelationalStorageV1.model_validate(relational_request(**changes))


def test_valid_low_and_high_bounds_and_nonblocking_busy_are_not_clamped():
    low = {field: minimum for field, minimum, _ in LIMITS}
    high = {field: maximum for field, _, maximum in LIMITS}
    for bounds in (low, high, dict(max_busy_ms=0)):
        value = relational_request(**bounds)
        assert (
            ApplicationRelationalStorageV1.model_validate(value).model_dump() == value
        )


@pytest.mark.parametrize(
    "field",
    [
        "path",
        "database_url",
        "namespace",
        "owner",
        "approved",
        "grant",
        "lifecycle_token",
        "execution_profile",
    ],
)
def test_package_cannot_select_paths_owners_or_authority(field):
    with pytest.raises(ValidationError, match="Extra inputs"):
        ApplicationRelationalStorageV1.model_validate(
            relational_request(**{field: "foreign"})
        )


@pytest.mark.parametrize(
    "changes",
    [
        dict(mode="*"),
        dict(mode="write"),
        dict(mode=True),
        dict(limit_class="isolated"),
        dict(limit_class="unlimited"),
    ],
)
def test_modes_and_limit_class_are_closed(changes):
    with pytest.raises(ValidationError):
        ApplicationRelationalStorageV1.model_validate(relational_request(**changes))


@pytest.mark.parametrize("sdk", ["1.0", "1.1", "1.2", "1.3"])
def test_optional_declaration_preserves_legacy_and_requires_sdk_13(sdk):
    value = definition()
    value["service"]["sdk_version"] = sdk
    assert parse_application_extension(json.dumps(value)).storage.relational is None
    value["storage"]["relational"] = relational_request()
    if sdk != "1.3":
        with pytest.raises(ValidationError, match="require SDK 1.3"):
            parse_application_extension(json.dumps(value))
    else:
        assert (
            parse_application_extension(json.dumps(value)).storage.relational.mode
            == "read_write"
        )


def test_files_and_database_requests_are_independent_and_keep_data_lifecycle_rules():
    value = definition()
    value["service"]["sdk_version"] = "1.3"
    value["storage"].update(
        relational=relational_request(mode="read"), private_files=file_request()
    )
    request = ApplicationExtensionV1.model_validate(value)
    assert request.storage.private_files.mode == "read_write"
    assert request.storage.relational.mode == "read"
    del value["storage"]["erasure_operation_id"]
    with pytest.raises(ValidationError, match="personal data requires"):
        ApplicationExtensionV1.model_validate(value)


@pytest.mark.parametrize("duplicate", ["mode", "relational", "storage"])
def test_raw_parser_refuses_duplicate_keys_including_hidden_opt_in(duplicate):
    value = definition()
    value["service"]["sdk_version"] = "1.3"
    value["storage"]["relational"] = relational_request()
    raw = json.dumps(value)
    if duplicate == "mode":
        raw = raw.replace(
            '"mode": "read_write"', '"mode": "read", "mode": "read_write"'
        )
    elif duplicate == "relational":
        raw = raw.replace('"relational":', '"relational": null, "relational":')
    else:
        legacy_storage = {
            key: item for key, item in value["storage"].items() if key != "relational"
        }
        raw = raw[:-1] + ', "storage": ' + json.dumps(legacy_storage) + "}"
    with pytest.raises(ValueError, match="duplicate JSON keys"):
        parse_application_extension(raw.encode("utf-8"))


@pytest.mark.parametrize(
    "constant", ["NaN", "Infinity", "-Infinity", "1e999", "-1e999"]
)
def test_raw_parser_refuses_non_json_numbers(constant):
    with pytest.raises(ValueError, match="non-finite"):
        parse_application_extension('{"extra": ' + constant + "}")


def test_schema_catalog_distinguishes_structural_support_from_blocked_runtime():
    entry = extension_schema_catalog()["contracts"]["application-extension.v1"]
    request = entry["schema"]["$defs"]["ApplicationRelationalStorageV1"]
    assert request["additionalProperties"] is False
    assert set(request["required"]) == set(relational_request())
    support = entry["declaration_support"]["storage.relational"]
    assert support["runtime_authority"] == "not_implemented"
    assert support["activation"] == "blocked" and support["sdk_version"] == "1.3"
