from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests


class OpenRouterClient:
    """Minimal OpenRouter Chat Completions client.

    Docs: https://openrouter.ai/docs
    Endpoint: POST https://openrouter.ai/api/v1/chat/completions
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://openrouter.ai/api/v1",
        # Note: OpenRouter free model availability changes; this is a commonly available free default.
        default_model: str = "meta-llama/llama-3.1-8b-instruct:free",
        timeout_seconds: int = 60,
    ):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def chat_completions(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2500,
        response_format: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        url = f"{self.base_url}/chat/completions"
        payload: Dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # OpenAI-style JSON mode. Not all models support it; callers should handle failures.
        if response_format:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # Optional but recommended by OpenRouter
        # headers["HTTP-Referer"] = "https://your-domain.example"  # not required
        # headers["X-Title"] = "3mm Extension Builder"  # not required
        if extra_headers:
            headers.update(extra_headers)

        resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout_seconds)
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            # Include response body to make debugging (e.g. model not found) easier.
            raise requests.HTTPError(f"{e} :: {resp.text}")
        return resp.json()
