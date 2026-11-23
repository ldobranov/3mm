"""Classify independent device failures from the ordinary admin export alone."""
import json
import sqlite3
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.accounts import tokens
from backend.devices.platform import api as platform
from backend.devices.telemetry import ingest_api
from backend.installation.identity import InstallationIdentityError
from backend.main import CustomErrorHandlerMiddleware
from backend.storage.sessions import get_db
from backend.system.diagnostics import api, failures
from backend.tests.test_device_pairing_routes import make_client
from backend.tests.test_device_platform import paired
from packages.protocol.device_platform import challenge
from tools.diagnostics import explain


def test_uninstrumented_route_retains_only_a_real_driver_code_not_a_guess():
    app, ring = FastAPI(), failures.RecentHttpFailures()
    app.add_middleware(CustomErrorHandlerMiddleware)
    app.add_middleware(failures.HttpFailureMiddleware, store=ring)
    @app.get('/read/{kind}')
    def read(kind: str):
        if kind == 'db':
            cause = sqlite3.OperationalError('PRIVATE_MARKER')
            cause.sqlite_errorcode = sqlite3.SQLITE_READONLY
            raise OperationalError('PRIVATE_MARKER', (), cause)
        raise RuntimeError('database is locked PRIVATE_MARKER')
    with TestClient(app) as client:
        for kind, cause in [('db', ('core.database', 'database_read_only')), ('other', ('http.response', 'server_error'))]:
            response = client.get('/read/' + kind)
            assert response.status_code == 500 and 'PRIVATE_MARKER' not in response.text
            row = ring.snapshot()['records'][0]
            assert (row['stage'], row['reason']) == cause
            assert 'PRIVATE_MARKER' not in json.dumps(row)


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(tokens, 'SECRET_KEY', 'isolated-diagnostic-test-key-at-least-32-bytes')
    monkeypatch.setenv('AI_SETTINGS_MASTER_KEY', Fernet.generate_key().decode())
    path = tmp_path/'lab.db'
    engine = create_engine('sqlite:///' + path.as_posix(), connect_args={'timeout': .08})
    client, setup, admin, viewer = make_client(engine)
    admin = {'Authorization': 'Bearer ' + admin}
    ring = failures.RecentHttpFailures()
    monkeypatch.setattr(api, 'recent_http_failures', ring)
    # No real device probes: these tests exercise Core request and export paths.
    monkeypatch.setattr(api, 'observe', lambda *_: {'probe_status': 'complete', 'components': []})
    for router in (platform.router, ingest_api.router, api.router):
        client.app.include_router(router)
    client.app.add_middleware(CustomErrorHandlerMiddleware)
    client.app.add_middleware(failures.HttpFailureMiddleware, store=ring)
    credential, _, _ = paired((client, setup, admin, None))
    setup.close()

    def session():
        with Session(engine) as db:
            yield db
    client.app.dependency_overrides[get_db] = session
    try:
        yield client, credential, admin, path, viewer
    finally:
        client.close()
        engine.dispose()


