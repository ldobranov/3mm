"""Privacy-conscious local hardware and operating-system inventory."""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from three_mm_protocol import AgentInventory


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


def _read_device_model(path: Path = Path("/proc/device-tree/model")) -> str | None:
    try:
        model = path.read_bytes().rstrip(b"\x00").decode("utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return model or None


def _memory_total_bytes() -> int | None:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (OSError, ValueError):
        return None


def _network_manager_active() -> bool | None:
    executable = shutil.which("nmcli")
    if executable is None:
        return None
    try:
        result = subprocess.run(
            [executable, "-t", "-f", "RUNNING", "general"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip().lower() == "running"


def collect_inventory(device_id: str) -> AgentInventory:
    os_release = _read_os_release()
    root_usage = shutil.disk_usage("/")

    return AgentInventory(
        device_id=device_id,
        collected_at=datetime.now(UTC),
        hostname=socket.gethostname(),
        model=_read_device_model(),
        operating_system=os_release.get("NAME", platform.system()),
        operating_system_version=os_release.get("VERSION_ID", platform.version()),
        kernel_version=platform.release(),
        architecture=platform.machine(),
        python_version=platform.python_version(),
        logical_cpu_count=os.cpu_count(),
        memory_total_bytes=_memory_total_bytes(),
        root_total_bytes=root_usage.total,
        root_free_bytes=root_usage.free,
        network_manager_active=_network_manager_active(),
    )
