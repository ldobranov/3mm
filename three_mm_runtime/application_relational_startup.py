"""Trusted prepared-host boot gate BEFORE any package import/factory.

No public SDK export or application-selected identity/path/deadline. One bounded
request over the existing signed platform socket, no retry/fallback on loss.
This is a reviewed-native startup boundary, not hostile Python isolation.
"""

import hashlib
import os
import socket
import time
import uuid
from pathlib import Path

from three_mm_application_sdk.relational_wire import (
    _RelationalBootStartupPermit,
    canonical,
    verify_metadata,
)
from three_mm_runtime.application_relational_boot_policy import (
    boot_gate_present,
    read_boot_policy,
)
from three_mm_runtime.application_relational_session import _clock, _read, _send
from three_mm_runtime.application_transport import sign_message, verify_message


def _identity():
    pid = os.getpid()
    fields = (
        Path(f"/proc/{pid}/stat")
        .read_text(encoding="ascii")
        .rpartition(") ")[2]
        .split()
    )
    if len(fields) < 20:
        raise ValueError("Host process identity unavailable")
    return {
        "process_pid": pid,
        "service_uid": os.geteuid(),
        "service_gid": os.getegid(),
        "process_start_ticks": int(fields[19]),
    }


def require_boot_startup(runtime, platform):
    """Manual start unchanged; Root ALWAYS publishes gate before boot enable.

    A surviving required marker OR policy makes validation mandatory, including
    partial publication. Only a Root verified-stop archive removes the markers.
    No grant is manufactured; normal SQL admission remains independent.
    """
    if not boot_gate_present(runtime.root):
        return  # Existing explicit prepared start, never implicit boot consent.
    if runtime._boot_startup_attempted:
        raise ValueError("Boot startup already attempted; do not retry")
    runtime._boot_startup_attempted = True
    if platform is None or os.geteuid() <= 0 or os.getegid() <= 0:
        raise ValueError("Boot startup requires the non-root host")
    policy = read_boot_policy(runtime.root, runtime.secret)
    identity = _identity()
    ticket = policy["ticket"]
    if (identity["service_uid"], identity["service_gid"]) != (
        ticket["service_uid"],
        ticket["service_gid"],
    ):
        raise ValueError("Boot host principal changed")
    boot_id, _ = _clock()
    session = runtime.session
    identifier = "platform_" + uuid.uuid4().hex
    request = sign_message(
        {
            "version": 1,
            "request_id": identifier,
            "timestamp": int(time.time()),
            "instance_id": ticket["instance_id"],
            "action": "relational.boot.startup",
            "runtime_nonce": session._nonce,
        },
        runtime.secret,
    )
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5)
        connection.connect(str(platform.socket_path))
        _send(connection, request)
        response = verify_message(
            _read(connection), runtime.secret, expected_request_id=identifier
        )
    if (
        type(response.get("version")) is not int
        or set(response)
        != {"version", "request_id", "timestamp", "ok", "result", "signature"}
        or response["ok"] is not True
    ):
        raise ValueError("Boot startup unconfirmed; do not retry")
    permit = _RelationalBootStartupPermit.model_validate(response["result"]).model_dump(
        mode="json"
    )
    verify_metadata(runtime.secret, "boot_startup", permit)
    current_boot, now = _clock()
    if (
        current_boot != boot_id
        or session._boot != boot_id
        or not permit["issued_at_ms"] <= now < permit["deadline_ms"]
        or any(
            permit[name] != value
            for name, value in {
                "instance_id": ticket["instance_id"],
                "runtime_nonce": session._nonce,
                "boot_enable_id": ticket["preparation_id"],
                "boot_id": boot_id,
                "policy_sha256": hashlib.sha256(canonical(policy)).hexdigest(),
                "lifecycle_sha256": hashlib.sha256(
                    canonical(session._record)
                ).hexdigest(),
                "authority_epoch": ticket["authority_epoch"],
                "recovery_generation": ticket["recovery_generation"],
                "grant_record_revision": ticket["grant_record_revision"],
                **identity,
            }.items()
        )
        or read_boot_policy(runtime.root, runtime.secret) != policy
        or _identity() != identity
    ):
        raise ValueError("Boot startup handoff expired or changed")
