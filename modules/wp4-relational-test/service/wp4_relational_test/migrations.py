"""Explicit owned migration only; importing this module performs no work."""

from three_mm_application_sdk import ApplicationMigration


def first(connection):
    connection.execute(
        "CREATE TABLE probe_writes ("
        "request_id TEXT PRIMARY KEY CHECK(length(request_id) = 32), "
        "text TEXT NOT NULL CHECK(length(text) <= 256), "
        "sha256 TEXT NOT NULL CHECK(length(sha256) = 64))"
    )


def get_migrations():
    return [ApplicationMigration("0001", first)]
