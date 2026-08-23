import json

from backend.schemas.ai_extension_builder import ExtensionSpec
from backend.utils.ai_extension_builder import generator
from three_mm_protocol import (
    BuilderSettingV1,
    CapabilityBindingV1,
    CapabilityPlanV1,
    CapabilityPresentationV1,
    PresentationStateV1,
)


class _RetryingOpenRouter:
    calls = []
    default_model = "openrouter/free"

    def __init__(self, api_key=None):
        self.api_key = api_key

    def is_configured(self):
        return True

    def chat_completions(self, **kwargs):
        self.calls.append(kwargs.get("response_format"))
        if len(self.calls) == 1:
            return {"choices": [{"message": {"content": "not valid json"}}]}
        payload = {
            "files": {
                "source/frontend/Widget.vue": (
                    "<template><time>{{ currentTime }}</time></template>"
                    "<script setup lang=\"ts\">const currentTime = '12:34:56'</script>"
                )
            }
        }
        return {"choices": [{"message": {"content": json.dumps(payload)}}]}


class _UnconfiguredGroq:
    default_model = "llama-3.1-8b-instant"

    def __init__(self, api_key=None):
        self.api_key = api_key

    def is_configured(self):
        return False


class _NoOpOpenRouter(_RetryingOpenRouter):
    calls = []

    def chat_completions(self, **kwargs):
        return {"choices": [{"message": {"content": json.dumps({"files": {}})}}]}


def test_invalid_json_response_is_retried_without_json_mode(monkeypatch):
    _RetryingOpenRouter.calls = []
    monkeypatch.setattr(generator, "OpenRouterClient", _RetryingOpenRouter)
    monkeypatch.setattr(generator, "GroqClient", _UnconfiguredGroq)

    spec = ExtensionSpec(
        name="ClockWidget",
        version="1.0.0",
        type="widget",
        description="Digital clock",
        api_prefix="/api/clock",
        backend_entry="clock.py",
        frontend_entry="ClockWidget.vue",
        frontend_routes=[],
        goal="Create a digital clock",
    )

    report, _, files = generator.build_extension_zip(
        spec,
        instructions=spec.goal,
        use_ai=True,
        openrouter_api_key="configured-for-test",
    )

    assert _RetryingOpenRouter.calls == [{"type": "json_object"}, None]
    assert "currentTime" in files["source/frontend/Widget.vue"]
    assert "source/frontend/WidgetEditor.vue" in files
    manifest = json.loads(files["manifest.json"])
    assert manifest["entrypoints"] == {"ui": "compiled-ui.json"}
    assert "ai.bad_response.retry" in {warning.code for warning in report.warnings}
    assert "ai.updated_files" in {warning.code for warning in report.warnings}


def test_compiled_widget_rejects_unchanged_generic_scaffold(monkeypatch):
    monkeypatch.setattr(generator, "OpenRouterClient", _NoOpOpenRouter)
    monkeypatch.setattr(generator, "GroqClient", _UnconfiguredGroq)
    spec = ExtensionSpec(
        name="LiveWidget", version="1.0.0", type="widget",
        description="Live changing widget", api_prefix="/api/live",
        backend_entry="live.py", frontend_entry="LiveWidget.vue",
        goal="Show a value that changes every second",
    )

    import pytest
    with pytest.raises(generator.IncompleteAIGenerationError):
        generator.build_extension_zip(
            spec, instructions=spec.goal, use_ai=True,
            ai_provider="openrouter", openrouter_api_key="configured-for-test",
        )


def test_timezone_schema_produces_a_working_live_widget_without_ai():
    spec = ExtensionSpec(
        name="TemporalDisplay", version="1.0.0", type="widget",
        description="Live time display", api_prefix="/api/temporal",
        backend_entry="temporal.py", frontend_entry="TemporalDisplay.vue",
        config_schema={"type": "object", "properties": {
            "timezone": {"type": "string", "format": "timezone", "default": "UTC"},
            "displayMode": {"type": "string", "enum": ["digital", "analog"], "default": "digital"},
            "hourFormat": {"type": "string", "enum": ["24", "12"], "default": "24"},
        }},
    )

    _, _, files = generator.build_extension_zip(spec, use_ai=False)
    widget = files["source/frontend/Widget.vue"]
    assert "setInterval" in widget
    assert "Intl.DateTimeFormat" in widget
    assert "clock-face" in widget


