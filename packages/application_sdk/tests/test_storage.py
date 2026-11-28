import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event

import pytest

from packages.application_sdk import ApplicationMigration, ApplicationStorage


def migrations():
    def first(connection):
        connection.execute(
            "CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )

    def second(connection):
        connection.execute("ALTER TABLE records ADD COLUMN enabled INTEGER DEFAULT 1")

    return [
        ApplicationMigration("0001", first),
        ApplicationMigration("0002", second),
    ]


def test_storage_applies_forward_migrations_once(tmp_path):
    storage = ApplicationStorage(tmp_path / "data")

    storage.migrate(migrations(), "0002")
    storage.migrate(migrations(), "0002")

    assert storage.status() == {"revision": "0002", "outbox": {}}
    with sqlite3.connect(storage.database_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(records)")
        }
    assert columns == {"id", "value", "enabled"}


def test_storage_rejects_downgrade_or_divergent_history(tmp_path):
    storage = ApplicationStorage(tmp_path / "data")
    storage.migrate(migrations(), "0002")

    with pytest.raises(ValueError, match="forward-compatible"):
        storage.migrate(migrations(), "0001")
    with pytest.raises(ValueError, match="forward-compatible"):
        storage.migrate([migrations()[1], migrations()[0]], "0001")


def test_concurrent_starts_apply_each_forward_revision_once(tmp_path):
    storage = ApplicationStorage(tmp_path / "data")
    storage.migrate(migrations(), "0001")
    with storage.transaction() as db:
        db.execute("INSERT INTO records(value) VALUES ('saved')")
    writers = Barrier(2, timeout=10)
    called = []

    class StartingStorage(ApplicationStorage):
        waited = False
        def _connect(self, **options):
            db = super()._connect(**options)
            def entering(sql):
                if not self.waited and sql.strip().upper() == "BEGIN IMMEDIATE":
                    self.waited = True
                    writers.wait()
            db.set_trace_callback(entering)
            return db

    def add_flag(db):
        called.append(True)
        db.execute("ALTER TABLE records ADD COLUMN enabled INTEGER DEFAULT 1")

    plan = [migrations()[0], ApplicationMigration("0002", add_flag)]
    with ThreadPoolExecutor(2) as workers:
        tasks = [workers.submit(StartingStorage(storage.data_dir).migrate, plan, "0002") for _ in range(2)]
        for task in tasks: task.result(timeout=15)
    assert len(called) == 1 and not writers.broken
    with sqlite3.connect(storage.database_path) as db:
        assert db.execute("SELECT value,enabled FROM records").fetchall() == [("saved", 1)]
        assert db.execute("SELECT revision FROM three_mm_schema_migrations ORDER BY rowid").fetchall() == [("0001",), ("0002",)]


def test_first_start_survives_busy_journal_switch_without_replaying_a_revision(tmp_path, monkeypatch):
    storage = ApplicationStorage(tmp_path)
    busy, released = Event(), Event()
    open_database = sqlite3.connect

    class Contended(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql == "PRAGMA journal_mode = WAL" and not busy.is_set():
                super().execute("PRAGMA busy_timeout = 0")
                try:
                    return super().execute(sql, parameters)
                except sqlite3.OperationalError as exc:
                    assert exc.sqlite_errorcode == sqlite3.SQLITE_BUSY
                    busy.set()
                    assert released.wait(5)
                    raise
            return super().execute(sql, parameters)

    reader = open_database(storage.database_path)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT name FROM sqlite_schema").fetchall()
        monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: open_database(*a, **k, factory=Contended))
        with ThreadPoolExecutor(1) as workers:
            task = workers.submit(storage.migrate, migrations(), "0002")
            try:
                assert busy.wait(5)
            finally:
                reader.rollback()
                released.set()
            task.result(timeout=5)
    finally:
        reader.close()
    with open_database(storage.database_path) as db:
        assert db.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert db.execute("SELECT revision FROM three_mm_schema_migrations ORDER BY rowid").fetchall() == [("0001",), ("0002",)]


def test_persistently_busy_journal_switch_does_not_run_application_migrations(tmp_path, monkeypatch):
    import packages.application_sdk as sdk
    monkeypatch.setattr(sdk, "_APPLICATION_DB_BUSY_SECONDS", 0.05)
    reader = sqlite3.connect(tmp_path / "state.sqlite3")
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT name FROM sqlite_schema").fetchall()
        with pytest.raises(sqlite3.OperationalError) as failure:
            ApplicationStorage(tmp_path).migrate(migrations(), "0002")
        assert failure.value.sqlite_errorcode == sqlite3.SQLITE_BUSY
        assert not reader.execute("SELECT name FROM sqlite_schema").fetchall()
    finally:
        reader.close()


@pytest.mark.parametrize("journal", ["wal", "delete"])
def test_refusing_unknown_history_does_not_change_application_schema(tmp_path, journal):
    storage = ApplicationStorage(tmp_path / "data")
    storage.data_dir.mkdir()
    with sqlite3.connect(storage.database_path) as db:
        assert db.execute(f"PRAGMA journal_mode={journal}").fetchone()[0] == journal
        db.execute("CREATE TABLE three_mm_schema_migrations(revision TEXT PRIMARY KEY)")
        db.execute("INSERT INTO three_mm_schema_migrations VALUES ('other')")
        db.execute("CREATE TABLE entries(note TEXT)")
        db.execute("INSERT INTO entries VALUES ('keep')")
        before = list(db.iterdump())
    with pytest.raises(ValueError, match="forward-compatible"):
        storage.migrate(migrations(), "0002")
    with sqlite3.connect(storage.database_path) as db:
        assert list(db.iterdump()) == before  # No SDK bookkeeping or application changes.
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == journal


def test_current_schema_reopens_while_another_connection_has_a_pending_write(tmp_path):
    storage = ApplicationStorage(tmp_path / "data")
    storage.migrate(migrations(), "0002")

    class ImmediateStorage(ApplicationStorage):
        def _connect(self, **options):
            db = super()._connect(**options)
            db.execute("PRAGMA busy_timeout=0")
            return db

    # Two physical connections; the writer has not released its transaction.
    with storage.transaction() as writer:
        writer.execute("INSERT INTO records(value) VALUES ('pending')")
        ImmediateStorage(storage.data_dir).migrate(migrations(), "0002")
        assert writer.in_transaction


def test_business_mutation_and_outbox_commit_or_rollback_together(tmp_path):
    storage = ApplicationStorage(tmp_path / "data")
    storage.migrate(migrations(), "0001")

    with storage.transaction() as connection:
        connection.execute("INSERT INTO records(value) VALUES ('accepted')")
        storage.enqueue_outbox(
            connection,
            outbox_id="out_1",
            event_type="record.accepted",
            payload={"record_id": 1},
            idempotency_key="record:1:accepted",
        )

    with pytest.raises(RuntimeError):
        with storage.transaction() as connection:
            connection.execute("INSERT INTO records(value) VALUES ('rolled-back')")
            storage.enqueue_outbox(
                connection,
                outbox_id="out_2",
                event_type="record.accepted",
                payload={"record_id": 2},
                idempotency_key="record:2:accepted",
            )
            raise RuntimeError("fail mutation")

    with sqlite3.connect(storage.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM three_mm_outbox").fetchone()[0] == 1
    assert storage.status()["outbox"] == {"pending": 1}
    with sqlite3.connect(storage.database_path) as connection:
        row = connection.execute("SELECT payload_hash, remote_idempotency_key FROM three_mm_outbox").fetchone()
        assert len(row[0]) == 64
        assert row[1] == "record:1:accepted"

    storage.update_outbox(
        "out_1",
        state="ambiguous",
        attempts=1,
        terminal_result="manual_review_required",
        last_error="response timeout",
    )
    assert storage.status()["outbox"] == {"ambiguous": 1}


def test_due_outbox_is_bounded_integrity_checked_and_time_aware(tmp_path):
    storage = ApplicationStorage(tmp_path / "data")
    storage.migrate(migrations(), "0001")
    with storage.transaction() as connection:
        storage.enqueue_outbox(
            connection,
            outbox_id="out_due",
            event_type="record.finalized",
            payload={"record_id": "record-1"},
            idempotency_key="remote-record-1",
        )
    items = storage.due_outbox(limit=1)
    assert len(items) == 1
    assert items[0].payload == {"record_id": "record-1"}
    assert items[0].remote_idempotency_key == "remote-record-1"

    storage.update_outbox(
        "out_due",
        state="retrying",
        attempts=1,
        next_attempt_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    assert storage.due_outbox() == []
    with pytest.raises(ValueError, match="limit"):
        storage.due_outbox(limit=101)
