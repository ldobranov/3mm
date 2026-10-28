import pytest

from backend.services.application_configuration import (
    ApplicationConfigurationError,
    device_configuration_keys,
    resolve_application_configuration,
    resolve_device_selection,
    require_available_device_bindings,
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


def optional_readers():
    value=application_definition()
    value['service']['sdk_version']='1.3'
    primary=value['event_subscriptions'][0]
    value['event_subscriptions'].append({**primary,'subscription_id':'secondary_scan','device_scope_config_key':'SECONDARY_DEVICE_ID'})
    value['optional_resources']=['event:identifier_scans','event:secondary_scan']
    return ApplicationExtensionV1.model_validate(value)


def reader_schema():
    from backend.tests.test_module_packages import application_manifest
    value=application_manifest()['configuration_schema']
    value['properties']['SECONDARY_DEVICE_ID']=value['properties']['READER_DEVICE_ID']
    return value


@pytest.mark.parametrize('selection',[{}, {'READER_DEVICE_ID':DEVICE_ID}, {'READER_DEVICE_ID':DEVICE_ID,'SECONDARY_DEVICE_ID':DEVICE_ID}])
def test_optional_selection_allows_none_or_either_number_of_available_devices(selection):
    resolved=resolve_device_selection(reader_schema(),{},optional_readers(),selection=selection)
    assert resolved==selection
    require_available_device_bindings(optional_readers(),resolved,{DEVICE_ID})


def test_explicit_optional_omission_clears_defaults_and_previous_selection_only():
    saved={'READER_DEVICE_ID':DEVICE_ID,'BUSINESS_API_URL':'https://example.test'}
    assert resolve_device_selection(reader_schema(),saved,optional_readers(),existing=saved,selection={})=={'BUSINESS_API_URL':'https://example.test'}
    assert resolve_device_selection(reader_schema(),{},optional_readers(),existing=saved)==saved
    assert resolve_device_selection(schema(),{},definition(),existing=saved,selection={})==saved
    cleared=resolve_device_selection(reader_schema(),saved,optional_readers(),existing=saved,selection={})
    assert resolve_application_configuration(reader_schema(),saved,optional_readers(),existing=cleared)==cleared


def test_optional_supplied_unknown_or_revoked_devices_and_required_omission_are_denied():
    with pytest.raises(ApplicationConfigurationError,match='SECONDARY_DEVICE_ID'):
        require_available_device_bindings(optional_readers(),{'SECONDARY_DEVICE_ID':DEVICE_ID},set())
    with pytest.raises(ApplicationConfigurationError,match='READER_DEVICE_ID'):
        require_available_device_bindings(definition(),{},set())
    with pytest.raises(ApplicationConfigurationError,match='declared'):
        resolve_device_selection(reader_schema(),{},optional_readers(),selection={'undeclared':DEVICE_ID})
