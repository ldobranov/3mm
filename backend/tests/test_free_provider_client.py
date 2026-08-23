from backend.utils.ai_extension_builder.free_provider_client import FreeProviderFallbackClient


class StubClient:
    def __init__(self, *, configured=True, result=None, error=None):
        self.configured = configured
        self.result = result
        self.error = error
        self.calls = []

    def is_configured(self):
        return self.configured

    def chat_completions(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.error:
            raise self.error
        return self.result


def test_free_provider_prefers_groq():
    openrouter = StubClient(result={"unused": True})
    groq = StubClient(result={"choices": []})
    client = FreeProviderFallbackClient(openrouter, groq)

    assert client.chat_completions([{"role": "user", "content": "test"}]) == {"choices": []}
    assert client.last_provider == "groq"
    assert openrouter.calls == []
    assert len(groq.calls) == 1


def test_free_provider_falls_back_to_openrouter_with_model_override():
    openrouter = StubClient(result={"choices": [{"message": {"content": "{}"}}]})
    groq = StubClient(error=RuntimeError("rate limited"))
    client = FreeProviderFallbackClient(openrouter, groq)

    client.chat_completions([], model="openrouter/free")

    assert client.last_provider == "openrouter"
    assert len(openrouter.calls) == 1
    assert len(groq.calls) == 1
    assert groq.calls[0][1]["model"] is None
    assert openrouter.calls[0][1]["model"] == "openrouter/free"


def test_free_provider_uses_configured_groq_when_openrouter_is_missing():
    openrouter = StubClient(configured=False)
    groq = StubClient(result={"ok": True})
    client = FreeProviderFallbackClient(openrouter, groq)

    assert client.is_configured()
    assert client.chat_completions([]) == {"ok": True}
    assert openrouter.calls == []
    assert client.last_provider == "groq"
