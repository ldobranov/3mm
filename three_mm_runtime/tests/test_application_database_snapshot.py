"""Own SQLite checkpoint + existing activation rollback; no live mutations."""

import json
import os
import sqlite3
from pathlib import Path

import pytest

from three_mm_application_sdk import ApplicationMigration, ApplicationStorage
from three_mm_runtime import application_activation as activation
from three_mm_runtime import application_database_snapshot as snapshots
from three_mm_runtime.tests.test_application_activation import EnabledSupervisor
from three_mm_runtime.tests.test_application_files_snapshot import (
    installed,
    rollbacks,
    run_candidate,
)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX lifecycle rollback")


@pytest.fixture
def paths(tmp_path):
    data, rollback = tmp_path / "data", tmp_path / ".activation-test.rollback"
    data.mkdir()
    rollback.mkdir(mode=0o700)
    return data / "state.sqlite3", rollback / "state.sqlite3"


def write_value(database, value):
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS records(value TEXT)")
        connection.execute("DELETE FROM records")
        connection.execute("INSERT INTO records VALUES (?)", (value,))


def value(database):
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        result = connection.execute("SELECT value FROM records").fetchall()
    connection.close()
    return result


def test_quiescent_wal_snapshot_preserves_committed_data_and_outbox(paths):
    database, snapshot = paths
    storage = ApplicationStorage(database.parent)
    storage.migrate(
        [
            ApplicationMigration(
                "0001", lambda db: db.execute("CREATE TABLE records(value TEXT)")
            )
        ],
        "0001",
    )
    # Keep a WAL connection open to prove the backup reads committed WAL pages.
    with storage.transaction() as connection:
        connection.execute("INSERT INTO records VALUES ('previous')")
        storage.enqueue_outbox(
            connection,
            outbox_id="out_1",
            event_type="example.v1",
            payload={"value": "previous"},
            idempotency_key="key_1",
        )
    keeper = sqlite3.connect(database)
    try:
        keeper.execute("PRAGMA journal_mode=WAL")
        keeper.execute("UPDATE records SET value = 'wal-committed'")
        keeper.commit()
        assert Path(str(database) + "-wal").stat().st_size > 0
        assert snapshots.capture_database(database, snapshot) is True
        assert value(snapshot) == [("wal-committed",)]
        copied = sqlite3.connect(snapshot.as_uri() + "?mode=ro", uri=True)
        try:
            assert json.loads(
                copied.execute("SELECT payload_json FROM three_mm_outbox").fetchone()[0]
            ) == {"value": "previous"}
        finally:
            copied.close()
    finally:
        keeper.close()
    manifest = json.loads((snapshot.parent / "database.json").read_bytes())
    assert manifest["present"] is True
    assert manifest["size_bytes"] == snapshot.stat().st_size
    assert snapshot.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("existed", [False, True])
def test_verified_restore_keeps_candidate_and_exact_original_presence(paths, existed):
    database, snapshot = paths
    if existed:
        write_value(database, "previous")
    assert snapshots.capture_database(database, snapshot) is existed
    assert database.exists() is existed  # Capture never creates the source.
    write_value(database, "candidate")
    snapshots.restore_database(database, snapshot, existed, os.getuid(), os.getgid())
    candidate = snapshot.parent / "candidate-state.sqlite3"
    assert value(candidate) == [("candidate",)]
    assert database.exists() is existed
    if existed:
        assert value(database) == [("previous",)]
        assert value(snapshot) == [("previous",)]
        assert database.stat().st_mode & 0o777 == 0o600
    else:
        assert not snapshot.exists()
    with pytest.raises(ValueError, match="recovery review"):
        snapshots.restore_database(database, snapshot, existed, None, None)


