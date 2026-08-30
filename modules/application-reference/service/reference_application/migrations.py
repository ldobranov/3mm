"""Forward-only storage migrations for the neutral reference application."""

from three_mm_application_sdk import ApplicationMigration


def _revision_0001(connection):
    connection.executescript(
        """
        CREATE TABLE records (
            record_id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            status TEXT NOT NULL,
            opaque_identifier TEXT UNIQUE,
            item_count INTEGER NOT NULL DEFAULT 0,
            session_started_at TEXT,
            session_ended_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE command_results (
            idempotency_key TEXT PRIMARY KEY,
            operation_id TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE catalog_items (
            item_id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            published_revision INTEGER NOT NULL
        );
        CREATE TABLE catalog_staging (
            item_id TEXT PRIMARY KEY,
            label TEXT NOT NULL
        );
        """
    )


def get_migrations():
    return [ApplicationMigration("0001", _revision_0001)]
