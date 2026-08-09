"""Portable Agent configuration with environment overrides."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path

from three_mm_protocol import AgentRole


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

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError("Agent port must be between 1 and 65535")
        if not self.display_name.strip():
            raise ValueError("Agent display name cannot be empty")

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
        )
