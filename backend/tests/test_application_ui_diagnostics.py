"""Capture real pre-relay UI failures before key/error redaction; never dispatch."""
import json
import os
import sqlite3

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.db.module import ApplicationPermissionGrant
from backend.db.session import UserSession
from backend.services import application_authority_management as authority
from backend.services import application_invocation_relay as relay, operation_diagnostics as diagnostics
from backend.tests.test_application_ui_concurrency import (
    ui_http, ui_app, managed_installed, source_subject, source_installed,
)
from three_mm_protocol.diagnostic_snapshot import validate_record
from three_mm_protocol.diagnostics import DiagnosticSession
from three_mm_runtime.application_transport import sign_message


pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Real protected key/flock UI denial')
PRIVATE = 'Bearer NEVER_EXPORT_THIS_TOKEN private SQL business content'


@pytest.fixture
def recorder(monkeypatch):
    session = DiagnosticSession('core', '1.0')
    session.start(300)
    monkeypatch.setattr(diagnostics, 'core_diagnostics', session)
    monkeypatch.setattr(relay, 'core_diagnostics', session)
    return session


def records(recorder):
    rows = recorder.snapshot()['records']
    assert rows
    assert all(validate_record(row) == row for row in rows)
    assert PRIVATE not in json.dumps(rows)
    assert len({row['trace_id'] for row in rows}) == 1
    assert diagnostics._authority_trace.get() is None
    return rows


@pytest.mark.parametrize('channel', ['discovery', 'operation'])
def test_real_key_contention_is_recorded_before_generic_http_refusal(ui_http, recorder, channel):
    s = ui_http
    # No fake trust/lock exception: another real EX lease excludes this request.
    with s.keys.locked():
        response = s.get_info() if channel == 'discovery' else s.invoke()
    assert response.status_code == 409
    assert s.sent == []
    rows = records(recorder)
    assert all(row['trace_id'] == response.headers['x-3mm-trace-id'] for row in rows)
    assert any(row['span_id'] == 'authority.key_acquire' and row['reason'] == 'review_key_busy'
               for row in rows)
    if channel == 'discovery':
        assert all(row['operation'] == 'application.ui.discover' for row in rows)
        assert rows[-1]['span_id'] == 'application.ui_discovery'
        assert not any(row['span_id'].startswith('application.dispatch') for row in rows)
    else:
        assert all(row['operation'] == 'application.invoke' for row in rows)
        assert rows[-1]['span_id'] == 'application.admission'
        assert response.json() == {'detail': 'Application UI code trust is temporarily unavailable'}


def test_original_key_failure_is_kept_without_starting_a_diagnostic_session(ui_http, monkeypatch):
    disabled = DiagnosticSession('core', '1.0')
    monkeypatch.setattr(diagnostics, 'core_diagnostics', disabled)
    monkeypatch.setattr(relay, 'core_diagnostics', disabled)
    with ui_http.keys.locked():
        response = ui_http.invoke()
    assert response.status_code == 409 and ui_http.sent == []
    assert disabled.snapshot()['records'] == []
    row = ui_http.failures.snapshot()['records'][0]
    assert row['trace_id'] == response.headers['x-3mm-trace-id']
    assert row['reason'] == 'review_key_busy' and row['stage'] == 'authority.key_acquire'
    assert row['phase'] == 'not_dispatched' and row['retryable'] is False


@pytest.mark.parametrize('phase', ['code_prepare', 'code_identity'])
@pytest.mark.parametrize('code', [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED])
def test_database_failure_survives_key_and_http_error_redaction(ui_http, recorder, monkeypatch, phase, code):
    s = ui_http
    original = sqlite3.OperationalError(PRIVATE)
    original.sqlite_errorcode = code
    failure = OperationalError(PRIVATE, {'secret': PRIVATE}, original)
    def denied(*args, **kwargs):
        raise failure
    monkeypatch.setattr(authority,
        '_prepare_installed_package' if phase == 'code_prepare' else '_resolve_code_identity', denied)
    response = s.invoke()
    assert response.status_code == 409 and s.sent == []
    assert PRIVATE not in response.text
    rows = records(recorder)
    expected_stage = 'authority.code_prepare' if phase == 'code_prepare' else 'authority.snapshot'
    assert any(row['span_id'] == expected_stage and row['reason'] == 'authority_database_busy'
               for row in rows)
    assert not any(row['span_id'] == 'authority.key_acquire' for row in rows)


