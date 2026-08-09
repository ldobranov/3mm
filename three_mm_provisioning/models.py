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


@dataclass(frozen=True, slots=True)
class NetworkCredentials:
    network_name: str = field(repr=False)
    passphrase: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.network_name.strip():
            raise ValueError("Network name cannot be empty")


@dataclass(frozen=True, slots=True)
class ProvisioningRequest:
    network: NetworkCredentials = field(repr=False)
    locale: str
    device_name: str
    administrator_name: str
    role: AgentRole
    hub_endpoint: str | None = None

    def __post_init__(self) -> None:
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
