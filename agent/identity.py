"""Stable, local Agent identity storage."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class AgentIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    created_at: datetime


class IdentityStoreError(RuntimeError):
    pass


class AgentIdentityStore:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self.path = data_dir / "identity.json"

    def load_or_create(self) -> AgentIdentity:
        if self.path.exists():
            return self._load()

        identity = AgentIdentity(
            device_id=f"dev_{uuid.uuid4().hex}",
            created_at=datetime.now(UTC),
        )
        self._write(identity)
        return identity

    def _load(self) -> AgentIdentity:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return AgentIdentity.model_validate(data)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise IdentityStoreError(
                f"Cannot load Agent identity from {self.path}"
            ) from exc

    def _write(self, identity: AgentIdentity) -> None:
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self._data_dir, 0o700)
            temporary_path = self.path.with_suffix(".tmp")
            temporary_path.write_text(
                identity.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self.path)
        except OSError as exc:
            raise IdentityStoreError(
                f"Cannot persist Agent identity in {self._data_dir}"
            ) from exc
