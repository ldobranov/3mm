"""Real sealed authority, real logins and existing brokers; no live device I/O."""

from datetime import UTC, datetime, timedelta
import io
import json
import os
import uuid
import zipfile
import threading

import pytest
import requests
from cryptography.fernet import Fernet
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.base import Base
from backend.db.application_authority_grant import ApplicationAuthorityAction as Action, ApplicationAuthorityGrant as Grant, ApplicationNativeReview as Native
from backend.db.authority import CoreAuthorityGuard
from backend.db.device import Device, DeviceCapabilityProvider, DeviceCommand, DeviceHeartbeat, DeviceCapabilityHealth
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage, ApplicationSecretReference
from backend.db.session import UserSession
from backend.db.user import User
from backend.services import application_authority_management as service
from backend.services.application_commands import submit_command, authorize_execution, command_lookup
from backend.services.application_connectors import execute_connector_request, ApplicationConnectorError
from backend.services.device_commands import deliver_next_command
from backend.services.device_capability_registry import capability_catalog
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_authority_subjects import installed as source_subject, source_installed
from backend.tests.test_application_authority_sources import PRIVATE
from backend.utils.jwt_utils import create_access_token


pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Requires real POSIX Core key ownership/locking')


def identity():
    return uuid.uuid4().hex


@pytest.fixture
def installed(source_subject, monkeypatch):
    s = source_subject
    secret_key = Fernet.generate_key()
    cipher = Fernet(secret_key)
    monkeypatch.setenv('AI_SETTINGS_MASTER_KEY', secret_key.decode('ascii'))
    manifest = s.validated.manifest.model_dump(mode='json')
    manifest.update(runtimes=['core'], entrypoints={'core': 'application-extension.json'})
    manifest['capabilities'] = {'provides': [], 'consumes': ['gpio.digital.control']}
    manifest['permissions'] = [value for value in manifest['permissions'] if not value.startswith('events.')]
    definition = s.validated.application_extension.model_dump(mode='json')
    definition.update(routes=[], event_subscriptions=[], jobs=[], permissions=[])
    definition['operations'] = [definition['operations'][0]]
    output = io.BytesIO()
    with zipfile.ZipFile(s.archive) as previous, zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('application-extension.json', json.dumps(definition))
        archive.writestr(definition['service']['artifact'], previous.read(definition['service']['artifact']))
    s.validated = validate_module_package(output.getvalue())
    s.archive = s.root / 'modules' / (s.validated.sha256 + '.zip')
    s.archive.write_bytes(output.getvalue())
    Base.metadata.create_all(s.engine, tables=[Base.metadata.tables[name] for name in (
        'users', 'sessions', 'audit_logs', 'application_native_reviews', 'application_authority_plans',
        'application_authority_grants', 'application_authority_actions', 'application_command_epochs',
        'application_command_requests', 'device_commands', 'application_connector_attempts',
        'device_capability_health', 'device_heartbeats', 'device_inventory_snapshots', 'application_sync_checkpoints')])
    s.token = create_access_token('1', {'sid': 1, 'token_version': 0})
    s.user_token = create_access_token('2', {'sid': 2, 'token_version': 0, 'role': 'admin'})
    with Session(s.engine) as db, db.begin():
        db.execute(update(ModulePackage).values(sha256=s.validated.sha256, size_bytes=len(output.getvalue()),
            manifest=manifest, file_path=str(s.archive)))
        db.add_all([User(id=1, username='admin', role='admin'), User(id=2, username='user', role='user')])
        db.flush()
        for uid, token in ((1, s.token), (2, s.user_token)):
            db.add(UserSession(id=uid, user_id=uid, token=token, is_active=True,
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)))
        db.execute(update(ApplicationSecretReference).values(encrypted_value=cipher.encrypt(json.dumps(
            {'username': 'example', 'password': PRIVATE}).encode()).decode()))
        db.add(DeviceHeartbeat(device_id=1, protocol_version='1.0', payload={}, received_at=datetime.now(UTC)))
        db.flush()
        declaration = capability_catalog(db, db.get(Device, 1))[0]
        db.add(DeviceCapabilityHealth(device_id=1, provider_type=declaration.provider_type,
            provider_id=declaration.provider_id, observed_at=datetime.now(UTC), report={
                'declaration_digest': declaration.declaration_digest,
                'capabilities': [{'capability_id': 'gpio.digital.control', 'healthy': True}]},
            expires_at=datetime.now(UTC) + timedelta(minutes=5)))
    s.manager = service.ApplicationAuthorityManager(s.engine, uploads_root=s.root,
        core_version='0.3.0', review_key_directory=s.key_directory)
    s.keys.provision()
    monkeypatch.setattr(service, 'configured_manager', lambda engine: s.manager if engine is s.engine else None)
    return s


