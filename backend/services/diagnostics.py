"""Deterministic, secret-redacted Standalone support diagnostics."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Literal, Protocol
from urllib.request import urlopen

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from backend.config import AppSettings, PROJECT_ROOT
from backend.services.backups import read_backup_operation_status
from three_mm_protocol import PROTOCOL_VERSION


SENSITIVE_KEY = re.compile(
    r"password|passphrase|secret|token|api[_-]?key|credential|authorization|cookie|private[_-]?key",
    re.IGNORECASE,
)
ASSIGNMENT_SECRET = re.compile(
    r"\b([A-Z0-9_]*(?:PASSWORD|PASSPHRASE|SECRET|TOKEN|API_KEY|CREDENTIAL)[A-Z0-9_]*)\s*=\s*([^\s,;]+)",
    re.IGNORECASE,
)
BEARER_SECRET = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
URL_USERINFO = re.compile(r"(https?://)[^/@\s]+@", re.IGNORECASE)


class StrictDiagnosticModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DiagnosticCheck(StrictDiagnosticModel):
    name: str
    status: Literal["ok", "warning", "error"]
    summary: str


class DiagnosticBundle(StrictDiagnosticModel):
    schema_version: Literal[1] = 1
    generated_at: AwareDatetime
    application: dict[str, str | None]
    system: dict[str, str | int | float | None]
    storage: dict[str, int]
    operations: dict[str, str | None]
    checks: tuple[DiagnosticCheck, ...]
    excluded: tuple[str, ...]


class DiagnosticPreview(StrictDiagnosticModel):
    generated_at: AwareDatetime
    ready: bool
    estimated_size_bytes: int = Field(ge=0)
    check_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    checks: tuple[DiagnosticCheck, ...]
    excluded: tuple[str, ...]


class DiskUsage(Protocol):
    total: int
    used: int
    free: int


def redact_diagnostic_data(value: Any, *, key: str | None = None) -> Any:
    """Recursively remove common secret fields and inline credential forms."""
    if key is not None and SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(child_key): redact_diagnostic_data(child_value, key=str(child_key))
            for child_key, child_value in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [redact_diagnostic_data(item) for item in value]
    if isinstance(value, str):
        redacted = BEARER_SECRET.sub("Bearer [REDACTED]", value)
        redacted = ASSIGNMENT_SECRET.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)
        return URL_USERINFO.sub(r"\1[REDACTED]@", redacted)
    return value


def _database_path(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///") or database_url.endswith(":memory:"):
        raise ValueError("Diagnostics require a file-backed SQLite database")
    return Path(database_url.removeprefix("sqlite:///"))


def _nearest_existing(path: Path) -> Path:
    candidate = path.resolve()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _database_check(database_url: str) -> tuple[DiagnosticCheck, str | None]:
    connection = None
    try:
        path = _database_path(database_url)
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        integrity = connection.execute("PRAGMA quick_check").fetchone()
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        if integrity is None or integrity[0] != "ok":
            return DiagnosticCheck(name="database", status="error", summary="SQLite quick check failed"), None
        if revision is None or not isinstance(revision[0], str):
            return DiagnosticCheck(name="database", status="warning", summary="SQLite is healthy; migration revision is unavailable"), None
        return DiagnosticCheck(name="database", status="ok", summary="SQLite quick check passed"), revision[0]
    except (OSError, sqlite3.Error, ValueError):
        return DiagnosticCheck(name="database", status="error", summary="SQLite diagnostics are unavailable"), None
    finally:
        if connection is not None:
            connection.close()


def _read_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("diagnostic source is unexpectedly large")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("diagnostic source is not an object")
    return value


def _device_fingerprint(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _agent_health() -> tuple[DiagnosticCheck, dict[str, str | None]]:
    try:
        with urlopen("http://127.0.0.1:8890/health", timeout=0.75) as response:
            if response.status != 200:
                raise ValueError("unexpected status")
            payload = json.loads(response.read(64 * 1024))
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            raise ValueError("invalid health response")
        return (
            DiagnosticCheck(name="agent", status="ok", summary="Agent health endpoint is ready"),
            {
                "agent_protocol_version": str(payload.get("protocol_version") or "unknown"),
                "device_fingerprint": _device_fingerprint(payload.get("device_id")),
            },
        )
    except Exception:
        return (
            DiagnosticCheck(name="agent", status="warning", summary="Agent health endpoint is unavailable"),
            {"agent_protocol_version": None, "device_fingerprint": None},
        )


def _application_metadata(settings: AppSettings) -> dict[str, str | None]:
    version = None
    try:
        version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip() or None
    except OSError:
        pass
    release: dict[str, Any] = {}
    try:
        release = _read_json(settings.updates.release_metadata_file)
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return {
        "version": version,
        "protocol_version": PROTOCOL_VERSION,
        "release_id": str(release.get("release_id")) if release.get("release_id") else None,
        "commit": str(release.get("commit")) if release.get("commit") else None,
        "branch": str(release.get("branch")) if release.get("branch") else None,
    }


def _system_metadata() -> dict[str, str | int | float | None]:
    load_1m: float | None = None
    try:
        load_1m = round(os.getloadavg()[0], 2)
    except (AttributeError, OSError):
        pass
    memory_total = memory_available = None
    try:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            name, value = line.split(":", 1)
            if name == "MemTotal":
                memory_total = int(value.strip().split()[0]) * 1024
            elif name == "MemAvailable":
                memory_available = int(value.strip().split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return {
        "hostname": platform.node() or None,
        "operating_system": platform.system() or None,
        "os_release": platform.release() or None,
        "architecture": platform.machine() or None,
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "load_1m": load_1m,
        "memory_total_bytes": memory_total,
        "memory_available_bytes": memory_available,
    }


def build_diagnostic_bundle(
    settings: AppSettings,
    *,
    now: datetime | None = None,
    disk_usage: Callable[[Path], DiskUsage] = shutil.disk_usage,
    agent_health: Callable[[], tuple[DiagnosticCheck, dict[str, str | None]]] = _agent_health,
) -> DiagnosticBundle:
    generated_at = now or datetime.now(UTC)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    database_check, database_revision = _database_check(settings.database_url)
    agent_check, agent_metadata = agent_health()
    checks = [database_check, agent_check]

    storage: dict[str, int] = {}
    try:
        usage = disk_usage(_nearest_existing(_database_path(settings.database_url)))
        storage = {"total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}
        checks.append(DiagnosticCheck(name="storage", status="ok", summary="Storage usage is available"))
    except (OSError, ValueError):
        storage = {"total_bytes": 0, "used_bytes": 0, "free_bytes": 0}
        checks.append(DiagnosticCheck(name="storage", status="warning", summary="Storage usage is unavailable"))

    try:
        backup_status = read_backup_operation_status(settings.backups.storage_dir / "status.json")
        operations = {
            "backup_state": backup_status.state,
            "backup_id": backup_status.backup_id,
            "backup_completed_at": backup_status.completed_at.isoformat() if backup_status.completed_at else None,
        }
    except ValueError:
        operations = {"backup_state": "invalid", "backup_id": None, "backup_completed_at": None}
        checks.append(DiagnosticCheck(name="backup_status", status="warning", summary="Backup operation status is invalid"))

    application = _application_metadata(settings)
    application["database_revision"] = database_revision
    application.update(agent_metadata)
    bundle = DiagnosticBundle(
        generated_at=generated_at,
        application=application,
        system=_system_metadata(),
        storage=storage,
        operations=operations,
        checks=tuple(checks),
        excluded=(
            "passwords, provider keys, tokens and authentication artifacts",
            "Wi-Fi profiles and network credentials",
            "environment values, database contents and application logs",
            "uploaded files, extension payloads and backup contents",
        ),
    )
    return DiagnosticBundle.model_validate(redact_diagnostic_data(bundle.model_dump(mode="json")))


def serialize_diagnostic_bundle(bundle: DiagnosticBundle) -> bytes:
    safe = redact_diagnostic_data(bundle.model_dump(mode="json"))
    return (json.dumps(safe, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def build_diagnostic_preview(settings: AppSettings) -> DiagnosticPreview:
    bundle = build_diagnostic_bundle(settings)
    serialized = serialize_diagnostic_bundle(bundle)
    warning_count = sum(check.status != "ok" for check in bundle.checks)
    return DiagnosticPreview(
        generated_at=bundle.generated_at,
        ready=True,
        estimated_size_bytes=len(serialized),
        check_count=len(bundle.checks),
        warning_count=warning_count,
        checks=bundle.checks,
        excluded=bundle.excluded,
    )
