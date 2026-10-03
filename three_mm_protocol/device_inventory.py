"""Inventory schema 2 over the unchanged device protocol 1.0.

Legacy reports remain a separate wire contract. Views/field accessors provide
compatibility without inventing Linux properties for other runtimes.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    Field,
    JsonValue,
    StrictBool,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)

from three_mm_protocol.models import AgentInventory, ProtocolModel

MAX_INVENTORY_BYTES = 64 * 1024
ByteCount = Annotated[StrictInt, Field(ge=0, le=2**63 - 1)]
PositiveCount = Annotated[StrictInt, Field(ge=1, le=2**63 - 1)]
CapabilityId = Annotated[str, Field(min_length=1, max_length=160)]


class InventoryPlatformV2(ProtocolModel):
    family: str = Field(min_length=1, max_length=64)
    system: str = Field(min_length=1, max_length=128)
    model: str | None = Field(default=None, max_length=255)
    version: str | None = Field(default=None, max_length=128)
    architecture: str | None = Field(default=None, max_length=64)


class InventoryRuntimeV2(ProtocolModel):
    name: str = Field(min_length=1, max_length=100)
    version: str | None = Field(default=None, max_length=64)


class InventoryResourcesV2(ProtocolModel):
    logical_cpu_count: PositiveCount | None = None
    memory_total_bytes: PositiveCount | None = None
    memory_free_bytes: ByteCount | None = None
    storage_total_bytes: PositiveCount | None = None
    storage_free_bytes: ByteCount | None = None
    flash_total_bytes: PositiveCount | None = None
    flash_free_bytes: ByteCount | None = None

    @model_validator(mode="after")
    def free_does_not_exceed_total(self):
        for resource in ("memory", "storage", "flash"):
            total = getattr(self, f"{resource}_total_bytes")
            free = getattr(self, f"{resource}_free_bytes")
            if total is not None and free is not None and free > total:
                raise ValueError(f"{resource} free bytes exceed total")
        return self


class InventoryNetworkV2(ProtocolModel):
    hostname: str | None = Field(default=None, min_length=1, max_length=255)
    connected: StrictBool | None = None


class DeviceInventoryV2(ProtocolModel):
    schema_version: Literal[2]
    protocol_version: Literal["1.0"] = "1.0"
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    collected_at: datetime
    platform: InventoryPlatformV2
    runtime: InventoryRuntimeV2
    resources: InventoryResourcesV2 = Field(default_factory=InventoryResourcesV2)
    network: InventoryNetworkV2 = Field(default_factory=InventoryNetworkV2)
    capabilities: tuple[CapabilityId, ...] = Field(default=(), max_length=128)
    platform_metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_schema(cls, value):
        if type(value) is not int or value != 2:
            raise ValueError("Inventory schema version must be integer 2")
        return value

    @field_validator("collected_at")
    @classmethod
    def aware_timestamp(cls, value):
        if value.utcoffset() is None:
            raise ValueError("Inventory collection time requires a timezone")
        return value

    @field_validator("capabilities")
    @classmethod
    def unique_capabilities(cls, value):
        if len(value) != len(set(value)) or any(not item.strip() for item in value):
            raise ValueError("Inventory capabilities must be unique and nonempty")
        return value

    @field_validator("platform_metadata")
    @classmethod
    def bounded_metadata(cls, value):
        def visit(item, depth=0):
            if depth > 4:
                raise ValueError("Inventory metadata nesting exceeds four levels")
            if isinstance(item, dict):
                if len(item) > 32 or any(len(key) > 96 for key in item):
                    raise ValueError("Inventory metadata object is too large")
                for child in item.values():
                    visit(child, depth + 1)
            elif isinstance(item, list):
                if len(item) > 32:
                    raise ValueError("Inventory metadata array is too large")
                for child in item:
                    visit(child, depth + 1)
            elif isinstance(item, str) and len(item) > 512:
                raise ValueError("Inventory metadata string is too large")

        visit(value)
        if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode()) > 8192:
            raise ValueError("Inventory metadata exceeds 8192 bytes")
        return value

    @model_validator(mode="after")
    def bounded_report(self):
        if len(self.model_dump_json().encode()) > MAX_INVENTORY_BYTES:
            raise ValueError("Inventory report exceeds 64 KiB")
        return self


_FIELD_PATHS = {
    "hostname": ("network", "hostname"),
    "model": ("platform", "model"),
    "architecture": ("platform", "architecture"),
    "operating_system": ("platform", "system"),
    "operating_system_version": ("platform", "version"),
    "logical_cpu_count": ("resources", "logical_cpu_count"),
    "memory_total_bytes": ("resources", "memory_total_bytes"),
    "root_total_bytes": ("resources", "storage_total_bytes"),
    "root_free_bytes": ("resources", "storage_free_bytes"),
}


def inventory_value(data: dict | None, field: str):
    """Legacy semantic field access; unavailable measurements stay unknown."""
    if not isinstance(data, dict):
        return None
    if "schema_version" not in data:
        return data.get(field)
    if type(data.get("schema_version")) is not int or data["schema_version"] != 2:
        return None
    if field not in _FIELD_PATHS:
        return data.get(field)
    section, key = _FIELD_PATHS[field]
    values = data.get(section)
    return values.get(key) if isinstance(values, dict) else None


def normalized_inventory(data: dict | None) -> dict | None:
    """Read-only schema-2 view, including incomplete historic legacy snapshots.

    These views are not fresh reports: unknown identity/time can remain null.
    Raw stored reports are never rewritten, truncated or migrated.
    """
    if not isinstance(data, dict):
        return None
    if "schema_version" in data:
        try:
            return DeviceInventoryV2.model_validate(data).model_dump(mode="json")
        except ValidationError:
            return None

    def text(key, limit=255):
        value = data.get(key)
        return value[:limit] if isinstance(value, str) and value else None

    def number(key, minimum=0):
        value = data.get(key)
        return value if type(value) is int and minimum <= value <= 2**63 - 1 else None

    metadata = {
        key: text(key, 512)
        for key in ("kernel_version", "python_version", "hardware_driver")
    }
    active = data.get("network_manager_active")
    metadata["network_manager_active"] = active if type(active) is bool else None
    capabilities = data.get("capabilities")
    capabilities = (
        list(
            dict.fromkeys(
                item
                for item in capabilities
                if isinstance(item, str) and 0 < len(item) <= 160
            )
        )[:128]
        if isinstance(capabilities, (list, tuple))
        else []
    )
    return {
        "schema_version": 2,
        "protocol_version": data.get("protocol_version", "1.0"),
        "device_id": data.get("device_id"),
        "collected_at": data.get("collected_at"),
        "platform": {
            "family": "legacy",
            "system": text("operating_system", 128) or "unknown",
            "model": text("model"),
            "version": text("operating_system_version", 128),
            "architecture": text("architecture", 64),
        },
        "runtime": {"name": "3mm-agent", "version": None},
        "resources": {
            "logical_cpu_count": number("logical_cpu_count", 1),
            "memory_total_bytes": number("memory_total_bytes", 1),
            "storage_total_bytes": number("root_total_bytes", 1),
            "storage_free_bytes": number("root_free_bytes"),
        },
        "network": {"hostname": text("hostname"), "connected": None},
        "capabilities": capabilities,
        "platform_metadata": metadata,
    }


def upgrade_agent_inventory(
    report: AgentInventory,
    *,
    runtime_version: str,
    platform_family: str,
    platform_system: str,
) -> DeviceInventoryV2:
    """Explicit legacy Linux/runtime adapter, not a Core platform decision."""
    value = normalized_inventory(report.model_dump(mode="json"))
    value["platform"].update(family=platform_family, system=platform_system)
    value["platform_metadata"]["operating_system"] = report.operating_system[:512]
    value["runtime"]["version"] = runtime_version
    return DeviceInventoryV2.model_validate(value)
