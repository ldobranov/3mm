import pytest
from pydantic import ValidationError

from three_mm_protocol import (
    BuilderSettingV1,
    CapabilityBindingV1,
    CapabilityPlanV1,
    CapabilityPresentationV1,
    PresentationStateV1,
)


def gpio_indicator_plan() -> CapabilityPlanV1:
    return CapabilityPlanV1(
        target="dashboard_widget",
        settings=(
            BuilderSettingV1(key="deviceId", label="Device", kind="device", required=True),
            BuilderSettingV1(key="pin", label="Pin", kind="capability_channel", required=True),
        ),
        bindings=(CapabilityBindingV1(
            alias="inputState", capability_id="gpio.digital.input", operation="subscribe",
            device_setting="deviceId", channel_setting="pin", permissions=("hardware.gpio",),
        ),),
        presentations=(CapabilityPresentationV1(
            kind="indicator", source_binding="inputState", states=(
                PresentationStateV1(value=True, label="On", color="#22C55E"),
                PresentationStateV1(value=False, label="Off", color="#EF4444"),
                PresentationStateV1(state="stale", label="Stale", color="#F59E0B"),
                PresentationStateV1(state="offline", label="Offline", color="#6B7280"),
                PresentationStateV1(state="error", label="Error", color="#DC2626"),
            ),
        ),),
    )


def test_gpio_plan_is_strict_and_serializable():
    plan = gpio_indicator_plan()
    assert plan.bindings[0].capability_id == "gpio.digital.input"
    assert "hardware.gpio" in plan.bindings[0].permissions
    assert CapabilityPlanV1.model_validate_json(plan.model_dump_json()) == plan


def test_binding_cannot_reference_an_undeclared_channel_setting():
    data = gpio_indicator_plan().model_dump()
    data["bindings"][0]["channel_setting"] = "missingPin"
    with pytest.raises(ValidationError, match="capability-channel setting"):
        CapabilityPlanV1.model_validate(data)


def test_indicator_requires_explicit_failure_states():
    data = gpio_indicator_plan().model_dump()
    data["presentations"][0]["states"] = data["presentations"][0]["states"][:2]
    with pytest.raises(ValidationError, match="stale, offline and error"):
        CapabilityPlanV1.model_validate(data)


def test_invoke_binding_requires_an_explicit_action():
    with pytest.raises(ValidationError, match="require an action"):
        CapabilityBindingV1(
            alias="command", capability_id="gpio.digital.control", operation="invoke",
            device_setting="deviceId",
        )

    binding = CapabilityBindingV1(
        alias="command", capability_id="gpio.digital.control", operation="invoke",
        action="set_output", device_setting="deviceId",
    )
    assert binding.action == "set_output"
