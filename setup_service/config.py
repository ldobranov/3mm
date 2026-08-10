"""Portable setup service configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from three_mm_provisioning import default_provisioning_data_dir


@dataclass(frozen=True, slots=True)
class SetupSettings:
    data_dir: Path = field(default_factory=default_provisioning_data_dir)
    host: str = "127.0.0.1"
    port: int = 8895
    network_helper_socket: Path | None = None

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ValueError("Setup host cannot be empty")
        if not 1 <= self.port <= 65535:
            raise ValueError("Setup port must be between 1 and 65535")

    @classmethod
    def from_env(cls) -> "SetupSettings":
        return cls(
            data_dir=Path(
                os.getenv("THREE_MM_PROVISIONING_DATA_DIR")
                or os.getenv("THREE_MM_SETUP_DATA_DIR")
                or str(default_provisioning_data_dir())
            ),
            host=os.getenv("THREE_MM_SETUP_HOST", "127.0.0.1"),
            port=int(os.getenv("THREE_MM_SETUP_PORT", "8895")),
            network_helper_socket=(
                Path(os.environ["THREE_MM_NETWORK_HELPER_SOCKET"])
                if os.getenv("THREE_MM_NETWORK_HELPER_SOCKET")
                else None
            ),
        )