def test_legacy_clock_settings_are_migrated_to_typed_widget_controls():
    spec = ExtensionSpec(
        name="ExistingWidget", version="1.0.0", type="widget",
        description="Digital and analog display with timezone and am/pm",
        api_prefix="/api/existing", backend_entry="existing.py",
        frontend_entry="ExistingWidget.vue",
        config_schema={"type": "object", "properties": {
            "mode": {"type": "boolean"}, "ampm": {"type": "boolean"},
            "timezone": {"type": "string"},
        }},
    )

    _, _, files = generator.build_extension_zip(spec, use_ai=False)
    manifest = json.loads(files["manifest.json"])
    properties = manifest["configuration_schema"]["properties"]
    assert properties["displayMode"]["enum"] == ["digital", "analog"]
    assert properties["hourFormat"]["enum"] == ["24", "12"]
    assert properties["timezone"]["format"] == "timezone"
    assert manifest["configuration_defaults"] == {
        "displayMode": "digital", "hourFormat": "24", "timezone": "UTC",
    }
    assert "setInterval" in files["source/frontend/Widget.vue"]


def test_capability_plan_produces_a_deterministic_gpio_indicator():
    plan = CapabilityPlanV1(
        target="dashboard_widget",
        settings=(
            BuilderSettingV1(key="deviceId", label="Device", kind="device", required=True),
            BuilderSettingV1(key="channel", label="Input pin", kind="capability_channel", required=True),
            BuilderSettingV1(key="activeHigh", label="Active high", kind="boolean", default=True),
        ),
        bindings=(CapabilityBindingV1(
            alias="inputState", capability_id="gpio.digital.input", operation="subscribe",
            device_setting="deviceId", channel_setting="channel", permissions=("hardware.gpio",),
        ),),
        presentations=(CapabilityPresentationV1(
            kind="indicator", source_binding="inputState", states=(
                PresentationStateV1(value=True, label="Active", color="#22C55E"),
                PresentationStateV1(value=False, label="Inactive", color="#EF4444"),
                PresentationStateV1(state="stale", label="Stale", color="#F59E0B"),
                PresentationStateV1(state="offline", label="Offline", color="#6B7280"),
                PresentationStateV1(state="error", label="Error", color="#DC2626"),
            ),
        ),),
    )
    spec = ExtensionSpec(
        name="InputLamp", version="1.0.0", type="widget",
        description="GPIO input lamp", api_prefix="/api/input-lamp",
        backend_entry="input_lamp.py", frontend_entry="InputLamp.vue",
        capability_plan=plan,
    )

    report, _, files = generator.build_extension_zip(
        spec, use_ai=True, instructions=spec.description,
    )

    manifest = json.loads(files["manifest.json"])
    contract = json.loads(files["compiled-ui.json"])
    widget = files["source/frontend/Widget.vue"]
    assert manifest["capabilities"]["consumes"] == ["gpio.digital.input"]
    assert manifest["permissions"] == ["hardware.gpio"]
    assert manifest["configuration_schema"]["properties"]["deviceId"]["format"] == "device"
    assert contract["capability_plan"]["bindings"][0]["alias"] == "inputState"
    runtime = files["source/frontend/capability-runtime.ts"]
    assert "useCapabilityFeed" in runtime
    assert "'/runtime-config.json'" in runtime
    assert "window.location.hostname" in runtime
    assert "async function apiFetch" in runtime
    assert "_publicCapabilityStateUrl" in runtime
    assert "/capabilities/${encodeURIComponent(capabilityDescriptor.capabilityId)}/state" in runtime
    assert "/events" in runtime and "setInterval(refresh, 3000)" in runtime
    assert "./capability-runtime" in widget
    assert "template.functional" in {warning.code for warning in report.warnings}


def test_compiled_capability_rebuild_preserves_source_and_syncs_contract_version():
    plan = CapabilityPlanV1(
        target="dashboard_widget",
        settings=(BuilderSettingV1(key="deviceId", label="Device", kind="device"),),
        bindings=(CapabilityBindingV1(
            alias="state", capability_id="sensor.temperature", operation="read_state",
            device_setting="deviceId", permissions=("data.read",),
        ),),
        presentations=(CapabilityPresentationV1(kind="metric", source_binding="state"),),
    )
    first = ExtensionSpec(
        name="Temperature", version="1.0.0", type="widget", description="Temperature",
        api_prefix="/api/temperature", backend_entry="temperature.py",
        frontend_entry="Temperature.vue", capability_plan=plan,
    )
    _, _, files = generator.build_extension_zip(first, use_ai=False)
    files["source/frontend/Widget.vue"] += "\n<!-- preserved edit -->\n"
    next_spec = first.model_copy(update={"version": "1.0.1"})

    _, _, rebuilt = generator.package_extension_zip(next_spec, files)

    assert "preserved edit" in rebuilt["source/frontend/Widget.vue"]
    assert json.loads(rebuilt["manifest.json"])["version"] == "1.0.1"
    assert json.loads(rebuilt["compiled-ui.json"])["version"] == "1.0.1"
    assert json.loads(rebuilt["manifest.json"])["capabilities"]["consumes"] == ["sensor.temperature"]
