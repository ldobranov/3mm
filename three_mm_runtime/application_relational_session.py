"""Private prepared-host metadata session; no SQL broker or activation bypass.

Production activation remains blocked until the protected lifecycle coordinator
can publish/restore the record coherently. A record is NOT a grant. This reader
never prepares a database, imports migrations or repairs stale lineage/keys.
HMAC authenticates reviewed-native transport, not hostile Python isolation.
"""

import hashlib
import json
import os
import socket
import sqlite3
import stat
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from three_mm_application_sdk.relational_receipts import _RelationalReceiptStore
from three_mm_application_sdk.relational_wire import (
    Digest,
    Identity,
    Millis,
    canonical,
    profile_digest,
    verify_metadata,
)
from three_mm_protocol.application_extension import ApplicationRelationalStorageV1
from three_mm_runtime.application_transport import (
    ApplicationTransportError,
    sign_message,
    verify_message,
)

MAX_METADATA_BYTES = 8192
MAX_INVOCATIONS = 128
_LIFECYCLE_UID = 0  # Fixed production owner; not environment/package configuration.
Instance = Annotated[str, Field(pattern=r"^[0-9a-f]{24}$")]
Boot = Annotated[
    str,
    Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _PreparedLifecycle(_Closed):
    version: Annotated[int, Field(strict=True, ge=1, le=1)]
    instance_id: Instance
    lifecycle_id: Identity
    database_lineage: Identity
    owner_sha256: Digest
    package_sha256: Digest
    service_sha256: Digest
    configuration_sha256: Digest
    profile_sha256: Digest
    schema_revision: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")]
    recovery_generation: Identity
    signature: Digest


class _Invocation(_Closed):
    version: Annotated[int, Field(strict=True, ge=1, le=1)]
    invocation_id: Identity
    operation_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")]
    instance_id: Instance
    runtime_nonce: Identity
    boot_id: Boot
    lifecycle_sha256: Digest
    binding_sha256: Digest
    authority_epoch: Identity
    recovery_generation: Identity
    started_at_ms: Millis
    deadline_ms: Millis
    signature: Digest

    @model_validator(mode="after")
    def budget(self):
        if not 0 < self.deadline_ms - self.started_at_ms <= 30000:
            raise ValueError("Invalid enclosing operation budget")
        return self


class _HostMetadata(_Closed):
    lifecycle: _PreparedLifecycle
    runtime_nonce: Identity
    boot_id: Boot
    clock_ms: Millis
    invocation: _Invocation | None


def _clock():
    if os.name != "posix" or not hasattr(time, "CLOCK_BOOTTIME"):
        raise ValueError("Relational host clock unavailable")
    boot = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    return boot, time.clock_gettime_ns(time.CLOCK_BOOTTIME) // 1_000_000


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate relational metadata")
        value[key] = item
    return value


def _nonfinite(_value):
    raise ValueError("Non-finite relational metadata")


def _decode(payload, *, limit=MAX_METADATA_BYTES):
    if not 0 < len(payload) <= limit:
        raise ValueError("Relational metadata limit exceeded")
    try:
        return json.loads(payload, object_pairs_hook=_unique, parse_constant=_nonfinite)
    except RecursionError:
        raise ValueError("Relational metadata nesting limit exceeded") from None


def _regular(path, *, protected=False):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Relational metadata requires lifecycle recovery")
    if protected and (info.st_uid != _LIFECYCLE_UID or info.st_mode & 0o022):
        raise ValueError("Relational lifecycle metadata is not protected")
    return info


def _protected_directory(path):
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != _LIFECYCLE_UID
        or info.st_mode & 0o022
    ):
        raise ValueError("Relational lifecycle directory is not protected")


