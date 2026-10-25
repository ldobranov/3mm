"""Privileged NetworkManager boundary for temporary setup access points."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Protocol, Sequence

from three_mm_provisioning.network import NetworkAdapterError


@dataclass(frozen=True, slots=True)
class MutationCommandResult:
    return_code: int
    standard_output: str = ""


class MutationCommandRunner(Protocol):
    def run(
        self,
        arguments: Sequence[str],
        timeout_seconds: float,
        secret_input: str | None = None,
    ) -> MutationCommandResult: ...


class SubprocessMutationCommandRunner:
    def run(
        self,
        arguments: Sequence[str],
        timeout_seconds: float,
        secret_input: str | None = None,
    ) -> MutationCommandResult:
        environment = os.environ.copy()
        environment["LC_ALL"] = "C"
        try:
            completed = subprocess.run(
                list(arguments),
                check=False,
                capture_output=True,
                text=True,
                input=secret_input,
                timeout=timeout_seconds,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise NetworkAdapterError(
                "NetworkManager mutation command did not complete"
            ) from exc
        return MutationCommandResult(completed.returncode, completed.stdout)


class NetworkManagerMutationBoundary:
    """Execute reviewed AP mutations behind an external rollback timer."""

    def __init__(
        self,
        nmcli: str = "/usr/bin/nmcli",
        systemd_run: str = "/usr/bin/systemd-run",
        systemctl: str = "/usr/bin/systemctl",
        python: str = "/opt/3mm/current/.venv/bin/python",
        runner: MutationCommandRunner | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._nmcli = nmcli
        self._systemd_run = systemd_run
        self._systemctl = systemctl
        self._python = python
        self._runner = runner or SubprocessMutationCommandRunner()
        self._timeout_seconds = timeout_seconds

    def active_connection_uuid(self, interface: str) -> str:
        result = self._run(
            self._nmcli,
            "-g",
            "GENERAL.CON-UUID",
            "device",
            "show",
            interface,
        )
        connection_uuid = result.standard_output.strip()
        if not connection_uuid:
            raise NetworkAdapterError("No active Wi-Fi connection is available")
        return connection_uuid

    def schedule_rollback(
        self,
        connection_uuid: str,
        delay_seconds: int = 90,
        unit_name: str = "3mm-network-rollback",
    ) -> None:
        if delay_seconds < 30:
            raise ValueError("Rollback delay must be at least 30 seconds")
        self._run(
            self._systemd_run,
            f"--unit={unit_name}",
            f"--on-active={delay_seconds}s",
            "--collect",
            self._nmcli,
            "connection",
            "up",
            "uuid",
            connection_uuid,
        )

    def schedule_runtime_activation(
        self,
        delay_seconds: int = 3,
        unit_name: str = "3mm-runtime-activation",
        recovery: bool = False,
    ) -> None:
        if delay_seconds < 1:
            raise ValueError("Runtime activation delay must be positive")
        self._run(
            self._systemctl,
            "stop",
            "3mm-setup-safety.timer",
            allow_failure=True,
        )
        self._run(
            self._systemd_run,
            f"--unit={unit_name}",
            f"--on-active={delay_seconds}s",
            "--collect",
            "--property=EnvironmentFile=-/etc/3mm/3mm.env",
            "--property=OnFailure=3mm-network-helper.service 3mm-setup-local.service",
            "/usr/bin/env",
            "PYTHONPATH=/opt/3mm/current",
            self._python,
            "-m",
            "three_mm_runtime.activate",
            *( ("--no-bootstrap-agent",) if recovery else () ),
        )

    def connect_temporary_wifi(
        self,
        *,
        interface: str,
        connection_name: str,
        network_name: str,
        passphrase: str,
    ) -> None:
        self._run(
            self._nmcli,
            "connection",
            "add",
            "type",
            "wifi",
            "ifname",
            interface,
            "con-name",
            connection_name,
            "autoconnect",
            "no",
            "ssid",
            network_name,
        )
        self._run(
            self._nmcli,
            "connection",
            "modify",
            connection_name,
            "802-11-wireless.mode",
            "infrastructure",
            "ipv4.method",
            "auto",
            "ipv6.method",
            "auto",
            "wifi-sec.key-mgmt",
            "wpa-psk",
            "wifi-sec.psk-flags",
            "2",
        )
        self._run(
            self._nmcli,
            "--ask",
            "connection",
            "up",
            connection_name,
            "ifname",
            interface,
            secret_input=f"{passphrase}\n",
        )

    def connect_persistent_wifi(
        self,
        *,
        interface: str,
        connection_name: str,
        network_name: str,
        passphrase: str,
        autoconnect: bool = True,
    ) -> None:
        """Create and activate a system profile whose secret NetworkManager owns."""
        self._run(
            self._nmcli,
            "connection",
            "add",
            "type",
            "wifi",
            "ifname",
            interface,
            "con-name",
            connection_name,
            "autoconnect",
            "yes" if autoconnect else "no",
            "ssid",
            network_name,
        )
        self._run(
            self._nmcli,
            "connection",
            "modify",
            connection_name,
            "802-11-wireless.mode",
            "infrastructure",
            "ipv4.method",
            "auto",
            "ipv6.method",
            "auto",
            "wifi-sec.key-mgmt",
            "wpa-psk",
            "wifi-sec.psk-flags",
            "0",
        )
        self._run(
            self._nmcli,
            "--ask",
            "connection",
            "up",
            connection_name,
            "ifname",
            interface,
            secret_input=f"{passphrase}\n",
        )

    def connection_uuid(self, connection_name: str) -> str | None:
        result = self._run(
            self._nmcli,
            "-g",
            "connection.uuid",
            "connection",
            "show",
            connection_name,
            allow_failure=True,
        )
        if result.return_code != 0:
            return None
        return result.standard_output.strip() or None

    def has_local_address(self, interface: str) -> bool:
        import ipaddress
        result = self._run(self._nmcli, "-g", "IP4.ADDRESS,IP6.ADDRESS", "device", "show", interface)
        for line in result.standard_output.splitlines():
            try:
                address = ipaddress.ip_interface(line.strip()).ip
                if not address.is_loopback and not address.is_link_local and not address.is_unspecified:
                    return True
            except ValueError:
                continue
        return False

    def set_autoconnect(self, connection_uuid: str, enabled: bool) -> None:
        self._run(self._nmcli, "connection", "modify", "uuid", connection_uuid,
                  "connection.autoconnect", "yes" if enabled else "no")

    def schedule_setup_rollback(self, identifier: str, delay_seconds: int = 120) -> None:
        self._run(self._systemd_run, f"--unit=3mm-setup-rollback-{identifier}",
                  f"--on-active={delay_seconds}s", "--collect", "/usr/bin/env",
                  "PYTHONPATH=/opt/3mm/current", self._python, "-m",
                  "three_mm_provisioning.network_transaction", "--rollback", identifier)

    def schedule_access_point_stop(self, identifier: str, delay_seconds: int) -> None:
        from three_mm_provisioning.network_transaction import IDENTIFIER
        if not IDENTIFIER.fullmatch(identifier) or not 60 <= delay_seconds <= 900:
            raise ValueError("Invalid AP rollback request")
        self._run(self._systemd_run, f"--unit=3mm-access-point-expire-{identifier}",
                  f"--on-active={delay_seconds}s", "--collect",
                  "--property=EnvironmentFile=-/etc/3mm/3mm.env", "/usr/bin/env",
                  "PYTHONPATH=/opt/3mm/current", self._python, "-m",
                  "three_mm_provisioning.recovery_access_point", "stop", "--id", identifier)

    def delete_connection(self, connection_uuid: str) -> None:
        self._run(
            self._nmcli,
            "connection",
            "delete",
            "uuid",
            connection_uuid,
        )

    def rename_connection(self, connection_uuid: str, connection_name: str) -> None:
        self._run(
            self._nmcli,
            "connection",
            "modify",
            "uuid",
            connection_uuid,
            "connection.id",
            connection_name,
        )

    def create_temporary_setup_access_point(
        self,
        *,
        interface: str,
        connection_name: str,
        network_name: str,
        passphrase: str,
    ) -> None:
        if len(passphrase) < 12:
            raise ValueError("Temporary access point passphrase is too short")
        self._run(
            self._nmcli,
            "connection",
            "add",
            "type",
            "wifi",
            "ifname",
            interface,
            "con-name",
            connection_name,
            "autoconnect",
            "no",
            "ssid",
            network_name,
        )
        self._run(
            self._nmcli,
            "connection",
            "modify",
            connection_name,
            "802-11-wireless.mode",
            "ap",
            "ipv4.method",
            "shared",
            "ipv6.method",
            "disabled",
            "wifi-sec.key-mgmt",
            "wpa-psk",
            "wifi-sec.psk-flags",
            "2",
        )
        self._run(
            self._nmcli,
            "--ask",
            "connection",
            "up",
            connection_name,
            "ifname",
            interface,
            secret_input=f"{passphrase}\n",
        )

    def create_temporary_open_setup_access_point(
        self,
        *,
        interface: str,
        connection_name: str,
        network_name: str,
        connection_uuid: str | None = None,
        ipv4_address: str | None = None,
    ) -> None:
        self._run(
            self._nmcli,
            "connection",
            "add",
            "type",
            "wifi",
            "ifname",
            interface,
            "con-name",
            connection_name,
            "autoconnect",
            "no",
            "ssid",
            network_name,
            *(("connection.uuid", connection_uuid) if connection_uuid else ()),
        )
        self._run(
            self._nmcli,
            "connection",
            "modify",
            connection_name,
            "802-11-wireless.mode",
            "ap",
            "ipv4.method",
            "shared",
            "ipv6.method",
            "disabled",
        )
        if ipv4_address:
            self._run(self._nmcli, "connection", "modify", connection_name,
                      "ipv4.addresses", ipv4_address)
        self._run(
            self._nmcli,
            "connection",
            "modify",
            connection_name,
            "remove",
            "802-11-wireless-security",
        )
        self._run(
            self._nmcli,
            "connection",
            "up",
            connection_name,
            "ifname",
            interface,
        )

    def cancel_rollback(self, unit_name: str = "3mm-network-rollback") -> None:
        self._run(self._systemctl, "stop", f"{unit_name}.timer")

    def restore_connection(self, connection_uuid: str) -> None:
        self._run(
            self._nmcli,
            "connection",
            "up",
            "uuid",
            connection_uuid,
        )

    def _run(
        self,
        *arguments: str,
        secret_input: str | None = None,
        allow_failure: bool = False,
    ) -> MutationCommandResult:
        result = self._runner.run(
            arguments,
            self._timeout_seconds,
            secret_input,
        )
        if result.return_code != 0 and not allow_failure:
            raise NetworkAdapterError("NetworkManager mutation command failed")
        return result
