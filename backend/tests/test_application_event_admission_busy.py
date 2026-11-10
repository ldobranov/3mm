"""Real sealed event grants defer contention, never turn it into a denial/replay."""
from contextlib import ExitStack
from datetime import UTC, datetime
import os
import sqlite3
from types import SimpleNamespace

import pytest
from sqlalchemy import event as sqlalchemy_event, select, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from backend.db.authority import CoreAuthorityGuard
from backend.db.device import DeviceCredential, DeviceEvent
from backend.db.module import ApplicationEventCursor, ApplicationEventDelivery
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.services import application_events as broker, application_extensions as gateway
from backend.services import application_authority_management as authority
from backend.tests.test_application_event_authority import (
    events as sealed_events, core_installed, source_subject, source_installed, activate, event, identity,
)
from backend.tests.test_application_events import pump
from backend.tests.test_application_authority_sources import CREDENTIAL, DEVICE


pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Real POSIX key leases and file-backed SQLite')


@pytest.fixture
def events(sealed_events, monkeypatch):
    s = sealed_events
    class Client:
        def __init__(self, *_args):
            pass
        def invoke(self, operation_id, payload, context):
            # The base fixture sends one event. Observe the current claim so a
            # second real queue row also proves that IPC holds no Core lease.
            with s.keys.locked(), Session(s.engine) as observer:
                current = observer.scalar(select(ApplicationEventDelivery).where(
                    ApplicationEventDelivery.status == 'delivering'))
                assert current is not None and current.attempts >= 1
            s.calls.append((operation_id, payload, context))
            return {}
    monkeypatch.setattr(gateway, 'ApplicationServiceClient', Client)
    return s


def clock(monkeypatch):
    value = ['a' * 36, 1000]
    monkeypatch.setattr(broker, '_clock', lambda: tuple(value))
    return value


def enqueue(s, identifier, *, capture_only=False):
    with Session(s.engine) as db:
        broker.enqueue_application_event(db, db.get(DeviceEvent, identifier), s.settings,
            capture_only=capture_only)


def rows(s):
    with Session(s.engine) as db:
        return [dict(id=row.id, event=row.device_event_id, status=row.status,
            attempts=row.attempts, epoch=row.authority_epoch, error=row.last_error,
            not_before=row.retry_not_before_ms, dispatch=row.dispatch_id)
            for row in db.scalars(select(ApplicationEventDelivery).order_by(ApplicationEventDelivery.device_event_id))]


def claim_idle(s):
    with Session(s.engine) as db:
        begin, origin = broker.claim_event_delivery(db, s.settings, runtime_generation='busy-test')
        assert begin['idle'] is True and origin is None


def test_disconnected_claim_during_sealed_admission_is_pending_not_a_denial(events):
    s=events;activate(s);identifier=event(s);enqueue(s,identifier)
    checks=[]
    def caller_current():
        checks.append(1)
        return len(checks)==1
    with Session(s.engine) as db:
        begin,origin=broker.claim_event_delivery(db,s.settings,runtime_generation='gone-caller',
            caller_current=caller_current)
    assert begin['idle'] is True and origin is None and not s.calls
    current=rows(s)
    assert len(checks)==2
    assert current[0]['status']=='pending' and current[0]['attempts']==0 and current[0]['dispatch'] is None


def drain(s):
    with Session(s.engine) as db:
        pump(db, s.settings, generation='busy-test')


def assert_once(s, identifiers, original):
    current = rows(s)
    assert [(row['id'], row['event'], row['epoch']) for row in current] == [
        (row['id'], row['event'], row['epoch']) for row in original]
    assert all(row['status'] == 'acknowledged' and row['attempts'] == 1 for row in current)
    with Session(s.engine) as db:
        event_ids = [db.get(DeviceEvent, identifier).event_id for identifier in identifiers]
        cursor = db.scalar(select(ApplicationEventCursor))
        assert cursor.acknowledged_count == len(identifiers) and cursor.dead_letter_count == 0
    assert [call[1]['event_id'] for call in s.calls] == event_ids
    assert [call[2]['idempotency_key'] for call in s.calls] == event_ids
    drain(s)
    assert len(s.calls) == len(identifiers)


