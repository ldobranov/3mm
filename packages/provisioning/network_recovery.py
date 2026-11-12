"""Secret-free policy and marker state for network recovery setup mode."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

POLICY_SCHEMA_VERSION = 1
MARKER_SCHEMA_VERSION = 1
DEFAULT_OFFLINE_AFTER_SECONDS = 300
RecoveryTrigger = Literal["manual", "automatic"]


class NetworkRecoveryStoreError(RuntimeError):
    """Network recovery state cannot be read or written safely."""


@dataclass(frozen=True, slots=True)
class NetworkRecoveryPolicy:
    automatic_setup_enabled: bool = True
    offline_after_seconds: int = DEFAULT_OFFLINE_AFTER_SECONDS
    schema_version: int = POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.automatic_setup_enabled) is not bool:
            raise ValueError("Automatic setup policy must be a boolean")
        if (
            type(self.offline_after_seconds) is not int
            or self.offline_after_seconds < 60
            or self.offline_after_seconds > 3600
        ):
            raise ValueError("Network recovery delay is invalid")
        if self.schema_version != POLICY_SCHEMA_VERSION:
            raise ValueError("Unsupported network recovery policy version")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "automatic_setup_enabled": self.automatic_setup_enabled,
            "offline_after_seconds": self.offline_after_seconds,
        }

    @classmethod
    def from_dict(cls, value: object) -> "NetworkRecoveryPolicy":
        if not isinstance(value, dict) or set(value) != {
            "schema_version",
            "automatic_setup_enabled",
            "offline_after_seconds",
        }:
            raise ValueError("Network recovery policy fields are invalid")
        return cls(
            schema_version=value["schema_version"],
            automatic_setup_enabled=value["automatic_setup_enabled"],
            offline_after_seconds=value["offline_after_seconds"],
        )


class FileNetworkRecoveryPolicyStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> NetworkRecoveryPolicy:
        if not self.path.exists():
            return NetworkRecoveryPolicy()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return NetworkRecoveryPolicy.from_dict(payload)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise NetworkRecoveryStoreError(
                f"Cannot load network recovery policy from {self.path}"
            ) from exc

    def save(self, policy: NetworkRecoveryPolicy) -> None:
        _atomic_json_write(self.path, policy.to_dict())


class FileNetworkRecoveryMarker:
    """An existence marker that asks the runtime planner to enter setup mode."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def is_active(self) -> bool:
        return self.path.is_file()

    def activate(
        self,
        trigger: RecoveryTrigger,
        *,
        owner: tuple[int, int] | None = None,
    ) -> None:
        if trigger not in {"manual", "automatic"}:
            raise ValueError("Network recovery trigger is invalid")
        _atomic_json_write(
            self.path,
            {
                "schema_version": MARKER_SCHEMA_VERSION,
                "trigger": trigger,
                "requested_at": datetime.now(UTC).isoformat(),
            },
            owner=owner,
        )

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise NetworkRecoveryStoreError(
                f"Cannot clear network recovery marker at {self.path}"
            ) from exc


def _atomic_json_write(
    path: Path,
    payload: dict[str, object],
    *,
    owner: tuple[int, int] | None = None,
) -> None:
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary_path, 0o600)
        if owner is not None:
            os.chown(temporary_path, *owner)
        os.replace(temporary_path, path)
    except OSError as exc:
        temporary_path.unlink(missing_ok=True)
        raise NetworkRecoveryStoreError(
            f"Cannot persist network recovery state at {path}"
        ) from exc
