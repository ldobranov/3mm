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

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError("Agent port must be between 1 and 65535")
        if not self.display_name.strip():
            raise ValueError("Agent display name cannot be empty")
        if self.heartbeat_interval_seconds < 5:
            raise ValueError("Heartbeat interval must be at least 5 seconds")

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
        )
