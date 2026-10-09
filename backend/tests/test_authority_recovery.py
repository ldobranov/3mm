"""Offline recovery on disposable SQLite files, never live services/data."""

from contextlib import closing
import sqlite3

import pytest

from deployment.authority_recovery import AuthorityRecoveryError, fence_recovered_authority


def add_metadata(db, *, applications_exist=False):
    """Minimal current metadata for fake-runtime backup fixtures (not migration proof)."""
    db.executescript("""
        CREATE TABLE core_authority_guard(singleton_id INTEGER PRIMARY KEY, generation TEXT, revision INTEGER);
        INSERT INTO core_authority_guard VALUES(1, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 17);
        CREATE TABLE application_connector_bindings(id INTEGER PRIMARY KEY, authority_revision TEXT);
        CREATE TABLE devices(id INTEGER PRIMARY KEY, device_id TEXT);
        CREATE TABLE device_platform_states(device_id INTEGER PRIMARY KEY, control_generation TEXT);
    """)
    if not applications_exist:
        db.execute("""CREATE TABLE application_extension_installations(id INTEGER PRIMARY KEY,
                      authority_incarnation TEXT, authority_epoch TEXT, authority_mode TEXT,
                      configuration TEXT, status TEXT, enabled INTEGER)""")
    else:
        for name in ("authority_incarnation", "authority_epoch", "authority_mode"):
            db.execute(f"ALTER TABLE application_extension_installations ADD COLUMN {name} TEXT")
        db.execute("""UPDATE application_extension_installations SET
                      authority_incarnation='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
                      authority_epoch='cccccccccccccccccccccccccccccccc', authority_mode='compatibility'""")


