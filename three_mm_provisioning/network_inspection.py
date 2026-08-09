"""Privacy-safe network inspection contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class NetworkInspectionError(RuntimeError):
    """The platform network state could not be inspected safely."""


@dataclass(frozen=True, slots=True)
class NetworkDeviceStatus:
    interface: str
    device_type: str
    state: str


@dataclass(frozen=True, slots=True)
class NetworkManagerStatus:
    running: bool
    state: str
    connectivity: str
    wifi_hardware_enabled: bool
    wifi_enabled: bool
    devices: tuple[NetworkDeviceStatus, ...]


class NetworkInspectionAdapter(Protocol):
    def inspect(self) -> NetworkManagerStatus: ...
