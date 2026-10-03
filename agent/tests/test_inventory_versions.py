from fastapi.testclient import TestClient
import pytest

from agent import __version__
from agent.cli import build_parser
from agent.config import AgentSettings
from agent.hardware import HardwareProfile
from agent.main import create_app
from three_mm_protocol import AgentInventory, DeviceInventoryV2


def test_settings_and_cli_keep_legacy_default_and_allow_explicit_schema2(monkeypatch):
    monkeypatch.delenv("THREE_MM_INVENTORY_SCHEMA_VERSION", raising=False)
    assert AgentSettings.from_env().inventory_schema_version == 1
    assert build_parser().parse_args([]).inventory_schema_version == 1
    monkeypatch.setenv("THREE_MM_INVENTORY_SCHEMA_VERSION", "2")
    assert AgentSettings.from_env().inventory_schema_version == 2
    assert build_parser().parse_args([]).inventory_schema_version == 2
    assert (
        build_parser()
        .parse_args(["--inventory-schema-version", "1"])
        .inventory_schema_version
        == 1
    )


@pytest.mark.parametrize("version", [0, 3, True, "2"])
def test_invalid_setting_is_rejected(tmp_path, version):
    with pytest.raises(ValueError, match="Inventory schema"):
        AgentSettings(data_dir=tmp_path, inventory_schema_version=version)


def test_local_inventory_legacy_and_schema2_share_identity_and_measurements(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("agent.inventory._network_manager_active", lambda: False)
    monkeypatch.setattr("agent.inventory.platform.system", lambda: "Linux")
    settings = AgentSettings(
        data_dir=tmp_path, hardware_profile=HardwareProfile.MOCK_PI3
    )
    with TestClient(create_app(settings)) as client:
        legacy = AgentInventory.model_validate(
            client.get("/api/v1/agent/inventory").json()
        )
        response = client.get("/api/v1/agent/inventory?schema_version=2")
        assert response.status_code == 200, response.text
        neutral = DeviceInventoryV2.model_validate(response.json())
        assert (
            neutral.device_id
            == legacy.device_id
            == client.get("/ready").json()["device_id"]
        )
        assert neutral.platform.family == neutral.platform.system == "linux"
        assert neutral.platform.architecture == legacy.architecture
        assert neutral.platform.model == legacy.model
        assert neutral.runtime.version == __version__
        assert neutral.resources.memory_total_bytes == legacy.memory_total_bytes
        assert neutral.resources.storage_free_bytes == legacy.root_free_bytes
        assert neutral.platform_metadata["network_manager_active"] is False
        assert neutral.platform_metadata["python_version"] == legacy.python_version
        assert client.get("/api/v1/agent/inventory?schema_version=3").status_code == 422
        assert "schema_version" not in client.get("/api/v1/agent/inventory").json()
