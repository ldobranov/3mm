from __future__ import annotations

import re

from backend.schemas.ai_extension_builder import ExtensionSpec


def compiled_module_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "widget"
    return f"org.3mm.generated.{slug}"


def normalize_widget_spec(spec: ExtensionSpec) -> ExtensionSpec:
    """Normalize common widget settings into the typed compiled-UI contract."""
    normalized = spec.model_copy(deep=True)
    schema = normalized.config_schema or {}
    original = schema.get("properties", {}) if isinstance(schema, dict) else {}
    properties = dict(original) if isinstance(original, dict) else {}
    intent = f"{normalized.description} {normalized.goal or ''}".casefold()

    if normalized.capability_plan:
        kind_schema = {
            "text": {"type": "string"},
            "number": {"type": "number"},
            "boolean": {"type": "boolean"},
            "select": {"type": "string"},
            "timezone": {"type": "string", "format": "timezone"},
            "color": {"type": "string", "format": "color"},
            "device": {"type": "string", "format": "device"},
            "capability_channel": {"type": "string", "format": "capability-channel"},
        }
        for setting in normalized.capability_plan.settings:
            item = {**kind_schema[setting.kind], "title": setting.label}
            if setting.default is not None:
                item["default"] = setting.default
            if setting.options:
                item["enum"] = list(setting.options)
            properties[setting.key] = item

    timezone_keys = [
        key for key, item in properties.items()
        if "timezone" in key.casefold()
        or (isinstance(item, dict) and "timezone" in str(item.get("title", "")).casefold())
    ]
    if timezone_keys or any(term in intent for term in ("timezone", "time zone", "часова зона")):
        for key in timezone_keys:
            properties.pop(key, None)
        properties["timezone"] = {
            "type": "string", "title": "Timezone", "format": "timezone", "default": "UTC",
        }

    mode_keys = [key for key in properties if key.casefold() in {"mode", "displaymode", "display_mode"}]
    if mode_keys or ("digital" in intent and "analog" in intent):
        for key in mode_keys:
            properties.pop(key, None)
        properties["displayMode"] = {
            "type": "string", "title": "Display", "enum": ["digital", "analog"], "default": "digital",
        }

    hour_keys = [key for key in properties if key.casefold() in {"ampm", "hourformat", "hour_format"}]
    if hour_keys or any(term in intent for term in ("12/24", "am/pm", "ap or pm", "12 hour", "24 hour")):
        for key in hour_keys:
            properties.pop(key, None)
        properties["hourFormat"] = {
            "type": "string", "title": "Hour format", "enum": ["24", "12"], "default": "24",
        }

    normalized.config_schema = {"type": "object", "properties": properties} if properties else {}
    return normalized
