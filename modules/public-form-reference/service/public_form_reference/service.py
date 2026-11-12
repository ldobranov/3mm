"""Neutral demo: submit one preset choice without collecting personal data."""
from uuid import uuid4

from packages.application_sdk import ApplicationMigration
from packages.protocol.public_forms import FORM_ID, FORM_REQUEST_ID

CHOICES = ('morning', 'afternoon')
CAPACITY = 1024
PATH = '/demo-request'


def _migration(connection):
    connection.execute('CREATE TABLE demo_submission (request_id TEXT PRIMARY KEY, choice TEXT NOT NULL)')


def get_migrations():
    return [ApplicationMigration('0001', _migration)]


class FormService:
    def __init__(self, application):
        self.storage = application.storage

    def handle(self, operation_id, payload, context):
        if operation_id == 'health' and context.audience == 'internal':
            return {'status': 'ready'}
        if context.audience != 'public' or context.actor.kind != 'anonymous':
            raise ValueError('Public form requires an anonymous actor')
        if operation_id == 'show_form':
            choices = ''.join(f'<option value="{choice}">{choice.title()}</option>' for choice in CHOICES)
            return {'status': 200, 'headers': {'Cache-Control': 'no-store'},
                    'content_type': 'text/html; charset=utf-8', 'body': (
                        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
                        '<meta name="viewport" content="width=device-width, initial-scale=1">'
                        '<title>Demo request</title></head><body><main><h1>Demo request</h1>'
                        '<p>Choose a time for this example. No personal data is collected.</p>'
                        f'<form action="{PATH}" method="post">'
                        f'<input type="hidden" name="{FORM_REQUEST_ID}" value="{uuid4().hex}">'
                        f'<label>Time <select name="choice" required>{choices}</select></label> '
                        '<button type="submit">Send request</button></form></main></body></html>')}
        if operation_id != 'submit_form':
            raise ValueError('Unknown form operation')
        key = context.idempotency_key
        if not isinstance(key, str) or FORM_ID.fullmatch(key) is None or set(payload) != {'choice'}:
            raise ValueError('Invalid form submission')
        choice = payload['choice']
        if choice not in CHOICES:
            raise ValueError('Invalid form choice')
        with self.storage.transaction() as connection:
            existing = connection.execute('SELECT choice FROM demo_submission WHERE request_id = ?', (key,)).fetchone()
            if existing is not None:
                return {'status': 'accepted' if existing[0] == choice else 'conflict'}
            if connection.execute('SELECT COUNT(*) FROM demo_submission').fetchone()[0] >= CAPACITY:
                return {'status': 'capacity_reached'}
            connection.execute('INSERT INTO demo_submission (request_id, choice) VALUES (?, ?)', (key, choice))
        return {'status': 'accepted'}


def create_service(application):
    return FormService(application)
