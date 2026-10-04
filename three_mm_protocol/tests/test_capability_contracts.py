from copy import deepcopy

import pytest
from pydantic import ValidationError

from examples.mock_embedded.contracts import control_contract
from three_mm_protocol.capability_contracts import (
    CapabilityContractV1,
    CapabilityContractError,
)
from three_mm_protocol import CapabilityAdvertisementV1, ModuleRegistration
from three_mm_protocol.application_commands import ApplicationCommandBindingV1


def test_exact_contract_and_legacy_serialization():
    contract = control_contract()
    request = {
        "capability_id": contract.capability_id,
        "contract_version": "1.0",
        "contract_digest": contract.digest(),
        "action": "set_output",
        "arguments": {"channel": "gpio.output.1", "value": True},
    }
    assert contract.invocation(request, require_digest=True)
    assert (
        "contract"
        not in CapabilityAdvertisementV1(
            capability_id=contract.capability_id
        ).model_dump()
    )
    assert (
        "contract"
        not in ModuleRegistration(
            kind="capability", registration_id=contract.capability_id
        ).model_dump()
    )
    binding = ApplicationCommandBindingV1(
        binding_id="output",
        target_device_config_key="OUTPUT_DEVICE_ID",
        capability_id=contract.capability_id,
        action="set_output",
        arguments_schema=contract.actions["set_output"].arguments_schema,
    )
    assert "contract_version" not in binding.model_dump()
    # Metadata and provider release versions never fabricate a capability version.
    advertised = CapabilityAdvertisementV1(
        capability_id=contract.capability_id, contract=contract
    )
    assert advertised.model_dump()["contract"]["contract_version"] == "1.0"


@pytest.mark.parametrize(
    "change",
    [
        {"contract_version": "2.0"},
        {"contract_digest": "0" * 64},
        {"action": "erase"},
        {"action": {}},
        {"arguments": {"channel": "gpio.output.1", "value": 1}},
        {"arguments": {"channel": "gpio.output.2", "value": True}},
        {"arguments": {"channel": "gpio.output.1", "value": True, "extra": True}},
    ],
)
def test_invalid_invocation_never_matches(change):
    contract = control_contract()
    payload = {
        "capability_id": contract.capability_id,
        "contract_version": "1.0",
        "contract_digest": contract.digest(),
        "action": "set_output",
        "arguments": {"channel": "gpio.output.1", "value": True},
    }
    with pytest.raises(CapabilityContractError):
        contract.invocation(payload | change, require_digest=True)


@pytest.mark.parametrize(
    "change",
    ["ref", "range", "unbounded", "extra", "bool_bound", "wrong_identity", "oversized"],
)
def test_unsupported_or_unbounded_contract_rejected(change):
    data = deepcopy(control_contract().model_dump())
    schema = data["actions"]["set_output"]["arguments_schema"]
    if change == "ref":
        schema["$ref"] = "https://invalid.test/schema"
    if change == "range":
        data["contract_version"] = ">=1.0"
    if change == "unbounded":
        schema["properties"]["channel"].pop("maxLength")
    if change == "extra":
        schema["additionalProperties"] = True
    if change == "bool_bound":
        schema["properties"]["channel"]["maxLength"] = True
    if change == "oversized":
        data["actions"]["x" * 161] = data["actions"]["set_output"]
    if change == "wrong_identity":
        with pytest.raises(ValidationError):
            CapabilityAdvertisementV1(capability_id="other.capability", contract=data)
        return
    with pytest.raises((ValidationError, CapabilityContractError)):
        CapabilityContractV1.model_validate(data)
