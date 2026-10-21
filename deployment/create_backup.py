#!/usr/bin/env python3
"""Create one encrypted, device-bound Standalone backup."""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, Sequence

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from backend.config import AppSettings, BackendSettings, BackupSettings
from backend.services.backups import (
    BackupCatalogItem,
    BackupOperationStatus,
    build_backup_preview,
    checksum_file,
    prune_backup_catalog,
    resolve_backup_entry,
    validate_application_backup_state,
    write_backup_catalog_item,
    write_backup_operation_status,
)


BACKUP_ROOT = Path("/var/lib/3mm/backups")
KEY_FILE = Path("/etc/3mm/backup.key")
MUTATION_LOCK = Path("/run/lock/3mm-release-mutation.lock")
RUNTIME_SERVICES = (
    "3mm-core.service",
    "3mm-agent.service",
    "3mm-application-extension@*.service",
)
ARCHIVE_MAGIC = b"3MMBKP1\0"
BACKUP_RETENTION_COUNT = 5


class ServiceController(Protocol):
    def stop(self, services: Sequence[str]) -> None: ...
    def start(self, services: Sequence[str]) -> None: ...


class SystemdServiceController:
    def __init__(self) -> None:
        self._resume_services: tuple[str, ...] | None = None

    def _run(self, action: str, services: Sequence[str]) -> None:
        subprocess.run(
            ["/usr/bin/systemctl", action, *services],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )

    def stop(self, services: Sequence[str]) -> None:
        if tuple(services) != RUNTIME_SERVICES or self._resume_services is not None:
            raise ValueError("Backup service pause has no fresh runtime snapshot")
        # systemctl start with a glob sees only currently loaded units. Stopped
        # instances may be unloaded before backup finishes, losing that match.
        # Capture exact names BEFORE stopping Core (PartOf also stops apps).
        listing = subprocess.run(
            ["/usr/bin/systemctl", "list-units", "--all", "--full", "--plain",
             "--no-legend", "--no-pager", RUNTIME_SERVICES[-1]],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=15,
        )
        units: set[str] = set()
        running: set[str] = set()
        for line in listing.stdout.splitlines():
            if not line.strip():
                continue
            fields = line.split(maxsplit=4)
            if (len(fields) < 4 or re.fullmatch(
                r"3mm-application-extension@[0-9a-f]{24}\.service", fields[0]
            ) is None or fields[2] not in {
                "active", "activating", "reloading", "inactive", "failed", "deactivating"
            }):
                raise ValueError("Backup application service inventory is invalid")
            unit, load, state, substate = fields[:4]
            if (load, state, substate) == ("not-found", "inactive", "dead"):
                continue
            units.add(unit)
            if state in {"active", "activating", "reloading"}:
                running.add(unit)
        self._run("stop", (*RUNTIME_SERVICES[:2], *sorted(units)))
        self._resume_services = (*RUNTIME_SERVICES[:2], *sorted(running))

    def start(self, services: Sequence[str]) -> None:
        if tuple(services) != RUNTIME_SERVICES or self._resume_services is None:
            raise ValueError("Backup runtime snapshot is unavailable; resume refused")
        self._run("start", self._resume_services)
        # systemctl is-active with several names succeeds if ANY is active.
        # Verify each one so healthy Core cannot hide a stopped application.
        for unit in self._resume_services:
            self._run("is-active", (unit,))
        self._resume_services = None


class EncryptingWriter:
    def __init__(self, target, key: bytes, *, magic: bytes = ARCHIVE_MAGIC) -> None:
        self._target = target
        self._nonce = os.urandom(12)
        self._encryptor = Cipher(
            algorithms.AES(key), modes.GCM(self._nonce)
        ).encryptor()
        self._position = 0
        target.write(magic + self._nonce)

    def write(self, data: bytes) -> int:
        self._target.write(self._encryptor.update(data))
        self._position += len(data)
        return len(data)

    def tell(self) -> int:
        return self._position

    def flush(self) -> None:
        self._target.flush()

    def finalize(self) -> None:
        self._target.write(self._encryptor.finalize())
        self._target.write(self._encryptor.tag)
        self._target.flush()
        os.fsync(self._target.fileno())


