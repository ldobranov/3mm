from datetime import datetime, timezone

import backend.database  # noqa: F401
import pytest
from backend.db.base import Base
from backend.db.device import Device, DeviceState
from backend.db.user import User
from backend.routes.device_state import router
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

DEVICE_ID = "dev_0123456789abcdef0123456789abcdef"

@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "test-only-key-with-at-least-32-bytes")

def test_admin_updates_desired_state_with_revision_check() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    admin = User(username="admin", email="admin@example.com", hashed_password=hash_password("test"), role="admin")
    device = Device(device_id=DEVICE_ID, display_name="pi", role="node", protocol_version="1.0", approved_at=datetime.now(timezone.utc))
    db.add_all([admin, device]); db.commit()
    app = FastAPI(); app.include_router(router); app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token(str(admin.id), {'role': 'admin'})}"}

    updated = client.put(f"/api/v1/devices/{DEVICE_ID}/desired-state", headers=headers, json={"expected_revision": 0, "state": {"inventory_generation": 1}})
    assert updated.status_code == 200
    assert updated.json()["revision"] == 1
    conflict = client.put(f"/api/v1/devices/{DEVICE_ID}/desired-state", headers=headers, json={"expected_revision": 0, "state": {}})
    assert conflict.status_code == 409
    summary = client.get(f"/api/v1/devices/{DEVICE_ID}/state", headers=headers).json()
    assert summary["synchronized"] is False
    db.close(); engine.dispose()

def test_state_summary_restores_utc_timezone_from_sqlite() -> None:
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
        hashed_password=hash_password("test"),
        role="admin",
    )
    device = Device(
        device_id=DEVICE_ID,
        display_name="pi",
        role="node",
        protocol_version="1.0",
        approved_at=datetime.now(timezone.utc),
    )
    db.add_all([admin, device])
    db.commit()
    db.refresh(device)

    db.add(
        DeviceState(
            device_id=device.id,
            reported_at=datetime(2026, 10, 1, 11, 13, 43),
        )
    )
    db.commit()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    headers = {
        "Authorization": (
            f"Bearer {create_access_token(str(admin.id), {'role': 'admin'})}"
        )
    }

    response = client.get(
        f"/api/v1/devices/{DEVICE_ID}/state",
        headers=headers,
    )

    assert response.status_code == 200
    reported_at = response.json()["reported_at"]
    parsed = datetime.fromisoformat(reported_at.replace("Z", "+00:00"))
    assert parsed.utcoffset() == timezone.utc.utcoffset(parsed)

    db.close()
    engine.dispose()
