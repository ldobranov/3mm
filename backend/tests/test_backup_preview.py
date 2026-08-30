import json
import errno
import sqlite3
import shutil
from datetime import UTC, datetime
from pathlib import Path

from backend.config import AppSettings, BackendSettings, BackupSettings
from backend.services.backups import (
    build_backup_preview,
    list_backup_catalog,
    read_backup_operation_status,
)
from deployment.create_backup import ARCHIVE_MAGIC, RUNTIME_SERVICES, create_backup
from deployment.restore_backup import restore_backup
from deployment.portable_backup import (
    PORTABLE_MAGIC,
    create_portable_export,
    import_portable_backup,
)


DEVICE_ID = "dev_0123456789abcdef0123456789abcdef"


def _settings(tmp_path: Path) -> AppSettings:
    core = tmp_path / "core"
    database = core / "3mm.db"
    core.mkdir()
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(64))")
        connection.execute(
            "INSERT INTO alembic_version (version_num) VALUES (?)",
            ("18d2e3f4a5b6",),
        )
        connection.commit()
    finally:
        connection.close()

    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "identity.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "device_id": DEVICE_ID,
                "created_at": "2026-08-28T10:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (agent / "core-credential.json").write_text("{}", encoding="utf-8")

    provisioning = tmp_path / "provisioning"
    provisioning.mkdir()
    (provisioning / "provisioning.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "provisioned",
                "role": "standalone",
                "locale": "en-US",
                "device_name": "rasp-3mm",
                "administrator_name": "raspberry",
                "hub_endpoint": None,
            }
        ),
        encoding="utf-8",
    )

    uploads = core / "uploads"
    uploads.mkdir()
    (uploads / "logo.png").write_bytes(b"image")
    host_config = tmp_path / "3mm.env"
    host_config.write_text("EXAMPLE=value\n", encoding="utf-8")
    applications = tmp_path / "application-extensions"
    applications.mkdir()

    return AppSettings(
        backend=BackendSettings(
            database_url=f"sqlite:///{database.as_posix()}",
            uploads_dir=uploads,
        ),
        backups=BackupSettings(
            agent_data_dir=agent,
            provisioning_data_dir=provisioning,
            backend_extensions_dir=core / "extensions" / "backend",
            frontend_extensions_dir=core / "extensions" / "frontend",
            compiled_artifacts_dir=core / "extensions" / "compiled",
            application_extensions_dir=applications,
            host_config_file=host_config,
            storage_dir=tmp_path / "backups",
            minimum_free_bytes=16 * 1024 * 1024,
        ),
    )


