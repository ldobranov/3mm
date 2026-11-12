"""Private loopback pilot transport. No signing key, inbox or Core access."""

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import socket
import sys
import time
from uuid import uuid4

from packages.platform_wire import peer_identity, read_frame, remaining
from packages.protocol.public_webhooks import MAX_WEBHOOK_BYTES


PILOT_VERSION = 1
PILOT_SECONDS = 3
PILOT_FRAME_BYTES = 90 * 1024
PILOT_REPLY_BYTES = 512
PILOT_STATUSES = frozenset({202, 403, 409, 503})
SIGNED_HEADERS = ("X-3mm-Webhook-Id", "X-3mm-Webhook-Timestamp", "X-3mm-Webhook-Signature")
SIGNED_LIMITS = (128, 11, 67)
PILOT_ID = re.compile(r"[0-9a-f]{32}")


def valid_signed_fields(fields):
    return (isinstance(fields, (list, tuple)) and len(fields) == len(SIGNED_LIMITS)
            and all(isinstance(value, str) and value.isascii() and 1 <= len(value) <= limit
                    for value, limit in zip(fields, SIGNED_LIMITS, strict=True)))


@dataclass(frozen=True, slots=True)
class WebhookPilotClient:
    path: str
    socket_path: Path
    broker_uid: int | None = None

    def __post_init__(self):
        if (sys.platform != "linux" or len(self.path) > 160
                or not re.fullmatch(r"/webhooks/[a-z0-9_-]+(?:/[a-z0-9_-]+)*", self.path)
                or not self.socket_path.is_absolute()
                or (self.broker_uid is not None and (type(self.broker_uid) is not int or self.broker_uid < 0))):
            raise ValueError("Invalid local webhook pilot")

    def submit(self, fields: tuple[str, str, str], body: bytes) -> tuple[int, str | None]:
        if not valid_signed_fields(fields) or not 1 <= len(body) <= MAX_WEBHOOK_BYTES:
            return 503, None
        request_id = uuid4().hex
        message = json.dumps({"version": PILOT_VERSION, "request_id": request_id, "path": self.path,
            "signed": fields, "body_base64": base64.b64encode(body).decode("ascii")},
            separators=(",", ":")).encode("ascii") + b"\n"
        deadline = time.monotonic() + PILOT_SECONDS
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(remaining(deadline))
                connection.connect(str(self.socket_path))
                expected_uid = os.geteuid() if self.broker_uid is None else self.broker_uid
                if peer_identity(connection)[1] != expected_uid:
                    return 503, None
                connection.settimeout(remaining(deadline))
                connection.sendall(message)
                response = read_frame(connection, deadline, max_bytes=PILOT_REPLY_BYTES)
        except (OSError, ValueError):
            return 503, None
        if (set(response) != {"version", "request_id", "status", "receipt_id"}
                or type(response["version"]) is not int or response["version"] != PILOT_VERSION
                or response["request_id"] != request_id
                or type(response["status"]) is not int or response["status"] not in PILOT_STATUSES):
            return 503, None
        status, receipt = response["status"], response["receipt_id"]
        if status == 202:
            return (status, receipt) if isinstance(receipt, str) and PILOT_ID.fullmatch(receipt) else (503, None)
        return (status, None) if receipt is None else (503, None)
