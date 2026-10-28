from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests


class GroqClient:
    """Minimal Groq Chat Completions client.

    Groq is OpenAI-compatible for chat completions.
    Endpoint: POST https://api.groq.com/openai/v1/chat/completions

    Env:
      - GROQ_API_KEY
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.groq.com/openai/v1",
        default_model: str = "llama-3.1-8b-instant",
        timeout_seconds: int = 60,
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
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
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")

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

        resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.json()
