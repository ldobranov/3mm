"""Resume one draft choice without a user account or personal data."""
from contextlib import closing
import sqlite3
import time
from uuid import uuid4

from packages.application_sdk import ApplicationMigration
from packages.protocol.public_forms import FORM_ID, FORM_REQUEST_ID, GUEST_PROOF_FIELD


CHOICES = ('morning', 'afternoon')
CAPACITY = 1024


def _migration(connection):
    connection.execute('''CREATE TABLE guest_draft (
        guest_id TEXT NOT NULL, request_id TEXT NOT NULL, choice TEXT NOT NULL,
        expires_at INTEGER NOT NULL, PRIMARY KEY (guest_id, request_id))''')


def get_migrations():
    return [ApplicationMigration('0001', _migration)]


def _page(guest_id, choice):
    options = ''.join(f'<option value="{item}"{" selected" if item == choice else ""}>{item.title()}</option>'
                      for item in CHOICES)
    status = 'Saved draft: ' + choice.title() if choice in CHOICES else 'No saved draft.'
    return {'status': 200, 'headers': {'Cache-Control': 'no-store'},
            'content_type': 'text/html; charset=utf-8', 'body': (
                '<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                '<title>Guest draft</title></head><body><main><h1>Guest draft</h1>'
                f'<p>{status}</p><p>Save a choice and reopen this page in the same browser. '
                'The guest session expires after 15 minutes.</p>'
                '<form action="/demo-guest" method="post">'
                f'<input type="hidden" name="{FORM_REQUEST_ID}" value="{uuid4().hex}">'
                f'<input type="hidden" name="{GUEST_PROOF_FIELD}" value="{guest_id}">'
                f'<label>Time <select name="choice" required>{options}</select></label> '
                '<button type="submit">Save draft</button></form></main></body></html>')}


class GuestService:
    def __init__(self, application):
        self.storage = application.storage

    def handle(self, operation_id, payload, context):
        if operation_id == 'health' and context.audience == 'internal':
            return {'status': 'ready'}
        guest = context.public_guest
        if context.audience != 'public' or context.actor.kind != 'anonymous' or guest is None:
            raise ValueError('A verified guest context is required')
        now = int(time.time())
        if now >= guest.expires_at:
            raise ValueError('Guest session expired')
        if operation_id == 'show_form':
            uri = self.storage.database_path.as_uri() + '?mode=ro'
            with closing(sqlite3.connect(uri, uri=True, timeout=1)) as connection:
                row = connection.execute('''SELECT choice FROM guest_draft WHERE guest_id = ? AND expires_at > ?
                    ORDER BY rowid DESC LIMIT 1''', (guest.guest_id, now)).fetchone()
            return _page(guest.guest_id, row[0] if row else None)
        key = context.idempotency_key
        if (operation_id != 'submit_form' or not isinstance(key, str) or FORM_ID.fullmatch(key) is None
                or set(payload) != {'choice'} or payload['choice'] not in CHOICES):
            raise ValueError('Invalid guest draft submission')
        choice = payload['choice']
        with self.storage.transaction() as connection:
            now = int(time.time())
            if now >= guest.expires_at:
                raise ValueError('Guest session expired')
            connection.execute('DELETE FROM guest_draft WHERE expires_at <= ?', (now,))
            existing = connection.execute('SELECT choice FROM guest_draft WHERE guest_id = ? AND request_id = ?',
                                          (guest.guest_id, key)).fetchone()
            if existing is not None:
                return {'status': 'accepted' if existing[0] == choice else 'conflict'}
            if connection.execute('SELECT COUNT(*) FROM guest_draft').fetchone()[0] >= CAPACITY:
                return {'status': 'capacity_reached'}
            connection.execute('INSERT INTO guest_draft VALUES (?, ?, ?, ?)',
                               (guest.guest_id, key, choice, guest.expires_at))
        return {'status': 'accepted'}


def create_service(application):
    return GuestService(application)
