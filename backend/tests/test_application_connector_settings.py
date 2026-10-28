"""Real administrator sessions, POSIX seals and atomic setup; no live services."""
import io
import json
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from backend.db.base import Base
from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationExtensionInstallation as Installation, ApplicationConnectorBinding as Binding, ApplicationSecretReference as Secret, ModulePackage
from backend.db.session import UserSession
from backend.db.user import User
from backend.routes.application_connector_settings import router
from backend.services import application_connector_settings as service
from backend.services import application_authority_management as authority
from backend.services import application_authority_sources as sources
from backend.services.application_consent import preview as consent_preview
from backend.services.application_secrets import decrypt_secret_reference, ApplicationSecretError
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_authority_management import installed as managed, source_subject, source_installed, identity, activate_grant, connector
from backend.utils.jwt_utils import create_access_token
from backend.utils.db_utils import get_db

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Real Core-owned seals and logins')
PASSWORD = 'DO_NOT_DISCLOSE_CONNECTOR_PASSWORD'


def repack(s, authentication='basic', *, relational=False, multiple=False, credential_pattern=None, optional=False):
    manifest = s.validated.manifest.model_dump(mode='json')
    definition = s.validated.application_extension.model_dump(mode='json')
    definition['command_bindings'] = []
    manifest['permissions'] = ['data.read', 'data.write', 'process.spawn', 'network.outbound']
    if authentication != 'none':
        manifest['permissions'].append('secrets.use')
    manifest['capabilities'] = {'provides': [], 'consumes': []}
    connector = definition['connectors'][0]
    connector.update(authentication=authentication, destination_config_key='API_URL',
        credential_ref_config_key='API_CREDENTIAL' if authentication != 'none' else None)
    if multiple:
        definition['connectors'].append({**connector, 'connector_id': 'other_api',
            'destination_config_key': 'OTHER_URL', 'credential_ref_config_key': 'OTHER_CREDENTIAL'})
    if relational:
        from three_mm_protocol.tests.test_application_relational_storage import relational_request
        definition['service']['sdk_version'] = '1.3'
        definition['storage']['relational'] = relational_request()
    if optional:
        definition['service']['sdk_version'] = '1.3'
        definition['optional_resources'] = ['connector:business_api']
    properties = {'API_URL': {'type': 'string'}, 'NOTE': {'type': 'string'}}
    required = ['API_URL']
    if authentication != 'none':
        properties['API_CREDENTIAL'] = {'type': 'string', 'x-3mm-secret-reference': True}
        if credential_pattern:
            properties['API_CREDENTIAL']['pattern'] = credential_pattern
        required.append('API_CREDENTIAL')
    if multiple:
        properties.update(OTHER_URL={'type': 'string'}, OTHER_CREDENTIAL={'type': 'string', 'x-3mm-secret-reference': True})
        required += ['OTHER_URL', 'OTHER_CREDENTIAL']
    manifest.update(configuration_schema={'type': 'object', 'properties': properties,
        'required': required, 'additionalProperties': False}, configuration_defaults={'NOTE': 'preserve me'})
    output = io.BytesIO()
    with zipfile.ZipFile(s.archive) as previous, zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('application-extension.json', json.dumps(definition))
        archive.writestr(definition['service']['artifact'], previous.read(definition['service']['artifact']))
    s.validated = validate_module_package(output.getvalue())
    s.archive = s.root / 'modules' / (s.validated.sha256 + '.zip')
    s.archive.write_bytes(output.getvalue())
    with s.engine.begin() as db:
        db.execute(update(ModulePackage).where(ModulePackage.id == 1).values(sha256=s.validated.sha256,
            manifest=manifest, size_bytes=len(output.getvalue()), file_path=str(s.archive)))


@pytest.fixture
def fresh(managed, monkeypatch):
    s = managed
    Base.metadata.create_all(s.engine)
    with s.engine.begin() as db:
        db.execute(delete(Binding)); db.execute(delete(Secret)); db.execute(delete(Installation))
    repack(s)
    import requests
    monkeypatch.setattr(requests.Session, 'request', lambda *a, **kw: pytest.fail('Unexpected external HTTP'))
    return s


def inspect(s):
    return service.inspect(s.manager, s.validated.sha256, s.token)


