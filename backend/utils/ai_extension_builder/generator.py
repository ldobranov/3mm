from __future__ import annotations

import base64
import json
import os
import re
import zipfile
from io import BytesIO
from typing import Dict, List, Tuple, Optional

import logging

from backend.schemas.ai_extension_builder import (
    BuildReport,
    BuildWarning,
    ExtensionSpec,
)
from backend.utils.ai_extension_builder.openrouter_client import OpenRouterClient
from backend.utils.ai_extension_builder.groq_client import GroqClient
from backend.utils.ai_extension_builder.validators import validate_extension_package


logger = logging.getLogger(__name__)


def _extension_namespace(name: str) -> str:
    # StoreExtension -> store
    base = re.sub(r"extension$", "", name, flags=re.IGNORECASE)
    base = base.strip() or name
    return re.sub(r"[^a-z0-9]", "", base.lower())


def _ensure_trailing_slash(path: str) -> str:
    return path if path.endswith("/") else f"{path}/"


def _json_bytes(data: Dict) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def _extract_json_object(text: str) -> Optional[Dict]:
    """Best-effort extraction of a JSON object from model output."""
    text = text.strip()
    # Common case: model returns fenced json
    if "```" in text:
        # Take the first fenced block
        parts = text.split("```")
        if len(parts) >= 3:
            candidate = parts[1]
            # remove optional language tag
            candidate = candidate.lstrip()
            if candidate.startswith("json"):
                candidate = candidate[4:]
            candidate = candidate.strip()
            try:
                return json.loads(candidate)
            except Exception:
                pass

    # Fallback: try to locate first {...}
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            return None
    return None


