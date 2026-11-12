"""Always-on safe HTTP metadata, without detailed recording or installed services."""
import json
import os
import re
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest
from starlette.concurrency import run_in_threadpool

from backend.system.diagnostics import failures
from backend.tests.test_diagnostics import _client, use_test_jwt_secret


PRIVATE = 'NEVER_STORE_TOKEN_OR_BUSINESS_CONTENT'


def event(index=0, **changes):
    return dict(trace_id='invoke_' + f'{index:032x}', method='POST',
                route='/api/v1/example/{record_id}', status=409, duration_ms=2, **changes)


def test_ring_is_count_byte_rate_and_time_bounded_and_returns_detached_metadata():
    now = [1.0]
    store = failures.RecentHttpFailures(clock=lambda: now[0], wall=lambda: now[0] + 1000)
    store.COALESCE_SECONDS = 0  # Exercise distinct retained events, not grouping.
    for index in range(130):
        now[0] += 1
        store.record(**event(index))
    value = store.snapshot()
    assert len(value['records']) == 100 and value['buffer_bytes'] <= value['max_bytes']
    assert value['records'][0]['trace_id'] == 'invoke_' + f'{129:032x}'
    value['records'][0]['details'].append({'reason': PRIVATE})
    assert PRIVATE not in json.dumps(store.snapshot())
    for index in range(20):
        store.record(**event(200 + index))
    assert store.snapshot()['dropped']['rate'] > 0
    now[0] += store.RETENTION_SECONDS
    assert store.snapshot()['records'] == [] and store.snapshot()['buffer_bytes'] == 0
    assert failures.RecentHttpFailures().snapshot()['records'] == []  # New process/allocation, no persistence.


@pytest.mark.parametrize('field,value', [
    ('route', '/path?token=' + PRIVATE), ('route', 'https://user:password@example.test'),
    ('trace_id', PRIVATE), ('phase', PRIVATE), ('method', PRIVATE), ('status', 200),
    ('duration_ms', float('nan')), ('details', [('http.response', PRIVATE)]),
])
def test_unknown_or_sensitive_labels_are_rejected(field, value):
    store = failures.RecentHttpFailures()
    values = event(); values[field] = value
    store.record(**values)
    snapshot = store.snapshot()
    assert snapshot['records'] == [] and PRIVATE not in json.dumps(snapshot)


def test_lock_contention_drops_optional_metadata_without_waiting():
    store = failures.RecentHttpFailures()
    with store._lock:
        store.record(**event())
        assert store.snapshot()['status'] == 'busy'
    assert store.snapshot()['records'] == [] and store.snapshot()['dropped']['busy'] == 1


@pytest.mark.parametrize('changes', [
    {'handled_refusal': 'true'}, {'details': []}, {'phase': 'unknown'},
    {'phase': 'execution_unconfirmed'}, {'method': 'POST'}, {'status': 201},
    {'status': 403}, {'details': [('session.resource', PRIVATE)]},
    {'transport': 'websocket', 'status': None},
])
def test_handled_success_marker_is_only_valid_for_explicit_unsent_read_refusals(changes):
    store = failures.RecentHttpFailures()
    values = event()
    values.update(method='GET', status=200, phase='not_dispatched', handled_refusal=True,
                  details=[('session.resource', 'session_permission_denied')])
    values.update(changes)
    store.record(**values)
    assert store.snapshot()['records'] == []


def test_only_explicit_handled_read_refusals_survive_http200_without_changing_the_response():
    store = failures.RecentHttpFailures()
    app = FastAPI()
    app.add_middleware(failures.HttpFailureMiddleware, store=store)
    @app.get('/discovery/{name}')
    def discover(name: str):
        failures.note_dispatch('not_dispatched')
        if name == 'marked':
            failures.note_failure('session.authority', 'review_key_busy')
            failures.note_handled_refusal('session.resource', 'authority_unavailable')
        elif name == 'invalid':
            failures.note_handled_refusal('session.resource', PRIVATE)
        else:
            failures.note_failure('session.resource', 'session_permission_denied')
        return {'targets': []}
    with TestClient(app) as http:
        for name in ('plain', 'invalid', 'marked'):
            response = http.get('/discovery/' + name, headers={'X-3mm-Trace-Id': PRIVATE})
            assert response.status_code == 200 and response.json() == {'targets': []}
        row = store.snapshot()['records'][0]
        assert len(store.snapshot()['records']) == 1
        assert row['trace_id'] == response.headers['x-3mm-trace-id']
        assert row['status'] == 200 and row['handled_refusal'] is True
        assert row['stage'] == 'session.authority' and row['reason'] == 'review_key_busy'
        assert row['phase'] == 'not_dispatched' and row['retryable'] is False
        assert PRIVATE not in json.dumps(row)


def application(store):
    app = FastAPI()
    app.add_middleware(failures.HttpFailureMiddleware, store=store)
    @app.get('/items/{record_id}')
    async def conflict(record_id: str):
        await run_in_threadpool(failures.note_failure, 'authority.key_acquire', 'review_key_busy')
        raise HTTPException(409, PRIVATE)
    @app.post('/unconfirmed')
    async def unconfirmed():
        failures.note_dispatch('not_dispatched')
        await run_in_threadpool(failures.note_dispatch, 'execution_unconfirmed')
        failures.note_dispatch('not_dispatched')  # Cannot falsely undo a dispatch observation.
        raise HTTPException(409, 'Application result is unconfirmed; do not replay')
    @app.get('/server-error')
    def server_error():
        return JSONResponse({'detail': PRIVATE}, status_code=503)
    @app.get('/ok')
    def ok():
        return {'status': 'ready'}
    return app