def save(s, *, state=None, connector='business_api', **changes):
    request = service.ConnectorSettingsRequest(**{
        'request_id': identity(), 'expected_snapshot': (state or inspect(s))['snapshot'],
        'action': 'save', 'destination_origin': 'http://127.0.0.1:9999',
        'create_credential': True, 'credential_label': 'Test API',
        'credential': {'username': 'operator', 'password': PASSWORD}, **changes})
    return service.configure(s.manager, s.validated.sha256, connector, request, s.token), request


def counts(s):
    with Session(s.engine) as db:
        return tuple(db.scalar(select(func.count()).select_from(model)) for model in (Installation, Secret, Binding))


@pytest.mark.parametrize('authentication', ['basic', 'bearer', 'api_key', 'none'])
def test_first_setup_is_atomic_inert_and_credentials_never_escape(fresh, authentication):
    s = fresh
    repack(s, authentication)
    before = inspect(s)
    assert before['installation_id'] is None and counts(s) == (0, 0, 0)
    assert before['connectors'][0]['state'] == 'unconfigured'
    values = {'basic': {'username': 'operator', 'password': PASSWORD},
        'bearer': {'token': PASSWORD}, 'api_key': {'header': 'X-Test-Key', 'value': PASSWORD}}
    result, request = save(s, state=before, credential=values.get(authentication),
        create_credential=authentication != 'none')
    assert result['status'] == 'applied'
    assert result['state']['state'] == 'configured'
    assert result['state']['authority'] == 'not_granted'
    assert counts(s) == (1, int(authentication != 'none'), 1)
    with Session(s.engine) as db:
        app = db.scalar(select(Installation))
        assert (app.status, app.enabled, app.active_version, app.authority_mode) == ('disabled', False, None, 'review_required')
        assert app.configuration['NOTE'] == 'preserve me'
        assert app.configuration['API_URL'] == result['state']['destination_origin']
        secret = db.scalar(select(Secret))
        if secret:
            assert app.configuration['API_CREDENTIAL'] == secret.secret_ref
            assert PASSWORD in decrypt_secret_reference(secret).values()
        for row in db.scalars(select(Action)):
            assert PASSWORD not in row.payload
        assert PASSWORD not in repr([r.changes for r in db.scalars(select(AuditLog))])
    assert PASSWORD not in json.dumps(inspect(s)) + json.dumps(result)
    # An unconfigured resource no longer prevents real sealed authority preview.
    preview = consent_preview(s.manager, app.id, actor_token=s.token, request_id=identity())
    assert 'connector:business_api' in preview['scopes']


def test_inert_partial_multiple_connectors_and_configuration_provenance(fresh):
    s = fresh
    repack(s, multiple=True)
    result, _ = save(s)
    with pytest.raises(authority.AuthorityManagementError):
        consent_preview(s.manager, 1, actor_token=s.token, request_id=identity())
    save(s, connector='other_api')
    preview = consent_preview(s.manager, 1, actor_token=s.token, request_id=identity())
    assert {'connector:business_api', 'connector:other_api'} <= set(preview['scopes'])
    # A later setup preserves immutable first registration and authenticates the
    # changed configuration through a separate sealed transition.
    save(s, create_credential=False, credential=None, secret_ref=result['state']['credential']['secret_ref'],
        destination_origin='https://other.example')
    consent_preview(s.manager, 1, actor_token=s.token, request_id=identity())
    with Session(s.engine) as db, db.begin():
        app = db.scalar(select(Installation))
        configuration = dict(app.configuration); configuration['NOTE'] = 'forged'
        db.execute(update(Installation).values(configuration=configuration))
    with pytest.raises(authority.AuthorityManagementError):
        consent_preview(s.manager, 1, actor_token=s.token, request_id=identity())


@pytest.mark.parametrize('case', ['key', 'origin', 'wrong_kind', 'invalid_secret', 'bad_schema'])
def test_invalid_setup_rolls_back_without_orphan_credentials(fresh, monkeypatch, case):
    s = fresh
    state = inspect(s)
    changes = {}
    if case == 'key': monkeypatch.delenv('AI_SETTINGS_MASTER_KEY')
    elif case == 'origin': changes['destination_origin'] = 'https://user:password@example.com/private'
    elif case == 'wrong_kind': changes['credential'] = {'token': PASSWORD}
    elif case == 'invalid_secret': changes.update(create_credential=False, credential=None, secret_ref='secret_' + 'f' * 32)
    else:
        repack(s, credential_pattern='^not-a-secret-reference$')
        state = inspect(s)
    with pytest.raises((authority.AuthorityManagementError, RuntimeError, ValueError)):
        save(s, state=state, **changes)
    assert counts(s) == (0, 0, 0)


