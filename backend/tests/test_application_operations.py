from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401 - register the complete model graph
from backend.db.base import Base
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.db.user import User
from backend.routes.application_operations import router
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token


def test_application_secrets_are_admin_only_and_never_return_plaintext(
    monkeypatch,
):
    monkeypatch.setenv("AI_SETTINGS_MASTER_KEY", Fernet.generate_key().decode())
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
        hashed_password="x",
        role="admin",
    )
    operator = User(
        username="operator",
        email="operator@example.com",
        hashed_password="x",
        role="user",
    )
    package = ModulePackage(
        module_id="org.3mm.secrets-test",
        version="1.0.0",
        manifest={},
        sha256="e" * 64,
        size_bytes=1,
        file_path="unused",
        registrations=[],
    )
    db.add_all([admin, operator, package])
    db.flush()
    db.add(
        ApplicationExtensionInstallation(
            module_id=package.module_id,
            module_package_id=package.id,
            instance_id="4" * 24,
            active_version=package.version,
            status="active",
            enabled=True,
            socket_path="unused",
        )
    )
    db.commit()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    path = f"/api/v1/application-extensions/{package.module_id}/secrets"
    payload = {
        "label": "Business API",
        "credential_kind": "basic",
        "value": {"username": "service-user", "password": "private-pass"},
    }
    operator_headers = {
        "Authorization": f"Bearer {create_access_token(str(operator.id), {'role': 'user'})}"
    }
    admin_headers = {
        "Authorization": f"Bearer {create_access_token(str(admin.id), {'role': 'admin'})}"
    }
    try:
        assert client.post(path, json=payload, headers=operator_headers).status_code == 403
        created = client.post(path, json=payload, headers=admin_headers)
        assert created.status_code == 201
        listed = client.get(path, headers=admin_headers)
        assert listed.status_code == 200
        rendered = f"{created.text}\n{listed.text}"
        assert "private-pass" not in rendered
        assert "service-user" not in rendered
        assert "encrypted_value" not in rendered
        assert created.json()["secret_ref"].startswith("secret_")
    finally:
        db.close()
        engine.dispose()
