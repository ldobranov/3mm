"""Current administrator, explicit component selection and redacted web boundary."""
import pytest
from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from backend.db.audit_log import AuditLog
from backend.db.user import User
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.db.device import Device, DeviceCommand
from backend.tests.test_system_update_routes import make_client, use_test_jwt_secret  # noqa: F401
from components.system_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError, ComponentUpdateNotAccepted
from components.system_runtime.component_updates import confirmation

BASE = '/api/v1/system-updates/components'
HOST = 'c'*24


def status(component='agent', target='local'):
    return dict(component=component, target_id=target, current_build_id='a'*64, previous_build_id='b'*64,
        ready=True, recovery_required=False, candidate=None, operation=None)


@pytest.fixture
def api(monkeypatch):
    client, db, admin, viewer = make_client()
    package = ModulePackage(module_id='org.test.app', version='1.0.0', manifest={'name': 'Test app'},
        file_path='/not-used', sha256='d'*64, size_bytes=100)
    # Match the real catalog model rather than bypassing the target lookup.
    db.add(package); db.flush()
    db.add(ApplicationExtensionInstallation(module_id=package.module_id, module_package_id=package.id,
        instance_id=HOST, active_version='1.0.0', enabled=True, status='active', socket_path='/not-used.sock'))
    db.commit()
    calls = []
    monkeypatch.setattr(UpdateHelperClient, 'component_status', lambda _self, c, t, u: status(c, t))
    def operation(_self, payload): calls.append(payload); return payload['request_id']
    monkeypatch.setattr(UpdateHelperClient, 'component_operation', operation)
    monkeypatch.setattr('backend.system.updates.components_api.ensure_apply_is_allowed', lambda *a, **k: None)
    try: yield client, db, {'Authorization': 'Bearer '+admin}, {'Authorization': 'Bearer '+viewer}, calls
    finally: client.close(); db.close()


@pytest.mark.parametrize('path', ['/targets', '/agent/local', '/agent/local/prepare', '/agent/local/apply', '/agent/local/rollback', '/agent/local/recover'])
def test_all_operations_require_current_admin_and_token(api, path):
    client, db, admin, viewer, calls = api
    method = client.get if path in {'/targets', '/agent/local'} else client.post
    assert method(BASE+path).status_code == 401
    assert method(BASE+path, headers=viewer).status_code == 403
    user = db.scalar(select(User).where(User.role == 'admin'))
    user.is_blocked = True; db.commit()
    assert method(BASE+path, headers=admin).status_code == 401
    user.is_blocked = False; user.token_version += 1; db.commit()
    assert method(BASE+path, headers=admin).status_code == 401 and not calls


def test_targets_are_explicit_instances_not_default_or_remote_devices(api):
    client, db, admin, _, calls = api
    response = client.get(BASE+'/targets', headers=admin)
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert [(t['component'], t['target_id']) for t in response.json()['targets']] == [('agent', 'local'), ('application_host', HOST)]
    for path in ['/agent/local', '/application_host/'+HOST]:
        result = client.get(BASE+path, headers=admin)
        assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
    assert not calls and not db.scalars(select(AuditLog)).all()


@pytest.mark.parametrize('action', ['prepare', 'apply', 'rollback', 'recover'])
@pytest.mark.parametrize('component,target', [('agent','local'), ('application_host',HOST)])
def test_exact_target_operation_is_queued_and_audited(api, action, component, target):
    client, db, admin, _, calls = api
    payload = dict(request_id='a'*32, expected_operation_id=None)
    if action in {'apply', 'rollback'}:
        payload.update(build_id='b'*64, confirmation=confirmation(action,component,target,'b'*64))
    if action == 'apply': payload['candidate_id'] = 'c'*32
    result = client.post(f'{BASE}/{component}/{target}/{action}', headers=admin, json=payload)
    assert result.status_code == 202 and result.json()['request_id'] == payload['request_id']
    assert calls[0] == {**payload, 'action':'component_'+action, 'component':component, 'target_id':target, 'requested_by_user_id':1}
    audit = db.scalar(select(AuditLog).where(AuditLog.action == 'COMPONENT_OPERATION_ACCEPTED'))
    assert audit.entity_name == target and audit.changes['request_id'] == payload['request_id']


