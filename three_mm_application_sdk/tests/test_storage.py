import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from three_mm_application_sdk import ApplicationMigration, ApplicationStorage


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
