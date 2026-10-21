import copy
import json

import pytest

from three_mm_protocol.application_extension import ApplicationExtensionV1
from three_mm_protocol.application_sessions import (
    ApplicationSessionBindingV1,
    ApplicationSessionProviderV1,
    session_contract,
)
from three_mm_protocol.tests.test_application_extension import definition


def binding(**changes):
    return {
        "contract_version": 1,
        "binding_id": "console",
        "target_device_config_key": "TARGET_DEVICE_ID",
        "provider_id": "org.example.console",
        "capability_id": "org.example.session",
        "access_mode": "write",
        "control_actions": ["resize"],
        "required_permission": "session_use",
        **changes,
    }


def test_session_declaration_is_an_explicit_bounded_request():
    value = ApplicationSessionBindingV1.model_validate(binding())
    assert value.options == {} and value.control_actions == ("resize",)
    assert value.contract_version == 1


def test_session_references_need_new_sdk_and_known_human_permission():
    value = definition()
    value["service"]["sdk_version"] = "1.3"
    value["session_bindings"] = [binding(required_permission="records_manage")]
    assert ApplicationExtensionV1.model_validate(value).session_bindings
    for change in ("sdk", "permission", "duplicate"):
        changed = copy.deepcopy(value)
        if change == "sdk":
            changed["service"]["sdk_version"] = "1.2"
        elif change == "permission":
            changed["session_bindings"][0]["required_permission"] = "unknown"
        else:
            changed["session_bindings"].append(changed["session_bindings"][0])
        with pytest.raises(ValueError):
            ApplicationExtensionV1.model_validate(changed)


@pytest.mark.parametrize(
    "changes",
    [
        {"contract_version": True},
        {"contract_version": "1"},
        {"contract_version": 2},
        {"binding_id": "*"},
        {"target_device_config_key": "/dev/pts/0"},
        {"access_mode": "root"},
        {"control_actions": ["resize", "resize"]},
        {"control_actions": ["../shell"]},
        {"control_actions": ["x"] * 17},
        {"required_permission": "*"},
        {"owner": "caller"},
        {"options": {"x": "x" * 9000}},
    ],
)
def test_bad_or_widened_declarations_are_refused(changes):
    with pytest.raises(ValueError):
        ApplicationSessionBindingV1.model_validate(binding(**changes))


def test_provider_metadata_requires_an_exact_versioned_session_contract():
    contract = {
        "contract_version": 1,
        "access_modes": ["read", "write"],
        "control_actions": ["resize"],
    }
    assert (
        session_contract(
            {"interactive_session_contract": json.dumps(contract)}
        ).contract_version
        == 1
    )
    for value in (
        None,
        {},
        True,
        "{}",
        json.dumps({**contract, "contract_version": True}),
        json.dumps({**contract, "isolation_proven": True}),
        '{"contract_version":1,"contract_version":1,"access_modes":["read"],"control_actions":[]}',
        "x" * 513,
    ):
        with pytest.raises((ValueError, TypeError)):
            session_contract({"interactive_session_contract": value})


def test_provider_factory_is_additive_bounded_and_requires_new_sdk():
    provider = {
        "capability_id": "example.console",
        "factory": "example.runtime:create_provider",
        "resource_profile": "isolated_session_v1",
        "contract": {
            "contract_version": 1,
            "access_modes": ["write"],
            "control_actions": ["resize"],
        },
    }
    assert ApplicationSessionProviderV1.model_validate(
        provider
    ).contract.access_modes == ("write",)
    value = definition()
    value["service"]["sdk_version"] = "1.3"
    value["session_providers"] = [provider]
    assert ApplicationExtensionV1.model_validate(value).session_providers
    for changes in (
        {"factory": "/bin/sh"},
        {"resource_profile": "unrestricted"},
        {"uid": 0},
        {"contract": {**provider["contract"], "contract_version": True}},
    ):
        with pytest.raises(ValueError):
            ApplicationSessionProviderV1.model_validate({**provider, **changes})
    value["service"]["sdk_version"] = "1.2"
    with pytest.raises(ValueError):
        ApplicationExtensionV1.model_validate(value)
