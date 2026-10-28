"""Actual signed file worker metadata, optional provider absence and authority fences."""
import os
import pytest
from sqlalchemy import event

from backend.services.application_resource_discovery import discover_resources
from backend.services.application_authority_management import AuthorityManagementError
from backend.tests.test_application_media_routes import environment, revoke
from backend.tests.test_application_ui_authority import ui_app, managed_installed, source_subject, source_installed

pytestmark = [pytest.mark.skipif(os.name!='posix', reason='Actual file worker'),
    pytest.mark.parametrize('ui_app', ['files'], indirect=True)]


def observe(s, scopes):
    return discover_resources(s.engine, 1, 'a'*24, scopes, transport_secret=s.secret)


@pytest.mark.parametrize('provider', ['ready', 'unavailable', 'unknown'])
def test_file_provider_readiness_is_separate_from_its_optional_image_dependency(environment, monkeypatch, provider):
    from three_mm_application_sdk import media_provider
    s = environment; monkeypatch.setattr(media_provider, 'probe_provider', lambda:provider)
    writes = []
    def trace(_connection, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE','CREATE')): writes.append(statement)
    event.listen(s.engine, 'before_cursor_execute', trace)
    try: value = observe(s, ['storage:private_files_read', 'storage:private_files_transform'])
    finally: event.remove(s.engine, 'before_cursor_execute', trace)
    files, image = value['resources']
    assert not writes and not (s.runtime/'data/sdk-media').exists()
    assert files['readiness'] == 'ready' and image['readiness'] == provider
    assert image['access'] == 'granted' and image['configured'] is True
    assert image['provider']['provider_id'] == 'image_provider_v1'
    assert 'runtime_nonce' not in str(value) and 'socket_path' not in str(value)


def test_no_file_or_media_probe_when_service_access_is_revoked(environment, monkeypatch):
    import backend.services.application_resource_discovery as resource
    s = environment; revoke(s)
    def forbidden(*args, **kwargs): pytest.fail('Unapproved scope reached the runtime')
    monkeypatch.setattr(resource, '_file_observation', forbidden)
    row = observe(s, ['storage:private_files_transform'])['resources'][0]
    assert row['access'] == 'required' and row['provider'] is None and row['configured'] is None


def test_revocation_during_probe_does_not_return_prior_resource_metadata(environment, monkeypatch):
    import backend.services.application_resource_discovery as resource
    s = environment; original = resource._file_observation
    def changed(*args, **kwargs):
        result = original(*args, **kwargs); revoke(s); return result
    monkeypatch.setattr(resource, '_file_observation', changed)
    with pytest.raises(AuthorityManagementError): observe(s, ['storage:private_files_read'])
