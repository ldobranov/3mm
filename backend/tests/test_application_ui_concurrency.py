"""Ordinary HTTP UI operations: real SQLite/key interleavings, no device I/O.

The application response handoff is doubled, not the Core actor/build/native
trust checks. DELETE establishes a real pending writer; WAL stays concurrent.
"""
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
import os
import sqlite3
import threading
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, event, update
from sqlalchemy.orm import Session

from backend.config import ApplicationRuntimeSettings
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation, ApplicationPermissionGrant, ModulePackage
from backend.db.session import UserSession
from backend.applications.management import api as routes
from backend.applications.authority import management as authority
from backend.applications.runtime import invocations as relay
from backend.artifacts import compiled_ui
from backend.tests.test_application_ui_authority import (
    ui_app, managed_installed, source_subject, source_installed, adopt, identity,
)
from backend.storage.sessions import get_db
from components.system_runtime.application_transport import sign_message


pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Real POSIX key leases and file-backed SQLite')


@pytest.fixture
def ui_http(ui_app, tmp_path, monkeypatch):
    s = ui_app
    s.reviewed = adopt(s)
    with Session(s.engine) as db, db.begin():
        db.add(ApplicationPermissionGrant(application_installation_id=1, user_id=2, permission_id='records_manage'))
        db.execute(update(Installation).values(socket_path='/test-owned-no-host.sock'))
    keys = tmp_path / 'transport'
    keys.mkdir()
    secret = b's' * 32
    (keys / ('a' * 24 + '.key')).write_bytes(secret)
    settings = ApplicationRuntimeSettings(root=keys, key_root=keys, helper_socket=keys / 'unused.sock')
    monkeypatch.setattr(routes, 'get_settings', lambda: SimpleNamespace(applications=settings))
    s.sessions, s.sent = [], []
    s.after_send = lambda: None
    s.before_metadata = lambda: None
    s.leases = {'active': 0, 'maximum': 0}

    def checkout(*args):
        s.leases['active'] += 1
        s.leases['maximum'] = max(s.leases['maximum'], s.leases['active'])
    def checkin(*args):
        s.leases['active'] -= 1
    event.listen(s.engine, 'checkout', checkout)
    event.listen(s.engine, 'checkin', checkin)

    def assert_unleased(db=None):
        assert all(not session.in_transaction() for session in s.sessions), 'HTTP DB lease crossed IPC or host wait'
        if db is not None:
            assert not db.in_transaction()
        # A separate EX lock cannot succeed while this HTTP path holds SH.
        with s.keys.locked():
            pass

    original_complete = relay.complete_application_preparation
    def complete(db, *args, **kwargs):
        assert_unleased(db)
        s.before_metadata()
        return original_complete(db, *args, **kwargs)
    monkeypatch.setattr(relay, 'complete_application_preparation', complete)

    class Waiter:
        timeout_seconds = 0
        response = None
        async def receive(self):
            assert_unleased()
            return self.response
        def close(self):
            pass
    waiter = Waiter()
    def reserve(settings):
        assert_unleased()
        return waiter
    def send(waiter, prepared, request_id):
        assert_unleased()
        s.sent.append(request_id)
        s.after_send()
        waiter.response = sign_message({'version': 1, 'timestamp': int(time.time()),
            'request_id': request_id, 'ok': True, 'result': {}}, prepared.secret)
    monkeypatch.setattr(relay, '_reserve', reserve)
    monkeypatch.setattr(relay, '_send', send)

    app = FastAPI()
    from backend.system.diagnostics.failures import HttpFailureMiddleware, RecentHttpFailures
    s.failures = RecentHttpFailures()
    app.add_middleware(HttpFailureMiddleware, store=s.failures)
    app.include_router(routes.router)
    def session():
        with Session(s.engine) as db:
            s.sessions.append(db)
            yield db
    app.dependency_overrides[get_db] = session
    binding = {'host_version': 1, 'entrypoint_id': 'operations',
        'artifact_sha256': s.validated.sha256, 'built_ui_sha256': s.build.built_ui_sha256}
    with TestClient(app) as client:
        s.get_info = lambda: client.get(
            '/api/v1/application-extensions/' + s.validated.manifest.module_id + '/ui-host/operations',
            params={key: binding[key] for key in ('artifact_sha256', 'built_ui_sha256')},
            headers={'Authorization': 'Bearer ' + s.user_token})
        def invoke(**changes):
            return client.post('/api/v1/application-extensions/' + s.validated.manifest.module_id
                + '/operator/operations/pulse_ui', headers={'Authorization': 'Bearer ' + s.user_token},
                json={'payload': {}, 'idempotency_key': 'fixture-once', 'ui_context': binding, **changes})
        s.invoke = invoke
        try:
            yield s
        finally:
            event.remove(s.engine, 'checkout', checkout)
            event.remove(s.engine, 'checkin', checkin)


def test_ordinary_http_reuses_one_current_connection_and_releases_before_ipc(ui_http):
    s = ui_http
    response = s.invoke()
    assert response.status_code == 200, response.text
    assert response.json() == {}
    assert len(s.sent) == 1
    assert s.leases == {'active': 0, 'maximum': 1}
    for db in s.sessions:
        assert not db.in_transaction() and authority._UI_TRUST_SNAPSHOT not in db.info