def test_unrelated_shared_reader_allows_enqueue_and_final_admission_once(events, monkeypatch):
    s = events
    activate(s)
    identifiers = [event(s), event(s)]
    # The other reader is a genuine independently opened flock, not an allow mock.
    with s.keys.read_locked():
        for identifier in identifiers:
            enqueue(s, identifier)
    before = rows(s)
    assert len(before) == 2 and all(row['attempts'] == 0 for row in before)
    admit = broker._admit_event_attempt
    def concurrent_reader(*args, **kwargs):
        with s.keys.read_locked():
            return admit(*args, **kwargs)
    monkeypatch.setattr(broker, '_admit_event_attempt', concurrent_reader)
    drain(s)
    assert_once(s, identifiers, before)


def test_exclusive_writer_during_enqueue_persists_original_pending_without_attempt(events, monkeypatch):
    s = events
    activate(s)
    now = clock(monkeypatch)
    identifiers = [event(s), event(s)]
    with s.keys.locked():
        for identifier in identifiers:
            enqueue(s, identifier, capture_only=True)
            enqueue(s, identifier, capture_only=True)  # Source identity remains a unique queue row.
        captured = rows(s)
        assert len(captured) == 2
        assert all(row['status'] == 'pending' and row['attempts'] == 0
            and row['error'] is None and row['not_before'] is None for row in captured)
        # Initial capture does not infer permission; the real grant check occurs
        # at Runtime admission, where the exclusive writer is transient busy.
        claim_idle(s)
    before = rows(s)
    assert len(before) == 2 and not s.calls
    assert all(row['status'] == 'pending' and row['attempts'] == 0 for row in before)
    assert before[0]['error'] == 'authority_admission_unavailable:key_busy'
    assert before[0]['not_before'] == now[1] + broker.AUTHORITY_ADMISSION_RETRY_MS
    claim_idle(s)
    now[1] += broker.AUTHORITY_ADMISSION_RETRY_MS
    drain(s)
    assert_once(s, identifiers, before)


@pytest.mark.parametrize('phase', ['claim', 'final_admission'])
def test_busy_claim_preserves_pending_fifo_and_rechecks_current_grant_after_release(events, monkeypatch, phase):
    s = events
    activate(s)
    now = clock(monkeypatch)
    identifiers = [event(s), event(s)]
    for identifier in identifiers:
        enqueue(s, identifier)
    before = rows(s)
    with ExitStack() as held:
        if phase == 'claim':
            held.enter_context(s.keys.locked())
        else:
            original = gateway.find_operation
            acquired = []
            def acquire_writer_after_preflight(definition, operation_id):
                operation = original(definition, operation_id)
                if not acquired:
                    held.enter_context(s.keys.locked())
                    acquired.append(True)
                return operation
            monkeypatch.setattr(gateway, 'find_operation', acquire_writer_after_preflight)
        claim_idle(s)
    deferred = rows(s)
    assert [(row['id'], row['event'], row['epoch']) for row in deferred] == [
        (row['id'], row['event'], row['epoch']) for row in before]
    assert all(row['status'] == 'pending' and row['attempts'] == 0 for row in deferred)
    assert deferred[0]['error'] == 'authority_admission_unavailable:key_busy'
    assert deferred[0]['not_before'] == now[1] + broker.AUTHORITY_ADMISSION_RETRY_MS
    assert not s.calls
    # Deferring the head cannot let its release/next event overtake it.
    claim_idle(s)
    now[1] += broker.AUTHORITY_ADMISSION_RETRY_MS
    drain(s)
    assert_once(s, identifiers, before)


