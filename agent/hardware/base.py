"""Hardware inventory driver contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class HardwareSnapshot:
    driver_id: str
    model: str | None
    architecture: str
    logical_cpu_count: int | None = None
    memory_total_bytes: int | None = None
    capabilities: tuple[str, ...] = ("hardware.inventory",)

    def __post_init__(self) -> None:
        if not self.driver_id.strip():
            raise ValueError("Hardware driver ID cannot be empty")
        if not self.architecture.strip():
            raise ValueError("Hardware architecture cannot be empty")
        if self.logical_cpu_count is not None and self.logical_cpu_count < 1:
            raise ValueError("Logical CPU count must be positive")
        if self.memory_total_bytes is not None and self.memory_total_bytes < 1:
            raise ValueError("Memory size must be positive")


class HardwareInventoryDriver(Protocol):
    def collect(self) -> HardwareSnapshot: ...
