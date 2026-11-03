"""Admission linearizes before bounded response capacity; dispatch phases stay honest."""
import os
from dataclasses import replace
from types import SimpleNamespace
import time

from fastapi import HTTPException
import pytest
from sqlalchemy import event, update

from backend.tests.test_application_health_probe import health_db, connector_db
from backend.services import application_invocation_relay as relay
from backend.services.application_extensions import ApplicationGatewayError
from backend.db.module import ApplicationExtensionInstallation as Installation
from three_mm_runtime.application_transport import sign_message
from three_mm_runtime.application_transport import DispatchPhase

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Linux Runtime account admission')


def spec_for(app, package):
    return relay.InvocationSpec(app, package, 'health', {}, {'audience': 'internal'}, 'internal')


def test_no_db_or_preparation_work_consumes_reserved_handoff_budget(health_db, monkeypatch):
    db, app, package, settings = health_db
    reserved = []
    preparations = []
    original = relay._prepare
    def prepare(*args, **kwargs):
        assert not reserved
        preparations.append(kwargs['defer_relational'])
        return original(*args, **kwargs)
    def reserve(settings):
        assert not db.in_transaction()
        reserved.append(True)
        return SimpleNamespace(timeout_seconds=0, close=lambda: None)
    def sql(*args):
        assert not reserved, 'Core performed DB work inside the short handoff budget'
    event.listen(db.bind, 'before_cursor_execute', sql)
    monkeypatch.setattr(relay, '_prepare', prepare)
    monkeypatch.setattr(relay, '_reserve', reserve)
    monkeypatch.setattr(relay, '_send', lambda *args: None)
    try:
        binding, waiter = relay.begin_invocation(db, settings, lambda: spec_for(app, package))
        assert binding.operation_id == 'health' and waiter.timeout_seconds == 10
        assert preparations == [True, True]
    finally:
        event.remove(db.bind, 'before_cursor_execute', sql)


@pytest.mark.parametrize('denial', ['session', 'permission', 'ui', 'epoch', 'package', 'key'])
def test_current_admission_denial_prevents_reservation_and_dispatch(health_db, monkeypatch, denial):
    db, app, package, settings = health_db
    calls = []
    def admit():
        calls.append(True)
        if len(calls) == 3:
            if denial in {'session', 'permission', 'ui'}:
                raise HTTPException(403, 'Current access denied')
            if denial == 'epoch': app.authority_epoch = 'e' * 32
            elif denial == 'package': package.sha256 = 'e' * 64
        return spec_for(app, package)
    original = relay._prepare
    preparations = []
    def prepare(*args, **kwargs):
        result = original(*args, **kwargs)
        preparations.append(True)
        return replace(result, secret=b'z'*32) if denial == 'key' and len(preparations) == 2 else result
    monkeypatch.setattr(relay, '_prepare', prepare)
    monkeypatch.setattr(relay, '_reserve', lambda *args: pytest.fail('Reserved after admission denial'))
    monkeypatch.setattr(relay, '_send', lambda *args: pytest.fail('Dispatched after admission denial'))
    with pytest.raises((HTTPException, ApplicationGatewayError)):
        relay.begin_invocation(db, settings, admit)
    assert not db.in_transaction()


def test_unavailable_response_runtime_is_known_not_dispatched(health_db, monkeypatch):
    db, app, package, settings = health_db
    def unavailable(*args): raise TimeoutError('Runtime capacity unavailable')
    monkeypatch.setattr(relay, '_reserve', unavailable)
    with pytest.raises(ApplicationGatewayError, match='not dispatched') as error:
        relay.begin_invocation(db, settings, lambda: spec_for(app, package))
    assert error.value.phase == DispatchPhase.NOT_DISPATCHED
    assert not db.in_transaction()


