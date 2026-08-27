import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401
from backend.db.base import Base
from backend.db.user import User
from backend.routes.user import router
from backend.utils import jwt_utils
from backend.utils.auth import hash_password, verify_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token


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
    operator = User(
        username="operator",
        email="operator@example.com",
        hashed_password=hash_password("operator-password"),
        role="user",
    )
    db.add_all([admin, operator])
    db.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api/user")
    app.dependency_overrides[get_db] = lambda: db
    return (
        TestClient(app),
        db,
        admin,
        operator,
        create_access_token(str(admin.id), {"role": "admin"}),
        create_access_token(str(operator.id), {"role": "user"}),
    )


def test_admin_can_create_user_with_selected_role() -> None:
    client, db, _admin, _operator, admin_token, viewer_token = make_client()
    payload = {
        "username": "maintainer",
        "email": "maintainer@example.com",
        "password": "maintainer-password",
        "role": "admin",
    }
    try:
        forbidden = client.post(
            "/api/user/create",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json=payload,
        )
        created = client.post(
            "/api/user/create",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=payload,
        )

        saved = db.query(User).filter(User.email == payload["email"]).one()
        assert forbidden.status_code == 403
        assert created.status_code == 200
        assert saved.role == "admin"
        assert verify_password(payload["password"], saved.hashed_password)
    finally:
        db.close()


def test_admin_can_change_another_users_password() -> None:
    client, db, _admin, operator, admin_token, _viewer_token = make_client()
    try:
        updated = client.put(
            "/api/user/update",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "id": operator.id,
                "username": operator.username,
                "email": operator.email,
                "role": "user",
                "password": "changed-password",
            },
        )

        db.refresh(operator)
        assert updated.status_code == 200
        assert verify_password("changed-password", operator.hashed_password)
    finally:
        db.close()


def test_last_administrator_cannot_be_demoted_or_self_deleted() -> None:
    client, db, admin, _operator, admin_token, _viewer_token = make_client()
    try:
        demoted = client.put(
            "/api/user/update",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "id": admin.id,
                "username": admin.username,
                "email": admin.email,
                "role": "user",
            },
        )
        deleted = client.delete(
            f"/api/user/delete/{admin.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        db.refresh(admin)
        assert demoted.status_code == 400
        assert demoted.json()["detail"] == "Cannot demote the last administrator"
        assert deleted.status_code == 400
        assert deleted.json()["detail"] == "Cannot delete your own account"
        assert admin.role == "admin"
    finally:
        db.close()
