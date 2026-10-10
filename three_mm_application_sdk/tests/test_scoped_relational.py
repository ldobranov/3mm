"""Real SQLite engine tests, NOT proof of production Core admission/lifecycle."""

import dataclasses
import sqlite3
import time
from pathlib import Path

import pytest

from three_mm_application_sdk import (
    ApplicationMigration,
    ApplicationPlatformClient,
    ApplicationStorage,
)
from three_mm_application_sdk.scoped_relational import (
    ApplicationRelationalExecutionUnconfirmed,
)
from three_mm_application_sdk.scoped_relational import (
    ApplicationRelationalStorageError as StorageError,
)
from three_mm_application_sdk.scoped_relational import (
    ApplicationScopedStorage,
    _TransactionAdmission,
)
from three_mm_protocol.application_extension import ApplicationRelationalStorageV1


def profile(**changes):
    return ApplicationRelationalStorageV1.model_validate(
        {
            "contract_version": 1,
            "mode": "read_write",
            "limit_class": "cooperative_v1",
            "max_database_bytes": 1024 * 1024,
            "auxiliary_pause_bytes": 1024 * 1024,
            "max_statement_bytes": 4096,
            "max_value_bytes": 4096,
            "max_result_bytes": 8192,
            "max_result_rows": 20,
            "max_transaction_ms": 1000,
            "max_busy_ms": 50,
            **changes,
        }
    )


class AdmissionDouble:
    """Ordering/refusal test double, deliberately not a fake sealed grant."""

    def __init__(self):
        self.calls = []
        self.denied = False

    def __call__(self, transaction_id, mode, digest, deadline):
        self.calls.append((transaction_id, mode, digest, deadline))
        if self.denied:
            raise StorageError("Current authority refused")
        return _TransactionAdmission(transaction_id, mode, digest, deadline)


