from datetime import datetime, timezone

import backend.database  # noqa: F401
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.db.device import Device
from backend.db.module import ModuleInstallation, ModulePackage
from backend.db.settings import Settings
from backend.db.user import User
from backend.routes.ai_automations import _server_managed_provider_key, router
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setattr(
        jwt_utils,
        "SECRET_KEY",
        "test-only-key-with-at-least-32-bytes",
    )


def test_admin_reads_trusted_capability_context_and_regular_user_is_denied():
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
    regular = User(
        username="operator",
        email="operator@example.com",
        hashed_password=hash_password("test-password"),
        role="user",
    )
    device = Device(
        device_id="dev_0123456789abcdef0123456789abcdef",
        display_name="Mock Pi",
        role="standalone",
        protocol_version="1.0",
        approved_at=datetime.now(timezone.utc),
    )
    db.add_all([admin, regular, device])
    db.commit()
    package = ModulePackage(
        module_id="org.3mm.mock-gpio",
        version="1.0.0",
        manifest={},
        sha256="b" * 64,
        size_bytes=1,
        file_path="unused",
        registrations=[{
            "kind": "capability",
            "registration_id": "gpio.digital.control",
            "metadata": {"driver": "mock"},
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
        "Authorization": f"Bearer {create_access_token(str(admin.id), {'role': 'admin'})}"
    }
    user_headers = {
        "Authorization": f"Bearer {create_access_token(str(regular.id), {'role': 'user'})}"
    }

    response = client.get("/api/v1/ai/automation-context", headers=admin_headers)

    assert response.status_code == 200
    assert response.json() == {
        "context_version": 1,
        "capabilities": [{
            "device_id": device.device_id,
            "device_name": "Mock Pi",
            "device_role": "standalone",
            "capability_id": "gpio.digital.control",
            "module_id": "org.3mm.mock-gpio",
            "module_version": "1.0.0",
            "metadata": {"driver": "mock"},
        }],
    }
    assert client.get(
        "/api/v1/ai/automation-context",
        headers=user_headers,
    ).status_code == 403
    assert client.get("/api/v1/ai/automation-context").status_code == 401

    candidate = {
        "schema_version": 1,
        "name": "Set mock output",
        "execution": "local",
        "enabled": True,
        "trigger": {
            "kind": "capability_event",
            "device_id": device.device_id,
            "capability_id": "gpio.digital.control",
            "event": "input.changed",
            "conditions": {"channel": "gpio.input.1", "value": True},
        },
        "actions": [{
            "kind": "capability_command",
            "device_id": device.device_id,
            "capability_id": "gpio.digital.control",
            "action": "set_output",
            "arguments": {"channel": "gpio.output.1", "value": True},
        }],
    }
    created = client.post(
        "/api/v1/ai/automation-proposals",
        headers=admin_headers,
        json={"intent": "Mirror input one to output one", "candidate": candidate},
    )
    assert created.status_code == 200
    proposal = created.json()
    assert proposal["status"] == "validated"
    assert proposal["diff"]["target_devices"] == [device.device_id]

    wrong_hash = client.post(
        f"/api/v1/ai/automation-proposals/{proposal['proposal_id']}/approve",
        headers=admin_headers,
        json={"expected_candidate_hash": "0" * 64},
    )
    assert wrong_hash.status_code == 409
    approved = client.post(
        f"/api/v1/ai/automation-proposals/{proposal['proposal_id']}/approve",
        headers=admin_headers,
        json={"expected_candidate_hash": proposal["candidate_hash"]},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    listed = client.get(
        "/api/v1/ai/automation-proposals?status=approved",
        headers=admin_headers,
    )
    assert listed.status_code == 200
    assert [item["proposal_id"] for item in listed.json()] == [proposal["proposal_id"]]
    assert client.get(
        "/api/v1/ai/automation-proposals",
        headers=user_headers,
    ).status_code == 403

    invalid_candidate = {
        **candidate,
        "actions": [{
            **candidate["actions"][0],
            "capability_id": "camera.capture",
        }],
    }
    invalid = client.post(
        "/api/v1/ai/automation-proposals",
        headers=admin_headers,
        json={"intent": "Take a photo", "candidate": invalid_candidate},
    )
    assert invalid.status_code == 200
    assert invalid.json()["status"] == "invalid"
    assert invalid.json()["validation_issues"][0]["code"] == "capability.unavailable"

    db.close()
    engine.dispose()


def test_server_managed_provider_key_comes_from_global_encrypted_settings(monkeypatch):
    monkeypatch.delenv("AI_SETTINGS_MASTER_KEY", raising=False)
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(Settings(
        key="ai_openrouter_api_key",
        value="stored-test-key",
        language_code=None,
        user_id=None,
    ))
    db.commit()

    assert _server_managed_provider_key(db, "openrouter") == "stored-test-key"
    assert _server_managed_provider_key(db, "groq") is None
    assert _server_managed_provider_key(db, "unsupported") is None

    db.close()
    engine.dispose()