def test_error_inside_acquired_lease_is_not_reported_as_key_acquisition_failure(ui_http, recorder, monkeypatch):
    from backend.routes import application_extensions as routes
    def fail_policy(*args, **kwargs):
        raise RuntimeError(PRIVATE)
    monkeypatch.setattr(routes, '_ui_route', fail_policy)
    # A programming failure is not rewritten into a key/trust HTTP409. The
    # HTTP middleware still records the failed request; TestClient rethrows it.
    with pytest.raises(RuntimeError, match=PRIVATE):
        ui_http.invoke()
    assert ui_http.sent == []
    rows = records(recorder)
    assert any(row['span_id'] == 'authority.ui_policy' for row in rows)
    assert not any(row['span_id'] == 'authority.key_acquire' for row in rows)
    failure, = ui_http.failures.snapshot()['records']
    assert failure['status'] == 500


def test_inactive_or_failing_recorder_cannot_change_business_or_denial(ui_http, recorder, monkeypatch):
    recorder.stop()
    response = ui_http.invoke()
    assert response.status_code == 200 and len(ui_http.sent) == 1
    assert recorder.snapshot()['records'] == []
    assert diagnostics._authority_trace.get() is None
    def broken_recorder(**kwargs):
        raise RuntimeError(PRIVATE)
    monkeypatch.setattr(recorder, 'record', broken_recorder)
    with ui_http.keys.locked():
        response = ui_http.invoke()
    assert response.status_code == 409 and len(ui_http.sent) == 1
    assert diagnostics._authority_trace.get() is None


@pytest.mark.parametrize('mismatch,expected_stage', [
    ('package', 'authority.ui_binding'),
    ('build', 'authority.ui_snapshot'),
])
def test_stale_browser_binding_is_identified_before_ui_error_redaction(ui_http, recorder, mismatch, expected_stage):
    s = ui_http
    binding = dict(host_version=1, entrypoint_id='operations',
        artifact_sha256='f' * 64 if mismatch == 'package' else s.validated.sha256,
        built_ui_sha256='f' * 64 if mismatch == 'build' else s.build.built_ui_sha256)
    response = s.invoke(ui_context=binding)
    assert response.status_code == 409 and s.sent == []
    rows = records(recorder)
    assert any(row['span_id'] == expected_stage for row in rows)
    failure, = s.failures.snapshot()['records']
    assert failure['stage'] == expected_stage
    assert failure['phase'] == 'not_dispatched' and failure['retryable'] is False


