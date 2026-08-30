"""Authenticated, bounded local RPC transport for application extensions."""

from __future__ import annotations

import hashlib
import hmac
import json
import socket
import time
import uuid
from pathlib import Path


TRANSPORT_VERSION = 1
MAX_MESSAGE_BYTES = 1024 * 1024
MAX_CLOCK_SKEW_SECONDS = 30


class ApplicationTransportError(RuntimeError):
    pass


def _canonical(value: dict[str, object]) -> bytes:
    unsigned = {key: item for key, item in value.items() if key != "signature"}
    return json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sign_message(value: dict[str, object], secret: bytes) -> dict[str, object]:
    signed = dict(value)
    signed["signature"] = hmac.new(
        secret,
        _canonical(signed),
        hashlib.sha256,
    ).hexdigest()
    return signed


def verify_message(
    value: object,
    secret: bytes,
    *,
    expected_request_id: str | None = None,
    now: int | None = None,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ApplicationTransportError("Application service message is invalid")
    signature = value.get("signature")
    timestamp = value.get("timestamp")
    request_id = value.get("request_id")
    if (
        value.get("version") != TRANSPORT_VERSION
        or not isinstance(signature, str)
        or len(signature) != 64
        or not isinstance(timestamp, int)
        or isinstance(timestamp, bool)
        or not isinstance(request_id, str)
    ):
        raise ApplicationTransportError("Application service message is invalid")
    expected = hmac.new(secret, _canonical(value), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ApplicationTransportError("Application service signature is invalid")
    current = int(time.time()) if now is None else now
    if abs(current - timestamp) > MAX_CLOCK_SKEW_SECONDS:
        raise ApplicationTransportError("Application service message has expired")
    if expected_request_id is not None and request_id != expected_request_id:
        raise ApplicationTransportError("Application service response does not match")
    return value


def read_message(connection: socket.socket) -> dict[str, object]:
    payload = b""
    while len(payload) <= MAX_MESSAGE_BYTES:
        chunk = connection.recv(min(65536, MAX_MESSAGE_BYTES + 1 - len(payload)))
        if not chunk:
            break
        payload += chunk
        if b"\n" in payload:
            break
    if len(payload) > MAX_MESSAGE_BYTES or b"\n" not in payload:
        raise ApplicationTransportError("Application service message is too large")
    try:
        value = json.loads(payload.split(b"\n", 1)[0])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApplicationTransportError("Application service message is invalid") from exc
    if not isinstance(value, dict):
        raise ApplicationTransportError("Application service message is invalid")
    return value


def send_message(connection: socket.socket, value: dict[str, object]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    ) + b"\n"
    if len(encoded) > MAX_MESSAGE_BYTES:
        raise ApplicationTransportError("Application service message is too large")
    connection.sendall(encoded)


class ApplicationServiceClient:
    def __init__(self, socket_path: Path, secret: bytes, timeout_seconds: float = 10) -> None:
        self._socket_path = socket_path
        self._secret = secret
        self._timeout_seconds = timeout_seconds

    def invoke(
        self,
        operation_id: str,
        payload: dict[str, object],
        context: dict[str, object],
    ) -> dict[str, object]:
        request_id = uuid.uuid4().hex
        request = sign_message(
            {
                "version": TRANSPORT_VERSION,
                "request_id": request_id,
                "timestamp": int(time.time()),
                "operation_id": operation_id,
                "payload": payload,
                "context": context,
            },
            self._secret,
        )
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self._timeout_seconds)
                connection.connect(str(self._socket_path))
                send_message(connection, request)
                response = read_message(connection)
        except OSError as exc:
            raise ApplicationTransportError(
                "Application extension service is unavailable"
            ) from exc
        verified = verify_message(
            response,
            self._secret,
            expected_request_id=request_id,
        )
        if verified.get("ok") is not True:
            error = verified.get("error")
            raise ApplicationTransportError(
                error if isinstance(error, str) else "Application operation failed"
            )
        result = verified.get("result")
        if not isinstance(result, dict):
            raise ApplicationTransportError("Application service response is invalid")
        return result
