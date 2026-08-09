from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from three_mm_protocol import (
    PROTOCOL_VERSION,
    AgentHeartbeat,
    AgentHello,
    AgentInventory,
    AgentRole,
)


def valid_hello_data() -> dict:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "agent_version": "0.1.0-dev",
        "device_id": "dev_0123456789abcdef0123456789abcdef",
        "display_name": "test-agent",
        "role": AgentRole.NODE,
        "started_at": datetime.now(UTC),
        "capabilities": (),
    }


def test_protocol_models_reject_unknown_fields():
    data = valid_hello_data()
    data["unexpected"] = "not allowed"

    with pytest.raises(ValidationError):
        AgentHello.model_validate(data)


def test_protocol_models_reject_unknown_versions():
    data = valid_hello_data()
    data["protocol_version"] = "99.0"

    with pytest.raises(ValidationError):
        AgentHello.model_validate(data)


def test_protocol_round_trip_uses_json_safe_values():
    original = AgentHello.model_validate(valid_hello_data())

    restored = AgentHello.model_validate_json(original.model_dump_json())

    assert restored == original


def test_inventory_supports_driver_and_capability_metadata():
    inventory = AgentInventory(
        device_id="dev_0123456789abcdef0123456789abcdef",
        collected_at=datetime.now(UTC),
        hostname="mock-pi",
        model="Raspberry Pi 3 Model B Plus Rev 1.4",
        operating_system="Debian GNU/Linux",
        operating_system_version="13",
        kernel_version="test-kernel",
        architecture="aarch64",
        python_version="3.13.5",
        logical_cpu_count=4,
        memory_total_bytes=1_073_741_824,
        root_total_bytes=32_000_000_000,
        root_free_bytes=24_000_000_000,
        hardware_driver="mock",
        capabilities=("hardware.inventory",),
    )

    assert inventory.hardware_driver == "mock"
    assert inventory.capabilities == ("hardware.inventory",)


def test_heartbeat_rejects_negative_uptime_and_unknown_status():
    payload = {
        "device_id": "dev_0123456789abcdef0123456789abcdef",
        "sent_at": datetime.now(UTC),
        "uptime_seconds": -1,
        "status": "unknown",
    }

    with pytest.raises(ValidationError):
        AgentHeartbeat.model_validate(payload)
