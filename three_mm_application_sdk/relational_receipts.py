"""Private own-DB commit evidence; preparation belongs to protected lifecycle.

Not called by ApplicationStorage.migrate or normal startup. The host lifecycle
adapter must quiesce/snapshot before preparing or changing any lineage/key.
"""

import json
import re
import sqlite3

from three_mm_application_sdk.relational_wire import (
    RelationalCommitReceipt,
    canonical,
    sign_metadata,
    verify_metadata,
)

MAX_COMMIT_RECEIPTS = 4096
_TABLES = {
    "three_mm_relational_lineage": "CREATE TABLE three_mm_relational_lineage (singleton INTEGER PRIMARY KEY CHECK (singleton = 1), payload TEXT NOT NULL)",
    "three_mm_relational_commits": "CREATE TABLE three_mm_relational_commits (transaction_id TEXT PRIMARY KEY, payload TEXT NOT NULL)",
}


def _identity(value):
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ValueError("Invalid relational identity")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate receipt metadata key")
        result[key] = value
    return result


def _decode(value):
    if type(value) is not str or not 0 < len(value) <= 2048:
        raise ValueError("Invalid receipt metadata size")
    return json.loads(value, object_pairs_hook=_unique)


class _RelationalReceiptStore:
    """Host-bound lineage/key; not writable configuration available to business SQL."""

    def __init__(self, *, database_lineage, schema_revision, secret):
        _identity(database_lineage)
        if type(schema_revision) is not str or not re.fullmatch(
            r"[a-z0-9][a-z0-9_.-]{0,63}", schema_revision
        ):
            raise ValueError("Invalid receipt schema identity")
        self.__lineage = database_lineage
        self.__schema = schema_revision
        self.__secret = secret
        self.__expected = sign_metadata(
            secret,
            "lineage",
            {
                "version": 1,
                "database_lineage": database_lineage,
                "schema_revision": schema_revision,
            },
        )

    def _validate(self, connection):
        rows = connection.execute(
            "SELECT name, type, tbl_name, sql FROM sqlite_schema WHERE "
            "name IN ('three_mm_relational_lineage', 'three_mm_relational_commits') "
            "OR (type = 'trigger' AND tbl_name IN ('three_mm_relational_lineage', 'three_mm_relational_commits'))"
        ).fetchall()
        if (
            len(rows) != 2
            or {row[0]: row[3] for row in rows if row[1] == "table"} != _TABLES
        ):
            raise ValueError("Receipt metadata schema requires lifecycle recovery")
        lineage = connection.execute(
            "SELECT payload FROM three_mm_relational_lineage WHERE singleton = 1"
        ).fetchone()
        if lineage is None or _decode(lineage[0]) != self.__expected:
            raise ValueError("Receipt metadata lineage requires lifecycle recovery")
        revision = connection.execute(
            "SELECT revision FROM three_mm_schema_migrations ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        if revision is None or revision[0] != self.__schema:
            raise ValueError("Receipt metadata schema revision changed")

    def _before_write(self, connection):
        self._validate(connection)
        if (
            connection.execute(
                "SELECT COUNT(*) FROM three_mm_relational_commits"
            ).fetchone()[0]
            >= MAX_COMMIT_RECEIPTS
        ):
            raise ValueError("Commit receipt journal is full")

    def _insert(self, connection, transaction_id, permit_sha256):
        receipt = RelationalCommitReceipt.model_validate(
            sign_metadata(
                self.__secret,
                "receipt",
                {
                    "version": 1,
                    "transaction_id": transaction_id,
                    "permit_sha256": permit_sha256,
                    "database_lineage": self.__lineage,
                    "schema_revision": self.__schema,
                    "outcome": "committed",
                },
            )
        ).model_dump(mode="json")

        # Restricted internal authorizer: even a trigger cannot mutate a business
        # table or other SDK state during the privileged receipt insert.
        def authorize(action, first, second, database, source):
            return (
                sqlite3.SQLITE_OK
                if action == sqlite3.SQLITE_INSERT
                and first == "three_mm_relational_commits"
                and database == "main"
                and source is None
                else sqlite3.SQLITE_DENY
            )

        connection.set_authorizer(authorize)
        try:
            connection.execute(
                "INSERT INTO three_mm_relational_commits(transaction_id, payload) VALUES (?, ?)",
                (transaction_id, canonical(receipt).decode("ascii")),
            )
        finally:
            connection.set_authorizer(None)
        return receipt

    def lookup(self, connection, transaction_id, permit_sha256):
        _identity(transaction_id)
        if type(permit_sha256) is not str or not re.fullmatch(
            r"[0-9a-f]{64}", permit_sha256
        ):
            raise ValueError("Invalid receipt admission digest")
        self._validate(connection)
        row = connection.execute(
            "SELECT payload FROM three_mm_relational_commits WHERE transaction_id = ?",
            (transaction_id,),
        ).fetchone()
        if row is None:
            return {
                "transaction_id": transaction_id,
                "outcome": "execution_unconfirmed",
            }
        receipt = RelationalCommitReceipt.model_validate(_decode(row[0])).model_dump(
            mode="json"
        )
        verify_metadata(self.__secret, "receipt", receipt)
        if (
            receipt["transaction_id"] != transaction_id
            or receipt["permit_sha256"] != permit_sha256
            or receipt["database_lineage"] != self.__lineage
            or receipt["schema_revision"] != self.__schema
        ):
            raise ValueError("Receipt metadata identity changed")
        return receipt


def _prepare_receipt_metadata(connection, *, database_lineage, schema_revision, secret):
    """One forward SDK metadata step inside the lifecycle caller's transaction.

    No implicit BEGIN/COMMIT, no DB creation, key rotation or lineage replacement.
    Caller owns rollback/preimage; a normal runtime call must never use this.
    """
    if not connection.in_transaction:
        raise ValueError("Receipt preparation requires protected lifecycle transaction")
    store = _RelationalReceiptStore(
        database_lineage=database_lineage,
        schema_revision=schema_revision,
        secret=secret,
    )
    found = connection.execute(
        "SELECT name FROM sqlite_schema WHERE name IN ('three_mm_relational_lineage', 'three_mm_relational_commits')"
    ).fetchall()
    if not found:
        revision = connection.execute(
            "SELECT revision FROM three_mm_schema_migrations ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        if revision is None or revision[0] != schema_revision:
            raise ValueError("Receipt preparation schema mismatch")
        for sql in _TABLES.values():
            connection.execute(sql)
        payload = sign_metadata(
            secret,
            "lineage",
            {
                "version": 1,
                "database_lineage": database_lineage,
                "schema_revision": schema_revision,
            },
        )
        connection.execute(
            "INSERT INTO three_mm_relational_lineage(singleton, payload) VALUES (1, ?)",
            (canonical(payload).decode("ascii"),),
        )
    store._validate(connection)
    return store


def _recover_receipt_lineage(
    connection, *, previous_lineage, database_lineage, schema_revision, secret
):
    """Protected quiescent lifecycle ONLY; preserve historical commit evidence.

    No rekey, receipt rewriting, SQL callback, journal deletion or automatic
    repair. Old receipts remain signed with their ORIGINAL lineage and cannot
    acknowledge a transaction admitted against the new database lineage.
    """
    if not connection.in_transaction or previous_lineage == database_lineage:
        raise ValueError("Recovery requires a fresh protected lineage transaction")
    previous = _RelationalReceiptStore(
        database_lineage=previous_lineage,
        schema_revision=schema_revision,
        secret=secret,
    )
    previous._validate(connection)
    _validate_receipt_history(
        connection, schema_revision=schema_revision, secret=secret
    )
    _replace_receipt_lineage(connection, database_lineage, schema_revision, secret)
    result = _RelationalReceiptStore(
        database_lineage=database_lineage,
        schema_revision=schema_revision,
        secret=secret,
    )
    result._validate(connection)
    return result


def _validate_receipt_history(connection, *, schema_revision, secret):
    """Bounded readonly historical evidence check; no lineage/receipt rewrite."""
    rows = connection.execute(
        "SELECT substr(transaction_id, 1, 33), substr(payload, 1, 2049) FROM three_mm_relational_commits LIMIT ?",
        (MAX_COMMIT_RECEIPTS + 1,),
    ).fetchall()
    if len(rows) > MAX_COMMIT_RECEIPTS:
        raise ValueError("Recovery receipt evidence exceeds journal budget")
    for identifier, payload in rows:
        receipt = RelationalCommitReceipt.model_validate(_decode(payload)).model_dump(
            mode="json"
        )
        verify_metadata(secret, "receipt", receipt)
        if (
            receipt["transaction_id"] != identifier
            or receipt["schema_revision"] != schema_revision
        ):
            raise ValueError("Recovery receipt evidence is invalid")


def _replace_receipt_lineage(connection, database_lineage, schema_revision, secret):
    payload = sign_metadata(
        secret,
        "lineage",
        {
            "version": 1,
            "database_lineage": database_lineage,
            "schema_revision": schema_revision,
        },
    )

    def authorize(action, first, second, database, source):
        return (
            sqlite3.SQLITE_OK
            if (
                database == "main"
                and source is None
                and (
                    action == sqlite3.SQLITE_UPDATE
                    and first == "three_mm_relational_lineage"
                    and second == "payload"
                    or action == sqlite3.SQLITE_READ
                    and first == "three_mm_relational_lineage"
                    and second == "singleton"
                )
            )
            else sqlite3.SQLITE_DENY
        )

    connection.set_authorizer(authorize)
    try:
        if (
            connection.execute(
                "UPDATE three_mm_relational_lineage SET payload = ? WHERE singleton = 1",
                (canonical(payload).decode("ascii"),),
            ).rowcount
            != 1
        ):
            raise ValueError("Recovery lineage update was not singular")
    finally:
        connection.set_authorizer(None)
