import pytest

from backend.services.application_configuration import (
    ApplicationConfigurationError,
    device_configuration_keys,
    resolve_application_configuration,
)
from backend.tests.test_module_packages import application_definition
from three_mm_protocol import ApplicationExtensionV1


DEVICE_ID = "dev_0123456789abcdef0123456789abcdef"


def definition() -> ApplicationExtensionV1:
    return ApplicationExtensionV1.model_validate(application_definition())


def schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "READER_DEVICE_ID": {
                "type": "string",
                "pattern": r"^dev_[0-9a-f]{32}$",
            },
            "BUSINESS_API_URL": {"type": "string"},
            "BUSINESS_API_CREDENTIAL": {"type": "string"},
        },
    }


def test_device_binding_is_derived_from_application_contract():
    assert device_configuration_keys(definition()) == ("READER_DEVICE_ID",)


def test_saved_device_binding_is_preserved_and_can_be_overridden():
    resolved = resolve_application_configuration(
        schema(),
        {"BUSINESS_API_URL": "https://example.test"},
        definition(),
        existing={"READER_DEVICE_ID": DEVICE_ID},
    )
    assert resolved["READER_DEVICE_ID"] == DEVICE_ID

    replacement = "dev_fedcba9876543210fedcba9876543210"
    resolved = resolve_application_configuration(
        schema(),
        {},
        definition(),
        existing={"READER_DEVICE_ID": DEVICE_ID},
        overrides={"READER_DEVICE_ID": replacement},
    )
    assert resolved["READER_DEVICE_ID"] == replacement


def test_missing_or_invalid_device_binding_is_rejected():
    with pytest.raises(ApplicationConfigurationError, match="required"):
        resolve_application_configuration(schema(), {}, definition())
    with pytest.raises(ApplicationConfigurationError, match="invalid format"):
        resolve_application_configuration(
            schema(),
            {},
            definition(),
            overrides={"READER_DEVICE_ID": "not-a-device"},
        )
