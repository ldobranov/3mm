"""Small stable SDK exposed to supervised application extension services."""

from __future__ import annotations

from dataclasses import dataclass, field
from contextlib import closing, contextmanager
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import time
from typing import Callable, Iterator, Mapping, Protocol, Sequence
import uuid
from datetime import UTC, datetime

from three_mm_protocol.diagnostics import DiagnosticSession, DiagnosticSpan
from three_mm_application_sdk.files import (
    ApplicationFile,
    ApplicationFileLimits,
    ApplicationFileStorage,
    ApplicationFileStorageError,
)
from three_mm_application_sdk.scoped_files import (
    ApplicationFileExecutionUnconfirmed,
    ApplicationScopedFileStorage,
)
from three_mm_application_sdk.scoped_media import ApplicationScopedMediaStorage
from three_mm_protocol.application_requirements import ApplicationPlatformRequirementV1, ApplicationRequirementsRequestV1


REVISION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
from three_mm_protocol.platform_transport import (
    MAX_MESSAGE_BYTES as PLATFORM_MESSAGE_LIMIT, REQUEST_TIMEOUT_SECONDS,
    MAX_CLOCK_SKEW_SECONDS, ERROR_REASONS, ENVELOPE_FIELDS, PlatformDiscoveryV1,
    canonical, read_frame, remaining,
)
SDK_VERSION = "1.3"
SUPPORTED_SDK_VERSIONS = ("1.0", "1.1", "1.2", "1.3")


class ApplicationPlatformError(RuntimeError):
    def __init__(self, message, *, reason="operation_failed", phase="execution_unconfirmed"):
        super().__init__(message)
        self.reason = reason
        self.phase = phase
        self.retryable = False  # The SDK never replays an operation automatically.


