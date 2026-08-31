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
    monkeypatch.setenv("THREE_MM_GPIO_DRIVER", "gpiod")
    monkeypatch.setenv("THREE_MM_GPIO_CHIP", "/dev/gpiochip4")
    monkeypatch.setenv("THREE_MM_GPIO_INPUTS", "gpio.input.1:17,input.door:22")
    monkeypatch.setenv("THREE_MM_GPIO_OUTPUTS", "gpio.output.1:27")
    monkeypatch.setenv("THREE_MM_IDENTIFIER_DRIVER", "mock")
    monkeypatch.setenv("THREE_MM_IDENTIFIER_READER_ID", "reader.usb.1")

    settings = AgentSettings.from_env()

    assert settings.data_dir == Path(tmp_path)
    assert settings.host == "0.0.0.0"
    assert settings.port == 9010
    assert settings.display_name == "mock-pi"
    assert settings.role is AgentRole.STANDALONE
    assert settings.hardware_profile is HardwareProfile.MOCK_PI3
    assert settings.provisioning_data_dir == tmp_path / "setup"
    assert settings.gpio_driver == "gpiod"
    assert settings.gpio_chip == "/dev/gpiochip4"
    assert settings.gpio_inputs == {"gpio.input.1": 17, "input.door": 22}
    assert settings.gpio_outputs == {"gpio.output.1": 27}
    assert settings.identifier_driver == "mock"
    assert settings.identifier_reader_id == "reader.usb.1"


@pytest.mark.parametrize("port", [0, 65536])
def test_agent_settings_reject_invalid_ports(tmp_path, port):
    with pytest.raises(ValueError):
        AgentSettings(data_dir=tmp_path, port=port)


def test_gpiod_settings_require_an_input_or_output_mapping(tmp_path):
    with pytest.raises(ValueError, match="at least one input or output"):
        AgentSettings(data_dir=tmp_path, gpio_driver="gpiod")


def test_gpiod_settings_allow_an_output_only_device(tmp_path):
    settings = AgentSettings(
        data_dir=tmp_path,
        gpio_driver="gpiod",
        gpio_outputs={"gpio.output.1": 27},
    )

    assert settings.gpio_inputs is None
    assert settings.gpio_outputs == {"gpio.output.1": 27}


def test_gpio_environment_mapping_is_validated(monkeypatch):
    monkeypatch.setenv("THREE_MM_GPIO_INPUTS", "gpio.input.1")

    with pytest.raises(ValueError, match="capability:BCM-line"):
        AgentSettings.from_env()
