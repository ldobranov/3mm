"""Shared application-owned note; optional resource observation has no effects."""
import json
import re

from packages.application_sdk import ApplicationPlatformError


def request_id(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
        raise ValueError('An original request ID is required')
    return value


class Service:
    def __init__(self, application):
        self.application = application

    def handle(self, operation_id, payload, context):
        if operation_id == 'health' and context.audience == 'internal' and payload == {}:
            return {'status': 'ready'}
        permission = 'note_write' if operation_id in {'save_note', 'lookup_save'} else 'note_read'
        if not context.has_application_permission(permission):
            raise ValueError('Current application permission is required')
        if operation_id == 'observe_resource' and payload == {}:
            if self.application.platform is None:
                return {'state': 'unavailable'}
            try:
                observed = self.application.platform.discover_command('resource')
            except ApplicationPlatformError:
                return {'state': 'unavailable'}
            if observed['access'] != 'granted':
                return {'state': 'access_required'}
            candidates = observed['candidates']
            ready = len(candidates) == 1 and candidates[0]['selectable'] and candidates[0]['readiness'] == 'ready'
            return {'state': 'ready' if ready else 'unavailable'}
        # Network/provider calls never run while our own SQLite write is locked.
        with self.application.storage.transaction() as connection:
            if operation_id == 'read_note' and payload == {}:
                row = connection.execute('SELECT text,revision FROM note WHERE id=1').fetchone()
                return dict(row)
            if operation_id == 'lookup_save' and set(payload) == {'request_id'}:
                row = connection.execute('SELECT result FROM saves WHERE actor=? AND request_id=?',
                    (context.user_id, request_id(payload['request_id']))).fetchone()
                return {'status': 'found', 'revision': json.loads(row[0])['revision']} if row else {'status': 'not_found', 'revision': None}
            if (operation_id != 'save_note' or set(payload) != {'text', 'revision'}
                    or not isinstance(payload['text'], str) or len(payload['text']) > 200
                    or type(payload['revision']) is not int or payload['revision'] < 0):
                raise ValueError('Operation or payload is invalid')
            original = request_id(context.idempotency_key)
            canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            old = connection.execute('SELECT payload,result FROM saves WHERE actor=? AND request_id=?',
                (context.user_id, original)).fetchone()
            if old:
                if old['payload'] != canonical:
                    raise ValueError('Original request has a different payload')
                return json.loads(old['result'])
            changed = connection.execute('UPDATE note SET text=?,revision=revision+1 WHERE id=1 AND revision=?',
                (payload['text'], payload['revision'])).rowcount
            if changed != 1:
                raise ValueError('Note changed; read the saved revision before editing')
            result = {'text': payload['text'], 'revision': payload['revision']+1}
            connection.execute('INSERT INTO saves VALUES (?,?,?,?)',
                (context.user_id, original, canonical, json.dumps(result)))
            return result


def create_service(application):
    return Service(application)