def test_exact_confirmation_and_maintenance_policy_are_not_bypassed(api, monkeypatch):
    client, _, admin, _, calls = api
    payload = dict(request_id='a'*32, expected_operation_id=None, build_id='b'*64, confirmation='anything')
    assert client.post(BASE+'/agent/local/rollback', headers=admin,json=payload).status_code == 422
    payload['confirmation'] = confirmation('rollback','agent','local','b'*64)
    from backend.system.updates.policy import UpdatePolicyError
    def denied(*a, **k): raise UpdatePolicyError('Outside maintenance window')
    monkeypatch.setattr('backend.system.updates.components_api.ensure_apply_is_allowed', denied)
    assert client.post(BASE+'/agent/local/rollback', headers=admin,json=payload).status_code == 409
    assert not calls


@pytest.mark.parametrize('path', ['/application_host/default', '/application_host/'+'f'*24, '/agent/remote', '/runtime/local'])
def test_missing_or_unsupported_targets_cannot_reach_root_helper(api, path):
    client, _, admin, _, calls = api
    assert client.post(BASE+path+'/prepare', headers=admin, json=dict(request_id='a'*32,expected_operation_id=None)).status_code in {404,422}
    assert not calls


def test_caller_paths_and_lost_reply_are_not_forwarded_or_retried(api, monkeypatch):
    client, _, admin, _, calls = api
    payload = dict(request_id='a'*32,expected_operation_id=None)
    assert client.post(BASE+'/agent/local/prepare',headers=admin,json={**payload,'source':'/tmp/upload'}).status_code == 422
    def lost(*a): calls.append(1); raise UpdateHelperError('/private/token secret')
    monkeypatch.setattr(UpdateHelperClient,'component_operation',lost)
    response = client.post(BASE+'/agent/local/prepare',headers=admin,json=payload)
    assert response.status_code == 409 and calls == [1] and '/private' not in response.text and 'secret' not in response.text


def test_wrong_helper_target_is_not_shown_as_selected_status(api, monkeypatch):
    client, _, admin, _, _ = api
    monkeypatch.setattr(UpdateHelperClient,'component_status',lambda *a: status('application_host',HOST))
    assert client.get(BASE+'/agent/local',headers=admin).status_code == 409


def test_proven_refusal_is_distinct_from_lost_response(api,monkeypatch):
    client,_,admin,_,calls=api
    def refused(*a):calls.append(1);raise ComponentUpdateNotAccepted('private preflight detail')
    monkeypatch.setattr(UpdateHelperClient,'component_operation',refused)
    response=client.post(BASE+'/agent/local/prepare',headers=admin,json=dict(request_id='a'*32,expected_operation_id=None))
    assert response.status_code==409 and response.json()=={'detail':{'code':'component_update_not_accepted'}} and calls==[1]


def test_node_registry_is_read_only_scoped_and_excludes_revoked_or_local_devices(api):
    client, db, admin, viewer, calls = api
    for n, role, revoked in [('a','node',False), ('b','node',True), ('c','standalone',False)]:
        db.add(Device(device_id='dev_'+n*32, display_name='Test '+n, role=role, protocol_version='1.0',
            approved_at=datetime.now(UTC), revoked_at=datetime.now(UTC) if revoked else None))
    db.flush()
    device = db.scalar(select(Device).where(Device.device_id=='dev_'+'a'*32))
    db.add(DeviceCommand(command_id='cmd_'+'d'*32,device_id=device.id,command_type='agent.update.prepare',
        payload={'operation_id':'nodeupd_'+'e'*32},idempotency_key='node-update-prepare:one',status='queued',
        expires_at=datetime.now(UTC)+timedelta(minutes=15)))
    db.commit()
    assert client.get(BASE+'/nodes',headers=viewer).status_code == 403
    response = client.get(BASE+'/nodes',headers=admin)
    assert response.status_code == 200 and response.headers['cache-control']=='no-store'
    assert response.json()['nodes']==[{'device_id':device.device_id,'label':'Test a',
        'current_release_id':None,'latest_operation_id':'nodeupd_'+'e'*32}]
    assert not calls
