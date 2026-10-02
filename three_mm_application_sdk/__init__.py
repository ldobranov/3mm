"""Small stable SDK exposed to supervised application extension services."""

from __future__ import annotations

from dataclasses import dataclass, field
from contextlib import closing, contextmanager
import base64
import hashlib
import hmac
import json
from pathlib import Path
import re
import socket
import sqlite3
import time
from typing import Callable, Iterator, Mapping, Protocol, Sequence
import uuid
from datetime import UTC, datetime


REVISION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
PLATFORM_MESSAGE_LIMIT = 6 * 1024 * 1024
SDK_VERSION = "1.2"
SUPPORTED_SDK_VERSIONS = ("1.0", "1.1", "1.2")


class ApplicationPlatformError(RuntimeError):
    pass


class ApplicationPlatformClient:
    """Signed Unix-socket access to platform connectors and checkpoints."""

    def __init__(self, socket_path: Path, instance_id: str, secret: bytes) -> None:
        self.socket_path = socket_path
        self.instance_id = instance_id
        self.secret = secret

    def _canonical(self, value: dict[str, object]) -> bytes:
        return json.dumps(
            {key: item for key, item in value.items() if key != "signature"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def _call(self, action: str, payload: dict[str, object]) -> dict[str, object]:
        request_id = f"platform_{uuid.uuid4().hex}"
        request: dict[str, object] = {
            "version": 1,
            "request_id": request_id,
            "timestamp": int(time.time()),
            "instance_id": self.instance_id,
            "action": action,
            **payload,
        }
        request["signature"] = hmac.new(
            self.secret, self._canonical(request), hashlib.sha256
        ).hexdigest()
        encoded = json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > PLATFORM_MESSAGE_LIMIT:
            raise ApplicationPlatformError("Platform request is too large")
        response_bytes = b""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(35)
                connection.connect(str(self.socket_path))
                connection.sendall(encoded)
                while b"\n" not in response_bytes and len(response_bytes) <= PLATFORM_MESSAGE_LIMIT:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    response_bytes += chunk
        except OSError as exc:
            raise ApplicationPlatformError("Application platform service is unavailable") from exc
        if b"\n" not in response_bytes or len(response_bytes) > PLATFORM_MESSAGE_LIMIT:
            raise ApplicationPlatformError("Platform response is invalid")
        try:
            response = json.loads(response_bytes.split(b"\n", 1)[0])
        except (UnicodeError, ValueError) as exc:
            raise ApplicationPlatformError("Platform response is invalid") from exc
        if not isinstance(response, dict) or response.get("request_id") != request_id:
            raise ApplicationPlatformError("Platform response does not match")
        signature = response.get("signature")
        expected = hmac.new(self.secret, self._canonical(response), hashlib.sha256).hexdigest()
        if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
            raise ApplicationPlatformError("Platform response signature is invalid")
        if abs(int(time.time()) - int(response.get("timestamp", 0))) > 30:
            raise ApplicationPlatformError("Platform response has expired")
        if response.get("ok") is not True:
            error = response.get("error")
            raise ApplicationPlatformError(
                error if isinstance(error, str) else "Platform operation failed"
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise ApplicationPlatformError("Platform response is invalid")
        return result

    def connector_request(
        self,
        connector_id: str,
        *,
        method: str,
        path: str,
        body: bytes = b"",
        headers: Mapping[str, str] | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        return self._call(
            "connector.request",
            {
                "connector_id": connector_id,
                "connector_request_id": request_id or f"connector_{uuid.uuid4().hex}",
                "method": method,
                "path": path,
                "body_base64": base64.b64encode(body).decode("ascii"),
                "headers": dict(headers or {}),
                "idempotency_key": idempotency_key,
            },
        )

    def get_checkpoint(self, checkpoint_id: str) -> dict[str, object]:
        return self._call("checkpoint.get", {"checkpoint_id": checkpoint_id})

    def get_installation_identity(self) -> dict[str, object]:
        """Read whole-Core public identity; requires declared platform permission."""
        from three_mm_protocol.installation_identity import InstallationIdentityResultV1

        result = self._call("installation.identity.get", {})
        return InstallationIdentityResultV1.model_validate(result).model_dump(mode="json")

    def prove_installation_identity(self, request: Mapping[str, object]) -> dict[str, object]:
        """Narrow receiver-bound possession proof, not consent or enrollment."""
        from three_mm_protocol.installation_identity import InstallationProofRequestV1, InstallationProofV1

        validated = InstallationProofRequestV1.model_validate(dict(request))
        result = self._call("installation.identity.prove", {"proof_request": validated.model_dump(mode="json")})
        proof = InstallationProofV1.model_validate(result)
        if proof.request != validated:
            raise ApplicationPlatformError("Installation proof response does not match")
        return proof.model_dump(mode="json")

    def enroll_installation_peer(self, link_id: str) -> dict[str, object]:
        """Resume a durable, locally approved enrollment; never invent an origin."""
        from three_mm_protocol.installation_peer import PeerOutboundStatusV1
        return PeerOutboundStatusV1.model_validate(self._call("installation.peers.enroll", {"link_id": link_id})).model_dump(mode="json")

    def list_installation_peers(self) -> dict[str, object]:
        return self._call("installation.peers.list", {})

    def approve_installation_peer(self, binding_id: str, *, expected_generation: int) -> dict[str, object]:
        """Receiver approval after the extension's own ownership/ACL checks."""
        from three_mm_protocol.installation_peer import PeerEnrollmentResultV1
        return PeerEnrollmentResultV1.model_validate(self._call("installation.peers.approve", {"binding_id": binding_id, "expected_generation": expected_generation})).model_dump(mode="json")

    def revoke_installation_peer(self, peer_id: str, *, direction: str) -> dict[str, object]:
        return self._call("installation.peers.revoke", {"peer_id": peer_id, "direction": direction})

    def rotate_installation_peer(self, link_id: str) -> dict[str, object]:
        from three_mm_protocol.installation_peer import PeerOutboundStatusV1
        return PeerOutboundStatusV1.model_validate(self._call("installation.peers.rotate", {"link_id": link_id})).model_dump(mode="json")

    def get_installation_status(self, link_id: str) -> dict[str, object]:
        from three_mm_protocol.installation_peer import InstallationProjectionV1
        result = self._call("installation.status.get", {"link_id": link_id})
        return InstallationProjectionV1.model_validate(result).model_dump(mode="json")

    def report_installation_status(self, link_id: str, *, report_id: str) -> dict[str, object]:
        """Core projects approved fields; no caller-supplied report/config payload."""
        return self._call("installation.peers.report", {"link_id": link_id, "report_id": report_id})

    def submit_command(self, binding_id: str, *, request_id: str,
                       arguments: Mapping[str, object], ttl_seconds: int = 10,
                       direction: str = 'forward', not_after: datetime | None = None) -> dict[str, object]:
        command = {
            'binding_id': binding_id, 'request_id': request_id, 'arguments': dict(arguments),
            'ttl_seconds': ttl_seconds, 'direction': direction}
        if not_after is not None:
            if not isinstance(not_after, datetime) or not_after.utcoffset() is None:
                raise ValueError('not_after requires a datetime with timezone')
            command['not_after'] = not_after.astimezone(UTC).isoformat()
        return self._call('command.submit', {'command': command})

    def command_lookup(self, *, request_id: str, binding_id: str) -> dict[str, object]:
        return self._call('command.lookup', {'lookup': {'request_id': request_id, 'binding_id': binding_id}})

    def command_status(self, command_id: str) -> dict[str, object]:
        return self._call('command.status', {'command_id': command_id})

    def put_checkpoint(
        self,
        checkpoint_id: str,
        value: Mapping[str, object],
        *,
        expected_revision: int,
    ) -> dict[str, object]:
        return self._call(
            "checkpoint.put",
            {
                "checkpoint_id": checkpoint_id,
                "value": dict(value),
                "expected_revision": expected_revision,
            },
        )


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ApplicationMigration:
    revision: str
    apply: Callable[[sqlite3.Connection], None]


@dataclass(frozen=True, slots=True)
class ApplicationOutboxItem:
    outbox_id: str
    event_type: str
    payload: dict[str, object]
    payload_hash: str
    remote_idempotency_key: str
    attempts: int


class ApplicationStorage:
    """Extension-owned SQLite database with forward migrations and outbox."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.database_path = data_dir / "state.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def migrate(
        self,
        migrations: Sequence[ApplicationMigration],
        target_revision: str,
    ) -> None:
        revisions = [migration.revision for migration in migrations]
        if (
            not REVISION_PATTERN.fullmatch(target_revision)
            or any(not REVISION_PATTERN.fullmatch(item) for item in revisions)
            or len(revisions) != len(set(revisions))
            or target_revision not in revisions
        ):
            raise ValueError("Application migration plan is invalid")
        target_index = revisions.index(target_revision)
        selected = list(migrations[: target_index + 1])
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS three_mm_schema_migrations (
                    revision TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS three_mm_outbox (
                    outbox_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    remote_idempotency_key TEXT,
                    state TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT,
                    terminal_result TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_error TEXT
                )
                """
            )
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(three_mm_outbox)")
            }
            additions = {
                "payload_hash": "TEXT",
                "remote_idempotency_key": "TEXT",
                "next_attempt_at": "TEXT",
                "terminal_result": "TEXT",
            }
            for name, declaration in additions.items():
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE three_mm_outbox ADD COLUMN {name} {declaration}"
                    )
            applied = [
                str(row[0])
                for row in connection.execute(
                    "SELECT revision FROM three_mm_schema_migrations ORDER BY rowid"
                )
            ]
        if applied != revisions[: len(applied)] or len(applied) > len(selected):
            raise ValueError("Application database revision is not forward-compatible")
        for migration in selected[len(applied) :]:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                migration.apply(connection)
                connection.execute(
                    "INSERT INTO three_mm_schema_migrations(revision) VALUES (?)",
                    (migration.revision,),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def enqueue_outbox(
        self,
        connection: sqlite3.Connection,
        *,
        outbox_id: str,
        event_type: str,
        payload: Mapping[str, object],
        idempotency_key: str,
    ) -> None:
        payload_json = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        connection.execute(
            """
            INSERT INTO three_mm_outbox(
                outbox_id, event_type, payload_json, payload_hash,
                idempotency_key, remote_idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                outbox_id,
                event_type,
                payload_json,
                hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
                idempotency_key,
                idempotency_key,
            ),
        )

    def update_outbox(
        self,
        outbox_id: str,
        *,
        state: str,
        attempts: int,
        next_attempt_at: datetime | None = None,
        terminal_result: str | None = None,
        last_error: str | None = None,
    ) -> None:
        allowed = {"pending", "retrying", "ambiguous", "failed", "succeeded", "manual_review"}
        if state not in allowed or attempts < 0:
            raise ValueError("Outbox transition is invalid")
        with self._connect() as connection:
            changed = connection.execute(
                """
                UPDATE three_mm_outbox
                SET state = ?, attempts = ?, next_attempt_at = ?, terminal_result = ?,
                    last_error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE outbox_id = ?
                """,
                (
                    state,
                    attempts,
                    next_attempt_at.isoformat() if next_attempt_at else None,
                    terminal_result,
                    last_error,
                    outbox_id,
                ),
            ).rowcount
        if changed != 1:
            raise ValueError("Outbox item was not found")

    def due_outbox(
        self,
        *,
        limit: int = 50,
        now: datetime | None = None,
    ) -> list[ApplicationOutboxItem]:
        if isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("Outbox batch limit is invalid")
        current = (now or datetime.now(UTC)).isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT outbox_id, event_type, payload_json, payload_hash,
                       remote_idempotency_key, attempts
                FROM three_mm_outbox
                WHERE state IN ('pending', 'retrying')
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY created_at, outbox_id
                LIMIT ?
                """,
                (current, limit),
            ).fetchall()
        items: list[ApplicationOutboxItem] = []
        for row in rows:
            payload_json = str(row[2])
            payload_hash = str(row[3] or "")
            if hashlib.sha256(payload_json.encode("utf-8")).hexdigest() != payload_hash:
                raise ValueError("Outbox payload integrity check failed")
            payload = json.loads(payload_json)
            if not isinstance(payload, dict):
                raise ValueError("Outbox payload is invalid")
            remote_key = row[4]
            if not isinstance(remote_key, str) or not remote_key:
                raise ValueError("Outbox remote idempotency identity is invalid")
            items.append(
                ApplicationOutboxItem(
                    outbox_id=str(row[0]),
                    event_type=str(row[1]),
                    payload=payload,
                    payload_hash=payload_hash,
                    remote_idempotency_key=remote_key,
                    attempts=int(row[5]),
                )
            )
        return items

    def status(self) -> dict[str, object]:
        if not self.database_path.is_file():
            return {"revision": None, "outbox": {}}
        with self._connect() as connection:
            revision = connection.execute(
                "SELECT revision FROM three_mm_schema_migrations ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            counts = {
                str(row[0]): int(row[1])
                for row in connection.execute(
                    "SELECT state, COUNT(*) FROM three_mm_outbox GROUP BY state"
                )
            }
        return {"revision": revision[0] if revision else None, "outbox": counts}


@dataclass(frozen=True, slots=True)
class ApplicationContext:
    """Installation-scoped values supplied by the 3mm Extension Host."""

    module_id: str
    version: str
    data_dir: Path
    configuration: Mapping[str, object]
    storage: ApplicationStorage
    platform: ApplicationPlatformClient | None = None
    clock: Clock = field(default_factory=SystemClock)


@dataclass(frozen=True, slots=True)
class InstallationMachineActor:
    """Core-verified installation subject, not an extension payload claim."""
    installation_id: str
    key_id: str
    binding_id: str
    generation: int
    scopes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OperationContext:
    """Identity and retry metadata supplied for one operation invocation."""

    audience: str
    correlation_id: str
    user_id: int | None = None
    idempotency_key: str | None = None
    machine: InstallationMachineActor | None = None

    @classmethod
    def from_platform(cls, value: Mapping[str, object]) -> "OperationContext":
        """Parse context only after the host authenticates the Core envelope."""
        audience = value.get("audience")
        machine = value.get("machine")
        peer_audience = audience in {"installation_peer", "installation_bootstrap"}
        if peer_audience:
            from three_mm_protocol.installation_peer import PEER_SCOPE
            if not isinstance(machine, dict) or value.get("user_id") is not None:
                raise ValueError("Peer operations require a machine-only context")
            if set(machine) != {"installation_id", "key_id", "binding_id", "generation", "scopes"}:
                raise ValueError("Machine context is invalid")
            if not re.fullmatch(r"inst_[0-9a-f]{32}", str(machine["installation_id"])) or not re.fullmatch(r"[0-9a-f]{64}", str(machine["key_id"])) or not re.fullmatch(r"peer_[0-9a-f]{32}", str(machine["binding_id"])):
                raise ValueError("Machine identity is invalid")
            if type(machine["generation"]) is not int or machine["generation"] < 1 or machine["scopes"] != ([PEER_SCOPE] if audience == "installation_peer" else []):
                raise ValueError("Machine generation or scope is invalid")
            machine = InstallationMachineActor(**{**machine, "scopes": tuple(machine["scopes"])})
        elif machine is not None:
            raise ValueError("Machine context is reserved for peer operations")
        user_id = value.get("user_id")
        return cls(audience=str(audience), correlation_id=str(value.get("correlation_id", "")),
                   user_id=user_id if type(user_id) is int else None,
                   idempotency_key=value.get("idempotency_key") if isinstance(value.get("idempotency_key"), str) else None,
                   machine=machine)


class ApplicationService(Protocol):
    """Interface implemented by an application extension service."""

    def handle(
        self,
        operation_id: str,
        payload: dict[str, object],
        context: OperationContext,
    ) -> dict[str, object]: ...


__all__ = [
    "SDK_VERSION",
    "SUPPORTED_SDK_VERSIONS",
    "verify_installation_proof",
    "ApplicationContext",
    "ApplicationMigration",
    "ApplicationOutboxItem",
    "ApplicationPlatformClient",
    "ApplicationPlatformError",
    "ApplicationService",
    "ApplicationStorage",
    "Clock",
    "OperationContext",
    "InstallationMachineActor",
    "SystemClock",
]


def verify_installation_proof(proof, *, expected_identity, expected_request, now=None):
    """Shared verifier; caller must independently trust expectations/consume nonce."""
    from three_mm_protocol.installation_identity import verify_installation_proof as verify

    return verify(proof, expected_identity=expected_identity, expected_request=expected_request, now=now)