@pytest.mark.parametrize('change', ['revoke', 'epoch', 'artifact'])
def test_actual_denial_after_busy_is_terminal_and_admin_retry_does_not_replay(events, monkeypatch, change):
    s = events
    activate(s)
    now = clock(monkeypatch)
    identifier = event(s)
    enqueue(s, identifier)
    with s.keys.locked():
        claim_idle(s)
    before = rows(s)[0]
    assert before['status'] == 'pending' and before['attempts'] == 0
    if change == 'revoke':
        s.manager.revoke(1, actor_token=s.token, request_id=identity(),
            expected_revision=s.manager.inspect(1)['grant_record_revision'])
    else:
        with s.engine.begin() as db:
            if change == 'epoch':
                db.execute(update(Installation).where(Installation.id == 1).values(authority_epoch=identity()))
            else:
                db.execute(update(ModulePackage).where(ModulePackage.id == 1).values(sha256='f' * 64))
    now[1] += broker.AUTHORITY_ADMISSION_RETRY_MS
    drain(s)
    denied = rows(s)[0]
    assert denied['id'] == before['id'] and denied['status'] == 'dead_letter'
    assert denied['attempts'] == 0 and not s.calls
    with Session(s.engine) as db:
        assert db.scalar(select(ApplicationEventCursor)).dead_letter_count == 1
        broker.request_application_event_retry(db)
        pump(db, s.settings, generation='busy-test')
        assert db.scalar(select(ApplicationEventCursor)).dead_letter_count == 1
    assert rows(s)[0]['status'] == 'dead_letter' and not s.calls


def test_sqlite_writer_busy_is_transient_not_an_invalid_grant(events):
    s = events
    activate(s)
    def no_wait(connection, _record, _proxy):
        connection.execute('PRAGMA busy_timeout=0')
    sqlalchemy_event.listen(s.engine, 'checkout', no_wait)
    try:
        with Session(s.engine) as writer:
            writer.connection().exec_driver_sql('BEGIN IMMEDIATE')
            writer.execute(update(CoreAuthorityGuard).values(revision=CoreAuthorityGuard.revision))
            with Session(s.engine) as reader:
                with pytest.raises(authority.AuthorityAdmissionUnavailable) as failure:
                    with authority.effect_admission(reader, 1, 'event:changes'):
                        pytest.fail('A DB writer cannot admit a new event attempt')
                assert failure.value.reason == 'database_busy'
                assert not reader.in_transaction()
            writer.rollback()
        with Session(s.engine) as db:
            with authority.effect_admission(db, 1, 'event:changes') as admission:
                assert 'event:changes' in admission.approved_scopes
                db.commit()
                admission()
        assert not s.calls
    finally:
        sqlalchemy_event.remove(s.engine, 'checkout', no_wait)


@pytest.mark.parametrize('damage', ['missing', 'corrupt'])
def test_missing_or_corrupt_review_key_is_denied_not_transient(events, damage):
    from backend.services.application_authority_keys import KEY_NAME
    s = events
    activate(s)
    enqueue(s, event(s))
    path = s.key_directory / KEY_NAME
    previous = path.read_bytes()
    if damage == 'missing':
        path.unlink()
    else:
        path.write_bytes(b'not a valid review key')
    try:
        claim_idle(s)
        failed = rows(s)[0]
        assert failed['status'] == 'dead_letter' and failed['attempts'] == 0
        assert not failed['error'].startswith('authority_admission_unavailable:')
        assert not s.calls
    finally:
        path.write_bytes(previous)
        path.chmod(0o600)
    # Restoring storage availability does not adopt old terminal work.
    with Session(s.engine) as db:
        broker.request_application_event_retry(db)
        pump(db, s.settings, generation='busy-test')
    assert rows(s)[0]['status'] == 'dead_letter' and not s.calls


def test_missing_sqlite_authority_table_is_not_classified_as_retryable_busy(events):
    s = events
    activate(s)
    CoreAuthorityGuard.__table__.drop(s.engine)  # This fixture's disposable database only.
    with Session(s.engine) as db:
        with pytest.raises(ValueError) as failure:
            with authority.effect_admission(db, 1, 'event:changes'):
                pytest.fail('Missing authority storage cannot admit an event')
        assert not isinstance(failure.value, authority.AuthorityAdmissionUnavailable)
        assert not db.in_transaction() and not s.calls


