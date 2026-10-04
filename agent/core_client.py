"""Authenticated Agent-to-Core inventory and heartbeat publishing."""

from __future__ import annotations

import logging
import json
import base64
import hashlib
import queue
import uuid
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from agent.module_runtime import AgentModuleRuntime, ModuleLifecycleError
from agent.automation_store import AutomationStore, StoredAutomation
from agent.physical_command_journal import PhysicalCommandFailure, PhysicalCommandJournal
from agent.node_update_transport import NodeUpdateTransport, NodeUpdateTransportError
from agent.node_update_client import NodeUpdateHelperError
from agent.node_update_execution import NodeUpdateExecution
from three_mm_protocol.node_updates import NodeUpdatePrepareRequest
from three_mm_protocol.passage import PassageEventV1
from three_mm_protocol.capability_contracts import CONTRACT_FEATURE, CapabilityContractError
from three_mm_protocol.capability_availability import AVAILABILITY_FEATURE
from agent.inventory import platform_neutral_inventory
from agent import __version__
from agent.runtime_features import RuntimeFeaturePublisher
from three_mm_protocol.node_features import (
    DeviceRuntimeFeaturesV1, FEATURE_COMMANDS, MANDATORY_NODE_FEATURES,
)

# Deprecated requests alias keeps existing embedding/test seams usable. All
# actual HTTP I/O and acknowledgement handling is in the reference adapter.
from agent.device_transport import HttpDeviceTransport, legacy_outbox_record, legacy_outbox_message, requests
from three_mm_protocol.transport import DeviceTransport, DeviceTransportError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from three_mm_protocol import (
    AgentCommand, AgentCommandResult, AgentHeartbeat, AgentInventory,
    AgentReportedState, CapabilityStateReportV1, DeviceDesiredState, DeviceInventoryV2,
    IdentifierScanEventV1,
    DeviceEventV1,
)

logger = logging.getLogger(__name__)
COMMAND_LONG_POLL_SECONDS = 5.0


