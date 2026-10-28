"""Real two-package M20 approvals and current-source fencing; no service dispatch."""
import io
import json
import os
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.base import Base
from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant, ApplicationNativeReview as Native
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.services import application_consent as consent
from backend.services.application_authority_management import AuthorityManagementError, _load, effect_admission
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_authority_sources import _Unavailable
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_authority_management import installed, source_subject, source_installed, identity
from three_mm_protocol.tests.test_application_composition import query_contract

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Real M20 seals/key ownership/flock')
SCOPE = 'query:directory:read'


def package(s, *, consumer=False):
    manifest = s.validated.manifest.model_dump(mode='json')
    app = s.validated.application_extension.model_dump(mode='json')
    module = 'org.example.consumer' if consumer else app['module_id']
    manifest.update(module_id=module, capabilities={'provides': [], 'consumes': []},
        permissions=['data.read', 'data.write', 'process.spawn'], configuration_defaults={},
        configuration_schema={'type': 'object', 'additionalProperties': False, 'properties': {}})
    app.update(module_id=module, operations=app['operations'][:1],
        command_bindings=[], connectors=[], query_exports=[], query_dependencies=[])
    app['service']['sdk_version'] = '1.3'
    contract = query_contract()
    if consumer:
        manifest['configuration_schema']['properties'] = {
            'DIRECTORY_INSTANCE': {'type': 'string'}, 'DIRECTORY_EXPORT': {'type': 'string'}}
        app['query_dependencies'] = [{'binding_id': 'directory', 'contract': contract,
            'provider_instance_config_key': 'DIRECTORY_INSTANCE', 'provider_export_config_key': 'DIRECTORY_EXPORT'}]
    else:
        app['operations'].append(dict(operation_id='lookup', kind='query', audiences=['internal'],
            idempotency='forbidden', input_schema=contract['input_schema'],
            output_schema=contract['output_schema'], timeout_seconds=5))
        app['query_exports'] = [dict(export_id='lookup', handler_operation_id='lookup', contract=contract)]
    output = io.BytesIO()
    with zipfile.ZipFile(s.archive) as old, zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('application-extension.json', json.dumps(app))
        archive.writestr(app['service']['artifact'], old.read(app['service']['artifact']))
    blob = output.getvalue()
    parsed = validate_module_package(blob)
    path = s.root / 'modules' / (parsed.sha256 + '.zip')
    path.write_bytes(blob)
    return parsed, path, len(blob)


@pytest.fixture
def pair(installed):
    s = installed
    Base.metadata.create_all(s.engine)
    provider, provider_path, provider_size = package(s)
    consumer, consumer_path, consumer_size = package(s, consumer=True)
    with Session(s.engine) as db, db.begin():
        db.execute(update(ModulePackage).where(ModulePackage.id == 1).values(
            sha256=provider.sha256, manifest=provider.manifest.model_dump(mode='json'),
            file_path=str(provider_path), size_bytes=provider_size))
        db.execute(update(Installation).where(Installation.id == 1).values(configuration={}))
        row = ModulePackage(module_id=consumer.manifest.module_id, version='1.0.0', sha256=consumer.sha256,
            manifest=consumer.manifest.model_dump(mode='json'), file_path=str(consumer_path), size_bytes=consumer_size)
        db.add(row); db.flush()
        db.add(Installation(id=2, module_id=consumer.manifest.module_id, module_package_id=row.id,
            instance_id='b'*24, active_version='1.0.0', status='active', enabled=True,
            socket_path=str(s.root/'not-a-running-service.sock'), configuration={
                'DIRECTORY_INSTANCE': 'a'*24, 'DIRECTORY_EXPORT': 'lookup'}))
    s.provider, s.consumer = provider, consumer
    approve(s, 1)
    return s


def preview(s, identifier=2, **kwargs):
    return consent.preview(s.manager, identifier, actor_token=kwargs.pop('actor_token', s.token),
        request_id=identity(), **kwargs)


def approve(s, identifier=2, *, plan=None, scopes=None, **kwargs):
    plan = plan or preview(s, identifier)
    return consent.allow(s.manager, identifier, actor_token=kwargs.pop('actor_token', s.token),
        request_id=kwargs.pop('request_id', identity()), preview_id=plan['preview_id'],
        expected_revision=plan['revision'], fingerprint=plan['fingerprint'],
        scopes=plan['selected_scopes'] if scopes is None else scopes,
        user_permissions=[], accept_native_code=True, **kwargs)


