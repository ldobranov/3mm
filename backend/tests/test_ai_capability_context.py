from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401
from backend.db.base import Base
from backend.db.device import Device
from backend.db.module import ModuleInstallation, ModulePackage
from backend.db.user import User
from backend.routes.ai_extension_builder_routes import router
from backend.services.ai_capability_context import build_automation_capability_context
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_context_contains_only_trusted_enabled_capabilities():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    approved = Device(
        device_id="dev_approved",
        display_name="Approved Pi",
        role="standalone",
        protocol_version="1.0",
        approved_at=datetime.now(timezone.utc),
    )
    revoked = Device(
        device_id="dev_revoked",
        display_name="Revoked Pi",
        role="node",
        protocol_version="1.0",
        approved_at=datetime.now(timezone.utc),
        revoked_at=datetime.now(timezone.utc),
    )
    db.add_all([approved, revoked])
    db.commit()
    package = ModulePackage(
        module_id="org.3mm.mock-gpio",
        version="1.0.0",
        manifest={},
        sha256="a" * 64,
        size_bytes=1,
        file_path="unused",
        registrations=[
            {"kind": "capability", "registration_id": "gpio.digital.control"},
            {"kind": "navigation", "registration_id": "gpio.navigation"},
        ],
    )
    db.add(package)
    db.commit()
    db.add_all([
        ModuleInstallation(
            device_id=approved.id,
            module_package_id=package.id,
            module_id=package.module_id,
            installed_version=package.version,
            desired_version=package.version,
            status="succeeded",
            enabled=True,
        ),
        ModuleInstallation(
            device_id=revoked.id,
            module_package_id=package.id,
            module_id=package.module_id,
            installed_version=package.version,
            desired_version=package.version,
            status="succeeded",
            enabled=True,
        ),
    ])
    db.commit()

    result = build_automation_capability_context(db)

    assert [item.model_dump() for item in result.capabilities] == [{
        "device_id": "dev_approved",
        "device_name": "Approved Pi",
        "device_role": "standalone",
        "capability_id": "gpio.digital.control",
        "module_id": "org.3mm.mock-gpio",
        "module_version": "1.0.0",
        "metadata": {},
    }]
    db.close()
    engine.dispose()


def test_builder_capability_endpoint_requires_admin_and_exposes_channels(monkeypatch):
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
        role="viewer",
    )
    device = Device(
        device_id="dev_gpio",
        display_name="Workshop Pi",
        role="standalone",
        protocol_version="1.0",
        approved_at=datetime.now(timezone.utc),
    )
    db.add_all([admin, viewer, device])
    db.commit()
    package = ModulePackage(
        module_id="org.3mm.mock-gpio",
        version="1.0.4",
        manifest={},
        sha256="b" * 64,
        size_bytes=1,
        file_path="unused",
        registrations=[{
            "kind": "capability",
            "registration_id": "gpio.digital.input",
            "metadata": {"automation_channels": "gpio.input.1,gpio.input.2"},
        }],
    )
    db.add(package)
    db.commit()
    db.add(ModuleInstallation(
        device_id=device.id,
        module_package_id=package.id,
        module_id=package.module_id,
        installed_version=package.version,
        desired_version=package.version,
        status="succeeded",
        enabled=True,
    ))
    db.commit()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    admin_headers = {
        "Authorization": f"Bearer {create_access_token(str(admin.id), {'role': 'admin'})}",
    }
    viewer_headers = {
        "Authorization": f"Bearer {create_access_token(str(viewer.id), {'role': 'viewer'})}",
    }

    response = client.get("/api/ai/extensions/capabilities", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["capabilities"] == [{
        "device_id": "dev_gpio",
        "device_name": "Workshop Pi",
        "device_role": "standalone",
        "capability_id": "gpio.digital.input",
        "module_id": "org.3mm.mock-gpio",
        "module_version": "1.0.4",
        "metadata": {"automation_channels": "gpio.input.1,gpio.input.2"},
    }]
    assert client.get("/api/ai/extensions/capabilities", headers=viewer_headers).status_code == 403
    db.close()
    engine.dispose()
