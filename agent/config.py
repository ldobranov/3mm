"""Portable Agent configuration with environment overrides."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path

from agent.hardware import HardwareProfile
from three_mm_protocol import AgentRole
from three_mm_provisioning import default_provisioning_data_dir


def default_data_dir() -> Path:
    data_home = os.getenv("XDG_DATA_HOME")
    if data_home:
        return Path(data_home) / "3mm" / "agent"
    return Path.home() / ".local" / "share" / "3mm" / "agent"


def _gpio_lines_from_env(name: str) -> dict[str, int]:
    value = os.getenv(name, "").strip()
    if not value:
        return {}
    result: dict[str, int] = {}
    for item in value.split(","):
        capability_id, separator, line_text = item.strip().partition(":")
        if not separator or not capability_id or not line_text:
            raise ValueError(f"{name} must contain capability:BCM-line pairs")
        line = int(line_text)
        if line < 0:
            raise ValueError(f"{name} GPIO lines cannot be negative")
        result[capability_id] = line
    return result


@dataclass(frozen=True, slots=True)
class AgentSettings:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8890
    display_name: str = "3mm-agent"
    role: AgentRole = AgentRole.NODE
    hardware_profile: HardwareProfile = HardwareProfile.NATIVE
    provisioning_data_dir: Path | None = None
    core_url: str | None = None
    heartbeat_interval_seconds: int = 30
    gpio_driver: str = "mock"
    gpio_chip: str = "/dev/gpiochip0"
    gpio_inputs: dict[str, int] | None = None
    gpio_outputs: dict[str, int] | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError("Agent port must be between 1 and 65535")
        if not self.display_name.strip():
            raise ValueError("Agent display name cannot be empty")
        if self.heartbeat_interval_seconds < 5:
            raise ValueError("Heartbeat interval must be at least 5 seconds")
        if self.gpio_driver not in {"mock", "gpiod"}:
            raise ValueError("GPIO driver must be 'mock' or 'gpiod'")
        if self.gpio_driver == "gpiod" and not self.gpio_inputs:
            raise ValueError("The gpiod driver requires at least one input mapping")

    @classmethod
    def from_env(cls) -> "AgentSettings":
        return cls(
            data_dir=Path(
                os.getenv("THREE_MM_AGENT_DATA_DIR", str(default_data_dir()))
            ),
            host=os.getenv("THREE_MM_AGENT_HOST", "127.0.0.1"),
            port=int(os.getenv("THREE_MM_AGENT_PORT", "8890")),
            display_name=os.getenv(
                "THREE_MM_AGENT_NAME", socket.gethostname() or "3mm-agent"
            ),
            role=AgentRole(os.getenv("THREE_MM_AGENT_ROLE", AgentRole.NODE.value)),
            hardware_profile=HardwareProfile(
                os.getenv(
                    "THREE_MM_AGENT_HARDWARE_PROFILE",
                    HardwareProfile.NATIVE.value,
                )
            ),
            provisioning_data_dir=Path(
                os.getenv("THREE_MM_PROVISIONING_DATA_DIR")
                or os.getenv("THREE_MM_SETUP_DATA_DIR")
                or str(default_provisioning_data_dir())
            ),
            core_url=os.getenv("THREE_MM_CORE_URL") or None,
            heartbeat_interval_seconds=int(
                os.getenv("THREE_MM_HEARTBEAT_INTERVAL_SECONDS", "30")
            ),
            gpio_driver=os.getenv("THREE_MM_GPIO_DRIVER", "mock").strip().lower(),
            gpio_chip=os.getenv("THREE_MM_GPIO_CHIP", "/dev/gpiochip0").strip(),
            gpio_inputs=_gpio_lines_from_env("THREE_MM_GPIO_INPUTS"),
            gpio_outputs=_gpio_lines_from_env("THREE_MM_GPIO_OUTPUTS"),
        )