def test_handled_409_and_5xx_have_server_trace_and_router_template_without_payloads():
    store = failures.RecentHttpFailures()
    with TestClient(application(store)) as client:
        response = client.get('/items/' + PRIVATE + '?password=' + PRIVATE,
                              headers={'Authorization': PRIVATE, 'X-3mm-Trace-Id': PRIVATE})
        assert response.status_code == 409 and response.json() == {'detail': PRIVATE}
        trace_id = response.headers['x-3mm-trace-id']
        assert re.fullmatch('invoke_[0-9a-f]{32}', trace_id)
        row = store.snapshot()['records'][0]
        assert row['trace_id'] == trace_id and row['route'] == '/items/{record_id}'
        assert row['reason'] == 'review_key_busy' and row['phase'] == 'unknown'
        assert PRIVATE not in json.dumps(store.snapshot())
        response = client.post('/unconfirmed', json={'secret': PRIVATE})
        row = store.snapshot()['records'][0]
        assert row['trace_id'] == response.headers['x-3mm-trace-id']
        assert row['phase'] == 'execution_unconfirmed' and row['retryable'] is False
        assert client.get('/server-error').status_code == 503
        assert store.snapshot()['records'][0]['reason'] == 'server_error'
        assert client.get('/ok').status_code == 200 and len(store.snapshot()['records']) == 3


def test_recorder_failure_never_changes_response_or_replays():
    class Broken:
        def record(self, **kwargs):
            raise RuntimeError(PRIVATE)
    with TestClient(application(Broken())) as client:
        response = client.post('/unconfirmed')
        assert response.status_code == 409 and 'do not replay' in response.text
        assert re.fullmatch('invoke_[0-9a-f]{32}', response.headers['x-3mm-trace-id'])


@pytest.mark.skipif(os.name != 'posix', reason='Owned Unix handoff socket, no live application')
def test_real_relay_send_marks_uncertainty_before_a_failed_first_write(monkeypatch):
    import socket
    import tempfile
    import time
    from pathlib import Path
    from backend.applications.runtime import invocations as relay
    from backend.applications.runtime.gateway import ApplicationGatewayError
    store = failures.RecentHttpFailures()
    app = FastAPI()
    app.add_middleware(failures.HttpFailureMiddleware, store=store)
    # Keep the owned AF_UNIX name short, independent of pytest's long test path.
    with tempfile.TemporaryDirectory(prefix='hf-') as root, socket.socket(socket.AF_UNIX) as listener:
        path = Path(root) / 's'
        listener.bind(str(path)); listener.listen(1)
        prepared = SimpleNamespace(secret=b'x' * 32, socket_path=path, expected_peer=None,
            operation_id='fixture', payload={}, context={}, relational_invocation=None)
        attempts = []
        def failed_write(*args):
            attempts.append(True)
            raise OSError(PRIVATE)
        monkeypatch.setattr(relay, 'send_message', failed_write)
        @app.post('/send')
        async def send():
            failures.note_dispatch('not_dispatched')
            try:
                relay._send(SimpleNamespace(handoff_deadline=time.monotonic() + 1), prepared, 'a' * 32)
            except ApplicationGatewayError as error:
                raise HTTPException(409, str(error)) from None
        with TestClient(app) as client:
            response = client.post('/send')
        assert response.status_code == 409 and attempts == [True]
        row = store.snapshot()['records'][0]
        assert row['phase'] == 'execution_unconfirmed' and row['retryable'] is False
        assert PRIVATE not in json.dumps(row)


def test_recent_metadata_and_export_need_current_admin_and_survive_opt_in_expiry(monkeypatch):
    store = failures.RecentHttpFailures()
    store.record(**event())
    monkeypatch.setattr('backend.system.diagnostics.api.recent_http_failures', store)
    client, db, admin, viewer = _client()
    try:
        for suffix in ('/failures', '/failures/export'):
            path = '/api/v1/diagnostics' + suffix
            assert client.get(path).status_code == 401
            assert client.get(path, headers={'Authorization': 'Bearer ' + viewer}).status_code == 403
            response = client.get(path, headers={'Authorization': 'Bearer ' + admin})
            assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
            assert len(response.json()['records']) == 1 and PRIVATE not in response.text
        from packages.protocol.diagnostics import DiagnosticSession
        session = DiagnosticSession('core', '1.0')
        session.start(1); session.stop(); session._expire(float('inf'))
        assert session.snapshot()['records'] == [] and len(store.snapshot()['records']) == 1
        with store._lock:
            response = client.get('/api/v1/diagnostics/failures/export', headers={'Authorization': 'Bearer ' + admin})
        assert response.status_code == 503  # Never download a busy/empty snapshot as success.
        from backend.db.user import User
        user = db.get(User, 1); user.token_version += 1; db.commit()
        assert client.get('/api/v1/diagnostics/failures', headers={'Authorization': 'Bearer ' + admin}).status_code == 401
    finally:
        client.close(); db.close()
