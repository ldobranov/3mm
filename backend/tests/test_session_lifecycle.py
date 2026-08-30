from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401
from backend.db.base import Base
from backend.db.session import Session as UserSession
from backend.db.settings import Settings
from backend.db.user import User
from backend.routes.auth_refresh import router as refresh_router
from backend.routes.user import router as user_router
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token, decode_token


@pytest.fixture(autouse=True)
def use_test_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "test-only-key-with-at-least-32-bytes")


def make_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    admin = User(
        username="admin",
        email="admin@example.com",
        hashed_password=hash_password("admin-password"),
        role="admin",
    )
    viewer = User(
        username="viewer",
        email="viewer@example.com",
        hashed_password=hash_password("viewer-password"),
        role="user",
    )
    db.add_all([admin, viewer])
    db.commit()

    app = FastAPI()
    app.include_router(user_router, prefix="/api/user")
    app.include_router(refresh_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app), db, admin, viewer


def login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/user/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "3mm-test-browser"},
    )
    assert response.status_code == 200
    return response.json()["token"]


def test_login_uses_configured_session_duration_and_stable_session_id() -> None:
    client, db, admin, _viewer = make_client()
    try:
        db.add(Settings(key="session_duration_hours", value="24"))
        db.commit()
        before = datetime.utcnow()

        token = login(client, admin.email, "admin-password")
        claims = decode_token(token)
        session = db.query(UserSession).filter(UserSession.user_id == admin.id).one()

        assert claims["sid"] == session.id
        assert session.token == token
        assert before + timedelta(hours=23, minutes=59) <= session.expires_at
        assert session.expires_at <= before + timedelta(hours=24, minutes=1)
    finally:
        db.close()


def test_expired_access_token_refreshes_while_persistent_session_is_active() -> None:
    client, db, admin, _viewer = make_client()
    try:
        token = login(client, admin.email, "admin-password")
        session = db.query(UserSession).filter(UserSession.user_id == admin.id).one()
        expired = create_access_token(
            str(admin.id),
            {"role": "admin", "sid": session.id},
            expires_delta=timedelta(seconds=-1),
        )
        session.token = expired
        db.commit()

        response = client.post(
            "/api/user/refresh",
            headers={"Authorization": f"Bearer {expired}"},
        )

        assert response.status_code == 200
        refreshed = response.json()["token"]
        db.refresh(session)
        assert session.token == refreshed
        assert decode_token(refreshed)["sid"] == session.id
    finally:
        db.close()


def test_refresh_rejects_revoked_or_expired_persistent_session() -> None:
    client, db, admin, _viewer = make_client()
    try:
        token = login(client, admin.email, "admin-password")
        session = db.query(UserSession).filter(UserSession.user_id == admin.id).one()
        session.is_active = False
        db.commit()
        revoked = client.post(
            "/api/user/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )

        session.is_active = True
        session.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
        expired = client.post(
            "/api/user/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert revoked.status_code == 401
        assert expired.status_code == 401
    finally:
        db.close()


def test_only_admin_can_change_bounded_session_duration() -> None:
    client, db, admin, viewer = make_client()
    try:
        admin_token = create_access_token(str(admin.id), {"role": "admin"})
        viewer_token = create_access_token(str(viewer.id), {"role": "user"})

        forbidden = client.put(
            "/api/admin/session-settings",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={"duration_hours": 48},
        )
        invalid = client.put(
            "/api/admin/session-settings",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"duration_hours": 721},
        )
        saved = client.put(
            "/api/admin/session-settings",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"duration_hours": 48},
        )
        loaded = client.get(
            "/api/admin/session-settings",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert forbidden.status_code == 403
        assert invalid.status_code == 422
        assert saved.status_code == 200
        assert saved.json()["duration_hours"] == 48
        assert loaded.json()["duration_hours"] == 48
    finally:
        db.close()