@pytest.mark.parametrize(
    "unsafe", ["symlink", "hardlink", "directory", "wal_symlink", "orphan_wal"]
)
def test_unsafe_source_is_refused_without_foreign_writes(paths, tmp_path, unsafe):
    database, snapshot = paths
    foreign = tmp_path / "foreign.sqlite3"
    write_value(foreign, "foreign")
    before = foreign.read_bytes()
    if unsafe == "symlink":
        database.symlink_to(foreign)
    elif unsafe == "hardlink":
        os.link(foreign, database)
    elif unsafe == "directory":
        database.mkdir()
    elif unsafe == "wal_symlink":
        write_value(database, "previous")
        Path(str(database) + "-wal").symlink_to(foreign)
    else:
        Path(str(database) + "-wal").write_bytes(b"orphan")
    with pytest.raises(ValueError):
        snapshots.capture_database(database, snapshot)
    assert not snapshot.exists() and not (snapshot.parent / "database.json").exists()
    assert foreign.read_bytes() == before


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "corrupt",
        "symlink",
        "hardlink",
        "size",
        "presence",
        "version",
        "duplicate",
        "extra",
        "oversized",
    ],
)
def test_invalid_preimage_never_detaches_or_changes_candidate(paths, tmp_path, damage):
    database, snapshot = paths
    write_value(database, "previous")
    snapshots.capture_database(database, snapshot)
    write_value(database, "candidate")
    before = database.read_bytes()
    manifest_path = snapshot.parent / "database.json"
    manifest = json.loads(manifest_path.read_bytes())
    if damage == "missing":
        snapshot.unlink()
    elif damage == "corrupt":
        snapshot.write_bytes(b"not SQLite")
    elif damage == "symlink":
        snapshot.unlink()
        snapshot.symlink_to(database)
    elif damage == "hardlink":
        os.link(snapshot, tmp_path / "duplicate.sqlite3")
    elif damage == "duplicate":
        manifest_path.write_bytes(b'{"version":1,"version":1}')
    elif damage == "oversized":
        manifest_path.write_bytes(b" " * 1025)
    else:
        if damage == "size":
            manifest["size_bytes"] = True
        elif damage == "presence":
            manifest["present"] = False
        elif damage == "version":
            manifest["version"] = True
        else:
            manifest["path"] = str(database)
        manifest_path.write_text(json.dumps(manifest))
    with pytest.raises((ValueError, OSError)):
        snapshots.restore_database(database, snapshot, True, None, None)
    assert database.read_bytes() == before
    assert not (snapshot.parent / "candidate-state.sqlite3").exists()
    assert not (snapshot.parent / "restored-state.sqlite3").exists()


def test_sqlite_lock_wait_has_a_deadline_and_retains_partial_attempt(
    paths, monkeypatch
):
    database, snapshot = paths
    write_value(database, "previous")
    connection = sqlite3.connect(database)
    connection.execute("BEGIN EXCLUSIVE")
    monkeypatch.setattr(snapshots, "SNAPSHOT_TIMEOUT", 0.05)
    try:
        with pytest.raises(TimeoutError, match="deadline"):
            snapshots.capture_database(database, snapshot)
    finally:
        connection.close()
    assert value(database) == [("previous",)]
    assert snapshot.exists() and not (snapshot.parent / "database.json").exists()
    with pytest.raises(ValueError, match="already exists"):
        snapshots.capture_database(database, snapshot)


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_snapshot_sidecars_cannot_override_verified_main_database(paths, suffix):
    database, snapshot = paths
    write_value(database, "previous")
    snapshots.capture_database(database, snapshot)
    write_value(database, "candidate")
    before = database.read_bytes()
    snapshot.with_name(snapshot.name + suffix).write_bytes(b"unrecorded sidecar")
    with pytest.raises(ValueError, match="unexpected sidecars"):
        snapshots.restore_database(database, snapshot, True, None, None)
    assert database.read_bytes() == before
    assert not (snapshot.parent / "candidate-state.sqlite3").exists()


def test_mid_switch_failure_retains_preimage_candidate_and_staged_copy(
    paths, monkeypatch
):
    database, snapshot = paths
    write_value(database, "previous")
    snapshots.capture_database(database, snapshot)
    write_value(database, "candidate")
    replace = snapshots.os.replace

    def fail(source, target):
        if source.name == "restored-state.sqlite3":
            raise OSError("publication interrupted")
        replace(source, target)

    monkeypatch.setattr(snapshots.os, "replace", fail)
    with pytest.raises(OSError, match="publication interrupted"):
        snapshots.restore_database(database, snapshot, True, None, None)
    assert not database.exists()
    assert value(snapshot) == [("previous",)]
    assert value(snapshot.parent / "candidate-state.sqlite3") == [("candidate",)]
    assert value(snapshot.parent / "restored-state.sqlite3") == [("previous",)]
    with pytest.raises(ValueError, match="recovery review"):
        snapshots.restore_database(database, snapshot, True, None, None)