@pytest.mark.parametrize('fault,expected_stage,reason', [
    ('permission', 'authority.ui_preflight', 'operation_denied'),
    ('session', 'authority.ui_preflight', 'authentication_failed'),
    ('transaction', 'authority.ui_snapshot', 'ui_code_unavailable'),
    ('expired_proof', 'authority.ui_snapshot', 'ui_code_unavailable'),
    ('commit', 'application.commit', 'authority_database_busy'),
])
@pytest.mark.parametrize('opt_in', [False, True])
def test_completion_identifies_the_original_check_even_without_opt_in(
    ui_http, recorder, monkeypatch, fault, expected_stage, reason, opt_in,
):
    s = ui_http
    if not opt_in:
        recorder.stop()
    def after_send():
        # The fixture doubles response transport, so explicitly mark the same
        # uncertainty transition that real _send records before the first byte.
        relay.note_dispatch('execution_unconfirmed')
        if fault in {'permission', 'session'}:
            with s.engine.begin() as connection:
                if fault == 'permission':
                    connection.execute(delete(ApplicationPermissionGrant))
                else:
                    connection.execute(update(UserSession).where(UserSession.id == 2).values(is_active=False))
    s.after_send = after_send
    original_artifact = authority._UiTrustSnapshot.artifact_for
    changed = []
    def artifact(proof, db, *args):
        if s.sent and not changed and fault in {'transaction', 'expired_proof'}:
            changed.append(True)
            if fault == 'transaction':
                db.rollback()
                db.begin()
            else:
                proof.active = False
        return original_artifact(proof, db, *args)
    monkeypatch.setattr(authority._UiTrustSnapshot, 'artifact_for', artifact)
    original_commit = Session.commit
    def commit(db):
        if fault == 'commit' and s.sent and db in s.sessions:
            original = sqlite3.OperationalError(PRIVATE)
            original.sqlite_errorcode = sqlite3.SQLITE_BUSY
            raise OperationalError(PRIVATE, {'secret': PRIVATE}, original)
        return original_commit(db)
    monkeypatch.setattr(Session, 'commit', commit)
    response = s.invoke()
    assert response.status_code == 409
    assert response.json() == {'detail': 'Application result is unconfirmed; do not replay'}
    assert len(s.sent) == 1, 'Completion failure must never replay the dispatched operation'
    failure, = s.failures.snapshot()['records']
    assert failure['stage'] == expected_stage and failure['reason'] == reason
    assert failure['trace_id'] == response.headers['x-3mm-trace-id']
    assert failure['phase'] == 'execution_unconfirmed' and failure['retryable'] is False
    assert any(item['stage'] == 'application.completion' for item in failure['details'])
    assert PRIVATE not in json.dumps(failure) and PRIVATE not in response.text
    if opt_in:
        rows = records(recorder)
        assert any(row['span_id'] == expected_stage and row['reason'] == reason for row in rows)
        assert not any(row['span_id'] == 'authority.key_acquire' for row in rows)
    else:
        assert recorder.snapshot()['records'] == []
    assert all(not db.in_transaction() and authority._UI_TRUST_SNAPSHOT not in db.info for db in s.sessions)
    assert s.leases['active'] == 0


@pytest.mark.parametrize('fault,reason,detail', [
    ('host_error', 'operation_failed', 'Application operation failed; outcome may be unconfirmed'),
    ('signature', 'response_invalid', 'Application result is unconfirmed; do not replay'),
    ('schema', 'response_invalid', 'Application result is invalid'),
])
@pytest.mark.parametrize('opt_in', [False, True])
def test_response_failure_survives_real_key_lease_without_becoming_a_trust_failure(
    ui_http, recorder, monkeypatch, fault, reason, detail, opt_in,
):
    s = ui_http
    if not opt_in:
        recorder.stop()
    original_send = relay._send
    def send(waiter, prepared, request_id):
        relay.note_dispatch('execution_unconfirmed')
        original_send(waiter, prepared, request_id)
        message = {**waiter.response, 'ok': fault != 'host_error',
            'error': PRIVATE, 'result': [] if fault == 'schema' else {}}
        waiter.response = sign_message(message, b'x' * 32 if fault == 'signature' else prepared.secret)
    monkeypatch.setattr(relay, '_send', send)
    response = s.invoke()
    assert response.status_code == 409 and response.json() == {'detail': detail}
    assert len(s.sent) == 1
    failure, = s.failures.snapshot()['records']
    assert failure['stage'] == 'application.response_check' and failure['reason'] == reason
    assert failure['phase'] == 'execution_unconfirmed' and failure['retryable'] is False
    assert failure['details'][-1] == {'stage': 'application.completion', 'reason': reason}
    assert not any(item['stage'] == 'authority.key_acquire' or item['reason'] in {
        'review_key_busy', 'review_key_unavailable', 'authority_unavailable',
    } for item in failure['details'])
    assert PRIVATE not in response.text and PRIVATE not in json.dumps(failure)
    if opt_in:
        rows = records(recorder)
        assert rows[-1]['span_id'] == 'application.completion' and rows[-1]['reason'] == reason
    else:
        assert recorder.snapshot()['records'] == []
    assert all(not db.in_transaction() and authority._UI_TRUST_SNAPSHOT not in db.info for db in s.sessions)
    # The current code/actor discovery still works after denial; no Start replay.
    assert s.get_info().status_code == 200 and len(s.sent) == 1


