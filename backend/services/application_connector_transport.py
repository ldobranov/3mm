"""Short Core connector admission and durable result-only completion."""
import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import re
import socket
import time
import uuid

from sqlalchemy import select
from backend.db.module import ApplicationConnectorAttempt, ApplicationExtensionInstallation
from backend.services.application_connectors import prepare_connector_request, record_connector_outcome, connector_outcome
from three_mm_platform_wire import canonical, peer_identity, process_generation, remaining

CONTRACT = 1


def failure(method, category):
    return {"outcome": "ambiguous" if method in {"POST", "PUT", "PATCH", "DELETE"} else "retryable",
        "http_status": None, "error_category": category, "body_base64": "", "headers": {}}


def clock():
    return (Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip(),
        int(time.clock_gettime(time.CLOCK_BOOTTIME) * 1000))


def expired(metadata):
    boot, now = clock()
    return metadata["boot_id"] != boot or now > metadata["deadline_ms"]


def sign(value, key):
    return {**value, "signature": hmac.new(key, canonical(value), hashlib.sha256).hexdigest()}


def verify(value, key):
    if not isinstance(value, dict) or not isinstance(value.get("signature"), str):
        raise ValueError("Invalid connector signature")
    if not hmac.compare_digest(sign(value, key)["signature"], value["signature"]):
        raise ValueError("Invalid connector signature")


def result_key(secret, dispatch_id):
    return hmac.new(secret, b"connector-result-only:" + dispatch_id.encode("ascii"), hashlib.sha256).digest()


@dataclass
class ConnectorDispatch:
    receipt: dict
    connection: socket.socket
    timeout: int


def expire_connector_attempts(db, installation_id):
    """Bounded reconciliation on request/status read; never sends or retries."""
    rows=list(db.scalars(select(ApplicationConnectorAttempt).where(
        ApplicationConnectorAttempt.application_installation_id == installation_id,
        ApplicationConnectorAttempt.outcome == "in_progress").limit(100)))
    for old in rows:
        if old.dispatch_metadata and expired(old.dispatch_metadata):
            record_connector_outcome(db, old, failure(old.method, "execution_unconfirmed"))


def begin_connector(db, installation, request, *, secret, runtime_generation, worker_path, worker_uid):
    headers = request.get("headers")
    if not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k,v in headers.items()):
        raise ValueError("Connector headers are invalid")
    try: body = base64.b64decode(str(request.get("body_base64", "")), validate=True)
    except ValueError as exc: raise ValueError("Connector body is invalid") from exc
    expire_connector_attempts(db, installation.id)
    boot, now = clock()
    metadata = {"dispatch_id": uuid.uuid4().hex, "boot_id": boot, "deadline_ms": now + 40000,
        "runtime_generation": runtime_generation, "sdk_request_id": request["request_id"],
        "instance_id": installation.instance_id}
    plan = prepare_connector_request(db, installation,
        connector_id=str(request.get("connector_id", "")), request_id=str(request.get("connector_request_id", "")),
        method=str(request.get("method", "")), path=str(request.get("path", "")), headers=headers, body=body,
        idempotency_key=request.get("idempotency_key") if isinstance(request.get("idempotency_key"), str) else None,
        dispatch_metadata=metadata)
    if "attempt_id" not in plan: return plan
    attempt = db.get(ApplicationConnectorAttempt, plan.pop("attempt_id"))
    receipt = sign({"connector_contract": CONTRACT, "attempt_id": attempt.id, **metadata}, secret)
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        deadline = time.monotonic() + 3
        connection.settimeout(remaining(deadline)); connection.connect(str(worker_path))
        pid, uid, _ = peer_identity(connection)
        if uid != worker_uid: raise ValueError("Connector worker principal is not trusted")
        process_generation(pid, uid)  # Validate a live kernel principal, not a forwarded identity.
        message = {"connector_contract": CONTRACT, "plan": plan,
            "result_key": result_key(secret, metadata["dispatch_id"]).hex()}
        encoded = json.dumps(message, separators=(",", ":"), allow_nan=False).encode() + b"\n"
        connection.settimeout(remaining(deadline)); connection.sendall(encoded)
        return ConnectorDispatch(receipt, connection, plan["timeout_seconds"])
    except Exception:
        connection.close()
        # Even a partial send may have caused a remote effect. Never call it safe to retry a mutation.
        return record_connector_outcome(db, attempt, failure(attempt.method, "worker_unavailable"))


def finish_connector(db, receipt, response, *, key_root, runtime_generation, failure_category=None):
    if (not isinstance(receipt, dict) or receipt.get("connector_contract") != CONTRACT
            or not isinstance(receipt.get("instance_id"), str)
            or re.fullmatch(r"[0-9a-f]{24}", receipt["instance_id"]) is None):
        raise ValueError("Invalid connector receipt")
    secret = (key_root / (receipt["instance_id"] + ".key")).read_bytes()
    if len(secret) != 32: raise ValueError("Invalid transport key")
    verify(receipt, secret)
    attempt = db.get(ApplicationConnectorAttempt, receipt["attempt_id"])
    metadata = {k:v for k,v in receipt.items() if k not in {"signature", "connector_contract", "attempt_id"}}
    app = db.get(ApplicationExtensionInstallation, attempt.application_installation_id) if attempt else None
    if (attempt is None or app is None or app.instance_id != receipt["instance_id"]
            or attempt.dispatch_metadata != metadata or metadata["runtime_generation"] != runtime_generation):
        raise ValueError("Connector result owner changed")
    if attempt.outcome != "in_progress": result = connector_outcome(attempt, duplicate=True)
    else:
        result = failure(attempt.method, "execution_unconfirmed")
        if not expired(metadata) and failure_category is None:
            try:
                verify(response, result_key(secret, metadata["dispatch_id"]))
                raw = {k:v for k,v in response.items() if k != "signature"}
                if (set(raw) != {"outcome", "http_status", "error_category", "body_base64", "headers"}
                        or raw["outcome"] not in {"succeeded", "rejected", "retryable", "ambiguous", "failed"}
                        or (raw["http_status"] is not None and (type(raw["http_status"]) is not int or not 100 <= raw["http_status"] <= 599))
                        or not isinstance(raw["body_base64"], str)
                        or len(base64.b64decode(raw["body_base64"], validate=True)) > metadata["max_response_bytes"]
                        or not isinstance(raw["headers"], dict)
                        or any(k != "Content-Type" or not isinstance(v, str) or len(v) > 256 for k,v in raw["headers"].items())
                        or raw["error_category"] not in {None, "response_limit", "response_timeout", "connection_lost", "worker_failed"}):
                    raise ValueError("Invalid connector result")
                result = raw
            except (ValueError, TypeError, KeyError): pass
        result = record_connector_outcome(db, attempt, result)
    # Completing an admitted effect after revocation is bookkeeping only.
    return sign({"version": 1, "request_id": metadata["sdk_request_id"], "timestamp": int(time.time()),
        "ok": True, "result": result}, secret)
