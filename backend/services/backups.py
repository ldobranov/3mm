"""Read-only Standalone backup inventory and preflight preview."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Callable, Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from agent.identity import AgentIdentity
from backend.config import AppSettings, PROJECT_ROOT
from three_mm_protocol import (
    PROTOCOL_VERSION,
    BackupCompatibilityV1,
    BackupEntryV1,
    BackupManifestV1,
    BackupProtectionV1,
)
from three_mm_provisioning import ProvisioningSnapshot, ProvisioningState


BACKUP_ID_PATTERN = r"^bkp_\d{8}T\d{6}Z_[0-9a-f]{8}$"


class StrictPreviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BackupPreviewIssue(StrictPreviewModel):
    severity: Literal["warning", "error"]
    code: str
    message: str


class BackupPreviewResponse(StrictPreviewModel):
    ready: bool
    manifest: BackupManifestV1 | None
    entry_count: int
    estimated_backup_bytes: int
    available_bytes: int
    minimum_free_after_backup_bytes: int
    required_available_bytes: int
    sufficient_space: bool
    storage_path: str
    issues: tuple[BackupPreviewIssue, ...] = ()


class BackupOperationStatus(StrictPreviewModel):
    state: Literal[
        "idle", "creating", "restoring", "completed", "rolled_back", "failed"
    ] = "idle"
    message: str = "No backup operation has run"
    requested_by_user_id: int | None = Field(default=None, ge=1)
    backup_id: str | None = None
    archive_name: str | None = None
    archive_size_bytes: int | None = Field(default=None, ge=0)
    archive_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None


class BackupCatalogItem(StrictPreviewModel):
    backup_id: str = Field(pattern=BACKUP_ID_PATTERN)
    archive_name: str = Field(pattern=r"^bkp_\d{8}T\d{6}Z_[0-9a-f]{8}\.3mmbak$")
    created_at: AwareDatetime
    application_version: str
    database_revision: str
    architecture: str
    entry_count: int = Field(ge=1)
    payload_size_bytes: int = Field(ge=0)
    archive_size_bytes: int = Field(ge=0)
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protection: BackupProtectionV1

    @model_validator(mode="after")
    def matching_archive_name(self):
        if self.archive_name != f"{self.backup_id}.3mmbak":
            raise ValueError("backup archive name does not match its identifier")
        return self


class BackupCatalogResponse(StrictPreviewModel):
    items: tuple[BackupCatalogItem, ...] = ()
    retention_count: int = Field(default=5, ge=1)
    issues: tuple[BackupPreviewIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class BackupSource:
    area: Literal["core", "agent", "provisioning", "host-config"]
    source: Path
    logical_path: str
    sensitivity: Literal["private", "secret"]
    required: bool = False
    report_missing: bool = True


class DiskUsage(Protocol):
    free: int


def _database_path(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///") or database_url.endswith(":memory:"):
        raise ValueError(
            "Standalone backup preview requires a file-backed SQLite database"
        )
    return Path(database_url.removeprefix("sqlite:///"))


def _read_database_revision(path: Path) -> str:
    if not path.is_file():
        raise ValueError("Core database is missing")
    uri = f"{path.resolve().as_uri()}?mode=ro"
    connection = None
    try:
        connection = sqlite3.connect(uri, uri=True)
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.Error as exc:
        raise ValueError("Core database migration revision cannot be read") from exc
    finally:
        if connection is not None:
            connection.close()
    if row is None or not isinstance(row[0], str) or not row[0].strip():
        raise ValueError("Core database migration revision is missing")
    return row[0].strip()


def _read_device_context(settings: AppSettings) -> tuple[str, str]:
    identity_path = settings.backups.agent_data_dir / "identity.json"
    provisioning_path = settings.backups.provisioning_data_dir / "provisioning.json"
    try:
        identity = AgentIdentity.model_validate_json(
            identity_path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise ValueError("Stable Agent identity is missing or invalid") from exc
    try:
        snapshot = ProvisioningSnapshot.from_dict(
            json.loads(provisioning_path.read_text(encoding="utf-8"))
        )
    except Exception as exc:
        raise ValueError("Provisioning state is missing or invalid") from exc
    if (
        snapshot.state is not ProvisioningState.PROVISIONED
        or snapshot.role is None
        or snapshot.role.value != "standalone"
    ):
        raise ValueError("Backup preview requires a provisioned Standalone device")
    return identity.device_id, snapshot.role.value


def _read_application_version() -> str:
    try:
        version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError("Application version cannot be read") from exc
    if not version:
        raise ValueError("Application version is empty")
    return version


def _nearest_existing_path(path: Path) -> Path:
    candidate = path.resolve()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    if not candidate.exists():
        raise ValueError("Backup storage filesystem cannot be inspected")
    return candidate


def _sha256_stable_file(path: Path) -> tuple[int, str]:
    for _attempt in range(2):
        before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) == (
            after.st_size,
            after.st_mtime_ns,
        ):
            return after.st_size, digest.hexdigest()
    raise OSError("file changed while its checksum was calculated")


def checksum_file(path: Path) -> tuple[int, str]:
    return _sha256_stable_file(path)


def _logical_entry_path(prefix: str, relative: PurePosixPath | None = None) -> str:
    base = PurePosixPath(prefix)
    return (base / relative).as_posix() if relative is not None else base.as_posix()


def _scan_source(
    source: BackupSource,
    issues: list[BackupPreviewIssue],
) -> list[BackupEntryV1]:
    if not source.source.exists():
        if source.required:
            issues.append(
                BackupPreviewIssue(
                    severity="error",
                    code="state.required_missing",
                    message=f"Required {source.area} state is missing: {source.logical_path}",
                )
            )
        elif source.report_missing:
            issues.append(
                BackupPreviewIssue(
                    severity="warning",
                    code="state.optional_missing",
                    message=f"Optional {source.area} state is not present: {source.logical_path}",
                )
            )
        return []

    if source.source.is_symlink():
        issues.append(
            BackupPreviewIssue(
                severity="error",
                code="state.symlink_rejected",
                message=f"Symbolic links are not accepted: {source.area}/{source.logical_path}",
            )
        )
        return []

    candidates: list[tuple[Path, PurePosixPath | None]]
    if source.source.is_file():
        candidates = [(source.source, None)]
    elif source.source.is_dir():
        candidates = []
        for candidate in sorted(source.source.rglob("*")):
            relative = PurePosixPath(candidate.relative_to(source.source).as_posix())
            if candidate.is_symlink():
                issues.append(
                    BackupPreviewIssue(
                        severity="error",
                        code="state.symlink_rejected",
                        message=(
                            "Symbolic links are not accepted: "
                            f"{source.area}/{_logical_entry_path(source.logical_path, relative)}"
                        ),
                    )
                )
            elif candidate.is_file():
                candidates.append((candidate, relative))
    else:
        issues.append(
            BackupPreviewIssue(
                severity="error",
                code="state.special_file_rejected",
                message=f"Unsupported state file type: {source.area}/{source.logical_path}",
            )
        )
        return []

    entries: list[BackupEntryV1] = []
    for candidate, relative in candidates:
        logical_path = _logical_entry_path(source.logical_path, relative)
        sensitivity = source.sensitivity
        if source.area == "agent" and logical_path == "core-credential.json":
            sensitivity = "secret"
        try:
            size_bytes, sha256 = _sha256_stable_file(candidate)
            entries.append(
                BackupEntryV1(
                    area=source.area,
                    path=logical_path,
                    sensitivity=sensitivity,
                    size_bytes=size_bytes,
                    sha256=sha256,
                )
            )
        except (OSError, ValueError) as exc:
            issues.append(
                BackupPreviewIssue(
                    severity="error",
                    code="state.read_failed",
                    message=f"Cannot read stable state file {source.area}/{logical_path}: {exc}",
                )
            )
    return entries


def _backup_sources(
    settings: AppSettings, database_path: Path
) -> tuple[BackupSource, ...]:
    core_root = database_path.parent
    return (
        BackupSource(
            "core", database_path, database_path.name, "secret", required=True
        ),
        BackupSource("core", settings.backend.uploads_dir, "uploads", "private"),
        BackupSource(
            "core",
            settings.backups.backend_extensions_dir,
            "extensions/backend",
            "private",
        ),
        BackupSource(
            "core",
            settings.backups.frontend_extensions_dir,
            "extensions/frontend",
            "private",
        ),
        BackupSource(
            "core",
            settings.backups.compiled_artifacts_dir,
            "extensions/compiled",
            "private",
        ),
        BackupSource(
            "core",
            core_root / "update-policy.json",
            "update-policy.json",
            "private",
            report_missing=False,
        ),
        BackupSource(
            "core",
            core_root / "network-recovery-policy.json",
            "network-recovery-policy.json",
            "private",
            report_missing=False,
        ),
        BackupSource(
            "agent", settings.backups.agent_data_dir, "", "private", required=True
        ),
        BackupSource(
            "provisioning",
            settings.backups.provisioning_data_dir / "provisioning.json",
            "provisioning.json",
            "private",
            required=True,
        ),
        BackupSource(
            "host-config",
            settings.backups.host_config_file,
            "3mm.env",
            "secret",
        ),
    )


def resolve_backup_entry(settings: AppSettings, entry: BackupEntryV1) -> Path:
    database_path = _database_path(settings.database_url)
    for source in _backup_sources(settings, database_path):
        if source.area != entry.area:
            continue
        prefix = PurePosixPath(source.logical_path)
        entry_path = PurePosixPath(entry.path)
        if source.source.is_file() and entry_path == prefix:
            return source.source
        if not source.source.is_dir():
            continue
        if source.logical_path:
            try:
                relative = entry_path.relative_to(prefix)
            except ValueError:
                continue
        else:
            relative = entry_path
        target = source.source.joinpath(*relative.parts)
        try:
            target.resolve(strict=True).relative_to(source.source.resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise ValueError("Backup entry escaped its allowlisted source") from exc
        if target.is_symlink() or not target.is_file():
            raise ValueError("Backup entry is no longer a regular file")
        return target
    raise ValueError("Backup entry is not part of the allowlisted state inventory")


def write_backup_operation_status(
    path: Path,
    status: BackupOperationStatus,
    *,
    owner: tuple[int, int] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(status.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o640)
    if owner is not None:
        os.chown(temporary, *owner)
    os.replace(temporary, path)


def read_backup_operation_status(path: Path) -> BackupOperationStatus:
    if not path.is_file():
        return BackupOperationStatus()
    try:
        return BackupOperationStatus.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise ValueError("Backup operation status is invalid") from exc


def _catalog_metadata_path(storage_dir: Path, backup_id: str) -> Path:
    if re.fullmatch(BACKUP_ID_PATTERN, backup_id) is None:
        raise ValueError("Invalid backup identifier")
    return storage_dir / f"{backup_id}.metadata.json"


def write_backup_catalog_item(
    storage_dir: Path,
    item: BackupCatalogItem,
    *,
    owner: tuple[int, int] | None = None,
) -> Path:
    storage_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
    path = _catalog_metadata_path(storage_dir, item.backup_id)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(item.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o640)
    if owner is not None:
        os.chown(temporary, *owner)
    os.replace(temporary, path)
    return path


def list_backup_catalog(
    storage_dir: Path,
    *,
    retention_count: int = 5,
) -> BackupCatalogResponse:
    if not storage_dir.exists():
        return BackupCatalogResponse(retention_count=retention_count)
    if storage_dir.is_symlink() or not storage_dir.is_dir():
        raise ValueError("Backup storage path is not a regular directory")

    items: list[BackupCatalogItem] = []
    issues: list[BackupPreviewIssue] = []
    for path in sorted(storage_dir.glob("bkp_*.metadata.json")):
        try:
            if path.is_symlink() or not path.is_file():
                raise ValueError("metadata is not a regular file")
            item = BackupCatalogItem.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            if path.name != f"{item.backup_id}.metadata.json":
                raise ValueError("metadata filename does not match backup identifier")
            archive = storage_dir / item.archive_name
            if archive.is_symlink() or not archive.is_file():
                raise ValueError("encrypted archive is missing")
            if archive.stat().st_size != item.archive_size_bytes:
                raise ValueError("encrypted archive size does not match metadata")
            items.append(item)
        except (OSError, ValueError) as exc:
            issues.append(
                BackupPreviewIssue(
                    severity="warning",
                    code="catalog.invalid_entry",
                    message=f"Ignored invalid backup metadata {path.name}: {exc}",
                )
            )

    items.sort(key=lambda item: item.created_at, reverse=True)
    return BackupCatalogResponse(
        items=tuple(items),
        retention_count=retention_count,
        issues=tuple(issues),
    )


def prune_backup_catalog(
    storage_dir: Path,
    *,
    retention_count: int = 5,
) -> tuple[str, ...]:
    catalog = list_backup_catalog(storage_dir, retention_count=retention_count)
    removed: list[str] = []
    for item in catalog.items[retention_count:]:
        archive = storage_dir / item.archive_name
        metadata = _catalog_metadata_path(storage_dir, item.backup_id)
        if archive.parent != storage_dir or metadata.parent != storage_dir:
            raise ValueError("Backup retention target escaped storage directory")
        archive.unlink()
        metadata.unlink()
        removed.append(item.backup_id)
    return tuple(removed)


def build_backup_preview(
    settings: AppSettings,
    *,
    now: datetime | None = None,
    disk_usage: Callable[[Path], DiskUsage] = shutil.disk_usage,
) -> BackupPreviewResponse:
    """Inspect backup readiness without creating directories or changing state."""
    issues: list[BackupPreviewIssue] = []
    entries: list[BackupEntryV1] = []
    database_path: Path | None = None
    database_revision: str | None = None
    device_id: str | None = None
    device_role: str | None = None
    application_version: str | None = None

    try:
        database_path = _database_path(settings.database_url)
        database_revision = _read_database_revision(database_path)
    except ValueError as exc:
        issues.append(
            BackupPreviewIssue(
                severity="error", code="compatibility.database", message=str(exc)
            )
        )

    try:
        device_id, device_role = _read_device_context(settings)
    except ValueError as exc:
        issues.append(
            BackupPreviewIssue(
                severity="error", code="compatibility.device", message=str(exc)
            )
        )

    try:
        application_version = _read_application_version()
    except ValueError as exc:
        issues.append(
            BackupPreviewIssue(
                severity="error", code="compatibility.application", message=str(exc)
            )
        )

    if database_path is not None:
        for source in _backup_sources(settings, database_path):
            entries.extend(_scan_source(source, issues))

    entries.sort(key=lambda entry: (entry.area, entry.path))
    estimated_bytes = sum(entry.size_bytes for entry in entries)

    try:
        usage = disk_usage(_nearest_existing_path(settings.backups.storage_dir))
        available_bytes = usage.free
    except (OSError, ValueError) as exc:
        available_bytes = 0
        issues.append(
            BackupPreviewIssue(
                severity="error",
                code="storage.inspect_failed",
                message=str(exc),
            )
        )

    required_available = estimated_bytes + settings.backups.minimum_free_bytes
    sufficient_space = available_bytes >= required_available
    if not sufficient_space:
        issues.append(
            BackupPreviewIssue(
                severity="error",
                code="storage.insufficient",
                message="Backup storage does not have enough free space",
            )
        )

    manifest: BackupManifestV1 | None = None
    if (
        not any(issue.severity == "error" for issue in issues)
        and database_revision is not None
        and device_id is not None
        and device_role == "standalone"
        and application_version is not None
        and entries
    ):
        created_at = now or datetime.now(UTC)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        backup_id = (
            f"bkp_{created_at.astimezone(UTC):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:8]}"
        )
        manifest = BackupManifestV1(
            backup_id=backup_id,
            created_at=created_at,
            device_id=device_id,
            device_role="standalone",
            compatibility=BackupCompatibilityV1(
                application_version=application_version,
                protocol_version=PROTOCOL_VERSION,
                database_revision=database_revision,
                architecture=platform.machine() or "unknown",
            ),
            protection=BackupProtectionV1(
                mode="device-bound",
                export_policy="local-only",
                secret_material_included=any(
                    entry.sensitivity == "secret" for entry in entries
                ),
            ),
            entries=tuple(entries),
            total_size_bytes=estimated_bytes,
        )

    return BackupPreviewResponse(
        ready=manifest is not None and sufficient_space,
        manifest=manifest,
        entry_count=len(entries),
        estimated_backup_bytes=estimated_bytes,
        available_bytes=available_bytes,
        minimum_free_after_backup_bytes=settings.backups.minimum_free_bytes,
        required_available_bytes=required_available,
        sufficient_space=sufficient_space,
        storage_path=str(settings.backups.storage_dir),
        issues=tuple(issues),
    )