@pytest.fixture
def prepared(tmp_path):
    legacy = ApplicationStorage(tmp_path / "data")

    def migrate(connection):
        connection.execute(
            "CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute("CREATE TABLE blobs (value BLOB)")
        connection.execute("INSERT INTO records(value) VALUES ('original')")

    legacy.migrate([ApplicationMigration("0001", migrate)], "0001")
    admission = AdmissionDouble()
    storage = ApplicationScopedStorage(
        legacy.data_dir,
        declaration=profile(),
        schema_revision="0001",
        admit=admission,
    )
    return legacy, storage, admission


def reopen(prepared, **changes):
    legacy, _, admission = prepared
    return ApplicationScopedStorage(
        legacy.data_dir,
        declaration=profile(**changes),
        schema_revision="0001",
        admit=admission,
    )


def raw_values(legacy):
    with sqlite3.connect(legacy.database_path) as connection:
        return connection.execute("SELECT value FROM records ORDER BY id").fetchall()


def test_existing_schema_and_legacy_api_are_preserved(prepared):
    legacy, storage, admission = prepared
    with storage.read_transaction() as session:
        row = session.execute("SELECT id, value FROM records").fetchone()
        assert row["value"] == "original"
        assert session.execute("PRAGMA table_info(records)").fetchall()
    assert storage.status() == {"revision": "0001", "outbox": {}}
    assert legacy.status() == storage.status()
    assert [item[1] for item in admission.calls] == ["read", "read", "read"]
    assert len({item[0] for item in admission.calls}) == 3


def test_absent_admission_does_not_open_or_create_database(tmp_path, monkeypatch):
    storage = ApplicationScopedStorage(
        tmp_path / "absent", declaration=profile(), schema_revision="0001"
    )
    monkeypatch.setattr(
        sqlite3, "connect", lambda *a, **k: pytest.fail("Opened before admission")
    )
    for method in (storage.read_transaction, storage.transaction):
        with pytest.raises(StorageError, match="admission is unavailable"):
            with method():
                pytest.fail("Entered without admission")
    with pytest.raises(StorageError):
        storage.status()
    with pytest.raises(StorageError):
        storage.due_outbox()
    with pytest.raises(StorageError):
        storage.update_outbox("out", state="succeeded", attempts=1)
    assert not storage.data_dir.exists()


@pytest.mark.parametrize(
    "change",
    [
        {"transaction_id": "stale"},
        {"mode": "write"},
        {"profile_sha256": "0" * 64},
        {"deadline": 0.0},
        {"deadline": float("inf")},
        {"deadline": True},
    ],
)
def test_mismatched_admission_never_opens_sqlite(prepared, change, monkeypatch):
    legacy, _, admission = prepared

    def invalid(*args):
        return dataclasses.replace(admission(*args), **change)

    storage = ApplicationScopedStorage(
        legacy.data_dir, declaration=profile(), schema_revision="0001", admit=invalid
    )
    monkeypatch.setattr(
        sqlite3, "connect", lambda *a, **k: pytest.fail("Opened on invalid admission")
    )
    with pytest.raises(StorageError, match="admission is invalid"):
        with storage.read_transaction():
            pytest.fail("Invalid admission")


def test_admission_cannot_extend_original_monotonic_deadline(prepared):
    legacy, _, admission = prepared

    def extended(*args):
        result = admission(*args)
        return dataclasses.replace(result, deadline=result.deadline + 1)

    storage = ApplicationScopedStorage(
        legacy.data_dir, declaration=profile(), schema_revision="0001", admit=extended
    )
    with pytest.raises(StorageError, match="expired"):
        with storage.read_transaction():
            pass


def test_each_new_transaction_requires_fresh_admission(prepared):
    legacy, storage, admission = prepared
    with storage.transaction() as session:
        session.execute("INSERT INTO records(value) VALUES (?)", ("accepted",))
    admission.denied = True
    for method in (storage.transaction, storage.read_transaction):
        with pytest.raises(StorageError, match="Current authority"):
            with method():
                pytest.fail("Reused previous admission")
    assert raw_values(legacy) == [("original",), ("accepted",)]


def test_missing_database_is_not_created_even_after_admission(tmp_path):
    storage = ApplicationScopedStorage(
        tmp_path / "absent",
        declaration=profile(),
        schema_revision="0001",
        admit=AdmissionDouble(),
    )
    with pytest.raises(StorageError, match="unavailable"):
        with storage.transaction():
            pass
    assert not storage.data_dir.exists()


def test_schema_mismatch_and_runtime_migration_never_change_data(prepared):
    legacy, _, admission = prepared
    storage = ApplicationScopedStorage(
        legacy.data_dir, declaration=profile(), schema_revision="0002", admit=admission
    )
    with pytest.raises(StorageError, match="lifecycle recovery"):
        with storage.read_transaction():
            pass
    with pytest.raises(StorageError, match="lifecycle authority"):
        storage.migrate(
            [ApplicationMigration("0002", lambda c: pytest.fail("Migration invoked"))],
            "0002",
        )
    with pytest.raises(StorageError, match="raw writable"):
        storage._connect()
    assert raw_values(legacy) == [("original",)]


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO records(value) VALUES ('forbidden')",
        "DELETE FROM records",
        "UPDATE records SET value = 'forbidden'",
        "PRAGMA user_version = 42",
        "PRAGMA journal_mode = DELETE",
        "CREATE TABLE escaped (id)",
        "BEGIN IMMEDIATE",
    ],
)
def test_read_session_cannot_write(prepared, sql):
    legacy, storage, _ = prepared
    with pytest.raises(StorageError):
        with storage.read_transaction() as session:
            session.execute(sql)
    assert raw_values(legacy) == [("original",)]


def test_read_only_declaration_refuses_write_before_admission(prepared):
    _, _, admission = prepared
    storage = reopen(prepared, mode="read")
    with pytest.raises(StorageError, match="read-only"):
        with storage.transaction():
            pass
    assert not admission.calls
    with storage.read_transaction() as session:
        assert session.execute("SELECT value FROM records").fetchone()[0] == "original"
    with pytest.raises(StorageError):
        storage.update_outbox("out", state="succeeded", attempts=1)


