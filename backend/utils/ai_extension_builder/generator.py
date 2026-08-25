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
from backend.utils.ai_extension_builder.free_provider_client import FreeProviderFallbackClient
from backend.utils.ai_extension_builder.validators import validate_extension_package
from backend.utils.ai_extension_builder.widget_spec import (
    compiled_module_id,
    normalize_widget_spec,
)


logger = logging.getLogger(__name__)


class IncompleteAIGenerationError(RuntimeError):
    """Raised when AI leaves a compiled widget as a non-functional scaffold."""


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
    # 3) Else auto: OpenRouter Free first, then Groq Free on failure.

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
        client = FreeProviderFallbackClient(openrouter, groq)
        provider_name = "groq -> openrouter/free"

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
        "Return STRICT JSON only, with no markdown, reasoning or explanation. "
        "Use exactly this shape: {\"files\": {\"path\": \"complete UTF-8 file content\"}}. "
        "Do not use Base64. If no file needs changes, return {\"files\": {}}. "
        "Only include files you changed. Only use paths from allowed_paths. "
        "Keep i18n keys namespaced and consistent with the JSON nesting. "
        "Do not change manifest.json structure (unless asked) and do not add new files.\n\n"
        "For a compiled widget, source/frontend/Widget.vue must implement the requested visible behavior; "
        "never leave the generic scaffold that only lists config values. Use reactive state and lifecycle "
        "hooks when live updates are required. Named choices must use string enum settings, not booleans; "
        "timezone settings use JSON Schema format 'timezone'.\n\n"
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

        used_response_format = True
        try:
            resp = _call(used_response_format)
        except Exception as e:
            # Some OpenRouter models reject response_format; retry without it.
            warnings.append(
                BuildWarning(
                    code="ai.response_format.unsupported",
                    message=f"AI provider rejected response_format JSON mode ({type(e).__name__}); retrying without it.",
                )
            )
            used_response_format = False
            resp = _call(used_response_format)
        content = (
            resp.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        data = _extract_json_object(content)
        if not data and used_response_format:
            warnings.append(
                BuildWarning(
                    code="ai.bad_response.retry",
                    message="AI returned invalid JSON; retrying once without JSON mode.",
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


def _compiled_widget_component(spec: ExtensionSpec) -> str:
    if spec.capability_plan and spec.capability_plan.presentations:
        return _compiled_capability_indicator_component(spec)
    properties = (spec.config_schema or {}).get("properties", {})
    has_timezone = any(
        isinstance(item, dict) and item.get("format") == "timezone"
        for item in properties.values()
    )
    if has_timezone:
        return _compiled_time_widget_component(spec)
    return f'''<template>
  <section class="generated-widget">
    <strong>{spec.name}</strong>
    <dl v-if="entries.length">
      <template v-for="([key, value]) in entries" :key="key">
        <dt>{{{{ key }}}}</dt><dd>{{{{ value }}}}</dd>
      </template>
    </dl>
    <span v-else>Ready</span>
  </section>
</template>

<script setup lang="ts">
import {{ computed }} from 'vue'
const props = defineProps<{{ config?: Record<string, unknown> }}>()
const entries = computed(() => Object.entries(props.config || {{}}))
</script>

<style scoped>
.generated-widget {{ display:grid; min-height:100%; place-content:center; gap:.75rem; padding:1rem; color:inherit }}
dl {{ display:grid; grid-template-columns:auto 1fr; gap:.35rem .75rem; margin:0 }}
dt {{ font-weight:600 }} dd {{ margin:0 }}
</style>
'''


def _compiled_widget_has_functional_scaffold(spec: ExtensionSpec) -> bool:
    if spec.capability_plan and spec.capability_plan.presentations:
        return True
    properties = (spec.config_schema or {}).get("properties", {})
    return any(
        isinstance(item, dict) and item.get("format") == "timezone"
        for item in properties.values()
    )


def _compiled_capability_runtime_source(spec: ExtensionSpec) -> str:
    plan = spec.capability_plan
    assert plan is not None
    binding = plan.bindings[0]
    descriptor = json.dumps({
        "capabilityId": binding.capability_id,
        "operation": binding.operation,
        "action": binding.action,
        "deviceSetting": binding.device_setting,
        "channelSetting": binding.channel_setting,
        "staleAfterMs": binding.stale_after_seconds * 1000,
    })
    return f'''import {{ computed, onBeforeUnmount, onMounted, ref, watch, type ComputedRef }} from 'vue'
export const capabilityDescriptor = {descriptor} as const
type FeedItem = {{ value: unknown; occurredAt: number }}
export function useCapabilityFeed(config: ComputedRef<Record<string, unknown>>) {{
  const value = ref<unknown>(null)
  const status = ref<'stale' | 'offline' | 'error' | 'ready'>('stale')
  const history = ref<FeedItem[]>([])
  const pending = ref(false)
  const deviceId = computed(() => String(config.value[capabilityDescriptor.deviceSetting] || ''))
  const channel = computed(() => capabilityDescriptor.channelSetting ? String(config.value[capabilityDescriptor.channelSetting] || '') : '')
  const publicStateUrl = computed(() => String(config.value._publicCapabilityStateUrl || ''))
  const authHeaders = () => {{ const token = localStorage.getItem('authToken'); return token ? {{ Authorization: `Bearer ${{token}}` }} : {{}} }}
  let backendUrlPromise: Promise<string> | undefined
  const normalizedUrl = (value: string) => value.trim().replace(/[/]+$/, '')
  async function backendUrl() {{
    if (!backendUrlPromise) backendUrlPromise = (async () => {{
      try {{
        const response = await fetch('/runtime-config.json', {{ cache: 'no-store' }})
        if (response.ok) {{
          const runtime = await response.json() as {{ backend_url?: unknown; backend_port?: unknown }}
          if (typeof runtime.backend_url === 'string' && runtime.backend_url.trim()) return normalizedUrl(runtime.backend_url)
          if (Number.isInteger(runtime.backend_port) && Number(runtime.backend_port) > 0 && Number(runtime.backend_port) <= 65535) {{
            return `${{window.location.protocol}}//${{window.location.hostname}}:${{Number(runtime.backend_port)}}`
          }}
        }}
      }} catch {{ /* continue with the configured fallback */ }}
      const override = localStorage.getItem('mm_backend_url_override')
      if (override !== null) return normalizedUrl(override)
      return `${{window.location.protocol}}//${{window.location.hostname}}:8887`
    }})()
    return backendUrlPromise
  }}
  async function apiFetch(path: string, init?: RequestInit) {{
    const base = await backendUrl()
    return fetch(base ? `${{base}}${{path}}` : path, init)
  }}
  async function refresh() {{
    if (!deviceId.value || (capabilityDescriptor.channelSetting && !channel.value)) {{ status.value = 'stale'; return }}
    try {{
      const statePath = publicStateUrl.value || `/api/v1/devices/${{encodeURIComponent(deviceId.value)}}/capabilities/${{encodeURIComponent(capabilityDescriptor.capabilityId)}}/state`
      const stateResponse = await apiFetch(statePath, {{ headers: authHeaders() }})
      if (!stateResponse.ok) {{ status.value = stateResponse.status === 404 ? 'stale' : stateResponse.status >= 500 ? 'offline' : 'error'; return }}
      const snapshot = await stateResponse.json() as {{ values?: Record<string, unknown>; observed_at?: string }}
      const stateValues = snapshot.values || {{}}
      value.value = channel.value ? stateValues[channel.value] : Object.values(stateValues)[0]
      const observedAt = Date.parse(snapshot.observed_at || '') || 0
      status.value = !observedAt || Date.now() - observedAt > capabilityDescriptor.staleAfterMs ? 'stale' : 'ready'
      if (publicStateUrl.value) {{ history.value = []; return }}
      const eventResponse = await apiFetch(`/api/v1/devices/${{encodeURIComponent(deviceId.value)}}/events`, {{ headers: authHeaders() }})
      if (eventResponse.ok) {{
        const events = await eventResponse.json() as Array<{{ payload?: Record<string, unknown>; occurred_at?: string }}>
        history.value = events.filter(item => !channel.value || item.payload?.channel === channel.value || item.payload?.capability_id === channel.value).slice(0, 20).map(item => ({{ value: item.payload?.value, occurredAt: Date.parse(item.occurred_at || '') || Date.now() }}))
      }}
    }} catch {{ status.value = 'offline' }}
  }}
  async function invoke(nextValue: boolean) {{
    if (capabilityDescriptor.operation !== 'invoke' || !capabilityDescriptor.action) return
    pending.value = true
    try {{
      const response = await apiFetch(`/api/v1/devices/${{encodeURIComponent(deviceId.value)}}/capabilities/invoke`, {{
        method: 'POST', headers: {{ 'Content-Type': 'application/json', ...authHeaders() }},
        body: JSON.stringify({{ capability_id: capabilityDescriptor.capabilityId, action: capabilityDescriptor.action, arguments: {{ channel: channel.value, value: nextValue }} }})
      }})
      status.value = response.ok ? 'stale' : 'error'
    }} catch {{ status.value = 'offline' }} finally {{ pending.value = false }}
  }}
  let timer: ReturnType<typeof setInterval> | undefined
  onMounted(() => {{ refresh(); timer = setInterval(refresh, 3000) }})
  onBeforeUnmount(() => {{ if (timer) clearInterval(timer) }})
  watch([deviceId, channel], refresh)
  return {{ value, status, history, pending, deviceId, channel, refresh, invoke }}
}}
'''


def _compiled_capability_indicator_component(spec: ExtensionSpec) -> str:
    plan = spec.capability_plan
    assert plan is not None
    presentation = plan.presentations[0]
    state_map = {
        (item.state, str(item.value).lower() if item.state == "value" else item.state): {
            "label": item.label, "color": item.color,
        }
        for item in presentation.states
    }
    defaults = {
        "active": state_map.get(("value", "true"), {"label": "Active", "color": "#22C55E"}),
        "inactive": state_map.get(("value", "false"), {"label": "Inactive", "color": "#EF4444"}),
        "stale": state_map.get(("stale", "stale"), {"label": "Stale", "color": "#F59E0B"}),
        "offline": state_map.get(("offline", "offline"), {"label": "Offline", "color": "#6B7280"}),
        "error": state_map.get(("error", "error"), {"label": "Error", "color": "#DC2626"}),
    }
    return f'''<template>
  <section class="capability-widget" :class="`is-${{visualState}}`">
    <template v-if="presentationKind === 'indicator'">
      <span class="lamp" :style="{{ backgroundColor: indicatorColor }}" aria-hidden="true"></span>
      <strong>{{{{ label }}}}</strong>
    </template>
    <template v-else-if="presentationKind === 'metric'">
      <strong class="metric">{{{{ displayValue }}}}</strong><span>{{{{ label }}}}</span>
    </template>
    <ol v-else-if="presentationKind === 'list'" class="history">
      <li v-for="item in history" :key="item.occurredAt"><strong>{{{{ item.value }}}}</strong><time>{{{{ new Date(item.occurredAt).toLocaleTimeString() }}}}</time></li>
    </ol>
    <div v-else-if="presentationKind === 'chart'" class="chart">
      <span v-for="item in history.slice().reverse()" :key="item.occurredAt" :style="{{ height: barHeight(item.value) }}"></span>
    </div>
    <label v-else-if="presentationKind === 'form'" class="command"><input v-model="formValue" type="checkbox" /><button type="button" :disabled="pending" @click="invoke(formValue)">{{{{ pending ? 'Sending…' : 'Apply' }}}}</button></label>
    <strong v-else>{{{{ displayValue }}}}</strong>
    <small>{{{{ channel || deviceId || 'Select a data source' }}}}</small>
  </section>
</template>

<script setup lang="ts">
import {{ computed, ref }} from 'vue'
import {{ useCapabilityFeed }} from './capability-runtime'
const props = defineProps<{{ config?: Record<string, unknown> }}>()
const config = computed(() => props.config || {{}})
const {{ value, status, history, pending, deviceId, channel, invoke }} = useCapabilityFeed(config)
const presentationKind = {json.dumps(presentation.kind)}
const defaults = {json.dumps(defaults)} as Record<string, {{ label: string; color: string }}>
const activeHigh = computed(() => props.config?.activeHigh !== false)
const visualState = computed(() => status.value === 'ready' ? (Boolean(value.value) === activeHigh.value ? 'active' : 'inactive') : status.value)
const label = computed(() => defaults[visualState.value]?.label || visualState.value)
const indicatorColor = computed(() => visualState.value === 'active' ? String(props.config?.activeColor || defaults.active.color) : visualState.value === 'inactive' ? String(props.config?.inactiveColor || defaults.inactive.color) : defaults[visualState.value]?.color || '#6B7280')
const displayValue = computed(() => value.value == null ? '—' : String(value.value))
const formValue = ref(false)
const barHeight = (item: unknown) => `${{Math.max(8, Math.min(100, typeof item === 'number' ? Math.abs(item) : item ? 100 : 8))}}%`
</script>

<style scoped>
.capability-widget {{ display:grid; min-height:100%; place-content:center; justify-items:center; gap:.55rem; padding:1rem; color:inherit; text-align:center }}
.lamp {{ width:clamp(3.5rem, 35%, 8rem); aspect-ratio:1; border-radius:50%; border:1px solid color-mix(in srgb, currentColor 18%, transparent); box-shadow:0 0 0 .55rem color-mix(in srgb, currentColor 5%, transparent), 0 .5rem 1.5rem color-mix(in srgb, currentColor 20%, transparent) }}
strong {{ font-size:1.1rem }} .metric {{ font-size:clamp(2rem, 8vw, 4.5rem); font-variant-numeric:tabular-nums }} small {{ color:var(--text-secondary, currentColor); opacity:.72 }}
.history {{ display:grid; gap:.35rem; width:100%; margin:0; padding:0; list-style:none }} .history li {{ display:flex; justify-content:space-between; gap:1rem }}
.chart {{ display:flex; align-items:end; gap:3px; width:min(100%, 18rem); height:8rem }} .chart span {{ flex:1; min-height:4px; border-radius:3px 3px 0 0; background:var(--accent-color, #4f7cff) }}
.command {{ display:flex; align-items:center; gap:.75rem }} button {{ padding:.45rem .8rem; border:0; border-radius:.45rem; background:var(--accent-color, #4f7cff); color:white }}
</style>
'''


def _compiled_time_widget_component(spec: ExtensionSpec) -> str:
    return f'''<template>
  <section class="time-widget" :class="`time-widget--${{displayMode}}`">
    <div v-if="displayMode === 'analog'" class="clock-face" aria-label="Analog clock">
      <span class="hand hand--hour" :style="hourStyle"></span>
      <span class="hand hand--minute" :style="minuteStyle"></span>
      <span class="hand hand--second" :style="secondStyle"></span>
      <span class="clock-dot"></span>
    </div>
    <time v-else :datetime="now.toISOString()">{{{{ formattedTime }}}}</time>
    <small>{{{{ timezone }}}}</small>
  </section>
</template>

<script setup lang="ts">
import {{ computed, onBeforeUnmount, onMounted, ref }} from 'vue'
const props = defineProps<{{ config?: Record<string, unknown> }}>()
const now = ref(new Date())
const timezone = computed(() => String(props.config?.timezone || 'UTC'))
const displayMode = computed(() => String(props.config?.displayMode || 'digital'))
const uses12Hours = computed(() => String(props.config?.hourFormat || '24') === '12')
const parts = computed(() => {{
  const values = new Intl.DateTimeFormat('en-GB', {{
    timeZone: timezone.value, hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
  }}).formatToParts(now.value)
  const read = (type: string) => Number(values.find(item => item.type === type)?.value || 0)
  return {{ hour: read('hour'), minute: read('minute'), second: read('second') }}
}})
const formattedTime = computed(() => new Intl.DateTimeFormat(undefined, {{
  timeZone: timezone.value, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: uses12Hours.value
}}).format(now.value))
const hourStyle = computed(() => ({{ transform: `rotate(${{(parts.value.hour % 12) * 30 + parts.value.minute * 0.5}}deg)` }}))
const minuteStyle = computed(() => ({{ transform: `rotate(${{parts.value.minute * 6 + parts.value.second * 0.1}}deg)` }}))
const secondStyle = computed(() => ({{ transform: `rotate(${{parts.value.second * 6}}deg)` }}))
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => {{ timer = setInterval(() => {{ now.value = new Date() }}, 1000) }})
onBeforeUnmount(() => {{ if (timer) clearInterval(timer) }})
</script>

<style scoped>
.time-widget {{ display:grid; min-height:100%; place-content:center; justify-items:center; gap:.65rem; padding:1rem; color:inherit }}
time {{ font-size:clamp(2rem, 8vw, 5rem); font-variant-numeric:tabular-nums; font-weight:650; letter-spacing:-.04em }}
small {{ color:var(--text-secondary, currentColor); opacity:.72 }}
.clock-face {{ position:relative; width:min(70%, 15rem); aspect-ratio:1; border:clamp(3px, .5vw, 6px) solid currentColor; border-radius:50%; background:color-mix(in srgb, currentColor 5%, transparent) }}
.hand {{ position:absolute; left:50%; bottom:50%; width:3px; border-radius:99px; background:currentColor; transform-origin:50% 100% }}
.hand--hour {{ height:27%; width:5px }} .hand--minute {{ height:38%; width:4px }}
.hand--second {{ height:42%; width:2px; background:var(--accent-color, #4f7cff) }}
.clock-dot {{ position:absolute; left:50%; top:50%; width:12px; aspect-ratio:1; border-radius:50%; background:currentColor; transform:translate(-50%, -50%) }}
</style>
'''


def _compiled_widget_editor(spec: ExtensionSpec) -> str:
    schema = json.dumps(spec.config_schema or {"type": "object", "properties": {}}, ensure_ascii=False)
    return f'''<template>
  <div class="generated-editor">
    <label v-for="field in fields" :key="field.key">
      <span>{{{{ field.title }}}}</span>
      <input v-if="field.type === 'boolean'" type="checkbox" :checked="Boolean(value[field.key])" @change="setBoolean(field.key, $event)" />
      <select v-else-if="field.options.length || field.format === 'timezone'" :value="value[field.key] ?? field.defaultValue ?? ''" @change="setValue(field.key, $event)">
        <option v-for="(option, index) in field.options" :key="String(option)" :value="option">{{{{ field.optionLabels[index] || option }}}}</option>
      </select>
      <input v-else :type="field.format === 'color' ? 'color' : field.type === 'integer' || field.type === 'number' ? 'number' : 'text'" :value="value[field.key] ?? field.defaultValue ?? ''" @input="setValue(field.key, $event)" />
    </label>
    <p v-if="!fields.length">This widget has no configurable fields.</p>
  </div>
</template>

<script setup lang="ts">
import {{ computed }} from 'vue'
const schema = {schema} as any
const props = defineProps<{{ config?: Record<string, unknown>; modelValue?: Record<string, unknown> }}>()
const emit = defineEmits<{{ (event: 'update:modelValue', value: Record<string, unknown>): void }}>()
const value = computed(() => props.config || props.modelValue || {{}})
const timezoneOptions = (() => {{
  try {{ return Array.from(new Set(['UTC', ...((Intl as any).supportedValuesOf?.('timeZone') || [])])) }} catch {{ return ['UTC'] }}
}})()
const fields = Object.entries(schema.properties || {{}}).map(([key, item]: [string, any]) => ({{
  key, title: item.title || key, type: item.type || 'string', format: item.format || '',
  defaultValue: item.default, options: item.enum || (item.format === 'timezone' ? timezoneOptions : []),
  optionLabels: item.enumNames || []
}}))
function setValue(key: string, event: Event) {{ const target = event.target as HTMLInputElement; const field = fields.find(item => item.key === key); const next = field?.type === 'integer' || field?.type === 'number' ? Number(target.value) : target.value; emit('update:modelValue', {{ ...value.value, [key]: next }}) }}
function setBoolean(key: string, event: Event) {{ emit('update:modelValue', {{ ...value.value, [key]: (event.target as HTMLInputElement).checked }}) }}
</script>

<style scoped>
.generated-editor {{ display:grid; gap:1rem }} label {{ display:grid; gap:.4rem }} span {{ font-weight:600 }} input,select {{ padding:.55rem .7rem; border:1px solid var(--input-border); border-radius:var(--border-radius-sm); background:var(--input-bg); color:var(--text-primary) }}
</style>
'''


def _build_compiled_widget_zip(
    spec: ExtensionSpec, instructions: Optional[str], use_ai: bool, model: Optional[str],
    ai_provider: Optional[str], groq_api_key: Optional[str], openrouter_api_key: Optional[str],
) -> Tuple[BuildReport, str, Dict[str, str]]:
    module_id = compiled_module_id(spec.name)
    widget_id = "widget"
    editor_id = "widget_editor"
    contract = {
        "compiled_ui_version": 1, "module_id": module_id, "version": spec.version,
        "entrypoints": [
            {"entrypoint_id": widget_id, "kind": "widget", "source": "source/frontend/Widget.vue", "label": {"en": spec.name, "translations": {"bg": spec.name}}},
            {"entrypoint_id": editor_id, "kind": "editor", "source": "source/frontend/WidgetEditor.vue", "label": {"en": f"{spec.name} settings", "translations": {"bg": f"Настройки на {spec.name}"}}, "target_entrypoint_id": widget_id},
        ],
    }
    if spec.capability_plan:
        contract["capability_plan"] = spec.capability_plan.model_dump(mode="json")
    schema_properties = (spec.config_schema or {}).get("properties", {})
    config_defaults = {
        key: value["default"] for key, value in schema_properties.items()
        if isinstance(value, dict) and "default" in value
    }
    manifest = {
        "manifest_version": 2, "module_id": module_id, "name": spec.name, "version": spec.version,
        "description": spec.description, "runtimes": ["ui"], "entrypoints": {"ui": "compiled-ui.json"},
        "compatibility": {"protocol": "1.0", "agent": ">=0.1.0", "core": ">=0.1.0", "architectures": ["any"]},
        "capabilities": {
            "provides": [],
            "consumes": sorted({binding.capability_id for binding in spec.capability_plan.bindings}) if spec.capability_plan else [],
        },
        "permissions": sorted({permission for binding in spec.capability_plan.bindings for permission in binding.permissions}) if spec.capability_plan else [],
        "dependencies": {}, "conflicts": [],
        "configuration_schema": spec.config_schema, "configuration_defaults": config_defaults,
        "health_check": {"type": "json_file", "path": "compiled-ui.json"},
        "registrations": [{"kind": "widget", "registration_id": f"{module_id}.widget", "metadata": {"entrypoint_id": widget_id}}],
    }
    files_text = {
        "manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2),
        "compiled-ui.json": json.dumps(contract, ensure_ascii=False, indent=2),
        "source/frontend/Widget.vue": _compiled_widget_component(spec),
        "source/frontend/WidgetEditor.vue": _compiled_widget_editor(spec),
    }
    if spec.capability_plan:
        files_text["source/frontend/capability-runtime.ts"] = _compiled_capability_runtime_source(spec)
    warnings: List[BuildWarning] = []
    if use_ai and (instructions or spec.goal) and _compiled_widget_has_functional_scaffold(spec):
        warnings.append(BuildWarning(
            code="template.functional",
            message="A tested built-in capability template was used; AI could not replace its runtime behavior.",
        ))
    elif use_ai and (instructions or spec.goal):
        editable_sources = {
            path: content for path, content in files_text.items()
            if path.startswith("source/frontend/") and path != "source/frontend/capability-runtime.ts"
        }
        compiled_instructions = (
            (instructions or spec.goal or "")
            + "\n\nThis is a compiled Vue widget package. Modify the widget and editor source as needed. "
              "Only import from 'vue' or relative source files. The widget receives a reactive config prop; "
              "the editor must emit update:modelValue with the complete new config object."
        )
        updates, ai_warnings = _ai_refine_files(
            spec, compiled_instructions, editable_sources, model,
            ai_provider, groq_api_key, openrouter_api_key
        )
        warnings.extend(ai_warnings)
        files_text.update(updates)
        widget_path = "source/frontend/Widget.vue"
        if files_text[widget_path].strip() == editable_sources[widget_path].strip():
            raise IncompleteAIGenerationError(
                "The AI provider did not implement the widget itself. Nothing was installed. "
                "Try again or make the description more specific."
            )
    buf = BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, content in files_text.items():
            zf.writestr(path, content.encode("utf-8"))
    return (
        BuildReport(extension_id=f"{module_id}_{spec.version}", files=sorted(files_text), warnings=warnings),
        base64.b64encode(buf.getvalue()).decode("ascii"), files_text,
    )


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

    if spec.type == "widget":
        spec = normalize_widget_spec(spec)
        return _build_compiled_widget_zip(
            spec, instructions, use_ai, model, ai_provider, groq_api_key, openrouter_api_key
        )

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

    is_compiled = "compiled-ui.json" in sanitized
    if is_compiled:
        normalized = normalize_widget_spec(spec)
        try:
            manifest = json.loads(sanitized["manifest.json"])
            contract = json.loads(sanitized["compiled-ui.json"])
            manifest.update({
                "name": normalized.name,
                "version": normalized.version,
                "description": normalized.description,
                "configuration_schema": normalized.config_schema,
                "configuration_defaults": {
                    key: value["default"]
                    for key, value in (normalized.config_schema or {}).get("properties", {}).items()
                    if isinstance(value, dict) and "default" in value
                },
                "capabilities": {
                    **(manifest.get("capabilities") or {}),
                    "consumes": sorted({
                        binding.capability_id for binding in normalized.capability_plan.bindings
                    }) if normalized.capability_plan else [],
                },
                "permissions": sorted({
                    permission
                    for binding in normalized.capability_plan.bindings
                    for permission in binding.permissions
                }) if normalized.capability_plan else [],
            })
            contract["version"] = normalized.version
            if normalized.capability_plan:
                contract["capability_plan"] = normalized.capability_plan.model_dump(mode="json")
            else:
                contract.pop("capability_plan", None)
            sanitized["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2)
            sanitized["compiled-ui.json"] = json.dumps(contract, ensure_ascii=False, indent=2)
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            warnings.append(BuildWarning(
                code="package.compiled_metadata_invalid",
                message=f"Compiled package metadata could not be synchronized: {exc}",
            ))
    required = (["manifest.json", "compiled-ui.json"] if is_compiled else [
        "manifest.json", f"backend/{spec.backend_entry}", f"frontend/{spec.frontend_entry}",
    ])
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
    if not is_compiled:
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
