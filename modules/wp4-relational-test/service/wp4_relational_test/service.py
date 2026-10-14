"""Synthetic own-DB actions only; no direct SQL/files/network or startup effects."""

import hashlib
import re

from three_mm_application_sdk.scoped_relational import (
    ApplicationRelationalExecutionUnconfirmed,
    ApplicationRelationalStorageError,
    ApplicationScopedStorage,
)


class Service:
    def __init__(self, application):
        # Factory and health must not open SQLite or request admission.
        self.application = application

    def handle(self, operation_id, payload, context):
        if operation_id == "health" and context.audience == "internal":
            return {"status": "ready"}
        if context.audience != "administrator" or context.user_id is None:
            raise ValueError("A Core-authenticated administrator is required")
        if operation_id not in {"db_get", "db_put", "db_record", "db_boundary"}:
            raise ValueError("Unknown relational test operation")
        storage = self.application.storage
        if not isinstance(storage, ApplicationScopedStorage):
            raise ValueError("This fixture requires the scoped relational adapter")
        if operation_id in {"db_put", "db_record"}:
            identifier = payload.get("request_id")
            if not isinstance(identifier, str) or not re.fullmatch(
                r"[0-9a-f]{32}", identifier
            ):
                raise ValueError("Persist a 32-hex request ID before a write")
        if operation_id == "db_put":
            text = payload.get("text")
            if not isinstance(text, str) or len(text) > 256:
                raise ValueError("Synthetic text must be at most 256 characters")
            if context.idempotency_key != identifier:
                raise ValueError("Use the same request ID and command idempotency key")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            result = {
                "status": "unconfirmed",
                "request_id": identifier,
                "sha256": None,
                "transaction_id": None,
            }
            try:
                with storage.transaction() as db:
                    existing = db.execute(
                        "SELECT text, sha256 FROM probe_writes WHERE request_id = ?",
                        (identifier,),
                    ).fetchone()
                    if existing is not None:
                        status = (
                            "replayed"
                            if tuple(existing) == (text, digest)
                            else "conflict"
                        )
                    elif (
                        db.execute("SELECT COUNT(*) FROM probe_writes").fetchone()[0]
                        >= 16
                    ):
                        status = "full"
                    else:
                        db.execute(
                            "INSERT INTO probe_writes(request_id, text, sha256) VALUES (?, ?, ?)",
                            (identifier, text, digest),
                        )
                        status = "stored"
                # Only claim stored/replayed after the signed completion returns.
                return {
                    **result,
                    "status": status,
                    "sha256": digest if status in {"stored", "replayed"} else None,
                }
            except ApplicationRelationalExecutionUnconfirmed as error:
                return {**result, "transaction_id": error.transaction_id}
            except ApplicationRelationalStorageError:
                # No retry, replacement ID, migration, or direct SQLite fallback.
                return result
        if operation_id == "db_get":
            try:
                with storage.read_transaction() as db:
                    count = db.execute("SELECT COUNT(*) FROM probe_writes").fetchone()[
                        0
                    ]
                    latest = db.execute(
                        "SELECT text, sha256 FROM probe_writes ORDER BY rowid DESC LIMIT 1"
                    ).fetchone()
                return {
                    "status": "found" if latest else "missing",
                    "text": latest[0] if latest else "",
                    "sha256": latest[1] if latest else None,
                    "write_count": count,
                }
            except ApplicationRelationalStorageError:
                return {
                    "status": "blocked",
                    "text": "",
                    "sha256": None,
                    "write_count": None,
                }
        if operation_id == "db_record":
            result = {
                "status": "blocked",
                "record_kind": "application_record_not_core_receipt",
                "request_id": identifier,
                "sha256": None,
            }
            try:
                with storage.read_transaction() as db:
                    row = db.execute(
                        "SELECT sha256 FROM probe_writes WHERE request_id = ?",
                        (identifier,),
                    ).fetchone()
                return {
                    **result,
                    "status": "found" if row else "missing",
                    "sha256": row[0] if row else None,
                }
            except ApplicationRelationalStorageError:
                return result
        try:
            with storage.read_transaction() as db:
                # In-memory target only: a broken boundary cannot touch another file.
                db.execute("ATTACH DATABASE ':memory:' AS other")
            return {"status": "unexpected_allowed"}
        except ApplicationRelationalStorageError:
            return {"status": "blocked"}


def create_service(application):
    return Service(application)