@pytest.mark.parametrize(
    "sql",
    [
        "ATTACH ':memory:' AS other",
        "DETACH other",
        "VACUUM",
        "VACUUM INTO '/tmp/escaped.db'",
        "CREATE TABLE escaped (id)",
        "CREATE TEMP TABLE escaped (id)",
        "DROP TABLE records",
        "ALTER TABLE records ADD COLUMN escaped",
        "CREATE INDEX escaped ON records(value)",
        "CREATE VIEW escaped AS SELECT * FROM records",
        "CREATE VIRTUAL TABLE escaped USING fts5(value)",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT escaped",
        "RELEASE escaped",
        "PRAGMA writable_schema = ON",
        "PRAGMA query_only = OFF",
        "PRAGMA foreign_keys = OFF",
        "PRAGMA max_page_count = 999999",
        "PRAGMA busy_timeout = 999999",
        "PRAGMA temp_store_directory = '/tmp'",
        "PRAGMA wal_checkpoint",
        "SELECT load_extension('escaped')",
        "DELETE FROM three_mm_schema_migrations",
        "DELETE FROM three_mm_outbox",
        "UPDATE sqlite_master SET sql = ''",
        "INSERT INTO three_mm_outbox(outbox_id) VALUES ('escape')",
    ],
)
def test_sql_escapes_are_refused_and_prior_writes_rollback(prepared, sql):
    legacy, storage, _ = prepared
    with pytest.raises(StorageError) as refused:
        with storage.transaction() as session:
            session.execute("INSERT INTO records(value) VALUES ('rollback')")
            session.execute(sql)
    assert isinstance(refused.value.__cause__, sqlite3.Error)
    sqlite_error = refused.value.__cause__
    if sql.startswith("VACUUM"):
        assert "cannot VACUUM from within a transaction" in str(sqlite_error)
    elif sql.startswith("UPDATE sqlite_master"):
        assert "may not be modified" in str(sqlite_error)
    else:
        # Function authorizer refusals use SQLITE_ERROR, not SQLITE_AUTH.
        assert (
            sqlite_error.sqlite_errorcode == sqlite3.SQLITE_AUTH
            or "not authorized" in str(sqlite_error)
        )
    assert raw_values(legacy) == [("original",)]


def test_caught_refusal_still_poisoned_and_rolls_back(prepared):
    legacy, storage, _ = prepared
    with pytest.raises(StorageError, match="has failed"):
        with storage.transaction() as session:
            session.execute("INSERT INTO records(value) VALUES ('rollback')")
            with pytest.raises(StorageError):
                session.execute("DELETE FROM three_mm_outbox")
    assert raw_values(legacy) == [("original",)]


def test_business_trigger_cannot_modify_protected_sdk_tables(prepared):
    legacy, storage, _ = prepared
    with sqlite3.connect(legacy.database_path) as connection:
        connection.execute(
            "CREATE TRIGGER audit_escape AFTER INSERT ON records BEGIN DELETE FROM three_mm_schema_migrations; END"
        )
    with pytest.raises(StorageError):
        with storage.transaction() as session:
            session.execute("INSERT INTO records(value) VALUES ('trigger')")
    assert raw_values(legacy) == [("original",)]
    assert legacy.status()["revision"] == "0001"


def test_no_public_connection_cursor_or_hook_escape(prepared):
    _, storage, _ = prepared
    with storage.transaction() as session:
        cursor = session.execute("SELECT value FROM records")
        for name in (
            "connection",
            "cursor",
            "commit",
            "rollback",
            "executescript",
            "set_authorizer",
            "set_progress_handler",
            "create_function",
            "load_extension",
            "backup",
            "serialize",
        ):
            assert not hasattr(session, name)
            assert not hasattr(cursor, name)
    for operation in (
        lambda: session.execute("SELECT 1"),
        cursor.fetchone,
        cursor.fetchall,
        lambda: cursor.rowcount,
    ):
        with pytest.raises(StorageError, match="closed"):
            operation()


def test_nested_transactions_and_platform_calls_are_denied_before_io(
    prepared, monkeypatch
):
    _, storage, _ = prepared
    client = ApplicationPlatformClient(Path("unused"), "a" * 24, b"a" * 32)
    import socket

    monkeypatch.setattr(
        socket, "socket", lambda *a, **k: pytest.fail("Platform I/O inside SQL")
    )
    with storage.transaction():
        with pytest.raises(StorageError, match="Nested"):
            with storage.read_transaction():
                pass
        with pytest.raises(RuntimeError, match="Platform calls are forbidden"):
            client._call("command.submit", {})


