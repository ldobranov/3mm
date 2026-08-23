from datetime import UTC, datetime, timedelta

import backend.database  # noqa: F401
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.db.device import Device, DeviceCapabilityState, DeviceCredential
from backend.db.module import ModuleInstallation, ModulePackage
from backend.db.user import User
from backend.routes.device_capability_state import router
from backend.services.device_pairing import credential_secret_hash
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token


DEVICE_ID = "dev_0123456789abcdef0123456789abcdef"
CAPABILITY_ID = "gpio.digital.input"


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "test-only-key-with-at-least-32-bytes")


def test_device_reports_latest_enabled_capability_state_and_admin_reads_it():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    admin = User(username="admin-state", email="state@example.com", hashed_password=hash_password("test"), role="admin")
    device = Device(device_id=DEVICE_ID, display_name="Pi", role="standalone", protocol_version="1.0", approved_at=datetime.now(UTC))
    db.add_all([admin, device]); db.commit()
    db.add(DeviceCredential(device_id=device.id, credential_id="cred_0123456789abcdef0123456789abcdef", secret_hash=credential_secret_hash("x" * 32)))
    package = ModulePackage(
        module_id="org.3mm.mock-gpio", version="1.0.4", manifest={}, sha256="c" * 64,
        size_bytes=1, file_path="unused",
        registrations=[{"kind": "capability", "registration_id": CAPABILITY_ID}],
    )
    db.add(package); db.commit()
    db.add(ModuleInstallation(
        device_id=device.id, module_package_id=package.id, module_id=package.module_id,
        installed_version=package.version, desired_version=package.version,
        status="succeeded", enabled=True,
    )); db.commit()
    app = FastAPI(); app.include_router(router); app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    device_headers = {"Authorization": "Device cred_0123456789abcdef0123456789abcdef:" + "x" * 32}
    admin_headers = {"Authorization": f"Bearer {create_access_token(str(admin.id), {'role': 'admin'})}"}
    observed = datetime.now(UTC)
    payload = {
        "device_id": DEVICE_ID, "capability_id": CAPABILITY_ID,
        "values": {"gpio.input.1": True}, "observed_at": observed.isoformat(),
    }

    created = client.post(
        f"/api/v1/devices/{DEVICE_ID}/capabilities/{CAPABILITY_ID}/state",
        headers=device_headers, json=payload,
    )
    assert created.status_code == 200
    assert created.json()["values"] == {"gpio.input.1": True}

    older = {**payload, "values": {"gpio.input.1": False}, "observed_at": (observed - timedelta(seconds=5)).isoformat()}
    assert client.post(
        f"/api/v1/devices/{DEVICE_ID}/capabilities/{CAPABILITY_ID}/state",
        headers=device_headers, json=older,
    ).json()["values"] == {"gpio.input.1": True}

    first_received_at = datetime.fromisoformat(created.json()["received_at"])
    newer = {
        **payload,
        "values": {"gpio.input.1": False},
        "observed_at": (observed + timedelta(seconds=5)).isoformat(),
    }
    updated = client.post(
        f"/api/v1/devices/{DEVICE_ID}/capabilities/{CAPABILITY_ID}/state",
        headers=device_headers,
        json=newer,
    )
    assert updated.status_code == 200
    assert updated.json()["values"] == {"gpio.input.1": False}
    assert datetime.fromisoformat(updated.json()["received_at"]) >= first_received_at

    read = client.get(
        f"/api/v1/devices/{DEVICE_ID}/capabilities/{CAPABILITY_ID}/state",
        headers=admin_headers,
    )
    assert read.status_code == 200
    assert read.json()["values"]["gpio.input.1"] is False
    assert db.query(DeviceCapabilityState).count() == 1
    db.close(); engine.dispose()


def test_state_report_rejects_an_unregistered_capability():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    device = Device(device_id=DEVICE_ID, display_name="Pi", role="standalone", protocol_version="1.0", approved_at=datetime.now(UTC))
    db.add(device); db.commit()
    db.add(DeviceCredential(device_id=device.id, credential_id="cred_0123456789abcdef0123456789abcdef", secret_hash=credential_secret_hash("x" * 32))); db.commit()
    app = FastAPI(); app.include_router(router); app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    response = client.post(
        f"/api/v1/devices/{DEVICE_ID}/capabilities/unknown.value/state",
        headers={"Authorization": "Device cred_0123456789abcdef0123456789abcdef:" + "x" * 32},
        json={
            "device_id": DEVICE_ID, "capability_id": "unknown.value",
            "values": {"value": True}, "observed_at": datetime.now(UTC).isoformat(),
        },
    )
    assert response.status_code == 409
    db.close(); engine.dispose()
