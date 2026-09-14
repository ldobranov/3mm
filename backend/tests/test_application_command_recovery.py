from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.tests.test_application_commands import setup, payload
from backend.db.device import DeviceCommand
from backend.services import application_commands as broker
from backend.services.device_commands import DeviceCommandError, command_envelope
from three_mm_protocol.application_commands import ApplicationCommandSubmitV1
from three_mm_application_sdk import ApplicationPlatformClient
from agent.physical_command_journal import PhysicalCommandJournal


def lookup(s, request_id='request-1'):
    return broker.command_lookup(s.db, s.app, {'request_id': request_id, 'binding_id': 'gate'})


def test_absolute_deadline_replay_conflict_and_agent_expiry(setup, monkeypatch, tmp_path):
    s = setup
    now = datetime.now(UTC)
    deadline = now + timedelta(seconds=3)
    request = {**payload(), 'not_after': deadline.isoformat()}
    original_queue = broker.queue_command
    monkeypatch.setattr(broker, 'queue_command', lambda *args, **kwargs: original_queue(*args, **kwargs, now=now + timedelta(seconds=1)))
    submitted = broker.submit_command(s.db, s.app, request)
    assert datetime.fromisoformat(submitted['expires_at']) == deadline
    # Replaying after expiry returns the original outcome, never a new deadline.
    monkeypatch.setattr(broker, 'queue_command', lambda *args, **kwargs: original_queue(*args, **kwargs, now=deadline + timedelta(seconds=1)))
    assert broker.submit_command(s.db, s.app, request)['expires_at'] == submitted['expires_at']
    equivalent = {**request, 'not_after': deadline.astimezone(timezone(timedelta(hours=3))).isoformat()}
    assert broker.submit_command(s.db, s.app, equivalent)['command_id'] == submitted['command_id']
    with pytest.raises(DeviceCommandError, match='different content'):
        broker.submit_command(s.db, s.app, {**request, 'not_after': (deadline + timedelta(seconds=1)).isoformat()})
    s.db.rollback()
    command = s.db.scalar(select(DeviceCommand))
    effects = []
    result = PhysicalCommandJournal(tmp_path / 'journal').execute(
        command_envelope(command, s.devices[0].device_id), lambda: effects.append(1), now=lambda: deadline)
    assert result.output['execution_state'] == 'not_executed'
    assert not effects


def test_delayed_submission_queues_nothing(setup, monkeypatch):
    s = setup
    deadline = datetime.now(UTC) + timedelta(seconds=1)
    original = broker.queue_command
    monkeypatch.setattr(broker, 'queue_command', lambda *args, **kwargs: original(*args, **kwargs, now=deadline))
    with pytest.raises(DeviceCommandError, match='deadline has expired'):
        broker.submit_command(s.db, s.app, {**payload(), 'not_after': deadline.isoformat()})
    assert not s.db.scalars(select(DeviceCommand)).all()


@pytest.mark.parametrize('value', ['2026-09-15T09:00:00', 1789300000, 'invalid'])
def test_deadline_requires_aware_datetime(value):
    with pytest.raises(ValueError):
        ApplicationCommandSubmitV1.model_validate({**payload(), 'not_after': value})


def test_lookup_lost_reply_changed_binding_invalidation_and_isolation(setup):
    s = setup
    assert lookup(s) == {'status': 'not_found'}
    submitted = broker.submit_command(s.db, s.app, payload())  # Treat reply as lost.
    s.app.configuration = {**s.app.configuration, 'OUTPUT_DEVICE_ID': s.devices[1].device_id}
    s.db.commit()
    found = lookup(s)
    assert found == {'status': 'found', 'command': submitted}
    assert found['command']['claimed'] is False
    assert len(s.db.scalars(select(DeviceCommand)).all()) == 1
    assert broker.command_lookup(s.db, SimpleNamespace(id=s.app.id + 1), {'request_id': 'request-1', 'binding_id': 'gate'}) == {'status': 'not_found'}
    with pytest.raises(ValueError):
        broker.command_lookup(s.db, s.app, {'request_id': 'request-1', 'binding_id': 'gate', 'installation_id': s.app.id + 1})
    broker.invalidate_commands(s.db, s.app.id)
    s.app.enabled = False
    s.db.commit()
    assert lookup(s)['command']['status'] == 'invalidated'
    assert lookup(s)['command']['command_id'] == submitted['command_id']


def test_lookup_ambiguous_original_targets_fails_explicitly(setup):
    s = setup
    broker.submit_command(s.db, s.app, payload())
    s.app.configuration = {**s.app.configuration, 'OUTPUT_DEVICE_ID': s.devices[1].device_id}
    s.db.commit()
    broker.submit_command(s.db, s.app, payload())
    with pytest.raises(ValueError, match='ambiguous'):
        lookup(s)


def test_lookup_during_delayed_submission_is_only_a_snapshot(setup, monkeypatch):
    s = setup
    original = broker.queue_command
    observed = []
    def delayed(*args, **kwargs):
        observed.append(lookup(s))
        return original(*args, **kwargs)
    monkeypatch.setattr(broker, 'queue_command', delayed)
    submitted = broker.submit_command(s.db, s.app, payload())
    assert observed == [{'status': 'not_found'}]
    assert lookup(s)['command']['command_id'] == submitted['command_id']


