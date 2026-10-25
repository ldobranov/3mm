"""Secret-free persistent state for provisioning recovery."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from three_mm_protocol import AgentRole
from three_mm_provisioning.models import NetworkMode, ProvisioningRequest, ProvisioningState

SNAPSHOT_SCHEMA_VERSION = 2


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
    network_mode: NetworkMode = NetworkMode.PRESERVE
    network_interface: str | None = None
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
        if not isinstance(self.network_mode, NetworkMode):
            raise ValueError("Provisioning snapshot network mode is invalid")
        if self.network_interface is not None:
            import re
            if not isinstance(self.network_interface, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,14}", self.network_interface):
                raise ValueError("Provisioning snapshot interface is invalid")
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
            network_mode=request.network_mode,
            network_interface=request.network_interface,
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
            "network_mode": self.network_mode.value,
            "network_interface": self.network_interface,
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
        version = value.get("schema_version")
        if version == 2:
            expected_keys |= {"network_mode", "network_interface"}
        if type(version) is not int or version not in {1, 2} or set(value) != expected_keys:
            raise ValueError("Provisioning snapshot fields are invalid")
        role_value = value["role"]
        return cls(
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            state=ProvisioningState(value["state"]),
            role=AgentRole(role_value) if role_value is not None else None,
            locale=_optional_string(value["locale"]),
            device_name=_optional_string(value["device_name"]),
            administrator_name=_optional_string(value["administrator_name"]),
            hub_endpoint=_optional_string(value["hub_endpoint"]),
            network_mode=NetworkMode(value.get("network_mode", "preserve")),
            network_interface=_optional_string(value.get("network_interface")),
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

    def load_runtime_snapshot(self) -> ProvisioningSnapshot | None:
        from three_mm_provisioning.setup_journal import SetupJournal
        attempt = SetupJournal(self._data_dir).load()
        if attempt is not None:
            return ProvisioningSnapshot.from_dict(attempt["previous"]) if attempt["previous"] else None
        return self.load()

    def setup_pending(self) -> bool:
        from three_mm_provisioning.setup_journal import SetupJournal
        return SetupJournal(self._data_dir).load() is not None

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
        try:
            from three_mm_provisioning.setup_journal import atomic_json
            atomic_json(self.path, snapshot.to_dict())
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
