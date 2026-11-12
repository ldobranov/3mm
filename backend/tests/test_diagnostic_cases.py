"""Useful bounded cases, including refused session tickets; no real provider."""
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.applications.sessions.api import application_session_router
from backend.applications.sessions.authority import SessionAuthorityError
from backend.applications.sessions.browser import ApplicationBrowserSessions
from backend.system.diagnostics import failures, operations
from backend.system.diagnostics.cases import build_cases
from backend.tests.test_diagnostics import _client, use_test_jwt_secret
from packages.protocol.diagnostics import DiagnosticSession
from packages.protocol.interactive_session import SessionOpenRequestV1

PRIVATE = 'TOKEN_AND_TERMINAL_TEXT_MUST_NOT_BE_STORED'


def request():
    return SessionOpenRequestV1(request_id='fixture_request', provider_id='org.example.fixture',
        capability_id='fixture.shell', device_id='dev_' + 'a' * 32, access_mode='write', options={'cols': 80, 'rows': 24})


def service():
    authority = SimpleNamespace(manager=SimpleNamespace(engine=None),
        admit=lambda **kwargs: SimpleNamespace(session_id=kwargs['session_id'], installation_id=1,
                                             binding_id='console', login_session_id=1))
    value = ApplicationBrowserSessions(authority)
    value.verify_ui = lambda *args: 1
    value._resource = lambda *args: {}
    value._runtime = lambda *args: object()
    return value


def client(value, monkeypatch):
    recorder = DiagnosticSession('core', '0.3.11')
    recorder.start(60)
    monkeypatch.setattr(operations, 'core_diagnostics', recorder)
    store = failures.RecentHttpFailures()
    app = FastAPI()
    app.add_middleware(failures.HttpFailureMiddleware, store=store)
    app.include_router(application_session_router(value))
    return TestClient(app), store, recorder


def body(request_id='fixture_request'):
    data = request().model_dump(mode='json'); data['request_id'] = request_id
    return {'binding_id': 'console', 'ui_context': {'host_version': 1, 'entrypoint_id': 'console',
        'artifact_sha256': 'a' * 64, 'built_ui_sha256': 'b' * 64}, 'request': data}


PATH = '/api/v1/application-extensions/org.example.fixture/session-host/console/ticket'


@pytest.mark.parametrize('reason', ['session_permission_denied', 'session_target_unavailable',
                                   'session_resource_unavailable', 'grant_not_current', 'review_key_busy'])
def test_omitted_discovery_resource_retains_safe_reason_with_http200_and_recording_off(monkeypatch, reason):
    value = service()
    declaration = SimpleNamespace(binding_id='console')
    prepared = SimpleNamespace(package=SimpleNamespace(application_extension=SimpleNamespace(session_bindings=[declaration])))
    value.authority.manager._prepare = lambda *_: prepared
    def denied(*_):
        # Do not need real credentials or a provider to exercise the existing catch boundary.
        operations.note_failure('session.authority', reason)
        raise SessionAuthorityError(PRIVATE, reason=reason)
    value._resource = denied
    http, store, recorder = client(value, monkeypatch)
    recorder.stop()
    with http:
        response = http.get(PATH.removesuffix('/ticket'), params={
            'artifact_sha256': 'a' * 64, 'built_ui_sha256': 'b' * 64}, headers={'Authorization': PRIVATE})
    assert response.status_code == 200 and response.json() == {'session_host_version': 1, 'targets': []}
    trace = response.headers['x-3mm-trace-id']
    case = build_cases(store.snapshot(), recorder.snapshot(), {'probe_status': 'complete'}, trace_id=trace)['cases'][0]
    assert case['evidence']['reason'] == reason
    assert case['evidence']['stage'] == 'session.authority'
    assert case['evidence']['handled_refusal'] is True and case['evidence']['status'] == 200
    assert case['execution'] == 'not_dispatched' and case['automatic_replay_allowed'] is False
    assert case['trace_records'] == [] and not value.tickets
    assert PRIVATE not in response.text and PRIVATE not in json.dumps(case)


def test_discovery_keeps_other_authorized_targets_without_disclosing_rejected_resource(monkeypatch):
    value = service()
    declarations = [SimpleNamespace(binding_id=name, provider_id='org.example.fixture',
        capability_id='fixture.shell', access_mode='write', control_actions=[], options={})
        for name in ('hidden', 'visible')]
    value.authority.manager._prepare = lambda *_: SimpleNamespace(package=SimpleNamespace(
        application_extension=SimpleNamespace(session_bindings=declarations)))
    def resource(_installation, binding, _authorization):
        if binding == 'hidden':
            raise SessionAuthorityError(PRIVATE, reason='session_permission_denied')
        return {'target_device_id': 'dev_' + 'a' * 32}
    value._resource = resource
    value._runtime = lambda *_: None
    http, store, _ = client(value, monkeypatch)
    with http:
        response = http.get(PATH.removesuffix('/ticket'), params={
            'artifact_sha256': 'a' * 64, 'built_ui_sha256': 'b' * 64})
    assert response.status_code == 200
    targets = response.json()['targets']
    assert len(targets) == 1 and targets[0]['bindingId'] == 'visible' and targets[0]['available'] is False
    row = store.snapshot()['records'][0]
    assert row['reason'] == 'session_permission_denied' and row['handled_refusal'] is True
    assert 'hidden' not in response.text and PRIVATE not in json.dumps(row)
    assert not value.tickets


