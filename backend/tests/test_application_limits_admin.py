"""Installed resource reporting is an admin observation, not an application action."""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.accounts.tokens import create_access_token
from backend.applications.management import api as routes
from backend.db.module import ApplicationExtensionInstallation
from backend.tests.test_application_lifecycle_authority import lifecycle


def test_admin_only_exact_instance_no_cache_no_helper(lifecycle, monkeypatch):
    s = lifecycle
    observed = []
    def collect(instance):
        assert not s.sessions[-1].in_transaction()
        observed.append(instance)
        return {'state': 'observed', 'usage': {'memory_bytes': None, 'tasks': 7}}
    monkeypatch.setattr(routes.application_resources, 'collect', collect)
    monkeypatch.setattr(routes, 'sys', type('Linux', (), {'platform': 'linux'}))
    path = s.base + '/resource-limits'
    assert s.client.get(path).status_code == 401
    user = {'Authorization': 'Bearer ' + create_access_token('2', {'role': 'user'})}
    assert s.client.get(path, headers=user).status_code == 403
    assert s.client.get('/api/v1/application-extensions/not-installed/resource-limits', headers=s.auth).status_code == 404
    assert observed == []
    response = s.client.get(path, headers=s.auth)
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert response.json()['usage'] == {'memory_bytes': None, 'tasks': 7}
    assert observed == [s.result['instance_id']] and not s.calls


@pytest.mark.parametrize('endpoint', ['/resource-limits', '/support-snapshot'])
def test_discard_sample_on_reinstall_and_release_busy_slot(lifecycle, monkeypatch, endpoint):
    s = lifecycle
    path = s.base + endpoint
    monkeypatch.setattr(routes, 'sys', type('Linux', (), {'platform': 'linux'}))
    def change(instance):
        assert not s.sessions[-1].in_transaction()
        with Session(s.engine) as db, db.begin():
            db.get(ApplicationExtensionInstallation, 1).authority_incarnation = 'd' * 32
        return {'state': 'observed', 'old_sample': True}
    monkeypatch.setattr(routes.application_resources, 'collect', change)
    with routes._resource_probe:
        assert s.client.get(path, headers=s.auth).status_code == 429
    response = s.client.get(path, headers=s.auth)
    assert response.status_code == 409 and 'old_sample' not in response.text
    monkeypatch.setattr(routes.application_resources, 'collect', lambda _: {'state': 'not_running'})
    sample = s.client.get(path, headers=s.auth).json()
    assert (sample.get('service', sample)) == {'state': 'not_running'}
    assert not s.calls


def test_only_verified_current_package_is_exported_without_global_history_or_app_execution(lifecycle, monkeypatch):
    from backend.system.diagnostics import failures
    from backend.db.module import ModulePackage
    from tools.diagnostics import explain
    s = lifecycle
    store = failures.RecentHttpFailures()
    monkeypatch.setattr(failures, 'recent_http_failures', store)
    monkeypatch.setattr(routes, 'sys', type('Linux', (), {'platform': 'linux'}))
    def sample(instance):
        assert not s.sessions[-1].in_transaction()
        return {'state': 'not_running', 'supervision': {'state': 'failed', 'result': 'exit-code'}}
    monkeypatch.setattr(routes.application_resources, 'collect', sample)
    with Session(s.engine) as db:
        app = db.get(ApplicationExtensionInstallation, 1)
        instance, incarnation, artifact = app.instance_id, app.authority_incarnation, db.get(ModulePackage, app.module_package_id).sha256
    path = s.base + '/support-snapshot'
    assert s.client.get(path).status_code == 401
    user = {'Authorization': 'Bearer ' + create_access_token('2', {'role': 'user'})}
    assert s.client.get(path, headers=user).status_code == 403
    ids = ['invoke_' + str(i) * 32 for i in range(5)]
    for trace, owner, tag in zip(ids, (instance, instance, instance, 'e'*24, instance), (
        failures.observation_revision(instance, incarnation, artifact), failures.observation_revision(instance, incarnation, 'b'*64),
        failures.observation_revision(instance, 'd'*32, artifact), failures.observation_revision('e'*24, incarnation, artifact), None)):
        store.record(trace_id=trace, instance_id=owner, application_revision=tag, route='/{module_id}/operations/{operation_id}',
                     method='POST', status=409, duration_ms=2)
    response = s.client.get(path, headers=s.auth)
    data = response.json()
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert 'attachment' in response.headers['content-disposition']
    assert data['status'] == 'ready' and data['service']['state'] == 'not_running'
    assert data['application']['artifact_sha256'] == artifact and not data['automatic_replay_allowed']
    assert [case['case_id'] for case in explain(data)['cases']] == [ids[0]]
    assert not any(trace in response.text for trace in ids[1:])
    assert 'dropped' not in response.text.split('"coverage":', 1)[0] and not s.calls
    with store._lock:
        partial = s.client.get(path, headers=s.auth).json()
    assert partial['status'] == 'partial' and partial['coverage']['failure_history'] == 'busy'
    assert partial['service']['state'] == 'not_running' and partial['cases'] == []
    with routes._resource_probe:
        assert s.client.get(path, headers=s.auth).status_code == 429


