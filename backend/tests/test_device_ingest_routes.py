from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401 - register complete model metadata
from backend.db.base import Base
from backend.db.device import Device, DeviceCredential, DeviceHeartbeat
from backend.routes.device_ingest import router
from backend.services.device_pairing import credential_secret_hash
from backend.utils.db_utils import get_db

DEVICE_ID = "dev_0123456789abcdef0123456789abcdef"
CREDENTIAL_ID = "cred_0123456789abcdef0123456789abcdef"
CREDENTIAL_SECRET = "test-device-secret-with-sufficient-entropy"


def make_client() -> tuple[TestClient, Session, DeviceCredential]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    device = Device(
        device_id=DEVICE_ID,
        display_name="Test Agent",
        role="node",
        protocol_version="1.0",
        approved_at=datetime.now(timezone.utc),
    )
    credential = DeviceCredential(
        credential_id=CREDENTIAL_ID,
        secret_hash=credential_secret_hash(CREDENTIAL_SECRET),
    )
    device.credentials.append(credential)
    db.add(device)
    db.commit()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app), db, credential


def heartbeat_payload(device_id: str = DEVICE_ID) -> dict:
    return {
        "protocol_version": "1.0",
        "device_id": device_id,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": 123.5,
        "status": "ready",
    }


def device_headers(secret: str = CREDENTIAL_SECRET) -> dict[str, str]:
    return {"Authorization": f"Device {CREDENTIAL_ID}:{secret}"}


def test_valid_device_credential_submits_heartbeat() -> None:
    client, db, credential = make_client()
    try:
        response = client.post(
            f"/api/v1/devices/{DEVICE_ID}/heartbeat",
            json=heartbeat_payload(),
            headers=device_headers(),
        )

        assert response.status_code == 202
        assert response.json() == {"status": "accepted"}
        assert db.query(DeviceHeartbeat).count() == 1
        db.refresh(credential)
        assert credential.last_used_at is not None
    finally:
        db.close()


def test_missing_wrong_and_revoked_credentials_are_rejected() -> None:
    client, db, credential = make_client()
    try:
        endpoint = f"/api/v1/devices/{DEVICE_ID}/heartbeat"
        assert client.post(endpoint, json=heartbeat_payload()).status_code == 401
        wrong = client.post(
            endpoint,
            json=heartbeat_payload(),
            headers=device_headers("wrong-secret"),
        )
        assert wrong.status_code == 401

        credential.revoked_at = datetime.now(timezone.utc)
        db.commit()
        revoked = client.post(
            endpoint,
            json=heartbeat_payload(),
            headers=device_headers(),
        )
        assert revoked.status_code == 401
        assert db.query(DeviceHeartbeat).count() == 0
    finally:
        db.close()


def test_credential_path_and_payload_identity_must_match() -> None:
    client, db, _ = make_client()
    try:
        other_device_id = "dev_ffffffffffffffffffffffffffffffff"
        wrong_path = client.post(
            f"/api/v1/devices/{other_device_id}/heartbeat",
            json=heartbeat_payload(other_device_id),
            headers=device_headers(),
        )
        wrong_payload = client.post(
            f"/api/v1/devices/{DEVICE_ID}/heartbeat",
            json=heartbeat_payload(other_device_id),
            headers=device_headers(),
        )

        assert wrong_path.status_code == 403
        assert wrong_payload.status_code == 403
        assert db.query(DeviceHeartbeat).count() == 0
    finally:
        db.close()
