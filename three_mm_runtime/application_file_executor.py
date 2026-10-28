"""Bounded target-owned file worker, separate from the occupied service socket.

This uses the existing reviewed-native HMAC transport, NOT malicious-code
isolation. Core owns durable admission/deduplication; a fresh worker nonce stops
old admissions executing after runtime restart/rollback. No automatic replay.
"""

import json
import os
import re
import socket
import threading
import time
import uuid

from three_mm_application_sdk import ApplicationFileLimits, ApplicationFileStorage
from three_mm_application_sdk.file_wire import (
    MAX_FILE_MESSAGE_BYTES,
    MAX_SCOPED_FILE_BYTES,
    execute_file_request,
    parse_file_request,
)
from three_mm_protocol.application_extension import ApplicationPrivateFilesV1, ApplicationPrivateFilesV2
from three_mm_application_sdk import media_wire
from three_mm_application_sdk.media_store import ApplicationMediaStore
from three_mm_runtime.application_transport import (
    sign_message,
    verify_message,
    ApplicationTransportError,
)


def _clock_ms():
    if not hasattr(time, "CLOCK_BOOTTIME"):
        raise ValueError("Private files require the supported runtime clock")
    return time.clock_gettime_ns(time.CLOCK_BOOTTIME) // 1_000_000