def test_durable_deduplication_outcome_and_changed_target_conflict(fresh):
    s = fresh
    result, request = save(s)
    assert service.configure(s.manager, s.validated.sha256, 'business_api', request, s.token) == result
    restarted = authority.ApplicationAuthorityManager(s.engine, uploads_root=s.root,
        core_version='0.3.0', review_key_directory=s.key_directory)
    assert service.outcome(restarted, s.validated.sha256, request.request_id, s.token) == result
    assert service.outcome(restarted, s.validated.sha256, identity(), s.token)['status'] == 'unknown'
    assert counts(s) == (1, 1, 1)
    changed = request.model_copy(update={'destination_origin': 'https://elsewhere.example'})
    with pytest.raises(authority.AuthorityManagementError, match='request_conflict'):
        service.configure(s.manager, s.validated.sha256, 'business_api', changed, s.token)


def test_stale_snapshot_and_concurrent_same_id_have_one_effect(fresh):
    s = fresh
    before = inspect(s)
    request = service.ConnectorSettingsRequest(request_id=identity(), expected_snapshot=before['snapshot'], action='save',
        destination_origin='https://service.example', create_credential=True, credential_label='Test API',
        credential={'username': 'operator', 'password': PASSWORD})
    # Key admission is intentionally fail-fast under contention. A loser can
    # only look up the durable result; it never automatically repeats Save.
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service.configure, s.manager, s.validated.sha256,
            'business_api', request, s.token) for _ in range(2)]
        results = []
        for future in futures:
            try: results.append(future.result())
            except Exception as error:
                from backend.services.application_authority_keys import AuthorityReviewKeyError
                assert isinstance(error, AuthorityReviewKeyError)
    assert results and all(r == results[0] for r in results)
    assert service.outcome(s.manager, s.validated.sha256, request.request_id, s.token) == results[0]
    with pytest.raises(authority.AuthorityManagementError, match='snapshot_conflict'):
        save(s, state=before)
    assert counts(s) == (1, 1, 1)


@pytest.mark.parametrize('change', ['non_admin', 'revoked', 'demoted', 'artifact'])
def test_current_actor_and_artifact_are_rechecked(fresh, change):
    s = fresh
    state = inspect(s)
    token = s.token
    if change == 'non_admin': token = s.user_token
    elif change == 'revoked':
        with s.engine.begin() as db: db.execute(update(UserSession).where(UserSession.id == 1).values(is_active=False))
    elif change == 'demoted':
        with s.engine.begin() as db: db.execute(update(User).where(User.id == 1).values(role='user'))
    else:
        with s.engine.begin() as db: db.execute(update(ModulePackage).values(sha256='e' * 64))
    request = service.ConnectorSettingsRequest(request_id=identity(), expected_snapshot=state['snapshot'], action='save')
    with pytest.raises((authority.AuthorityManagementError, ValueError)):
        service.configure(s.manager, s.validated.sha256, 'business_api', request, token)
    assert counts(s) == (0, 0, 0)


def test_rotate_revoke_are_confirmed_versioned_and_never_restore_authority(fresh):
    s = fresh
    result, _ = save(s)
    secret_ref = result['state']['credential']['secret_ref']
    for action in ('rotate', 'revoke'):
        state = inspect(s)
        fields = dict(request_id=identity(), expected_snapshot=state['snapshot'], action=action,
            secret_ref=secret_ref, credential={'username': 'new', 'password': PASSWORD + '_ROTATED'} if action == 'rotate' else None)
        with pytest.raises(authority.AuthorityManagementError):
            service.configure(s.manager, s.validated.sha256, 'business_api', service.ConnectorSettingsRequest(**fields), s.token)
        request = service.ConnectorSettingsRequest(**fields, confirm_credential_change=True)
        value = service.configure(s.manager, s.validated.sha256, 'business_api', request, s.token)
        assert value['state']['authority'] != 'granted'
        assert value['state']['credential']['version'] == 2
    assert value['state']['credential']['revoked'] is True
    with Session(s.engine) as db:
        with pytest.raises(ApplicationSecretError): decrypt_secret_reference(db.scalar(select(Secret)))