@pytest.mark.parametrize('route', ['heartbeat', 'authority-exchange'])
def test_json_distinguishes_real_writer_lock_from_rejected_device_credential(lab, route):
    client, credential, admin, path, viewer = lab
    url = '/api/v1/devices/' + credential.device_id + '/' + route
    payload = ({'device_id': credential.device_id, 'sent_at': datetime.now(UTC).isoformat(), 'uptime_seconds': 20}
               if route == 'heartbeat' else challenge(credential.device_id, credential.credential_id, 'command').model_dump(mode='json'))
    headers = {'Authorization': f'Device {credential.credential_id}:{credential.credential_secret}'}
    lock = sqlite3.connect(path)
    try:
        # A reserved writer still allows authentication reads; an exclusive
        # lock is necessary to make a truly read-only check fail.
        lock.execute('BEGIN IMMEDIATE' if route == 'heartbeat' else 'BEGIN EXCLUSIVE')
        busy = client.post(url, json=payload, headers=headers)
    finally:
        lock.close()
    denied = client.post(url, json=payload, headers={'Authorization': 'Device unknown:PRIVATE_MARKER'})
    assert busy.status_code == 500 and denied.status_code == 401
    assert busy.json() == {'error': 'Internal Server Error'}
    assert client.post(url, json=payload, headers=headers).is_success
    assert client.get('/api/v1/diagnostics/cases', headers={'Authorization': 'Bearer ' + viewer}).status_code == 403
    location = (('device.heartbeat_write', 'database_busy', 'device.identity_match') if route == 'heartbeat'
                else ('device.credential', 'database_busy', 'device.credential_header'))
    for response, expected in [(busy, location),
                               (denied, ('device.credential', 'device_credential_refused', 'device.credential_header'))]:
        case = _export(client, admin, response, credential)
        assert (case['stage'], case['reason'], case['last_passed_stage']) == expected
        assert 0 <= case['failed_step_ms'] <= case['duration_ms']


def _export(client, admin, response, credential):
    trace = response.headers['x-3mm-trace-id']
    snapshot = client.get('/api/v1/diagnostics/cases', headers=admin, params={'trace_id': trace})
    assert snapshot.is_success
    assert not any(secret in snapshot.text for secret in (credential.credential_secret, 'PRIVATE_MARKER', 'UPDATE device'))
    case, = explain(json.loads(snapshot.content))['cases']
    assert case['timing_trace_id'] == trace and not case['automatic_replay_allowed']
    return case


@pytest.mark.parametrize(('busy','expected'), [('key_busy','review_key_busy'), ('database_busy','database_busy')])
def test_permit_conflict_records_typed_contention_without_changing_http_or_disclosing_input(lab, monkeypatch, busy, expected):
    from backend.applications.authority.management import AuthorityAdmissionUnavailable
    from backend.applications.commands import broker
    client, credential, admin, _, _ = lab
    def unavailable(*_):
        raise AuthorityAdmissionUnavailable(busy)
    monkeypatch.setattr(broker, 'authorize_execution', unavailable)
    request = challenge(credential.device_id, credential.credential_id, 'execution_permit', command_id='cmd_' + 'a'*32)
    response = client.post('/api/v1/devices/' + credential.device_id + '/authority-exchange',
        headers={'Authorization': f'Device {credential.credential_id}:{credential.credential_secret}'},
        json=request.model_dump(mode='json'))
    assert response.status_code == 409
    case = _export(client, admin, response, credential)
    assert (case['stage'], case['reason'], case['last_passed_stage']) == (
        'device.execution_permit', expected, 'device.identity_match')


def test_signer_unavailable_is_not_reported_as_denial_or_core_boot(lab, monkeypatch):
    client, credential, admin, _, _ = lab
    def unavailable(*_):
        raise InstallationIdentityError('PRIVATE_MARKER')
    monkeypatch.setattr(platform, 'sign_authority', unavailable)
    response = client.post('/api/v1/devices/' + credential.device_id + '/authority-exchange',
        headers={'Authorization': f'Device {credential.credential_id}:{credential.credential_secret}'},
        json=challenge(credential.device_id, credential.credential_id, 'command').model_dump(mode='json'))
    assert response.status_code == 503
    case = _export(client, admin, response, credential)
    assert (case['stage'], case['reason'], case['last_passed_stage']) == (
        'device.authority_sign', 'installation_identity_unavailable', 'device.authority_snapshot')


