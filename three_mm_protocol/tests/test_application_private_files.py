"""File declarations are bounded author requests, not live storage authority."""

import json

import pytest
from pydantic import ValidationError

from three_mm_application_sdk import ApplicationFileLimits
from three_mm_protocol import ApplicationExtensionV1, ApplicationPrivateFilesV1
from three_mm_protocol.extension_schemas import extension_schema_catalog
from three_mm_protocol.tests.test_application_extension import definition


def file_request(**changes):
    return {
        "file_contract_version": 1,
        "namespace": "private_files",
        "mode": "read_write",
        "max_file_bytes": 1024 * 1024,
        "max_total_bytes": 16 * 1024 * 1024,
        "max_files": 256,
        **changes,
    }


@pytest.mark.parametrize("mode", ["read", "read_write"])
def test_typed_request_roundtrips_without_host_paths_or_grants(mode):
    request = ApplicationPrivateFilesV1.model_validate(file_request(mode=mode))
    assert (
        ApplicationPrivateFilesV1.model_validate_json(request.model_dump_json())
        == request
    )
    limits = ApplicationFileLimits(
        request.max_file_bytes, request.max_total_bytes, request.max_files
    )
    assert limits == ApplicationFileLimits()
    assert set(request.model_dump()) == set(file_request())
    assert "approved" not in request.model_dump_json()


@pytest.mark.parametrize(
    "field",
    ["file_contract_version", "mode", "max_file_bytes", "max_total_bytes", "max_files"],
)
def test_omission_is_not_unlimited_authority(field):
    value = file_request()
    del value[field]
    with pytest.raises(ValidationError):
        ApplicationPrivateFilesV1.model_validate(value)


@pytest.mark.parametrize("version", [True, False, 1.0, "1", 0, 2, None])
def test_unknown_or_coerced_versions_are_refused(version):
    with pytest.raises(ValidationError):
        ApplicationPrivateFilesV1.model_validate(
            file_request(file_contract_version=version)
        )


@pytest.mark.parametrize(
    "field, ceiling",
    [
        ("max_file_bytes", 16 * 1024 * 1024),
        ("max_total_bytes", 64 * 1024 * 1024),
        ("max_files", 1024),
    ],
)
@pytest.mark.parametrize("bad", [True, False, 1.0, "1", -1, 0, None, "overflow"])
def test_limits_are_strict_positive_bounded_integers(field, ceiling, bad):
    value = ceiling + 1 if bad == "overflow" else bad
    with pytest.raises(ValidationError):
        ApplicationPrivateFilesV1.model_validate(file_request(**{field: value}))


def test_limits_match_sdk_ceiling_and_need_coherent_total():
    request = ApplicationPrivateFilesV1.model_validate(
        file_request(
            max_file_bytes=16 * 1024 * 1024,
            max_total_bytes=64 * 1024 * 1024,
            max_files=1024,
        )
    )
    assert ApplicationFileLimits(
        request.max_file_bytes, request.max_total_bytes, request.max_files
    )
    with pytest.raises(ValidationError, match="inconsistent"):
        ApplicationPrivateFilesV1.model_validate(file_request(max_total_bytes=1))


@pytest.mark.parametrize(
    "namespace", ["core", "foreign", "../files", "/var/lib/3mm", "sdk-files", "*", None]
)
def test_namespace_never_selects_host_or_foreign_storage(namespace):
    with pytest.raises(ValidationError):
        ApplicationPrivateFilesV1.model_validate(file_request(namespace=namespace))


@pytest.mark.parametrize(
    "extra",
    [
        "path",
        "data_dir",
        "owner",
        "grant",
        "approved",
        "unlimited",
        "schema_revision",
        "database_url",
        "execution_profile",
    ],
)
def test_author_cannot_supply_authority_paths_or_database_policy(extra):
    with pytest.raises(ValidationError, match="Extra inputs"):
        ApplicationPrivateFilesV1.model_validate(
            file_request(**{extra: "not-authority"})
        )


@pytest.mark.parametrize("mode", ["write", "admin", "*", True, None])
def test_mode_is_closed(mode):
    with pytest.raises(ValidationError):
        ApplicationPrivateFilesV1.model_validate(file_request(mode=mode))


@pytest.mark.parametrize("sdk_version", ["1.0", "1.1", "1.2", "1.3"])
def test_file_declaration_requires_sdk_13_without_changing_old_packages(sdk_version):
    old = definition()
    old["service"]["sdk_version"] = sdk_version
    assert ApplicationExtensionV1.model_validate(old).storage.private_files is None
    old["storage"]["private_files"] = file_request()
    if sdk_version != "1.3":
        with pytest.raises(ValidationError, match="require SDK 1.3"):
            ApplicationExtensionV1.model_validate(old)
    else:
        assert (
            ApplicationExtensionV1.model_validate(old).storage.private_files.mode
            == "read_write"
        )


def test_personal_file_data_keeps_existing_retention_export_and_erasure_rules():
    value = definition()
    value["service"]["sdk_version"] = "1.3"
    value["storage"]["private_files"] = file_request()
    for field in (
        "retention_operation_id",
        "export_operation_id",
        "erasure_operation_id",
    ):
        broken = json.loads(json.dumps(value))
        del broken["storage"][field]
        with pytest.raises(ValidationError, match="personal data requires"):
            ApplicationExtensionV1.model_validate(broken)
    value["storage"]["erasure_operation_id"] = "unknown"
    with pytest.raises(ValidationError, match="unknown operation"):
        ApplicationExtensionV1.model_validate(value)


def test_public_schema_exposes_bounded_local_runtime_without_automatic_grants():
    catalog = extension_schema_catalog()
    entry = catalog["contracts"]["application-extension.v1"]
    files = entry["schema"]["$defs"]["ApplicationPrivateFilesV1"]
    assert files["additionalProperties"] is False
    assert files["properties"]["max_files"]["maximum"] == 1024
    assert set(files["required"]) == {
        "file_contract_version",
        "mode",
        "max_file_bytes",
        "max_total_bytes",
        "max_files",
    }
    assert (
        entry["declaration_support"]["storage.private_files"]["runtime_authority"]
        == "reviewed_native_scoped_local"
    )
    from three_mm_application_sdk.file_wire import MAX_SCOPED_FILE_BYTES
    support = entry["declaration_support"]["storage.private_files"]
    assert support["authority_administration"] == "core_admin_review_api"
    assert support["native_trust_administration"] == "local_core_only"
    assert support["runtime_max_file_bytes"] == MAX_SCOPED_FILE_BYTES
    assert catalog["requires_authoritative_validation"] is True
