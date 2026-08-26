from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401 - register complete model metadata
from backend.db.base import Base
from backend.db.user import User
from backend.routes.system_updates import router
from backend.services.system_updates import (
    CurrentRelease,
    UpdateCheckResponse,
)
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token


@pytest.fixture(autouse=True)
def use_test_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "test-only-key-with-at-least-32-bytes")


def make_client() -> tuple[TestClient, Session, str, str]:
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
        hashed_password=hash_password("test-password"),
        role="admin",
    )
    viewer = User(
        username="viewer",
        email="viewer@example.com",
        hashed_password=hash_password("test-password"),
        role="user",
    )
    db.add_all([admin, viewer])
    db.commit()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    return (
        TestClient(app),
        db,
        create_access_token(str(admin.id), {"role": "admin"}),
        create_access_token(str(viewer.id), {"role": "user"}),
    )


def response_payload(status: str = "not_checked") -> UpdateCheckResponse:
    return UpdateCheckResponse(
        status=status,
        message="Catalog state",
        repository="ldobranov/3mm",
        repository_url="https://github.com/ldobranov/3mm",
        architecture="aarch64",
        current=CurrentRelease(
            release_id="test-release",
            commit="a" * 40,
            metadata_available=True,
        ),
        update_available=None,
    )


def test_update_status_requires_an_administrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db, admin_token, viewer_token = make_client()
    monkeypatch.setattr(
        "backend.routes.system_updates.read_local_update_status",
        lambda _settings: response_payload(),
    )
    try:
        assert client.get("/api/v1/system-updates/status").status_code == 401
        assert (
            client.get(
                "/api/v1/system-updates/status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            ).status_code
            == 403
        )

        response = client.get(
            "/api/v1/system-updates/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "not_checked"
    finally:
        db.close()


def test_update_check_is_read_only_and_admin_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db, admin_token, viewer_token = make_client()
    monkeypatch.setattr(
        "backend.routes.system_updates.check_update_catalog",
        lambda _settings: response_payload("no_release"),
    )
    try:
        assert (
            client.post(
                "/api/v1/system-updates/check",
                headers={"Authorization": f"Bearer {viewer_token}"},
            ).status_code
            == 403
        )

        response = client.post(
            "/api/v1/system-updates/check",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "no_release"
    finally:
        db.close()
