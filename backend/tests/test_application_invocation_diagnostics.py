"""Keep fixed internal reasons/stages without changing dispatch/replay semantics."""
import asyncio
import json
import math
import os
import re
import sqlite3
import time
from types import SimpleNamespace

import backend.database  # noqa: F401 -- register Core's full ORM metadata
from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.db.base import Base
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.services import application_invocation_relay as relay, operation_diagnostics as diagnostics
from backend.services.application_extensions import ApplicationGatewayError
from backend.services.application_response_relay import ApplicationResponseError
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_invocation_relay import spec_for
from backend.tests.test_module_packages import application_package
from three_mm_protocol.diagnostics import DiagnosticSession
from three_mm_runtime.application_transport import DispatchPhase, sign_message

PRIVATE = 'Bearer PRIVATE_TOKEN business payload and native exception details'
pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Linux Runtime account admission')


@pytest.fixture
def invocation_db(tmp_path):
    # Exercise the real async -> worker admission/completion path. The shared
    # health fixture's sqlite:// database is single-thread-only and cannot be
    # passed to run_in_threadpool. Match Core's file-backed SQLite configuration;
    # the one Session is used sequentially, never concurrently across threads.
    import pwd
    blob = application_package()
    validated = validate_module_package(blob)
    archive = tmp_path / 'application.zip'
    archive.write_bytes(blob)
    engine = create_engine(f"sqlite:///{(tmp_path / 'core.db').as_posix()}",
        connect_args={'check_same_thread': False})
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            package = ModulePackage(module_id=validated.manifest.module_id,
                version=validated.manifest.version, manifest=validated.manifest.model_dump(mode='json'),
                sha256=validated.sha256, size_bytes=len(blob), file_path=str(archive), registrations=[])
            db.add_all([package, CoreAuthorityGuard(singleton_id=1)])
            db.flush()
            app = Installation(module_id=package.module_id, module_package_id=package.id,
                instance_id='1' * 24, active_version=package.version,
                status='active', enabled=True, authority_mode='compatibility', socket_path='unused')
            db.add(app)
            db.commit()
            (tmp_path / (app.instance_id + '.key')).write_bytes(b's' * 32)
            settings = SimpleNamespace(key_root=tmp_path,
                runtime_user=pwd.getpwuid(os.geteuid()).pw_name,
                application_response_socket=tmp_path / 'unused.sock')
            db.rollback()
            yield db, app, package, settings
    finally:
        engine.dispose()