def test_backup_preview_reports_manifest_checksums_and_space(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    preview = build_backup_preview(
        settings,
        now=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
        disk_usage=lambda _path: shutil_disk_usage(100_000_000),
    )

    assert preview.ready is True
    assert preview.sufficient_space is True
    assert preview.manifest is not None
    assert preview.manifest.device_id == DEVICE_ID
    assert preview.manifest.compatibility.database_revision == "18d2e3f4a5b6"
    assert preview.manifest.protection.secret_material_included is True
    assert preview.entry_count == len(preview.manifest.entries)
    assert preview.estimated_backup_bytes == sum(
        entry.size_bytes for entry in preview.manifest.entries
    )
    assert all(len(entry.sha256) == 64 for entry in preview.manifest.entries)
    paths = {(entry.area, entry.path) for entry in preview.manifest.entries}
    assert ("core", "3mm.db") in paths
    assert ("core", "uploads/logo.png") in paths
    assert ("agent", "identity.json") in paths
    assert ("provisioning", "provisioning.json") in paths
    assert ("host-config", "3mm.env") in paths


def test_backup_preview_fails_closed_when_identity_is_missing(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    (settings.backups.agent_data_dir / "identity.json").unlink()

    preview = build_backup_preview(
        settings,
        disk_usage=lambda _path: shutil_disk_usage(100_000_000),
    )

    assert preview.ready is False
    assert preview.manifest is None
    assert any(issue.code == "compatibility.device" for issue in preview.issues)


def test_backup_preview_includes_only_application_owned_data(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    instance = "a" * 24
    instance_root = settings.backups.application_extensions_dir / instance
    data = instance_root / "data"
    data.mkdir(parents=True)
    (data / "state.sqlite3").write_bytes(b"application-state")
    (instance_root / "active.json").write_text("not backup data", encoding="utf-8")
    (instance_root / "run").mkdir()
    (instance_root / "run/service.sock").write_text("transient", encoding="utf-8")

    preview = build_backup_preview(
        settings,
        disk_usage=lambda _path: shutil_disk_usage(100_000_000),
    )
    application_paths = {
        entry.path for entry in preview.manifest.entries if entry.area == "applications"
    }

    assert application_paths == {f"{instance}/data/state.sqlite3"}


def test_backup_preview_reports_insufficient_space(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    preview = build_backup_preview(
        settings,
        disk_usage=lambda _path: shutil_disk_usage(1),
    )

    assert preview.ready is False
    assert preview.sufficient_space is False
    assert preview.manifest is None
    assert any(issue.code == "storage.insufficient" for issue in preview.issues)


def test_create_backup_encrypts_archive_and_restores_services(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    calls = []

    class FakeController:
        def stop(self, services) -> None:
            calls.append(("stop", tuple(services)))

        def start(self, services) -> None:
            calls.append(("start", tuple(services)))

    result = create_backup(
        settings,
        key_file=tmp_path / "keys" / "backup.key",
        requested_by_user_id=7,
        controller=FakeController(),
    )

    archive = settings.backups.storage_dir / result.archive_name
    encrypted = archive.read_bytes()
    assert result.state == "completed"
    assert encrypted.startswith(ARCHIVE_MAGIC)
    assert b"manifest.json" not in encrypted
    assert b"admin@example.com" not in encrypted
    assert (tmp_path / "keys" / "backup.key").stat().st_size == 32
    catalog = list_backup_catalog(settings.backups.storage_dir)
    assert [item.backup_id for item in catalog.items] == [result.backup_id]
    assert catalog.items[0].archive_sha256 == result.archive_sha256
    assert calls == [("stop", RUNTIME_SERVICES), ("start", RUNTIME_SERVICES)]


def test_backup_creation_keeps_only_five_newest_archives(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    class FakeController:
        def stop(self, _services) -> None:
            pass

        def start(self, _services) -> None:
            pass

    for _index in range(6):
        create_backup(
            settings,
            key_file=tmp_path / "keys" / "backup.key",
            requested_by_user_id=7,
            controller=FakeController(),
        )

    catalog = list_backup_catalog(settings.backups.storage_dir)
    assert len(catalog.items) == 5
    assert len(list(settings.backups.storage_dir.glob("*.3mmbak"))) == 5
    assert len(list(settings.backups.storage_dir.glob("*.metadata.json"))) == 5


def test_portable_export_can_be_imported_with_a_new_device_key(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    original_key = tmp_path / "keys" / "backup.key"

    class BackupController:
        def stop(self, _services) -> None:
            pass

        def start(self, _services) -> None:
            pass

    backup = create_backup(
        settings,
        key_file=original_key,
        requested_by_user_id=7,
        controller=BackupController(),
    )
    exported = create_portable_export(
        settings.backups.storage_dir,
        original_key,
        backup.backup_id,
        "recovery-password",
    )
    assert exported.path.read_bytes().startswith(PORTABLE_MAGIC)
    assert original_key.read_bytes() not in exported.path.read_bytes()

    upload = tmp_path / "uploaded.3mmrecovery"
    shutil.copyfile(exported.path, upload)
    imported_root = tmp_path / "fresh-backups"
    imported_root.mkdir()
    fresh_key = tmp_path / "fresh-keys" / "backup.key"
    imported_id = import_portable_backup(
        upload,
        imported_root,
        fresh_key,
        "recovery-password",
        max_archive_bytes=32 * 1024 * 1024,
    )

    assert imported_id == backup.backup_id
    assert original_key.read_bytes() != fresh_key.read_bytes()
    assert [item.backup_id for item in list_backup_catalog(imported_root).items] == [
        backup.backup_id
    ]
    assert not upload.exists()


def test_portable_import_rejects_the_wrong_password(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    key_file = tmp_path / "keys" / "backup.key"

    class BackupController:
        def stop(self, _services) -> None:
            pass

        def start(self, _services) -> None:
            pass

    backup = create_backup(
        settings,
        key_file=key_file,
        requested_by_user_id=7,
        controller=BackupController(),
    )
    exported = create_portable_export(
        settings.backups.storage_dir,
        key_file,
        backup.backup_id,
        "correct-password",
    )
    upload = tmp_path / "wrong-password.3mmrecovery"
    shutil.copyfile(exported.path, upload)

    import pytest

    with pytest.raises(ValueError, match="password or file is invalid"):
        import_portable_backup(
            upload,
            tmp_path / "fresh-backups",
            tmp_path / "fresh-key",
            "wrong-password",
            max_archive_bytes=32 * 1024 * 1024,
        )
    assert not upload.exists()


def test_restore_replaces_state_and_runs_health_boundary(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    key_file = tmp_path / "keys" / "backup.key"
    application_state = (
        settings.backups.application_extensions_dir
        / ("b" * 24)
        / "data/state.sqlite3"
    )
    application_state.parent.mkdir(parents=True)
    application_state.write_bytes(b"application-before-backup")

    class BackupController:
        def stop(self, _services) -> None:
            pass

        def start(self, _services) -> None:
            pass

    backup = create_backup(
        settings,
        key_file=key_file,
        requested_by_user_id=7,
        controller=BackupController(),
    )
    (settings.backend.uploads_dir / "logo.png").write_bytes(b"changed")
    application_state.write_bytes(b"application-after-backup")
    calls = []

    class RestoreController:
        def stop(self, services) -> None:
            calls.append(("stop", tuple(services)))

        def migrate(self) -> None:
            calls.append(("migrate",))

        def activate_and_verify(self) -> None:
            calls.append(("verify",))

    result = restore_backup(
        settings,
        backup_id=backup.backup_id,
        key_file=key_file,
        requested_by_user_id=7,
        runtime=RestoreController(),
        service_ids=(1000, 1000),
        state_root=tmp_path,
        host_config=settings.backups.host_config_file,
        apply_ownership=False,
    )

    assert result.state == "completed"
    assert (settings.backend.uploads_dir / "logo.png").read_bytes() == b"image"
    assert application_state.read_bytes() == b"application-before-backup"
    assert (tmp_path / "core/backup-imports").is_dir()
    assert (settings.backups.application_extensions_dir / "platform").is_dir()
    assert [call[0] for call in calls] == ["stop", "migrate", "verify"]


def test_restore_host_config_never_renames_across_filesystems(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = _settings(tmp_path)
    key_file = tmp_path / "keys" / "backup.key"

    class BackupController:
        def stop(self, _services) -> None:
            pass

        def start(self, _services) -> None:
            pass

    backup = create_backup(
        settings,
        key_file=key_file,
        requested_by_user_id=7,
        controller=BackupController(),
    )
    settings.backups.host_config_file.write_text("EXAMPLE=changed\n", encoding="utf-8")
    real_replace = __import__("os").replace

    def reject_cross_device_replace(source, destination):
        source_path = Path(source)
        destination_path = Path(destination)
        if (
            source_path == settings.backups.host_config_file
            and source_path.parent != destination_path.parent
        ):
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return real_replace(source, destination)

    monkeypatch.setattr("deployment.restore_backup.os.replace", reject_cross_device_replace)

    class RestoreController:
        def stop(self, _services) -> None:
            pass

        def migrate(self) -> None:
            pass

        def activate_and_verify(self) -> None:
            pass

    result = restore_backup(
        settings,
        backup_id=backup.backup_id,
        key_file=key_file,
        requested_by_user_id=7,
        runtime=RestoreController(),
        service_ids=(1000, 1000),
        state_root=tmp_path,
        host_config=settings.backups.host_config_file,
        apply_ownership=False,
    )

    assert result.state == "completed"
    assert settings.backups.host_config_file.read_text(encoding="utf-8") == "EXAMPLE=value\n"


def test_restore_failure_rolls_back_previous_state(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    key_file = tmp_path / "keys" / "backup.key"

    class BackupController:
        def stop(self, _services) -> None:
            pass

        def start(self, _services) -> None:
            pass

    backup = create_backup(
        settings,
        key_file=key_file,
        requested_by_user_id=7,
        controller=BackupController(),
    )
    logo = settings.backend.uploads_dir / "logo.png"
    logo.write_bytes(b"state-before-restore")

    class FailingRestoreController:
        def stop(self, _services) -> None:
            pass

        def migrate(self) -> None:
            raise RuntimeError("migration failed")

        def activate_and_verify(self) -> None:
            pass

    import pytest

    with pytest.raises(RuntimeError, match="migration failed"):
        restore_backup(
            settings,
            backup_id=backup.backup_id,
            key_file=key_file,
            requested_by_user_id=7,
            runtime=FailingRestoreController(),
            service_ids=(1000, 1000),
            state_root=tmp_path,
            host_config=settings.backups.host_config_file,
            apply_ownership=False,
        )

    assert logo.read_bytes() == b"state-before-restore"
    status = read_backup_operation_status(settings.backups.storage_dir / "status.json")
    assert status.state == "rolled_back"


def test_restore_switch_failure_restarts_existing_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = _settings(tmp_path)
    key_file = tmp_path / "keys" / "backup.key"

    class BackupController:
        def stop(self, _services) -> None:
            pass

        def start(self, _services) -> None:
            pass

    backup = create_backup(
        settings,
        key_file=key_file,
        requested_by_user_id=7,
        controller=BackupController(),
    )
    calls = []

    class RestoreController:
        def stop(self, _services) -> None:
            calls.append("stop")

        def migrate(self) -> None:
            calls.append("migrate")

        def activate_and_verify(self) -> None:
            calls.append("verify")

    def fail_switch(*_args, **_kwargs):
        raise OSError("switch failed")

    monkeypatch.setattr("deployment.restore_backup._switch_state", fail_switch)

    import pytest

    with pytest.raises(OSError, match="switch failed"):
        restore_backup(
            settings,
            backup_id=backup.backup_id,
            key_file=key_file,
            requested_by_user_id=7,
            runtime=RestoreController(),
            service_ids=(1000, 1000),
            state_root=tmp_path,
            host_config=settings.backups.host_config_file,
            apply_ownership=False,
        )

    assert calls == ["stop", "verify"]
    status = read_backup_operation_status(settings.backups.storage_dir / "status.json")
    assert status.state == "rolled_back"


def test_corrupt_backup_is_rejected_before_services_stop(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    key_file = tmp_path / "keys" / "backup.key"

    class BackupController:
        def stop(self, _services) -> None:
            pass

        def start(self, _services) -> None:
            pass

    backup = create_backup(
        settings,
        key_file=key_file,
        requested_by_user_id=7,
        controller=BackupController(),
    )
    archive = settings.backups.storage_dir / backup.archive_name
    damaged = bytearray(archive.read_bytes())
    damaged[-20] ^= 1
    archive.write_bytes(damaged)
    calls = []

    class RestoreController:
        def stop(self, _services) -> None:
            calls.append("stop")

        def migrate(self) -> None:
            calls.append("migrate")

        def activate_and_verify(self) -> None:
            calls.append("verify")

    import pytest

    with pytest.raises(ValueError, match="authentication failed"):
        restore_backup(
            settings,
            backup_id=backup.backup_id,
            key_file=key_file,
            requested_by_user_id=7,
            runtime=RestoreController(),
            service_ids=(1000, 1000),
            state_root=tmp_path,
            host_config=settings.backups.host_config_file,
            apply_ownership=False,
        )

    assert calls == []
    status = read_backup_operation_status(settings.backups.storage_dir / "status.json")
    assert status.error_code == "restore_validation_failed"


def test_system_restore_refreshes_helper_after_health_verification(monkeypatch):
    import deployment.restore_backup as restore_backup_module

    commands: list[tuple[str, ...]] = []
    runtime = restore_backup_module.SystemRestoreRuntime()
    monkeypatch.setattr(
        runtime,
        "_run",
        lambda command: commands.append(tuple(command)),
    )
    monkeypatch.setattr(restore_backup_module, "verify_release", lambda _endpoints: None)

    runtime.activate_and_verify()

    assert commands[-1] == (
        "/usr/bin/systemctl",
        "try-restart",
        "3mm-update-helper.service",
    )


def shutil_disk_usage(free: int):
    from shutil import _ntuple_diskusage

    return _ntuple_diskusage(total=200_000_000, used=200_000_000 - free, free=free)
