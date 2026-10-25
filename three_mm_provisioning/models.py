"""Framework-independent provisioning domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from three_mm_protocol import AgentRole


class ProvisioningState(str, Enum):
    UNPROVISIONED = "unprovisioned"
    SETUP = "setup"
    APPLYING_NETWORK = "applying_network"
    VERIFYING_NETWORK = "verifying_network"
    PROVISIONED = "provisioned"


class NetworkMode(str, Enum):
    PRESERVE = "preserve"
    WIFI = "wifi"
    LOCAL = "local"


@dataclass(frozen=True, slots=True)
class NetworkCredentials:
    network_name: str = field(repr=False)
    passphrase: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.network_name.strip():
            raise ValueError("Network name cannot be empty")


@dataclass(frozen=True, slots=True)
class ProvisioningRequest:
    network: NetworkCredentials | None = field(repr=False)
    locale: str
    device_name: str
    administrator_name: str
    role: AgentRole
    hub_endpoint: str | None = None
    network_mode: NetworkMode = NetworkMode.WIFI
    network_interface: str | None = None

    def __post_init__(self) -> None:
        if self.network_mode is NetworkMode.WIFI and self.network is None:
            raise ValueError("Wi-Fi credentials are required")
        if self.network_mode is not NetworkMode.WIFI and (self.network or self.network_interface):
            raise ValueError("Host networking does not accept Wi-Fi settings")
        if self.network_mode is NetworkMode.LOCAL and self.role is not AgentRole.STANDALONE:
            raise ValueError("Local operation requires the standalone role")
        for label, value in (
            ("Locale", self.locale),
            ("Device name", self.device_name),
            ("Administrator name", self.administrator_name),
        ):
            if not value.strip():
                raise ValueError(f"{label} cannot be empty")


@dataclass(frozen=True, slots=True)
class ProvisioningResult:
    state: ProvisioningState
    role: AgentRole | None
    recovery_required: bool
    error_code: str | None = None