def test_sdk_preserves_legacy_and_serializes_deadline(monkeypatch, tmp_path):
    client = ApplicationPlatformClient(tmp_path / 'unused', 'a'*24, b's'*32)
    calls = []
    monkeypatch.setattr(client, '_call', lambda action, body: calls.append((action, body)) or {})
    client.submit_command('gate', request_id='one', arguments={})
    assert 'not_after' not in calls[-1][1]['command']
    deadline = datetime.now(UTC)
    client.submit_command('gate', request_id='one', arguments={}, not_after=deadline)
    assert calls[-1][1]['command']['not_after'] == deadline.isoformat()
    with pytest.raises(ValueError):
        client.submit_command('gate', request_id='one', arguments={}, not_after=datetime.now())
    client.command_lookup(request_id='one', binding_id='gate')
    assert calls[-1] == ('command.lookup', {'lookup': {'request_id': 'one', 'binding_id': 'gate'}})


def test_signed_lookup_allows_disabled_history_but_not_submit(setup, monkeypatch, tmp_path):
    import json
    import hmac
    import hashlib
    import time
    import backend.database
    from sqlalchemy.orm import sessionmaker
    from backend.services.application_platform import ApplicationPlatformServer
    s = setup
    submitted = broker.submit_command(s.db, s.app, payload())
    s.app.enabled = False
    s.db.commit()
    server = ApplicationPlatformServer(tmp_path / 'unused.sock', tmp_path)
    secret = b's'*32
    (tmp_path / f'{s.app.instance_id}.key').write_bytes(secret)
    monkeypatch.setattr(backend.database, 'SessionLocal', sessionmaker(bind=s.db.get_bind()))
    request = {'version': 1, 'instance_id': s.app.instance_id, 'timestamp': int(time.time()),
        'request_id': 'transport-1', 'action': 'command.lookup',
        'lookup': {'request_id': 'request-1', 'binding_id': 'gate'}}
    monkeypatch.setattr(server, '_read', lambda connection: request)
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def sendall(self, value): self.response = json.loads(value)
    connection = Connection()
    request['signature'] = 'wrong'
    server._handle(connection)
    assert connection.response['ok'] is False
    request['signature'] = hmac.new(secret, server._canonical(request), hashlib.sha256).hexdigest()
    server._handle(connection)
    assert connection.response['result']['command']['command_id'] == submitted['command_id']
    assert connection.response['result']['command']['status'] == 'invalidated'
    request['action'] = 'command.submit'
    request['command'] = payload('another')
    request['signature'] = hmac.new(secret, server._canonical(request), hashlib.sha256).hexdigest()
    server._handle(connection)
    assert connection.response['ok'] is False
    assert len(s.db.scalars(select(DeviceCommand)).all()) == 1


def test_lookup_after_actual_restore_retains_original_association(setup, tmp_path, monkeypatch):
    import sqlite3
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from backend.db.module import ApplicationExtensionInstallation
    from deployment import restore_application_extensions as restore
    s = setup
    submitted = broker.submit_command(s.db, s.app, payload())
    app_id = s.app.id
    s.app.enabled = False
    s.db.commit()
    database = tmp_path / 'restored.db'
    with sqlite3.connect(database) as destination:
        s.db.connection().connection.driver_connection.backup(destination)
    monkeypatch.setattr(restore, 'WANTS_ROOT', tmp_path / 'missing')
    restore.restore_application_extensions(database, service_ids=(1, 1))
    engine = create_engine(f'sqlite:///{database.as_posix()}')
    try:
        with Session(engine) as db:
            app = db.get(ApplicationExtensionInstallation, app_id)
            recovered = broker.command_lookup(db, app, {'binding_id': 'gate', 'request_id': 'request-1'})
            assert recovered['command']['command_id'] == submitted['command_id']
            assert recovered['command']['status'] == 'invalidated'
            assert recovered['command']['claimed'] is False
    finally:
        engine.dispose()


def test_lookup_racing_uncommitted_submit_does_not_write(setup, tmp_path, monkeypatch):
    import sqlite3
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import Session
    from backend.db.module import ApplicationExtensionInstallation
    s = setup
    app_id = s.app.id
    s.db.commit()
    database = tmp_path / 'concurrent.db'
    with sqlite3.connect(database) as destination:
        s.db.connection().connection.driver_connection.backup(destination)
    engine = create_engine(f'sqlite:///{database.as_posix()}')
    pending, release = threading.Event(), threading.Event()
    original = broker.commit_queued_command
    def pause_before_commit(*args, **kwargs):
        pending.set()
        if not release.wait(5):
            raise RuntimeError('Test submit timed out')
        return original(*args, **kwargs)
    monkeypatch.setattr(broker, 'commit_queued_command', pause_before_commit)
    def submit():
        with Session(engine) as db:
            return broker.submit_command(db, db.get(ApplicationExtensionInstallation, app_id), payload())
    reads = []
    def inspect_lookup(conn, cursor, statement, parameters, context, executemany):
        if threading.current_thread() is threading.main_thread():
            reads.append(statement.lstrip().split()[0].upper())
    event.listen(engine, 'before_cursor_execute', inspect_lookup)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(submit)
            try:
                assert pending.wait(5)
                with Session(engine) as db:
                    app = db.get(ApplicationExtensionInstallation, app_id)
                    assert broker.command_lookup(db, app, {'request_id': 'request-1', 'binding_id': 'gate'}) == {'status': 'not_found'}
            finally:
                release.set()
            submitted = future.result(timeout=5)
            with Session(engine) as db:
                app = db.get(ApplicationExtensionInstallation, app_id)
                assert broker.command_lookup(db, app, {'request_id': 'request-1', 'binding_id': 'gate'})['command']['command_id'] == submitted['command_id']
        assert reads and set(reads) == {'SELECT'}
    finally:
        engine.dispose()