def test_failed_forward_migrations_restore_database_history_outbox_and_files(installed):
    storage = ApplicationStorage(installed.data)
    first = ApplicationMigration(
        "0001", lambda db: db.execute("CREATE TABLE records(value TEXT)")
    )
    storage.migrate([first], "0001")
    with storage.transaction() as connection:
        connection.execute("INSERT INTO records VALUES ('previous')")
        storage.enqueue_outbox(
            connection,
            outbox_id="out_1",
            event_type="example.v1",
            payload={"value": "previous"},
            idempotency_key="key_1",
        )
    logo = installed.files.put("logo", b"previous", expected_sha256=None)

    def committed_step(connection):
        connection.execute("UPDATE records SET value = 'partial migration'")
        connection.execute("CREATE TABLE added(value TEXT)")

    def failed_step(connection):
        installed.files.put("logo", b"candidate", expected_sha256=logo.sha256)
        connection.execute("DELETE FROM three_mm_outbox")
        raise RuntimeError("migration failed")

    supervisor = EnabledSupervisor()
    with pytest.raises(
        activation.ApplicationActivationError, match="previous version was restored"
    ):
        run_candidate(
            installed,
            lambda: storage.migrate(
                [
                    first,
                    ApplicationMigration("0002", committed_step),
                    ApplicationMigration("0003", failed_step),
                ],
                "0003",
            ),
            supervisor=supervisor,
        )
    assert value(storage.database_path) == [("previous",)]
    assert storage.due_outbox()[0].payload == {"value": "previous"}
    with sqlite3.connect(storage.database_path) as connection:
        assert connection.execute(
            "SELECT revision FROM three_mm_schema_migrations"
        ).fetchall() == [("0001",)]
        assert (
            connection.execute(
                "SELECT name FROM sqlite_schema WHERE name = 'added'"
            ).fetchall()
            == []
        )
    assert installed.files.get("logo").content == b"previous"
    assert not rollbacks(installed)
    assert supervisor.calls[-1][0] == "restart"


def test_corrupt_db_snapshot_blocks_both_db_and_file_rollback(installed):
    write_value(installed.data / "state.sqlite3", "previous")
    logo = installed.files.put("logo", b"previous", expected_sha256=None)

    def mutate():
        write_value(installed.data / "state.sqlite3", "candidate")
        installed.files.put("logo", b"candidate", expected_sha256=logo.sha256)
        (rollbacks(installed)[0] / "state.sqlite3").write_bytes(b"corrupt")

    supervisor = EnabledSupervisor()
    with pytest.raises(
        activation.ApplicationActivationError, match="rollback is unconfirmed"
    ):
        run_candidate(installed, mutate, supervisor=supervisor)
    assert value(installed.data / "state.sqlite3") == [("candidate",)]
    assert installed.files.get("logo").content == b"candidate"
    assert supervisor.calls[-1][0] == "stop"
    assert not (rollbacks(installed)[0] / "candidate-sdk-files").exists()


def test_prepared_relational_state_cannot_be_downgraded_by_legacy_activation(installed):
    record = installed.instance / "relational.json"
    record.write_bytes(b"protected preparation evidence")
    before = {
        path: path.read_bytes()
        for path in installed.instance.rglob("*")
        if path.is_file()
    }
    supervisor = EnabledSupervisor()
    with pytest.raises(
        activation.ApplicationActivationError, match="relational lifecycle"
    ):
        run_candidate(
            installed,
            lambda: pytest.fail("legacy downgrade started"),
            supervisor=supervisor,
        )
    assert not supervisor.calls and not rollbacks(installed)
    assert {
        path: path.read_bytes()
        for path in installed.instance.rglob("*")
        if path.is_file()
    } == before
