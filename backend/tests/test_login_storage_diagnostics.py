"""Real SQLite contention is classified without collecting login or SQL data."""
import json
import sqlite3
from contextlib import closing

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import backend.database  # registers all tables
from backend.accounts import tokens
from backend.accounts.passwords import hash_password
from backend.accounts.users_api import router
from backend.db.base import Base
from backend.db.session import UserSession
from backend.db.audit_log import AuditLog
from backend.db.user import User
from backend.storage.sessions import get_db
from backend.system.diagnostics import failures
from backend.system.diagnostics.cases import build_cases


def test_login_during_actual_write_lock_is_private_and_recovers(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(tokens, 'SECRET_KEY', 'local-only-test-key-at-least-32-bytes')
    username, email, password = 'private-fixture-user', 'private@example.test', 'private-fixture-password'
    path = tmp_path / 'sessions.db'
    engine = create_engine('sqlite:///' + path.as_posix(), connect_args={'timeout': .05})
    Base.metadata.create_all(engine)
    with Session(engine) as db, db.begin():
        db.add(User(username=username, email=email, hashed_password=hash_password(password), role='user'))
    def database():
        with Session(engine) as db:
            yield db
    store = failures.RecentHttpFailures()
    app = FastAPI()
    app.include_router(router, prefix='/api/user')
    app.dependency_overrides[get_db] = database
    app.add_middleware(failures.HttpFailureMiddleware, store=store)
    try:
        with TestClient(app) as client:
            with closing(sqlite3.connect(path)) as writer:
                writer.execute('BEGIN IMMEDIATE')
                denied = client.post('/api/user/login', json={'email': email, 'password': password})
                assert denied.status_code == 503 and denied.headers['Retry-After'] == '2'
                assert denied.json() == {'detail': 'Login temporarily unavailable: storage is busy'}
                writer.rollback()
            cases = build_cases(store.snapshot(), {}, {}, trace_id=denied.headers['x-3mm-trace-id'])
            case, = cases['cases']
            assert case['operation'] == 'account.login' and not case['automatic_replay_allowed']
            assert (case['evidence']['stage'], case['evidence']['reason']) == ('login.session_write', 'database_busy')
            assert case['next_check'] == 'inspect_login_storage'
            # Previously the offline reader rejected this valid Core export.
            # Exercise the wire bytes; neither tool should need the failed DB.
            from tools.diagnostics import parse_bundle, explain
            offline, = explain(parse_bundle(json.dumps(cases).encode()))['cases']
            assert (offline['summary'], offline['next_check'], offline['case_id']) == (
                case['summary'], case['next_check'], denied.headers['x-3mm-trace-id'])
            with Session(engine) as db:
                assert db.query(UserSession).count() == 0
                assert db.query(AuditLog).count() == 0
            # Also exercise a failure *after* the session row has been flushed.
            # An inaccessible audit table must not leave an unreported valid login.
            with closing(sqlite3.connect(path)) as writer:
                writer.execute("""CREATE TRIGGER reject_audit BEFORE INSERT ON audit_logs
                                BEGIN SELECT RAISE(ABORT,'private audit failure'); END""")
                writer.commit()
            rejected = client.post('/api/user/login', json={'email': email, 'password': password})
            assert rejected.status_code == 500 and 'token' not in rejected.json()
            failed_audit, = build_cases(store.snapshot(), {}, {}, trace_id=rejected.headers['x-3mm-trace-id'])['cases']
            assert (failed_audit['evidence']['stage'], failed_audit['evidence']['reason']) == ('login.audit_write', 'database_constraint')
            with Session(engine) as db:
                assert db.query(UserSession).count() == db.query(AuditLog).count() == 0
            with closing(sqlite3.connect(path)) as writer:
                writer.execute('DROP TRIGGER reject_audit')
                writer.commit()
            ok = client.post('/api/user/login', json={'email': email, 'password': password})
            assert ok.status_code == 200
            with Session(engine) as db:
                assert db.query(UserSession).one().id == db.query(AuditLog).filter_by(action='LOGIN').one().session_id
            private = (email, username, password, ok.json()['token'], 'INSERT INTO', 'pending-')
            assert all(x not in json.dumps(cases) + caplog.text for x in private)
    finally:
        engine.dispose()


def test_database_classification_does_not_guess_from_message():
    assert failures.note_database_error('login.session_write', sqlite3.OperationalError('database is locked')) == 'database_operation_failed'
    err = sqlite3.OperationalError('private details')
    err.sqlite_errorcode = sqlite3.SQLITE_READONLY | (2 << 8)
    assert failures.note_database_error('login.audit_write', err) == 'database_read_only'
