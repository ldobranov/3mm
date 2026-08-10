"""Unprivileged provisioning adapter for the local network helper."""

from __future__ import annotations

import json
import socket
from pathlib import Path

from three_mm_provisioning.models import NetworkCredentials
from three_mm_provisioning.network import NetworkAdapterError


class NetworkHelperClientAdapter:
    def __init__(self, socket_path: Path, timeout_seconds: float = 45.0) -> None:
        self._socket_path = socket_path
        self._timeout_seconds = timeout_seconds
        self._credentials: NetworkCredentials | None = None
        self._connected = False

    def enter_setup_mode(self) -> None:
        return None

    def stage_configuration(self, credentials: NetworkCredentials) -> None:
        self._credentials = credentials

    def activate_staged(self) -> None:
        if self._credentials is None:
            raise NetworkAdapterError("No Wi-Fi configuration was staged")
        result = self._request(
            {
                "network_name": self._credentials.network_name,
                "passphrase": self._credentials.passphrase,
            }
        )
        if result != {"ok": True}:
            raise NetworkAdapterError("Network helper rejected configuration")
        self._connected = True

    def activate_runtime(self) -> None:
        result = self._request({"action": "activate_runtime"})
        if result != {"ok": True}:
            raise NetworkAdapterError("Network helper rejected runtime activation")

    def _request(self, payload: dict[str, str]) -> object:
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
        self._credentials = None

    def rollback(self) -> None:
        self._credentials = None
        self._connected = False

    def leave_setup_mode(self) -> None:
        return None
