"""Atomic SQLite receipt primitives, not protected production host lifecycle."""

import dataclasses
import json
import sqlite3
import time

import pytest

from three_mm_application_sdk.relational_receipts import (
    _prepare_receipt_metadata,
    _RelationalReceiptStore,
)
from three_mm_application_sdk.scoped_relational import (
    ApplicationRelationalExecutionUnconfirmed,
    ApplicationRelationalStorageError,
    ApplicationScopedStorage,
)
from three_mm_application_sdk.tests.test_scoped_relational import prepared, raw_values

SECRET = b"r" * 32
LINEAGE = "1" * 32
DIGEST = "2" * 64


@pytest.fixture
def receipts(prepared):
    legacy, old, admission = prepared
    with sqlite3.connect(legacy.database_path) as db:
        db.execute("BEGIN IMMEDIATE")
        store = _prepare_receipt_metadata(
            db, database_lineage=LINEAGE, schema_revision="0001", secret=SECRET
        )

    def admit(*args):
        return dataclasses.replace(admission(*args), permit_sha256=DIGEST)

    storage = ApplicationScopedStorage(
        legacy.data_dir,
        declaration=old.declaration,
        schema_revision="0001",
        admit=admit,
        receipts=store,
    )
    return legacy, storage, admission, store


def test_receipt_and_business_and_outbox_commit_together(receipts):
    legacy, storage, admission, _ = receipts
    with storage.transaction() as db:
        db.execute("INSERT INTO records(value) VALUES ('committed')")
        storage.enqueue_outbox(
            db,
            outbox_id="one",
            event_type="example",
            payload={"one": 1},
            idempotency_key="one",
        )
    transaction_id = admission.calls[0][0]
    receipt = storage.transaction_status(transaction_id, DIGEST)
    assert receipt["outcome"] == "committed" and receipt["database_lineage"] == LINEAGE
    assert raw_values(legacy) == [("original",), ("committed",)]
    with sqlite3.connect(legacy.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM three_mm_outbox").fetchone()[0] == 1
    assert len(admission.calls) == 1  # Lookup requires no fresh runtime grant.


def test_failed_body_rolls_back_receipt_and_outbox(receipts):
    legacy, storage, admission, _ = receipts
    with pytest.raises(RuntimeError, match="business failure"):
        with storage.transaction() as db:
            db.execute("INSERT INTO records(value) VALUES ('not committed')")
            storage.enqueue_outbox(
                db,
                outbox_id="one",
                event_type="example",
                payload={},
                idempotency_key="one",
            )
            raise RuntimeError("business failure")
    assert (
        storage.transaction_status(admission.calls[0][0], DIGEST)["outcome"]
        == "execution_unconfirmed"
    )
    assert raw_values(legacy) == [("original",)]
    with sqlite3.connect(legacy.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM three_mm_outbox").fetchone()[0] == 0


def test_lost_completion_ack_after_unlock_has_durable_receipt_and_no_retry(receipts):
    legacy, old, admission, store = receipts
    completed = []

    def finish(receipt):
        # Another writer can begin now: no SQLite lock or transaction guard.
        with sqlite3.connect(legacy.database_path, timeout=0) as db:
            db.execute("BEGIN IMMEDIATE")
            db.rollback()
        completed.append(receipt)
        raise OSError("Lost Core acknowledgement")

    storage = ApplicationScopedStorage(
        legacy.data_dir,
        declaration=old.declaration,
        schema_revision="0001",
        admit=lambda *args: dataclasses.replace(admission(*args), permit_sha256=DIGEST),
        receipts=store,
        complete=finish,
    )
    with pytest.raises(ApplicationRelationalExecutionUnconfirmed) as error:
        with storage.transaction() as db:
            db.execute("INSERT INTO records(value) VALUES ('once')")
    assert completed[0]["transaction_id"] == error.value.transaction_id
    admission.denied = True
    assert (
        storage.transaction_status(error.value.transaction_id, DIGEST) == completed[0]
    )
    assert len(admission.calls) == 1 and raw_values(legacy) == [
        ("original",),
        ("once",),
    ]


def test_read_does_not_create_receipt(receipts):
    legacy, storage, admission, _ = receipts
    with storage.read_transaction() as db:
        assert db.execute("SELECT value FROM records").fetchone()[0] == "original"
    with sqlite3.connect(legacy.database_path) as db:
        assert (
            db.execute("SELECT COUNT(*) FROM three_mm_relational_commits").fetchone()[0]
            == 0
        )


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM three_mm_relational_lineage",
        "UPDATE three_mm_relational_lineage SET payload = '{}'",
        "INSERT INTO three_mm_relational_commits VALUES ('fake', '{}')",
        "DELETE FROM three_mm_relational_commits",
    ],
)
def test_business_sql_cannot_forge_or_delete_sdk_evidence(receipts, sql):
    legacy, storage, _, _ = receipts
    with pytest.raises(ApplicationRelationalStorageError):
        with storage.transaction() as db:
            db.execute("INSERT INTO records(value) VALUES ('rollback')")
            db.execute(sql)
    assert raw_values(legacy) == [("original",)]