def _ai_refine_files(
    spec: ExtensionSpec,
    instructions: Optional[str],
    base_files_text: Dict[str, str],
    model: Optional[str],
    ai_provider: Optional[str],
    groq_api_key: Optional[str],
    openrouter_api_key: Optional[str],
) -> Tuple[Dict[str, str], List[BuildWarning]]:
    """Call OpenRouter to refine scaffold file contents.

    Returns: (updated_files_text, warnings)
    """

    warnings: List[BuildWarning] = []

    # Provider selection:
    # 1) If ai_provider is set (from Application Settings) it wins.
    # 2) Else fall back to environment AI_PROVIDER.
    # 3) Else auto: prefer Groq when key exists.

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
        client: object = groq
        provider_name = "groq"
    elif provider == "openrouter":
        client = openrouter
        provider_name = "openrouter"
    else:
        if groq.is_configured():
            client = groq
            provider_name = "groq"
        else:
            client = openrouter
            provider_name = "openrouter"

    if not getattr(client, "is_configured")():
        warnings.append(
            BuildWarning(
                code="ai.not_configured",
                message=(
                    "AI not configured: set AI provider and API key in Application Settings or env vars. "
                    "Returning scaffold only."
                ),
            )
        )
        return {}, warnings

    selected_model = model or getattr(client, "default_model", None)
    warnings.append(
        BuildWarning(
            code="ai.provider.selected",
            message=f"Using AI provider '{provider_name}' with model '{selected_model}'.",
        )
    )

    allowed_paths = sorted(base_files_text.keys())

    repo_context = (
        "Repo extension rules (condensed):\n"
        "- Keep ZIP structure and filenames unchanged; do not add new files.\n"
        "- Backend entry must implement initialize_extension(context) and register an APIRouter(prefix=spec.api_prefix).\n"
        "- Protected endpoints must use Depends(require_user) from backend.utils.auth_dep.\n"
        "- Prefer stable API prefixes across versions (e.g. /api/<nameWithoutExtension>).\n"
        "- i18n keys must be namespaced and match JSON nesting exactly; use t('key', 'fallback') on the frontend.\n"
        "- If creating DB tables, use lowercase names and the ext_<extensionbase>_* naming to support cleanup.\n"
        "- If relationships/provides.content_embedders are present, ensure the frontend component exists and keys for its labels exist.\n"
    )

    system = (
        "You are an expert developer for a FastAPI + Vue 3 extension system. "
        "You will receive an ExtensionSpec and a set of scaffold files. "
        "Return STRICT JSON only (no markdown). Prefer BASE64 to avoid JSON escaping issues. "
        "Shape: {\"files_b64\": {\"path\": \"BASE64_UTF8_CONTENT\", ...}}. "
        "(Legacy accepted: {\"files\": {\"path\": \"content\", ...}}.) "
        "Only include files you changed. Only use paths from allowed_paths. "
        "Keep i18n keys namespaced and consistent with the JSON nesting. "
        "Do not change manifest.json structure (unless asked) and do not add new files.\n\n"
        + repo_context
    )

    user = {
        "spec": spec.model_dump(),
        "instructions": instructions or spec.goal or "",
        "repo_context": repo_context,
        "allowed_paths": allowed_paths,
        "scaffold_files": base_files_text,
    }

    try:
        # Prefer JSON mode when the provider/model supports it.
        response_format = {"type": "json_object"}

        def _call(use_response_format: bool) -> Dict:
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
                ],
                "temperature": 0.2,
                "max_tokens": 2500,
            }
            if use_response_format:
                kwargs["response_format"] = response_format
            return getattr(client, "chat_completions")(**kwargs)

        try:
            resp = _call(True)
        except Exception as e:
            # Some OpenRouter models reject response_format; retry without it.
            warnings.append(
                BuildWarning(
                    code="ai.response_format.unsupported",
                    message=f"AI provider rejected response_format JSON mode ({type(e).__name__}); retrying without it.",
                )
            )
            resp = _call(False)
        content = (
            resp.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        data = _extract_json_object(content)
        if not data or not isinstance(data, dict):
            warnings.append(
                BuildWarning(
                    code="ai.bad_response",
                    message="AI response could not be parsed as the expected JSON; returning scaffold only.",
                )
            )
            return {}, warnings

        files_plain = data.get("files") if isinstance(data.get("files"), dict) else None
        files_b64 = data.get("files_b64") if isinstance(data.get("files_b64"), dict) else None

        if not files_plain and not files_b64:
            warnings.append(
                BuildWarning(
                    code="ai.bad_response",
                    message="AI JSON did not contain 'files_b64' or 'files'; returning scaffold only.",
                )
            )
            return {}, warnings

        updates: Dict[str, str] = {}
        source = files_b64 if files_b64 else files_plain

        for path, text in (source or {}).items():
            if path not in base_files_text:
                warnings.append(
                    BuildWarning(
                        code="ai.invalid_path",
                        message=f"AI attempted to modify unsupported path '{path}'; ignored.",
                    )
                )
                continue

            if not isinstance(text, str):
                warnings.append(
                    BuildWarning(
                        code="ai.invalid_content",
                        message=f"AI returned non-string content for '{path}'; ignored.",
                    )
                )
                continue

            if files_b64:
                try:
                    candidate = base64.b64decode(text).decode("utf-8")
                except Exception as e:
                    warnings.append(
                        BuildWarning(
                            code="ai.invalid_base64",
                            message=f"AI returned invalid base64 content for '{path}' ({type(e).__name__}); ignored.",
                        )
                    )
                    continue
            else:
                candidate = text

            # Safety: refuse extremely large updates (prevents UI lockups / runaway generations).
            max_chars = 200_000
            if len(candidate) > max_chars:
                warnings.append(
                    BuildWarning(
                        code="ai.content_too_large",
                        message=f"AI content for '{path}' is too large ({len(candidate)} chars); ignored.",
                    )
                )
                continue

            # Guard against common "refusal placeholders" where the model replaces file content
            # with messages like "file too large for pasting here".
            lowered = candidate.lower()
            refusal_markers = [
                "file too large",
                "too large for pasting",
                "too large to paste",
                "omitted",
                "[omitted]",
                "content omitted",
                "cannot provide",
                "can't provide",
                "refuse",
            ]
            if any(m in lowered for m in refusal_markers):
                warnings.append(
                    BuildWarning(
                        code="ai.refusal_placeholder",
                        message=(
                            f"AI returned a refusal/placeholder message for '{path}'; ignored to keep the scaffold version."
                        ),
                    )
                )
                continue

            # If AI touched JSON files, require valid JSON so we don't ship broken locales/manifest.
            if path.endswith('.json'):
                try:
                    json.loads(candidate) if candidate.strip() else {}
                except Exception as e:
                    warnings.append(
                        BuildWarning(
                            code="ai.invalid_json",
                            message=f"AI returned invalid JSON for '{path}' ({type(e).__name__}: {e}); ignored.",
                        )
                    )
                    continue

            updates[path] = candidate

        if updates:
            changed = sorted(updates.keys())
            logger.info("AI updated %s file(s): %s", len(changed), changed)
            preview = ", ".join(changed[:12])
            if len(changed) > 12:
                preview += f" (+{len(changed) - 12} more)"
            warnings.append(
                BuildWarning(
                    code="ai.updated_files",
                    message=f"AI updated file(s): {preview}",
                )
            )

        return updates, warnings

    except Exception as e:
        warnings.append(
            BuildWarning(
                code="ai.error",
                message=f"AI call failed via {provider_name} ({type(e).__name__}): {e}. Returning scaffold only.",
            )
        )
        return {}, warnings


def _python_backend_entry(spec: ExtensionSpec) -> str:
    prefix = spec.api_prefix
    ns = _extension_namespace(spec.name)
    # Keep skeleton aligned with EXTENSION_DEVELOPMENT_GUIDE.md patterns.
    return f'''from __future__ import annotations

from fastapi import APIRouter, Depends
from backend.utils.auth_dep import require_user


def initialize_extension(context):
    """Initialize {spec.name} {spec.version}."""
    router = APIRouter(prefix="{prefix}")

    @router.get("/health")
    def health():
        return {{"ok": True, "extension": "{spec.name}", "version": "{spec.version}"}}

    @router.get("/private")
    def private_endpoint(claims: dict = Depends(require_user)):
        return {{"user_id": claims.get("user_id") or claims.get("sub"), "ns": "{ns}"}}

    # TODO: Add endpoints required by relationships (content embedders, shared APIs, etc.)

    context.register_router(router)
    return {{"routes_registered": len(router.routes), "status": "initialized"}}


def cleanup_extension(context):
    return {{"status": "cleaned_up"}}
'''


def _vue_main_component(spec: ExtensionSpec) -> str:
    ns = _extension_namespace(spec.name)
    title_key = f"{ns}.title"
    return f'''<template>
  <div class="extension-container">
    <div class="extension-header">
      <h1>{{{{ t('{title_key}', '{spec.name}') }}}}</h1>
      <p class="muted">{spec.description}</p>
    </div>

    <div class="extension-content">
      <p>{{{{ t('{ns}.status.ready', 'Ready') }}}}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import {{ useI18n }} from '@/utils/i18n'

const {{ t }} = useI18n()
</script>

<style scoped>
.extension-container {{
  max-width: 1200px;
  margin: 0 auto;
  padding: 1.5rem;
}}

.extension-header {{
  margin-bottom: 1rem;
}}

.muted {{
  opacity: 0.75;
}}
</style>
'''


def _vue_embedder_component(component_name: str, spec: ExtensionSpec) -> str:
    ns = _extension_namespace(spec.name)
    return f'''<template>
  <div class="embedder">
    <strong>{{{{ t('{ns}.embedders.{component_name}.title', '{component_name}') }}}}</strong>
    <p class="muted">{{{{ t('{ns}.embedders.{component_name}.hint', 'Embedder component placeholder') }}}}</p>
  </div>
</template>

<script setup lang="ts">
import {{ useI18n }} from '@/utils/i18n'

const {{ t }} = useI18n()
</script>

<style scoped>
.embedder {{
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  padding: 0.75rem;
}}

.muted {{
  opacity: 0.75;
}}
</style>
'''


def _vue_route_component(component_name: str, spec: ExtensionSpec, route_path: Optional[str] = None) -> str:
    """Generic placeholder component for a manifest frontend route."""
    ns = _extension_namespace(spec.name)
    safe_component = component_name.replace('.vue', '')
    title_key = f"{ns}.routes.{safe_component}.title"
    hint_key = f"{ns}.routes.{safe_component}.hint"
    route_hint = f"Route: {route_path}" if route_path else "Route component placeholder"
    return f'''<template>
  <div class="route">
    <h2>{{{{ t('{title_key}', '{safe_component}') }}}}</h2>
    <p class="muted">{{{{ t('{hint_key}', '{route_hint}') }}}}</p>
  </div>
</template>

<script setup lang="ts">
import {{ useI18n }} from '@/utils/i18n'

const {{ t }} = useI18n()
</script>

<style scoped>
.route {{
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  padding: 0.75rem;
}}

.muted {{
  opacity: 0.75;
}}
</style>
'''


def _default_locales(spec: ExtensionSpec) -> Tuple[Dict, Dict]:
    ns = _extension_namespace(spec.name)
    en = {
        ns: {
            "title": spec.name,
            "status": {"ready": "Ready"},
            "actions": {"save": "Save", "cancel": "Cancel"},
            "embedders": {},
            "routes": {},
        }
    }

    bg = {
        ns: {
            "title": spec.name,
            "status": {"ready": "Готово"},
            "actions": {"save": "Запази", "cancel": "Отказ"},
            "embedders": {},
            "routes": {},
        }
    }

    # Add placeholder strings for any provided embedders
    provides = spec.provides.content_embedders if spec.provides and spec.provides.content_embedders else None
    if provides:
        for embedder_type, cfg in provides.items():
            component = cfg.component
            en[ns]["embedders"][component] = {
                "title": f"{component}",
                "hint": f"Embedder: {embedder_type}",
            }
            bg[ns]["embedders"][component] = {
                "title": f"{component}",
                "hint": f"Вграждане: {embedder_type}",
            }

    # Add placeholder strings for any configured frontend routes (beyond the main entry)
    for r in spec.frontend_routes or []:
        comp = r.component
        if not comp:
            continue
        comp_name = comp.replace('.vue', '')
        en[ns]["routes"].setdefault(comp_name, {})
        bg[ns]["routes"].setdefault(comp_name, {})
        en[ns]["routes"][comp_name].setdefault("title", comp_name)
        bg[ns]["routes"][comp_name].setdefault("title", comp_name)
        if r.path:
            en[ns]["routes"][comp_name].setdefault("hint", f"Route: {r.path}")
            bg[ns]["routes"][comp_name].setdefault("hint", f"Път: {r.path}")

    return en, bg


def build_extension_zip(
    spec: ExtensionSpec,
    instructions: Optional[str] = None,
    use_ai: bool = True,
    model: Optional[str] = None,
    ai_provider: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    openrouter_api_key: Optional[str] = None,
) -> Tuple[BuildReport, str, Dict[str, str]]:
    """Build a ZIP package (base64) matching backend upload expectations.

    Structure:
      - manifest.json (root)
      - backend/<backend_entry>
      - frontend/<frontend_entry>
      - frontend/<extra components>
      - locales/<lang>.json
    """

    extension_id = f"{spec.name}_{spec.version}"
    warnings: List[BuildWarning] = []

    # Normalize locales directory
    locales_dir = _ensure_trailing_slash(spec.locales.directory)

    manifest: Dict = {
        "name": spec.name,
        "version": spec.version,
        "type": spec.type,
        "description": spec.description,
        "author": spec.author,
        "backend_entry": spec.backend_entry,
        "frontend_entry": spec.frontend_entry,
        "frontend_components": spec.frontend_components,
        "frontend_routes": [r.model_dump() for r in spec.frontend_routes],
        "locales": {
            "supported": spec.locales.supported,
            "default": spec.locales.default,
            "directory": locales_dir,
        },
        "permissions": spec.permissions,
        "public_endpoints": spec.public_endpoints,
        "dependencies": spec.dependencies,
    }

    if spec.provides is not None:
        manifest["provides"] = spec.provides.model_dump(exclude_none=True)

    if spec.consumes is not None:
        manifest["consumes"] = spec.consumes.model_dump(exclude_none=True)

    # Files
    files: Dict[str, bytes] = {}

    files["manifest.json"] = _json_bytes(manifest)

    # Backend
    files[f"backend/{spec.backend_entry}"] = _python_backend_entry(spec).encode("utf-8")

    # Frontend
    files[f"frontend/{spec.frontend_entry}"] = _vue_main_component(spec).encode("utf-8")

    # Ensure all route components exist (so generated extensions aren't "empty" due to missing .vue files).
    for r in spec.frontend_routes or []:
        comp = r.component
        if not comp:
            continue
        comp_file = comp if comp.endswith('.vue') else f"{comp}.vue"
        frontend_path = f"frontend/{comp_file}"
        if frontend_path in files:
            continue
        files[frontend_path] = _vue_route_component(comp_file, spec, route_path=r.path).encode("utf-8")

    # Ensure frontend_components exist
    for comp in spec.frontend_components or []:
        comp_file = comp if comp.endswith('.vue') else f"{comp}.vue"
        frontend_path = f"frontend/{comp_file}"
        if frontend_path in files:
            continue
        files[frontend_path] = _vue_route_component(comp_file, spec).encode("utf-8")

    # Relationship-aware components (provider side)
    provides = spec.provides.content_embedders if spec.provides and spec.provides.content_embedders else None
    if provides:
        for _, cfg in provides.items():
            comp_name = cfg.component
            # Ensure .vue suffix
            comp_file = f"{comp_name}.vue" if not comp_name.endswith(".vue") else comp_name
            files[f"frontend/{comp_file}"] = _vue_embedder_component(comp_name.replace('.vue', ''), spec).encode("utf-8")

    # Locales (root locales/ as per installer expectations)
    en_json, bg_json = _default_locales(spec)
    for lang in spec.locales.supported:
        if lang == "en":
            files[f"{locales_dir}{lang}.json"] = _json_bytes(en_json)
        elif lang == "bg":
            files[f"{locales_dir}{lang}.json"] = _json_bytes(bg_json)
        else:
            warnings.append(
                BuildWarning(
                    code="locale.missing",
                    message=f"Locale '{lang}' requested but generator only scaffolds en/bg in v1; created empty file.",
                )
            )
            files[f"{locales_dir}{lang}.json"] = _json_bytes({})

    # Optional AI refinement step: modify ONLY existing files.
    if use_ai and (instructions or spec.goal):
        base_files_text = {}
        for path, content in files.items():
            # Only pass text files to the model
            try:
                base_files_text[path] = content.decode("utf-8")
            except Exception:
                continue

        updates, ai_warnings = _ai_refine_files(
            spec,
            instructions,
            base_files_text,
            model,
            ai_provider=ai_provider,
            groq_api_key=groq_api_key,
            openrouter_api_key=openrouter_api_key,
        )
        warnings.extend(ai_warnings)

        for path, text in updates.items():
            files[path] = text.encode("utf-8")

        # Validation + optional self-fix pass
        current_files_text: Dict[str, str] = {}
        for p, b in files.items():
            try:
                current_files_text[p] = b.decode("utf-8")
            except Exception:
                continue

        validation_warnings = validate_extension_package(spec, current_files_text)
        warnings.extend(validation_warnings)

        if validation_warnings:
            # Try one additional AI pass to address deterministic validator warnings.
            fix_lines = [
                f"- {w.code}: {w.message}" for w in validation_warnings[:15]
            ]
            fix_instructions = (
                (instructions or spec.goal or "")
                + "\n\nFix these build/validation warnings without adding files or changing paths:\n"
                + "\n".join(fix_lines)
            )

            fix_updates, fix_ai_warnings = _ai_refine_files(
                spec,
                fix_instructions,
                current_files_text,
                model,
                ai_provider=ai_provider,
                groq_api_key=groq_api_key,
                openrouter_api_key=openrouter_api_key,
            )
            warnings.extend(fix_ai_warnings)

            for path, text in fix_updates.items():
                files[path] = text.encode("utf-8")

            # Re-run validators to surface any remaining issues
            current_files_text_after: Dict[str, str] = {}
            for p, b in files.items():
                try:
                    current_files_text_after[p] = b.decode("utf-8")
                except Exception:
                    continue
            warnings.extend(validate_extension_package(spec, current_files_text_after))

    # ZIP
    buf = BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)

    report = BuildReport(
        extension_id=extension_id,
        files=sorted(files.keys()),
        warnings=warnings,
    )

    zip_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    # Expose text contents for in-app editing (best-effort utf-8 decoding).
    files_text: Dict[str, str] = {}
    for path, content in files.items():
        try:
            files_text[path] = content.decode("utf-8")
        except Exception:
            # Skip non-text files.
            continue

    return report, zip_b64, files_text


