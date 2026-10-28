from three_mm_application_sdk import ApplicationMigration


def get_migrations():
    return [ApplicationMigration("0001", lambda _connection: None)]