@pytest.mark.parametrize(
    "drift",
    ["lineage", "key", "schema", "table", "trigger", "receipt", "foreign_digest"],
)
def test_lookup_refuses_tampering_or_recovery_drift(receipts, drift):
    legacy, storage, admission, store = receipts
    with storage.transaction() as db:
        db.execute("INSERT INTO records(value) VALUES ('retained')")
    identifier = admission.calls[0][0]
    digest = DIGEST
    if drift in {"lineage", "key", "schema"}:
        store = _RelationalReceiptStore(
            database_lineage="3" * 32 if drift == "lineage" else LINEAGE,
            schema_revision="0002" if drift == "schema" else "0001",
            secret=b"x" * 32 if drift == "key" else SECRET,
        )
        storage = ApplicationScopedStorage(
            legacy.data_dir,
            declaration=storage.declaration,
            schema_revision="0001",
            receipts=store,
        )
    else:
        with sqlite3.connect(legacy.database_path) as db:
            if drift == "table":
                db.execute(
                    "ALTER TABLE three_mm_relational_commits ADD COLUMN extra TEXT"
                )
            elif drift == "trigger":
                db.execute(
                    "CREATE TRIGGER forge AFTER INSERT ON three_mm_relational_commits BEGIN DELETE FROM records; END"
                )
            elif drift == "receipt":
                value = json.loads(
                    db.execute(
                        "SELECT payload FROM three_mm_relational_commits"
                    ).fetchone()[0]
                )
                value["signature"] = "0" * 64
                db.execute(
                    "UPDATE three_mm_relational_commits SET payload = ?",
                    (json.dumps(value),),
                )
            else:
                digest = "4" * 64
    with pytest.raises(ApplicationRelationalStorageError, match="lifecycle recovery"):
        storage.transaction_status(identifier, digest)
    assert raw_values(legacy) == [("original",), ("retained",)]


def test_full_receipt_journal_refuses_before_business_callback(receipts, monkeypatch):
    from three_mm_application_sdk import relational_receipts

    legacy, storage, _, _ = receipts
    monkeypatch.setattr(relational_receipts, "MAX_COMMIT_RECEIPTS", 1)
    with storage.transaction() as db:
        db.execute("INSERT INTO records(value) VALUES ('once')")
    with pytest.raises(ApplicationRelationalStorageError):
        with storage.transaction():
            pytest.fail("Callback entered after journal full")
    assert raw_values(legacy) == [("original",), ("once",)]


