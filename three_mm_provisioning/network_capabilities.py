"""Discover usable managed adapters. No radio, profile or route changes."""

from __future__ import annotations

import re

from three_mm_runtime.install_profile import NetworkBackend, read_network_backend
from three_mm_provisioning.network_manager import NetworkManagerReadOnlyAdapter

INTERFACE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,14}\Z")


def managed_interfaces(*, adapter=None, status=None) -> list[dict]:
    if read_network_backend() is not NetworkBackend.NETWORK_MANAGER:
        return []
    try:
        adapter = adapter or NetworkManagerReadOnlyAdapter.from_system()
        status = status if status is not None else adapter.inspect()
        if not status.running or not status.wifi_enabled or not status.wifi_hardware_enabled:
            return []
        items = []
        for device in status.devices:
            if (device.device_type != "wifi" or not INTERFACE.fullmatch(device.interface)
                    or device.state in {"unmanaged", "unavailable"}):
                continue
            try:
                ap = adapter._execute("-g", "WIFI-PROPERTIES.AP", "device", "show", device.interface).strip() == "yes"
            except Exception:
                ap = False
            items.append({"name": device.interface, "access_point": ap})
        return items
    except Exception:
        return []


def require_interface(interface: str) -> None:
    if not any(item["name"] == interface for item in managed_interfaces()):
        from three_mm_provisioning.network import NetworkAdapterError
        raise NetworkAdapterError("Managed Wi-Fi adapter unavailable")


def setup_interface(preferred: str | None = None) -> str:
    """Select the first-setup AP adapter after opting into managed networking.

    Its existing Wi-Fi connection may carry the installation's SSH session.
    Provisioned devices never enter this path; recovery uses its own transaction.
    """
    candidates = [item["name"] for item in managed_interfaces() if item["access_point"]]
    if preferred in candidates:
        return preferred
    if preferred is None and len(candidates) == 1:
        return candidates[0]
    raise RuntimeError("Select an available AP-capable adapter using THREE_MM_SETUP_INTERFACE")
