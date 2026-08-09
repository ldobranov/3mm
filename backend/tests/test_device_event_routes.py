from datetime import datetime, timezone
import backend.database  # noqa: F401
import pytest
from backend.db.base import Base
from backend.db.device import Device, DeviceCredential, DeviceEvent
from backend.db.user import User
from backend.routes.device_events import router
from backend.services.device_pairing import credential_secret_hash
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

DEVICE_ID="dev_0123456789abcdef0123456789abcdef"


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "test-only-key-with-at-least-32-bytes")

def test_authenticated_event_is_persisted_once_when_replayed():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool); Base.metadata.create_all(engine); db=Session(engine)
    admin=User(username="admin",email="admin@example.com",hashed_password=hash_password("test-password"),role="admin")
    device=Device(device_id=DEVICE_ID,display_name="test",role="node",protocol_version="1.0",approved_at=datetime.now(timezone.utc)); db.add(device); db.commit()
    db.add(admin); db.commit()
    db.add(DeviceCredential(device_id=device.id,credential_id="cred_0123456789abcdef0123456789abcdef",secret_hash=credential_secret_hash("x"*32))); db.commit()
    app=FastAPI(); app.include_router(router); app.dependency_overrides[get_db]=lambda:db; client=TestClient(app)
    headers={"Authorization":"Device cred_0123456789abcdef0123456789abcdef:"+"x"*32}
    payload={"event_id":"evt_0123456789abcdef0123456789abcdef","device_id":DEVICE_ID,"event_type":"gpio.input.changed","payload":{"value":True},"occurred_at":datetime.now(timezone.utc).isoformat()}
    assert client.post(f"/api/v1/devices/{DEVICE_ID}/events",headers=headers,json=payload).json()["duplicate"] is False
    assert client.post(f"/api/v1/devices/{DEVICE_ID}/events",headers=headers,json=payload).json()["duplicate"] is True
    assert len(list(db.scalars(select(DeviceEvent))))==1
    admin_headers={"Authorization":f"Bearer {create_access_token(str(admin.id),{'role':'admin'})}"}
    listed=client.get(f"/api/v1/devices/{DEVICE_ID}/events",headers=admin_headers)
    assert listed.status_code==200
    assert listed.json()[0]["device_id"]==DEVICE_ID
    assert listed.json()[0]["event_type"]=="gpio.input.changed"
    db.close(); engine.dispose()
