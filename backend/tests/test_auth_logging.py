"""G4: fixture secrets must not enter authentication logs, even at DEBUG."""

import ast
import inspect
import logging
from datetime import timedelta

import backend.database  # noqa: F401 - register existing ORM relationships
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.db.user import User
from backend.routes import user as routes
from backend.utils import auth_dep, jwt_utils
from backend.utils.db_utils import get_db

PASSWORD = "fixture-only-password-do-not-log"
WRONG_PASSWORD = "fixture-only-wrong-password-do-not-log"
BAD_TOKEN = "fixture-only-invalid-bearer-do-not-log"
CLAIM_MARKER = "fixture-only-private-claim-do-not-log"
IDENTITY = {
    "username": "fixture-private-user",
    "email": "fixture-private@example.invalid",
}


@pytest.fixture
def auth_logging(monkeypatch, caplog):
    monkeypatch.setattr(
        jwt_utils, "SECRET_KEY", "fixture-only-signing-key-at-least-32-bytes"
    )
    caplog.set_level(logging.DEBUG, logger=routes.__name__)
    caplog.set_level(logging.DEBUG, logger=auth_dep.__name__)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Base.metadata.tables[name]
            for name in ("users", "sessions", "audit_logs", "settings")
        ],
    )
    with Session(engine) as db:
        app = FastAPI()
        app.include_router(routes.router, prefix="/api/user")
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app) as client:
            yield client, db, caplog
    engine.dispose()


def assert_no_secrets(caplog, *extra):
    records = [
        record
        for record in caplog.records
        if record.name in {routes.__name__, auth_dep.__name__}
    ]
    assert records, "The check must actually exercise authentication logging"
    text = "\n".join(record.getMessage() for record in records)
    for secret in (
        PASSWORD,
        WRONG_PASSWORD,
        BAD_TOKEN,
        CLAIM_MARKER,
        *IDENTITY.values(),
        *extra,
    ):
        assert secret not in text
    assert all(
        record.exc_info is None and record.stack_info is None for record in records
    )


def register(client):
    return client.post("/api/user/register", json={**IDENTITY, "password": PASSWORD})


def login(client, password=PASSWORD, email=IDENTITY["email"]):
    return client.post("/api/user/login", json={"email": email, "password": password})


def test_successful_registration_login_and_profile_never_log_credentials(auth_logging):
    client, db, caplog = auth_logging
    assert register(client).status_code == 200
    saved = db.query(User).one()
    response = login(client)
    assert response.status_code == 200
    token = response.json()["token"]
    authorization = f"Bearer {token}"
    profile = client.get("/api/user/profile", headers={"Authorization": authorization})
    assert profile.status_code == 200 and profile.json()["email"] == IDENTITY["email"]
    assert_no_secrets(caplog, token, authorization, saved.hashed_password)
    assert any(record.levelno == logging.DEBUG for record in caplog.records)


def test_duplicate_registration_and_failed_logins_do_not_log_secrets(auth_logging):
    client, db, caplog = auth_logging
    assert register(client).status_code == 200
    assert register(client).status_code == 400
    assert login(client, WRONG_PASSWORD).status_code == 400
    assert login(client, email="missing-private@example.invalid").status_code == 404
    saved = db.query(User).one()
    saved.is_blocked = True
    db.commit()
    assert login(client).status_code == 403
    # Framework/body validation failure must not introduce custom payload logging.
    assert (
        client.post("/api/user/login", json={"email": IDENTITY["email"]}).status_code
        == 422
    )
    assert_no_secrets(caplog, saved.hashed_password, "missing-private@example.invalid")


def test_profile_expired_invalid_and_revoked_token_logs_are_safe(
    auth_logging, monkeypatch
):
    client, db, caplog = auth_logging
    assert register(client).status_code == 200
    saved = db.query(User).one()
    expired = jwt_utils.create_access_token(
        str(saved.id),
        {"private_fixture": CLAIM_MARKER},
        expires_delta=timedelta(minutes=-1),
    )
    valid = jwt_utils.create_access_token(
        str(saved.id), {"private_fixture": CLAIM_MARKER}
    )
    missing = jwt_utils.create_access_token("999", {"private_fixture": CLAIM_MARKER})
    assert (
        client.get(
            "/api/user/profile", headers={"Authorization": f"Bearer {valid}"}
        ).status_code
        == 200
    )
    # Preserve legacy profile error wrapping: this task does not change auth statuses.
    monkeypatch.setattr(routes, "token_blacklist", {valid})
    for authorization in (
        f"Bearer {BAD_TOKEN}",
        f"Bearer {expired}",
        f"Bearer {valid}",
        f"Bearer {missing}",
        "Basic " + BAD_TOKEN,
    ):
        assert (
            client.get(
                "/api/user/profile", headers={"Authorization": authorization}
            ).status_code
            >= 400
        )
    assert_no_secrets(caplog, expired, valid, missing, saved.hashed_password)


@pytest.mark.parametrize("stage", ["registration", "login", "profile", "optional_auth"])
def test_exception_text_cannot_leak_bound_credentials(auth_logging, monkeypatch, stage):
    from sqlalchemy.exc import StatementError

    client, db, caplog = auth_logging
    assert register(client).status_code == 200
    token = login(client).json()["token"]
    password_hash = db.query(User).one().hashed_password
    # Real SQLAlchemy formatting includes bound parameters, which may be secrets.
    failure = StatementError(
        "fixture database failure",
        "fixture statement",
        {"password": PASSWORD, "token": token, "hash": password_hash},
        RuntimeError(CLAIM_MARKER),
    )

    def fail(*_args, **_kwargs):
        raise failure

    if stage == "registration":
        monkeypatch.setattr(routes, "hash_password", fail)
        assert register(client).status_code == 500
    elif stage == "login":
        monkeypatch.setattr(db, "commit", fail)
        assert login(client).status_code == 500
    elif stage == "profile":
        monkeypatch.setattr(routes, "decode_token", fail)
        assert (
            client.get(
                "/api/user/profile", headers={"Authorization": f"Bearer {token}"}
            ).status_code
            >= 400
        )
    else:
        monkeypatch.setattr(auth_dep, "decode_token", fail)
        assert auth_dep.try_get_claims("Bearer " + token) is None
    assert_no_secrets(caplog, token, password_hash)
    assert any(record.levelno >= logging.WARNING for record in caplog.records)


def test_auth_logger_calls_are_literal_events_with_only_exception_type_metadata():
    # Guard error/management branches too, without a large endpoint test matrix.
    for module in (routes, auth_dep):
        for call in ast.walk(ast.parse(inspect.getsource(module))):
            if not isinstance(call, ast.Call) or not isinstance(
                call.func, ast.Attribute
            ):
                continue
            if (
                not isinstance(call.func.value, ast.Name)
                or call.func.value.id != "logger"
            ):
                continue
            assert call.func.attr in {"debug", "info", "warning", "error"}
            assert isinstance(call.args[0], ast.Constant) and isinstance(
                call.args[0].value, str
            )
            assert not call.keywords  # No raw objects, exc_info, extra or traceback.
            for argument in call.args[1:]:
                assert (
                    isinstance(argument, ast.Attribute) and argument.attr == "__name__"
                )
                assert isinstance(argument.value, ast.Call)
                assert (
                    isinstance(argument.value.func, ast.Name)
                    and argument.value.func.id == "type"
                )