@pytest.mark.parametrize('opt_in', [False, True])
@pytest.mark.parametrize('collector_broken', [False, True])
def test_verified_host_detail_reaches_http_ring_with_same_trace_without_replay(
    ui_http, recorder, monkeypatch, opt_in, collector_broken,
):
    s = ui_http
    if not opt_in:
        recorder.stop()
    if collector_broken:
        def broken(**kwargs):
            raise RuntimeError(PRIVATE)
        monkeypatch.setattr(recorder, 'record', broken)
    original_send = relay._send
    def send(waiter, prepared, request_id):
        relay.note_dispatch('execution_unconfirmed')
        original_send(waiter, prepared, request_id)
        waiter.response = sign_message({**waiter.response, 'ok': False, 'error': PRIVATE,
            'failure': {'version': 1, 'stage': 'application.host_handler',
                'reason': 'host_sdk_operation_denied', 'duration_ms': 725.2}}, prepared.secret)
    monkeypatch.setattr(relay, '_send', send)
    response = s.invoke()
    assert response.status_code == 409 and response.json() == {
        'detail': 'Application operation failed; outcome may be unconfirmed'}
    assert len(s.sent) == 1
    failure, = s.failures.snapshot()['records']
    assert failure['stage'] == 'application.host_handler' and failure['reason'] == 'host_sdk_operation_denied'
    assert failure['trace_id'] == response.headers['x-3mm-trace-id']
    assert failure['phase'] == 'execution_unconfirmed' and failure['retryable'] is False
    assert failure['details'][-1] == {'stage': 'application.completion', 'reason': 'operation_failed'}
    assert PRIVATE not in response.text and PRIVATE not in json.dumps(failure)
    if opt_in and not collector_broken:
        rows = records(recorder)
        host_row, = [row for row in rows if row['span_id'] == 'application.host_handler']
        assert host_row['trace_id'] == failure['trace_id'] and host_row['instance_id'] == 'a'*24
        assert host_row['duration_ms'] == 725.2 and host_row['parent_span_id'] == 'application.response_check'
        assert rows[-1]['reason'] == 'operation_failed'
    else:
        assert recorder.snapshot()['records'] == []
    assert all(not db.in_transaction() for db in s.sessions)
    assert s.get_info().status_code == 200 and len(s.sent) == 1


@pytest.mark.parametrize('fault', ['missing', 'malformed', 'signature', 'request_id', 'success', 'revoked'])
def test_host_detail_cannot_bypass_verification_policy_or_change_an_operation(ui_http, recorder, monkeypatch, fault):
    s = ui_http
    original_send = relay._send
    def send(waiter, prepared, request_id):
        relay.note_dispatch('execution_unconfirmed')
        original_send(waiter, prepared, request_id)
        detail = {'version': 1, 'stage': 'application.host_handler', 'reason': 'host_value_error', 'duration_ms': 1}
        if fault == 'malformed':
            detail['error'] = PRIVATE  # Even a signed peer cannot export arbitrary fields.
        message = {**waiter.response, 'ok': fault == 'success', 'error': PRIVATE}
        if fault != 'missing':
            message['failure'] = detail
        if fault == 'request_id':
            message['request_id'] = 'e'*32
        waiter.response = sign_message(message, b'x'*32 if fault == 'signature' else prepared.secret)
        if fault == 'revoked':
            with s.engine.begin() as db:
                db.execute(delete(ApplicationPermissionGrant))
    monkeypatch.setattr(relay, '_send', send)
    response = s.invoke()
    assert len(s.sent) == 1 and response.status_code == (200 if fault == 'success' else 409)
    rows = recorder.snapshot()['records']
    assert not any(row['span_id'].startswith('application.host_') for row in rows)
    assert PRIVATE not in response.text and PRIVATE not in json.dumps(rows)
    failures = s.failures.snapshot()['records']
    if fault == 'success':
        assert response.json() == {} and not failures
    else:
        failure, = failures
        assert failure['phase'] == 'execution_unconfirmed' and failure['retryable'] is False
        assert not any(item['stage'].startswith('application.host_') for item in failure['details'])
        assert PRIVATE not in json.dumps(failure)
    assert all(not db.in_transaction() for db in s.sessions)
