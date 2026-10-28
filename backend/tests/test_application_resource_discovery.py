"""Real SDK/Core transport and approved admin UI; resource views never grant work."""
import os
from datetime import UTC, datetime, timedelta
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session

from backend.db.device import DeviceHeartbeat
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.session import UserSession
from backend.routes.application_extensions import router
from backend.services import application_resource_discovery as discovery
from backend.services.application_authority_management import AuthorityManagementError
from backend.tests.test_application_command_discovery import vertical, add_provider
from backend.tests.test_application_authority_management import installed, source_subject, source_installed, identity
from backend.tests.test_application_consent import allow, preview
from backend.tests.test_application_ui_authority import ui_app, adopt, managed_installed
from backend.utils.db_utils import get_db
from three_mm_application_sdk import ApplicationPlatformError

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Actual sealed authority and Unix transport')


def test_signed_resource_view_distinguishes_access_readiness_and_unobserved_executor(vertical):
    s = vertical
    scopes = ['command:pulse', 'connector:business_api', 'command:not_declared']
    denied = s.sdk.discover_resources(scopes)
    assert denied['resources'][0]['access'] == 'required' and denied['resources'][0]['provider'] is None
    allow(s, preview(s), scopes=['command:pulse','connector:business_api'])
    add_provider(s)
    writes = []
    def trace(_connection, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE','CREATE')): writes.append(statement)
    event.listen(s.engine, 'before_cursor_execute', trace)
    try: result = s.sdk.discover_resources(scopes)
    finally: event.remove(s.engine, 'before_cursor_execute', trace)
    command, connector, absent = result['resources']
    assert not writes and result['admission_required'] is True
    assert command['access'] == 'granted' and command['readiness'] == 'ready'
    assert command['selected_resource_id'] == s.configuration['TARGET_DEVICE_ID']
    assert connector['configured'] is True and connector['access'] == 'granted'
    assert connector['readiness'] == 'unknown' and connector['reasons'] == ['runtime_not_observed']
    assert absent['declared'] is False and absent['provider'] is None
    with s.engine.begin() as db:
        db.execute(update(DeviceHeartbeat).where(DeviceHeartbeat.device_id==1).values(received_at=datetime.now(UTC)-timedelta(days=1)))
    offline = s.sdk.discover_resources(['command:pulse'])['resources'][0]
    assert offline['access'] == 'granted' and offline['readiness'] == 'unavailable'
    assert offline['selected_resource_id'] == command['selected_resource_id']
    assert 'device_offline' in offline['reasons']


def test_subset_and_revoked_grants_never_reveal_an_unapproved_resource(vertical):
    s = vertical
    allow(s, preview(s), scopes=['connector:business_api'])
    row = s.sdk.discover_resources(['command:pulse'])['resources'][0]
    assert row['access'] == 'required' and row['configured'] is None and row['provider'] is None
    status = s.manager.inspect(1)
    s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=status['grant_record_revision'])
    assert s.sdk.discover_resources(['connector:business_api'])['resources'][0]['provider'] is None
    with s.engine.begin() as db: db.execute(update(Installation).values(enabled=False, status='disabled'))
    with pytest.raises(ApplicationPlatformError): s.sdk.discover_resources(['command:pulse'])


@pytest.fixture
def resource_ui(ui_app):
    s = ui_app; adopt(s)
    app = FastAPI(); app.include_router(router)
    def database():
        with Session(s.engine) as db: yield db
    app.dependency_overrides[get_db] = database
    s.resource_body = {'artifact_sha256':s.validated.sha256, 'built_ui_sha256':s.build.built_ui_sha256, 'scopes':['command:pulse']}
    s.resource_url = f'/api/v1/application-extensions/{s.validated.manifest.module_id}/ui-host/operations/resources/inspect'
    with TestClient(app) as client:
        s.client = client
        yield s


@pytest.mark.parametrize('ui_app', ['administration_resources'], indirect=True)
def test_browser_reads_same_own_resource_without_a_service_token(resource_ui):
    s = resource_ui
    result = s.client.post(s.resource_url, headers={'Authorization':'Bearer '+s.token}, json=s.resource_body)
    assert result.status_code == 200, result.text
    assert result.headers['cache-control'] == 'no-store'
    assert result.json()['artifact_sha256'] == s.validated.sha256
    assert result.json()['resources'][0]['scope'] == 'command:pulse'
    assert result.json()['resources'][0]['access'] == 'granted'
    assert not any(name in result.text for name in ('socket_path','configuration','secret_ref','PRIVATE_MUST_NOT_APPEAR'))


@pytest.mark.parametrize('ui_app', ['administration_resources'], indirect=True)
@pytest.mark.parametrize('fault', ['anonymous','nonadmin','session','artifact','build','duplicate','path'])
def test_browser_denials_precede_resource_probes(resource_ui, monkeypatch, fault):
    s = resource_ui; body = dict(s.resource_body); token = s.token
    if fault == 'nonadmin': token = s.user_token
    if fault == 'session':
        with s.engine.begin() as db: db.execute(update(UserSession).where(UserSession.user_id==1).values(is_active=False))
    if fault == 'artifact': body['artifact_sha256'] = 'f'*64
    if fault == 'build': body['built_ui_sha256'] = 'f'*64
    if fault == 'duplicate': body['scopes'] = ['command:pulse']*2
    if fault == 'path': body['scopes'] = ['../../other']
    def forbidden(*args, **kwargs): pytest.fail('Denied read reached provider observation')
    monkeypatch.setattr(discovery, 'discover_resources', forbidden)
    headers = {} if fault == 'anonymous' else {'Authorization':'Bearer '+token}
    assert s.client.post(s.resource_url, headers=headers, json=body).status_code in {401,403,404,409,422}


@pytest.mark.parametrize('ui_app', ['administration_resources'], indirect=True)
def test_human_revocation_after_observation_discards_the_response(resource_ui, monkeypatch):
    s = resource_ui; original = discovery.discover_resources
    def revoke(*args, **kwargs):
        value = original(*args, **kwargs)
        with s.engine.begin() as db: db.execute(update(UserSession).where(UserSession.user_id==1).values(is_active=False))
        return value
    monkeypatch.setattr(discovery, 'discover_resources', revoke)
    result = s.client.post(s.resource_url, headers={'Authorization':'Bearer '+s.token}, json=s.resource_body)
    assert result.status_code in {401,403}


@pytest.mark.parametrize('ui_app', ['administration_resources'], indirect=True)
def test_service_authority_change_during_browser_probe_returns_no_partial_metadata(resource_ui, monkeypatch):
    def changed(*args, **kwargs): raise AuthorityManagementError('grant_not_current')
    monkeypatch.setattr(discovery, 'discover_resources', changed)
    s = resource_ui
    result = s.client.post(s.resource_url, headers={'Authorization':'Bearer '+s.token}, json=s.resource_body)
    assert result.status_code == 409
    assert 'provider' not in result.text and 'grant_not_current' not in result.text


@pytest.mark.parametrize('ui_app', ['administration'], indirect=True)
def test_existing_admin_read_declarations_do_not_imply_resource_inspection(resource_ui):
    s = resource_ui
    assert s.client.post(s.resource_url, headers={'Authorization':'Bearer '+s.token}, json=s.resource_body).status_code == 403