def test_credential_activity_and_heartbeat_commit_together(lab):
    from contextlib import closing
    client, credential, _, path, _ = lab
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TRIGGER reject_heartbeat BEFORE INSERT ON device_heartbeats "
                   "BEGIN SELECT RAISE(ABORT, 'test only'); END")
        db.commit()
    response = client.post('/api/v1/devices/' + credential.device_id + '/heartbeat',
        json={'device_id': credential.device_id, 'sent_at': datetime.now(UTC).isoformat(), 'uptime_seconds': 1},
        headers={'Authorization': f'Device {credential.credential_id}:{credential.credential_secret}'})
    assert response.status_code == 500
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT count(*) FROM device_heartbeats').fetchone() == (0,)
        assert db.execute('SELECT last_used_at FROM device_credentials WHERE credential_id=?',
                          (credential.credential_id,)).fetchone() == (None,)


def test_heartbeat_cannot_use_an_active_sibling_if_the_presented_key_changed(lab, monkeypatch):
    from contextlib import closing
    from backend.devices import auth
    client, credential, _, path, _ = lab
    authenticate = auth.authenticate_device
    def change_after_verification(session, key, secret):
        device = authenticate(session, key, secret)
        with closing(sqlite3.connect(path)) as writer:
            writer.execute("INSERT INTO device_credentials(device_id,credential_id,secret_hash) "
                           "SELECT device_id,'test-sibling','not-presented' FROM device_credentials WHERE credential_id=?", (key,))
            writer.execute("UPDATE device_credentials SET revoked_at=CURRENT_TIMESTAMP WHERE credential_id=?", (key,))
            writer.commit()
        return device
    monkeypatch.setattr(auth, "authenticate_device", change_after_verification)
    response = client.post('/api/v1/devices/' + credential.device_id + '/heartbeat',
        json={'device_id': credential.device_id, 'sent_at': datetime.now(UTC).isoformat(), 'uptime_seconds': 1},
        headers={'Authorization': f'Device {credential.credential_id}:{credential.credential_secret}'})
    assert response.status_code == 401
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT count(*) FROM device_credentials WHERE revoked_at IS NULL').fetchone() == (1,)
        assert db.execute('SELECT count(*) FROM device_credentials WHERE last_used_at IS NOT NULL').fetchone() == (0,)
        assert db.execute('SELECT count(*) FROM device_heartbeats').fetchone() == (0,)


def test_empty_signed_poll_survives_concurrent_writer_without_weakening_revocation(lab):
    from backend.db.device import DeviceCredential
    from contextlib import closing
    client, credential, admin, path, _ = lab
    engine = create_engine('sqlite:///' + path.as_posix())
    url = '/api/v1/devices/' + credential.device_id + '/authority-exchange'
    def poll(operation='command'):
        return client.post(url, headers=headers, json=challenge(
            credential.device_id, credential.credential_id, operation).model_dump(mode='json'))
    headers = {'Authorization': f'Device {credential.credential_id}:{credential.credential_secret}'}
    try:
        assert poll().status_code == 200  # initialize the signer, but not a credential write
        with closing(sqlite3.connect(path, timeout=.08)) as writer:
            assert writer.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
            writer.execute('BEGIN IMMEDIATE')
            response = poll()
            assert response.status_code == 200 and response.json()['payload']['command'] is None
        with Session(engine) as db:
            row = db.query(DeviceCredential).filter_by(credential_id=credential.credential_id).one()
            assert row.last_used_at is None
            heartbeat = url.removesuffix('/authority-exchange') + '/heartbeat'
            body = {'device_id': credential.device_id, 'sent_at': datetime.now(UTC).isoformat(), 'uptime_seconds': 20}
            assert client.post(heartbeat, json=body, headers=headers).status_code == 202
            db.refresh(row)
            assert row.last_used_at is not None
            old = datetime(2020, 1, 1)
            row.last_used_at = old
            db.commit()
            with closing(sqlite3.connect(path)) as writer:
                writer.execute('BEGIN IMMEDIATE')
                assert poll().status_code == 200
            db.refresh(row)
            assert row.last_used_at == old  # Even an old stamp cannot make the poll a writer.
            row.revoked_at = datetime.now(UTC)
            db.commit()
        assert poll().status_code == 401
    finally:
        engine.dispose()