def test_write_and_outbox_are_atomic_and_helpers_do_not_re_admit(prepared):
    legacy, storage, admission = prepared
    with storage.transaction() as session:
        result = session.executemany(
            "INSERT INTO records(value) VALUES (?)", [("one",), ("two",)]
        )
        assert result.rowcount == 2
        assert result.lastrowid is None
        storage.enqueue_outbox(
            session,
            outbox_id="out_1",
            event_type="record.accepted",
            payload={"id": 2},
            idempotency_key="record:2",
        )
    assert len(admission.calls) == 1
    with pytest.raises(RuntimeError, match="rollback"):
        with storage.transaction() as session:
            session.execute("INSERT INTO records(value) VALUES ('rollback')")
            storage.enqueue_outbox(
                session,
                outbox_id="out_2",
                event_type="record.accepted",
                payload={"id": 4},
                idempotency_key="record:4",
            )
            raise RuntimeError("rollback")
    assert raw_values(legacy) == [("original",), ("one",), ("two",)]
    assert [item.outbox_id for item in storage.due_outbox()] == ["out_1"]
    storage.update_outbox("out_1", state="ambiguous", attempts=1)
    assert storage.status()["outbox"] == {"ambiguous": 1}
    assert len(admission.calls) == 5


def test_outbox_cannot_accept_foreign_or_closed_session(prepared):
    legacy, storage, _ = prepared
    values = dict(
        outbox_id="out", event_type="record.accepted", payload={}, idempotency_key="out"
    )
    with legacy.transaction() as raw:
        with pytest.raises(StorageError, match="active session"):
            storage.enqueue_outbox(raw, **values)
    foreign = reopen(prepared)
    with foreign.transaction() as session:
        with pytest.raises(StorageError, match="active session"):
            storage.enqueue_outbox(session, **values)
    with storage.transaction() as session:
        pass
    with pytest.raises(StorageError, match="closed"):
        storage.enqueue_outbox(session, **values)


@pytest.mark.parametrize(
    "value", [b"x" * 65, "я" * 33, True, float("nan"), float("inf"), 2**64, object()]
)
def test_parameter_value_bounds_and_unsupported_adapters(prepared, value):
    legacy, _, _ = prepared
    storage = reopen(prepared, max_value_bytes=64)
    with pytest.raises(StorageError):
        with storage.transaction() as session:
            session.execute("INSERT INTO records(value) VALUES ('rollback')")
            session.execute("INSERT INTO blobs(value) VALUES (?)", (value,))
    assert raw_values(legacy) == [("original",)]


def test_utf8_statement_limit_before_sql(prepared):
    legacy, _, _ = prepared
    storage = reopen(prepared, max_statement_bytes=80)
    with pytest.raises(StorageError, match="statement limit"):
        with storage.transaction() as session:
            session.execute("INSERT INTO records(value) VALUES ('rollback')")
            session.execute("SELECT 1 /*" + "я" * 40 + "*/")
    assert raw_values(legacy) == [("original",)]


@pytest.mark.parametrize(
    "style", ["fetchall", "fetchmany", "iterator", "separate_cursors"]
)
def test_result_row_limit_is_aggregate_for_session(prepared, style):
    legacy, _, _ = prepared
    storage = reopen(prepared, max_result_rows=2)
    with pytest.raises(StorageError, match="row limit"):
        with storage.transaction() as session:
            session.execute("INSERT INTO records(value) VALUES ('rollback')")
            sql = "SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3"
            if style == "fetchall":
                session.execute(sql).fetchall()
            elif style == "fetchmany":
                cursor = session.execute(sql)
                cursor.fetchmany(2)
                cursor.fetchmany(1)
            elif style == "iterator":
                list(session.execute(sql))
            else:
                for _ in range(3):
                    session.execute("SELECT 1").fetchone()
    assert raw_values(legacy) == [("original",)]