@pytest.mark.parametrize('journal_mode', ['delete', 'wal'])
def test_ordinary_http_ui_reader_does_not_open_a_nested_reader_behind_sdk_writer(
    ui_http, monkeypatch, tmp_path, journal_mode,
):
    s = ui_http
    database = Path(s.engine.url.database).resolve()
    assert database.is_relative_to(tmp_path.resolve()), 'Only the private fixture DB may be configured'
    s.engine.dispose()
    with closing(sqlite3.connect(database, isolation_level=None)) as setup:
        assert setup.execute(f'PRAGMA journal_mode={journal_mode.upper()}').fetchone()[0] == journal_mode
    ready, committed = threading.Event(), threading.Event()
    errors, pending, intercepted = [], [], []

    def writer():
        try:
            with s.engine.connect() as connection:
                connection.exec_driver_sql('PRAGMA busy_timeout=1500')
                connection.commit()
                with connection.begin():
                    connection.execute(update(Installation).where(Installation.id == 1)
                        .values(updated_at=Installation.updated_at))
                    ready.set()
                committed.set()
        except Exception as exc:
            errors.append(type(exc).__name__)
        finally:
            ready.set()
    worker = threading.Thread(target=writer, daemon=True)
    original = compiled_ui.application_ui_artifact
    def concurrent_artifact(db, installation, validated, **kwargs):
        if not intercepted:
            intercepted.append(True)
            assert db.in_transaction()
            worker.start()
            assert ready.wait(3), 'Fixture writer did not reach commit'
            assert not errors, errors
            if journal_mode == 'delete':
                with closing(sqlite3.connect(database, timeout=0, isolation_level=None)) as probe:
                    deadline = time.monotonic() + 1
                    while time.monotonic() < deadline:
                        try:
                            probe.execute(f'SELECT id FROM "{Installation.__tablename__}" LIMIT 1').fetchall()
                        except sqlite3.OperationalError as exc:
                            if exc.sqlite_errorcode == sqlite3.SQLITE_BUSY:
                                pending.append(True)
                                break
                            raise
                        time.sleep(0.005)
                assert pending, 'Fixture did not establish a real pending commit'
            else:
                assert committed.wait(3), 'WAL writer could not commit alongside the reader'
        return original(db, installation, validated, **kwargs)
    monkeypatch.setattr(compiled_ui, 'application_ui_artifact', concurrent_artifact)
    try:
        response = s.invoke()
    finally:
        if worker.ident is not None:
            worker.join(timeout=4)
    assert not worker.is_alive() and not errors, errors
    assert committed.is_set() and bool(pending) == (journal_mode == 'delete')
    assert response.status_code == 200, response.text
    assert len(s.sent) == 1


@pytest.mark.parametrize('phase', ['metadata', 'response'])
@pytest.mark.parametrize('change', ['permission', 'session', 'native', 'recovery', 'epoch', 'package', 'build'])
def test_http_rechecks_current_policy_after_unleased_ipc_without_replay(ui_http, phase, change):
    s = ui_http
    def revoke():
        if change == 'native':
            s.manager.revoke_native_review(1, actor_token=s.token, request_id=identity(),
                native_review_id=s.reviewed['native_review_id'], expected_revision=s.reviewed['native_revision'])
        elif change == 'build':
            (s.build.path / 'assets/operations.mjs').write_text('changed in private fixture')
        else:
            with s.engine.begin() as db:
                if change == 'permission':
                    db.execute(delete(ApplicationPermissionGrant))
                elif change == 'session':
                    db.execute(update(UserSession).where(UserSession.id == 2).values(is_active=False))
                elif change == 'recovery':
                    db.execute(update(CoreAuthorityGuard).values(generation=identity()))
                elif change == 'package':
                    db.execute(update(ModulePackage).values(sha256='f' * 64))
                else:
                    db.execute(update(Installation).values(authority_epoch=identity()))
    if phase == 'metadata':
        s.before_metadata = revoke
    else:
        s.after_send = revoke
    response = s.invoke()
    assert response.status_code in {401, 403, 409}, response.text
    assert len(s.sent) == (0 if phase == 'metadata' else 1)
    if phase == 'response':
        assert 'unconfirmed' in response.json()['detail']
    assert s.leases['active'] == 0


@pytest.mark.parametrize('fault', ['session', 'transaction', 'installation', 'package', 'build', 'expired', 'forged'])
def test_http_code_proof_cannot_be_reused_outside_exact_boundary(ui_app, fault):
    s = ui_app
    adopt(s)
    with Session(s.engine, expire_on_commit=False) as db:
        with s.manager.invocation_transaction(db, 1):
            proof = db.info[authority._UI_TRUST_SNAPSHOT]
            installation = db.get(Installation, 1)
            assert compiled_ui.application_ui_artifact(db, installation, s.validated) is proof.artifact
            if fault == 'session':
                with Session(s.engine) as other:
                    other.info[authority._UI_TRUST_SNAPSHOT] = proof
                    with pytest.raises(compiled_ui.CompiledUiBuildError):
                        compiled_ui.application_ui_artifact(other, installation, s.validated)
            elif fault != 'expired':
                if fault == 'transaction':
                    db.rollback()
                    db.begin()
                elif fault == 'forged':
                    db.info[authority._UI_TRUST_SNAPSHOT] = True
                with pytest.raises(compiled_ui.CompiledUiBuildError):
                    compiled_ui.application_ui_artifact(db,
                        SimpleNamespace(id=2) if fault == 'installation' else installation,
                        SimpleNamespace(sha256='f' * 64) if fault == 'package' else s.validated,
                        expected_build='f' * 64 if fault == 'build' else s.build.built_ui_sha256)
        assert not proof.active and authority._UI_TRUST_SNAPSHOT not in db.info
        if fault == 'expired':
            db.info[authority._UI_TRUST_SNAPSHOT] = proof
            with pytest.raises(compiled_ui.CompiledUiBuildError):
                compiled_ui.application_ui_artifact(db, installation, s.validated)
