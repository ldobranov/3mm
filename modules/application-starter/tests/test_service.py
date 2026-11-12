from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from packages.application_sdk import ApplicationContext, ApplicationStorage, OperationContext, ApplicationPlatformError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'service'))
from starter_app.service import create_service
from starter_app.migrations import get_migrations


@pytest.fixture
def application(tmp_path):
    storage = ApplicationStorage(tmp_path/'own')
    storage.migrate(get_migrations(), '0001')
    return ApplicationContext('org.3mm.application-starter', '1.0.0', storage.data_dir, {}, storage)


def actor(*permissions, key=None, user=1):
    return OperationContext('operator', 'test', user_id=user, permission_ids=tuple(permissions), idempotency_key=key)


def test_missing_permission(application):
    service = create_service(application)
    with pytest.raises(ValueError, match='permission'):
        service.handle('read_note', {}, actor())
    with pytest.raises(ValueError, match='permission'):
        service.handle('save_note', {'text': 'not allowed', 'revision': 0}, actor('note_read', key='a'*32))
    assert service.handle('read_note', {}, actor('note_read')) == {'text': '', 'revision': 0}


def test_revoked_access(application):
    class Platform:
        granted = True
        def discover_command(self, binding):
            assert binding == 'resource'
            return {'access': 'granted' if self.granted else 'required',
                    'candidates': [{'selectable': True, 'readiness': 'ready'}] if self.granted else []}
    platform = Platform()
    bound = ApplicationContext(application.module_id, '1.0.0', application.data_dir, {}, application.storage, platform)
    service = create_service(bound)
    assert service.handle('observe_resource', {}, actor('note_read')) == {'state': 'ready'}
    platform.granted = False
    assert service.handle('observe_resource', {}, actor('note_read')) == {'state': 'access_required'}
    with pytest.raises(ValueError):
        service.handle('read_note', {}, actor())  # Human permission was also revoked.
    assert service.handle('save_note', {'text': 'independent', 'revision': 0}, actor('note_write', key='a'*32))['revision'] == 1


def test_provider_unavailable(application):
    for platform in [None, SimpleNamespace(discover_command=lambda _: {'access': 'granted', 'candidates': []}),
                     SimpleNamespace(discover_command=lambda _: {'access': 'granted', 'candidates': [{'selectable': False, 'readiness': 'unavailable'}]})]:
        bound = ApplicationContext(application.module_id, '1.0.0', application.data_dir, {}, application.storage, platform)
        service = create_service(bound)
        assert service.handle('observe_resource', {}, actor('note_read')) == {'state': 'unavailable'}
        assert service.handle('read_note', {}, actor('note_read')) == {'text': '', 'revision': 0}


def test_lost_platform_observation_is_not_a_write_or_success(application):
    def unavailable(_):
        raise ApplicationPlatformError('not confirmed')
    bound = ApplicationContext(application.module_id, '1.0.0', application.data_dir, {}, application.storage,
        SimpleNamespace(discover_command=unavailable))
    assert create_service(bound).handle('observe_resource', {}, actor('note_read')) == {'state': 'unavailable'}


def test_note_survives_restart_with_actor_scoped_receipt_and_conflict(application):
    service = create_service(application)
    payload = {'text': 'Здравей', 'revision': 0}
    reply = service.handle('save_note', payload, actor('note_write', key='a'*32))
    application.storage.migrate(get_migrations(), '0001')
    service = create_service(application)
    assert service.handle('read_note', {}, actor('note_read')) == reply == {'text': 'Здравей', 'revision': 1}
    assert service.handle('save_note', payload, actor('note_write', key='a'*32)) == reply
    assert service.handle('lookup_save', {'request_id': 'a'*32}, actor('note_write')) == {'status': 'found', 'revision': 1}
    assert service.handle('lookup_save', {'request_id': 'a'*32}, actor('note_write', user=2))['status'] == 'not_found'
    with pytest.raises(ValueError, match='different payload'):
        service.handle('save_note', {'text': 'changed', 'revision': 1}, actor('note_write', key='a'*32))
    with pytest.raises(ValueError, match='Note changed'):
        service.handle('save_note', {'text': 'stale', 'revision': 0}, actor('note_write', key='b'*32))
    assert service.handle('read_note', {}, actor('note_read')) == reply


def test_instances_do_not_share_storage(application, tmp_path):
    create_service(application).handle('save_note', {'text': 'first', 'revision': 0}, actor('note_write', key='a'*32))
    storage = ApplicationStorage(tmp_path/'other')
    storage.migrate(get_migrations(), '0001')
    other = ApplicationContext(application.module_id, '1.0.0', storage.data_dir, {}, storage)
    assert create_service(other).handle('read_note', {}, actor('note_read')) == {'text': '', 'revision': 0}
