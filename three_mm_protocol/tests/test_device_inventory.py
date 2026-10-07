"""C1 inventory contracts: explicit versioning, no compulsory Linux fields."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from three_mm_protocol import AgentInventory, DeviceInventoryV2
from three_mm_protocol.device_inventory import inventory_value, normalized_inventory


def embedded_inventory(device_id="dev_" + "a" * 32):
    return {
        "schema_version": 2,
        "device_id": device_id,
        "collected_at": datetime.now(UTC).isoformat(),
        "platform": {
            "family": "embedded",
            "system": "mock-embedded",
            "model": "Test board",
        },
        "runtime": {"name": "3mm-embedded-test", "version": "0.1.0"},
        "resources": {"memory_total_bytes": 409600, "flash_total_bytes": 4194304},
        "capabilities": ["gpio.digital.control"],
    }


def test_embedded_inventory_needs_no_linux_values():
    value = DeviceInventoryV2.model_validate(embedded_inventory())
    serialized = value.model_dump(mode="json")
    assert value.protocol_version == "1.0"
    assert value.network.hostname is None
    assert value.resources.storage_total_bytes is None
    assert value.platform.architecture is None
    assert value.platform_metadata == {}
    assert "python_version" not in serialized
    with pytest.raises(ValidationError):
        AgentInventory.model_validate(serialized)


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 1},
        {"schema_version": 3},
        {"schema_version": "2"},
        {"schema_version": True},
        {"protocol_version": "2.0"},
        {"collected_at": "2026-10-02T12:00:00"},
        {"resources": {"memory_total_bytes": True}},
        {"resources": {"flash_total_bytes": 100, "flash_free_bytes": 101}},
        {"resources": {"storage_free_bytes": -1}},
        {"capabilities": ["gpio.digital.control", "gpio.digital.control"]},
        {"capabilities": [" "]},
        {"capabilities": ["a" * 161]},
        {"capabilities": [f"cap.{i}" for i in range(129)]},
        {"platform_metadata": {"note": "a" * 513}},
        {"platform_metadata": {f"key{i}": "a" * 512 for i in range(20)}},
        {"platform_metadata": {"deep": {"a": {"b": {"c": {"d": {"e": 1}}}}}}},
        {"platform_metadata": {"invalid": float("nan")}},
        {"hostname": "not-a-v2-top-level-field"},
    ],
)
def test_invalid_or_unbounded_inventory_is_rejected(changes):
    with pytest.raises(ValidationError):
        DeviceInventoryV2.model_validate({**embedded_inventory(), **changes})


def test_schema_tag_is_required_and_unknown_sections_are_rejected():
    payload = embedded_inventory()
    del payload["schema_version"]
    with pytest.raises(ValidationError):
        DeviceInventoryV2.model_validate(payload)
    payload = embedded_inventory()
    payload["platform"]["vendor_special_case"] = True
    with pytest.raises(ValidationError):
        DeviceInventoryV2.model_validate(payload)


def test_legacy_views_preserve_raw_data_and_unknowns():
    raw = {
        "hostname": "old-node",
        "architecture": "armv6l",
        "root_free_bytes": 0,
        "network_manager_active": False,
    }
    original = deepcopy(raw)
    view = normalized_inventory(raw)
    assert raw == original
    assert view["schema_version"] == 2
    assert view["platform"]["family"] == "legacy"
    assert view["runtime"]["version"] is None
    assert view["device_id"] is None
    assert view["resources"]["storage_free_bytes"] == 0
    assert view["resources"]["memory_total_bytes"] is None
    assert view["platform_metadata"]["network_manager_active"] is False
    assert (
        inventory_value(raw, "hostname")
        == inventory_value(view, "hostname")
        == "old-node"
    )
    assert inventory_value(view, "root_free_bytes") == 0
    assert normalized_inventory(None) is None
    assert normalized_inventory({"schema_version": 9}) is None


def test_resource_access_is_not_platform_specific():
    value = DeviceInventoryV2.model_validate(embedded_inventory()).model_dump(
        mode="json"
    )
    assert inventory_value(value, "memory_total_bytes") == 409600
    assert inventory_value(value, "root_total_bytes") is None
    assert inventory_value(value, "architecture") is None