def _prepared(instance_root, secret):
    """Readonly readiness only. Missing/stale state is never self-repaired."""
    if os.name != "posix" or type(secret) is not bytes or len(secret) != 32:
        raise ValueError("Relational prepared host unavailable")
    _protected_directory(instance_root.parent)
    _protected_directory(instance_root)
    active = instance_root / "active.json"
    if _regular(active, protected=True).st_size > 131072:
        raise ValueError("Relational active metadata limit exceeded")
    metadata = _decode(active.read_bytes(), limit=131072)
    # Any unresolved activation/database rollback stops normal startup.
    if tuple(instance_root.glob(".activation-*.rollback")) or tuple(
        instance_root.glob(".database-*.rollback")
    ):
        raise ValueError("Relational lifecycle recovery is pending")
    path = instance_root / "relational.json"
    info = _regular(path, protected=True)
    if info.st_size > MAX_METADATA_BYTES:
        raise ValueError("Relational metadata limit exceeded")
    record = _PreparedLifecycle.model_validate(_decode(path.read_bytes())).model_dump(
        mode="json"
    )
    verify_metadata(secret, "lifecycle", record)
    declaration = ApplicationRelationalStorageV1.model_validate(
        metadata["storage"]["relational"]
    )
    revision = metadata["storage"]["schema_revision"]
    configuration = metadata.get("configuration")
    if type(configuration) is not dict or metadata.get("wheel") != "service.whl":
        raise ValueError("Relational active metadata invalid")
    expected = {
        "instance_id": metadata["instance_id"],
        "package_sha256": metadata["sha256"],
        "schema_revision": revision,
        "configuration_sha256": hashlib.sha256(canonical(configuration)).hexdigest(),
        "profile_sha256": profile_digest(declaration, revision),
    }
    if instance_root.name != record["instance_id"] or any(
        record[key] != item for key, item in expected.items()
    ):
        raise ValueError("Relational lifecycle identity changed")
    _protected_directory(instance_root / "releases")
    release = instance_root / "releases" / record["package_sha256"]
    _protected_directory(release)
    wheel = release / "service.whl"
    _regular(wheel, protected=True)
    with wheel.open("rb") as stream:
        if (
            hashlib.file_digest(stream, "sha256").hexdigest()
            != record["service_sha256"]
        ):
            raise ValueError("Relational prepared artifact changed")
    data = instance_root / "data"
    if not stat.S_ISDIR(data.lstat().st_mode) or not stat.S_ISDIR(
        (instance_root / "run").lstat().st_mode
    ):
        raise ValueError("Relational own namespace unavailable")
    database = data / "state.sqlite3"
    _regular(database)
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = data / ("state.sqlite3" + suffix)
        if os.path.lexists(sidecar):
            _regular(sidecar)
    store = _RelationalReceiptStore(
        database_lineage=record["database_lineage"],
        schema_revision=revision,
        secret=secret,
    )
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0)
    try:
        deadline = _clock()[1] + 2000
        connection.set_progress_handler(lambda: int(_clock()[1] >= deadline), 1000)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("BEGIN")
        store._validate(connection)
    finally:
        connection.close()
    return record


def _read(connection):
    chunks = bytearray()
    while b"\n" not in chunks and len(chunks) <= MAX_METADATA_BYTES:
        chunk = connection.recv(min(4096, MAX_METADATA_BYTES + 1 - len(chunks)))
        if not chunk:
            break
        chunks.extend(chunk)
    if b"\n" not in chunks or len(chunks) > MAX_METADATA_BYTES:
        raise ValueError("Relational metadata limit exceeded")
    return _decode(chunks.split(b"\n", 1)[0])


def _send(connection, value):
    encoded = canonical(value) + b"\n"
    if len(encoded) > MAX_METADATA_BYTES:
        raise ValueError("Relational metadata limit exceeded")
    connection.sendall(encoded)


