import backend.database  # noqa: F401 - register all model metadata
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.db.user import User
from backend.routes.application_events import router
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token


def test_event_broker_observability_is_admin_only(monkeypatch):
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "test-only-key-with-at-least-32-bytes")
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
    db.add_all((admin, viewer))
    db.commit()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    viewer_token = create_access_token(str(viewer.id), {"role": "user"})
    admin_token = create_access_token(str(admin.id), {"role": "admin"})

    assert client.get("/api/v1/application-events/status").status_code == 401
    assert client.get(
        "/api/v1/application-events/status",
        headers={"Authorization": f"Bearer {viewer_token}"},
    ).status_code == 403
    response = client.get(
        "/api/v1/application-events/status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"subscriptions": []}
    db.close()
    engine.dispose()
