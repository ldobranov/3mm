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
from backend.system import control as system_control
from backend.system.control import router
from backend.accounts import tokens as jwt_utils
from backend.accounts.passwords import hash_password
from backend.storage.sessions import get_db
from backend.accounts.tokens import create_access_token


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


@pytest.mark.parametrize("route,confirmation", [
    ("restart", "RESTART"), ("factory-reset", "FACTORY RESET"),
])
@pytest.mark.parametrize("revocation", ["demoted", "blocked", "token_version"])
def test_system_actions_require_current_admin_before_helper_or_audit(
    tmp_path, monkeypatch, route, confirmation, revocation,
):
    client, db, token, _viewer_token = make_client(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(system_control, "UpdateHelperClient", lambda *_: calls.append("helper"))
    try:
        admin = db.get(User, 1)
        if revocation == "demoted":
            admin.role = "user"
        elif revocation == "blocked":
            admin.is_blocked = True
        else:
            admin.token_version += 1
        db.commit()
        response = client.post(
            "/api/v1/system-control/" + route,
            headers={"Authorization": "Bearer " + token},
            json={"confirmation": confirmation},
        )
        assert response.status_code == (403 if revocation == "demoted" else 401)
        assert calls == []
        assert db.scalars(select(AuditLog)).first() is None
    finally:
        db.close()


@pytest.mark.parametrize("route,confirmation", [
    ("restart", "RESTART"), ("factory-reset", "FACTORY RESET"),
])
@pytest.mark.parametrize("failure", [system_control.UpdateHelperError, ValueError])
def test_helper_refusal_does_not_report_queued_or_write_success_audit(
    tmp_path, monkeypatch, route, confirmation, failure,
):
    client, db, token, _viewer_token = make_client(tmp_path, monkeypatch)
    calls = []

    class UnavailableHelper:
        def __init__(self, _socket):
            pass

        def request_system_action(self, action, user_id):
            calls.append((action, user_id))
            raise failure("helper unavailable")

    monkeypatch.setattr(system_control, "UpdateHelperClient", UnavailableHelper)
    try:
        response = client.post(
            "/api/v1/system-control/" + route,
            headers={"Authorization": "Bearer " + token},
            json={"confirmation": confirmation},
        )
        assert response.status_code == 409
        assert response.json() == {"detail": "helper unavailable"}
        assert calls == [("restart_device" if route == "restart" else "factory_reset", 1)]
        assert db.scalars(select(AuditLog)).first() is None
    finally:
        db.close()
