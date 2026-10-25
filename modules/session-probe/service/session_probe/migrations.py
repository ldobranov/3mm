from three_mm_application_sdk import ApplicationMigration

def get_migrations():
    return [ApplicationMigration('0001',lambda db: db.execute('CREATE TABLE probe_state (singleton INTEGER PRIMARY KEY CHECK(singleton=1))'))]
