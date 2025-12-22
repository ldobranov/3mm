from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from backend.schemas.ai_extension_builder import (
    BuildWarning,
    ClarifyExtensionResponse,
    ClarifyQuestion,
    ExtensionSpec,
)
from backend.utils.ai_extension_builder.groq_client import GroqClient
from backend.utils.ai_extension_builder.openrouter_client import OpenRouterClient


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort extraction of a JSON object from model output."""
    text = (text or "").strip()
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            candidate = parts[1].lstrip()
            if candidate.startswith("json"):
                candidate = candidate[4:]
            candidate = candidate.strip()
            try:
                return json.loads(candidate)
            except Exception:
                pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            return None
    return None


def _select_ai_client(
    ai_provider: Optional[str],
    groq_api_key: Optional[str],
    openrouter_api_key: Optional[str],
) -> Tuple[Optional[object], Optional[str], List[BuildWarning]]:
    warnings: List[BuildWarning] = []
    groq = GroqClient(api_key=groq_api_key)
    openrouter = OpenRouterClient(api_key=openrouter_api_key)

    provider = (ai_provider or os.getenv("AI_PROVIDER", "")).strip().lower()
    if provider and provider not in {"groq", "openrouter"}:
        warnings.append(
            BuildWarning(
                code="ai.provider.invalid",
                message=f"AI provider '{provider}' is invalid; falling back to auto selection.",
            )
        )
        provider = ""

    if provider == "groq":
        return groq, "groq", warnings if groq.is_configured() else warnings
    if provider == "openrouter":
        return openrouter, "openrouter", warnings if openrouter.is_configured() else warnings

    # auto
    if groq.is_configured():
        return groq, "groq", warnings
    if openrouter.is_configured():
        return openrouter, "openrouter", warnings
    return None, None, warnings


def clarify_extension_spec(
    *,
    draft_spec: ExtensionSpec,
    goal: str,
    model: Optional[str],
    ai_provider: Optional[str],
    groq_api_key: Optional[str],
    openrouter_api_key: Optional[str],
) -> ClarifyExtensionResponse:
    """Ask the model to propose a better spec + clarifying questions."""

    client, provider_name, warnings = _select_ai_client(ai_provider, groq_api_key, openrouter_api_key)
    if not client or not getattr(client, "is_configured")():
        return ClarifyExtensionResponse(
            suggested_spec=draft_spec,
            questions=[],
            notes=["AI not configured; returning draft spec."],
        )

    repo_context = (
        "Repo context (very condensed):\n"
        "- Extensions have manifest.json + backend entry (FastAPI) + frontend Vue entry + locales.\n"
        "- Backend entry must provide initialize_extension(context) and register routes under /api/...\n"
        "- Frontend uses app i18n and must provide en/bg locale JSON with namespaced keys.\n"
        "- Relationships can be declared in manifest provides/consumes; content_embedders is the main pattern.\n"
        "- If DB is used: lowercase ext_<extensionbase>_* table naming.\n"
    )

    system = (
        "You are an expert product+engineering assistant for a FastAPI + Vue 3 extension system. "
        "Your job: propose an improved ExtensionSpec and ask only the questions needed to implement it correctly. "
        "Return STRICT JSON ONLY (no markdown). "
        "Shape: {"
        "\"suggested_spec\": <ExtensionSpec JSON>, "
        "\"questions\": [{\"id\": str, \"question\": str, \"suggestions\": [str,...]}], "
        "\"notes\": [str,...]"
        "}. "
        "Keep questions short and concrete. Prefer 3-8 questions max. "
        "Do not invent unknown APIs; keep routing/i18n/relationships aligned with the repo context.\n\n"
        + repo_context
    )

    user = {
        "goal": goal,
        "draft_spec": draft_spec.model_dump(),
        "repo_context": repo_context,
    }

    try:
        resp = getattr(client, "chat_completions")(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=1200,
        )
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        data = _extract_json_object(content)
        if not data:
            return ClarifyExtensionResponse(
                suggested_spec=draft_spec,
                questions=[],
                notes=[f"AI response from {provider_name} could not be parsed as JSON; returning draft spec."],
            )

        suggested_raw = data.get("suggested_spec")
        questions_raw = data.get("questions")
        notes_raw = data.get("notes")

        suggested = draft_spec
        if isinstance(suggested_raw, dict):
            try:
                suggested = ExtensionSpec.model_validate(suggested_raw)
            except Exception:
                suggested = draft_spec

        questions: List[ClarifyQuestion] = []
        if isinstance(questions_raw, list):
            for q in questions_raw:
                if isinstance(q, dict) and isinstance(q.get("id"), str) and isinstance(q.get("question"), str):
                    questions.append(
                        ClarifyQuestion(
                            id=q["id"],
                            question=q["question"],
                            suggestions=q.get("suggestions") or [],
                        )
                    )

        notes: List[str] = []
        if isinstance(notes_raw, list):
            notes = [str(n) for n in notes_raw]
        elif warnings:
            notes = [w.message for w in warnings]

        return ClarifyExtensionResponse(suggested_spec=suggested, questions=questions, notes=notes)

    except Exception as e:
        return ClarifyExtensionResponse(
            suggested_spec=draft_spec,
            questions=[],
            notes=[f"AI clarify failed via {provider_name} ({type(e).__name__}): {e}"],
        )

