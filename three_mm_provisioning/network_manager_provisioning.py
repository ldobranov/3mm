"""Safe planning boundary for NetworkManager-based Wi-Fi provisioning."""

from __future__ import annotations

from dataclasses import dataclass

from three_mm_provisioning.network_inspection import NetworkInspectionError
from three_mm_provisioning.network_manager import NetworkManagerReadOnlyAdapter


PROVISIONING_OPERATIONS = (
    "enable_wifi",
    "create_open_setup_access_point",
    "expose_captive_setup_portal",
    "stage_target_wifi_profile",
    "activate_target_wifi_profile",
    "verify_connectivity",
    "commit_or_restore_setup_access_point",
)


@dataclass(frozen=True, slots=True)
class NetworkManagerProvisioningPlan:
    """Secret-free description of a future privileged provisioning run."""

    interface: str
    operations: tuple[str, ...] = PROVISIONING_OPERATIONS
    mutation_enabled: bool = False


class NetworkManagerProvisioningPlanner:
    """Build a dry-run plan from privacy-safe NetworkManager inspection."""

    def __init__(
        self,
        inspector: NetworkManagerReadOnlyAdapter,
        interface: str | None = None,
    ) -> None:
        self._inspector = inspector
        self._interface = interface

    @classmethod
    def from_system(
        cls,
        interface: str | None = None,
    ) -> "NetworkManagerProvisioningPlanner":
        return cls(NetworkManagerReadOnlyAdapter.from_system(), interface)

    def dry_run(self) -> NetworkManagerProvisioningPlan:
        status = self._inspector.inspect()
        if not status.running:
            raise NetworkInspectionError("NetworkManager is not running")
        if not status.wifi_hardware_enabled:
            raise NetworkInspectionError("Wi-Fi hardware is disabled")

        wifi_interfaces = tuple(
            device.interface
            for device in status.devices
            if device.device_type == "wifi"
        )
        if self._interface is not None:
            if self._interface not in wifi_interfaces:
                raise NetworkInspectionError(
                    "Requested Wi-Fi interface is unavailable"
                )
            interface = self._interface
        elif len(wifi_interfaces) == 1:
            interface = wifi_interfaces[0]
        elif not wifi_interfaces:
            raise NetworkInspectionError("No Wi-Fi interface is available")
        else:
            raise NetworkInspectionError(
                "Multiple Wi-Fi interfaces require an explicit selection"
            )

        return NetworkManagerProvisioningPlan(interface=interface)
