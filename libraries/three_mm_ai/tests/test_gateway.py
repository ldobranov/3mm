from types import SimpleNamespace
import pytest
from three_mm_ai import gateway
from three_mm_ai.groq_client import GroqClient
from three_mm_ai.openrouter_client import OpenRouterClient


@pytest.mark.parametrize("client_type", [GroqClient, OpenRouterClient])
def test_clients_keep_request_contract_without_network_or_core(client_type, monkeypatch):
    calls = []
    response = {"choices": [{"message": {"content": "{}"}}]}
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: response)
    monkeypatch.setattr("requests.post", post)
    client = client_type(api_key="local-test-key", base_url="https://provider.invalid/v1", timeout_seconds=2)
    assert client.chat_completions([{"role": "user", "content": "test"}], model="chosen-model") == response
    assert len(calls) == 1
    url, options = calls[0]
    assert url == "https://provider.invalid/v1/chat/completions"
    assert options["json"]["model"] == "chosen-model" and options["timeout"] == 2
    assert options["headers"]["Authorization"] == "Bearer local-test-key"


def test_gateway_preserves_content_and_usage_boundary(monkeypatch):
    class Client:
        def __init__(self, api_key): assert api_key == "test-key"
        def chat_completions(self, *args, **kwargs):
            return {"choices": [{"message": {"content": "{}"}}], "usage": {"prompt_tokens": 12, "completion_tokens": 3}, "id": "original"}
    monkeypatch.setattr(gateway, "GroqClient", Client)
    result = gateway.get_ai_gateway().complete(provider="groq", model="chosen", messages=[], max_tokens=10, api_key="test-key")
    assert (result.content, result.input_tokens, result.output_tokens, result.provider_request_id) == ("{}", 12, 3, "original")
