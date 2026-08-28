from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401
from backend.db.audit_log import AuditLog
from backend.db.base import Base
from backend.db.user import User
from backend.routes import system_control
from backend.routes.system_control import router
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token


@pytest.fixture(autouse=True)
def use_test_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "test-only-key-with-at-least-32-bytes")


def make_client(tmp_path, monkeypatch):
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
    monkeypatch.setattr(
        system_control,
        "get_settings",
        lambda: SimpleNamespace(
            updates=SimpleNamespace(helper_socket=tmp_path / "helper.sock")
        ),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    return (
        TestClient(app),
        db,
        create_access_token(str(admin.id), {"role": "admin"}),
        create_access_token(str(viewer.id), {"role": "user"}),
    )


def test_system_actions_are_admin_only_and_require_exact_confirmation(
    tmp_path, monkeypatch
) -> None:
    client, db, admin_token, viewer_token = make_client(tmp_path, monkeypatch)
    calls: list[tuple[str, int]] = []

    class FakeClient:
        def __init__(self, _socket):
            pass

        def request_system_action(self, action: str, user_id: int) -> None:
            calls.append((action, user_id))

    monkeypatch.setattr(system_control, "UpdateHelperClient", FakeClient)
    try:
        assert client.post(
            "/api/v1/system-control/restart",
            json={"confirmation": "RESTART"},
        ).status_code == 401
        assert client.post(
            "/api/v1/system-control/restart",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={"confirmation": "RESTART"},
        ).status_code == 403
        assert client.post(
            "/api/v1/system-control/factory-reset",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"confirmation": "yes"},
        ).status_code == 409

        restarted = client.post(
            "/api/v1/system-control/restart",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"confirmation": "RESTART"},
        )
        reset = client.post(
            "/api/v1/system-control/factory-reset",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"confirmation": "FACTORY RESET"},
        )

        assert restarted.status_code == 202
        assert reset.status_code == 202
        assert calls == [
            ("restart_device", 1),
            ("factory_reset", 1),
        ]
        assert [row.action for row in db.scalars(select(AuditLog)).all()] == [
            "DEVICE_RESTART_REQUESTED",
            "FACTORY_RESET_REQUESTED",
        ]
    finally:
        db.close()
