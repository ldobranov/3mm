"""Own-application schema, invoked only by the existing migration host."""
from three_mm_application_sdk import ApplicationMigration

def first(db):
    db.execute('CREATE TABLE crud_records (entity_id TEXT NOT NULL, record_id TEXT NOT NULL, data TEXT NOT NULL, revision INTEGER NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(entity_id,record_id))')
    db.execute('CREATE TABLE crud_requests (request_id TEXT PRIMARY KEY, fingerprint TEXT, result TEXT NOT NULL, actor_id TEXT, operation_id TEXT)')

def get_migrations():
    return [ApplicationMigration('0001',first)]
