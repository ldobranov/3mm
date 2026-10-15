"""Separate 1.1.0 candidate source; never included in the original 1.0.0 ZIP.

Only the explicit non-root upgrade worker may call this migration. Existing
probe_writes, SDK history and outbox are untouched. No code runs on import.
"""

from three_mm_application_sdk import ApplicationMigration


def applied_prefix(connection):
    raise RuntimeError("Previously applied 0001 must not execute again")


def second(connection):
    connection.execute(
        "CREATE TABLE upgrade_probe ("
        "id INTEGER PRIMARY KEY CHECK(id = 1), "
        "version TEXT NOT NULL CHECK(version = '1.1.0'))"
    )
    connection.execute("INSERT INTO upgrade_probe (id, version) VALUES (1, '1.1.0')")


def get_migrations():
    return [
        ApplicationMigration("0001", applied_prefix),
        ApplicationMigration("0002", second),
    ]