def _read(connection):
    chunks = bytearray()
    while b"\n" not in chunks and len(chunks) <= MAX_FILE_MESSAGE_BYTES:
        chunk = connection.recv(min(65536, MAX_FILE_MESSAGE_BYTES + 1 - len(chunks)))
        if not chunk:
            break
        chunks.extend(chunk)
    if len(chunks) > MAX_FILE_MESSAGE_BYTES or b"\n" not in chunks:
        raise ValueError("Private file message exceeds its limit")

    def unique(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError("Private file message has duplicate fields")
            result[name] = value
        return result

    return json.loads(chunks.split(b"\n", 1)[0], object_pairs_hook=unique)


def _send(connection, value):
    encoded = json.dumps(value, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(encoded) > MAX_FILE_MESSAGE_BYTES:
        raise ValueError("Private file message exceeds its limit")
    connection.sendall(encoded)


def call_file_executor(path, secret, action, payload, *, timeout=8):
    identifier = uuid.uuid4().hex
    request = sign_message(
        {
            "version": 1,
            "request_id": identifier,
            "timestamp": int(time.time()),
            "action": action,
            "payload": payload,
        },
        secret,
    )
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(str(path))
        _send(connection, request)
        response = verify_message(
            _read(connection), secret, expected_request_id=identifier
        )
    if response.get("ok") is not True or type(response.get("result")) is not dict:
        raise ApplicationTransportError(
            "Private file runtime did not confirm execution"
        )
    return response["result"]


class ApplicationFileExecutor:
    def __init__(self, instance_root, metadata, secret, group_id=None):
        self.root, self.metadata, self.secret, self.group_id = (
            instance_root,
            metadata,
            secret,
            group_id,
        )
        declaration_type = ApplicationPrivateFilesV2 if metadata['storage']['private_files'].get('file_contract_version') == 2 else ApplicationPrivateFilesV1
        self.declaration = declaration_type.model_validate(
            metadata["storage"]["private_files"]
        )
        self.streaming = self.declaration.file_contract_version == 2
        if not self.streaming and self.declaration.max_file_bytes > MAX_SCOPED_FILE_BYTES:
            raise ValueError("Private file request exceeds the scoped runtime limit")
        self.storage = ApplicationMediaStore(instance_root / 'data', self.declaration) if self.streaming else ApplicationFileStorage(
            instance_root / "data",
            mode=self.declaration.mode,
            limits=ApplicationFileLimits(
                self.declaration.max_file_bytes,
                self.declaration.max_total_bytes,
                self.declaration.max_files,
            ),
        )
        self.nonce, self.seen = uuid.uuid4().hex, {}
        self.path = instance_root / "run" / "files.sock"
        self.stop_event = threading.Event()
        self.server = self.thread = None

    def __enter__(self):
        self.path.unlink(missing_ok=True)
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(self.path))
        if self.group_id is not None:
            os.chown(self.path, -1, self.group_id)
        os.chmod(self.path, 0o660)
        self.server.listen(4)
        self.server.settimeout(0.2)
        self.thread = threading.Thread(
            target=self._run, daemon=True, name="3mm-private-file-worker"
        )
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.stop_event.set()
        self.server.close()
        self.thread.join(timeout=3)
        self.path.unlink(missing_ok=True)

    def _execute(self, action, payload):
        if action == 'probe' and payload == {}:
            from three_mm_application_sdk.media_provider import probe_provider
            return {**self._execute('hello', {}), 'media_provider':
                probe_provider() if self.streaming and self.declaration.media_transforms else 'unavailable'}
        if action == "hello" and payload == {}:
            return {
                "instance_id": self.metadata["instance_id"],
                "package_sha256": self.metadata["sha256"],
                "runtime_nonce": self.nonce,
                "clock_ms": _clock_ms(),
                "declaration": self.declaration.model_dump(mode="json"),
            }
        if (
            action != "execute"
            or type(payload) is not dict
            or set(payload) != {"admission", "request"}
        ):
            raise ValueError("Private file execution request is invalid")
        admission = payload["admission"]
        request = media_wire.parse_media_request(payload['request']) if self.streaming else parse_file_request(payload['request'])[0]
        if type(admission) is not dict or set(admission) != {
            "runtime_nonce",
            "instance_id",
            "package_sha256",
            "declaration",
            "deadline_ms",
            "authority_epoch",
        } | ({'owner', 'link_epoch'} if self.streaming else set()):
            raise ValueError("Private file admission is invalid")
        now = _clock_ms()
        declaration = type(self.declaration).model_validate(admission["declaration"])
        if (
            admission["runtime_nonce"] != self.nonce
            or admission["instance_id"] != self.metadata["instance_id"]
            or admission["package_sha256"] != self.metadata["sha256"]
            or declaration != self.declaration
            or type(admission["deadline_ms"]) is not int
            or not now < admission["deadline_ms"] <= now + 5000
            or type(admission["authority_epoch"]) is not str
            or not re.fullmatch(r"[0-9a-f]{32}", admission["authority_epoch"])
        ):
            raise ValueError(
                "Private file admission is stale or belongs to another runtime"
            )
        self.seen = {
            key: expires for key, expires in self.seen.items() if expires > now
        }
        if request["request_id"] in self.seen or len(self.seen) >= 128:
            raise ValueError(
                "Private file admission was consumed or the worker is busy"
            )
        self.seen[request["request_id"]] = admission["deadline_ms"]
        # Consume before opening the namespace. An error/sync timeout is not replay.
        if self.streaming:
            if (type(admission['owner']) is not str or not 1 <= len(admission['owner']) <= 320
                    or type(admission['link_epoch']) is not str or not re.fullmatch(r'[0-9a-f]{64}', admission['link_epoch'])):
                raise ValueError('Streaming file actor is invalid')
            return self.storage.execute(request, admission['owner'], admission['link_epoch'])
        return execute_file_request(self.storage, request)

    def _run(self):
        while not self.stop_event.is_set():
            try:
                connection, _ = self.server.accept()
            except OSError:
                continue
            with connection:
                connection.settimeout(2)
                identifier = "invalid"
                try:
                    request = verify_message(_read(connection), self.secret)
                    identifier = request["request_id"]
                    result = self._execute(
                        request.get("action"), request.get("payload")
                    )
                    response = {"ok": True, "result": result}
                except Exception:
                    response = {
                        "ok": False,
                        "error": "Private file runtime did not confirm execution",
                    }
                try:
                    _send(
                        connection,
                        sign_message(
                            {
                                "version": 1,
                                "request_id": identifier,
                                "timestamp": int(time.time()),
                                **response,
                            },
                            self.secret,
                        ),
                    )
                except (OSError, ValueError):
                    pass  # Completion may have happened. Core keeps uncertainty, no replay.
