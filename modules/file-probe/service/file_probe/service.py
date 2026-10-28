"""Neutral CAP11 consumer; health is independent of files/media providers."""
from three_mm_application_sdk import ApplicationMigration


def get_migrations():
    return [ApplicationMigration('0001', lambda db: db.execute('CREATE TABLE probe_metadata (id INTEGER PRIMARY KEY)'))]


class Service:
    def handle(self, operation_id, payload, context):
        if operation_id != 'health' or context.audience != 'internal':
            raise ValueError('Unsupported operation')
        return {'status': 'ready'}


def create_service(application):
    return Service()
