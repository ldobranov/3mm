"""Fixed protected metadata steps; never application migration callbacks."""

import hashlib
import re

from three_mm_application_sdk.relational_receipts import (
    MAX_COMMIT_RECEIPTS,
    _decode,
    _RelationalReceiptStore,
    _replace_receipt_lineage,
)
from three_mm_application_sdk.relational_wire import (
    RelationalCommitReceipt,
    canonical,
    verify_metadata,
)

MAX_SCHEMA_HISTORY = 128


def receipt_metadata_digest(connection):
    """Bounded, key-free fingerprint; does not authenticate a lifecycle itself."""
    schema = connection.execute(
        "SELECT name, type, tbl_name, sql FROM sqlite_schema WHERE "
        "name IN ('three_mm_relational_lineage', 'three_mm_relational_commits') "
        "OR (type='trigger' AND tbl_name IN ('three_mm_relational_lineage', 'three_mm_relational_commits')) "
        "ORDER BY name LIMIT 4"
    ).fetchall()
    lineage = connection.execute(
        "SELECT singleton, substr(payload,1,2049) FROM three_mm_relational_lineage LIMIT 2"
    ).fetchall()
    receipts = connection.execute(
        "SELECT substr(transaction_id,1,33), substr(payload,1,2049) "
        "FROM three_mm_relational_commits ORDER BY transaction_id LIMIT ?",
        (MAX_COMMIT_RECEIPTS + 1,),
    ).fetchall()
    if len(schema) != 2 or len(lineage) != 1 or len(receipts) > MAX_COMMIT_RECEIPTS:
        raise ValueError("Upgrade receipt metadata exceeds fixed bounds")
    return hashlib.sha256(
        canonical([list(map(list, rows)) for rows in (schema, lineage, receipts)])
    ).hexdigest()


def validate_upgrade_history(connection, *, schema_revision, secret):
    """Old signed receipts remain evidence, never permits for the new lineage."""
    rows = connection.execute(
        "SELECT substr(revision,1,65) FROM three_mm_schema_migrations ORDER BY rowid LIMIT ?",
        (MAX_SCHEMA_HISTORY + 1,),
    ).fetchall()
    history = [row[0] for row in rows]
    if (
        not history
        or len(history) > MAX_SCHEMA_HISTORY
        or any(
            type(item) is not str
            or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", item)
            for item in history
        )
        or history[-1] != schema_revision
        or len(history) != len(set(history))
    ):
        raise ValueError("Upgrade migration history changed")
    receipts = connection.execute(
        "SELECT substr(transaction_id,1,33), substr(payload,1,2049) "
        "FROM three_mm_relational_commits LIMIT ?",
        (MAX_COMMIT_RECEIPTS + 1,),
    ).fetchall()
    if len(receipts) > MAX_COMMIT_RECEIPTS:
        raise ValueError("Upgrade receipt history exceeds bounds")
    for identifier, payload in receipts:
        receipt = RelationalCommitReceipt.model_validate(_decode(payload)).model_dump(
            mode="json"
        )
        verify_metadata(secret, "receipt", receipt)
        if (
            receipt["transaction_id"] != identifier
            or receipt["schema_revision"] not in history
        ):
            raise ValueError("Upgrade historical receipt changed")


def upgrade_receipt_lineage(
    connection,
    *,
    source_lineage,
    source_schema,
    database_lineage,
    schema_revision,
    secret,
):
    if (
        not connection.in_transaction
        or source_lineage == database_lineage
        or source_schema == schema_revision
    ):
        raise ValueError("Upgrade requires a fresh protected lineage transaction")
    _RelationalReceiptStore(
        database_lineage=source_lineage, schema_revision=source_schema, secret=secret
    )._validate_metadata(connection)
    validate_upgrade_history(connection, schema_revision=schema_revision, secret=secret)
    history = [
        row[0]
        for row in connection.execute(
            "SELECT substr(revision,1,65) FROM three_mm_schema_migrations ORDER BY rowid LIMIT 129"
        )
    ]
    if source_schema not in history[:-1]:
        raise ValueError("Upgrade is not a forward migration")
    _replace_receipt_lineage(connection, database_lineage, schema_revision, secret)
    _RelationalReceiptStore(
        database_lineage=database_lineage,
        schema_revision=schema_revision,
        secret=secret,
    )._validate(connection)
