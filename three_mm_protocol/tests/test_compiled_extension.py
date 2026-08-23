import pytest
from pydantic import ValidationError

from three_mm_protocol import CompiledUiExtensionV1


def definition(**changes):
    value = {
        "compiled_ui_version": 1,
        "module_id": "org.3mm.clock",
        "version": "1.0.0",
        "entrypoints": [
            {
                "entrypoint_id": "clock",
                "kind": "widget",
                "source": "source/frontend/ClockWidget.vue",
                "label": {"en": "Clock"},
            },
            {
                "entrypoint_id": "clock_editor",
                "kind": "editor",
                "source": "source/frontend/ClockEditor.vue",
                "label": {"en": "Clock settings"},
                "target_entrypoint_id": "clock",
            },
        ],
    }
    value.update(changes)
    return value


def test_compiled_ui_contract_supports_widget_and_editor():
    compiled = CompiledUiExtensionV1.model_validate(definition())
    assert [item.kind for item in compiled.entrypoints] == ["widget", "editor"]


def test_compiled_ui_contract_accepts_a_versioned_capability_plan():
    value = definition(capability_plan={
        "schema_version": 1,
        "target": "dashboard_widget",
        "settings": [
            {"key": "deviceId", "label": "Device", "kind": "device", "required": True},
        ],
        "bindings": [{
            "alias": "inputState",
            "capability_id": "gpio.digital.input",
            "operation": "read_state",
            "device_setting": "deviceId",
        }],
        "presentations": [],
    })

    compiled = CompiledUiExtensionV1.model_validate(value)

    assert compiled.capability_plan is not None
    assert compiled.capability_plan.bindings[0].capability_id == "gpio.digital.input"


def test_route_entrypoint_requires_a_route():
    value = definition()
    value["entrypoints"] = [
        {
            "entrypoint_id": "clock_page",
            "kind": "route",
            "source": "source/frontend/ClockPage.vue",
            "label": {"en": "Clock"},
        }
    ]
    with pytest.raises(ValidationError, match="route entrypoints require route"):
        CompiledUiExtensionV1.model_validate(value)


def test_editor_must_target_a_widget():
    value = definition()
    value["entrypoints"][1]["target_entrypoint_id"] = "missing"
    with pytest.raises(ValidationError, match="must reference a widget"):
        CompiledUiExtensionV1.model_validate(value)


@pytest.mark.parametrize(
    "source",
    ["../Clock.vue", "backend/Clock.vue", "source/frontend/Clock.py"],
)
def test_compiled_source_must_be_a_safe_vue_file(source):
    value = definition()
    value["entrypoints"][0]["source"] = source
    with pytest.raises(ValidationError, match="safe .vue file"):
        CompiledUiExtensionV1.model_validate(value)
