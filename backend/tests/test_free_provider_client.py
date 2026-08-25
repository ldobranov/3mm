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
    result = {"choices": [{"message": {"content": "{}"}}]}
    groq = StubClient(result=result)
    client = FreeProviderFallbackClient(openrouter, groq)

    assert client.chat_completions([{"role": "user", "content": "test"}]) == result
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
    result = {"choices": [{"message": {"content": "{}"}}]}
    groq = StubClient(result=result)
    client = FreeProviderFallbackClient(openrouter, groq)

    assert client.is_configured()
    assert client.chat_completions([]) == result
    assert openrouter.calls == []
    assert client.last_provider == "groq"


def test_free_provider_falls_back_when_groq_returns_null_content():
    openrouter_result = {"choices": [{"message": {"content": '{"files": {}}'}}]}
    openrouter = StubClient(result=openrouter_result)
    groq = StubClient(result={"choices": [{"message": {"content": None}}]})
    client = FreeProviderFallbackClient(openrouter, groq)

    assert client.chat_completions([]) == openrouter_result
    assert len(groq.calls) == 1
    assert len(openrouter.calls) == 1
    assert client.last_provider == "openrouter"


def test_free_provider_falls_back_when_content_fails_caller_validation():
    openrouter_result = {"choices": [{"message": {"content": '{"files": {}}'}}]}
    openrouter = StubClient(result=openrouter_result)
    groq = StubClient(result={"choices": [{"message": {"content": "plain explanation"}}]})
    client = FreeProviderFallbackClient(openrouter, groq)

    result = client.chat_completions(
        [], response_validator=lambda response: '"files"' in response["choices"][0]["message"]["content"]
    )

    assert result == openrouter_result
    assert len(groq.calls) == 1
    assert len(openrouter.calls) == 1
    assert client.last_provider == "openrouter"


def test_free_provider_accepts_text_content_parts():
    result = {"choices": [{"message": {"content": [{"type": "text", "text": "{}"}]}}]}
    client = FreeProviderFallbackClient(StubClient(configured=False), StubClient(result=result))

    assert client.chat_completions([]) == result
