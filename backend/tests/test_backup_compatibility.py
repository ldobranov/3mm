from pathlib import Path

import pytest

from deployment.backup_compatibility import BackupCompatibilityError, validate_release_path, version_key

ROOT = Path(__file__).parents[2]
REVISION = "18d2e3f4a5b6"


def test_revision_preflight_never_initializes_runtime_database():
    import subprocess
    import sys

    result = subprocess.run([sys.executable, "-c", """
import builtins
from pathlib import Path
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'backend.database':
        raise AssertionError('Preflight must not initialize a database')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from deployment.backup_compatibility import validate_release_path
validate_release_path('0.3.0-beta.9', '0.3.0-beta.10', '18d2e3f4a5b6', Path.cwd())
"""], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("source", ["0.3.0-beta.9", "0.3.0-beta.10"])
def test_known_older_database_can_upgrade(source):
    validate_release_path(source, "0.3.0-beta.10", REVISION, ROOT)


@pytest.mark.parametrize("source, revision, message", [
    ("0.3.0-beta.11", REVISION, "Update the device first"),
    ("0.3.0", REVISION, "Update the device first"),
    ("0.2.0", REVISION, "outside the supported"),
    ("0.3.0-beta.9", "unknown", "no supported migration path"),
])
def test_unsupported_archive_is_rejected(source, revision, message):
    with pytest.raises(BackupCompatibilityError, match=message):
        validate_release_path(source, "0.3.0-beta.10", revision, ROOT)


def test_prerelease_order_is_numeric_and_build_metadata_is_ignored():
    assert version_key("0.3.0-beta.9") < version_key("0.3.0-beta.10")
    assert version_key("0.3.0-beta.10") < version_key("0.3.0")
    assert version_key("0.3.0+build.1") == version_key("0.3.0+build.2")


def test_older_portable_archive_restores_and_migrates_real_database(tmp_path, monkeypatch):
    import sqlite3
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from backend.tests.test_backup_preview import _settings
    from deployment.create_backup import create_backup
    from deployment.portable_backup import create_portable_export, import_portable_backup
    from deployment.restore_backup import restore_backup

    settings = _settings(tmp_path)
    monkeypatch.setattr("logging.config.fileConfig", lambda *args, **kwargs: None)
    database = tmp_path / "core/3mm.db"
    database.unlink()
    monkeypatch.setattr("backend.config.get_settings", lambda: settings)
    config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(config, REVISION)
    monkeypatch.setattr("backend.services.backups._read_application_version", lambda: "0.3.0-beta.9")
    application_file = settings.backups.application_extensions_dir / ("a" * 24) / "data/example.txt"
    application_file.parent.mkdir(parents=True)
    application_file.write_text("archived application data")

    class Controller:
        def stop(self, services):
            pass

        def start(self, services):
            pass

        def migrate(self):
            command.upgrade(config, "head")

        def activate_and_verify(self):
            with sqlite3.connect(database) as connection:
                assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == ScriptDirectory.from_config(config).get_current_head()

    old_key, new_key = tmp_path / "old.key", tmp_path / "new.key"
    backup = create_backup(settings, key_file=old_key, requested_by_user_id=1, controller=Controller())
    export = create_portable_export(settings.backups.storage_dir, old_key, backup.backup_id, "test-password")
    imported_root = tmp_path / "fresh-backups"
    backup_id = import_portable_backup(export.path, imported_root, new_key, "test-password", max_archive_bytes=32 * 1024 * 1024)
    application_file.write_text("live data replaced by restore")
    target_settings = settings.model_copy(update={"backups": settings.backups.model_copy(update={"storage_dir": imported_root})})
    result = restore_backup(target_settings, backup_id=backup_id, key_file=new_key,
                            requested_by_user_id=1, runtime=Controller(), service_ids=(1000, 1000),
                            state_root=tmp_path, host_config=settings.backups.host_config_file,
                            apply_ownership=False)
    assert result.state == "completed"
    assert application_file.read_text() == "archived application data"