class ApplicationPlatformClient:
    """Signed installation-scoped platform access over the existing Unix socket."""

    def __init__(self, socket_path: Path, instance_id: str, secret: bytes, *,
                 diagnostics: DiagnosticSession | None = None, timeout_seconds: float | None = None) -> None:
        import math
        if timeout_seconds is not None and (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= REQUEST_TIMEOUT_SECONDS):
            raise ValueError("SDK timeout exceeds its transport budget")
        self.socket_path = socket_path
        self.instance_id = instance_id
        self.secret = secret
        self.diagnostics = diagnostics
        self.timeout_seconds = timeout_seconds

    def _canonical(self, value: dict[str, object]) -> bytes:
        return canonical(value)

    def discover_platform(self) -> dict[str, object]:
        """Fresh supported contract and generations, never a grant or cached lease."""
        try:
            result = PlatformDiscoveryV1.model_validate(self._call("platform.discover", {}))
            if result.instance_id != self.instance_id:
                raise ValueError("Discovery installation changed")
        except ValueError as exc:
            raise ApplicationPlatformError("Platform discovery is invalid", reason="response_invalid") from exc
        return result.model_dump(mode="json")

    def discover_requirements(self, requirements: Sequence[Mapping[str, object]]) -> dict[str, object]:
        """Observe required/optional transport functions and approved command bindings.

        No provider selection, grants, mutation, retry or human permission claim.
        Every execution must still pass its ordinary fresh admission checks.
        """
        from three_mm_application_sdk.discovery import discover_requirements
        return discover_requirements(self, requirements)

    def discover_resources(self, scopes: Sequence[str]) -> dict[str, object]:
        """Observe only this installation's current scoped resources; no selection."""
        from three_mm_protocol.application_resources import ResourceDiscoveryRequestV1, ResourceDiscoveryV1
        request = ResourceDiscoveryRequestV1(scopes=scopes if isinstance(scopes, str) else tuple(scopes))
        value = self._call('platform.discover', {'resource_scopes':list(request.scopes)})
        try:
            result = ResourceDiscoveryV1.model_validate_json(json.dumps(value))
            if result.instance_id != self.instance_id or tuple(item.scope for item in result.resources) != request.scopes:
                raise ValueError('Resource observation identity changed')
        except ValueError as exc:
            raise ApplicationPlatformError('Resource observation is invalid', reason='response_invalid') from exc
        return result.model_dump(mode='json')

    def _delegation_call(self, action: str, delegation_id: str) -> dict[str, object]:
        from three_mm_protocol.application_delegation import DelegationReceiptV1
        if not isinstance(delegation_id, str) or re.fullmatch(r"[0-9a-f]{32}", delegation_id) is None:
            raise ValueError("Delegation ID is invalid")
        result = DelegationReceiptV1.model_validate_json(json.dumps(self._call(action, {"delegation_id": delegation_id})))
        if result.delegation_id != delegation_id or result.executor.instance_id != self.instance_id:
            raise ApplicationPlatformError("Delegation result belongs to another executor", reason="response_invalid")
        return result.model_dump(mode="json")

    def execute_delegation(self, delegation_id: str) -> dict[str, object]:
        """Consume one exact Core-issued operation; call from a worker, never retry."""
        from three_mm_application_sdk.transaction_guard import require_delegation_worker
        require_delegation_worker()
        return self._delegation_call("delegation.execute", delegation_id)

    def lookup_delegation(self, delegation_id: str) -> dict[str, object]:
        """Read the sealed outcome; never dispatch or infer rollback from a timeout."""
        return self._delegation_call("delegation.lookup", delegation_id)

    def _call(self, action: str, payload: dict[str, object]) -> dict[str, object]:
        request_id = f"platform_{uuid.uuid4().hex}"
        if self.diagnostics is None:
            return self._exchange(action, payload, request_id)
        with DiagnosticSpan(self.diagnostics, request_id, "sdk.call", operation=action, instance_id=self.instance_id) as span:
            try:
                return self._exchange(action, payload, request_id)
            except ApplicationPlatformError as exc:
                span.end("denied" if exc.reason == "operation_denied" else "error", exc.reason)
                raise

    def _exchange(self, action: str, payload: dict[str, object], request_id: str) -> dict[str, object]:
        from three_mm_application_sdk.transaction_guard import (
            require_outside_relational_transaction,
        )

        require_outside_relational_transaction()
        if set(payload) & ENVELOPE_FIELDS:
            raise ApplicationPlatformError("Reserved platform fields", reason="request_invalid", phase="not_dispatched")
        request: dict[str, object] = {
            "version": 1, "request_id": request_id, "timestamp": int(time.time()),
            "instance_id": self.instance_id, "action": action, **payload,
        }
        try:
            request["signature"] = hmac.new(self.secret, self._canonical(request), hashlib.sha256).hexdigest()
            encoded = json.dumps(request, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
        except (ValueError, TypeError, RecursionError) as exc:
            raise ApplicationPlatformError("Platform request is invalid", reason="request_invalid", phase="not_dispatched") from exc
        if len(encoded) > PLATFORM_MESSAGE_LIMIT:
            raise ApplicationPlatformError("Platform request is too large", reason="request_invalid", phase="not_dispatched")
        deadline = time.monotonic() + (REQUEST_TIMEOUT_SECONDS if self.timeout_seconds is None else self.timeout_seconds)
        phase = "not_dispatched"
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(remaining(deadline))
                connection.connect(str(self.socket_path))
                phase = "execution_unconfirmed"  # Partial send is already ambiguous.
                connection.settimeout(remaining(deadline))
                connection.sendall(encoded)
                response = read_frame(connection, deadline)
        except TimeoutError as exc:
            raise ApplicationPlatformError("Platform deadline exceeded", reason="deadline_exceeded", phase=phase) from exc
        except OSError as exc:
            raise ApplicationPlatformError("Application platform service is unavailable", reason="transport_unavailable", phase=phase) from exc
        except ValueError as exc:
            raise ApplicationPlatformError("Platform response is invalid", reason="response_invalid") from exc
        if (response.get("request_id") != request_id or type(response.get("version")) is not int
                or response["version"] != 1 or type(response.get("timestamp")) is not int):
            raise ApplicationPlatformError("Platform response does not match", reason="response_invalid")
        signature = response.get("signature")
        try:
            expected = hmac.new(self.secret, self._canonical(response), hashlib.sha256).hexdigest()
        except (ValueError, TypeError, RecursionError) as exc:
            raise ApplicationPlatformError("Platform response is invalid", reason="response_invalid") from exc
        if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
            raise ApplicationPlatformError("Platform response signature is invalid", reason="response_invalid")
        if abs(int(time.time()) - response["timestamp"]) > MAX_CLOCK_SKEW_SECONDS:
            raise ApplicationPlatformError("Platform response has expired", reason="response_invalid")
        if response.get("ok") is not True:
            error, reason = response.get("error"), response.get("reason")
            if response.get("ok") is not False or not isinstance(reason, str) or reason not in ERROR_REASONS:
                raise ApplicationPlatformError("Platform error response is invalid", reason="response_invalid")
            raise ApplicationPlatformError(error if isinstance(error, str) else "Platform operation failed", reason=reason)
        result = response.get("result")
        if not isinstance(result, dict):
            raise ApplicationPlatformError("Platform response is invalid", reason="response_invalid")
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

    def publish_event(self, publication_id: str, *, event_id: str,
            payload: Mapping[str, object], occurred_at: datetime) -> dict[str, object]:
        """Publish one exact declared event; persist/reuse the SAME ID on retry.

        No automatic outbox drain, replay, device fallback or new ID on timeout.
        Old Core runtimes reject this additive SDK 1.3 method as unsupported.
        """
        from three_mm_protocol.application_event_publication import (
            ApplicationEventPublishRequestV1, ApplicationEventPublicationReceiptV1,
        )
        request = ApplicationEventPublishRequestV1(publication_request_version=1,
            publication_id=publication_id, event_id=event_id, payload=dict(payload), occurred_at=occurred_at)
        try:
            result = self._call('event.publish', {'publication': request.model_dump(mode='json')})
        except ApplicationPlatformError as error:
            # Earlier gateways route unknown actions through checkpoint parsing.
            # Report that explicit refusal; never retry through device ingestion.
            if str(error) in {'Checkpoint identity is invalid', 'Platform action is unsupported'}:
                raise ApplicationPlatformError('Core does not support application event publication') from error
            raise
        try:
            receipt = ApplicationEventPublicationReceiptV1.model_validate(result)
        except ValueError as error:
            raise ApplicationPlatformError('Publication receipt is invalid') from error
        if receipt.event_id != request.event_id or receipt.publication_id != request.publication_id:
            raise ApplicationPlatformError('Publication receipt does not match')
        return receipt.model_dump(mode='json')

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
        from three_mm_protocol.installation_peer_v2 import parse_peer
        return parse_peer(PeerOutboundStatusV1, self._call("installation.peers.enroll", {"link_id": link_id})).model_dump(mode="json")

    def get_installation_peer_capabilities(self) -> dict[str, object]:
        """Require approval-binding v2 explicitly; never downgrade silently."""
        from three_mm_protocol.installation_peer_v2 import PeerCapabilitiesV2
        return PeerCapabilitiesV2.model_validate(self._call("installation.peers.capabilities", {})).model_dump(mode="json")

    def list_installation_peers(self) -> dict[str, object]:
        from three_mm_protocol.installation_peer_v2 import PeerInboundStatusV2
        result = self._call("installation.peers.list", {})
        for value in result.get("inbound", []):
            if value.get("peer_version") == 2:
                PeerInboundStatusV2.model_validate(value)
        return result

    def read_installation_peer(self, binding_id: str) -> dict[str, object]:
        """Read one configured outbound binding under an exact current grant.

        Additive SDK 1.3 operation. Old Core refuses; never fall back to listing,
        enrollment or remote calls. Credential expiry is intentionally unknown.
        """
        from three_mm_protocol.application_peer_read import ApplicationPeerReadV1

        if type(binding_id) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,95}", binding_id) is None:
            raise ValueError("Peer binding identity is invalid")
        result = self._call("installation.peers.read", {"binding_id": binding_id})
        try:
            response = ApplicationPeerReadV1.model_validate(result)
        except ValueError as error:
            raise ApplicationPlatformError("Peer read response is invalid") from error
        if response.binding_id != binding_id:
            raise ApplicationPlatformError("Peer read response does not match")
        return response.model_dump(mode="json")

    def approve_installation_peer(self, binding_id: str, *, expected_generation: int,
                                  expected_metadata_revision: int | None = None,
                                  expected_metadata_hash: str | None = None) -> dict[str, object]:
        """Receiver approval after the extension's own ownership/ACL checks."""
        from three_mm_protocol.installation_peer import PeerEnrollmentResultV1
        from three_mm_protocol.installation_peer_v2 import parse_peer
        payload = {"binding_id": binding_id, "expected_generation": expected_generation}
        if expected_metadata_revision is not None or expected_metadata_hash is not None:
            from three_mm_protocol.installation_peer_v2 import PeerApprovalReviewV2
            review = PeerApprovalReviewV2(
                expected_generation=expected_generation,
                expected_metadata_revision=expected_metadata_revision,
                expected_metadata_hash=expected_metadata_hash,
            )
            payload.update(review.model_dump(mode="json"))
        return parse_peer(PeerEnrollmentResultV1, self._call("installation.peers.approve", payload)).model_dump(mode="json")

    def revoke_installation_peer(self, peer_id: str, *, direction: str) -> dict[str, object]:
        return self._call("installation.peers.revoke", {"peer_id": peer_id, "direction": direction})

    def rotate_installation_peer(self, link_id: str) -> dict[str, object]:
        from three_mm_protocol.installation_peer import PeerOutboundStatusV1
        from three_mm_protocol.installation_peer_v2 import parse_peer
        return parse_peer(PeerOutboundStatusV1, self._call("installation.peers.rotate", {"link_id": link_id})).model_dump(mode="json")

    def get_installation_status(self, link_id: str) -> dict[str, object]:
        from three_mm_protocol.installation_peer import InstallationProjectionV1
        result = self._call("installation.status.get", {"link_id": link_id})
        return InstallationProjectionV1.model_validate(result).model_dump(mode="json")

    def report_installation_status(self, link_id: str, *, report_id: str) -> dict[str, object]:
        """Core projects approved fields; no caller-supplied report/config payload."""
        return self._call("installation.peers.report", {"link_id": link_id, "report_id": report_id})

    def discover_command(self, binding_id: str) -> dict[str, object]:
        """Observe a declared command's granted resource; never select or retry."""
        from three_mm_protocol.application_command_discovery import (
            CommandDiscoveryRequestV1, CommandDiscoveryV1,
        )
        request = CommandDiscoveryRequestV1(binding_id=binding_id)
        result = self._call("command.discover", request.model_dump(mode="json"))
        try:
            observation = CommandDiscoveryV1.model_validate_json(json.dumps(result))
            if observation.binding_id != binding_id or observation.access == "not_evaluated":
                raise ValueError("Discovery binding changed")
        except ValueError as exc:
            raise ApplicationPlatformError("Command discovery is invalid", reason="response_invalid") from exc
        return observation.model_dump(mode="json")

    def submit_task(self, task_id: str, *, request_id: str, payload: Mapping[str, object],
                    due_at: datetime, not_after: datetime) -> dict[str, object]:
        """Admit once; a lost reply must be resolved by lookup_task, never retry."""
        from three_mm_protocol.application_tasks import TaskSubmitV1
        request = TaskSubmitV1(task_id=task_id, request_id=request_id, payload=dict(payload),
            due_at=due_at, not_after=not_after)
        return self._task_result("task.submit", {"task": request.model_dump(mode="json")}, task_id, request_id)

    def lookup_task(self, task_id: str, *, request_id: str) -> dict[str, object]:
        from three_mm_protocol.application_tasks import TaskLookupV1
        request = TaskLookupV1(task_id=task_id, request_id=request_id)
        return self._task_result("task.lookup", {"lookup": request.model_dump(mode="json")}, task_id, request_id)

    def cancel_task(self, task_id: str, *, request_id: str) -> dict[str, object]:
        """Only queued work can be cancelled; running work is returned unchanged."""
        from three_mm_protocol.application_tasks import TaskLookupV1
        request = TaskLookupV1(task_id=task_id, request_id=request_id)
        return self._task_result("task.cancel", {"lookup": request.model_dump(mode="json")}, task_id, request_id)

    def create_task_schedule(self, task_id: str, *, request_id: str, payload: Mapping[str, object],
                             rule: Mapping[str, object], start_at: datetime, end_at: datetime,
                             max_occurrences: int = 1_000_000, history_limit: int = 16,
                             start_window_seconds: int = 5) -> dict[str, object]:
        from three_mm_protocol.application_tasks import TaskScheduleCreateV1
        request = TaskScheduleCreateV1(task_id=task_id, request_id=request_id, payload=dict(payload),
            rule=dict(rule), start_at=start_at, end_at=end_at, max_occurrences=max_occurrences,
            history_limit=history_limit, start_window_seconds=start_window_seconds)
        return self._schedule_result("task.schedule.create", {"schedule": request.model_dump(mode="json")}, task_id, request_id)

    def lookup_task_schedule(self, task_id: str, *, request_id: str) -> dict[str, object]:
        from three_mm_protocol.application_tasks import TaskScheduleLookupV1
        query = TaskScheduleLookupV1(task_id=task_id, request_id=request_id)
        return self._schedule_result("task.schedule.lookup", {"lookup": query.model_dump(mode="json")}, task_id, request_id)

    def cancel_task_schedule(self, task_id: str, *, request_id: str) -> dict[str, object]:
        from three_mm_protocol.application_tasks import TaskScheduleLookupV1
        query = TaskScheduleLookupV1(task_id=task_id, request_id=request_id)
        return self._schedule_result("task.schedule.cancel", {"lookup": query.model_dump(mode="json")}, task_id, request_id)

    def _schedule_result(self, action, payload, task_id, request_id):
        from three_mm_protocol.application_tasks import TaskScheduleStatusV1
        response = self._call(action, payload)
        try:
            result = TaskScheduleStatusV1.model_validate_json(json.dumps(response))
            if result.task_id != task_id or result.request_id != request_id:
                raise ValueError("Schedule response identity changed")
        except ValueError as error:
            raise ApplicationPlatformError("Schedule response is invalid", reason="response_invalid") from error
        return result.model_dump(mode="json")

    def submit_task_command(self, execution, binding_id: str, *, request_id: str,
                            arguments: Mapping[str, object], ttl_seconds: int = 10) -> dict[str, object]:
        """One task-bound command admission. Lost replies require lookup only."""
        from three_mm_protocol.application_tasks import TaskExecutionV1
        if isinstance(execution, TaskExecutionV1):
            execution = execution.model_dump(mode="json")
        context = TaskExecutionV1.model_validate(execution)
        return self._call("command.submit", {"command": {"binding_id": binding_id,
            "request_id": request_id, "arguments": dict(arguments), "ttl_seconds": ttl_seconds},
            "task_execution": context.model_dump(mode="json")})

    def lookup_task_command(self, task_run_id: str, binding_id: str, *, request_id: str) -> dict[str, object]:
        from three_mm_protocol.application_tasks import task_command_request_id
        return self.command_lookup(binding_id=binding_id,
            request_id=task_command_request_id(task_run_id, binding_id, request_id))

    def start_task(self, execution) -> dict[str, object]:
        """Host-only one-use start gate; never automatically retry this call."""
        from three_mm_protocol.application_tasks import TaskExecutionV1, TaskStartV1
        if isinstance(execution, TaskExecutionV1): execution = execution.model_dump(mode="json")
        execution = TaskExecutionV1.model_validate(execution)
        result = self._call("task.start", {"execution": execution.model_dump(mode="json")})
        try:
            receipt = TaskStartV1.model_validate_json(json.dumps(result))
            if receipt.task_run_id != execution.task_run_id or receipt.task_id != execution.task_id:
                raise ValueError("Task start identity changed")
        except ValueError as error:
            raise ApplicationPlatformError("Task start is invalid", reason="response_invalid") from error
        return receipt.model_dump(mode="json")

    def task_progress(self, execution, progress: int) -> dict[str, object]:
        from three_mm_protocol.application_tasks import TaskProgressV1, TaskExecutionV1, TaskStatusV1
        if isinstance(execution, TaskExecutionV1):
            execution = execution.model_dump(mode="json")
        request = TaskProgressV1.model_validate({"execution": execution, "progress": progress})
        response = self._call("task.progress", {"progress": request.model_dump(mode="json")})
        try:
            result = TaskStatusV1.model_validate_json(json.dumps(response))
            if result.task_run_id != request.execution.task_run_id or result.task_id != request.execution.task_id:
                raise ValueError("Task progress identity changed")
        except ValueError as error:
            raise ApplicationPlatformError("Task progress is invalid", reason="response_invalid") from error
        return result.model_dump(mode="json")

    def _task_result(self, action, payload, task_id, request_id):
        from three_mm_protocol.application_tasks import TaskStatusV1
        response = self._call(action, payload)
        try:
            result = TaskStatusV1.model_validate_json(json.dumps(response))
            if result.task_id != task_id or result.request_id != request_id:
                raise ValueError("Task response identity changed")
        except ValueError as error:
            raise ApplicationPlatformError("Task response is invalid", reason="response_invalid") from error
        return result.model_dump(mode="json")

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
    # Trusted host adapter, not a package-supplied grant. Keyword-only preserves
    # the old constructor/clock positions for SDK 1.0–1.3 applications.
    file_storage: ApplicationFileStorage | ApplicationScopedMediaStorage | None = field(
        default=None, kw_only=True, repr=False
    )
    platform_requirements: tuple[ApplicationPlatformRequirementV1, ...] = field(default=(), kw_only=True)

    def __post_init__(self) -> None:
        if type(self.platform_requirements) is not tuple or any(
                not isinstance(item, ApplicationPlatformRequirementV1) for item in self.platform_requirements):
            raise ValueError('Platform requirements must be validated package declarations')
        if self.platform_requirements:
            ApplicationRequirementsRequestV1(requirements=self.platform_requirements)
        if self.file_storage is not None and (
            not isinstance(self.file_storage, (ApplicationFileStorage, ApplicationScopedMediaStorage))
            or self.file_storage.data_dir != self.data_dir
        ):
            raise ValueError("Private file adapter must belong to this context")

    @property
    def files(self) -> ApplicationFileStorage | ApplicationScopedMediaStorage:
        """Host-selected own-file adapter; legacy defaults do not imply a grant."""
        return (
            self.file_storage
            if self.file_storage is not None
            else ApplicationFileStorage(self.data_dir)
        )


