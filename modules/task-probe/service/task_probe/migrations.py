from three_mm_application_sdk import ApplicationMigration


def _initial(connection):
    connection.execute("CREATE TABLE task_probe_attempts (attempt_id INTEGER PRIMARY KEY, task_run_id TEXT NOT NULL)")


def get_migrations():
    return [ApplicationMigration("0001", _initial)]