def _load_or_create_key(path: Path) -> bytes:
    if path.exists():
        key = path.read_bytes()
        unsafe_mode = os.name != "nt" and bool(path.stat().st_mode & 0o077)
        if len(key) != 32 or unsafe_mode:
            raise ValueError("Device backup key is invalid or has unsafe permissions")
        return key
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    key = os.urandom(32)
    with os.fdopen(descriptor, "wb") as target:
        target.write(key)
        target.flush()
        os.fsync(target.fileno())
    return key


def production_settings(backup_root: Path = BACKUP_ROOT) -> AppSettings:
    core = Path("/var/lib/3mm/core")
    return AppSettings(
        backend=BackendSettings(
            database_url="sqlite:////var/lib/3mm/core/3mm.db",
            uploads_dir=core / "uploads",
        ),
        backups=BackupSettings(
            agent_data_dir=Path("/var/lib/3mm/agent"),
            provisioning_data_dir=Path("/var/lib/3mm/provisioning"),
            backend_extensions_dir=core / "extensions/backend",
            frontend_extensions_dir=core / "extensions/frontend",
            compiled_artifacts_dir=core / "extensions/compiled",
            application_extensions_dir=Path(
                "/var/lib/3mm/application-extensions"
            ),
            host_config_file=Path("/etc/3mm/3mm.env"),
            storage_dir=backup_root,
        ),
    )


