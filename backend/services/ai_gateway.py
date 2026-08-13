"""Provider-independent AI completion boundary with no secret persistence."""

from dataclasses import dataclass
from typing import Protocol

from backend.utils.ai_extension_builder.groq_client import GroqClient
from backend.utils.ai_extension_builder.openrouter_client import OpenRouterClient


@dataclass(frozen=True)
class AiCompletion:
    content: str
    input_tokens: int
    output_tokens: int
    provider_request_id: str | None = None


class AiProviderGateway(Protocol):
    def complete(self, *, provider: str, model: str, messages: list[dict[str, str]], max_tokens: int, api_key: str | None) -> AiCompletion: ...


class OpenAiCompatibleGateway:
    def complete(self, *, provider: str, model: str, messages: list[dict[str, str]], max_tokens: int, api_key: str | None) -> AiCompletion:
        if provider == "groq":
            raw = GroqClient(api_key=api_key).chat_completions(messages, model=model, max_tokens=max_tokens, response_format={"type": "json_object"})
        elif provider == "openrouter":
            raw = OpenRouterClient(api_key=api_key).chat_completions(messages, model=model, max_tokens=max_tokens, response_format={"type": "json_object"})
        else:
            raise ValueError("Unsupported AI provider")
        usage = raw.get("usage") or {}
        choices = raw.get("choices") or []
        if not choices or not isinstance(choices[0].get("message", {}).get("content"), str):
            raise ValueError("AI provider returned no completion")
        return AiCompletion(
            content=choices[0]["message"]["content"],
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            provider_request_id=raw.get("id"),
        )


def get_ai_gateway() -> AiProviderGateway:
    return OpenAiCompatibleGateway()