def client(s):
    app = FastAPI()
    app.include_router(router, prefix='/api/v1/application-extensions')
    def session():
        with Session(s.engine) as db: yield db
    app.dependency_overrides[get_db] = session
    return TestClient(app)


def test_http_denial_and_validation_never_echo_credential_bodies(fresh):
    s = fresh
    http = client(s)
    root = '/api/v1/application-extensions/packages/' + s.validated.sha256 + '/connector-settings'
    headers = {'Authorization': 'Bearer ' + s.token}
    response = http.get(root, headers=headers)
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    for payload in ({'credential': {'password': PASSWORD}}, {'credential': PASSWORD},
            {'credential': {'password': [PASSWORD]}}, {'unexpected': PASSWORD}):
        result = http.post(root + '/business_api', headers=headers, json=payload)
        assert result.status_code == 422 and PASSWORD not in result.text
    assert http.get(root, headers={'Authorization': 'Bearer ' + s.user_token}).status_code == 403
    assert counts(s) == (0, 0, 0)


def test_http_save_and_outcome_are_scoped_atomic_and_do_not_execute_the_application(fresh):
    s = fresh
    http = client(s)
    root = '/api/v1/application-extensions/packages/' + s.validated.sha256 + '/connector-settings'
    headers = {'Authorization': 'Bearer ' + s.token}
    state = http.get(root, headers=headers).json()
    body = dict(request_id=identity(), expected_snapshot=state['snapshot'], action='save',
        destination_origin='https://service.example', create_credential=True,
        credential_label='Test API', credential={'username': 'operator', 'password': PASSWORD})
    response = http.post(root + '/business_api', headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'applied' and PASSWORD not in response.text
    assert http.post(root + '/business_api', headers=headers, json=body).json() == response.json()
    assert http.get(root + '/outcomes/' + body['request_id'], headers=headers).json() == response.json()
    assert counts(s) == (1, 1, 1)
    state = http.get(root, headers=headers).json()
    bad = {**body, 'request_id': identity(), 'expected_snapshot': state['snapshot'],
        'destination_origin': 'https://private-password@service.example/api'}
    rejected = http.post(root + '/business_api', headers=headers, json=bad)
    assert rejected.status_code == 422 and rejected.json()['detail']['code'] == 'invalid_request'
    assert PASSWORD not in rejected.text and 'private-password' not in rejected.text
    assert counts(s) == (1, 1, 1)
    from backend.routes.modules import router as module_router
    http.app.include_router(module_router)
    catalog = http.get('/api/v1/modules/packages', headers=headers)
    assert catalog.status_code == 200 and catalog.json()[0]['has_connector_settings'] is True


def test_own_sqlite_bootstrap_and_existing_registration_keep_sealed_provenance(fresh):
    from backend.services.application_relational_registration import register_relational_package
    s = fresh
    repack(s, relational=True, optional=True)
    registered = register_relational_package(s.manager, package_id=1, artifact_sha256=s.validated.sha256,
        configuration={'API_URL': 'https://unconfigured.example', 'API_CREDENTIAL': 'secret_' + 'f' * 32},
        actor_token=s.token, request_id=identity(), confirm_register_without_start=True)
    with Session(s.engine) as db:
        original = db.get(Action, registered['registration_id']).payload
    save(s)
    preview = consent_preview(s.manager, registered['installation_id'], actor_token=s.token, request_id=identity())
    assert 'connector:business_api' in preview['scopes']
    assert 'storage:relational_read' in preview['scopes']
    with Session(s.engine) as db:
        assert db.get(Action, registered['registration_id']).payload == original
        app = db.scalar(select(Installation))
        assert app.active_version is None and app.status == 'disabled' and not app.enabled


def test_required_own_sqlite_connector_can_be_configured_before_any_native_consent(fresh):
    s = fresh
    repack(s, relational=True)
    save(s)
    result = consent_preview(s.manager, 1, actor_token=s.token, request_id=identity())
    assert {'connector:business_api', 'storage:relational_read'} <= set(result['scopes'])


@pytest.mark.parametrize('action', ['rotate', 'revoke'])
def test_credential_change_withdraws_an_actual_grant_before_any_further_send(managed, action):
    s = managed
    activate_grant(s)
    assert s.manager.inspect(1)['grant_effective']
    state = inspect(s)
    request = service.ConnectorSettingsRequest(request_id=identity(), expected_snapshot=state['snapshot'],
        action=action, confirm_credential_change=True, secret_ref=state['connectors'][0]['credential']['secret_ref'],
        credential={'username': 'replacement', 'password': PASSWORD} if action == 'rotate' else None)
    service.configure(s.manager, s.validated.sha256, 'business_api', request, s.token)
    assert not s.manager.inspect(1)['grant_effective']
    def forbidden(*a, **kw): pytest.fail('Revoked authority reached the external service')
    with pytest.raises((authority.AuthorityManagementError, RuntimeError, ValueError)):
        connector(s, transport=forbidden)


@pytest.mark.parametrize('case', ['key', 'origin', 'credential'])
def test_rejected_edit_leaves_a_healthy_application_and_grant_unchanged(managed, monkeypatch, case):
    s = managed
    activate_grant(s)
    state = inspect(s)
    def snapshot():
        with Session(s.engine) as db:
            app = db.get(Installation, 1)
            return (app.configuration, app.authority_mode, app.authority_epoch,
                [(r.secret_ref, r.version, r.encrypted_value) for r in db.scalars(select(Secret))],
                [(r.destination_origin, r.secret_reference_id, r.authority_revision) for r in db.scalars(select(Binding))])
    before = snapshot()
    fields = dict(request_id=identity(), expected_snapshot=state['snapshot'], action='save',
        destination_origin='https://service.example', create_credential=True, credential_label='Replacement',
        credential={'username': 'operator', 'password': PASSWORD})
    if case == 'key': monkeypatch.delenv('AI_SETTINGS_MASTER_KEY')
    elif case == 'origin': fields['destination_origin'] = 'file:///private'
    else: fields['credential'] = {'token': PASSWORD}
    with pytest.raises(authority.AuthorityManagementError):
        service.configure(s.manager, s.validated.sha256, 'business_api', service.ConnectorSettingsRequest(**fields), s.token)
    assert snapshot() == before
    assert s.manager.inspect(1)['grant_effective']


def test_origin_change_preserves_other_configuration_and_requires_fresh_consent(managed):
    s = managed
    activate_grant(s)
    with Session(s.engine) as db:
        before = dict(db.get(Installation, 1).configuration)
    result, _ = save(s)
    assert result['state']['authority'] == 'stale'
    with Session(s.engine) as db:
        current = db.get(Installation, 1).configuration
        declaration = s.validated.application_extension.connectors[0]
        other = set(before) - {declaration.destination_config_key, declaration.credential_ref_config_key}
        assert {k: current[k] for k in other} == {k: before[k] for k in other}
        assert current[declaration.destination_config_key] == 'http://127.0.0.1:9999'
        assert current[declaration.credential_ref_config_key] == result['state']['credential']['secret_ref']
    assert not s.manager.inspect(1)['grant_effective']


def test_other_administrator_cannot_read_a_receipt_and_stale_snapshot_cannot_overwrite(fresh):
    from datetime import UTC, datetime, timedelta
    s = fresh
    state = inspect(s)
    token = create_access_token('3', {'sid': 3, 'token_version': 0})
    with Session(s.engine) as db, db.begin():
        db.add(User(id=3, username='other-admin', role='admin')); db.flush()
        db.add(UserSession(id=3, user_id=3, token=token, is_active=True,
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)))
    result, request = save(s, state=state)
    with pytest.raises(authority.AuthorityManagementError):
        service.outcome(s.manager, s.validated.sha256, request.request_id, token)
    changed = request.model_copy(update={'request_id': identity()})
    with pytest.raises(authority.AuthorityManagementError, match='snapshot_conflict'):
        service.configure(s.manager, s.validated.sha256, 'business_api', changed, token)
    assert counts(s) == (1, 1, 1)


