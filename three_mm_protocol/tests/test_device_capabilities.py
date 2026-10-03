import pytest
from pydantic import ValidationError

from three_mm_protocol import CapabilityProviderReportV1


def report(**changes):
    return {
        "schema_version": 1,
        "device_id": "dev_" + "1" * 32,
        "provider_type": "embedded_firmware",
        "provider_id": "org.example.runtime",
        "provider_version": "0.1",
        "expected_revision": 0,
        "capabilities": [
            {"capability_id": "gpio.digital.control", "metadata": {"active": True}}
        ],
        **changes,
    }


@pytest.mark.parametrize(
    "provider_type", ["native", "embedded_firmware", "gateway", "future.adapter"]
)
def test_generic_provider_contract_needs_no_linux_or_module_fields(provider_type):
    parsed = CapabilityProviderReportV1.model_validate(
        report(provider_type=provider_type)
    )
    assert parsed.capabilities[0].metadata["active"] is True
    assert parsed.protocol_version == "1.0"


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"protocol_version": "2.0"},
        {"device_id": "unknown"},
        {"provider_type": "agent_module"},
        {"provider_id": "../module"},
        {"expected_revision": -1},
        {"expected_revision": True},
        {"enabled": True},
        {"capabilities": [{"capability_id": "gpio"}] * 2},
        {"capabilities": [{"capability_id": f"cap.{i}"} for i in range(65)]},
        {
            "capabilities": [
                {"capability_id": "gpio", "metadata": {"nested": {"value": True}}}
            ]
        },
        {
            "capabilities": [
                {"capability_id": "gpio", "metadata": {"bad": float("nan")}}
            ]
        },
        {"capabilities": [{"capability_id": "gpio", "metadata": {"long": "x" * 513}}]},
        {
            "capabilities": [
                {"capability_id": "gpio", "metadata": {str(i): 1 for i in range(33)}}
            ]
        },
        {
            "capabilities": [
                {
                    "capability_id": f"cap.{i}",
                    "metadata": {str(j): "x" * 400 for j in range(16)},
                }
                for i in range(12)
            ]
        },
    ],
)
def test_declarations_reject_spoofing_invalid_revisions_and_unbounded_metadata(changes):
    with pytest.raises(ValidationError):
        CapabilityProviderReportV1.model_validate(report(**changes))


def test_explicit_schema_and_empty_withdrawal():
    value = report(capabilities=[])
    assert CapabilityProviderReportV1.model_validate(value).capabilities == ()
    del value["schema_version"]
    with pytest.raises(ValidationError):
        CapabilityProviderReportV1.model_validate(value)
