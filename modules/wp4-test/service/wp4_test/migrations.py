"""Only this application's legacy bootstrap schema; not scoped SQL acceptance."""
from three_mm_application_sdk import ApplicationMigration


def get_migrations():
    return [ApplicationMigration("0001", lambda connection: connection.execute(
        "CREATE TABLE wp4_test_state (singleton INTEGER PRIMARY KEY CHECK(singleton = 1))"
    ))]