def test_other_installation_cannot_select_or_rotate_the_credential(fresh):
    s = fresh
    result, request = save(s)
    manifest = s.validated.manifest.model_dump(mode='json')
    definition = s.validated.application_extension.model_dump(mode='json')
    manifest['module_id'] = definition['module_id'] = 'org.example.other-connection'
    output = io.BytesIO()
    with zipfile.ZipFile(s.archive) as old, zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('application-extension.json', json.dumps(definition))
        archive.writestr(definition['service']['artifact'], old.read(definition['service']['artifact']))
    package = validate_module_package(output.getvalue())
    path = s.root / 'modules' / (package.sha256 + '.zip'); path.write_bytes(output.getvalue())
    with Session(s.engine) as db, db.begin():
        db.add(ModulePackage(module_id=manifest['module_id'], version=manifest['version'], manifest=manifest,
            sha256=package.sha256, file_path=str(path), size_bytes=len(output.getvalue()), registrations=[]))
    other = service.inspect(s.manager, package.sha256, s.token)
    fields = dict(request_id=identity(), expected_snapshot=other['snapshot'], action='save',
        destination_origin='https://other.example', secret_ref=result['state']['credential']['secret_ref'])
    with pytest.raises(authority.AuthorityManagementError):
        service.configure(s.manager, package.sha256, 'business_api', service.ConnectorSettingsRequest(**fields), s.token)
    with pytest.raises(authority.AuthorityManagementError):
        service.outcome(s.manager, package.sha256, request.request_id, s.token)
    assert counts(s) == (1, 1, 1)


