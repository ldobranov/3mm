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
WIFI_FIELDS = "SSID,SIGNAL,SECURITY"


@dataclass(frozen=True, slots=True)
class CommandResult:
    return_code: int
    standard_output: str


@dataclass(frozen=True, slots=True)
class WifiNetwork:
    network_name: str
    signal: int
    secured: bool


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

    def scan_wifi_networks(
        self,
        *,
        rescan: bool = False,
        interface: str | None = None,
    ) -> tuple[WifiNetwork, ...]:
        """Return a Wi-Fi scan, optionally refreshing before setup AP activation."""

        arguments = [
            "-t",
            "-e",
            "yes",
            "-f",
            WIFI_FIELDS,
            "device",
            "wifi",
            "list",
        ]
        if interface is not None:
            arguments.extend(("ifname", interface))
        arguments.extend(("--rescan", "yes" if rescan else "no"))
        output = self._execute(*arguments)
        return _parse_wifi_networks(output)

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


def _parse_wifi_networks(output: str) -> tuple[WifiNetwork, ...]:
    strongest: dict[str, WifiNetwork] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        fields = _split_escaped_fields(line)
        if len(fields) != 3:
            raise NetworkInspectionError("NetworkManager Wi-Fi output is invalid")
        network_name, signal_value, security = fields
        if not network_name or len(network_name) > 32:
            continue
        try:
            signal = int(signal_value)
        except ValueError as exc:
            raise NetworkInspectionError(
                "NetworkManager Wi-Fi signal is invalid"
            ) from exc
        if not 0 <= signal <= 100:
            raise NetworkInspectionError("NetworkManager Wi-Fi signal is invalid")
        candidate = WifiNetwork(
            network_name=network_name,
            signal=signal,
            secured=security.strip() not in {"", "--"},
        )
        previous = strongest.get(network_name)
        if previous is None or candidate.signal > previous.signal:
            strongest[network_name] = candidate
    return tuple(
        sorted(
            strongest.values(),
            key=lambda item: (-item.signal, item.network_name.casefold()),
        )[:30]
    )


def _split_escaped_fields(value: str) -> list[str]:
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for character in value:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    fields.append("".join(current))
    return fields


def _parse_flag(value: str, true_value: str, false_value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == true_value:
        return True
    if normalized == false_value:
        return False
    raise NetworkInspectionError("NetworkManager boolean field is invalid")