def test_capacity_refusal_and_missing_executor_have_different_safe_cases_without_starting_provider(monkeypatch):
    value = service()
    http, store, recorder = client(value, monkeypatch)
    with http:
        assert http.post(PATH, json=body('first')).status_code == 200
        response = http.post(PATH, json=body('second'))
        trace = response.headers['x-3mm-trace-id']
        case = build_cases(store.snapshot(), recorder.snapshot(), {'probe_status': 'complete'}, trace_id=trace)['cases'][0]
        assert case['evidence']['reason'] == 'session_binding_busy'
        assert case['evidence']['stage'] == 'session.capacity'
        assert case['execution'] == 'not_dispatched' and case['automatic_replay_allowed'] is False
        assert case['trace_records'] and case['next_check'] == 'inspect_session_recovery'
        value._runtime = lambda *args: None
        response = http.post(PATH, json=body('third'))
        assert response.status_code == 403 and store.snapshot()['records'][0]['reason'] == 'session_runtime_unavailable'
        assert 'Current session access is unavailable' in response.text


def test_403_diagnostics_keep_typed_reason_but_never_the_exception_or_credentials(monkeypatch):
    value = service()
    def denied(*args):
        raise SessionAuthorityError(PRIVATE, reason='session_permission_denied')
    value._resource = denied
    http, store, recorder = client(value, monkeypatch)
    with http:
        response = http.post(PATH + '?secret=' + PRIVATE, json=body(), headers={'Authorization': PRIVATE})
    assert response.status_code == 403
    bundle = build_cases(store.snapshot(), recorder.snapshot(), {'probe_status': 'complete'})
    assert bundle['cases'][0]['evidence']['reason'] == 'session_permission_denied'
    assert PRIVATE not in json.dumps(bundle) and PRIVATE not in response.text


def test_repetitions_are_aggregated_but_distinct_causes_and_instances_remain_visible():
    now = [1.0]
    store = failures.RecentHttpFailures(clock=lambda: now[0], wall=lambda: now[0])
    for index in range(20):
        now[0] += 1
        store.record(trace_id='invoke_' + f'{index:032x}', method='POST', route='/ticket', status=403,
            duration_ms=2, details=[('session.capacity', 'session_binding_busy')], instance_id='a' * 24)
    row = store.snapshot()['records'][0]
    assert row['occurrences'] == 20 and len(row['trace_ids']) == 8
    assert len(store.snapshot()['records']) == 1
    store.record(trace_id='invoke_' + 'b' * 32, method='POST', route='/ticket', status=403,
        duration_ms=2, details=[('session.runtime', 'session_runtime_unavailable')], instance_id='b' * 24)
    assert len(store.snapshot()['records']) == 2
    row['trace_ids'].append(PRIVATE)
    assert PRIVATE not in json.dumps(store.snapshot())


def test_unknown_or_partial_evidence_is_not_a_success_or_a_replay_instruction():
    value = build_cases({'status': 'busy', 'records': []}, {'status': 'busy', 'records': []},
                        {'probe_status': 'unavailable'}, trace_id='invoke_' + 'a' * 32)
    assert value['status'] == 'partial' and value['selection']['result'] == 'not_found_in_retained_evidence'
    assert next(row for row in value['coverage'] if row['boundary'] == 'browser')['status'] == 'not_collected'
    assert not any(value['actions_performed'].values())


def test_cases_and_export_require_current_admin_and_use_same_bounded_evidence(monkeypatch):
    from backend.system.diagnostics import api
    store = failures.RecentHttpFailures()
    store.record(trace_id='invoke_' + 'a' * 32, method='POST', route='/fixture/{id}', status=403, duration_ms=3)
    monkeypatch.setattr(api, 'recent_http_failures', store)
    monkeypatch.setattr(api, 'observe', lambda *args: {'probe_status': 'complete', 'components': []})
    http, db, admin, viewer = _client()
    try:
        for path in ('/api/v1/diagnostics/cases', '/api/v1/diagnostics/cases/export'):
            assert http.get(path).status_code == 401
            assert http.get(path, headers={'Authorization': 'Bearer ' + viewer}).status_code == 403
            response = http.get(path, headers={'Authorization': 'Bearer ' + admin})
            assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
            assert response.json()['cases'][0]['case_id'] == 'invoke_' + 'a' * 32
            assert PRIVATE not in response.text
        with api._case_lock:
            assert http.get('/api/v1/diagnostics/cases', headers={'Authorization': 'Bearer ' + admin}).status_code == 409
        assert http.get('/api/v1/diagnostics/cases?trace_id=bad', headers={'Authorization': 'Bearer ' + admin}).status_code == 422
        from backend.db.user import User
        db.get(User, 1).token_version += 1; db.commit()
        assert http.get('/api/v1/diagnostics/cases', headers={'Authorization': 'Bearer ' + admin}).status_code == 401
    finally:
        http.close(); db.close()
