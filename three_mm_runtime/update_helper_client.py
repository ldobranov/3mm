"""Unprivileged client for the local, narrowly scoped privileged helper."""

from __future__ import annotations

import json
import socket
from pathlib import Path


class UpdateHelperError(RuntimeError):
    """Raised when the privileged update helper rejects or misses a request."""


class UpdateHelperClient:
    def __init__(self, socket_path: Path, timeout_seconds: float = 10.0) -> None:
        self._socket_path = socket_path
        self._timeout_seconds = timeout_seconds

    def schedule(
        self,
        release_id: str,
        approval_nonce: str,
        requested_by_user_id: int,
    ) -> None:
        payload = {
            "action": "apply",
            "release_id": release_id,
            "approval_nonce": approval_nonce,
            "requested_by_user_id": requested_by_user_id,
        }
        self._request(payload)

    def request_network_setup(self, requested_by_user_id: int) -> None:
        self._request(
            {
                "action": "start_network_setup",
                "requested_by_user_id": requested_by_user_id,
            }
        )

    def request_system_action(
        self,
        action: str,
        requested_by_user_id: int,
    ) -> None:
        if action not in {"restart_device", "factory_reset"}:
            raise ValueError("Unsupported system action")
        self._request(
            {
                "action": action,
                "requested_by_user_id": requested_by_user_id,
            }
        )

    def request_backup(self, requested_by_user_id: int) -> None:
        self._request(
            {
                "action": "create_backup",
                "requested_by_user_id": requested_by_user_id,
            }
        )

    def request_restore(self, backup_id: str, requested_by_user_id: int) -> None:
        self._request(
            {
                "action": "restore_backup",
                "backup_id": backup_id,
                "requested_by_user_id": requested_by_user_id,
            }
        )

    def request_portable_export(
        self,
        backup_id: str,
        passphrase: str,
        requested_by_user_id: int,
    ) -> dict[str, object]:
        result = self._request(
            {
                "action": "export_backup",
                "backup_id": backup_id,
                "passphrase": passphrase,
                "requested_by_user_id": requested_by_user_id,
            },
            expected_status="ready",
        )
        if not all(
            isinstance(result.get(field), str)
            for field in ("export_id", "backup_id", "filename")
        ):
            raise UpdateHelperError("The recovery export response is invalid")
        return result

    def request_portable_restore(
        self,
        upload_id: str,
        passphrase: str,
        requested_by_user_id: int,
    ) -> str:
        result = self._request(
            {
                "action": "restore_portable_backup",
                "upload_id": upload_id,
                "passphrase": passphrase,
                "requested_by_user_id": requested_by_user_id,
            }
        )
        backup_id = result.get("backup_id")
        if not isinstance(backup_id, str):
            raise UpdateHelperError("The portable restore response is invalid")
        return backup_id

    def _request(
        self,
        payload: dict[str, object],
        *,
        expected_status: str = "queued",
    ) -> dict[str, object]:
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
            raise UpdateHelperError("The system update helper is unavailable") from exc
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise UpdateHelperError("The system update helper rejected the request")
        if result.get("status") != expected_status:
            raise UpdateHelperError("The system update helper response is invalid")
        return result