def native(s):
    return s.manager.record_native_review(1, actor_token=s.token, request_id=identity(),
        artifact_sha256=s.validated.sha256, review_document_sha256='b' * 64,
        native_code_review_completed=True, accepts_native_host_risk=True)


def review(s, n=None, **overrides):
    n = n or native(s)
    return s.manager.create_review(1, actor_token=s.token, request_id=identity(),
        native_review_id=n['native_review_id'], scopes=['command:pulse', 'connector:business_api'], **overrides)


def decide(s, plan, action, request_id=None):
    return s.manager.decide(1, actor_token=s.token, request_id=request_id or identity(),
        plan_id=plan['plan_id'], expected_revision=plan['revision'], fingerprint=plan['fingerprint'], decision=action)


def activate_grant(s):
    # Production first adoption is disabled-only. Existing lifecycle separately
    # confirms stop/start and invalidates the epoch; this fixture models a stopped
    # app, then a fresh review after same-artifact re-enable (not a new artifact).
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status='disabled'))
    n = native(s)
    decide(s, decide(s, review(s, n), 'approve'), 'apply')
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=True, status='active', authority_epoch=identity()))
    return decide(s, decide(s, review(s, n), 'approve'), 'apply')


def command(request_id='one'):
    return {'binding_id': 'pulse', 'request_id': request_id, 'arguments': {'channel': 'output.1', 'duration_ms': 50},
        'ttl_seconds': 5}


def connector(s, request_id=None, transport=None, path='/api/check'):
    with Session(s.engine) as db:
        return execute_connector_request(db, db.get(Installation, 1), connector_id='business_api',
            request_id=request_id or 'connector_' + identity(), method='POST', path=path,
            headers={}, body=b'{}', idempotency_key='test-1', transport=transport)


def test_native_proof_and_permission_approval_are_separate_and_sealed(installed):
    s = installed
    with pytest.raises(service.AuthorityManagementError):
        review(s, {'native_review_id': identity()})
    n = native(s)
    plan = review(s, n)
    approved = decide(s, plan, 'approve')
    status = s.manager.inspect(1)
    assert not status['grant_effective'] and status['grant_state'] is None
    with pytest.raises(service.AuthorityManagementError, match='disabled_adoption_required'):
        decide(s, approved, 'apply')
    with s.engine.begin() as db:
        db.execute(update(Native).values(payload='{}'))
    with pytest.raises(service.AuthorityManagementError):
        review(s, n)


def test_apply_command_permit_connector_revoke_and_historical_lookup(installed):
    s = installed
    activate_grant(s)
    status = s.manager.inspect(1)
    assert status['grant_effective'] and status['mode'] == 'enforced'
    with Session(s.engine) as db:
        app, device = db.get(Installation, 1), db.get(Device, 1)
        queued = submit_command(db, app, command())
        delivered = deliver_next_command(db, device=device)
        assert authorize_execution(db, device, delivered.command_id)['authorized']
        with pytest.raises(ValueError):
            authorize_execution(db, device, delivered.command_id)
    effects = []
    def transport(*args, **kwargs):
        effects.append(args)
        # A key rotation would fail if the key lease still spanned HTTP I/O.
        with s.keys.locked():
            pass
        return type('Response', (), {'status_code': 200, 'content': b'{}', 'headers': {}})()
    request_id = 'connector_' + identity()
    assert connector(s, request_id, transport)['outcome'] == 'succeeded'
    assert connector(s, request_id, transport)['duplicate']
    revoked = s.manager.revoke(1, actor_token=s.token, request_id=identity(),
        expected_revision=status['grant_record_revision'])
    assert revoked['state'] == 'revoked' and not s.manager.inspect(1)['grant_effective']
    with pytest.raises(ApplicationConnectorError):
        connector(s, transport=transport)
    assert connector(s, request_id, transport)['duplicate'] and len(effects) == 1
    with Session(s.engine) as db:
        app = db.get(Installation, 1)
        with pytest.raises(ValueError):
            submit_command(db, app, command('two'))
        assert command_lookup(db, app, {'binding_id': 'pulse', 'request_id': 'one'})['status'] == 'found'
        assert len(db.scalars(select(DeviceCommand)).all()) == 1