def grant(s, identifier=2):
    with s.manager.keys.locked() as key, Session(s.engine) as db, db.begin():
        return _load(db, key, 'grant', db.get(Grant, identifier), identifier)


def require(s):
    prepared = s.manager._prepare(2)
    with s.manager.keys.locked() as key, Session(s.engine) as db, db.begin():
        return s.manager._require_grant(db, key, 2, prepared, SCOPE)


def test_preview_resolves_both_exact_packages_but_does_not_select_or_grant(pair):
    s = pair
    plan = preview(s)
    assert plan['scopes'] == [SCOPE] and plan['selected_scopes'] == []
    query = plan['resources']['queries'][0]
    assert query['owner']['application_installation_id'] == '2'
    assert query['provider']['application_installation_id'] == '1'
    assert query['owner_instance_id'] == 'b'*24 and query['provider_instance_id'] == 'a'*24
    assert query['package_artifact_sha256'] == s.consumer.sha256
    assert query['provider_artifact']['sha256'] == s.provider.sha256
    assert query['contract_digest'] == s.consumer.application_extension.query_dependencies[0].contract.digest()
    assert query['provider_grant_record_revision'] == grant(s, 1)['revision']
    with Session(s.engine) as db: assert db.get(Grant, 2) is None
    assert not (s.root/'not-a-running-service.sock').exists()


def test_exact_selection_is_sealed_without_claiming_connected_runtime(pair):
    s = pair
    result = approve(s, scopes=[SCOPE])
    assert result['saved'] and not result['effective']
    stored = grant(s)
    assert stored['data']['subject']['subject_version'] == 12
    assert stored['data']['selection']['scopes'] == [SCOPE]
    assert require(s)['revision'] == stored['revision']
    status = s.manager.inspect(2)
    assert status['access_saved'] and not status['grant_effective']
    assert status['runtime_blockers'] == ['query_runtime_not_connected']
    assert preview(s)['selected_scopes'] == [SCOPE]


def test_empty_selection_does_not_authorize_query(pair):
    approve(pair, scopes=[])
    with pytest.raises(AuthorityManagementError): require(pair)


@pytest.mark.parametrize('fault', ['disable', 'revoke', 'renew', 'native_seal', 'configuration', 'incarnation', 'instance', 'corrupt_seal', 'artifact_changed', 'package_pointer'])
def test_provider_drift_fences_existing_consumer_grant_without_restoring_or_replay(pair, fault):
    s = pair
    approve(s, scopes=[SCOPE])
    original = grant(s)
    provider = grant(s, 1)
    if fault == 'revoke':
        s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=provider['revision'])
    elif fault == 'renew': approve(s, 1)
    elif fault == 'artifact_changed':
        with Session(s.engine) as db:
            path = Path(db.get(ModulePackage, 1).file_path)
        path.write_bytes(path.read_bytes() + b'changed after approval')
    else:
        with Session(s.engine) as db, db.begin():
            if fault == 'disable': db.execute(update(Installation).where(Installation.id == 1).values(enabled=False, status='disabled'))
            elif fault == 'configuration': db.execute(update(Installation).where(Installation.id == 1).values(configuration={'unexpected': 'x'}))
            elif fault == 'incarnation': db.execute(update(Installation).where(Installation.id == 1).values(authority_incarnation=identity()))
            elif fault == 'instance': db.execute(update(Installation).where(Installation.id == 1).values(instance_id='c'*24))
            elif fault == 'corrupt_seal': db.execute(update(Grant).where(Grant.installation_id == 1).values(seal='f'*64))
            elif fault == 'native_seal': db.execute(update(Native).where(
                Native.review_id == provider['data']['native_review_id']).values(seal='f'*64))
            elif fault == 'package_pointer': db.execute(update(Installation).where(Installation.id == 1).values(
                module_package_id=db.get(Installation, 2).module_package_id))
    with pytest.raises((AuthorityManagementError, AuthorityReviewKeyError, _Unavailable, ValueError)):
        require(s)
    assert grant(s) == original  # No replacement grant, restored permission or dispatch.


def test_provider_change_without_guard_update_still_invalidates_pending_preview(pair):
    s = pair
    plan = preview(s)
    with Session(s.engine) as db, db.begin():
        db.execute(update(Installation).where(Installation.id == 1).values(enabled=False, status='disabled'))
    with pytest.raises(AuthorityManagementError): approve(s, plan=plan, scopes=[SCOPE])
    with Session(s.engine) as db: assert db.get(Grant, 2) is None


