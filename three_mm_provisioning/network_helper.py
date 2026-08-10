"""Root-only NetworkManager helper exposed through a local Unix socket."""

from __future__ import annotations

import argparse
import json
import os
import socket
from pathlib import Path

from three_mm_provisioning.models import NetworkCredentials
from three_mm_provisioning.network_manager_persistent import (
    PersistentNetworkManagerAdapter,
)
from three_mm_provisioning.network_manager_mutation import (
    NetworkManagerMutationBoundary,
)

MAX_REQUEST_BYTES = 4096


def _handle_request(payload: object) -> dict[str, object]:
    if payload == {"action": "activate_runtime"}:
        try:
            NetworkManagerMutationBoundary().schedule_runtime_activation()
        except Exception:
            return {"ok": False, "error": "runtime_activation_failed"}
        return {"ok": True}
    if not isinstance(payload, dict) or set(payload) != {
        "network_name",
        "passphrase",
    }:
        return {"ok": False, "error": "invalid_request"}
    network_name = payload["network_name"]
    passphrase = payload["passphrase"]
    if (
        not isinstance(network_name, str)
        or not 1 <= len(network_name) <= 32
        or not isinstance(passphrase, str)
        or not 8 <= len(passphrase) <= 63
    ):
        return {"ok": False, "error": "invalid_request"}

    adapter = PersistentNetworkManagerAdapter()
    adapter.enter_setup_mode()
    adapter.stage_configuration(NetworkCredentials(network_name, passphrase))
    try:
        adapter.activate_staged()
        if not adapter.verify_connectivity():
            adapter.rollback()
            return {"ok": False, "error": "connectivity_failed"}
        adapter.commit()
        adapter.leave_setup_mode()
    except Exception:
        adapter.rollback()
        return {"ok": False, "error": "network_configuration_failed"}
    return {"ok": True}


def serve(socket_path: Path, group_name: str = "3mm") -> None:
    import grp

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
                request = b""
                while len(request) <= MAX_REQUEST_BYTES:
                    chunk = connection.recv(1024)
                    if not chunk:
                        break
                    request += chunk
                    if b"\n" in request:
                        break
                try:
                    if len(request) > MAX_REQUEST_BYTES:
                        raise ValueError("request_too_large")
                    payload = json.loads(request.split(b"\n", 1)[0])
                    response = _handle_request(payload)
                except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
                    response = {"ok": False, "error": "invalid_request"}
                connection.sendall(
                    json.dumps(response, separators=(",", ":")).encode("utf-8")
                    + b"\n"
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the 3mm network helper")
    parser.add_argument(
        "--socket",
        type=Path,
        default=Path("/run/3mm/network-helper.sock"),
    )
    parser.add_argument("--group", default="3mm")
    arguments = parser.parse_args()
    serve(arguments.socket, arguments.group)


if __name__ == "__main__":
    main()