def _call_host_metadata(path, secret, *, timeout=2):
    identifier = uuid.uuid4().hex
    request = sign_message(
        {
            "version": 1,
            "request_id": identifier,
            "timestamp": int(time.time()),
            "action": "context",
            "payload": {},
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
    if (
        response.get("ok") is not True
        or type(response.get("version")) is not int
        or set(response)
        != {"version", "request_id", "timestamp", "ok", "result", "signature"}
    ):
        raise ApplicationTransportError("Relational host metadata unavailable")
    value = _HostMetadata.model_validate(response["result"]).model_dump(mode="json")
    verify_metadata(secret, "lifecycle", value["lifecycle"])
    if value["invocation"] is not None:
        verify_metadata(secret, "invocation", value["invocation"])
    return value


class _RelationalHostSession:
    """Independent metadata worker for the future host dispatch adapter.

    Only the host invocation boundary accepts a Core-signed ticket. Socket
    requests cannot set an invocation, lineage, deadline or maintenance mode.
    No package factory/health code, SQLite callback or application payload here.
    """

    def __init__(self, instance_root, secret, group_id=None):
        self._record = _prepared(instance_root, secret)
        self._secret, self._group_id = secret, group_id
        self._nonce, self._boot = uuid.uuid4().hex, _clock()[0]
        self.path = instance_root / "run" / "relational.sock"
        self._lock, self._stop = threading.Lock(), threading.Event()
        self._active, self._seen = None, {}
        self._server = self._thread = None

    @contextmanager
    def invocation(self, ticket, *, operation_id):
        ticket = _Invocation.model_validate(ticket).model_dump(mode="json")
        verify_metadata(self._secret, "invocation", ticket)
        with self._lock:
            boot, now = _clock()
            if (
                self._server is None
                or self._stop.is_set()
                or self._active is not None
                or ticket["operation_id"] != operation_id
                or not ticket["started_at_ms"] <= now < ticket["deadline_ms"]
                or any(
                    ticket[key] != value
                    for key, value in {
                        "instance_id": self._record["instance_id"],
                        "runtime_nonce": self._nonce,
                        "boot_id": self._boot,
                        "recovery_generation": self._record["recovery_generation"],
                        "lifecycle_sha256": hashlib.sha256(
                            canonical(self._record)
                        ).hexdigest(),
                    }.items()
                )
                or boot != self._boot
            ):
                raise ValueError("Relational invocation is stale or foreign")
            self._seen = {
                key: expires for key, expires in self._seen.items() if expires > now
            }
            if (
                ticket["invocation_id"] in self._seen
                or len(self._seen) >= MAX_INVOCATIONS
            ):
                raise ValueError("Relational invocation consumed or capacity exhausted")
            self._seen[ticket["invocation_id"]] = ticket["deadline_ms"]
            self._active = ticket
        try:
            yield
        finally:
            with self._lock:
                self._active = None

    def _context(self, action, payload):
        if action != "context" or type(payload) is not dict or payload:
            raise ValueError("Relational host accepts metadata lookup only")
        with self._lock:
            boot, now = _clock()
            if boot != self._boot or self._stop.is_set():
                raise ValueError("Relational host session expired")
            active = self._active
            return {
                "lifecycle": self._record,
                "runtime_nonce": self._nonce,
                "boot_id": boot,
                "clock_ms": now,
                # An expired invocation can report an original commit receipt;
                # admission/verifier independently refuse any further SQL.
                "invocation": active,
            }

    def _permit_expectations(self, transaction_id, mode):
        """Host-selected values for the signed permit verifier, never its reply."""
        with self._lock:
            ticket = self._active
            if (
                self._stop.is_set()
                or ticket is None
                or _clock()[1] >= ticket["deadline_ms"]
            ):
                raise ValueError("No active relational host invocation")
            return {
                "transaction_id": transaction_id,
                "mode": mode,
                "profile_sha256": self._record["profile_sha256"],
                "instance_id": self._record["instance_id"],
                "runtime_nonce": self._nonce,
                "database_lineage": self._record["database_lineage"],
                "boot_id": self._boot,
                "authority_epoch": ticket["authority_epoch"],
                "recovery_generation": self._record["recovery_generation"],
                "binding_sha256": ticket["binding_sha256"],
            }

    def __enter__(self):
        if self._server is not None or self._stop.is_set():
            raise ValueError("Relational host session cannot restart")
        self.path.unlink(missing_ok=True)
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self._server.bind(str(self.path))
            if self._group_id is not None:
                os.chown(self.path, -1, self._group_id)
            os.chmod(self.path, 0o660)
            self._server.listen(4)
            self._server.settimeout(0.2)
            self._thread = threading.Thread(
                target=self._run, daemon=True, name="3mm-relational-metadata"
            )
            self._thread.start()
        except Exception:
            self._server.close()
            self.path.unlink(missing_ok=True)
            self._stop.set()
            raise
        return self

    def __exit__(self, *_args):
        self._stop.set()
        self._server.close()
        self._thread.join(timeout=3)
        self.path.unlink(missing_ok=True)

    def _run(self):
        while not self._stop.is_set():
            try:
                connection, _ = self._server.accept()
            except OSError:
                continue
            with connection:
                connection.settimeout(1)
                identifier = "invalid"
                try:
                    request = verify_message(_read(connection), self._secret)
                    identifier = request["request_id"]
                    if (
                        type(request["version"]) is not int
                        or request["version"] != 1
                        or set(request)
                        != {
                            "version",
                            "request_id",
                            "timestamp",
                            "action",
                            "payload",
                            "signature",
                        }
                    ):
                        raise ValueError("Unknown relational request fields")
                    result = self._context(request["action"], request["payload"])
                    response = {"ok": True, "result": result}
                except Exception:
                    response = {
                        "ok": False,
                        "error": "Relational host metadata unavailable",
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
                            self._secret,
                        ),
                    )
                except (OSError, ValueError):
                    pass  # No mutations/admission/replay occur on this socket.
