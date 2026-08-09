"""Privacy-conscious local hardware and operating-system inventory."""

from __future__ import annotations

import platform
import shutil
import socket
from datetime import UTC, datetime
from pathlib import Path

from agent.hardware import HardwareInventoryDriver, LinuxHardwareDriver
from three_mm_protocol import AgentInventory
from three_mm_provisioning import (
    NetworkInspectionError,
    NetworkManagerReadOnlyAdapter,
)


def _read_os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values

    for line in lines:
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    return values


def _network_manager_active() -> bool | None:
    try:
        return NetworkManagerReadOnlyAdapter.from_system().inspect().running
    except NetworkInspectionError:
        return None


def collect_inventory(
    device_id: str,
    hardware: HardwareInventoryDriver | None = None,
) -> AgentInventory:
    hardware_snapshot = (hardware or LinuxHardwareDriver()).collect()
    os_release = _read_os_release()
    root_usage = shutil.disk_usage("/")

    return AgentInventory(
        device_id=device_id,
        collected_at=datetime.now(UTC),
        hostname=socket.gethostname(),
        model=hardware_snapshot.model,
        operating_system=os_release.get("NAME", platform.system()),
        operating_system_version=os_release.get("VERSION_ID", platform.version()),
        kernel_version=platform.release(),
        architecture=hardware_snapshot.architecture,
        python_version=platform.python_version(),
        logical_cpu_count=hardware_snapshot.logical_cpu_count,
        memory_total_bytes=hardware_snapshot.memory_total_bytes,
        root_total_bytes=root_usage.total,
        root_free_bytes=root_usage.free,
        network_manager_active=_network_manager_active(),
        hardware_driver=hardware_snapshot.driver_id,
        capabilities=hardware_snapshot.capabilities,
    )
