"""Secret-free persistent state for provisioning recovery."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from three_mm_protocol import AgentRole
from three_mm_provisioning.models import ProvisioningRequest, ProvisioningState

SNAPSHOT_SCHEMA_VERSION = 1


def default_provisioning_data_dir() -> Path:
    data_home = os.getenv("XDG_DATA_HOME")
    if data_home:
        return Path(data_home) / "3mm" / "setup"
    return Path.home() / ".local" / "share" / "3mm" / "setup"


class ProvisioningStoreError(RuntimeError):
    """Persistent provisioning state cannot be safely read or written."""


@dataclass(frozen=True, slots=True)
class ProvisioningSnapshot:
    state: ProvisioningState
    role: AgentRole | None = None
    locale: str | None = None
    device_name: str | None = None
    administrator_name: str | None = None
    hub_endpoint: str | None = None
    schema_version: int = SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != SNAPSHOT_SCHEMA_VERSION
        ):
            raise ValueError("Unsupported provisioning snapshot version")
        if not isinstance(self.state, ProvisioningState):
            raise ValueError("Provisioning snapshot state is invalid")
        if self.role is not None and not isinstance(self.role, AgentRole):
            raise ValueError("Provisioning snapshot role is invalid")
        if self.state not in {
            ProvisioningState.APPLYING_NETWORK,
            ProvisioningState.PROVISIONED,
        }:
            raise ValueError("Provisioning snapshot has an unsupported state")
        if self.state is ProvisioningState.PROVISIONED:
            required = (
                self.role,
                self.locale,
                self.device_name,
                self.administrator_name,
            )
            if any(value is None for value in required):
                raise ValueError("Provisioned snapshot is incomplete")
        elif any(
            value is not None
            for value in (
                self.role,
                self.locale,
                self.device_name,
                self.administrator_name,
                self.hub_endpoint,
            )
        ):
            raise ValueError("Attempt snapshot contains unexpected settings")

    @classmethod
    def attempt_started(cls) -> "ProvisioningSnapshot":
        return cls(state=ProvisioningState.APPLYING_NETWORK)

    @classmethod
    def provisioned(
        cls,
        request: ProvisioningRequest,
    ) -> "ProvisioningSnapshot":
        return cls(
            state=ProvisioningState.PROVISIONED,
            role=request.role,
            locale=request.locale,
            device_name=request.device_name,
            administrator_name=request.administrator_name,
            hub_endpoint=request.hub_endpoint,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "state": self.state.value,
            "role": self.role.value if self.role is not None else None,
            "locale": self.locale,
            "device_name": self.device_name,
            "administrator_name": self.administrator_name,
            "hub_endpoint": self.hub_endpoint,
        }

    @classmethod
    def from_dict(cls, value: object) -> "ProvisioningSnapshot":
        if not isinstance(value, dict):
            raise ValueError("Provisioning snapshot must be an object")
        expected_keys = {
            "schema_version",
            "state",
            "role",
            "locale",
            "device_name",
            "administrator_name",
            "hub_endpoint",
        }
        if set(value) != expected_keys:
            raise ValueError("Provisioning snapshot fields are invalid")
        role_value = value["role"]
        return cls(
            schema_version=value["schema_version"],
            state=ProvisioningState(value["state"]),
            role=AgentRole(role_value) if role_value is not None else None,
            locale=_optional_string(value["locale"]),
            device_name=_optional_string(value["device_name"]),
            administrator_name=_optional_string(value["administrator_name"]),
            hub_endpoint=_optional_string(value["hub_endpoint"]),
        )


def _optional_string(value: object) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError("Provisioning snapshot value must be a string or null")


class ProvisioningStore(Protocol):
    def load(self) -> ProvisioningSnapshot | None: ...

    def save(self, snapshot: ProvisioningSnapshot) -> None: ...

    def clear(self) -> None: ...


class FileProvisioningStore:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self.path = data_dir / "provisioning.json"

    def load(self) -> ProvisioningSnapshot | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return ProvisioningSnapshot.from_dict(payload)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProvisioningStoreError(
                f"Cannot load provisioning state from {self.path}"
            ) from exc

    def save(self, snapshot: ProvisioningSnapshot) -> None:
        temporary_path = self.path.with_suffix(".tmp")
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self._data_dir, 0o700)
            temporary_path.write_text(
                json.dumps(snapshot.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self.path)
        except OSError as exc:
            raise ProvisioningStoreError(
                f"Cannot persist provisioning state in {self._data_dir}"
            ) from exc

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise ProvisioningStoreError(
                f"Cannot clear provisioning state at {self.path}"
            ) from exc


class MemoryProvisioningStore:
    def __init__(self, snapshot: ProvisioningSnapshot | None = None) -> None:
        self.snapshot = snapshot

    def load(self) -> ProvisioningSnapshot | None:
        return self.snapshot

    def save(self, snapshot: ProvisioningSnapshot) -> None:
        self.snapshot = snapshot

    def clear(self) -> None:
        self.snapshot = None