def test_result_byte_and_value_limits_are_utf8_and_transaction_aggregate(prepared):
    storage = reopen(prepared, max_value_bytes=32, max_result_bytes=32)
    with pytest.raises(StorageError, match="byte limit"):
        with storage.read_transaction() as session:
            session.execute("SELECT ?", ("я" * 8,)).fetchone()
            session.execute("SELECT ?", ("я" * 8,)).fetchone()
    with pytest.raises(StorageError, match="value limit"):
        with storage.read_transaction() as session:
            session.execute("SELECT zeroblob(33)").fetchone()


def test_deadline_after_callback_and_progress_budget_rollback(prepared, monkeypatch):
    legacy, storage, _ = prepared
    actual = time.monotonic()
    with pytest.raises(StorageError, match="deadline"):
        with storage.transaction() as session:
            session.execute("INSERT INTO records(value) VALUES ('rollback')")
            monkeypatch.setattr(time, "monotonic", lambda: actual + 10)
    monkeypatch.undo()
    assert raw_values(legacy) == [("original",)]
    storage = reopen(prepared, max_transaction_ms=100, max_busy_ms=0)
    started = time.monotonic()
    with pytest.raises(StorageError):
        with storage.transaction() as session:
            session.execute("INSERT INTO records(value) VALUES ('rollback')")
            session.execute(
                "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x < 100000000) SELECT sum(x) FROM n"
            ).fetchone()
    assert time.monotonic() - started < 1.5
    assert raw_values(legacy) == [("original",)]


def test_lock_wait_is_bounded_without_retry(prepared):
    legacy, _, admission = prepared
    storage = reopen(prepared, max_transaction_ms=100, max_busy_ms=30)
    with sqlite3.connect(legacy.database_path) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        started = time.monotonic()
        with pytest.raises(StorageError, match="could not start"):
            with storage.transaction():
                pass
        assert time.monotonic() - started < 0.5
    assert len(admission.calls) == 1


