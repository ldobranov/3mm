"""Unprivileged provisioning adapter for the local network helper."""

from __future__ import annotations

import json
import socket
from pathlib import Path

from three_mm_provisioning.models import NetworkCredentials
from three_mm_provisioning.network import NetworkAdapterError
from three_mm_provisioning.network_manager import WifiNetwork


class NetworkHelperClientAdapter:
    def __init__(self, socket_path: Path, timeout_seconds: float = 115.0) -> None:
        self._socket_path = socket_path
        self._timeout_seconds = timeout_seconds
        self._credentials: NetworkCredentials | None = None
        self._connected = False
        self.attempt_id: str | None = None
        self.interface: str | None = None

    def begin_attempt(self, identifier: str, interface: str) -> None:
        self.attempt_id, self.interface = identifier, interface

    def transaction_phase(self, identifier: str) -> str:
        return self._transaction("wifi.status", identifier)

    def _transaction(self, action: str, identifier: str | None = None) -> str:
        result = self._request({"action": action, "id": identifier or self.attempt_id})
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise NetworkAdapterError("Network transaction unavailable")
        return result.get("phase", "missing")

    def rollback_attempt(self, identifier: str) -> str:
        return self._transaction("wifi.rollback", identifier)

    def enter_setup_mode(self) -> None:
        return None

    def stage_configuration(self, credentials: NetworkCredentials) -> None:
        self._credentials = credentials

    def activate_staged(self) -> None:
        if self._credentials is None:
            raise NetworkAdapterError("No Wi-Fi configuration was staged")
        result = self._request(
            {
                "action": "wifi.apply",
                "id": self.attempt_id,
                "interface": self.interface,
                "network_name": self._credentials.network_name,
                "passphrase": self._credentials.passphrase,
            }
        )
        if result != {"ok": True, "phase": "verified"}:
            raise NetworkAdapterError("Network helper rejected configuration")
        self._connected = True

    def activate_runtime(self, *, recovery: bool = False) -> None:
        result = self._request({"action": "activate_runtime", "recovery": recovery})
        if result != {"ok": True}:
            raise NetworkAdapterError("Network helper rejected runtime activation")

    def scan_wifi_networks(self) -> tuple[WifiNetwork, ...]:
        result = self._request({"action": "scan_wifi"})
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise NetworkAdapterError("Network helper rejected Wi-Fi scan")
        items = result.get("items")
        if not isinstance(items, list):
            raise NetworkAdapterError("Network helper returned an invalid Wi-Fi scan")
        try:
            return tuple(
                WifiNetwork(
                    network_name=item["network_name"],
                    signal=item["signal"],
                    secured=item["secured"],
                )
                for item in items
                if isinstance(item, dict)
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise NetworkAdapterError(
                "Network helper returned an invalid Wi-Fi scan"
            ) from exc

    def _request(self, payload: dict[str, object]) -> object:
        request = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self._timeout_seconds)
                client.connect(str(self._socket_path))
                client.sendall(request)
                response = b""
                while len(response) <= 4096:
                    chunk = client.recv(1024)
                    if not chunk:
                        break
                    response += chunk
                    if b"\n" in response:
                        break
            result = json.loads(response.split(b"\n", 1)[0])
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise NetworkAdapterError("Network helper is unavailable") from exc
        return result

    def verify_connectivity(self) -> bool:
        return self._connected

    def commit(self) -> None:
        if self._transaction("wifi.commit") != "committed":
            raise NetworkAdapterError("Network transaction was not committed")
        self._credentials = None

    def rollback(self) -> None:
        self._credentials = None
        self._connected = False
        if self.attempt_id:
            self.rollback_attempt(self.attempt_id)

    def leave_setup_mode(self) -> None:
        return None