@dataclass(frozen=True, slots=True)
class InstallationMachineActor:
    """Core-verified installation subject, not an extension payload claim."""
    installation_id: str
    key_id: str
    binding_id: str
    generation: int
    scopes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OperationActor:
    """Observed initiator from a Core-authenticated invocation, never a grant.

    Application-specific memberships and customer/business roles are not inferred
    from the platform administrator flag. This value is not a delegation token.
    """
    kind: str
    user_id: int | None = None
    subject_id: str | None = None
    terminal_id: str | None = None
    installation_id: str | None = None
    platform_administrator: bool = False


@dataclass(frozen=True, slots=True)
class OperationContext:
    """Identity and retry metadata supplied for one operation invocation."""

    audience: str
    correlation_id: str
    user_id: int | None = None
    idempotency_key: str | None = None
    machine: InstallationMachineActor | None = None
    task_execution: object | None = None
    terminal_id: str | None = field(default=None, kw_only=True)
    permission_ids: tuple[str, ...] = field(default=(), kw_only=True)
    platform_administrator: bool = field(default=False, kw_only=True)
    subject_id: str | None = field(default=None, kw_only=True)
    executor: object | None = field(default=None, kw_only=True)
    delegation: object | None = field(default=None, kw_only=True)

    @property
    def initiator(self) -> OperationActor:
        return self.actor

    @property
    def actor(self) -> OperationActor:
        if self.machine is not None:
            return OperationActor("installation", installation_id=self.machine.installation_id)
        if self.task_execution is not None:
            return OperationActor("worker")
        if self.user_id is not None:
            return OperationActor("user", user_id=self.user_id,
                subject_id=self.subject_id, platform_administrator=self.platform_administrator)
        if self.terminal_id is not None:
            return OperationActor("kiosk", terminal_id=self.terminal_id)
        return OperationActor("anonymous" if self.audience == "public" else "service")

    def has_application_permission(self, permission_id: str) -> bool:
        """This invocation's human app permission, independent of service grants.

        A snapshot is not a future execution permit; Core rechecks each operation.
        """
        return self.audience in {"operator", "administrator"} and self.user_id is not None and permission_id in self.permission_ids

    @classmethod
    def from_platform(cls, value: Mapping[str, object]) -> "OperationContext":
        """Parse context only after the host authenticates the Core envelope."""
        audience = value.get("audience")
        if not isinstance(audience, str) or audience not in {"public", "kiosk", "operator", "administrator", "internal",
                "installation_peer", "installation_bootstrap"}:
            raise ValueError("Operation audience is invalid")
        human = audience in {"operator", "administrator"}
        user_id = value.get("user_id")
        subject_id = value.get("subject_id")
        terminal_id = value.get("terminal_id")
        administrator = value.get("platform_administrator", audience == "administrator")
        permissions = value.get("permission_ids", [])
        if (human and (type(user_id) is not int or user_id < 1 or not isinstance(subject_id, str)
                    or re.fullmatch(r"usr_[0-9a-f]{32}", subject_id) is None)
                or not human and (user_id is not None or subject_id is not None)
                or type(administrator) is not bool or not human and administrator
                or audience == "administrator" and not administrator):
            raise ValueError("Operation human identity is invalid")
        if (audience == "kiosk" and (not isinstance(terminal_id, str)
                or re.fullmatch(r"[0-9a-f]{32}", terminal_id) is None)
                or audience != "kiosk" and terminal_id is not None):
            raise ValueError("Operation kiosk identity is invalid")
        if (type(permissions) is not list or len(permissions) > 96
                or any(not isinstance(item, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,95}", item) is None for item in permissions)
                or len(set(permissions)) != len(permissions) or not human and permissions):
            raise ValueError("Operation application permissions are invalid")
        from three_mm_protocol.application_delegation import OperationExecutorV1, OperationDelegationV1
        executor = value.get("executor")
        if executor is not None:
            executor = OperationExecutorV1.model_validate(executor)
        delegation = value.get("delegation")
        if delegation is not None:
            delegation = OperationDelegationV1.model_validate_json(json.dumps(delegation))
            if (audience != "operator" or administrator or delegation.initiator.user_id != user_id
                    or delegation.initiator.subject_id != subject_id
                    or executor != delegation.executor or delegation.required_permission not in permissions):
                raise ValueError("Delegation cannot change its initiator, executor or human permission")
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
        task = value.get("task_execution")
        if task is not None:
            from three_mm_protocol.application_tasks import TaskExecutionV1
            if audience != "internal" or machine is not None or value.get("user_id") is not None:
                raise ValueError("Task execution requires an internal machine context")
            task = TaskExecutionV1.model_validate(task)
        return cls(audience=str(audience), correlation_id=str(value.get("correlation_id", "")),
                   user_id=user_id, subject_id=subject_id, terminal_id=terminal_id, permission_ids=tuple(permissions),
                   platform_administrator=administrator,
                   executor=executor, delegation=delegation,
                   idempotency_key=value.get("idempotency_key") if isinstance(value.get("idempotency_key"), str) else None,
                   machine=machine, task_execution=task)


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
    "ApplicationFile",
    "ApplicationFileLimits",
    "ApplicationFileStorage",
    "ApplicationFileStorageError",
    "ApplicationFileExecutionUnconfirmed",
    "ApplicationScopedFileStorage",
    "ApplicationMigration",
    "ApplicationOutboxItem",
    "ApplicationPlatformClient",
    "ApplicationPlatformError",
    "ApplicationService",
    "ApplicationStorage",
    "Clock",
    "OperationContext",
    "OperationActor",
    "InstallationMachineActor",
    "SystemClock",
]


def verify_installation_proof(proof, *, expected_identity, expected_request, now=None):
    """Shared verifier; caller must independently trust expectations/consume nonce."""
    from three_mm_protocol.installation_identity import verify_installation_proof as verify

    return verify(proof, expected_identity=expected_identity, expected_request=expected_request, now=now)
