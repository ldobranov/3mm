"""Generic, validated per-installation configuration for application extensions."""

from __future__ import annotations

import json
import re
from typing import Any

from three_mm_protocol import ApplicationExtensionV1


MAX_CONFIGURATION_BYTES = 32 * 1024


class ApplicationConfigurationError(ValueError):
    """Raised when installation configuration does not match its manifest."""


def device_configuration_keys(definition: ApplicationExtensionV1) -> tuple[str, ...]:
    """Return configuration keys that scope declared event subscriptions to devices."""
    return tuple(
        sorted(
            {
                subscription.device_scope_config_key
                for subscription in definition.event_subscriptions
            }
        )
    )


def _matches_type(value: object, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "null":
        return value is None
    return False


def _validate_value(value: object, schema: dict[str, Any], path: str) -> None:
    expected = schema.get("type")
    if not isinstance(expected, str) or not _matches_type(value, expected):
        raise ApplicationConfigurationError(f"{path} has an invalid value type")
    if "enum" in schema and value not in schema["enum"]:
        raise ApplicationConfigurationError(f"{path} is not an allowed value")
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            raise ApplicationConfigurationError(f"{path} is too short")
        if len(value) > int(schema.get("maxLength", MAX_CONFIGURATION_BYTES)):
            raise ApplicationConfigurationError(f"{path} is too long")
        pattern = schema.get("pattern")
        if isinstance(pattern, str):
            try:
                matches = re.search(pattern, value) is not None
            except re.error as exc:
                raise ApplicationConfigurationError(
                    f"{path} declares an invalid pattern"
                ) from exc
            if not matches:
                raise ApplicationConfigurationError(f"{path} has an invalid format")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ApplicationConfigurationError(f"{path} is below its minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ApplicationConfigurationError(f"{path} is above its maximum")
    elif isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_value(item, item_schema, f"{path}[{index}]")
    elif isinstance(value, dict):
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise ApplicationConfigurationError(f"{path} has an invalid schema")
        if schema.get("additionalProperties") is False:
            unknown = set(value) - set(properties)
            if unknown:
                raise ApplicationConfigurationError(f"{path} contains unknown fields")
        for key in schema.get("required", []):
            if key not in value:
                raise ApplicationConfigurationError(f"{path}.{key} is required")
        for key, item in value.items():
            item_schema = properties.get(key)
            if isinstance(item_schema, dict):
                _validate_value(item, item_schema, f"{path}.{key}")


def resolve_application_configuration(
    schema: dict[str, Any],
    defaults: dict[str, Any],
    definition: ApplicationExtensionV1,
    *,
    existing: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge defaults, saved values and explicit overrides, then validate them."""
    properties = schema.get("properties")
    if (
        schema.get("type") != "object"
        or schema.get("additionalProperties") is not False
        or not isinstance(properties, dict)
    ):
        raise ApplicationConfigurationError(
            "Application configuration schema is invalid"
        )
    result = dict(defaults)
    result.update(existing or {})
    result.update(overrides or {})
    required = set(schema.get("required", [])) | set(
        device_configuration_keys(definition)
    )
    missing = sorted(key for key in required if key not in result)
    if missing:
        raise ApplicationConfigurationError(
            "Application configuration is required: " + ", ".join(missing)
        )
    unknown = sorted(set(result) - set(properties))
    if unknown:
        raise ApplicationConfigurationError(
            "Application configuration contains undeclared keys"
        )
    for key, value in result.items():
        field_schema = properties.get(key)
        if not isinstance(field_schema, dict):
            raise ApplicationConfigurationError(
                f"Application configuration field {key} has an invalid schema"
            )
        try:
            _validate_value(value, field_schema, key)
        except ApplicationConfigurationError:
            raise
        except (TypeError, ValueError) as exc:
            raise ApplicationConfigurationError(
                f"Application configuration field {key} has an invalid schema"
            ) from exc
    try:
        encoded = json.dumps(result, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ApplicationConfigurationError(
            "Application configuration is not valid JSON"
        ) from exc
    if len(encoded.encode("utf-8")) > MAX_CONFIGURATION_BYTES:
        raise ApplicationConfigurationError("Application configuration is too large")
    return result
