from __future__ import annotations

from typing import Any, Dict, List, Optional

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

    def chat_completions(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2500,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        errors: List[Exception] = []
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
                self.last_provider = provider_name
                return response
            except Exception as exc:
                errors.append(exc)

        if errors:
            raise RuntimeError("All configured free AI providers failed") from errors[-1]
        raise RuntimeError("No free AI provider API key is configured")
