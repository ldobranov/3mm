import pytest
from fastapi.testclient import TestClient

from agent.config import AgentSettings
from agent.main import create_app
from agent.role import AgentRoleResolver
from setup_service.main import create_app as create_setup_app
from three_mm_protocol import AgentRole
from three_mm_provisioning import (
    FileProvisioningStore,
    MemoryProvisioningStore,
    ProvisioningSnapshot,
    ProvisioningState,
    ProvisioningStoreError,
)
from three_mm_provisioning.mock_network import MockNetworkAdapter


def _provisioned(role: AgentRole) -> ProvisioningSnapshot:
    return ProvisioningSnapshot(
        state=ProvisioningState.PROVISIONED,
        role=role,
        locale="bg-BG",
        device_name="mock-device",
        administrator_name="admin",
    )


def test_completed_provisioning_role_overrides_fallback():
    resolver = AgentRoleResolver(
        MemoryProvisioningStore(_provisioned(AgentRole.STANDALONE))
    )

    assert resolver.resolve(AgentRole.NODE) is AgentRole.STANDALONE


def test_incomplete_provisioning_keeps_explicit_fallback():
    resolver = AgentRoleResolver(
        MemoryProvisioningStore(ProvisioningSnapshot.attempt_started())
    )

    assert resolver.resolve(AgentRole.NODE) is AgentRole.NODE


def test_role_change_across_restart_preserves_device_identity(tmp_path):
    agent_data = tmp_path / "agent"
    provisioning_store = FileProvisioningStore(tmp_path / "setup")
    settings = AgentSettings(
        data_dir=agent_data,
        role=AgentRole.NODE,
        provisioning_data_dir=tmp_path / "setup",
    )

    provisioning_store.save(_provisioned(AgentRole.STANDALONE))
    with TestClient(create_app(settings)) as client:
        first_hello = client.get("/api/v1/agent/hello").json()

    provisioning_store.save(_provisioned(AgentRole.HUB))
    with TestClient(create_app(settings)) as client:
        second_hello = client.get("/api/v1/agent/hello").json()

    assert first_hello["role"] == "standalone"
    assert second_hello["role"] == "hub"
    assert second_hello["device_id"] == first_hello["device_id"]


def test_corrupt_provisioning_state_fails_agent_startup(tmp_path):
    provisioning_store = FileProvisioningStore(tmp_path / "setup")
    provisioning_store.path.parent.mkdir(parents=True)
    provisioning_store.path.write_text('{"state": "broken"}', encoding="utf-8")
    settings = AgentSettings(
        data_dir=tmp_path / "agent",
        provisioning_data_dir=tmp_path / "setup",
    )

    with pytest.raises(ProvisioningStoreError):
        with TestClient(create_app(settings)):
            pass


def test_setup_service_role_is_consumed_by_agent(tmp_path):
    provisioning_store = FileProvisioningStore(tmp_path / "setup")
    setup_payload = {
        "network_name": "private-test-network",
        "passphrase": "not-a-real-secret",
        "locale": "bg-BG",
        "device_name": "standalone-device",
        "administrator_name": "admin",
        "role": "standalone",
    }
    with TestClient(
        create_setup_app(MockNetworkAdapter(), provisioning_store)
    ) as setup_client:
        response = setup_client.post(
            "/api/v1/setup/configure",
            json=setup_payload,
        )

    settings = AgentSettings(
        data_dir=tmp_path / "agent",
        role=AgentRole.NODE,
        provisioning_data_dir=tmp_path / "setup",
    )
    with TestClient(create_app(settings)) as agent_client:
        hello = agent_client.get("/api/v1/agent/hello").json()

    assert response.status_code == 200
    assert hello["role"] == "standalone"