@pytest.mark.parametrize('change', ['configuration', 'provider', 'credential', 'key', 'recovery', 'native'])
def test_active_grant_never_survives_actual_resource_or_trust_drift(installed, change):
    s = installed
    activate_grant(s)
    if change == 'key':
        s.keys.rotate(expected_key_id=s.keys.identity().key_id)
    elif change == 'native':
        with s.engine.begin() as db:
            db.execute(update(Native).values(payload='{}'))
    else:
        with s.engine.begin() as db:
            if change == 'configuration':
                db.execute(update(Installation).values(configuration={**s.configuration, 'PRIVATE_NOTE': 'changed'}))
            elif change == 'provider':
                db.execute(update(DeviceCapabilityProvider).values(revision=9))
            elif change == 'credential':
                db.execute(update(ApplicationSecretReference).values(version=10))
            else:
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
    with Session(s.engine) as db:
        with pytest.raises(ValueError):
            submit_command(db, db.get(Installation, 1), command())
        assert not db.scalars(select(DeviceCommand)).all()


@pytest.mark.parametrize('fault', ['config', 'expire', 'reboot', 'session', 'role', 'foreign_actor'])
def test_review_cannot_approve_after_drift_or_lost_actor_authority(installed, monkeypatch, fault):
    s = installed
    plan = review(s)
    if fault in {'expire', 'reboot'}:
        boot, now = service._clock()
        monkeypatch.setattr(service, '_clock', lambda: (identity() if fault == 'reboot' else boot, now + 900_001))
    else:
        with s.engine.begin() as db:
            if fault == 'config':
                db.execute(update(Installation).values(configuration={**s.configuration, 'PRIVATE_NOTE': 'changed'}))
            elif fault == 'session':
                db.execute(update(UserSession).where(UserSession.id == 1).values(is_active=False))
            elif fault == 'role':
                db.execute(update(User).where(User.id == 1).values(role='user'))
            else:
                s.token = s.user_token
    with pytest.raises(service.AuthorityManagementError):
        decide(s, plan, 'approve')
    with Session(s.engine) as db:
        assert not db.scalars(select(Grant)).all()


def test_idempotent_decision_is_historical_and_cannot_apply_twice(installed):
    s = installed
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status='disabled'))
    p = decide(s, review(s), 'approve')
    request_id = identity()
    applied = decide(s, p, 'apply', request_id)
    replayed = decide(s, p, 'apply', request_id)
    assert replayed == {**applied, 'replayed': True, 'historical': True}
    with pytest.raises(service.AuthorityManagementError):
        decide(s, p, 'apply')
    with Session(s.engine) as db:
        assert db.get(Grant, 1).revision == 1
        assert PRIVATE not in ''.join(row.payload for row in db.scalars(select(Action)))


@pytest.mark.parametrize('path', ['/api/../other', '/api/%2e%2e/other', '/api/\\other', '/api//other'])
def test_enforced_connector_rejects_ambiguous_paths_before_transport(installed, path):
    s = installed
    activate_grant(s)
    def forbidden(*args, **kwargs):
        pytest.fail('unsafe request was dispatched')
    with pytest.raises(ApplicationConnectorError):
        connector(s, path=path, transport=forbidden)


def test_lost_post_response_and_revocation_during_transport_never_replay(installed):
    s = installed
    activate_grant(s)
    status = s.manager.inspect(1)
    effects = []
    def transport(*args, **kwargs):
        effects.append(1)
        s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=status['grant_record_revision'])
        raise requests.ReadTimeout()
    request_id = 'connector_' + identity()
    assert connector(s, request_id, transport)['outcome'] == 'ambiguous'
    assert connector(s, request_id, transport)['duplicate'] and effects == [1]


def test_native_revocation_invalidates_active_permissions(installed):
    s = installed
    activate_grant(s)
    with Session(s.engine) as db:
        grant = json.loads(db.get(Grant, 1).payload)
        n = db.get(Native, grant['data']['native_review_id'])
        value = json.loads(n.payload)
    s.manager.revoke_native_review(1, actor_token=s.token, request_id=identity(),
        native_review_id=n.review_id, expected_revision=value['revision'])
    with Session(s.engine) as db:
        with pytest.raises(ValueError):
            submit_command(db, db.get(Installation, 1), command())