def snapshot(path):
    with closing(sqlite3.connect(path)) as db:
        return {table: db.execute(f"SELECT * FROM {table}").fetchall()
                for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "state.db"
    with closing(sqlite3.connect(path)) as db, db:
        add_metadata(db)
        db.execute("INSERT INTO devices VALUES(1, 'dev_stable')")
        db.execute("INSERT INTO device_platform_states VALUES(1, ?)", ("d" * 32,))
        for i, mode in enumerate(("compatibility", "review_required"), 1):
            db.execute("INSERT INTO application_extension_installations VALUES(?, ?, ?, ?, ?, 'recovery_required', 0)",
                       (i, str(i) * 32, "c" * 32, mode, '{"private":"do-not-log"}'))
        db.execute("INSERT INTO application_connector_bindings VALUES(1, ?)", ("e" * 32,))
        db.executescript("""
            CREATE TABLE device_credentials(id INTEGER PRIMARY KEY, secret_hash TEXT);
            INSERT INTO device_credentials VALUES(1, 'preserve-secret-verifier');
            CREATE TABLE device_states(id INTEGER PRIMARY KEY, desired_revision INTEGER, reported_revision INTEGER);
            INSERT INTO device_states VALUES(1, 17, 16);
            CREATE TABLE application_command_epochs(installation_id INTEGER, generation TEXT);
            INSERT INTO application_command_epochs VALUES(1, 'ffffffffffffffffffffffffffffffff');
            CREATE TABLE application_job_states(id INTEGER PRIMARY KEY, lease_token TEXT, lease_until TEXT,
                                               last_outcome TEXT, last_error TEXT, cursor TEXT);
            INSERT INTO application_job_states VALUES(1, 'busy', 'later', 'unknown', 'execution_unconfirmed', 'cursor-preserved');
            CREATE TABLE device_commands(id INTEGER PRIMARY KEY, command_type TEXT, status TEXT,
                                         error TEXT, result TEXT, delivered_at TEXT, delivery_attempts INTEGER);
            INSERT INTO device_commands VALUES(1, 'capability.invoke', 'queued', NULL, NULL, NULL, 0);
            INSERT INTO device_commands VALUES(2, 'application.capability.invoke', 'delivered', NULL, '{"receipt":"preserve"}', '2026-10-08', 1);
            INSERT INTO device_commands VALUES(3, 'capability.invoke', 'unknown', 'execution_unconfirmed', '{}', '2026-10-07', 2);
            INSERT INTO device_commands VALUES(4, 'module.install', 'delivered', NULL, '{}', '2026-10-07', 1);
            INSERT INTO device_commands VALUES(5, 'capability.invoke', 'queued', NULL, '{"attempted":true}', NULL, 1);
            INSERT INTO device_commands VALUES(6, 'capability.invoke', 'queued', NULL, '{"attempted":true}', '2026-10-07', 0);
        """)
    return path


@pytest.mark.parametrize("reason", ["backup_restore", "restore_rollback", "deployment_rollback", "factory_reset"])
def test_fresh_fences_preserve_identity_modes_secrets_and_uncertain_evidence(database, reason, caplog):
    before = snapshot(database)
    with caplog.at_level("INFO"):
        first = fence_recovered_authority(database, reason=reason)
    after = snapshot(database)
    assert (first.applications, first.connectors, first.devices) == (2, 1, 1)
    assert after["core_authority_guard"] == [(1, first.generation, 2)]
    assert first.generation != before["core_authority_guard"][0][1]
    for old, new in zip(before["application_extension_installations"], after["application_extension_installations"]):
        assert new[:2] == old[:2] and new[3:] == old[3:] and new[2] != old[2]
    for table in ("devices", "device_credentials", "device_states"):
        assert after[table] == before[table]
    assert after["device_platform_states"][0][1] != before["device_platform_states"][0][1]
    assert after["application_connector_bindings"][0][1] != before["application_connector_bindings"][0][1]
    assert after["application_command_epochs"] != before["application_command_epochs"]
    assert after["device_commands"][0][2] == "failed"
    assert after["device_commands"][1][2:4] == ("unknown", "restore_unconfirmed")
    assert after["device_commands"][1][4:] == before["device_commands"][1][4:]
    assert after["device_commands"][2:4] == before["device_commands"][2:4]
    for old, current in zip(before["device_commands"][4:], after["device_commands"][4:]):
        assert current[2:4] == ("unknown", "restore_unconfirmed")
        assert current[4:] == old[4:]
    claim = after["application_job_states"][0]
    assert claim[1] and claim[1] != "busy" and claim[2] is None
    assert claim[3:] == ("unknown", "restore_unconfirmed", "cursor-preserved")
    assert "do-not-log" not in caplog.text and "preserve-secret-verifier" not in caplog.text
    second = fence_recovered_authority(database, reason=reason)
    assert second.generation not in {first.generation, before["core_authority_guard"][0][1]}


@pytest.mark.parametrize("corrupt", [
    "DELETE FROM core_authority_guard", "DROP TABLE core_authority_guard",
    "UPDATE core_authority_guard SET revision=0", "UPDATE core_authority_guard SET generation='invalid'",
    "UPDATE application_extension_installations SET authority_mode='enforced'",
    "UPDATE application_extension_installations SET authority_incarnation=NULL",
    "UPDATE application_connector_bindings SET authority_revision='invalid'",
    "DELETE FROM device_platform_states", "UPDATE device_platform_states SET control_generation=NULL",
    "DROP TABLE application_connector_bindings",
])
def test_missing_or_corrupt_metadata_never_falls_back_or_repairs(database, corrupt):
    with closing(sqlite3.connect(database)) as db, db:
        db.execute(corrupt)
    before = snapshot(database)
    with pytest.raises(AuthorityRecoveryError):
        fence_recovered_authority(database, reason="restore_rollback", allow_legacy=True)
    assert snapshot(database) == before


def test_error_after_generation_updates_rolls_back_every_fence(database, caplog):
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("""CREATE TRIGGER fail_command_update BEFORE UPDATE ON device_commands
                      BEGIN SELECT RAISE(ABORT, 'injected'); END""")
    before = snapshot(database)
    with caplog.at_level("INFO"), pytest.raises(AuthorityRecoveryError):
        fence_recovered_authority(database, reason="backup_restore")
    assert snapshot(database) == before
    assert "Recovery authority fenced" not in caplog.text


def test_only_explicit_pre_metadata_rollback_may_use_legacy(tmp_path):
    database = tmp_path / "old.db"
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("CREATE TABLE alembic_version(version_num TEXT)")
        db.execute("INSERT INTO alembic_version VALUES('a7bf06b7c8d9')")
    before = snapshot(database)
    with pytest.raises(AuthorityRecoveryError):
        fence_recovered_authority(database, reason="backup_restore")
    assert fence_recovered_authority(database, reason="deployment_rollback", allow_legacy=True).generation is None
    assert snapshot(database) == before
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE alembic_version SET version_num='b8c017c8d9e0'")
    with pytest.raises(AuthorityRecoveryError):
        fence_recovered_authority(database, reason="deployment_rollback", allow_legacy=True)


def test_missing_database_not_created(tmp_path):
    missing = tmp_path / "absent.db"
    with pytest.raises(AuthorityRecoveryError):
        fence_recovered_authority(missing, reason="factory_reset")
    assert not missing.exists()


@pytest.mark.parametrize("revision", ["b8c017c8d9e0", "c9d128d9e0f1", "unknown_future_revision"])
def test_new_or_unknown_revision_with_all_metadata_missing_is_not_legacy(tmp_path, revision):
    database = tmp_path / "missing-authority.db"
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("CREATE TABLE alembic_version(version_num TEXT)")
        db.execute("INSERT INTO alembic_version VALUES(?)", (revision,))
    before = snapshot(database)
    with pytest.raises(AuthorityRecoveryError):
        fence_recovered_authority(database, reason="deployment_rollback", allow_legacy=True)
    assert snapshot(database) == before


def test_legacy_revision_with_partial_policy_store_is_not_legacy(tmp_path):
    database = tmp_path / "partial-policy.db"
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("CREATE TABLE alembic_version(version_num TEXT)")
        db.execute("INSERT INTO alembic_version VALUES('a7bf06b7c8d9')")
        db.execute("CREATE TABLE application_policy_reviews(review_id TEXT)")
    with pytest.raises(AuthorityRecoveryError):
        fence_recovered_authority(database, reason="deployment_rollback", allow_legacy=True)


def test_frozen_legacy_revision_allowlist_matches_actual_pre_authority_graph():
    from alembic.script import ScriptDirectory
    from backend.tests.test_migration_history import REPOSITORY_ROOT
    from deployment.authority_recovery import PRE_AUTHORITY_REVISIONS

    graph = ScriptDirectory(str(REPOSITORY_ROOT / "backend/alembic"))
    assert PRE_AUTHORITY_REVISIONS == {r.revision for r in graph.iterate_revisions("a7bf06b7c8d9", "base")}


@pytest.mark.parametrize("rollback_corrupt", [False, True])
def test_corrupt_restored_authority_is_never_activated_and_rollback_is_fenced(tmp_path, rollback_corrupt):
    from backend.services.backups import read_backup_operation_status
    from backend.tests.test_backup_preview import _settings
    from deployment.create_backup import create_backup
    from deployment.restore_backup import restore_backup

    settings = _settings(tmp_path)
    database = tmp_path / "core/3mm.db"
    activations = []

    class Runtime:
        def stop(self, _services):
            pass
        def start(self, _services):
            pass
        def migrate(self):
            pass
        def activate_and_verify(self):
            activations.append(snapshot(database)["core_authority_guard"][0][1])

    with closing(sqlite3.connect(database)) as db, db:
        db.execute("DELETE FROM core_authority_guard")
    key = tmp_path / "backup.key"
    backup = create_backup(settings, key_file=key, requested_by_user_id=7, controller=Runtime())
    if not rollback_corrupt:
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("INSERT INTO core_authority_guard VALUES(1, ?, 9)", ("a" * 32,))
    with pytest.raises(RuntimeError, match="manual recovery" if rollback_corrupt else "authority metadata"):
        restore_backup(settings, backup_id=backup.backup_id, key_file=key,
                       requested_by_user_id=7, runtime=Runtime(), service_ids=(1000, 1000),
                       state_root=tmp_path, host_config=settings.backups.host_config_file, apply_ownership=False)
    status = read_backup_operation_status(settings.backups.storage_dir / "status.json")
    if rollback_corrupt:
        assert activations == [] and status.error_code == "restore_rollback_failed"
        assert (settings.backups.storage_dir / f".rollback-{backup.backup_id}").is_dir()
    else:
        assert len(activations) == 1 and activations[0] != "a" * 32
        assert status.state == "rolled_back"
