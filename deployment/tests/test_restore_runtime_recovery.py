"""Restore/rollback uses current keys and proves its host write boundary first.

The systemd manager is doubled here; no services, installed paths or device
commands are used. Encrypted archives, directory switches, identity crypto and
authority recovery fences are real.
"""

import errno
import subprocess
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import backend.database  # noqa: F401 - register relationship targets
from backend.db.installation_identity import CoreInstallationIdentity
from backend.installation import identity
from backend.system.backups.service import read_backup_operation_status
from backend.tests.test_backup_preview import _settings
from deployment import restore_backup as restore
from deployment.create_backup import create_backup


class BackupPause:
    def stop(self, _services):
        pass

    def start(self, _services):
        pass


def initialize_identity(database, key, monkeypatch):
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        CoreInstallationIdentity.__table__.create(engine, checkfirst=True)
        with engine.begin() as connection:
            connection.execute(CoreInstallationIdentity.__table__.delete())
        with monkeypatch.context() as environment:
            environment.setenv("AI_SETTINGS_MASTER_KEY", key)
            with Session(engine) as db:
                return identity.installation_identity(db).identity
    finally:
        engine.dispose()


def restore_fixture(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    database = tmp_path / "core/3mm.db"
    environment = settings.backups.host_config_file
    archived_key = Fernet.generate_key().decode()
    archived_identity = initialize_identity(database, archived_key, monkeypatch)
    environment.write_text(f"AI_SETTINGS_MASTER_KEY={archived_key}\n")
    key_file = tmp_path / "backup.key"
    backup = create_backup(settings, key_file=key_file, requested_by_user_id=7,
                           controller=BackupPause())
    live_key = Fernet.generate_key().decode()
    live_identity = initialize_identity(database, live_key, monkeypatch)
    environment.write_text(f"AI_SETTINGS_MASTER_KEY={live_key}\n")
    (settings.backend.uploads_dir / "logo.png").write_bytes(b"current-before-restore")
    # Neither the helper's nor the coordinator's stale process environment may
    # be used to decrypt either database. No key may be placed in child argv.
    monkeypatch.setenv("AI_SETTINGS_MASTER_KEY", Fernet.generate_key().decode())
    host_paths = (tmp_path / "host-journals", tmp_path / "hosts/instances")
    for directory in host_paths:
        directory.mkdir(parents=True)
    monkeypatch.setattr(restore, "RESTORE_HOST_WRITABLE_PATHS", host_paths)
    runtime = restore.SystemRestoreRuntime(host_config=environment)
    monkeypatch.setattr(restore, "SystemRestoreRuntime", lambda **kwargs: runtime)
    return settings, database, environment, key_file, backup, runtime, archived_identity, live_identity


@pytest.mark.parametrize("failure", [None, "migration", "applications", "bootstrap", "health"])
def test_state_switch_and_rollback_load_their_own_environment(tmp_path, monkeypatch, failure):
    (settings, database, environment, key_file, backup, runtime,
     archived_identity, live_identity) = restore_fixture(tmp_path, monkeypatch)
    children = []
    services = []
    failed = False
    legacy_key = tmp_path / 'ai-settings.key'
    pre_restore_key = environment.read_text().strip().split('=', 1)[1]
    legacy_key.write_text(pre_restore_key + '\n')

    def run(arguments, *, timeout=180):
        nonlocal failed
        if arguments[0] == "/usr/bin/systemctl":
            services.append(tuple(arguments[1:]))
            return
        assert arguments[:5] == (
            "/usr/bin/systemd-run", "--quiet", "--pipe", "--wait", "--collect")
        assert timeout == 210
        assert "--property=RuntimeMaxSec=180s" in arguments
        assert "--property=KillMode=control-group" in arguments
        assert "--property=ProtectSystem=strict" in arguments
        assert f"--property=EnvironmentFile={environment}" in arguments
        assert not any("AI_SETTINGS_MASTER_KEY=" in argument for argument in arguments)
        # Emulate PID 1 opening the file at EXECUTION time, not a cached parent
        # environment. Values below are generated single-line test fixtures.
        key = environment.read_text().strip().split("=", 1)[1]
        with monkeypatch.context() as child:
            child.setenv("AI_SETTINGS_MASTER_KEY", key)
            engine = create_engine(f"sqlite:///{database.as_posix()}")
            try:
                with Session(engine) as db:
                    observed = identity.installation_identity(db).identity
            finally:
                engine.dispose()
        if arguments[-1] == "/usr/bin/true":
            stage = "preflight"
        elif arguments[-1].endswith("/migrate_database.py"):
            stage = "migration"
            assert "/usr/sbin/runuser" in arguments
        elif arguments[-1].endswith("/restore_application_extensions.py"):
            stage = "applications"
        else:
            assert arguments[-2:] == ("-m", "components.system_runtime.activate")
            stage = "bootstrap"
        children.append((stage, observed))
        if failure == stage and not failed:
            failed = True
            raise subprocess.CalledProcessError(1, arguments)

    health_calls = 0

    def health(_endpoints):
        nonlocal health_calls
        health_calls += 1
        if failure == "health" and health_calls <= 15:
            raise restore.SmokeFailure("injected unhealthy restored runtime")

    monkeypatch.setattr(runtime, "_run", run)
    monkeypatch.setattr(restore, "verify_release", health)
    monkeypatch.setattr(restore.time, "sleep", lambda _seconds: None)
    arguments = dict(settings=settings, backup_id=backup.backup_id, key_file=key_file,
                     requested_by_user_id=7, service_ids=(1000, 1000),
                     state_root=tmp_path, host_config=environment, apply_ownership=False)
    if failure is None:
        assert restore.restore_backup(**arguments).state == "completed"
        assert children == [("preflight", live_identity), ("migration", archived_identity),
                            ("applications", archived_identity), ("bootstrap", archived_identity)]
        assert (settings.backend.uploads_dir / "logo.png").read_bytes() == b"image"
        # An upgrade after restore must use the same key as the running Core.
        # The legacy file deliberately still contains the pre-restore key.
        selected = identity.select_installer_master_key(database, environment, legacy_key)
        assert selected != pre_restore_key
        assert legacy_key.read_text() == pre_restore_key + '\n'
        with monkeypatch.context() as child:
            child.setenv('AI_SETTINGS_MASTER_KEY', selected)
            engine = create_engine(f'sqlite:///{database.as_posix()}')
            try:
                with Session(engine) as db:
                    assert identity.installation_identity(db).identity == archived_identity
            finally:
                engine.dispose()
    else:
        with pytest.raises((subprocess.CalledProcessError, RuntimeError)):
            restore.restore_backup(**arguments)
        assert children[0] == ("preflight", live_identity)
        assert children[1] == ("migration", archived_identity)
        assert children[-2:] == [("applications", live_identity), ("bootstrap", live_identity)]
        status = read_backup_operation_status(settings.backups.storage_dir / "status.json")
        assert status.state == "rolled_back" and status.error_code == "restore_rolled_back"
        assert (settings.backend.uploads_dir / "logo.png").read_bytes() == b"current-before-restore"
    assert services[-1] == ("try-restart", "3mm-update-helper.service")
    assert not (settings.backups.storage_dir / f".rollback-{backup.backup_id}").exists()


@pytest.mark.parametrize('failure', ['wrong', 'missing', 'duplicate', 'invalid'])
def test_upgrade_refuses_unverified_identity_key_without_rewriting_any_file(tmp_path, monkeypatch, failure):
    database, environment, legacy_key = (tmp_path / name for name in ('3mm.db', '3mm.env', 'ai-settings.key'))
    actual = Fernet.generate_key().decode()
    initialize_identity(database, actual, monkeypatch)
    unrelated = Fernet.generate_key().decode()
    settings = {
        'wrong': f'AI_SETTINGS_MASTER_KEY={unrelated}\n',
        'missing': 'UNRELATED=1\n',
        'duplicate': f'AI_SETTINGS_MASTER_KEY={actual}\nAI_SETTINGS_MASTER_KEY={actual}\n',
        'invalid': 'AI_SETTINGS_MASTER_KEY=not-a-key\n',
    }
    environment.write_text(settings[failure])
    if failure != 'missing':
        legacy_key.write_text(actual + '\n')
    before = database.read_bytes()
    with pytest.raises(identity.InstallationIdentityError, match='Cannot preserve'):
        identity.select_installer_master_key(database, environment, legacy_key)
    assert database.read_bytes() == before and environment.read_text() == settings[failure]


def test_installer_accepts_legacy_key_only_without_configured_key_and_generates_on_first_install(tmp_path, monkeypatch):
    database, environment, legacy_key = (tmp_path / name for name in ('3mm.db', '3mm.env', 'ai-settings.key'))
    fresh = identity.select_installer_master_key(database, environment, legacy_key)
    Fernet(fresh.encode('ascii'))
    assert not any(path.exists() for path in (database, environment, legacy_key))
    initialize_identity(database, fresh, monkeypatch)
    legacy_key.write_text(fresh + '\n')
    assert identity.select_installer_master_key(database, environment, legacy_key) == fresh


@pytest.mark.parametrize("failure", ["readonly_journal", "readonly_pointers", "child_environment", "rollback_key"])
def test_invalid_recovery_boundary_refuses_before_stop_or_switch(tmp_path, monkeypatch, failure):
    settings, _database, environment, key_file, backup, runtime, *_ = restore_fixture(tmp_path, monkeypatch)
    commands = []

    def run(arguments, **_kwargs):
        commands.append(tuple(arguments))
        assert arguments[0] != "/usr/bin/systemctl", "Must not stop live services"
        raise subprocess.CalledProcessError(1, arguments)

    monkeypatch.setattr(runtime, "_run", run)
    if failure.startswith("readonly_"):
        original = restore.tempfile.TemporaryFile
        denied = restore.RESTORE_HOST_WRITABLE_PATHS[0 if failure == "readonly_journal" else 1]

        def write_probe(*args, **kwargs):
            if kwargs.get("dir") == denied:
                raise OSError(errno.EROFS, "injected read-only restore mount")
            return original(*args, **kwargs)

        monkeypatch.setattr(restore.tempfile, "TemporaryFile", write_probe)
    elif failure == "rollback_key":
        environment.write_text(f"AI_SETTINGS_MASTER_KEY={Fernet.generate_key().decode()}\n")
    before = environment.read_bytes()
    with pytest.raises((OSError, subprocess.CalledProcessError, identity.InstallationIdentityError)):
        restore.restore_backup(settings, backup_id=backup.backup_id, key_file=key_file,
                               requested_by_user_id=7, service_ids=(1000, 1000),
                               state_root=tmp_path, host_config=environment, apply_ownership=False)
    assert environment.read_bytes() == before
    assert (settings.backend.uploads_dir / "logo.png").read_bytes() == b"current-before-restore"
    status = read_backup_operation_status(settings.backups.storage_dir / "status.json")
    assert status.state == "failed" and status.error_code == "restore_validation_failed"
    assert not (settings.backups.storage_dir / f".rollback-{backup.backup_id}").exists()
    assert len(commands) == (1 if failure == "child_environment" else 0)


def test_failed_rollback_activation_preserves_recovery_status_and_evidence(tmp_path, monkeypatch):
    settings, _database, environment, key_file, backup, runtime, *_ = restore_fixture(tmp_path, monkeypatch)
    # Environment loading works; both initial activation and rollback activation
    # fail independently. Restoring files alone must NEVER report rolled_back.
    def run(arguments, **_kwargs):
        if arguments[-2:] == ("-m", "components.system_runtime.activate"):
            raise subprocess.CalledProcessError(1, arguments)

    monkeypatch.setattr(runtime, "_run", run)
    with pytest.raises(RuntimeError, match="rollback requires manual recovery"):
        restore.restore_backup(settings, backup_id=backup.backup_id, key_file=key_file,
                               requested_by_user_id=7, service_ids=(1000, 1000),
                               state_root=tmp_path, host_config=environment, apply_ownership=False)
    status = read_backup_operation_status(settings.backups.storage_dir / "status.json")
    assert status.state == "failed" and status.error_code == "restore_rollback_failed"
    assert (settings.backups.storage_dir / f".rollback-{backup.backup_id}").is_dir()
    assert (settings.backend.uploads_dir / "logo.png").read_bytes() == b"current-before-restore"