def test_session_expiry_at_the_final_commit_check_rolls_back_the_entire_setup(fresh, monkeypatch):
    from backend.services.application_policy_reviews import PolicyReviewStoreError
    s = fresh
    original = service.create_secret_reference
    def expires_during_write(*args, **kwargs):
        result = original(*args, **kwargs)
        def expired(*a, **kw): raise PolicyReviewStoreError('actor_unavailable')
        monkeypatch.setattr(service, '_actor', expired)
        return result
    monkeypatch.setattr(service, 'create_secret_reference', expires_during_write)
    with pytest.raises(authority.AuthorityManagementError, match='actor_unavailable'):
        save(s)
    assert counts(s) == (0, 0, 0)


def test_receipts_survive_token_refresh_but_not_a_different_login_or_incarnation(fresh):
    from datetime import UTC, datetime, timedelta
    s = fresh
    result, request = save(s)
    from backend.utils.jwt_utils import decode_token
    refreshed = create_access_token('1', {'sid': 1, 'token_version': 0, 'jti': decode_token(s.token)['jti'], 'test_refresh': identity()})
    other_login = create_access_token('1', {'sid': 9, 'token_version': 0})
    with Session(s.engine) as db, db.begin():
        db.execute(update(UserSession).where(UserSession.id == 1).values(token=refreshed))
        db.add(UserSession(id=9, user_id=1, token=other_login, is_active=True,
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)))
    assert service.outcome(s.manager, s.validated.sha256, request.request_id, refreshed) == result
    assert service.configure(s.manager, s.validated.sha256, 'business_api', request, refreshed) == result
    with pytest.raises(authority.AuthorityManagementError):
        service.outcome(s.manager, s.validated.sha256, request.request_id, other_login)
    replacement = create_access_token('1', {'sid': 1, 'token_version': 0})
    with s.engine.begin() as db:
        db.execute(update(UserSession).where(UserSession.id == 1).values(token=replacement))
    with pytest.raises(authority.AuthorityManagementError):
        service.outcome(s.manager, s.validated.sha256, request.request_id, replacement)
    with s.engine.begin() as db:
        db.execute(update(UserSession).where(UserSession.id == 1).values(token=refreshed))
    with s.engine.begin() as db:
        db.execute(update(Installation).values(authority_incarnation=identity()))
    with pytest.raises(authority.AuthorityManagementError):
        service.outcome(s.manager, s.validated.sha256, request.request_id, refreshed)
    assert counts(s) == (1, 1, 1)


def test_stopped_installation_can_complete_setup_before_first_native_consent(managed):
    s = managed
    Base.metadata.create_all(s.engine)
    with s.engine.begin() as db: db.execute(delete(Binding))
    with pytest.raises(authority.AuthorityManagementError, match='stop_required'):
        save(s)
    with s.engine.begin() as db:
        db.execute(update(Installation).values(status='disabled', enabled=False))
    save(s)
    result = consent_preview(s.manager, 1, actor_token=s.token, request_id=identity())
    assert 'connector:business_api' in result['scopes']
    with Session(s.engine) as db:
        app = db.get(Installation, 1)
        assert app.authority_mode == 'review_required' and not app.enabled
