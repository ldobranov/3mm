from pathlib import Path

import pytest

from agent.config import AgentSettings
from agent.hardware import HardwareProfile
from three_mm_protocol import AgentRole


def test_agent_settings_are_environment_driven(monkeypatch, tmp_path):
    monkeypatch.setenv("THREE_MM_AGENT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("THREE_MM_AGENT_HOST", "0.0.0.0")
    monkeypatch.setenv("THREE_MM_AGENT_PORT", "9010")
    monkeypatch.setenv("THREE_MM_AGENT_NAME", "mock-pi")
    monkeypatch.setenv("THREE_MM_AGENT_ROLE", "standalone")
    monkeypatch.setenv("THREE_MM_AGENT_HARDWARE_PROFILE", "mock-pi3")
    monkeypatch.setenv("THREE_MM_PROVISIONING_DATA_DIR", str(tmp_path / "setup"))

    settings = AgentSettings.from_env()

    assert settings.data_dir == Path(tmp_path)
    assert settings.host == "0.0.0.0"
    assert settings.port == 9010
    assert settings.display_name == "mock-pi"
    assert settings.role is AgentRole.STANDALONE
    assert settings.hardware_profile is HardwareProfile.MOCK_PI3
    assert settings.provisioning_data_dir == tmp_path / "setup"


@pytest.mark.parametrize("port", [0, 65536])
def test_agent_settings_reject_invalid_ports(tmp_path, port):
    with pytest.raises(ValueError):
        AgentSettings(data_dir=tmp_path, port=port)