def test_page_ceiling_is_enforced_and_existing_overage_is_preserved(prepared):
    legacy, _, _ = prepared
    storage = reopen(
        prepared, max_database_bytes=65536, max_value_bytes=4096, max_result_bytes=8192
    )
    with pytest.raises(StorageError):
        with storage.transaction() as session:
            for _ in range(100):
                session.execute("INSERT INTO blobs(value) VALUES (?)", (b"x" * 4000,))
    with sqlite3.connect(legacy.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM blobs").fetchone()[0] == 0
        connection.executemany(
            "INSERT INTO blobs(value) VALUES (?)", [(b"x" * 4000,)] * 30
        )
    with pytest.raises(StorageError, match="page limit"):
        with storage.transaction():
            pass
    with storage.read_transaction() as session:
        assert session.execute("SELECT COUNT(*) FROM blobs").fetchone()[0] == 30


def test_auxiliary_overage_pauses_writes_without_cleanup(prepared):
    legacy, _, _ = prepared
    storage = reopen(prepared, auxiliary_pause_bytes=65536)
    sidecar = legacy.database_path.with_name("state.sqlite3-shm")
    # Use a real live WAL reader; do not manufacture invalid SQLite sidecars.
    with sqlite3.connect(legacy.database_path) as reader:
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM records").fetchone()
        with sqlite3.connect(legacy.database_path) as writer:
            writer.executemany(
                "INSERT INTO blobs(value) VALUES (?)", [(b"x" * 4000,)] * 30
            )
        assert sidecar.exists()
        with pytest.raises(StorageError, match="auxiliary"):
            with storage.transaction():
                pass
        assert sidecar.exists()
        with storage.read_transaction() as session:
            assert session.execute("SELECT COUNT(*) FROM blobs").fetchone()[0] == 30


def test_symlink_database_is_refused(prepared, tmp_path):
    legacy, _, _ = prepared
    link_dir = tmp_path / "link-data"
    link_dir.mkdir()
    (link_dir / "state.sqlite3").symlink_to(legacy.database_path)
    storage = ApplicationScopedStorage(
        link_dir, declaration=profile(), schema_revision="0001", admit=AdmissionDouble()
    )
    with pytest.raises(StorageError, match="regular file"):
        with storage.read_transaction():
            pass


def test_virtual_and_shadow_tables_cannot_be_used_at_runtime(prepared):
    legacy, storage, _ = prepared
    with sqlite3.connect(legacy.database_path) as connection:
        connection.execute("CREATE VIRTUAL TABLE search USING fts5(value)")
        connection.execute("INSERT INTO search(value) VALUES ('hidden')")
    for sql in (
        "SELECT * FROM search",
        "SELECT * FROM search_data",
        "INSERT INTO search(value) VALUES ('escape')",
    ):
        with pytest.raises(StorageError):
            with storage.transaction() as session:
                session.execute(sql).fetchall()


def test_failed_input_generator_cannot_commit_a_partial_batch(prepared):
    legacy, storage, _ = prepared

    def batch():
        yield ("rollback",)
        raise ValueError("input failed")

    with pytest.raises(StorageError, match="has failed"):
        with storage.transaction() as session:
            with pytest.raises(StorageError):
                session.executemany("INSERT INTO records(value) VALUES (?)", batch())
    assert raw_values(legacy) == [("original",)]


def test_empty_batch_is_still_a_closed_lifetime_bounded_cursor(prepared):
    _, storage, _ = prepared
    with storage.transaction() as session:
        result = session.executemany("INSERT INTO records(value) VALUES (?)", [])
        assert result.rowcount == 0
        assert result.lastrowid is None
        assert result.fetchall() == []
    with pytest.raises(StorageError, match="closed"):
        result.fetchone()


def test_lost_commit_result_is_unconfirmed_and_never_replayed(prepared, monkeypatch):
    legacy, storage, admission = prepared
    real_connect = sqlite3.connect

    class LostCommit(sqlite3.Connection):
        def commit(self):
            super().commit()
            raise sqlite3.OperationalError("Lost outcome after commit")

    monkeypatch.setattr(
        sqlite3, "connect", lambda *a, **kw: real_connect(*a, **kw, factory=LostCommit)
    )
    with pytest.raises(ApplicationRelationalExecutionUnconfirmed) as unconfirmed:
        with storage.transaction() as session:
            session.execute("INSERT INTO records(value) VALUES ('committed')")
    assert unconfirmed.value.transaction_id == admission.calls[0][0]
    assert len(admission.calls) == 1
    monkeypatch.undo()
    assert raw_values(legacy) == [("original",), ("committed",)]
    from three_mm_application_sdk.transaction_guard import relational_transaction_active

    assert relational_transaction_active.get() is False


def test_file_calls_in_sql_are_not_misclassified_as_uncertain_writes(prepared):
    from three_mm_application_sdk import (
        ApplicationFileExecutionUnconfirmed,
        ApplicationScopedFileStorage,
    )

    _, storage, _ = prepared

    class Platform:
        def _call(self, *args):
            pytest.fail("File request inside SQL reached platform")

    files = ApplicationScopedFileStorage(storage.data_dir, platform=Platform())
    with storage.transaction():
        with pytest.raises(
            RuntimeError, match="Platform calls are forbidden"
        ) as refused:
            files.put("logo", b"x", expected_sha256=None)
        assert not isinstance(refused.value, ApplicationFileExecutionUnconfirmed)
        with pytest.raises(RuntimeError, match="Platform calls are forbidden"):
            files.operation_status("a" * 32)


def test_supported_api_cannot_rebind_namespace_limits_or_session_mode(prepared):
    _, storage, _ = prepared
    for name, value in (
        ("data_dir", Path("foreign")),
        ("database_path", Path("foreign.db")),
        ("declaration", profile(max_value_bytes=8000)),
        ("schema_revision", "0002"),
        ("profile_sha256", "0" * 64),
    ):
        with pytest.raises(AttributeError):
            setattr(storage, name, value)
    with storage.read_transaction() as session:
        for name, value in (
            ("mode", "write"),
            ("storage", None),
            ("limits", profile()),
        ):
            with pytest.raises(AttributeError):
                setattr(session, name, value)


def test_empty_batch_still_checks_statement_bound(prepared):
    _, storage, _ = prepared
    with pytest.raises(StorageError, match="statement limit"):
        with storage.transaction() as session:
            session.executemany("SELECT 1 /*" + "x" * 4096 + "*/", [])
