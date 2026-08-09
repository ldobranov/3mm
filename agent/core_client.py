"""Authenticated Agent-to-Core inventory and heartbeat publishing."""

from __future__ import annotations

import logging
import json
import base64
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from agent.module_runtime import AgentModuleRuntime, ModuleLifecycleError

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from three_mm_protocol import (
    AgentCommand, AgentCommandResult, AgentHeartbeat, AgentInventory,
    AgentReportedState, DeviceDesiredState,
)

logger = logging.getLogger(__name__)


class DeviceCredential(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    credential_id: str = Field(pattern=r"^cred_[0-9a-f]{32}$")
    credential_secret: str = Field(min_length=32)


class DeviceCredentialStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "core-credential.json"

    def load(self) -> DeviceCredential | None:
        if not self.path.exists():
            return None
        try:
            return DeviceCredential.model_validate_json(
                self.path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as exc:
            raise RuntimeError(f"Cannot load Core credential from {self.path}") from exc

    def save(self, credential: DeviceCredential) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(credential.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)


class CommandJournal:
    """Small persistent cache preventing repeated idempotent actions."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "command-journal.json"
        self._results: dict[str, AgentCommandResult] = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self._results = {
                    key: AgentCommandResult.model_validate(value)
                    for key, value in raw.items()
                }
            except (OSError, ValueError, ValidationError) as exc:
                raise RuntimeError(f"Cannot load command journal from {self.path}") from exc

    def get(self, idempotency_key: str) -> AgentCommandResult | None:
        return self._results.get(idempotency_key)

    def save(self, idempotency_key: str, result: AgentCommandResult) -> None:
        self._results[idempotency_key] = result
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {key: value.model_dump(mode="json") for key, value in self._results.items()},
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)


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
        entries.append(entry)
        self.save(entries[-500:])


@dataclass(slots=True)
class CorePublisher:
    core_url: str
    credential: DeviceCredential
    inventory_provider: Callable[[], AgentInventory]
    command_journal: CommandJournal
    reconciliation_store: ReconciliationStore
    outbox: OutboxStore
    started_monotonic: float
    module_runtime: AgentModuleRuntime | None = None
    interval_seconds: int = 30
    _stop: threading.Event = field(init=False, repr=False)
    _thread: threading.Thread | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        self.core_url = self.core_url.rstrip("/")
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def headers(self) -> dict[str, str]:
        value = f"Device {self.credential.credential_id}:{self.credential.credential_secret}"
        return {"Authorization": value}

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="3mm-core-publisher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _post(self, suffix: str, payload: dict) -> None:
        response = requests.post(
            f"{self.core_url}/api/v1/devices/{self.credential.device_id}/{suffix}",
            json=payload,
            headers=self.headers,
            timeout=10,
        )
        response.raise_for_status()

    def _publish_inventory(self) -> None:
        self._post("inventory", self.inventory_provider().model_dump(mode="json"))

    def _send_or_queue(self, suffix: str, payload: dict, deduplication_key: str) -> bool:
        try:
            self._post(suffix, payload)
            return True
        except requests.RequestException:
            self.outbox.enqueue(OutboxEntry(suffix=suffix, payload=payload, deduplication_key=deduplication_key))
            return False

    def _flush_outbox(self) -> None:
        remaining: list[OutboxEntry] = []
        entries = self.outbox.load()
        for index, entry in enumerate(entries):
            try:
                self._post(entry.suffix, entry.payload)
            except requests.RequestException:
                remaining.extend(entries[index:])
                break
        self.outbox.save(remaining)

    def _submit_result(self, result: AgentCommandResult) -> None:
        self._send_or_queue(
            f"commands/{result.command_id}/result",
            result.model_dump(mode="json"),
            f"command-result:{result.command_id}",
        )

    def _poll_command(self) -> None:
        response = requests.get(
            f"{self.core_url}/api/v1/devices/{self.credential.device_id}/commands/next",
            headers=self.headers,
            timeout=10,
        )
        if response.status_code == 204:
            return
        response.raise_for_status()
        command = AgentCommand.model_validate(response.json())
        cached = self.command_journal.get(command.idempotency_key)
        if cached is not None:
            replay = cached.model_copy(update={"command_id": command.command_id})
            self._submit_result(replay)
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
            except requests.RequestException as exc:
                result = AgentCommandResult(
                    command_id=command.command_id,
                    device_id=self.credential.device_id,
                    status="failed",
                    completed_at=datetime.now(UTC),
                    error=f"Inventory publish failed: {type(exc).__name__}",
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
        self.command_journal.save(command.idempotency_key, result)
        self._submit_result(result)

    def _reconcile_state(self) -> None:
        response = requests.get(
            f"{self.core_url}/api/v1/devices/{self.credential.device_id}/desired-state",
            headers=self.headers,
            timeout=10,
        )
        response.raise_for_status()
        desired = DeviceDesiredState.model_validate(response.json())
        current = self.reconciliation_store.load()
        if desired.revision <= current.applied_revision:
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
        self._send_or_queue("reported-state", reported.model_dump(mode="json"), "reported-state")

    def _run(self) -> None:
        inventory_published = False
        while not self._stop.is_set():
            try:
                self._flush_outbox()
            except RuntimeError as exc:
                logger.warning("Agent outbox flush failed: %s", exc)
            if not inventory_published:
                try:
                    self._publish_inventory()
                    inventory_published = True
                except requests.RequestException as exc:
                    logger.warning("Core inventory publish failed: %s", exc)
            heartbeat = AgentHeartbeat(
                device_id=self.credential.device_id,
                sent_at=datetime.now(UTC),
                uptime_seconds=max(0.0, time.monotonic() - self.started_monotonic),
            )
            try:
                self._send_or_queue("heartbeat", heartbeat.model_dump(mode="json"), "heartbeat")
            except requests.RequestException as exc:
                logger.warning("Core heartbeat publish failed: %s", exc)
            try:
                self._poll_command()
            except (requests.RequestException, ValidationError) as exc:
                logger.warning("Core command poll failed: %s", exc)
            try:
                self._reconcile_state()
            except (requests.RequestException, ValidationError) as exc:
                logger.warning("Core state reconciliation failed: %s", exc)
            self._stop.wait(self.interval_seconds)