def test_administrator_api_real_sessions_review_apply_and_revoke(installed):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routes.application_authority import router
    from backend.utils.db_utils import get_db
    s = installed
    app = FastAPI()
    app.include_router(router)
    def database():
        with Session(s.engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    base = '/api/v1/application-extensions/' + s.validated.manifest.module_id + '/authority'
    with TestClient(app) as client:
        assert client.get(base).status_code == 401
        assert client.get(base, headers={'Authorization': 'Bearer ' + s.user_token}).status_code == 403
        headers = {'Authorization': 'Bearer ' + s.token}
        with s.engine.begin() as db:
            db.execute(update(Installation).values(enabled=False, status='disabled'))
        n = native(s)
        payload = {'request_id': identity(), 'native_review_id': n['native_review_id'],
            'scopes': ['command:pulse', 'connector:business_api']}
        assert client.post(base + '/reviews', json={**payload, 'isolation_proven': True}, headers=headers).status_code == 422
        sessionless = create_access_token('1', {'token_version': 0})
        assert client.post(base + '/reviews', json=payload, headers={'Authorization': 'Bearer ' + sessionless}).status_code == 403
        response = client.post(base + '/reviews', json=payload, headers=headers)
        assert response.status_code == 200, response.text
        plan = response.json()
        assert plan['resources']['commands'][0]['target_device_id'].startswith('dev_')
        assert PRIVATE not in response.text and plan['isolation_proven'] is False
        for action in ('approve', 'apply'):
            response = client.post(base + '/reviews/' + plan['plan_id'] + '/' + action, headers=headers,
                json={'request_id': identity(), 'expected_revision': plan['revision'], 'fingerprint': plan['fingerprint']})
            assert response.status_code == 200, response.text
            plan = response.json()
        status = client.get(base, headers=headers).json()
        assert status['mode'] == 'enforced' and status['grant_state'] == 'active' and not status['grant_effective']
        response = client.post(base + '/revoke', headers=headers,
            json={'request_id': identity(), 'expected_revision': status['grant_record_revision']})
        assert response.status_code == 200 and response.json()['state'] == 'revoked'
        assert not any('native-review' in path for path in app.openapi()['paths'])


def test_concurrent_apply_is_one_durable_grant(installed):
    s = installed
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status='disabled'))
    plan = decide(s, review(s), 'approve')
    barrier = threading.Barrier(2)
    successes, failures = [], []
    def apply():
        try:
            barrier.wait(5)
            successes.append(decide(s, plan, 'apply'))
        except service.AuthorityManagementError as exc:
            failures.append(exc)
    threads = [threading.Thread(target=apply) for _ in range(2)]
    for thread in threads: thread.start()
    for thread in threads:
        thread.join(10)
        assert not thread.is_alive()
    assert len(successes) == 1 and len(failures) == 1
    with Session(s.engine) as db:
        assert db.get(Grant, 1).revision == 1


def test_no_new_artifact_or_configuration_can_reuse_native_activation(installed):
    from backend.services.authority_metadata import read_authority_guard
    s = installed
    activate_grant(s)
    with Session(s.engine) as db:
        guard = read_authority_guard(db)
    with s.manager.native_activation(1, s.validated.sha256, s.configuration, guard):
        pass
    for artifact, configuration in (('f' * 64, s.configuration),
            (s.validated.sha256, {**s.configuration, 'PRIVATE_NOTE': 'changed'})):
        with pytest.raises(service.AuthorityManagementError):
            with s.manager.native_activation(1, artifact, configuration, guard):
                pytest.fail('changed artifact/configuration was admitted')


def test_unsupported_signed_platform_actions_never_fall_back_to_legacy(installed, tmp_path):
    from backend.services.application_platform import ApplicationPlatformServer
    s = installed
    activate_grant(s)
    server = ApplicationPlatformServer(tmp_path / 'unused.sock', tmp_path)
    with Session(s.engine) as db:
        for action in ('checkpoint.put', 'installation.identity.get', 'installation.peers.enroll'):
            with pytest.raises(ValueError, match='no supported resource grant'):
                server._dispatch(db, db.get(Installation, 1), {'action': action})


def test_revoke_committed_between_preflight_and_admission_wins(installed, monkeypatch):
    s = installed
    activate_grant(s)
    status = s.manager.inspect(1)
    original = s.manager._prepare
    def interleave(installation_id):
        prepared = original(installation_id)
        s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=status['grant_record_revision'])
        return prepared
    monkeypatch.setattr(s.manager, '_prepare', interleave)
    with Session(s.engine) as db:
        with pytest.raises(ValueError):
            submit_command(db, db.get(Installation, 1), command())
        assert not db.scalars(select(DeviceCommand)).all()


def test_current_core_policy_adapter_revision_invalidates_old_grants(installed, monkeypatch):
    from backend.services import application_authority_policy as policy
    s = installed
    activate_grant(s)
    monkeypatch.setattr(policy, 'POLICY_ADAPTER_REVISION', policy.POLICY_ADAPTER_REVISION + 1)
    with Session(s.engine) as db:
        with pytest.raises(ValueError):
            submit_command(db, db.get(Installation, 1), command())


