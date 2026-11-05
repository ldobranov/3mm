"""Bounded CAP12 delivery between private, disposable local lab directories."""

import base64
from dataclasses import dataclass
import os
from pathlib import Path
import re
import socket
import sqlite3
import time

from backend.config import ApplicationRuntimeSettings
from backend.services.application_webhook_admission import ReviewedWebhookAdmission, WebhookHostTarget
from three_mm_platform_wire import read_frame, remaining
from three_mm_protocol.application_delegation import OperationExecutorV1
from three_mm_protocol.diagnostic_snapshot import read_regular
from three_mm_protocol.public_webhooks import WebhookRejected
from three_mm_runtime.application_transport import (
    TRANSPORT_VERSION, ApplicationTransportError, send_message, sign_message, verify_message,
)
from tools.webhook_lab import DeliveryAttempt, WebhookInbox


MAX_ATTEMPTS_PER_CYCLE = 4


@dataclass(frozen=True, slots=True)
class DeliveryCycle:
    status: str
    attempts: tuple[DeliveryAttempt, ...]


def _private_root(path: Path) -> Path:
    root = path.resolve(strict=True)
    info = root.stat()
    if not root.is_dir() or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError("Use a private lab directory")
    return root


def _transport(target: WebhookHostTarget, settings: ApplicationRuntimeSettings):
    try:
        if os.name != "posix" or re.fullmatch(r"[0-9a-f]{24}", target.instance_id) is None:
            raise ValueError("Invalid lab target")
        expected = _private_root(settings.root) / target.instance_id / "run" / "service.sock"
        if target.socket_path != str(expected) or expected.resolve() != expected:
            raise ValueError("Invalid lab socket")
        secret = read_regular(_private_root(settings.key_root) / f"{target.instance_id}.key", 32)
        if len(secret) != 32:
            raise ValueError("Invalid lab key")
    except (OSError, RuntimeError, ValueError):
        raise WebhookRejected("Webhook delivery target is unavailable") from None
    return expected, secret


def _send_once(target, path, secret, attempt, receipt):
    event_id, body = receipt
    executor = OperationExecutorV1(module_id=target.module_id, instance_id=target.instance_id,
                                   artifact_sha256=target.artifact_sha256)
    message = sign_message({
        "version": TRANSPORT_VERSION, "request_id": attempt.attempt_id, "timestamp": int(time.time()),
        "operation_id": target.operation_id,
        "payload": {"receipt_id": attempt.receipt_id, "event_id": event_id,
                    "body_base64": base64.b64encode(body).decode("ascii")},
        "context": {"audience": "internal", "correlation_id": attempt.attempt_id,
                    "idempotency_key": attempt.receipt_id, "executor": executor.model_dump()},
    }, secret)
    deadline = time.monotonic() + min(3, target.timeout_seconds)
    dispatch_started = False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(remaining(deadline))
            connection.connect(str(path))
            connection.settimeout(remaining(deadline))
            dispatch_started = True  # A partial send also has an unknown outcome.
            send_message(connection, message)
            response = verify_message(read_frame(connection, deadline, max_bytes=4096), secret,
                                      expected_request_id=attempt.attempt_id)
    except (OSError, TypeError, ValueError, ApplicationTransportError):
        return "unconfirmed" if dispatch_started else "not_dispatched"
    if (set(response) != {"version", "request_id", "timestamp", "ok", "result", "signature"}
            or type(response["version"]) is not int or response["ok"] is not True):
        return "unconfirmed"
    if response["result"] == {"status": "accepted"}:
        return "delivered"
    if response["result"] == {"status": "rejected"}:
        return "rejected"
    return "unconfirmed"


def deliver_one(inbox: WebhookInbox, admission: ReviewedWebhookAdmission,
                settings: ApplicationRuntimeSettings, receipt_id: str) -> DeliveryAttempt:
    """Claim under the current approval; never send a second attempt for a receipt."""
    if not isinstance(receipt_id, str):
        raise WebhookRejected("Webhook receipt is unavailable")
    return _deliver(inbox, admission, settings, receipt_id)


def consume_pending(inbox: WebhookInbox, admission: ReviewedWebhookAdmission,
                    settings: ApplicationRuntimeSettings) -> DeliveryCycle:
    """One opt-in local cycle; no daemon, polling or automatic retry."""
    attempts = []
    status = "limit_reached"
    for _ in range(MAX_ATTEMPTS_PER_CYCLE):
        try:
            attempt = _deliver(inbox, admission, settings, None)
        except (sqlite3.Error, WebhookRejected):
            status = "blocked"
            break
        if attempt is None:
            status = "drained"
            break
        attempts.append(attempt)
        if attempt.status in {"unconfirmed", "not_dispatched"}:
            status = "paused"
            break
    return DeliveryCycle(status, tuple(attempts))


def _deliver(inbox, admission, settings, receipt_id):
    try:
        if os.name != "posix" or _private_root(inbox.path.parent) != inbox.path.parent or inbox.path.is_symlink():
            raise ValueError("Invalid lab inbox")
    except (OSError, RuntimeError, ValueError):
        raise WebhookRejected("Webhook receipt is unavailable") from None
    with admission.hold_delivery() as target:
        path, secret = _transport(target, settings)
        if receipt_id is None:
            # Don't consume queued receipts when the socket is already absent.
            # It may still disappear after the claim; that attempt is final.
            if not path.is_socket():
                raise WebhookRejected("Webhook delivery target is unavailable")
            claimed = inbox.claim_next_delivery(admission.binding_sha256)
            if claimed is None:
                return None
        else:
            claimed = inbox.claim_delivery(receipt_id, admission.binding_sha256)
        attempt, receipt = claimed
    if receipt is None:
        return attempt
    # Release the Core authority fence before connecting or waiting. An already
    # admitted attempt cannot be recalled; revocation prevents any new claims.
    status = _send_once(target, path, secret, attempt, receipt)
    if status == "unconfirmed":
        return attempt
    try:
        return inbox.finish_delivery(attempt, status)
    except (sqlite3.Error, WebhookRejected):
        return attempt  # No durable confirmation, so still do not replay.
