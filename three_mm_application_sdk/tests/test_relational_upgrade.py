"""Private wire/fixed metadata only; test keys never grant runtime authority."""

import json
import sqlite3

import pytest
from pydantic import ValidationError

from three_mm_application_sdk.relational_receipts import (
    _prepare_receipt_metadata,
    _RelationalReceiptStore,
)
from three_mm_application_sdk.relational_upgrade_receipts import (
    receipt_metadata_digest,
    upgrade_receipt_lineage,
    validate_upgrade_history,
)
from three_mm_application_sdk.relational_upgrade_wire import (
    _RelationalUpgradeTicket,
    upgrade_worker_profile_digest,
    upgraded_lifecycle,
)
from three_mm_application_sdk.relational_wire import _preparation_ticket, sign_metadata

SECRET = b"u" * 32


def ticket(**changes):
    value = {
        "version": 1,
        "action": "upgrade_prepared_schema",
        "preparation_id": "1" * 32,
        "instance_id": "1" * 24,
        "database_lineage": "2" * 32,
        "schema_revision": "0002",
        "grant_record_revision": "3" * 32,
        "authority_epoch": "4" * 32,
        "recovery_generation": "5" * 32,
        "boot_id": "00000000-0000-0000-0000-000000000001",
        "issued_at_ms": 1,
        "deadline_ms": 1001,
        "source_preparation_id": "6" * 32,
        "source_preparation_revision": "7" * 32,
        "source_schema_revision": "0001",
        "source_database_lineage": "8" * 32,
        "worker_profile_sha256": upgrade_worker_profile_digest(),
    }
    for name in _RelationalUpgradeTicket.model_fields:
        if name not in value and name != "signature":
            value[name] = "a" * 64
    return sign_metadata(SECRET, "database_upgrade", {**value, **changes})


@pytest.mark.parametrize(
    "changes",
    [
        {"action": "prepare_migrated_schema"},
        {"database_path": "/foreign"},
        {"version": True},
        {"deadline_ms": True},
        {"source_database_lineage": "2" * 32},
        {"source_schema_revision": "0002"},
        {"source_preparation_id": "1" * 32},
        {"worker_profile_sha256": "invalid"},
    ],
)
def test_upgrade_contract_is_closed_separate_and_never_reuses_source(changes):
    with pytest.raises(ValidationError):
        _RelationalUpgradeTicket.model_validate(ticket(**changes))


def test_upgrade_signature_cannot_be_used_as_initial_preparation_or_other_purpose():
    value = ticket()
    with pytest.raises(ValidationError):
        _preparation_ticket(value)
    with pytest.raises(ValueError, match="signature"):
        upgraded_lifecycle(
            sign_metadata(SECRET, "migration_preparation", value), SECRET
        )
    assert upgraded_lifecycle(value, SECRET)["schema_revision"] == "0002"


def test_completed_history_is_not_reinterpreted_as_fresh_worker_permission():
    # Old signed worker profile remains historical lifecycle evidence. Current
    # Core/Root execution checks enforce their current profile separately.
    value = ticket(worker_profile_sha256="0" * 64)
    assert upgraded_lifecycle(value, SECRET)["schema_revision"] == "0002"


@pytest.fixture
def database():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE three_mm_schema_migrations(revision TEXT PRIMARY KEY)"
    )
    connection.execute("INSERT INTO three_mm_schema_migrations VALUES ('0001')")
    connection.execute("CREATE TABLE business(value TEXT)")
    connection.execute("INSERT INTO business VALUES ('original')")
    _prepare_receipt_metadata(
        connection, database_lineage="1" * 32, schema_revision="0001", secret=SECRET
    )
    old = _RelationalReceiptStore(
        database_lineage="1" * 32, schema_revision="0001", secret=SECRET
    )
    old._insert(connection, "2" * 32, "a" * 64)
    connection.commit()
    yield connection
    connection.close()


def test_upgrade_keeps_original_receipts_across_multiple_forward_schemas(database):
    db = database
    original = db.execute("SELECT payload FROM three_mm_relational_commits").fetchone()[
        0
    ]
    for previous, current, source, target in (
        ("0001", "0002", "1" * 32, "3" * 32),
        ("0002", "0003", "3" * 32, "4" * 32),
    ):
        before = receipt_metadata_digest(db)
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO three_mm_schema_migrations VALUES (?)", (current,))
        assert receipt_metadata_digest(db) == before
        upgrade_receipt_lineage(
            db,
            source_lineage=source,
            source_schema=previous,
            database_lineage=target,
            schema_revision=current,
            secret=SECRET,
        )
        db.commit()
        validate_upgrade_history(db, schema_revision=current, secret=SECRET)
        assert (
            db.execute("SELECT payload FROM three_mm_relational_commits").fetchone()[0]
            == original
        )
        assert db.execute("SELECT value FROM business").fetchone() == ("original",)
        with pytest.raises(ValueError, match="identity changed"):
            _RelationalReceiptStore(
                database_lineage=target, schema_revision=current, secret=SECRET
            ).lookup(db, "2" * 32, "a" * 64)


@pytest.mark.parametrize(
    "problem",
    ["foreign_schema", "signature", "receipt_deleted", "receipt_added", "trigger"],
)
def test_historical_metadata_tamper_changes_fingerprint_or_refuses_validation(
    database, problem
):
    db = database
    before = receipt_metadata_digest(db)
    if problem == "receipt_deleted":
        db.execute("DELETE FROM three_mm_relational_commits")
    elif problem == "trigger":
        db.execute(
            "CREATE TRIGGER corrupt AFTER UPDATE ON three_mm_relational_lineage BEGIN DELETE FROM three_mm_relational_commits; END"
        )
    else:
        value = json.loads(
            db.execute("SELECT payload FROM three_mm_relational_commits").fetchone()[0]
        )
        value = (
            sign_metadata(
                SECRET, "receipt", {**value, "schema_revision": "not_applied"}
            )
            if problem == "foreign_schema"
            else {**value, "signature": "0" * 64}
        )
        if problem == "receipt_added":
            db.execute(
                "INSERT INTO three_mm_relational_commits VALUES (?,?)",
                ("3" * 32, json.dumps(value)),
            )
        else:
            db.execute(
                "UPDATE three_mm_relational_commits SET payload=?", (json.dumps(value),)
            )
    if problem == "trigger":
        with pytest.raises(ValueError):
            receipt_metadata_digest(db)
    else:
        assert receipt_metadata_digest(db) != before
    if problem in {"foreign_schema", "signature", "receipt_added"}:
        with pytest.raises(ValueError):
            validate_upgrade_history(db, schema_revision="0001", secret=SECRET)


def test_history_revision_values_are_bounded_before_decoding(database):
    database.execute(
        "INSERT INTO three_mm_schema_migrations VALUES (?)", ("x" * 65536,)
    )
    with pytest.raises(ValueError, match="history changed"):
        validate_upgrade_history(database, schema_revision="0001", secret=SECRET)