def test_metadata_preparation_is_forward_atomic_and_does_not_replace_lineage(prepared):
    legacy, _, _ = prepared
    with sqlite3.connect(legacy.database_path) as db:
        with pytest.raises(ValueError, match="lifecycle transaction"):
            _prepare_receipt_metadata(
                db, database_lineage=LINEAGE, schema_revision="0001", secret=SECRET
            )
        db.execute("BEGIN IMMEDIATE")
        _prepare_receipt_metadata(
            db, database_lineage=LINEAGE, schema_revision="0001", secret=SECRET
        )
        db.rollback()
        assert not db.execute(
            "SELECT name FROM sqlite_schema WHERE name LIKE 'three_mm_relational_%'"
        ).fetchall()
        db.execute("BEGIN IMMEDIATE")
        _prepare_receipt_metadata(
            db, database_lineage=LINEAGE, schema_revision="0001", secret=SECRET
        )
        db.commit()
        db.execute("BEGIN IMMEDIATE")
        _prepare_receipt_metadata(
            db, database_lineage=LINEAGE, schema_revision="0001", secret=SECRET
        )
        db.commit()
        db.execute("BEGIN IMMEDIATE")
        with pytest.raises(ValueError, match="lineage"):
            _prepare_receipt_metadata(
                db, database_lineage="5" * 32, schema_revision="0001", secret=SECRET
            )
        db.rollback()
    assert raw_values(legacy) == [("original",)]


def test_unprepared_database_is_not_implicitly_migrated(prepared):
    legacy, old, admission = prepared
    storage = ApplicationScopedStorage(
        legacy.data_dir,
        declaration=old.declaration,
        schema_revision="0001",
        admit=lambda *args: dataclasses.replace(admission(*args), permit_sha256=DIGEST),
        receipts=_RelationalReceiptStore(
            database_lineage=LINEAGE, schema_revision="0001", secret=SECRET
        ),
    )
    with pytest.raises(ApplicationRelationalStorageError):
        with storage.transaction():
            pytest.fail("Runtime implicitly prepared receipt metadata")
    with sqlite3.connect(legacy.database_path) as db:
        assert not db.execute(
            "SELECT name FROM sqlite_schema WHERE name LIKE 'three_mm_relational_%'"
        ).fetchall()


def test_receipt_insert_failure_rolls_back_business_and_keeps_original_evidence(
    receipts, monkeypatch
):
    legacy, storage, admission, store = receipts

    def fail(*args):
        raise sqlite3.OperationalError("Receipt write failed")

    monkeypatch.setattr(store, "_insert", fail)
    with pytest.raises(ApplicationRelationalStorageError):
        with storage.transaction() as db:
            db.execute("INSERT INTO records(value) VALUES ('rollback')")
    assert raw_values(legacy) == [("original",)]
    assert (
        storage.transaction_status(admission.calls[0][0], DIGEST)["outcome"]
        == "execution_unconfirmed"
    )


def test_mismatched_admission_digest_refuses_before_sqlite_open(receipts, monkeypatch):
    legacy, old, admission, store = receipts
    storage = ApplicationScopedStorage(
        legacy.data_dir,
        declaration=old.declaration,
        schema_revision="0001",
        admit=admission,
        receipts=store,
    )
    monkeypatch.setattr(
        storage,
        "_open_existing",
        lambda *args: pytest.fail("SQLite opened before signed admission validated"),
    )
    with pytest.raises(ApplicationRelationalStorageError, match="admission is invalid"):
        with storage.transaction():
            pytest.fail("Unsigned receipt execution")


@pytest.mark.skipif(
    not hasattr(time, "CLOCK_BOOTTIME"), reason="Linux suspend-aware clock"
)
def test_suspend_elapsed_time_cannot_extend_signed_core_deadline(receipts, monkeypatch):
    legacy, old, admission, store = receipts
    now = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    storage = ApplicationScopedStorage(
        legacy.data_dir,
        declaration=old.declaration,
        schema_revision="0001",
        admit=lambda *args: dataclasses.replace(
            admission(*args),
            permit_sha256=DIGEST,
            boot_deadline_ms=now // 1_000_000 + 500,
        ),
        receipts=store,
    )
    with pytest.raises(ApplicationRelationalStorageError, match="deadline exceeded"):
        with storage.transaction() as db:
            db.execute("INSERT INTO records(value) VALUES ('rollback')")
            # CLOCK_BOOTTIME advances across suspend even when monotonic does not.
            monkeypatch.setattr(
                time, "clock_gettime_ns", lambda clock: now + 10_000_000_000
            )
    assert raw_values(legacy) == [("original",)]
