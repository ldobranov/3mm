"""Detached root worker for one durable, prepared Node update operation."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from three_mm_runtime.node_update_helper import (
    AGENT_DATA, CURRENT_ROOT, SOCKET_PATH, MAX_REQUEST_BYTES, NodeUpdateError, NodeUpdateStore,
    inspect_prepared_archive, read_small, trusted_path,
)
from three_mm_runtime.node_update_trust import verify_node_update_authorization


def snapshot_agent_state(agent_data):
    result = {}
    for name in ("identity.json", "core-credential.json", "core-binding.json", "gpio-configuration.json"):
        path = Path(agent_data) / name
        result[name] = hashlib.sha256(read_small(path)).hexdigest() if path.exists() else None
    return result


def check_health(device_id):
    with urlopen("http://127.0.0.1:8890/ready", timeout=5) as response:
        value = json.loads(response.read(64 * 1024))
    return value.get("status") == "ready" and value.get("device_id") == device_id


def check_helper(operation_id):
    """Bounded startup check of the new helper, not just Type=simple is-active."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(1)
                connection.connect(str(SOCKET_PATH))
                connection.sendall(b'{"action":"status"}\n')
                response = b""
                while (b"\n" not in response and len(response) <= MAX_REQUEST_BYTES
                       and time.monotonic() < deadline):
                    chunk = connection.recv(1024)
                    if not chunk:
                        break
                    response += chunk
            if len(response) <= MAX_REQUEST_BYTES and b"\n" in response:
                value = json.loads(response.split(b"\n", 1)[0])
                operation = value.get("operation") if isinstance(value, dict) else None
                if (value.get("ok") is True and isinstance(operation, dict)
                        and operation.get("operation_id") == operation_id and operation.get("status") == "running"):
                    return True
        except (OSError, ValueError, AttributeError):
            pass
        time.sleep(0.5)
    return False


def run_installer(arguments):
    # The detached systemd unit bounds the entire installer process tree. A
    # Python timeout would kill only bash and could leave mutation children alive.
    return subprocess.run(arguments, check=False,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}).returncode


def apply_node_update(operation_id, *, store=None, validator=None, runner=run_installer,
                      current_root=CURRENT_ROOT, agent_data=AGENT_DATA, health_checker=check_health,
                      helper_checker=check_helper, authorization_verifier=None):
    store = store or NodeUpdateStore()
    authorization_verifier = authorization_verifier or (
        lambda authorization: verify_node_update_authorization(authorization, state_root=store.root))
    validator = validator or (lambda request: inspect_prepared_archive(request, store=store,
        current_root=current_root, agent_data=agent_data))
    with store.locked():
        record = store.read(operation_id)
        if record is None:
            raise NodeUpdateError("missing_operation", "Node update was not accepted by the helper")
        if record["operation"].status != "accepted":
            return 0 if record["operation"].status == "succeeded" else 1
        request = record["request"]
        try:
            authorization_verifier(record.get("authorization"))
            archive_path, target_metadata = validator(request)
            previous = Path(current_root).resolve(strict=True)
            trusted_path(previous / ".3mm-release.json", permissions=store.enforce_permissions)
            trusted_path(previous / "deployment/install-systemd.sh", permissions=store.enforce_permissions)
            previous_metadata = json.loads(read_small(previous / ".3mm-release.json"))
            preserved = snapshot_agent_state(agent_data)
            store.transition(record, "running", previous_release_id=previous_metadata["release_id"])
        except (NodeUpdateError, ValueError, OSError, KeyError):
            store.transition(record, "failed", error_code="preflight_failed")
            return 1
    # The accepted request and running state are durable before any mutation.
    # The existing installer's global flock remains the authoritative release lock.
    mutated = False
    try:
        if request.expires_at <= datetime.now(UTC):
            raise NodeUpdateError("expired", "Node update handoff expired before installer invocation")
        authorization_verifier(record.get("authorization"))
        if request.expires_at <= datetime.now(UTC):
            raise NodeUpdateError("expired", "Node update handoff expired during approval verification")
        mutated = True
        result = runner(["/usr/bin/bash", str(previous / "deployment/install-systemd.sh"),
            str(archive_path), request.release_id, "http://localhost", "", request.archive_sha256, "node"])
        active = Path(current_root).resolve(strict=True)
        trusted_path(active, directory=True, permissions=store.enforce_permissions)
        for name in (".3mm-release.json", ".3mm-install-profile", "VERSION"):
            trusted_path(active / name, permissions=store.enforce_permissions)
        metadata = json.loads(read_small(active / ".3mm-release.json"))
        verified_profile = (read_small(active / ".3mm-install-profile").strip() == b"node"
            and read_small(active / "VERSION").decode("ascii").strip() == metadata.get("version"))
        state_preserved = snapshot_agent_state(agent_data) == preserved
        healthy = health_checker(request.device_id)
        helper_ready = helper_checker(request.operation_id) if result == 0 else False
        if (result == 0 and metadata == target_metadata and active == previous.parent / request.release_id
                and verified_profile and state_preserved and healthy and helper_ready):
            status, error = "succeeded", None
        elif (result != 0 and active == previous and metadata == previous_metadata
                and verified_profile and state_preserved and healthy):
            status, error = "rolled_back", "installer_failed"
        else:
            status, error = "unknown", "postflight_unverified"
    except Exception as exc:
        status = "unknown" if mutated else "failed"
        error = exc.code if isinstance(exc, NodeUpdateError) else "installer_unresolved"
    with store.locked():
        store.transition(record, status, error_code=error)
    return 0 if status == "succeeded" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation-id", required=True)
    arguments = parser.parse_args()
    if sys.platform != "linux" or os.geteuid() != 0:
        raise SystemExit("Node update worker must run as root on Linux")
    return apply_node_update(arguments.operation_id)


if __name__ == "__main__":
    raise SystemExit(main())
