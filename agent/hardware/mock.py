"""Deterministic laptop hardware profiles."""

from __future__ import annotations

from enum import Enum

from agent.hardware.base import HardwareSnapshot


class HardwareProfile(str, Enum):
    NATIVE = "native"
    MOCK_PI3 = "mock-pi3"
    MOCK_ZERO2 = "mock-zero2"
    MOCK_LINUX = "mock-linux"


_MOCK_PROFILES = {
    HardwareProfile.MOCK_PI3: HardwareSnapshot(
        driver_id="mock",
        model="Raspberry Pi 3 Model B Plus Rev 1.4",
        architecture="aarch64",
        logical_cpu_count=4,
        memory_total_bytes=1_073_741_824,
    ),
    HardwareProfile.MOCK_ZERO2: HardwareSnapshot(
        driver_id="mock",
        model="Raspberry Pi Zero 2 W Rev 1.0",
        architecture="aarch64",
        logical_cpu_count=4,
        memory_total_bytes=536_870_912,
    ),
    HardwareProfile.MOCK_LINUX: HardwareSnapshot(
        driver_id="mock",
        model="Generic Linux development host",
        architecture="x86_64",
        logical_cpu_count=4,
        memory_total_bytes=4_294_967_296,
    ),
}


class MockHardwareDriver:
    def __init__(self, snapshot: HardwareSnapshot) -> None:
        self._snapshot = snapshot

    @classmethod
    def for_profile(cls, profile: HardwareProfile) -> "MockHardwareDriver":
        if profile is HardwareProfile.NATIVE:
            raise ValueError("Native profile requires the Linux hardware driver")
        try:
            snapshot = _MOCK_PROFILES[profile]
        except KeyError as exc:
            raise ValueError(f"Unknown mock hardware profile: {profile}") from exc
        return cls(snapshot)

    def collect(self) -> HardwareSnapshot:
        return self._snapshot
