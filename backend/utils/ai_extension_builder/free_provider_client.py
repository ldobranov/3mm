from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from backend.utils.ai_extension_builder.groq_client import GroqClient
from backend.utils.ai_extension_builder.openrouter_client import OpenRouterClient


class FreeProviderFallbackClient:
    """Use the predictable Groq free model first, then OpenRouter Free."""

    default_model = "llama-3.1-8b-instant -> openrouter/free"

    def __init__(self, openrouter: OpenRouterClient, groq: GroqClient):
        self.openrouter = openrouter
        self.groq = groq
        self.last_provider: Optional[str] = None

    def is_configured(self) -> bool:
        return self.openrouter.is_configured() or self.groq.is_configured()

    @staticmethod
    def _has_usable_content(response: Dict[str, Any]) -> bool:
        if not isinstance(response, dict):
            return False
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            return False
        first = choices[0]
        if not isinstance(first, dict):
            return False
        message = first.get("message")
        if not isinstance(message, dict):
            return False
        content = message.get("content")
        if isinstance(content, str):
            return bool(content.strip())
        if isinstance(content, list):
            return any(
                isinstance(part, dict)
                and isinstance(part.get("text"), str)
                and bool(part["text"].strip())
                for part in content
            )
        return False

    def chat_completions(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2500,
        response_format: Optional[Dict[str, Any]] = None,
        response_validator: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> Dict[str, Any]:
        errors: List[Exception] = []
        last_rejected_response: Optional[Dict[str, Any]] = None
        providers = (
            ("groq", self.groq),
            ("openrouter", self.openrouter),
        )
        for provider_name, client in providers:
            if not client.is_configured():
                continue
            try:
                response = client.chat_completions(
                    messages=messages,
                    model=model if provider_name == "openrouter" else None,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                )
                if not self._has_usable_content(response):
                    raise RuntimeError(f"{provider_name} returned empty completion content")
                if response_validator is not None and not response_validator(response):
                    self.last_provider = provider_name
                    last_rejected_response = response
                    continue
                self.last_provider = provider_name
                return response
            except Exception as exc:
                errors.append(exc)

        # Let the caller inspect the last non-empty response when every configured
        # provider answered but none satisfied the caller-specific output contract.
        if last_rejected_response is not None:
            return last_rejected_response
        if errors:
            raise RuntimeError("All configured free AI providers failed") from errors[-1]
        raise RuntimeError("No free AI provider API key is configured")
