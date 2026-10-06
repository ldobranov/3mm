"""Minimal forward-only storage migration for the public-web reference."""

from three_mm_application_sdk import ApplicationMigration


def _revision_0001(connection):
    connection.execute(
        "CREATE TABLE public_reference_state ("
        "singleton INTEGER PRIMARY KEY CHECK(singleton = 1), "
        "created_at TEXT"
        ")"
    )


def get_migrations():
    return [ApplicationMigration("0001", _revision_0001)]