def package_extension_zip(
    spec: ExtensionSpec,
    files_text: Dict[str, str],
) -> Tuple[BuildReport, str, Dict[str, str]]:
    """Package a ZIP (base64) from provided text files.

    This is used for the "edit → rebuild" flow in the AI Extension Builder UI.
    """

    extension_id = f"{spec.name}_{spec.version}"
    warnings: List[BuildWarning] = []

    # Basic path safety and normalization
    sanitized: Dict[str, str] = {}
    for path, text in (files_text or {}).items():
        if not isinstance(path, str) or not isinstance(text, str):
            continue
        if path.startswith("/") or ".." in path.split("/"):
            warnings.append(
                BuildWarning(
                    code="package.invalid_path",
                    message=f"Refusing to include unsafe path '{path}'.",
                )
            )
            continue
        sanitized[path] = text

    required = [
        "manifest.json",
        f"backend/{spec.backend_entry}",
        f"frontend/{spec.frontend_entry}",
    ]
    for req in required:
        if req not in sanitized:
            warnings.append(
                BuildWarning(
                    code="package.missing_required",
                    message=f"Missing required file '{req}'. The resulting ZIP may not install.",
                )
            )

    files_bytes: Dict[str, bytes] = {p: t.encode("utf-8") for p, t in sanitized.items()}

    # Deterministic validations (surface issues early in UI)
    warnings.extend(validate_extension_package(spec, sanitized))

    buf = BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, content in files_bytes.items():
            zf.writestr(path, content)

    report = BuildReport(
        extension_id=extension_id,
        files=sorted(files_bytes.keys()),
        warnings=warnings,
    )
    zip_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return report, zip_b64, sanitized