def test_enforced_relay_without_key_boundary_fails_before_prepare_or_dispatch(health_db, monkeypatch):
    db, app, package, settings = health_db
    app.authority_mode = 'enforced'
    db.commit()
    monkeypatch.setattr(relay, '_prepare', lambda *a, **kw: pytest.fail('Prepared without a key boundary'))
    monkeypatch.setattr(relay, '_reserve', lambda *a: pytest.fail('Reserved without a key boundary'))
    monkeypatch.setattr(relay, '_send', lambda *a: pytest.fail('Dispatched without a key boundary'))
    with pytest.raises(ApplicationGatewayError, match='authority boundary') as error:
        relay.begin_invocation(db, settings, lambda: spec_for(app, package))
    assert error.value.phase == DispatchPhase.NOT_DISPATCHED
    assert not db.in_transaction()


def test_relational_metadata_is_prepared_once_outside_policy_transactions(health_db, monkeypatch):
    from backend.services import application_relational
    db, app, package, settings = health_db
    metadata, sent = [], []
    original = relay._prepare
    def prepare(*args, **kwargs):
        return replace(original(*args, **kwargs), needs_relational_invocation=True)
    def prepare_host(db, installation_id, operation_id, **kwargs):
        assert not db.in_transaction()
        metadata.append((installation_id, operation_id))
        return {'test_owned_ticket': True}
    monkeypatch.setattr(relay, '_prepare', prepare)
    monkeypatch.setattr(application_relational, 'prepare_host_invocation', prepare_host)
    monkeypatch.setattr(relay, '_reserve', lambda *args: SimpleNamespace(timeout_seconds=0, close=lambda: None))
    def send(waiter, prepared, request_id):
        assert not db.in_transaction()
        assert prepared.relational_invocation == {'test_owned_ticket': True}
        assert not prepared.needs_relational_invocation
        sent.append(request_id)
    monkeypatch.setattr(relay, '_send', send)
    relay.begin_invocation(db, settings, lambda: spec_for(app, package))
    assert metadata == [(app.id, 'health')] and len(sent) == 1


def test_completion_fence_failure_never_claims_not_dispatched(health_db, monkeypatch):
    db, app, package, settings = health_db
    monkeypatch.setattr(relay, '_reserve', lambda *args: SimpleNamespace(timeout_seconds=0, close=lambda: None))
    sent = []
    monkeypatch.setattr(relay, '_send', lambda *args: sent.append(True))
    binding, waiter = relay.begin_invocation(db, settings, lambda: spec_for(app, package))
    db.execute(update(Installation).where(Installation.id == binding.installation_id).values(authority_epoch='f' * 32))
    db.commit()
    response = sign_message({'version': 1, 'request_id': binding.request_id,
        'timestamp': int(time.time()), 'ok': True, 'result': {'status': 'ready'}}, binding.secret)
    with pytest.raises(ApplicationGatewayError, match='unconfirmed') as error:
        relay.finish_invocation(db, settings, lambda: spec_for(app, package), binding, response)
    assert error.value.phase == DispatchPhase.EXECUTION_UNCONFIRMED
    assert len(sent) == 1 and not db.in_transaction()


@pytest.mark.parametrize('failure', ['deadline', 'connect', 'partial_send', 'handoff'])
def test_transport_phase_changes_only_when_request_bytes_may_have_left(monkeypatch, failure):
    sent = []
    class Origin:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def settimeout(self, timeout): pass
        def connect(self, path):
            if failure == 'connect': raise ConnectionRefusedError()
        def sendall(self, data):
            sent.append(data)
            if failure == 'partial_send': raise BrokenPipeError()
    def handoff(origin): raise TimeoutError('FD handoff lost')
    monkeypatch.setattr(relay.socket, 'socket', lambda *args: Origin())
    waiter = SimpleNamespace(handoff_deadline=0 if failure == 'deadline' else time.monotonic()+2, handoff=handoff)
    prepared = SimpleNamespace(operation_id='command', payload={}, context={}, secret=b's'*32,
        socket_path='/unused', expected_peer=None, relational_invocation=None)
    with pytest.raises(ApplicationGatewayError) as error:
        relay._send(waiter, prepared, 'r'*32)
    unknown = failure in {'partial_send', 'handoff'}
    assert error.value.phase == (DispatchPhase.EXECUTION_UNCONFIRMED if unknown else DispatchPhase.NOT_DISPATCHED)
    assert bool(sent) == unknown
