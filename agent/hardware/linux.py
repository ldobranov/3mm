"""Generic Linux/host hardware inventory driver."""

from __future__ import annotations

import os
import platform
from pathlib import Path

from agent.hardware.base import HardwareSnapshot


def _read_device_model(path: Path = Path("/proc/device-tree/model")) -> str | None:
    try:
        model = path.read_bytes().rstrip(b"\x00").decode("utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return model or None


def _memory_total_bytes() -> int | None:
    sysconf = getattr(os, "sysconf", None)
    if sysconf is None:
        return None
    try:
        return sysconf("SC_PAGE_SIZE") * sysconf("SC_PHYS_PAGES")
    except (OSError, ValueError):
        return None


class LinuxHardwareDriver:
    def collect(self) -> HardwareSnapshot:
        return HardwareSnapshot(
            driver_id="linux",
            model=_read_device_model(),
            architecture=platform.machine() or "unknown",
            logical_cpu_count=os.cpu_count(),
            memory_total_bytes=_memory_total_bytes(),
        )
