"""Authenticated Agent-to-Core inventory and heartbeat publishing."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from three_mm_protocol import AgentHeartbeat, AgentInventory

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


@dataclass(slots=True)
class CorePublisher:
    core_url: str
    credential: DeviceCredential
    inventory: AgentInventory
    started_monotonic: float
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

    def _run(self) -> None:
        inventory_published = False
        while not self._stop.is_set():
            if not inventory_published:
                try:
                    self._post("inventory", self.inventory.model_dump(mode="json"))
                    inventory_published = True
                except requests.RequestException as exc:
                    logger.warning("Core inventory publish failed: %s", exc)
            heartbeat = AgentHeartbeat(
                device_id=self.credential.device_id,
                sent_at=datetime.now(UTC),
                uptime_seconds=max(0.0, time.monotonic() - self.started_monotonic),
            )
            try:
                self._post("heartbeat", heartbeat.model_dump(mode="json"))
            except requests.RequestException as exc:
                logger.warning("Core heartbeat publish failed: %s", exc)
            self._stop.wait(self.interval_seconds)