class DeviceCredential(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    credential_id: str = Field(pattern=r"^cred_[0-9a-f]{32}$")
    credential_secret: str = Field(min_length=32, repr=False)
    hub_endpoint: str | None = None
    api_endpoint: str | None = None


class DeviceCredentialStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "core-credential.json"
        self.binding_path = data_dir / "core-binding.json"

    def load(self) -> DeviceCredential | None:
        if self.path.is_symlink() or self.binding_path.is_symlink():
            raise RuntimeError("Credential files cannot be symbolic links")
        if not self.path.exists():
            return None
        try:
            os.chmod(self.path, 0o600)
            credential = DeviceCredential.model_validate_json(
                self.path.read_text(encoding="utf-8")
            )
            if self.binding_path.exists():
                binding = json.loads(self.binding_path.read_text(encoding="utf-8"))
                if (not isinstance(binding, dict)
                        or binding.get("credential_id") != credential.credential_id
                        or binding.get("device_id") != credential.device_id):
                    raise ValueError("Hub binding does not match the credential")
                credential = DeviceCredential.model_validate({
                    **credential.model_dump(),
                    "hub_endpoint": binding["hub_endpoint"], "api_endpoint": binding["api_endpoint"],
                })
            return credential
        except (OSError, ValueError, KeyError, ValidationError) as exc:
            raise RuntimeError(f"Cannot load Core credential from {self.path}") from exc

    def save(self, credential: DeviceCredential) -> None:
        if self.path.is_symlink() or self.binding_path.is_symlink():
            raise RuntimeError("Credential files cannot be symbolic links")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        if credential.hub_endpoint is not None:
            # Keep the legacy secret-file schema readable by rollback releases.
            binding = self.binding_path.with_suffix(".tmp")
            if binding.is_symlink():
                raise RuntimeError("Credential temporary file cannot be a symbolic link")
            binding.write_text(json.dumps({
                "device_id": credential.device_id, "credential_id": credential.credential_id,
                "hub_endpoint": credential.hub_endpoint, "api_endpoint": credential.api_endpoint,
            }) + "\n", encoding="utf-8")
            os.chmod(binding, 0o600)
            os.replace(binding, self.binding_path)
        temporary = self.path.with_suffix(".tmp")
        if temporary.is_symlink():
            raise RuntimeError("Credential temporary file cannot be a symbolic link")
        temporary.write_text(credential.model_dump_json(indent=2, exclude={"hub_endpoint", "api_endpoint"}) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)


class CommandJournal:
    """Small persistent cache preventing repeated idempotent actions."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "command-journal.json"
        # Keep the old result file readable by rollback releases. A separate
        # proof binds command content AND result; partial writes fail closed.
        self.proof_path = data_dir / "command-journal-proofs.json"
        self._proofs: dict = {}
        if self.proof_path.exists():
            try:
                self._proofs = json.loads(self.proof_path.read_text(encoding="utf-8"))
                if not isinstance(self._proofs, dict):
                    raise ValueError("Invalid receipt proofs")
            except (OSError, ValueError) as exc:
                raise RuntimeError("Cannot load command receipt proofs") from exc
        self._results: dict[str, AgentCommandResult] = {}
        self._unverified: dict[str, object] = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise ValueError("Invalid command journal")
                for key, value in raw.items():
                    try:
                        self._results[key] = AgentCommandResult.model_validate(value)
                    except ValidationError:
                        # Historic receipts may exceed new bounds. Retain their
                        # raw evidence, but never treat them as a cache miss.
                        self._unverified[key] = value
            except (OSError, ValueError, ValidationError) as exc:
                raise RuntimeError(f"Cannot load command journal from {self.path}") from exc

    def get(self, idempotency_key: str) -> AgentCommandResult | None:
        return self._results.get(idempotency_key)

    @staticmethod
    def _digest(value) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

    def get_for_command(self, command: AgentCommand) -> AgentCommandResult | None:
        if command.idempotency_key in self._unverified:
            return AgentCommandResult(
                command_id=command.command_id, device_id=command.device_id,
                status="failed", completed_at=datetime.now(UTC),
                output={"execution_state": "unknown", "recovery_code": "legacy_receipt_invalid"},
                error="Stored receipt requires recovery; automatic replay refused",
            )
        result = self.get(command.idempotency_key)
        if result is None:
            return None
        proof = self._proofs.get(command.idempotency_key)
        expected = {
            "command": self._digest(command.model_dump(mode="json", exclude={"command_id"})),
            "result": self._digest(result.model_dump(mode="json")),
        }
        if proof != expected:
            return AgentCommandResult(
                command_id=command.command_id, device_id=command.device_id,
                status="failed", completed_at=datetime.now(UTC),
                output={"execution_state": "unknown" if proof is None else "conflict"},
                error="Cached receipt cannot verify this command; automatic replay refused",
            )
        return result.model_copy(update={"command_id": command.command_id})

    def save(self, idempotency_key: str, result: AgentCommandResult, *, command: AgentCommand | None = None) -> None:
        if idempotency_key in self._unverified:
            raise RuntimeError("Unverified historical receipt must not be overwritten")
        self._results[idempotency_key] = result
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {**self._unverified, **{key: value.model_dump(mode="json") for key, value in self._results.items()}},
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)
        if command is not None:
            self._proofs[idempotency_key] = {
                "command": self._digest(command.model_dump(mode="json", exclude={"command_id"})),
                "result": self._digest(result.model_dump(mode="json")),
            }
            temporary = self.proof_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self._proofs) + "\n", encoding="utf-8")
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.proof_path)


class ReconciliationState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    applied_revision: int = Field(default=0, ge=0)
    inventory_generation: int = Field(default=0, ge=0)


class ReconciliationStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "reconciliation-state.json"

    def load(self) -> ReconciliationState:
        if not self.path.exists():
            return ReconciliationState()
        try:
            return ReconciliationState.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise RuntimeError(f"Cannot load reconciliation state from {self.path}") from exc

    def save(self, state: ReconciliationState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)


class OutboxEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    suffix: str
    payload: dict
    deduplication_key: str


class OutboxStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "outbox.json"

    def load(self) -> list[OutboxEntry]:
        if not self.path.exists():
            return []
        try:
            return [OutboxEntry.model_validate(item) for item in json.loads(self.path.read_text(encoding="utf-8"))]
        except (OSError, ValueError, ValidationError) as exc:
            raise RuntimeError(f"Cannot load Agent outbox from {self.path}") from exc

    def save(self, entries: list[OutboxEntry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps([entry.model_dump(mode="json") for entry in entries], indent=2) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)

    def enqueue(self, entry: OutboxEntry) -> None:
        entries = [item for item in self.load() if item.deduplication_key != entry.deduplication_key]
        if len(entries) >= 500:
            raise RuntimeError("Agent outbox is full; pending records were preserved")
        entries.append(entry)
        self.save(entries)


@dataclass(slots=True)
class CorePublisher:
    core_url: str
    credential: DeviceCredential
    inventory_provider: Callable[[], AgentInventory | DeviceInventoryV2]
    command_journal: CommandJournal
    reconciliation_store: ReconciliationStore
    outbox: OutboxStore
    started_monotonic: float
    module_runtime: AgentModuleRuntime | None = None
    automation_store: AutomationStore | None = None
    gpio_configuration: object | None = None
    node_update_transport: NodeUpdateTransport | None = None
    node_update_execution: NodeUpdateExecution | None = None
    interval_seconds: int = 30
    inventory_schema_version: int = 1
    # Legacy embedding/test adapter. The production Agent opts in explicitly.
    feature_negotiation: bool = False
    capability_availability: bool = False
    authority_verification: bool = False
    transport: DeviceTransport | None = None
    _runtime_features: RuntimeFeaturePublisher | None = field(init=False, default=None, repr=False)
    _stop: threading.Event = field(init=False, repr=False)
    _thread: threading.Thread | None = field(init=False, default=None, repr=False)
    _event_thread: threading.Thread | None = field(init=False, default=None, repr=False)
    _command_thread: threading.Thread | None = field(init=False, default=None, repr=False)
    _event_queue: queue.Queue[dict] = field(init=False, repr=False)
    _outbox_lock: threading.Lock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.inventory_schema_version) is not int
            or self.inventory_schema_version not in (1, 2)
        ):
            raise ValueError("Inventory schema version must be 1 or 2")
        self.core_url = self.core_url.rstrip("/")
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._event_thread = None
        self._command_thread = None
        self._event_queue = queue.Queue(maxsize=500)
        self._outbox_lock = threading.Lock()
        if self.transport is None:
            from three_mm_protocol.device_authority import DeviceAuthorityStore
            authority_store = DeviceAuthorityStore(self.command_journal.path.parent,
                self.credential.device_id, self.credential.credential_id) if self.authority_verification else None
            self.transport = HttpDeviceTransport(self.core_url, self.credential, authority_store=authority_store)
        if self.transport.device_id != self.credential.device_id:
            raise ValueError("Transport device identity mismatch")
        if self.feature_negotiation:
            self._runtime_features = RuntimeFeaturePublisher(self.core_url, self.credential, transport=self.transport)

    @property
    def headers(self) -> dict[str, str]:
        return getattr(self.transport, "headers", {})

    def start(self) -> None:
        self._event_thread = threading.Thread(
            target=self._run_event_delivery,
            name="3mm-event-publisher",
            daemon=True,
        )
        self._event_thread.start()
        self._command_thread = threading.Thread(
            target=self._run_commands,
            name="3mm-command-receiver",
            daemon=True,
        )
        self._command_thread.start()
        self._thread = threading.Thread(target=self._run, name="3mm-core-publisher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self._event_thread is not None:
            self._event_thread.join(timeout=5)
        if self._command_thread is not None:
            self._command_thread.join(timeout=COMMAND_LONG_POLL_SECONDS + 2)

    def _post(self, suffix: str, payload: dict) -> None:
        # Compatibility boundary for persisted pre-C10 outboxes and optional
        # OTA callbacks, not a transport operation in the protocol contract.
        self.transport.publish(legacy_outbox_message(suffix, payload))

    def _runtime_declaration(self) -> dict:
        features = set(MANDATORY_NODE_FEATURES) | {"inventory_refresh"}
        if self.module_runtime is not None:
            features.update({"module_lifecycle", "application_execution_permits", CONTRACT_FEATURE})
            if self.capability_availability:
                features.add(AVAILABILITY_FEATURE)
        if self.automation_store is not None:
            features.add("local_automations")
        if self.gpio_configuration is not None:
            features.add("gpio_configuration")
        if self.node_update_transport is not None:
            features.add("release_update_prepare")
            support = self._node_update_support()
            if support is not None and support.get("signed_apply_supported") is True:
                features.add("release_update_apply")
        commands = {command for feature in features for command in FEATURE_COMMANDS.get(feature, ())}
        return DeviceRuntimeFeaturesV1(
            device_id=self.credential.device_id, runtime_name="3mm-agent",
            runtime_version=__version__, features=tuple(sorted(features)),
            command_types=tuple(sorted(commands)),
        ).model_dump(mode="json")

    def _negotiated_inventory_version(self) -> int:
        if self._runtime_features is None:
            return self.inventory_schema_version
        return self._runtime_features.inventory_version(self.inventory_schema_version, self._runtime_declaration)

    def _publish_inventory(self) -> None:
        version = self._negotiated_inventory_version()
        report = self.inventory_provider()
        if version == 2 and isinstance(report, AgentInventory):
            report = platform_neutral_inventory(report)
        if version == 1 and isinstance(report, DeviceInventoryV2):
            raise ValueError("Inventory schema 2 cannot be downgraded to fabricated Linux inventory")
        self._post(*legacy_outbox_record(report))

    def _send_or_queue(self, suffix: str, payload: dict, deduplication_key: str) -> bool:
        try:
            self._post(suffix, payload)
            return True
        except DeviceTransportError:
            with self._outbox_lock:
                self.outbox.enqueue(OutboxEntry(suffix=suffix, payload=payload, deduplication_key=deduplication_key))
            return False

    def _flush_outbox(self) -> None:
        with self._outbox_lock:
            remaining: list[OutboxEntry] = []
            entries = self.outbox.load()
            for index, entry in enumerate(entries):
                try:
                    self._post(entry.suffix, entry.payload)
                except DeviceTransportError:
                    remaining.extend(entries[index:])
                    break
            self.outbox.save(remaining)

    def _submit_result(self, result: AgentCommandResult) -> None:
        self._send_or_queue(
            *legacy_outbox_record(result),
            f"command-result:{result.command_id}",
        )

    def publish_event(self, event: dict) -> None:
        event_type = event.get("event_type")
        event_payload = event.get("payload")
        if not isinstance(event_type, str) or not isinstance(event_payload, dict):
            raise ValueError("Agent event must contain an event type and object payload")
        payload = {
            "event_id": f"evt_{uuid.uuid4().hex}",
            "device_id": self.credential.device_id,
            "occurred_at": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "payload": event_payload,
        }
        if event_type == "identifier.scan.v1":
            payload = IdentifierScanEventV1.model_validate(payload).model_dump(mode="json")
        if event_type == 'access.passage.v1':
            payload = PassageEventV1.model_validate(payload).model_dump(mode='json')
        try:
            self._event_queue.put_nowait(payload)
        except queue.Full:
            logger.warning("Agent event delivery queue is full; dropping event %s", payload["event_id"])

    def _deliver_event(self, payload: dict) -> None:
        self._send_or_queue(*legacy_outbox_record(DeviceEventV1.model_validate(payload)), f"event:{payload['event_id']}")
        try:
            self._publish_capability_states()
        except (ModuleLifecycleError, ValidationError) as exc:
            logger.warning("Capability state publish after event failed: %s", exc)

    def _run_event_delivery(self) -> None:
        while not self._stop.is_set() or not self._event_queue.empty():
            try:
                payload = self._event_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._deliver_event(payload)
            except Exception as exc:
                logger.warning("Agent event delivery failed: %s", exc)
            finally:
                self._event_queue.task_done()

    def _publish_capability_states(self) -> None:
        if self.module_runtime is None:
            return
        self._publish_capability_availability()
        observed_at = datetime.now(UTC)
        for capability_id, values in self.module_runtime.capability_states().items():
            report = CapabilityStateReportV1(
                device_id=self.credential.device_id,
                capability_id=capability_id,
                values=values,
                observed_at=observed_at,
            )
            self._send_or_queue(
                *legacy_outbox_record(report),
                f"capability-state:{capability_id}",
            )

    def _publish_capability_availability(self):
        if (self.module_runtime is None or self._runtime_features is None
                or not self._runtime_features.availability_enabled):
            return
        for report in self.module_runtime.availability_reports(self.credential.device_id):
            try:
                self.transport.publish(report)
            except DeviceTransportError as exc:
                logger.warning("Ephemeral capability health was not acknowledged: %s", type(exc).__name__)

    def _node_execution(self) -> NodeUpdateExecution | None:
        if self.node_update_execution is None and self.node_update_transport is not None:
            self.node_update_execution = NodeUpdateExecution(
                data_dir=self.command_journal.path.parent,
                device_id=self.credential.device_id,
                helper=self.node_update_transport.helper,
            )
        return self.node_update_execution

    def _node_update_support(self) -> dict | None:
        execution = self._node_execution()
        if execution is None:
            return None
        try:
            support = execution.helper.support()
            if support.trusted_device_id not in (None, self.credential.device_id):
                raise NodeUpdateHelperError("node_update_device_mismatch")
            return support.model_dump(mode="json")
        except NodeUpdateHelperError:
            return {"schema_version": 1, "signed_apply_supported": False}

    def _poll_command(self, *, wait_seconds: float = 0.0) -> None:
        self._negotiated_inventory_version()
        command = self.transport.receive_command(timeout_seconds=wait_seconds)
        if command is None:
            return
        if command.device_id != self.credential.device_id:
            raise ValueError('Command device identity mismatch')
        cached = self.command_journal.get_for_command(command)
        if cached is not None:
            replay = cached.model_copy(update={"command_id": command.command_id})
            self._submit_result(replay)
            return

        if command.command_type == 'agent.gpio.configure' and self.gpio_configuration is not None:
            journal = PhysicalCommandJournal(self.command_journal.path.parent)
            def configure_gpio():
                if (command.expires_at - command.created_at).total_seconds() > 10:
                    raise PhysicalCommandFailure('not_executed', 'GPIO configuration requires a deadline of at most ten seconds')
                return self.gpio_configuration.apply(command.payload, self.module_runtime)
            result = journal.execute(command, configure_gpio)
            self._submit_result(result)
            self._reconcile_state()
            return

        if command.command_type in {'capability.invoke', 'application.capability.invoke'} and self.module_runtime is not None:
            journal = PhysicalCommandJournal(self.command_journal.path.parent)
            def authorize():
                started = time.monotonic()
                body = self.transport.authorize_execution(command.command_id)
                if body.get('authorized') is not True or body.get('command_id') != command.command_id or time.monotonic() - started > 2:
                    raise ValueError('Execution permit was not received promptly')
            def invoke_capability():
                if (self.capability_availability
                        and not self.module_runtime.capability_healthy(command.payload.get('capability_id'))):
                    raise PhysicalCommandFailure('not_executed', 'Capability runtime is unavailable')
                try:
                    self.module_runtime.validate_invocation(command.payload)
                except CapabilityContractError as exc:
                    raise PhysicalCommandFailure('not_executed', str(exc)) from exc
                return self.module_runtime.invoke(
                    command.payload['capability_id'], command.payload['action'], command.payload.get('arguments', {}),
                    contract_version=command.payload.get('contract_version'),
                    contract_digest=command.payload.get('contract_digest'))
            result = journal.execute(command, invoke_capability,
                authorize=authorize if command.command_type == 'application.capability.invoke' else None)
            self._submit_result(result)
            self._publish_capability_states()
            return

        completed_at = datetime.now(UTC)
        if command.expires_at <= completed_at:
            return
        if command.command_type == "agent.refresh_inventory":
            try:
                self._publish_inventory()
                result = AgentCommandResult(
                    command_id=command.command_id,
                    device_id=self.credential.device_id,
                    status="succeeded",
                    completed_at=datetime.now(UTC),
                    output={"inventory_published": True},
                )
            except DeviceTransportError as exc:
                result = AgentCommandResult(
                    command_id=command.command_id,
                    device_id=self.credential.device_id,
                    status="failed",
                    completed_at=datetime.now(UTC),
                    error=f"Inventory publish failed: {type(exc).__name__}",
                )
        elif (
            command.command_type
            == "agent.update.prepare"
            and self.node_update_transport is not None
        ):
            try:
                request = (
                    NodeUpdatePrepareRequest.model_validate(
                        command.payload
                    )
                )

                if (
                    request.device_id
                    != self.credential.device_id
                ):
                    raise NodeUpdateTransportError(
                        "node_update_device_mismatch"
                    )

                prepared = (
                    self.node_update_transport.prepare(
                        request
                    )
                )

                result = AgentCommandResult(
                    command_id=command.command_id,
                    device_id=self.credential.device_id,
                    status="succeeded",
                    completed_at=datetime.now(UTC),
                    output={
                        "operation_id":
                            prepared.operation_id,
                        "release_id":
                            prepared.release_id,
                        "archive_sha256":
                            prepared.archive_sha256,
                        "archive_size_bytes":
                            prepared.archive_size_bytes,
                        "prepared_at":
                            prepared.prepared_at.isoformat(),
                    },
                )

            except (
                ValidationError,
                NodeUpdateTransportError,
            ) as exc:
                result = AgentCommandResult(
                    command_id=command.command_id,
                    device_id=self.credential.device_id,
                    status="failed",
                    completed_at=datetime.now(UTC),
                    error=str(exc),
                )        
        elif command.command_type == "agent.update.apply" and self._node_execution() is not None:
            try:
                operation = self.node_update_execution.apply(command)
                result = AgentCommandResult(
                    command_id=command.command_id, device_id=self.credential.device_id,
                    status="succeeded", completed_at=datetime.now(UTC),
                    output={"operation_id": operation.operation_id,
                            "release_id": operation.release_id,
                            "archive_sha256": operation.archive_sha256,
                            "handoff_status": operation.status},
                )
            except (NodeUpdateHelperError, ValidationError, OSError) as exc:
                result = AgentCommandResult(
                    command_id=command.command_id, device_id=self.credential.device_id,
                    status="failed", completed_at=datetime.now(UTC), error=str(exc),
                )
        elif command.command_type in {"automation.apply", "automation.remove"} and self.automation_store is not None:
            try:
                if command.command_type == "automation.apply":
                    output = self.automation_store.apply(
                        StoredAutomation.model_validate(command.payload),
                        device_id=self.credential.device_id,
                    )
                else:
                    output = self.automation_store.remove(
                        command.payload["automation_id"], command.payload["revision"]
                    )
                result = AgentCommandResult(
                    command_id=command.command_id, device_id=self.credential.device_id,
                    status="succeeded", completed_at=datetime.now(UTC), output=output,
                )
            except (KeyError, ValueError, RuntimeError, ValidationError) as exc:
                result = AgentCommandResult(
                    command_id=command.command_id, device_id=self.credential.device_id,
                    status="failed", completed_at=datetime.now(UTC), error=str(exc),
                )
        elif command.command_type in {"module.install", "module.disable"} and self.module_runtime is not None:
            try:
                if command.command_type == "module.install":
                    package = base64.b64decode(command.payload["package_base64"], validate=True)
                    lifecycle = self.module_runtime.install(package, expected_sha256=command.payload["sha256"])
                else:
                    lifecycle = self.module_runtime.disable(command.payload["module_id"])
                result = AgentCommandResult(
                    command_id=command.command_id, device_id=self.credential.device_id,
                    status="succeeded", completed_at=datetime.now(UTC),
                    output={"module_id": lifecycle.module_id, "version": lifecycle.version, "status": lifecycle.status, "previous_version": lifecycle.previous_version},
                )
            except (KeyError, ValueError, ModuleLifecycleError) as exc:
                result = AgentCommandResult(
                    command_id=command.command_id, device_id=self.credential.device_id,
                    status="failed", completed_at=datetime.now(UTC), error=str(exc),
                )
        else:
            result = AgentCommandResult(
                command_id=command.command_id,
                device_id=self.credential.device_id,
                status="failed",
                completed_at=completed_at,
                error="Unsupported command type",
            )
        self.command_journal.save(command.idempotency_key, result, command=command)
        self._submit_result(result)
        if command.command_type in {"module.install", "module.disable"} and self.gpio_configuration is not None:
            self._reconcile_state()
            self._publish_capability_states()

    def _run_commands(self) -> None:
        while not self._stop.is_set():
            started_at = time.monotonic()
            try:
                self._poll_command(wait_seconds=COMMAND_LONG_POLL_SECONDS)
            except (DeviceTransportError, ValueError, OSError, sqlite3.Error, ModuleLifecycleError) as exc:
                logger.warning("Core command receive failed: %s", exc)
            elapsed = time.monotonic() - started_at
            if elapsed < 0.5:
                self._stop.wait(0.5 - elapsed)

    def _reconcile_state(self) -> None:
        desired = self.transport.desired_state()
        if desired.device_id != self.credential.device_id:
            raise ValueError("Desired state device identity mismatch")
        current = self.reconciliation_store.load()
        if desired.revision <= current.applied_revision:
            node_update_support = self._node_update_support()
            if self.gpio_configuration is not None or node_update_support is not None:
                state = {"inventory_generation": current.inventory_generation}
                if self.gpio_configuration is not None:
                    state["gpio_configuration"] = self.gpio_configuration.describe(self.module_runtime)
                if node_update_support is not None:
                    state["node_update"] = node_update_support
                self._send_or_queue("reported-state", AgentReportedState(
                    device_id=self.credential.device_id, desired_revision=desired.revision,
                    applied_revision=current.applied_revision, reported_at=datetime.now(UTC),
                    state=state,
                ).model_dump(mode="json"), "reported-state")
            return
        supported_keys = {"inventory_generation"}
        unsupported = sorted(set(desired.state) - supported_keys)
        generation = desired.state.get("inventory_generation", current.inventory_generation)
        if unsupported or not isinstance(generation, int) or generation < 0:
            reported = AgentReportedState(
                device_id=self.credential.device_id,
                desired_revision=desired.revision,
                applied_revision=current.applied_revision,
                reported_at=datetime.now(UTC),
                state={
                    "inventory_generation": current.inventory_generation,
                    "reconciliation_error": "Unsupported or invalid desired state",
                },
            )
        else:
            if generation != current.inventory_generation:
                self._publish_inventory()
            current = ReconciliationState(
                applied_revision=desired.revision,
                inventory_generation=generation,
            )
            self.reconciliation_store.save(current)
            reported = AgentReportedState(
                device_id=self.credential.device_id,
                desired_revision=desired.revision,
                applied_revision=current.applied_revision,
                reported_at=datetime.now(UTC),
                state={"inventory_generation": current.inventory_generation},
            )
        if self.gpio_configuration is not None:
            reported = reported.model_copy(update={"state": {
                **reported.state, "gpio_configuration": self.gpio_configuration.describe(self.module_runtime)}})
        node_update_support = self._node_update_support()
        if node_update_support is not None:
            reported = reported.model_copy(update={"state": {**reported.state, "node_update": node_update_support}})
        self._send_or_queue("reported-state", reported.model_dump(mode="json"), "reported-state")

    def _run(self) -> None:
        inventory_published = False
        while not self._stop.is_set():
            try:
                self._negotiated_inventory_version()
            except (DeviceTransportError, ValueError) as exc:
                logger.warning("Core protocol negotiation failed: %s", type(exc).__name__)
                self._stop.wait(self.interval_seconds)
                continue
            try:
                self._flush_outbox()
            except RuntimeError as exc:
                logger.warning("Agent outbox flush failed: %s", exc)
            try:
                execution = self._node_execution()
                if execution is not None:
                    execution.report_pending(self._post)
            except (DeviceTransportError, NodeUpdateHelperError, ValidationError, OSError) as exc:
                logger.warning("Core Node update outcome publish failed: %s", exc)
            if not inventory_published:
                try:
                    self._publish_inventory()
                    inventory_published = True
                except (DeviceTransportError, ValueError) as exc:
                    logger.warning("Core inventory publish failed: %s", exc)
            heartbeat = AgentHeartbeat(
                device_id=self.credential.device_id,
                sent_at=datetime.now(UTC),
                uptime_seconds=max(0.0, time.monotonic() - self.started_monotonic),
            )
            try:
                self._send_or_queue("heartbeat", heartbeat.model_dump(mode="json"), "heartbeat")
            except DeviceTransportError as exc:
                logger.warning("Core heartbeat publish failed: %s", exc)
            try:
                self._reconcile_state()
            except (DeviceTransportError, ValueError) as exc:
                logger.warning("Core state reconciliation failed: %s", exc)
            try:
                self._publish_capability_states()
            except (ModuleLifecycleError, ValidationError) as exc:
                logger.warning("Core capability state publish failed: %s", exc)
            self._stop.wait(self.interval_seconds)
