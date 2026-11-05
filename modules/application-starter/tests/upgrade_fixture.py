"""Trusted, disposable old-package seed and candidate verification for this note.

These assertions are domain evidence, not installed Core authority or universal
data preservation. The runner imports each service from its exact wheel in a
separate process. Never seed real/personal data here.
"""
from three_mm_application_sdk import OperationContext


def seed(application):
    from starter_app.service import create_service

    request_id = '9' * 32
    payload = {'text': 'Disposable upgrade note · бележка', 'revision': 0}
    actor = OperationContext('operator', 'upgrade-seed', user_id=1,
        permission_ids=('note_read', 'note_write'), idempotency_key=request_id)
    saved = create_service(application).handle('save_note', payload, actor)
    return {'saved': saved, 'payload': payload, 'request_id': request_id}


def verify(application, expected):
    from starter_app.service import create_service

    service = create_service(application)
    actor = OperationContext('operator', 'upgrade-verify', user_id=1,
        permission_ids=('note_read', 'note_write'), idempotency_key=expected['request_id'])
    assert service.handle('read_note', {}, actor) == expected['saved']
    assert service.handle('lookup_save', {'request_id': expected['request_id']}, actor) == {
        'status': 'found', 'revision': expected['saved']['revision']}
    # Reading the original receipt must not apply the old edit a second time.
    assert service.handle('save_note', expected['payload'], actor) == expected['saved']
    assert service.handle('read_note', {}, actor) == expected['saved']
    other = OperationContext('operator', 'upgrade-other', user_id=2,
        permission_ids=('note_read', 'note_write'))
    assert service.handle('lookup_save', {'request_id': expected['request_id']}, other)['status'] == 'not_found'