def test_real_offline_restore_fences_old_grants_but_allows_fresh_local_review(installed):
    from pathlib import Path
    from deployment.authority_recovery import fence_recovered_authority
    s = installed
    activate_grant(s)
    old_key = s.keys.identity().key_id
    fence_recovered_authority(Path(s.engine.url.database), reason='backup_restore')
    with Session(s.engine) as db:
        assert db.get(Installation, 1).authority_mode == 'enforced'
        with pytest.raises(ValueError):
            submit_command(db, db.get(Installation, 1), command())
    s.keys.recover(expected_key_id=old_key)
    decide(s, decide(s, review(s), 'approve'), 'apply')
    with Session(s.engine) as db:
        assert submit_command(db, db.get(Installation, 1), command())['status'] == 'queued'


def test_actual_lifecycle_gate_reenables_same_artifact_without_resurrecting_grant(installed, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routes.application_extensions import router
    from backend.utils.db_utils import get_db
    from three_mm_runtime.update_helper_client import UpdateHelperClient
    s = installed
    activate_grant(s)
    app = FastAPI()
    app.include_router(router)
    def database():
        with Session(s.engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    calls = []
    def helper(operation):
        def invoke(*args, **kwargs):
            with s.keys.locked():  # Key lease must be released before helper I/O.
                pass
            with Session(s.engine) as db:
                current = db.get(Installation, 1)
                assert current.status == operation and not current.enabled
            calls.append(operation)
            return {'module_id': s.validated.manifest.module_id, 'version': '1.0.0',
                'sha256': s.validated.sha256, 'instance_id': 'a' * 24, 'socket_path': 'service.sock'}
        return invoke
    monkeypatch.setattr(UpdateHelperClient, 'disable_application_extension', helper('disabling'))
    monkeypatch.setattr(UpdateHelperClient, 'activate_application_extension', helper('activating'))
    base = '/api/v1/application-extensions'
    headers = {'Authorization': 'Bearer ' + s.token}
    with TestClient(app) as client:
        response = client.post(base + '/' + s.validated.manifest.module_id + '/disable', headers=headers)
        assert response.status_code == 200, response.text
        response = client.post(base + '/packages/' + s.validated.sha256 + '/activate', json={'configuration': {}}, headers=headers)
        assert response.status_code == 200, response.text
    assert calls == ['disabling', 'activating']
    assert not s.manager.inspect(1)['grant_effective']
    decide(s, decide(s, review(s), 'approve'), 'apply')
    assert s.manager.inspect(1)['grant_effective']


@pytest.mark.parametrize('failure', [OSError, KeyError, TypeError, AttributeError])
def test_administrator_status_redacts_storage_and_corrupt_record_errors(installed, monkeypatch, failure):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routes.application_authority import router
    from backend.utils.db_utils import get_db
    s = installed
    app = FastAPI()
    app.include_router(router)
    def database():
        with Session(s.engine) as db:
            yield db
    def broken_status(installation_id):
        raise failure(PRIVATE)
    monkeypatch.setattr(s.manager, 'inspect', broken_status)
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        response = client.get('/api/v1/application-extensions/' + s.validated.manifest.module_id + '/authority',
            headers={'Authorization': 'Bearer ' + s.token})
    assert response.status_code == 409
    assert response.json() == {'detail': {'code': 'authority_unavailable'}}
    assert PRIVATE not in response.text


@pytest.mark.parametrize('administrator', [True, False])
def test_local_key_cli_checks_actual_login_and_never_grants_permissions(installed, monkeypatch, capsys, administrator):
    import sys
    from backend import database
    from backend.db.audit_log import AuditLog
    from backend.services import application_authority_admin as admin
    s = installed
    before = s.keys.identity()
    monkeypatch.setattr(database, 'engine', s.engine)
    monkeypatch.setattr(admin.getpass, 'getpass', lambda prompt: s.token if administrator else s.user_token)
    monkeypatch.setattr(sys, 'argv', ['application_authority_admin', 'provision-key'])
    if administrator:
        admin.main()
        output = capsys.readouterr().out
        assert json.loads(output) == {'key_id': before.key_id, 'permission_approval': 'not_evaluated'}
        assert PRIVATE not in output and s.token not in output
    else:
        with pytest.raises(SystemExit, match='no permission fallback'):
            admin.main()
    assert s.keys.identity() == before
    with Session(s.engine) as db:
        assert not db.scalars(select(Grant)).all()
        assert len(db.scalars(select(AuditLog).where(AuditLog.action == 'APPLICATION_AUTHORITY_KEY')).all()) == int(administrator)
