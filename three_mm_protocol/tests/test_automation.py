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
            metadata={
                "automation_role": "trigger",
                "automation_events": "changed,input.changed,gpio.input.changed",
                "automation_channels": "gpio.input.1",
                "automation_required_fields": "channel,value",
                "automation_value_type": "boolean",
            },
        ),
        CapabilityContextEntry(
            device_id=DEVICE_ID,
            device_name="mock-pi",
            device_role="standalone",
            capability_id="gpio.digital.control",
            module_id="org.3mm.mock-gpio",
            module_version="1.0.0",
            metadata={
                "automation_role": "action",
                "automation_actions": "set_output,pulse_output",
                "automation_channels": "gpio.output.1",
                "automation_required_fields_set_output": "channel,value",
                "automation_value_type_set_output": "boolean",
                "automation_required_fields_pulse_output": "channel,duration_ms",
            },
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


def test_declared_automation_contract_rejects_wrong_role_and_operation():
    candidate = mock_gpio_automation().model_copy(update={
        "trigger": mock_gpio_automation().trigger.model_copy(update={
            "capability_id": "gpio.digital.control",
            "event": "state_changed",
            "conditions": {},
        })
    })

    issues = validate_automation_capabilities(candidate, context())

    assert issues[0].path == "trigger"
    assert "cannot be used" in issues[0].message


def test_declared_automation_contract_rejects_string_boolean():
    candidate = mock_gpio_automation().model_copy(update={
        "trigger": mock_gpio_automation().trigger.model_copy(update={
            "conditions": {"channel": "gpio.input.1", "value": "true"},
        })
    })

    issues = validate_automation_capabilities(candidate, context())

    assert issues[0].path == "trigger"
    assert "Boolean value" in issues[0].message


def test_action_specific_contract_accepts_a_duration_based_pulse():
    candidate = mock_gpio_automation().model_copy(update={
        "actions": (mock_gpio_automation().actions[0].model_copy(update={
            "action": "pulse_output",
            "arguments": {"channel": "gpio.output.1", "duration_ms": 500},
        }),)
    })

    assert validate_automation_capabilities(candidate, context()) == ()


def test_action_specific_contract_requires_pulse_duration():
    candidate = mock_gpio_automation().model_copy(update={
        "actions": (mock_gpio_automation().actions[0].model_copy(update={
            "action": "pulse_output",
            "arguments": {"channel": "gpio.output.1"},
        }),)
    })

    issues = validate_automation_capabilities(candidate, context())

    assert "duration_ms" in issues[0].message


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
