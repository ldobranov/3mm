import json

from backend.schemas.ai_extension_builder import ExtensionSpec
from backend.utils.ai_extension_builder import generator


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
