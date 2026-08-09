"""Read-only NetworkManager inspection through a fixed nmcli allowlist."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Protocol, Sequence

from three_mm_provisioning.network_inspection import (
    NetworkDeviceStatus,
    NetworkInspectionError,
    NetworkManagerStatus,
)

GENERAL_FIELDS = "RUNNING,STATE,CONNECTIVITY,WIFI-HW,WIFI"
DEVICE_FIELDS = "DEVICE,TYPE,STATE"


@dataclass(frozen=True, slots=True)
class CommandResult:
    return_code: int
    standard_output: str


class CommandRunner(Protocol):
    def run(
        self, arguments: Sequence[str], timeout_seconds: float
    ) -> CommandResult: ...


class SubprocessCommandRunner:
    def run(
        self,
        arguments: Sequence[str],
        timeout_seconds: float,
    ) -> CommandResult:
        environment = os.environ.copy()
        environment["LC_ALL"] = "C"
        try:
            completed = subprocess.run(
                list(arguments),
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise NetworkInspectionError(
                "NetworkManager inspection command did not complete"
            ) from exc
        return CommandResult(
            return_code=completed.returncode,
            standard_output=completed.stdout,
        )


class NetworkManagerReadOnlyAdapter:
    def __init__(
        self,
        executable: str,
        runner: CommandRunner | None = None,
        timeout_seconds: float = 2.0,
    ) -> None:
        if not executable:
            raise ValueError("nmcli executable cannot be empty")
        if timeout_seconds <= 0:
            raise ValueError("Inspection timeout must be positive")
        self._executable = executable
        self._runner = runner or SubprocessCommandRunner()
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_system(
        cls,
        runner: CommandRunner | None = None,
        timeout_seconds: float = 2.0,
    ) -> "NetworkManagerReadOnlyAdapter":
        executable = shutil.which("nmcli")
        if executable is None:
            raise NetworkInspectionError("NetworkManager CLI is unavailable")
        return cls(
            executable=executable,
            runner=runner,
            timeout_seconds=timeout_seconds,
        )

    def inspect(self) -> NetworkManagerStatus:
        general = self._execute(
            "-t",
            "-e",
            "no",
            "-f",
            GENERAL_FIELDS,
            "general",
        )
        devices = self._execute(
            "-t",
            "-e",
            "no",
            "-f",
            DEVICE_FIELDS,
            "device",
            "status",
        )
        return _parse_status(general, devices)

    def _execute(self, *arguments: str) -> str:
        result = self._runner.run(
            (self._executable, *arguments),
            self._timeout_seconds,
        )
        if result.return_code != 0:
            raise NetworkInspectionError("NetworkManager inspection command failed")
        return result.standard_output


def _parse_status(general_output: str, device_output: str) -> NetworkManagerStatus:
    general_lines = [
        line.strip() for line in general_output.splitlines() if line.strip()
    ]
    if len(general_lines) != 1:
        raise NetworkInspectionError("NetworkManager general output is invalid")
    general_fields = general_lines[0].split(":")
    if len(general_fields) != 5:
        raise NetworkInspectionError("NetworkManager general fields are invalid")

    devices: list[NetworkDeviceStatus] = []
    for line in device_output.splitlines():
        if not line.strip():
            continue
        fields = line.split(":")
        if len(fields) != 3 or not all(fields):
            raise NetworkInspectionError("NetworkManager device fields are invalid")
        devices.append(
            NetworkDeviceStatus(
                interface=fields[0],
                device_type=fields[1],
                state=fields[2],
            )
        )

    return NetworkManagerStatus(
        running=_parse_flag(general_fields[0], "running", "not running"),
        state=general_fields[1],
        connectivity=general_fields[2],
        wifi_hardware_enabled=_parse_flag(general_fields[3], "enabled", "disabled"),
        wifi_enabled=_parse_flag(general_fields[4], "enabled", "disabled"),
        devices=tuple(devices),
    )


def _parse_flag(value: str, true_value: str, false_value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == true_value:
        return True
    if normalized == false_value:
        return False
    raise NetworkInspectionError("NetworkManager boolean field is invalid")
