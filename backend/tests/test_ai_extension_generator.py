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