def test_revocation_during_support_observation_withholds_the_download(lifecycle, monkeypatch):
    from backend.db.user import User
    s = lifecycle
    monkeypatch.setattr(routes, 'sys', type('Linux', (), {'platform': 'linux'}))
    def revoke(_instance):
        assert not s.sessions[-1].in_transaction()
        with Session(s.engine) as db, db.begin():
            db.get(User, 1).token_version += 1
        return {'state': 'observed'}
    monkeypatch.setattr(routes.application_resources, 'collect', revoke)
    response = s.client.get(s.base + '/support-snapshot', headers=s.auth)
    assert response.status_code == 401 and 'artifact_sha256' not in response.text
    assert not s.calls


def test_support_joins_only_exact_task_command_and_admitted_sensor_event(lifecycle, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from backend.db.application_command import ApplicationCommandEpoch, ApplicationCommandRequest
    from backend.db.application_task import ApplicationTaskRun
    from backend.db.device import Device, DeviceCommand, DeviceEvent
    from tools.diagnostics import explain
    s = lifecycle
    monkeypatch.setattr(routes, 'sys', type('Linux', (), {'platform': 'linux'}))
    probes = []
    monkeypatch.setattr(routes.application_resources, 'collect', lambda _: probes.append(1) or {'state':'not_running'})
    stamp = datetime.now(UTC)
    secret = 'BUSINESS-DATA-NOT-FOR-SUPPORT'
    task, cmd = 'task_' + '5'*32, 'cmd_' + '6'*32
    with Session(s.engine) as db, db.begin():
        app = db.get(ApplicationExtensionInstallation, 1)
        db.add(ApplicationTaskRun(task_run_id=task, installation_id=1, package_id=1, incarnation=app.authority_incarnation,
            authority_epoch=app.authority_epoch, grant_revision=1, task_id='job', request_id='r', request_hash='e'*64,
            state='running', payload={'private':secret}, result={'private':secret}, due_at=stamp, not_after=stamp, progress=21,
            dispatched=True, started=False))
        db.add(Device(id=2, device_id='dev_'+'2'*32, display_name=secret, role='node', protocol_version='1.0',approved_at=stamp))
        db.flush()
        db.add(DeviceEvent(device_id=2,event_id='private-event-reference',event_type='example',
                           payload={'secret':secret},occurred_at=stamp))
        db.add(DeviceCommand(device_id=1, command_id=cmd, command_type='application.capability.invoke', idempotency_key='fixture',
                             payload={'secret':secret}, status='succeeded', expires_at=stamp,
                             created_at=stamp-timedelta(seconds=23.5), delivered_at=stamp, delivery_attempts=2,
                             completed_at=stamp-timedelta(hours=1)))  # intentionally different device clock
        db.flush()
        db.add(ApplicationCommandRequest(command_id=cmd,installation_id=1,package_id=1,generation='c'*32,claimed=True,
                                         task_run_id=task,passage_event_id='private-event-reference'))
    path = s.base + '/support-snapshot'
    def reference(ref):
        response = s.client.get(path, params={'reference':ref}, headers=s.auth)
        assert response.status_code == 200 and secret not in response.text and 'private-event-reference' not in response.text
        return explain(response.json())['work']
    assert s.client.get(path, params={'reference':'not a reference'}, headers=s.auth).status_code == 400 and not probes
    assert reference(cmd) == {'reference':cmd,'status':'found','recorded_state':'succeeded','linked_task':task,'device_event_recorded':True,
                              'delivery':{'recorded_attempts':2,'queue_to_latest_offer_seconds':23}}
    assert reference(task) == {'reference':task,'status':'found','recorded_state':'running','progress':21,'start_boundary':'dispatch_recorded'}
    with Session(s.engine) as db, db.begin():
        db.get(ApplicationTaskRun, task).started=True
        db.scalar(select(DeviceCommand).where(DeviceCommand.command_id == cmd)).delivered_at=stamp-timedelta(days=1)
    assert reference(task)['start_boundary']=='start_permit_consumed'
    assert reference(cmd)['delivery']=={'recorded_attempts':2,'queue_to_latest_offer_seconds':None}
    with Session(s.engine) as db, db.begin():
        db.get(ApplicationTaskRun, task).incarnation = '1'*32
    assert reference(cmd)['linked_task'] is None and reference(task)['status'] == 'not_found_in_scope'
    with Session(s.engine) as db, db.begin():
        db.get(ApplicationCommandEpoch, 1).generation = '1'*32
    assert reference(cmd)['status'] == reference('cmd_'+'0'*32)['status'] == 'not_found_in_scope'
    assert not s.calls
