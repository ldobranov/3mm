from backend.schemas.ai_extension_builder import ExtensionSpec
from backend.utils.ai_extension_builder.widget_spec import (
    compiled_module_id,
    normalize_widget_spec,
)
from three_mm_protocol import BuilderSettingV1, CapabilityPlanV1


def widget_spec(**updates) -> ExtensionSpec:
    values = {
        "name": "Test Widget",
        "version": "1.0.0",
        "type": "widget",
        "description": "A test widget",
        "api_prefix": "/api/test",
        "backend_entry": "test.py",
        "frontend_entry": "TestWidget.vue",
    }
    values.update(updates)
    return ExtensionSpec(**values)


def test_compiled_module_id_is_stable_and_namespaced():
    assert compiled_module_id("GPIO Status Widget") == "org.3mm.generated.gpio-status-widget"
    assert compiled_module_id("---") == "org.3mm.generated.widget"


def test_normalization_upgrades_legacy_clock_fields_without_mutating_draft():
    draft = widget_spec(
        description="Digital or analog clock with timezone and 12/24 hour mode",
        config_schema={"type": "object", "properties": {
            "mode": {"type": "boolean"},
            "ampm": {"type": "boolean"},
            "timezoneText": {"type": "string"},
        }},
    )

    normalized = normalize_widget_spec(draft)
    properties = normalized.config_schema["properties"]

    assert set(properties) == {"timezone", "displayMode", "hourFormat"}
    assert properties["timezone"]["format"] == "timezone"
    assert properties["displayMode"]["enum"] == ["digital", "analog"]
    assert properties["hourFormat"]["enum"] == ["24", "12"]
    assert "mode" in draft.config_schema["properties"]


def test_normalization_maps_capability_settings_to_typed_ui_fields():
    draft = widget_spec(capability_plan=CapabilityPlanV1(
        target="dashboard_widget",
        settings=(
            BuilderSettingV1(key="deviceId", label="Device", kind="device"),
            BuilderSettingV1(key="channel", label="Input", kind="capability_channel"),
            BuilderSettingV1(
                key="unit", label="Unit", kind="select", options=("C", "F"),
            ),
        ),
    ))

    properties = normalize_widget_spec(draft).config_schema["properties"]

    assert properties["deviceId"]["format"] == "device"
    assert properties["channel"] == {
        "type": "string",
        "format": "capability-channel",
        "title": "Input",
    }
    assert properties["unit"]["enum"] == ["C", "F"]