@pytest.mark.parametrize('value', ['missing', 'c'*24, 'http://provider/private', '*', 'b'*24])
def test_missing_foreign_or_self_selection_does_not_fall_back(pair, value):
    with Session(pair.engine) as db, db.begin():
        db.execute(update(Installation).where(Installation.id == 2).values(configuration={
            'DIRECTORY_INSTANCE': value, 'DIRECTORY_EXPORT': 'lookup'}))
    with pytest.raises(AuthorityManagementError): preview(pair)


def test_wrong_export_and_non_administrator_cannot_approve(pair):
    with pytest.raises(AuthorityManagementError): preview(pair, actor_token=pair.user_token)
    with Session(pair.engine) as db, db.begin():
        db.execute(update(Installation).where(Installation.id == 2).values(configuration={
            'DIRECTORY_INSTANCE': 'a'*24, 'DIRECTORY_EXPORT': 'health'}))
    with pytest.raises(AuthorityManagementError): preview(pair)


def test_generic_effect_lease_refuses_query_even_with_a_saved_grant(pair):
    approve(pair, scopes=[SCOPE])
    with Session(pair.engine) as db:
        with pytest.raises(ValueError, match='dedicated Runtime adapter'):
            with effect_admission(db, 2, SCOPE): pytest.fail('Must never yield a generic lease')


def test_consumer_revocation_and_conflicting_request_do_not_restore_authority(pair):
    s = pair
    plan = preview(s)
    request_id = identity()
    approve(s, plan=plan, scopes=[SCOPE], request_id=request_id)
    current = grant(s)
    with pytest.raises(AuthorityManagementError, match='request_conflict'):
        approve(s, plan=plan, scopes=[], request_id=request_id)
    assert grant(s) == current
    s.manager.revoke(2, actor_token=s.token, request_id=identity(), expected_revision=current['revision'])
    with pytest.raises(AuthorityManagementError): require(s)
    assert grant(s)['state'] == 'revoked'


def test_existing_admin_http_consent_accepts_exact_query_scope_not_replacement_authority(pair):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routes.application_authority import router
    from backend.utils.db_utils import get_db

    s = pair
    app = FastAPI(); app.include_router(router)
    def database():
        with Session(s.engine) as db: yield db
    app.dependency_overrides[get_db] = database
    base = '/api/v1/application-extensions/org.example.consumer/authority/consent'
    with TestClient(app) as client:
        assert client.post(base+'/preview', json={'request_id': identity()}).status_code == 401
        assert client.post(base+'/preview', json={'request_id': identity()},
            headers={'Authorization': 'Bearer '+s.user_token}).status_code == 403
        headers = {'Authorization': 'Bearer '+s.token}
        response = client.post(base+'/preview', json={'request_id': identity()}, headers=headers)
        assert response.status_code == 200, response.text
        plan = response.json()
        payload = dict(request_id=identity(), preview_id=plan['preview_id'],
            expected_revision=plan['revision'], fingerprint=plan['fingerprint'],
            scopes=[SCOPE], user_permissions=[], accept_native_code=True)
        assert client.post(base+'/allow', json={**payload, 'provider_instance_id': 'c'*24},
            headers=headers).status_code == 422
        assert client.post(base+'/allow', json={**payload, 'scopes': ['query:*:read']},
            headers=headers).status_code == 422
        response = client.post(base+'/allow', json=payload, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()['saved'] and not response.json()['effective']
        assert require(s)['data']['selection']['scopes'] == [SCOPE]


def test_manual_code_review_and_two_step_m20_apply_use_the_same_query_resource(pair):
    s = pair
    # Preserve M20's existing disabled-only first manual adoption rule.
    with Session(s.engine) as db, db.begin():
        db.execute(update(Installation).where(Installation.id == 2).values(status='disabled', enabled=False))
    native = s.manager.record_native_review(2, actor_token=s.token, request_id=identity(),
        artifact_sha256=s.consumer.sha256, review_document_sha256='d'*64,
        native_code_review_completed=True, accepts_native_host_risk=True)
    plan = s.manager.create_review(2, actor_token=s.token, request_id=identity(),
        native_review_id=native['native_review_id'], scopes=[SCOPE])
    query = plan['resources']['queries'][0]
    assert query['provider_grant_record_revision'] == grant(s, 1)['revision']
    for decision in ('approve', 'apply'):
        plan = s.manager.decide(2, actor_token=s.token, request_id=identity(),
            plan_id=plan['plan_id'], expected_revision=plan['revision'],
            fingerprint=plan['fingerprint'], decision=decision)
    assert require(s)['data']['selection']['scopes'] == [SCOPE]
    assert not s.manager.inspect(2)['grant_effective']
