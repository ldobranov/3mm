from packages.application_sdk import ApplicationMigration


def create_note(connection):
    connection.execute('CREATE TABLE note (id INTEGER PRIMARY KEY CHECK(id=1), text TEXT NOT NULL, revision INTEGER NOT NULL)')
    connection.execute("INSERT INTO note VALUES (1, '', 0)")
    connection.execute('CREATE TABLE saves (actor INTEGER NOT NULL, request_id TEXT NOT NULL, payload TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY(actor, request_id))')


def get_migrations():
    return [ApplicationMigration('0001', create_note)]
