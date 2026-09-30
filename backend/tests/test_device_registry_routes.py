from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401 - register complete model metadata
from backend.db.base import Base
from backend.db.device import Device, DeviceHeartbeat, DeviceInventorySnapshot
from backend.db.user import User
from backend.db.module import ModulePackage, ModuleInstallation
from backend.routes.device_registry import router
from backend.services.device_registry import is_device_online
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


def test_online_policy_uses_heartbeat_window_and_revocation() -> None:
    now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    threshold = timedelta(seconds=90)

    assert is_device_online(
        last_seen_at=now - timedelta(seconds=89),
        now=now,
        offline_after=threshold,
    )
    assert not is_device_online(
        last_seen_at=now - timedelta(seconds=91),
        now=now,
        offline_after=threshold,
    )
    assert not is_device_online(
        last_seen_at=now,
        now=now,
        offline_after=threshold,
        revoked_at=now,
    )


def test_admin_lists_latest_real_inventory_and_derived_status() -> None:
    client, db, admin_token, viewer_token = make_client()
    try:
        now = datetime.now(timezone.utc)
        device = Device(
            device_id="dev_0123456789abcdef0123456789abcdef",
            display_name="Workshop Pi",
            role="node",
            protocol_version="1.0",
            approved_at=now,
        )
        device.heartbeats.append(
            DeviceHeartbeat(
                protocol_version="1.0",
                payload={"status": "ready"},
                received_at=now - timedelta(seconds=5),
            )
        )
        device.inventory_snapshots.extend(
            [
                DeviceInventorySnapshot(
                    inventory={"hostname": "old-name"},
                    received_at=now - timedelta(minutes=5),
                ),
                DeviceInventorySnapshot(
                    inventory={"hostname": "rasp-3mm"},
                    received_at=now,
                ),
            ]
        )
        db.add(device)
        db.commit()

        assert client.get("/api/v1/devices").status_code == 401
        forbidden = client.get(
            "/api/v1/devices",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert forbidden.status_code == 403

        response = client.get(
            "/api/v1/devices",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["total"] == 1
        item = response.json()["items"][0]
        assert item["device_id"] == device.device_id
        assert item["online"] is True
        assert item["latest_inventory"]["hostname"] == "rasp-3mm"
    finally:
        db.close()

def test_admin_reads_device_detail_with_modules() -> None:
    client, db, admin_token, viewer_token = make_client()

    try:
        now = datetime.now(timezone.utc)

        device = Device(
            device_id="dev_0123456789abcdef0123456789abcdef",
            display_name="Reader Node",
            role="node",
            protocol_version="1.0",
            approved_at=now,
        )

        device.heartbeats.append(
            DeviceHeartbeat(
                protocol_version="1.0",
                payload={"status": "ready"},
                received_at=now,
            )
        )

        device.inventory_snapshots.append(
            DeviceInventorySnapshot(
                inventory={
                    "hostname": "reader-node",
                    "architecture": "armv6l",
                },
                received_at=now,
            )
        )

        package = ModulePackage(
            module_id="org.3mm.example",
            version="1.2.0",
            manifest={},
            sha256="a" * 64,
            size_bytes=123,
            file_path="/tmp/example.zip",
            registrations=[],
        )

        db.add_all([device, package])
        db.flush()

        installation = ModuleInstallation(
            device_id=device.id,
            module_package_id=package.id,
            module_id="org.3mm.example",
            desired_version="1.2.0",
            installed_version="1.1.0",
            status="succeeded",
            enabled=True,
            data_retained=True,
        )

        db.add(installation)
        db.commit()

        endpoint = f"/api/v1/devices/{device.device_id}"

        assert client.get(endpoint).status_code == 401

        forbidden = client.get(
            endpoint,
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert forbidden.status_code == 403

        response = client.get(
            endpoint,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200

        payload = response.json()

        assert payload["device_id"] == device.device_id
        assert payload["display_name"] == "Reader Node"
        assert payload["online"] is True
        assert payload["latest_inventory"]["hostname"] == "reader-node"

        assert payload["modules"] == [
            {
                "module_id": "org.3mm.example",
                "installed_version": "1.1.0",
                "desired_version": "1.2.0",
                "status": "succeeded",
                "enabled": True,
                "error": None,
            }
        ]

        missing = client.get(
            "/api/v1/devices/dev_ffffffffffffffffffffffffffffffff",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert missing.status_code == 404

    finally:
        db.close()
