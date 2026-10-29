"""Admin/revocation, exact payload, redaction and audit for the Runtime web API."""
import pytest
from sqlalchemy import select
from backend.db.audit_log import AuditLog
from backend.db.user import User
from backend.tests.test_system_update_routes import make_client, use_test_jwt_secret  # noqa: F401
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError

BASE = '/api/v1/system-updates/runtime'


def status():
    return {'current_build_id': 'a'*64, 'previous_build_id': None,
        'ready': True, 'recovery_required': False, 'features': {'query_execution_contract': None},
        'reason': None, 'candidate': None, 'operation': None}


@pytest.fixture
def api(monkeypatch):
    client, db, token, viewer = make_client()
    calls = []
    monkeypatch.setattr(UpdateHelperClient, 'platform_runtime_status', lambda _self: status())
    def operation(_self, payload):
        calls.append(payload)
        return payload['request_id']
    monkeypatch.setattr(UpdateHelperClient, 'platform_runtime_operation', operation)
    monkeypatch.setattr('backend.routes.system_updates.ensure_apply_is_allowed', lambda *_a, **_kw: None)
    try:
        yield client, db, {'Authorization': 'Bearer '+token}, {'Authorization': 'Bearer '+viewer}, calls
    finally:
        client.close(); db.close()


@pytest.mark.parametrize('path', ['', '/prepare', '/apply', '/recover'])
def test_all_runtime_endpoints_require_current_administrator(api, path):
    client, db, admin, viewer, calls = api
    method = client.get if not path else client.post
    assert method(BASE+path).status_code == 401
    assert method(BASE+path, headers=viewer).status_code == 403
    user = db.scalar(select(User).where(User.role == 'admin'))
    user.is_blocked = True; db.commit()
    assert method(BASE+path, headers=admin).status_code == 401
    user.is_blocked = False; user.token_version += 1; db.commit()
    assert method(BASE+path, headers=admin).status_code == 401
    assert not calls


def test_status_is_no_store_and_missing_query_feature_is_not_faked(api):
    client, db, admin, viewer, calls = api
    response = client.get(BASE, headers=admin)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['features']['query_execution_contract'] is None
    assert not calls and not db.scalars(select(AuditLog)).all()


def test_prepare_queues_one_bounded_request_and_audits_its_identity(api):
    client, db, admin, viewer, calls = api
    result = client.post(BASE+'/prepare', headers=admin, json={'request_id':'a'*32, 'expected_operation_id':None})
    assert result.status_code == 202 and result.json()['request_id'] == 'a'*32
    assert len(calls) == 1 and calls[0]['action'] == 'platform_runtime_prepare'
    assert set(calls[0]) == {'action','request_id','expected_operation_id','requested_by_user_id'}
    log = db.scalar(select(AuditLog).where(AuditLog.action == 'PLATFORM_RUNTIME_OPERATION_ACCEPTED'))
    assert log.entity_name == 'a'*32


def test_apply_requires_exact_confirmation_and_separate_policy_approval(api, monkeypatch):
    client, db, admin, viewer, calls = api
    payload = {'request_id':'b'*32, 'expected_operation_id':'a'*32,
        'candidate_id':'a'*32, 'build_id':'c'*64, 'confirmation':'UPDATE ANYTHING'}
    assert client.post(BASE+'/apply', headers=admin, json=payload).status_code == 422
    assert not calls
    payload['confirmation'] = 'UPDATE RUNTIME '+'c'*64
    from backend.services.update_policy import UpdatePolicyError
    def deny(*args, **kwargs): raise UpdatePolicyError('Outside maintenance window')
    monkeypatch.setattr('backend.routes.system_updates.ensure_apply_is_allowed', deny)
    assert client.post(BASE+'/apply', headers=admin, json=payload).status_code == 409
    assert not calls


@pytest.mark.parametrize('extra', [{'artifact':'/tmp/x'}, {'source':'/tmp/core'}, {'component':'agent'}])
def test_browser_cannot_supply_privileged_paths_or_components(api, extra):
    client, db, admin, viewer, calls = api
    assert client.post(BASE+'/prepare', headers=admin,
        json={'request_id':'a'*32,'expected_operation_id':None,**extra}).status_code == 422
    assert not calls


def test_helper_failure_is_redacted_and_not_automatically_retried(api, monkeypatch):
    client, db, admin, viewer, calls = api
    attempts = []
    def failed(*args):
        attempts.append(1)
        raise UpdateHelperError('/etc/private password=not-public')
    monkeypatch.setattr(UpdateHelperClient, 'platform_runtime_operation', failed)
    response = client.post(BASE+'/prepare', headers=admin,
        json={'request_id':'a'*32,'expected_operation_id':None})
    assert response.status_code == 409 and len(attempts) == 1
    assert 'password' not in response.text and '/etc/private' not in response.text
