"""Root helper: bounded local protocol, explicit managed Wi-Fi transactions."""

from __future__ import annotations

import argparse
import json
import os
import socket
from pathlib import Path

from three_mm_provisioning.network_capabilities import INTERFACE, managed_interfaces
from three_mm_provisioning.network_transaction import IDENTIFIER, NetworkTransaction
from three_mm_provisioning.network_manager import NetworkManagerReadOnlyAdapter
from three_mm_provisioning.network_manager_mutation import NetworkManagerMutationBoundary

MAX_REQUEST_BYTES = 4096


def _handle_request(payload: object, transaction=None) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid_request"}
    try:
        if payload == {"action": "capabilities"}:
            return {"ok": True, "interfaces": managed_interfaces()}
        if payload == {"action": "scan_wifi"}:
            if not managed_interfaces():
                return {"ok": False, "error": "wifi_unavailable"}
            items = NetworkManagerReadOnlyAdapter.from_system(timeout_seconds=5).scan_wifi_networks()
            return {"ok": True, "items": [{"network_name": item.network_name,
                    "signal": item.signal, "secured": item.secured} for item in items]}
        if (set(payload) == {"action", "recovery"} and payload["action"] == "activate_runtime"
                and type(payload["recovery"]) is bool):
            NetworkManagerMutationBoundary().schedule_runtime_activation(recovery=payload["recovery"])
            return {"ok": True}
        action = payload.get("action")
        fields = {"action", "id"}
        if action == "wifi.apply":
            fields |= {"interface", "network_name", "passphrase"}
            if (not isinstance(payload.get("interface"), str) or not INTERFACE.fullmatch(payload["interface"])
                    or not isinstance(payload.get("network_name"), str) or not 1 <= len(payload["network_name"].encode()) <= 32
                    or not isinstance(payload.get("passphrase"), str) or not 8 <= len(payload["passphrase"]) <= 63
                    or any(c in payload["passphrase"] for c in "\r\n\0")):
                return {"ok": False, "error": "invalid_request"}
        elif action not in {"wifi.status", "wifi.commit", "wifi.rollback"}:
            return {"ok": False, "error": "invalid_request"}
        if (set(payload) != fields or not isinstance(payload.get("id"), str)
                or not IDENTIFIER.fullmatch(payload["id"])):
            return {"ok": False, "error": "invalid_request"}
        return (transaction or NetworkTransaction()).handle(payload)
    except Exception:
        # Never expose exception text, nmcli output, SSIDs or credentials.
        return {"ok": False, "error": "operation_failed"}


def serve(socket_path: Path, group_name: str = "3mm") -> None:
    import grp

    transaction = NetworkTransaction()
    transaction.recover()
    group_id = grp.getgrnam(group_name).gr_gid
    socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    os.chown(socket_path.parent, 0, group_id)
    os.chmod(socket_path.parent, 0o750)
    socket_path.unlink(missing_ok=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(socket_path))
        os.chown(socket_path, 0, group_id)
        os.chmod(socket_path, 0o660)
        server.listen(4)
        while True:
            connection, _ = server.accept()
            with connection:
                connection.settimeout(5)
                try:
                    request = b""
                    while len(request) <= MAX_REQUEST_BYTES and b"\n" not in request:
                        chunk = connection.recv(1024)
                        if not chunk:
                            break
                        request += chunk
                    if len(request) > MAX_REQUEST_BYTES:
                        raise ValueError("request_too_large")
                    payload = json.loads(request.split(b"\n", 1)[0])
                    response = _handle_request(payload, transaction)
                    connection.sendall(json.dumps(response, separators=(",", ":")).encode() + b"\n")
                except (OSError, ValueError):
                    # A malformed or abandoned client cannot stop the helper.
                    continue


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", type=Path, default=Path("/run/3mm/network-helper.sock"))
    parser.add_argument("--group", default="3mm")
    arguments = parser.parse_args()
    serve(arguments.socket, arguments.group)


if __name__ == "__main__":
    main()
