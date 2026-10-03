import pytest
from pydantic import ValidationError

from three_mm_protocol.node_features import (
    DeviceRuntimeFeaturesReportV1,
    MANDATORY_NODE_FEATURES,
)


def report(**changes):
    return (
        dict(
            schema_version=1,
            device_id="dev_" + "1" * 32,
            runtime_name="reference",
            runtime_version="1",
            features=sorted(MANDATORY_NODE_FEATURES),
            command_types=["capability.invoke"],
            expected_revision=0,
        )
        | changes
    )


def test_runtime_features_roundtrip_and_future_generic_contracts():
    value = report(
        features=sorted(MANDATORY_NODE_FEATURES | {"future_transport", "ota"}),
        command_types=["capability.invoke", "future.command"],
    )
    parsed = DeviceRuntimeFeaturesReportV1.model_validate(value)
    assert parsed.model_dump(mode="json") == value | {"protocol_version": "1.0"}
    assert "agent.update.apply" not in parsed.command_types  # ota is not Linux OTA.


@pytest.mark.parametrize(
    "changes",
    [
        {"features": []},
        {"features": sorted(MANDATORY_NODE_FEATURES) + ["events"]},
        {"command_types": ["capability.invoke", "capability.invoke"]},
        {"command_types": []},
        {"command_types": ["capability.invoke", "module.install"]},
        {"features": sorted(MANDATORY_NODE_FEATURES | {"module_lifecycle"})},
        {"expected_revision": True},
        {"expected_revision": -1},
        {"schema_version": 2},
        {"protocol_version": "2.0"},
        {"capabilities": ["gpio.digital.control"]},
        {"features": sorted(MANDATORY_NODE_FEATURES) + ["a" * 101]},
        {"command_types": ["capability.invoke"] + [f"future.{i}" for i in range(64)]},
    ],
)
def test_invalid_or_inconsistent_advertisements(changes):
    with pytest.raises(ValidationError):
        DeviceRuntimeFeaturesReportV1.model_validate(report(**changes))
