import pytest
from pydantic import ValidationError

from three_mm_protocol.automation import (
    AutomationCapabilityContextV1,
    AutomationDefinitionV1,
    CapabilityCommandAction,
    CapabilityContextEntry,
    CapabilityEventTrigger,
    validate_automation_capabilities,
)


DEVICE_ID = "dev_0123456789abcdef0123456789abcdef"


def context() -> AutomationCapabilityContextV1:
    return AutomationCapabilityContextV1(capabilities=(
        CapabilityContextEntry(
            device_id=DEVICE_ID,
            device_name="mock-pi",
            device_role="standalone",
            capability_id="gpio.digital.input",
            module_id="org.3mm.mock-gpio",
            module_version="1.0.0",
        ),
        CapabilityContextEntry(
            device_id=DEVICE_ID,
            device_name="mock-pi",
            device_role="standalone",
            capability_id="gpio.digital.control",
            module_id="org.3mm.mock-gpio",
            module_version="1.0.0",
        ),
    ))


def mock_gpio_automation() -> AutomationDefinitionV1:
    return AutomationDefinitionV1(
        name="Mirror input one to output one",
        trigger=CapabilityEventTrigger(
            device_id=DEVICE_ID,
            capability_id="gpio.digital.input",
            event="changed",
            conditions={"channel": "gpio.input.1", "value": True},
        ),
        actions=(CapabilityCommandAction(
            device_id=DEVICE_ID,
            capability_id="gpio.digital.control",
            action="set_output",
            arguments={"channel": "gpio.output.1", "value": True},
        ),),
    )


def test_mock_gpio_scenario_is_declarative_and_capability_valid():
    automation = mock_gpio_automation()
    assert automation.execution == "local"
    assert validate_automation_capabilities(automation, context()) == ()
    assert "python" not in automation.model_dump_json().lower()


def test_unknown_capability_is_rejected_before_apply():
    automation = mock_gpio_automation().model_copy(update={
        "actions": (mock_gpio_automation().actions[0].model_copy(
            update={"capability_id": "camera.capture"}
        ),)
    })
    issues = validate_automation_capabilities(automation, context())
    assert [(issue.path, issue.code) for issue in issues] == [
        ("actions.0", "capability.unavailable")
    ]


def test_local_automation_cannot_span_devices():
    with pytest.raises(ValidationError, match="exactly one device"):
        mock_gpio_automation().model_copy(update={
            "actions": (mock_gpio_automation().actions[0].model_copy(
                update={"device_id": "dev_other"}
            ),)
        }).model_validate(
            mock_gpio_automation().model_copy(update={
                "actions": (mock_gpio_automation().actions[0].model_copy(
                    update={"device_id": "dev_other"}
                ),)
            }).model_dump()
        )
