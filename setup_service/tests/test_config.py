from pathlib import Path

import pytest

from setup_service.config import SetupSettings


def test_setup_settings_are_environment_driven(monkeypatch):
    monkeypatch.setenv("THREE_MM_PROVISIONING_DATA_DIR", "test-data")
    monkeypatch.setenv("THREE_MM_SETUP_HOST", "0.0.0.0")
    monkeypatch.setenv("THREE_MM_SETUP_PORT", "9015")
    monkeypatch.setenv("THREE_MM_NETWORK_HELPER_SOCKET", "helper.sock")

    settings = SetupSettings.from_env()

    assert settings.data_dir == Path("test-data")
    assert settings.host == "0.0.0.0"
    assert settings.port == 9015
    assert settings.network_helper_socket == Path("helper.sock")


@pytest.mark.parametrize("port", [0, 65536])
def test_setup_settings_reject_invalid_ports(port):
    with pytest.raises(ValueError):
        SetupSettings(port=port)


def test_legacy_setup_data_dir_remains_supported(monkeypatch):
    monkeypatch.delenv("THREE_MM_PROVISIONING_DATA_DIR", raising=False)
    monkeypatch.setenv("THREE_MM_SETUP_DATA_DIR", "legacy-test-data")

    assert SetupSettings.from_env().data_dir == Path("legacy-test-data")