@pytest.fixture
def event_api(events, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routes import device_events as route
    from backend.services.device_pairing import credential_secret_hash
    from backend.utils.db_utils import get_db
    s = events
    secret = 'event-route-fixture-only-secret'
    with s.engine.begin() as db:
        db.execute(update(DeviceCredential).where(DeviceCredential.credential_id == CREDENTIAL)
            .values(secret_hash=credential_secret_hash(secret)))
    activate(s)
    monkeypatch.setattr('backend.database.SessionLocal', lambda: Session(s.engine))
    monkeypatch.setattr(route, 'get_settings', lambda: SimpleNamespace(applications=s.settings))
    app = FastAPI()
    app.include_router(route.router)
    def database():
        with Session(s.engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    acknowledgements = []
    class ObserveAcknowledgement:
        def __init__(self, app):
            self.app = app
        async def __call__(self, scope, receive, send):
            async def observe(message):
                if message['type'] == 'http.response.start' and message['status'] == 202:
                    # Observe the true ACK point, before any BackgroundTasks.
                    durable = rows(s)
                    acknowledgements.append((durable, len(s.calls)))
                await send(message)
            await self.app(scope, receive, observe)
    app.add_middleware(ObserveAcknowledgement)
    with TestClient(app) as client:
        yield SimpleNamespace(s=s, client=client, route=route, acknowledgements=acknowledgements,
            headers={'Authorization':'Device ' + CREDENTIAL + ':' + secret},
            path='/api/v1/devices/' + DEVICE + '/events', payload={
                'event_id':'evt_' + identity(), 'device_id':DEVICE, 'event_type':'device.changed.v1',
                'occurred_at':datetime.now(UTC).isoformat(),
                'payload':{'capability_id':'gpio.digital.control', 'value':True}})


def test_http_202_is_sent_only_after_current_event_has_durable_application_queue_row(event_api):
    api = event_api
    response = api.client.post(api.path, headers=api.headers, json=api.payload)
    assert response.status_code == 202, response.text
    assert response.json() == {'status':'accepted', 'duplicate':False}
    assert len(api.acknowledgements) == 1 and not api.s.calls
    captured, call_count = api.acknowledgements[0]
    assert len(captured) == 1 and captured[0]['status'] == 'pending'
    assert captured[0]['attempts'] == 0 and call_count == 0
    before = rows(api.s)
    drain(api.s)
    assert_once(api.s, [before[0]['event']], before)


def regrant(s):
    s.manager.revoke(1, actor_token=s.token, request_id=identity(),
        expected_revision=s.manager.inspect(1)['grant_record_revision'])
    activate(s)
    assert s.manager.inspect(1)['grant_effective'] is True


def test_http_exact_duplicate_does_not_rematch_historical_raw_event_under_new_grant(event_api):
    api = event_api
    historical = event(api.s)  # Old raw history has no captured application epoch.
    with Session(api.s.engine) as db:
        saved = db.get(DeviceEvent, historical)
        occurred = saved.occurred_at
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=UTC)
        old_payload = {**api.payload, 'event_id':saved.event_id, 'event_type':saved.event_type,
            'occurred_at':occurred.isoformat(), 'payload':saved.payload}
    regrant(api.s)
    response = api.client.post(api.path, headers=api.headers, json=old_payload)
    assert response.status_code == 202, response.text
    assert response.json() == {'status':'accepted', 'duplicate':True}
    assert api.acknowledgements == [([], 0)]
    drain(api.s)
    assert not rows(api.s) and not api.s.calls
    # A newly ingested event still captures this current grant epoch normally.
    response = api.client.post(api.path, headers=api.headers, json=api.payload)
    assert response.status_code == 202 and response.json()['duplicate'] is False
    before = rows(api.s)
    assert len(before) == 1 and before[0]['event'] != historical
    drain(api.s)
    assert_once(api.s, [before[0]['event']], before)


def test_http_duplicate_keeps_old_captured_epoch_and_cannot_adopt_regranted_rights(event_api):
    api = event_api
    response = api.client.post(api.path, headers=api.headers, json=api.payload)
    assert response.status_code == 202
    before = rows(api.s)[0]
    regrant(api.s)
    with Session(api.s.engine) as db:
        assert before['epoch'] != db.get(Installation, 1).authority_epoch
    response = api.client.post(api.path, headers=api.headers, json=api.payload)
    assert response.status_code == 202 and response.json()['duplicate'] is True
    captured = rows(api.s)[0]
    assert (captured['id'], captured['epoch'], captured['attempts']) == (
        before['id'], before['epoch'], 0)
    drain(api.s)
    terminal = rows(api.s)[0]
    assert terminal['status'] == 'dead_letter' and terminal['attempts'] == 0 and not api.s.calls
    response = api.client.post(api.path, headers=api.headers, json=api.payload)
    assert response.status_code == 202 and response.json()['duplicate'] is True
    drain(api.s)
    assert rows(api.s)[0]['status'] == 'dead_letter' and not api.s.calls


def test_revoked_device_credential_cannot_persist_raw_event_or_application_capture(event_api):
    api = event_api
    with api.s.engine.begin() as db:
        db.execute(update(DeviceCredential).where(DeviceCredential.credential_id == CREDENTIAL)
            .values(revoked_at=datetime.now(UTC)))
    response = api.client.post(api.path, headers=api.headers, json=api.payload)
    assert response.status_code == 401
    with Session(api.s.engine) as db:
        assert db.scalar(select(DeviceEvent).where(DeviceEvent.event_id == api.payload['event_id'])) is None
    assert not rows(api.s) and not api.s.calls and not api.acknowledgements


@pytest.mark.parametrize('busy', ['sqlite', 'matcher_lock'])
def test_http_matching_busy_keeps_agent_same_id_retry_and_does_not_sweep_history(event_api, monkeypatch, busy):
    api = event_api
    old_identifier = event(api.s)  # An unrelated historical event is not replayed.
    ingest = api.route.DeviceOperations.event
    failures = [True]
    def once_busy(operations, report, *, before_commit=None):
        assert callable(before_commit), 'HTTP must capture the queue in the raw event transaction'
        def capture_then_busy(*args, **kwargs):
            result = before_commit(*args, **kwargs)
            if failures:
                failures.pop()
                original = sqlite3.OperationalError('database is locked')
                original.sqlite_errorcode = sqlite3.SQLITE_BUSY
                raise OperationalError('fixture capture write', {}, original)
            return result
        return ingest(operations, report, before_commit=capture_then_busy)
    if busy == 'sqlite':
        monkeypatch.setattr(api.route.DeviceOperations, 'event', once_busy)
        response = api.client.post(api.path, headers=api.headers, json=api.payload)
    else:
        # A real held matching lock exhausts the bounded acquisition and enters
        # the EventMatchingBusy route path, without a wall-clock assertion.
        with broker._worker_lock:
            response = api.client.post(api.path, headers=api.headers, json=api.payload)
    assert response.status_code == 503, response.text
    assert response.headers['retry-after'] == '1'
    assert not api.acknowledgements and not rows(api.s) and not api.s.calls
    with Session(api.s.engine) as db:
        saved = db.scalar(select(DeviceEvent).where(DeviceEvent.event_id == api.payload['event_id']))
        assert saved is None  # Raw event and all queue rows rolled back together.
        assert db.get(DeviceEvent, old_identifier) is not None
    response = api.client.post(api.path, headers=api.headers, json=api.payload)
    assert response.status_code == 202, response.text
    assert response.json() == {'status':'accepted', 'duplicate':False}
    before = rows(api.s)
    with Session(api.s.engine) as db:
        saved_identifier = db.scalar(select(DeviceEvent.id).where(DeviceEvent.event_id == api.payload['event_id']))
    assert len(before) == 1 and before[0]['event'] == saved_identifier != old_identifier
    drain(api.s)
    assert_once(api.s, [saved_identifier], before)
