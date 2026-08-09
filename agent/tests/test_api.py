from fastapi.testclient import TestClient

from agent.config import AgentSettings
from agent.hardware import HardwareProfile
from agent.main import create_app
from three_mm_protocol import (
    PROTOCOL_VERSION,
    AgentHealth,
    AgentHello,
    AgentInventory,
    AgentRole,
)


def test_agent_exposes_versioned_health_hello_and_inventory(tmp_path):
    settings = AgentSettings(
        data_dir=tmp_path,
        display_name="mock-pi3-01",
        role=AgentRole.NODE,
        hardware_profile=HardwareProfile.MOCK_PI3,
    )

    with TestClient(create_app(settings)) as client:
        health_response = client.get("/health")
        ready_response = client.get("/ready")
        hello_response = client.get("/api/v1/agent/hello")
        inventory_response = client.get("/api/v1/agent/inventory")

    assert health_response.status_code == 200
    health = AgentHealth.model_validate(health_response.json())
    assert health.status == "ok"
    assert health.protocol_version == PROTOCOL_VERSION

    assert ready_response.status_code == 200
    assert ready_response.json() == {
        "status": "ready",
        "device_id": health.device_id,
    }

    hello = AgentHello.model_validate(hello_response.json())
    assert hello.device_id == health.device_id
    assert hello.display_name == "mock-pi3-01"
    assert hello.role is AgentRole.NODE
    assert hello.capabilities == ("hardware.inventory",)

    inventory = AgentInventory.model_validate(inventory_response.json())
    assert inventory.device_id == health.device_id
    assert inventory.root_total_bytes > 0
    assert inventory.python_version
    assert inventory.hardware_driver == "mock"
    assert inventory.model == "Raspberry Pi 3 Model B Plus Rev 1.4"
    assert inventory.architecture == "aarch64"
    assert inventory.capabilities == hello.capabilities

    serialized_inventory = inventory_response.json()
    assert "machine_id" not in serialized_inventory
    assert "boot_id" not in serialized_inventory
    assert "ip_address" not in serialized_inventory


def test_restart_preserves_device_identity(tmp_path):
    settings = AgentSettings(data_dir=tmp_path)

    with TestClient(create_app(settings)) as client:
        first_device_id = client.get("/ready").json()["device_id"]

    with TestClient(create_app(settings)) as client:
        second_device_id = client.get("/ready").json()["device_id"]

    assert second_device_id == first_device_id


def test_two_agents_have_independent_identities(tmp_path):
    first_settings = AgentSettings(
        data_dir=tmp_path / "agent-1",
        port=8890,
        hardware_profile=HardwareProfile.MOCK_PI3,
    )
    second_settings = AgentSettings(
        data_dir=tmp_path / "agent-2",
        port=8891,
        hardware_profile=HardwareProfile.MOCK_ZERO2,
    )

    with (
        TestClient(create_app(first_settings)) as first_client,
        TestClient(create_app(second_settings)) as second_client,
    ):
        first_id = first_client.get("/ready").json()["device_id"]
        second_id = second_client.get("/ready").json()["device_id"]
        first_inventory = first_client.get("/api/v1/agent/inventory").json()
        second_inventory = second_client.get("/api/v1/agent/inventory").json()

    assert first_id != second_id
    assert first_inventory["model"] != second_inventory["model"]
    assert (
        first_inventory["memory_total_bytes"] > second_inventory["memory_total_bytes"]
    )
