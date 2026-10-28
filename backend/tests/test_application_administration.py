"""Current admin -> reviewed route -> real registry; no service grant/token relay."""
import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.session import UserSession
from backend.db.user import User
from backend.routes.application_extensions import router
from backend.services import device_registry_read
from backend.tests.test_application_ui_authority import ui_app, adopt
from backend.tests.test_application_authority_management import installed as managed_installed
from backend.tests.test_application_authority_subjects import installed as source_subject, source_installed
from backend.utils.db_utils import get_db


@pytest.fixture
def administration(ui_app):
    s = ui_app
    s.native_proof = adopt(s)
    app = FastAPI()
    app.include_router(router)
    def session():
        with Session(s.engine) as db:
            yield db
    app.dependency_overrides[get_db] = session
    s.params = {"artifact_sha256": s.validated.sha256, "built_ui_sha256": s.build.built_ui_sha256}
    s.base = f"/api/v1/application-extensions/{s.validated.manifest.module_id}/ui-host/operations/devices"
    s.auth = {"Authorization": "Bearer " + s.token}
    with TestClient(app) as client:
        s.client = client
        yield s


pytestmark = [pytest.mark.skipif(os.name != 'posix', reason='Real protected review keys'),
              pytest.mark.parametrize('ui_app', ['administration'], indirect=True)]


def test_actual_registry_projection_paging_and_read_only_snapshot(administration, monkeypatch):
    s = administration
    original = device_registry_read.read_devices
    def checked(db, *args, **kwargs):
        assert db.connection().exec_driver_sql('PRAGMA query_only').scalar_one() == 1
        assert db.get(User, 1).role == 'admin'
        return original(db, *args, **kwargs)
    monkeypatch.setattr(device_registry_read, 'read_devices', checked)
    response = s.client.get(s.base, params={**s.params, 'limit': 1}, headers=s.auth)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    listing = response.json()
    assert len(listing['items']) == 1 and listing['total'] >= 1
    item = listing['items'][0]
    detail = s.client.get(s.base + '/' + item['device_id'], params=s.params, headers=s.auth)
    assert detail.status_code == 200, detail.text
    assert detail.json() == {**item, 'modules': []}
    assert s.client.get(s.base, params={**s.params, 'offset': listing['total']}, headers=s.auth).json()['items'] == []
    assert not {'token', 'credentials', 'socket_path', 'configuration'} & item.keys()
    assert s.client.post(s.base, params=s.params, headers=s.auth, json={}).status_code == 405


@pytest.mark.parametrize('fault', ['anonymous', 'ordinary_user', 'role', 'session', 'blocked', 'disabled',
    'source', 'build', 'tampered_build', 'undeclared', 'foreign_app', 'compatibility', 'expired_session', 'token_version', 'native_revoked'])
def test_no_cached_preflight_or_cross_route_authority(administration, fault):
    s = administration
    assert s.client.get(s.base, params=s.params, headers=s.auth).status_code == 200
    params, auth, base = dict(s.params), dict(s.auth), s.base
    with s.engine.begin() as db:
        if fault == 'role': db.execute(update(User).where(User.id == 1).values(role='user'))
        if fault == 'blocked': db.execute(update(User).where(User.id == 1).values(is_blocked=True))
        if fault == 'expired_session': db.execute(update(UserSession).where(UserSession.id == 1).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        if fault == 'token_version': db.execute(update(User).where(User.id == 1).values(token_version=1))
        if fault == 'session': db.execute(update(UserSession).where(UserSession.id == 1).values(is_active=False))
        if fault == 'disabled': db.execute(update(Installation).values(enabled=False, status='disabled'))
        if fault == 'compatibility': db.execute(update(Installation).values(authority_mode='compatibility'))
    if fault == 'native_revoked':
        s.manager.revoke_native_review(1, actor_token=s.token, request_id='c' * 32,
            native_review_id=s.native_proof['native_review_id'], expected_revision=s.native_proof['native_revision'])
    if fault == 'anonymous': auth = {}
    if fault == 'ordinary_user': auth = {'Authorization': 'Bearer ' + s.user_token}
    if fault == 'source': params['artifact_sha256'] = 'f' * 64
    if fault == 'build': params['built_ui_sha256'] = 'f' * 64
    if fault == 'tampered_build': (s.build.path / 'assets/operations.mjs').write_text('changed')
    if fault == 'undeclared': base = base.replace('/operations/', '/registration/')
    if fault == 'foreign_app': base = base.replace(s.validated.manifest.module_id, 'org.example.other')
    response = s.client.get(base, params=params, headers=auth)
    assert response.status_code in {401, 403, 404, 409}, response.text
    assert 'items' not in response.json()


def test_device_identity_and_bounds_are_server_validated(administration):
    s = administration
    for params in ({'limit': 101}, {'limit': 0}, {'offset': -1}, {'offset': 2**63}, {'built_ui_sha256': '../artifact'}):
        assert s.client.get(s.base, params={**s.params, **params}, headers=s.auth).status_code == 422
    assert s.client.get(s.base + '/not-a-device', params=s.params, headers=s.auth).status_code == 422
    assert s.client.get(s.base + '/dev_' + 'f' * 32, params=s.params, headers=s.auth).status_code == 404


def test_actor_is_rechecked_after_native_trust_preparation(administration, monkeypatch):
    s = administration
    original = s.manager.ui_trust_snapshot
    @contextmanager
    def revoked_before_snapshot(*args, **kwargs):
        with s.engine.begin() as db:
            db.execute(update(UserSession).where(UserSession.id == 1).values(is_active=False))
        with original(*args, **kwargs) as db:
            yield db
    monkeypatch.setattr(s.manager, 'ui_trust_snapshot', revoked_before_snapshot)
    assert s.client.get(s.base, params=s.params, headers=s.auth).status_code == 401
