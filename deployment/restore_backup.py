#!/usr/bin/env python3
"""Validate and transactionally restore one device-bound Standalone backup."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Protocol, Sequence

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from agent.identity import AgentIdentity
from backend.config import AppSettings
from backend.services.backups import (
    BackupOperationStatus,
    write_backup_operation_status,
)
from deployment.create_backup import (
    ARCHIVE_MAGIC,
    BACKUP_ROOT,
    KEY_FILE,
    MUTATION_LOCK,
    production_settings,
)
from deployment.release_smoke import ReleaseEndpoints, SmokeFailure, verify_release
from three_mm_protocol import PROTOCOL_VERSION, BackupManifestV1
from three_mm_provisioning import ProvisioningSnapshot, ProvisioningState


RUNTIME_SERVICES = (
    "3mm-core.service",
    "3mm-agent.service",
    "3mm-web.service",
    "3mm-application-extension@*.service",
)
BACKUP_ID_PATTERN = r"^bkp_\d{8}T\d{6}Z_[0-9a-f]{8}$"


class RestoreRuntime(Protocol):
    def stop(self, services: Sequence[str]) -> None: ...
    def migrate(self) -> None: ...
    def activate_and_verify(self) -> None: ...


class SystemRestoreRuntime:
    def _run(self, arguments: Sequence[str]) -> None:
        subprocess.run(
            list(arguments),
            check=True,
            timeout=180,
        )
        
    def stop(self, services: Sequence[str]) -> None:
        self._run(("/usr/bin/systemctl", "stop", *services))

    def migrate(self) -> None:
        release = Path("/opt/3mm/current")
        python = release / ".venv/bin/python"
        self._run(
            (
                "/usr/sbin/runuser",
                "-u",
                "3mm",
                "--",
                "/usr/bin/env",
                "DATABASE_URL=sqlite:////var/lib/3mm/core/3mm.db",
                "UPLOADS_DIR=/var/lib/3mm/core/uploads",
                "BACKEND_EXTENSIONS_DIR=/var/lib/3mm/core/extensions/backend",
                "FRONTEND_EXTENSIONS_DIR=/var/lib/3mm/core/extensions/frontend",
                "COMPILED_UI_ARTIFACTS_DIR=/var/lib/3mm/core/extensions/compiled",
                f"PYTHONPATH={release}",
                str(python),
                str(release / "deployment/migrate_database.py"),
            )
        )

    def activate_and_verify(self) -> None:
        release = Path("/opt/3mm/current")
        self._run(
            (
                "/usr/bin/env",
                f"PYTHONPATH={release}",
                str(release / ".venv/bin/python"),
                str(release / "deployment/restore_application_extensions.py"),
            )
        )
        self._run(
            (
                "/usr/bin/env",
                f"PYTHONPATH={release}",
                str(release / ".venv/bin/python"),
                "-m",
                "three_mm_runtime.activate",
            )
        )
        last_error: Exception | None = None
        for _attempt in range(15):
            try:
                verify_release(ReleaseEndpoints(timeout=3.0))
                # Restore swaps persistent directories atomically. Refresh the
                # privileged helper so its hardened bind-mount namespace sees
                # the restored application state instead of detached inodes.
                self._run(
                    (
                        "/usr/bin/systemctl",
                        "try-restart",
                        "3mm-update-helper.service",
                    )
                )
                return
            except SmokeFailure as exc:
                last_error = exc
                time.sleep(2)
        raise RuntimeError(
            "Restored runtime did not pass health verification"
        ) from last_error


def _decrypt_archive_with_key(
    archive: Path,
    key: bytes,
    destination: Path,
) -> None:
    size = archive.stat().st_size
    minimum = len(ARCHIVE_MAGIC) + 12 + 16
    if size <= minimum:
        raise ValueError("Encrypted backup is truncated")
    with archive.open("rb") as source:
        if source.read(len(ARCHIVE_MAGIC)) != ARCHIVE_MAGIC:
            raise ValueError("Encrypted backup header is invalid")
        nonce = source.read(12)
        source.seek(-16, os.SEEK_END)
        tag = source.read(16)
        ciphertext_size = size - minimum
        source.seek(len(ARCHIVE_MAGIC) + 12)
        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        with destination.open("xb") as target:
            os.chmod(destination, 0o600)
            remaining = ciphertext_size
            try:
                while remaining:
                    block = source.read(min(1024 * 1024, remaining))
                    if not block:
                        raise ValueError("Encrypted backup is truncated")
                    remaining -= len(block)
                    target.write(decryptor.update(block))
                target.write(decryptor.finalize())
            except InvalidTag as exc:
                raise ValueError("Encrypted backup authentication failed") from exc


def _decrypt_archive(archive: Path, key_file: Path, destination: Path) -> None:
    key = key_file.read_bytes()
    unsafe_mode = os.name != "nt" and bool(key_file.stat().st_mode & 0o077)
    if len(key) != 32 or unsafe_mode:
        raise ValueError("Device backup key is missing or unsafe")
    _decrypt_archive_with_key(archive, key, destination)


def _validate_compatibility(manifest: BackupManifestV1) -> None:
    current_version = (
        (Path(__file__).resolve().parents[1] / "VERSION")
        .read_text(encoding="utf-8")
        .strip()
    )
    compatibility = manifest.compatibility
    if compatibility.application_version != current_version:
        raise ValueError("Backup application version is not supported by this release")
    if compatibility.protocol_version != PROTOCOL_VERSION:
        raise ValueError("Backup protocol version is not supported")
    if compatibility.architecture != (platform.machine() or "unknown"):
        raise ValueError("Backup architecture does not match this device")


def _validate_database(path: Path, expected_revision: str) -> None:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    connection = None
    try:
        connection = sqlite3.connect(uri, uri=True)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
    except sqlite3.Error as exc:
        raise ValueError("Restored database cannot be validated") from exc
    finally:
        if connection is not None:
            connection.close()
    if integrity != ("ok",):
        raise ValueError("Restored database integrity check failed")
    if revision is None or revision[0] != expected_revision:
        raise ValueError("Restored database revision does not match the manifest")


def _validate_identity_and_role(payload: Path, manifest: BackupManifestV1) -> None:
    try:
        identity = AgentIdentity.model_validate_json(
            (payload / "agent/identity.json").read_text(encoding="utf-8")
        )
        snapshot = ProvisioningSnapshot.from_dict(
            json.loads(
                (payload / "provisioning/provisioning.json").read_text(encoding="utf-8")
            )
        )
    except Exception as exc:
        raise ValueError("Backup identity or provisioning state is invalid") from exc
    if identity.device_id != manifest.device_id:
        raise ValueError("Backup Agent identity does not match its manifest")
    if (
        snapshot.state is not ProvisioningState.PROVISIONED
        or snapshot.role is None
        or snapshot.role.value != "standalone"
    ):
        raise ValueError("Backup is not a provisioned Standalone device")


def _validate_and_stage(
    decrypted: Path,
    staging: Path,
    expected_backup_id: str,
) -> BackupManifestV1:
    with tarfile.open(decrypted, mode="r:") as archive:
        members = archive.getmembers()
        by_name = {member.name: member for member in members}
        if len(by_name) != len(members) or "manifest.json" not in by_name:
            raise ValueError("Backup archive index is invalid")
        manifest_member = by_name["manifest.json"]
        if not manifest_member.isfile() or manifest_member.size > 8 * 1024 * 1024:
            raise ValueError("Backup manifest entry is invalid")
        manifest_file = archive.extractfile(manifest_member)
        if manifest_file is None:
            raise ValueError("Backup manifest cannot be read")
        manifest = BackupManifestV1.model_validate_json(manifest_file.read())
        if manifest.backup_id != expected_backup_id:
            raise ValueError("Backup ID does not match the selected archive")
        _validate_compatibility(manifest)

        expected = {
            f"payload/{entry.area}/{entry.path}": entry for entry in manifest.entries
        }
        if set(by_name) != {"manifest.json", *expected}:
            raise ValueError("Backup archive contents do not match the manifest")
        payload = staging / "payload"
        for name, entry in expected.items():
            member = by_name[name]
            if not member.isfile() or member.size != entry.size_bytes:
                raise ValueError("Backup payload entry size or type is invalid")
            relative = PurePosixPath(entry.area) / PurePosixPath(entry.path)
            destination = payload.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            content = archive.extractfile(member)
            if content is None:
                raise ValueError("Backup payload entry cannot be read")
            digest = hashlib.sha256()
            with destination.open("xb") as target:
                os.chmod(destination, 0o600)
                for block in iter(lambda: content.read(1024 * 1024), b""):
                    digest.update(block)
                    target.write(block)
            if digest.hexdigest() != entry.sha256:
                raise ValueError("Backup payload checksum failed")

    _validate_database(
        staging / "payload/core/3mm.db",
        manifest.compatibility.database_revision,
    )
    _validate_identity_and_role(staging / "payload", manifest)
    return manifest


def _chown_tree(
    path: Path,
    uid: int,
    gid: int,
    *,
    directory_mode: int,
    apply_ownership: bool,
) -> None:
    for candidate in (path, *path.rglob("*")):
        if candidate.is_symlink():
            raise ValueError("Restore staging contains a symbolic link")
        if apply_ownership:
            os.chown(candidate, uid, gid)
        os.chmod(candidate, directory_mode if candidate.is_dir() else 0o600)


def _prepare_payload(
    payload: Path,
    uid: int,
    gid: int,
    *,
    apply_ownership: bool = True,
    application_service_ids: tuple[int, int] | None = None,
) -> None:
    core = payload / "core"
    agent = payload / "agent"
    provisioning = payload / "provisioning"
    applications = payload / "applications"
    for required in (
        core / "3mm.db",
        agent / "identity.json",
        provisioning / "provisioning.json",
    ):
        if not required.is_file():
            raise ValueError("Backup is missing required Standalone state")
    (core / "update-staging").mkdir(parents=True, exist_ok=True)
    # Empty runtime directories are excluded from the archive but must exist
    # before hardened systemd units resolve their ReadWritePaths entries.
    (core / "backup-imports").mkdir(parents=True, exist_ok=True)
    _chown_tree(core, uid, gid, directory_mode=0o750, apply_ownership=apply_ownership)
    _chown_tree(agent, uid, gid, directory_mode=0o700, apply_ownership=apply_ownership)
    _chown_tree(
        provisioning,
        uid,
        gid,
        directory_mode=0o700,
        apply_ownership=apply_ownership,
    )
    applications.mkdir(parents=True, exist_ok=True)
    application_uid, application_gid = application_service_ids or (uid, gid)
    _chown_tree(
        applications,
        application_uid,
        application_gid,
        directory_mode=0o750,
        apply_ownership=apply_ownership,
    )
    # Runtime-only platform sockets are intentionally excluded from backups,
    # but systemd requires their parent to exist before Core can start.
    platform_directory = applications / "platform"
    platform_directory.mkdir(mode=0o750)
    os.chmod(platform_directory, 0o750)
    if apply_ownership:
        os.chown(applications, 0, application_gid)
        os.chown(platform_directory, uid, application_gid)
    host_config = payload / "host-config/3mm.env"
    if host_config.exists():
        if apply_ownership:
            os.chown(host_config, 0, gid)
        os.chmod(host_config, 0o640)


def _switch_state(
    payload: Path,
    rollback: Path,
    *,
    state_root: Path = Path("/var/lib/3mm"),
    host_config: Path = Path("/etc/3mm/3mm.env"),
) -> list[tuple[Path, Path | None]]:
    if rollback.exists():
        try:
            rollback.rmdir()
        except OSError as exc:
            raise ValueError("Previous restore recovery state is not empty") from exc
    rollback.mkdir(parents=True, exist_ok=False, mode=0o700)
    switches: list[tuple[Path, Path | None]] = []
    locations = (
        (state_root / "core", payload / "core", rollback / "core"),
        (state_root / "agent", payload / "agent", rollback / "agent"),
        (
            state_root / "provisioning",
            payload / "provisioning",
            rollback / "provisioning",
        ),
        (
            state_root / "application-extensions",
            payload / "applications",
            rollback / "application-extensions",
        ),
    )
    try:
        for live, replacement, previous in locations:
            saved: Path | None = None
            if live.exists():
                os.replace(live, previous)
                saved = previous
            switches.append((live, saved))
            os.replace(replacement, live)

        host = payload / "host-config/3mm.env"
        if host.is_file():
            suffix = rollback.name.removeprefix(".rollback-")
            previous = host_config.parent / f".{host_config.name}.{suffix}.previous"
            temporary = host_config.parent / f".{host_config.name}.{suffix}.incoming"
            if previous.exists() or temporary.exists():
                raise ValueError("Previous host-config recovery state is not empty")
            reference = host_config if host_config.exists() else host
            reference_stat = reference.stat()
            saved = None
            if host_config.exists():
                os.replace(host_config, previous)
                saved = previous
            switches.append((host_config, saved))
            try:
                shutil.copyfile(host, temporary)
                if hasattr(os, "chown"):
                    os.chown(temporary, reference_stat.st_uid, reference_stat.st_gid)
                os.chmod(temporary, reference_stat.st_mode & 0o777)
                os.replace(temporary, host_config)
                host.unlink()
            finally:
                temporary.unlink(missing_ok=True)
    except Exception:
        _rollback_switches(switches)
        raise
    return switches


def _rollback_switches(switches: list[tuple[Path, Path | None]]) -> None:
    for live, previous in reversed(switches):
        if live.is_dir():
            shutil.rmtree(live)
        else:
            live.unlink(missing_ok=True)
        if previous is not None and previous.exists():
            os.replace(previous, live)


def _discard_previous_state(switches: list[tuple[Path, Path | None]]) -> None:
    for _live, previous in switches:
        if previous is None or not previous.exists():
            continue
        if previous.is_dir():
            shutil.rmtree(previous)
        else:
            previous.unlink()


def restore_backup(
    settings: AppSettings,
    *,
    backup_id: str,
    key_file: Path,
    requested_by_user_id: int,
    runtime: RestoreRuntime | None = None,
    service_ids: tuple[int, int] | None = None,
    application_service_ids: tuple[int, int] | None = None,
    status_owner: tuple[int, int] | None = None,
    state_root: Path = Path("/var/lib/3mm"),
    host_config: Path = Path("/etc/3mm/3mm.env"),
    apply_ownership: bool = True,
) -> BackupOperationStatus:
    if not __import__("re").fullmatch(BACKUP_ID_PATTERN, backup_id):
        raise ValueError("Backup ID is invalid")
    backup_root = settings.backups.storage_dir
    archive = backup_root / f"{backup_id}.3mmbak"
    if not archive.is_file() or archive.is_symlink():
        raise ValueError("Selected backup archive is unavailable")
    status_path = backup_root / "status.json"
    started_at = datetime.now(UTC)
    controller = runtime or SystemRestoreRuntime()
    uid, gid = service_ids or _service_ids()
    write_backup_operation_status(
        status_path,
        BackupOperationStatus(
            state="restoring",
            message="Validating encrypted backup before restore",
            requested_by_user_id=requested_by_user_id,
            backup_id=backup_id,
            started_at=started_at,
        ),
        owner=status_owner,
    )
    switches: list[tuple[Path, Path | None]] = []
    with tempfile.TemporaryDirectory(prefix=".restore-", dir=backup_root) as temporary:
        work = Path(temporary)
        decrypted = work / "archive.tar"
        staging = work / "staging"
        staging.mkdir(mode=0o700)
        try:
            _decrypt_archive(archive, key_file, decrypted)
            manifest = _validate_and_stage(decrypted, staging, backup_id)
            decrypted.unlink()
            _prepare_payload(
                staging / "payload",
                uid,
                gid,
                apply_ownership=apply_ownership,
                application_service_ids=application_service_ids,
            )
        except Exception:
            write_backup_operation_status(
                status_path,
                BackupOperationStatus(
                    state="failed",
                    message="Backup validation failed before persistent state changed",
                    requested_by_user_id=requested_by_user_id,
                    backup_id=backup_id,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    error_code="restore_validation_failed",
                ),
                owner=status_owner,
            )
            raise
        rollback = backup_root / f".rollback-{backup_id}"
        remove_rollback = False
        try:
            controller.stop(RUNTIME_SERVICES)
            switches = _switch_state(
                staging / "payload",
                rollback,
                state_root=state_root,
                host_config=host_config,
            )
            controller.migrate()
            controller.activate_and_verify()
            remove_rollback = True
        except Exception as restore_error:
            rollback_error: Exception | None = None
            if switches:
                try:
                    controller.stop(RUNTIME_SERVICES)
                    _rollback_switches(switches)
                    controller.activate_and_verify()
                    remove_rollback = True
                except Exception as exc:
                    rollback_error = exc
            else:
                try:
                    controller.activate_and_verify()
                    remove_rollback = True
                except Exception as exc:
                    rollback_error = exc
            write_backup_operation_status(
                status_path,
                BackupOperationStatus(
                    state=(
                        "rolled_back"
                        if rollback_error is None
                        else "failed"
                    ),
                    message=(
                        "Restore failed; previous Standalone state was restored"
                        if rollback_error is None
                        else "Restore and automatic rollback failed; recovery state was preserved"
                    ),
                    requested_by_user_id=requested_by_user_id,
                    backup_id=backup_id,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    error_code=(
                        "restore_rolled_back"
                        if rollback_error is None
                        else "restore_rollback_failed"
                    ),
                ),
                owner=status_owner,
            )
            if rollback_error is not None:
                raise RuntimeError(
                    f"Restore failed and rollback requires manual recovery at {rollback}"
                ) from rollback_error
            raise restore_error
        finally:
            if remove_rollback:
                _discard_previous_state(switches)
                if rollback.exists():
                    shutil.rmtree(rollback)

    completed = BackupOperationStatus(
        state="completed",
        message="Standalone backup restored and health checks passed",
        requested_by_user_id=requested_by_user_id,
        backup_id=manifest.backup_id,
        started_at=started_at,
        completed_at=datetime.now(UTC),
    )
    write_backup_operation_status(status_path, completed, owner=status_owner)
    return completed


def _service_ids() -> tuple[int, int]:
    import grp
    import pwd

    return pwd.getpwnam("3mm").pw_uid, grp.getgrnam("3mm").gr_gid


def _application_service_ids() -> tuple[int, int]:
    import grp
    import pwd

    return pwd.getpwnam("3mm-app").pw_uid, grp.getgrnam("3mm-app").gr_gid


def main() -> None:
    import fcntl
    import grp

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-root", type=Path, default=BACKUP_ROOT)
    parser.add_argument("--key-file", type=Path, default=KEY_FILE)
    parser.add_argument("--backup-id", required=True)
    parser.add_argument("--requested-by-user-id", type=int, required=True)
    arguments = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Backup restore must run as root")
    if arguments.backup_root != BACKUP_ROOT or arguments.key_file != KEY_FILE:
        raise SystemExit("Restore paths are not the fixed production paths")
    MUTATION_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with MUTATION_LOCK.open("w", encoding="ascii") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit("Another 3mm mutation is already running") from exc
        restore_backup(
            production_settings(arguments.backup_root),
            backup_id=arguments.backup_id,
            key_file=arguments.key_file,
            requested_by_user_id=arguments.requested_by_user_id,
            status_owner=(0, grp.getgrnam("3mm").gr_gid),
            application_service_ids=_application_service_ids(),
        )


if __name__ == "__main__":
    main()