def _write_archive(path: Path, key: bytes, settings: AppSettings, preview) -> None:
    temporary = path.with_suffix(".tmp")
    try:
        with temporary.open("xb") as raw:
            os.chmod(temporary, 0o600)
            encrypted = EncryptingWriter(raw, key)
            with tarfile.open(
                fileobj=encrypted, mode="w|", format=tarfile.PAX_FORMAT
            ) as archive:
                manifest_data = preview.manifest.model_dump_json(indent=2).encode(
                    "utf-8"
                )
                manifest_info = tarfile.TarInfo("manifest.json")
                manifest_info.size = len(manifest_data)
                manifest_info.mode = 0o600
                archive.addfile(manifest_info, io.BytesIO(manifest_data))
                for entry in preview.manifest.entries:
                    source = resolve_backup_entry(settings, entry)
                    size, digest = checksum_file(source)
                    if size != entry.size_bytes or digest != entry.sha256:
                        raise ValueError("State changed after backup preflight")
                    info = tarfile.TarInfo(f"payload/{entry.area}/{entry.path}")
                    info.size = size
                    info.mode = 0o600
                    with source.open("rb") as content:
                        archive.addfile(info, content)
            encrypted.finalize()
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def encrypt_file(source: Path, destination: Path, key: bytes) -> None:
    """Encrypt one prepared tar archive with the device backup format."""

    temporary = destination.with_suffix(".tmp")
    try:
        with source.open("rb") as content, temporary.open("xb") as raw:
            os.chmod(temporary, 0o600)
            encrypted = EncryptingWriter(raw, key)
            for block in iter(lambda: content.read(1024 * 1024), b""):
                encrypted.write(block)
            encrypted.finalize()
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def create_backup(
    settings: AppSettings,
    *,
    key_file: Path,
    requested_by_user_id: int,
    controller: ServiceController | None = None,
    status_owner: tuple[int, int] | None = None,
) -> BackupOperationStatus:
    backup_root = settings.backups.storage_dir
    status_path = backup_root / "status.json"
    service_controller = controller or SystemdServiceController()
    started_at = datetime.now(UTC)
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o750)
    write_backup_operation_status(
        status_path,
        BackupOperationStatus(
            state="creating",
            message="Creating encrypted local backup",
            requested_by_user_id=requested_by_user_id,
            started_at=started_at,
        ),
        owner=status_owner,
    )
    stopped = False
    archive_path: Path | None = None
    metadata_path: Path | None = None
    try:
        # Refuse pending activation evidence without stopping/restarting any
        # review-required application. The CLI holds the existing mutation lock;
        # full file validation is repeated below after ordinary runtime quiescence.
        validate_application_backup_state(
            settings.backups.application_extensions_dir,
            validate_files=False,
        )
        service_controller.stop(RUNTIME_SERVICES)
        stopped = True
        preview = build_backup_preview(settings)
        if not preview.ready or preview.manifest is None:
            raise ValueError("Backup preflight failed after services were quiesced")
        key = _load_or_create_key(key_file)
        archive_name = f"{preview.manifest.backup_id}.3mmbak"
        archive_path = backup_root / archive_name
        _write_archive(archive_path, key, settings, preview)
        archive_size, archive_sha256 = checksum_file(archive_path)
        metadata_path = write_backup_catalog_item(
            backup_root,
            BackupCatalogItem(
                backup_id=preview.manifest.backup_id,
                archive_name=archive_name,
                created_at=preview.manifest.created_at,
                application_version=preview.manifest.compatibility.application_version,
                database_revision=preview.manifest.compatibility.database_revision,
                architecture=preview.manifest.compatibility.architecture,
                entry_count=len(preview.manifest.entries),
                payload_size_bytes=preview.manifest.total_size_bytes,
                archive_size_bytes=archive_size,
                archive_sha256=archive_sha256,
                protection=preview.manifest.protection,
            ),
            owner=status_owner,
        )
        retention_warning = False
        try:
            prune_backup_catalog(
                backup_root,
                retention_count=BACKUP_RETENTION_COUNT,
            )
        except (OSError, ValueError):
            retention_warning = True
        completed = BackupOperationStatus(
            state="completed",
            message=(
                "Encrypted local backup completed; old backup cleanup needs attention"
                if retention_warning
                else "Encrypted local backup completed"
            ),
            requested_by_user_id=requested_by_user_id,
            backup_id=preview.manifest.backup_id,
            archive_name=archive_name,
            archive_size_bytes=archive_size,
            archive_sha256=archive_sha256,
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
        write_backup_operation_status(status_path, completed, owner=status_owner)
        return completed
    except Exception:
        if metadata_path is not None:
            metadata_path.unlink(missing_ok=True)
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)
        failed = BackupOperationStatus(
            state="failed",
            message="Encrypted local backup failed",
            requested_by_user_id=requested_by_user_id,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            error_code="backup_failed",
        )
        write_backup_operation_status(status_path, failed, owner=status_owner)
        raise
    finally:
        if stopped:
            try:
                service_controller.start(RUNTIME_SERVICES)
            except Exception:
                write_backup_operation_status(
                    status_path,
                    BackupOperationStatus(
                        state="failed",
                        message="Backup completed but runtime services did not restart",
                        requested_by_user_id=requested_by_user_id,
                        started_at=started_at,
                        completed_at=datetime.now(UTC),
                        error_code="service_restart_failed",
                    ),
                    owner=status_owner,
                )
                raise


def main() -> None:
    import fcntl
    import grp

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-root", type=Path, default=BACKUP_ROOT)
    parser.add_argument("--key-file", type=Path, default=KEY_FILE)
    parser.add_argument("--requested-by-user-id", type=int, required=True)
    arguments = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Backup creation must run as root")
    if arguments.backup_root != BACKUP_ROOT or arguments.key_file != KEY_FILE:
        raise SystemExit("Backup paths are not the fixed production paths")
    MUTATION_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with MUTATION_LOCK.open("w", encoding="ascii") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit("Another 3mm mutation is already running") from exc
        create_backup(
            production_settings(arguments.backup_root),
            key_file=arguments.key_file,
            requested_by_user_id=arguments.requested_by_user_id,
            status_owner=(0, grp.getgrnam("3mm").gr_gid),
        )


if __name__ == "__main__":
    main()