@pytest.mark.parametrize('failure,stage,reason,dispatched,detail', [
    ('actor', 'application.admission', 'authentication_failed', False, None),
    ('reserve', 'application.admission', 'deadline_exceeded', False, None),
    ('connect', 'application.dispatch', 'transport_unavailable', False, None),
    ('partial_send', 'application.dispatch', 'transport_unavailable', True, None),
    ('deadline_exceeded', 'application.response', 'deadline_exceeded', True, None),
    ('response_unconfirmed', 'application.response', 'response_unconfirmed', True, None),
    ('response_invalid', 'application.response', 'response_invalid', True, None),
    ('permission', 'application.completion', 'operation_denied', True, 'application.policy_check'),
    ('permission_recheck', 'application.completion', 'operation_denied', True, 'application.policy_recheck'),
    ('session_recheck', 'application.completion', 'authentication_failed', True, 'application.policy_recheck'),
    ('lifecycle', 'application.completion', 'authority_unavailable', True, None),
    ('binding', 'application.completion', 'authority_unavailable', True, 'application.binding_check'),
    ('transport_key', 'application.completion', 'authority_unavailable', True, 'application.binding_check'),
    ('signature', 'application.completion', 'response_invalid', True, 'application.response_check'),
    ('schema', 'application.completion', 'response_invalid', True, 'application.response_check'),
    ('service', 'application.completion', 'operation_failed', True, 'application.response_check'),
    ('commit', 'application.completion', 'authority_unavailable', True, 'application.commit'),
])
def test_exact_safe_failure_stage_retains_trace_and_never_replays(invocation_db, monkeypatch, failure, stage, reason, dispatched, detail):
    db, app, package, settings = invocation_db
    recorder = DiagnosticSession('core', '1.0')
    recorder.start()
    monkeypatch.setattr(relay, 'core_diagnostics', recorder)
    monkeypatch.setattr(diagnostics, 'core_diagnostics', recorder)
    sends, reads, admissions = [], [], []
    class Waiter:
        timeout_seconds = 0
        response = None
        async def receive(self):
            assert not db.in_transaction()
            reads.append(True)
            if failure in {'deadline_exceeded', 'response_unconfirmed', 'response_invalid'}:
                raise ApplicationResponseError(failure)
            return self.response
        def close(self):
            pass
    waiter = Waiter()
    def admit():
        admissions.append(True)
        if failure == 'actor':
            raise HTTPException(401, PRIVATE)
        if failure == 'permission' and len(admissions) == 4:
            raise HTTPException(403, PRIVATE)
        if failure in {'permission_recheck', 'session_recheck'} and len(admissions) == 5:
            raise HTTPException(401 if failure == 'session_recheck' else 403, PRIVATE)
        if failure == 'binding' and len(admissions) == 4:
            app.socket_path = 'changed-within-private-fixture'
        return spec_for(app, package)
    def reserve(*args):
        assert not db.in_transaction()
        if failure == 'reserve':raise TimeoutError(PRIVATE)
        return waiter
    def send(waiter, prepared, identifier):
        assert not db.in_transaction()
        if failure == 'connect':
            raise ApplicationGatewayError('Application request was not dispatched', phase=DispatchPhase.NOT_DISPATCHED,
                diagnostic_reason='transport_unavailable')
        sends.append(identifier)
        if failure == 'partial_send':
            raise ApplicationGatewayError('Application result is unconfirmed; do not replay', diagnostic_reason='transport_unavailable')
        if failure == 'lifecycle':
            db.execute(update(Installation).where(Installation.id == app.id).values(authority_epoch='f' * 32))
            db.commit()
        if failure == 'transport_key':
            (settings.key_root / ('1' * 24 + '.key')).write_bytes(b't' * 32)
        waiter.response = sign_message({'version': 1, 'timestamp': int(time.time()), 'request_id': identifier,
            'ok': failure != 'service', 'result': [] if failure == 'schema' else {'status': 'ready'},
            'error': PRIVATE}, b'x' * 32 if failure == 'signature' else prepared.secret)
    monkeypatch.setattr(relay, '_reserve', reserve)
    monkeypatch.setattr(relay, '_send', send)
    if failure == 'commit':
        original_commit = db.commit
        def commit():
            if sends:
                original = sqlite3.OperationalError(PRIVATE)
                original.sqlite_errorcode = sqlite3.SQLITE_BUSY
                raise OperationalError(PRIVATE, {'private': PRIVATE}, original)
            return original_commit()
        monkeypatch.setattr(db, 'commit', commit)
    with pytest.raises((ApplicationGatewayError, HTTPException)) as error:
        asyncio.run(relay.invoke_with_relay(db, settings, admit))
    if isinstance(error.value, ApplicationGatewayError):
        assert error.value.phase == (DispatchPhase.EXECUTION_UNCONFIRMED if dispatched else DispatchPhase.NOT_DISPATCHED)
        assert error.value.retryable is False
        assert PRIVATE not in str(error.value)
    assert len(sends) == int(dispatched)
    if failure == 'actor':
        assert admissions == [True], 'Actor denial was masked by an earlier fixture failure'
    if stage in {'application.admission', 'application.dispatch'}:
        assert not reads
    records = recorder.snapshot()['records']
    assert records[-1]['span_id'] == stage and records[-1]['reason'] == reason
    assert len({row['trace_id'] for row in records}) == 1
    assert re.fullmatch(r'invoke_[0-9a-f]{32}', records[0]['trace_id'])
    assert all(math.isfinite(row['duration_ms']) and row['duration_ms'] >= 0 for row in records)
    assert PRIVATE not in json.dumps(records)
    if detail is not None:
        specific = next(row for row in records if row['span_id'] == detail)
        assert specific['reason'] == ('authority_database_busy' if failure == 'commit' else reason)
        assert specific['parent_span_id'] == 'application.completion'
    if stage == 'application.completion':
        assert any(row['span_id'] == 'application.response' and row['result'] == 'ok' for row in records)
        assert records[-1]['parent_span_id'] == 'application.response'
    assert not db.in_transaction()


@pytest.mark.parametrize('recorder_broken', [False, True])
def test_success_is_not_changed_by_optional_diagnostics(invocation_db, monkeypatch, recorder_broken):
    db, app, package, settings = invocation_db
    recorder = DiagnosticSession('core', '1.0')
    recorder.start()
    monkeypatch.setattr(relay, 'core_diagnostics', recorder)
    monkeypatch.setattr(diagnostics, 'core_diagnostics', recorder)
    if recorder_broken:
        def broken(**kwargs):raise RuntimeError(PRIVATE)
        monkeypatch.setattr(recorder, 'record', broken)
    class Waiter:
        timeout_seconds = 0
        async def receive(self):return self.response
        def close(self):pass
    waiter = Waiter()
    def send(waiter, prepared, identifier):
        waiter.response = sign_message({'version': 1, 'timestamp': int(time.time()), 'request_id': identifier,
            'ok': True, 'result': {'status': 'ready'}}, prepared.secret)
    monkeypatch.setattr(relay, '_reserve', lambda *args: waiter)
    monkeypatch.setattr(relay, '_send', send)
    assert asyncio.run(relay.invoke_with_relay(db, settings, lambda: spec_for(app, package))) == {'status': 'ready'}
    if not recorder_broken:
        assert [row['span_id'] for row in recorder.snapshot()['records']] == [
            'application.admission', 'application.dispatch', 'application.response', 'application.completion']


@pytest.mark.parametrize('unsafe', [PRIVATE, {}, None])
def test_unknown_diagnostic_reason_is_not_an_exception_text_channel(unsafe):
    assert ApplicationGatewayError('unconfirmed', diagnostic_reason=unsafe).diagnostic_reason == 'operation_failed'
