import json
import subprocess
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401 - register the complete Core model graph
from backend.config import ApplicationRuntimeSettings
from backend.db.base import Base
from backend.db.module import (
    ApplicationExtensionInstallation,
    ApplicationPermissionGrant,
    ModulePackage,
)
from backend.db.user import User
from backend.routes import application_extensions, modules
from backend.routes.application_extensions import router as application_router
from backend.routes.modules import router as module_router
from backend.services import application_extensions as gateway
from backend.services import compiled_ui
from backend.services.compiled_ui import compile_ui_package
from backend.services.module_packages import validate_module_package
from backend.tests.test_module_packages import application_definition, application_package
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token


class ReadyClient:
    def __init__(self, *_args):
        pass

    def invoke(self, _operation_id, _payload, _context):
        return {}


def fake_compiler(command, **_kwargs):
    output = Path(command[3])
    (output / "assets").mkdir(parents=True)
    entries = {}
    for entrypoint_id in ("registration", "operations"):
        name = f"assets/{entrypoint_id}.mjs"
        (output / name).write_text("export default {}", encoding="utf-8")
        entries[entrypoint_id] = name
    (output / "entrypoints.json").write_text(
        json.dumps({"entries": entries, "styles": []}),
        encoding="utf-8",
    )
    return subprocess.CompletedProcess(command, 0, "", "")


def environment(monkeypatch, tmp_path, blob=None):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    admin = User(username="admin", email="admin@example.com", hashed_password="x", role="admin")
    operator = User(username="operator", email="operator@example.com", hashed_password="x", role="user")
    db.add_all([admin, operator])
    db.commit()

    blob = blob or application_package()
    validated = validate_module_package(blob)
    archive = tmp_path / f"{validated.sha256}.zip"
    archive.write_bytes(blob)
    package = ModulePackage(
        module_id=validated.manifest.module_id,
        version=validated.manifest.version,
        manifest=validated.manifest.model_dump(mode="json"),
        sha256=validated.sha256,
        size_bytes=len(blob),
        file_path=str(archive),
        registrations=[],
    )
    db.add(package)
    db.commit()
    installation = ApplicationExtensionInstallation(
        module_id=package.module_id,
        module_package_id=package.id,
        instance_id="a" * 24,
        active_version=package.version,
        status="active",
        enabled=True,
        socket_path=str(tmp_path / "service.sock"),
    )
    db.add(installation)
    db.commit()

    key_root = tmp_path / "keys"
    key_root.mkdir()
    (key_root / f"{installation.instance_id}.key").write_bytes(b"s" * 32)
    runtime_settings = ApplicationRuntimeSettings(
        root=tmp_path / "apps",
        key_root=key_root,
        helper_socket=tmp_path / "helper.sock",
    )
    monkeypatch.setattr(
        application_extensions,
        "get_settings",
        lambda: type("Settings", (), {"applications": runtime_settings})(),
    )
    monkeypatch.setattr(gateway, "ApplicationServiceClient", ReadyClient)

    app = FastAPI()
    app.include_router(application_router)
    app.include_router(module_router)
    from backend.routes.auth_refresh import router as refresh_router
    app.include_router(refresh_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    admin_token = create_access_token(str(admin.id), {"role": "admin"})
    operator_token = create_access_token(str(operator.id), {"role": "user"})
    return client, db, engine, admin, operator, installation, package, admin_token, operator_token


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_operator_permission_is_server_enforced_and_revocable(monkeypatch, tmp_path):
    client, db, engine, admin, operator, _installation, _package, admin_token, operator_token = environment(monkeypatch, tmp_path)
    try:
        path = "/api/v1/application-extensions/org.3mm.workflow-reference/operator/operations/approve"
        request = {"payload": {}, "idempotency_key": "request-0001"}
        assert client.post(path, json=request, headers=headers(operator_token)).status_code == 403
        granted = client.post(
            "/api/v1/application-extensions/org.3mm.workflow-reference/permissions/grants",
            json={"user_id": operator.id, "permission_id": "records_manage"},
            headers=headers(admin_token),
        )
        assert granted.status_code == 201
        assert client.post(path, json=request, headers=headers(operator_token)).status_code == 200
        revoked = client.delete(
            f"/api/v1/application-extensions/org.3mm.workflow-reference/permissions/grants/{operator.id}/records_manage",
            headers=headers(admin_token),
        )
        assert revoked.status_code == 200
        assert client.post(path, json=request, headers=headers(operator_token)).status_code == 403
    finally:
        db.close()
        engine.dispose()


def test_kiosk_enrollment_session_and_revocation_are_independent_from_users(monkeypatch, tmp_path):
    client, db, engine, _admin, _operator, _installation, _package, admin_token, _operator_token = environment(monkeypatch, tmp_path)
    try:
        base = "/api/v1/application-extensions/org.3mm.workflow-reference/kiosk"
        created = client.post(
            f"{base}/enrollments",
            json={"label": "Front desk tablet"},
            headers=headers(admin_token),
        )
        assert created.status_code == 201
        claimed = client.post(
            f"{base}/enrollments/claim",
            json={"code": created.json()["code"]},
        )
        assert claimed.status_code == 200
        identity = claimed.json()
        assert client.post(
            f"{base}/enrollments/claim",
            json={"code": created.json()["code"]},
        ).status_code == 400
        session = client.post(
            f"{base}/sessions",
            json={
                "terminal_id": identity["terminal_id"],
                "credential": identity["credential"],
            },
        )
        assert session.status_code == 200
        kiosk_token = session.json()["access_token"]
        operation = client.post(
            f"{base}/operations/register",
            json={"payload": {}, "idempotency_key": "kiosk-request-0001"},
            headers=headers(kiosk_token),
        )
        assert operation.status_code == 200
        operator_path = "/api/v1/application-extensions/org.3mm.workflow-reference/operator/operations/approve"
        assert client.post(
            operator_path,
            json={"payload": {}, "idempotency_key": "kiosk-request-0002"},
            headers=headers(kiosk_token),
        ).status_code == 401
        assert client.post("/api/user/refresh", headers=headers(kiosk_token)).status_code == 401
        assert client.delete(
            f"{base}/terminals/{identity['terminal_id']}",
            headers=headers(admin_token),
        ).status_code == 200
        assert client.post(
            f"{base}/operations/register",
            json={"payload": {}, "idempotency_key": "kiosk-request-0003"},
            headers=headers(kiosk_token),
        ).status_code == 401
    finally:
        db.close()
        engine.dispose()


def test_public_gateway_allows_only_explicitly_public_operations(monkeypatch, tmp_path):
    definition = application_definition()
    definition["operations"][1]["audiences"] = ["public", "kiosk"]
    blob = application_package(definition=definition)
    client, db, engine, *_rest = environment(monkeypatch, tmp_path, blob=blob)
    try:
        base = "/api/v1/application-extensions/org.3mm.workflow-reference/public/operations"
        assert client.post(
            f"{base}/register",
            json={"payload": {}, "idempotency_key": "public-request-0001"},
        ).status_code == 200
        assert client.post(
            f"{base}/approve",
            json={"payload": {}, "idempotency_key": "public-request-0002"},
        ).status_code == 409
    finally:
        db.close()
        engine.dispose()


def test_compiled_application_catalog_returns_only_authorized_routes(monkeypatch, tmp_path):
    client, db, engine, _admin, operator, installation, _package, admin_token, operator_token = environment(monkeypatch, tmp_path)
    try:
        monkeypatch.setenv("COMPILED_UI_ARTIFACTS_DIR", str(tmp_path / "compiled"))
        monkeypatch.setattr(compiled_ui.subprocess, "run", fake_compiler)
        package = db.get(ModulePackage, installation.module_package_id)
        validated = validate_module_package(Path(package.file_path).read_bytes())
        compile_ui_package(Path(package.file_path).read_bytes(), validated)

        catalog = "/api/v1/modules/compiled-ui/catalog"
        assert client.get(catalog).json()["items"] == []
        assert client.get(catalog, headers=headers(operator_token)).json()["items"] == []
        db.add(
            ApplicationPermissionGrant(
                application_installation_id=installation.id,
                user_id=operator.id,
                permission_id="records_manage",
            )
        )
        db.commit()
        operator_item = client.get(catalog, headers=headers(operator_token)).json()["items"][0]
        assert [item["entrypoint_id"] for item in operator_item["entrypoints"]] == ["operations"]
        assert operator_item["entrypoints"][0]["application_audience"] == "operator"
        admin_item = client.get(catalog, headers=headers(admin_token)).json()["items"][0]
        assert [item["entrypoint_id"] for item in admin_item["entrypoints"]] == ["operations"]
        enrollment = client.post(
            "/api/v1/application-extensions/org.3mm.workflow-reference/kiosk/enrollments",
            json={"label": "Catalog tablet"},
            headers=headers(admin_token),
        ).json()
        kiosk_token = client.post(
            "/api/v1/application-extensions/org.3mm.workflow-reference/kiosk/enrollments/claim",
            json={"code": enrollment["code"]},
        ).json()["access_token"]
        kiosk_item = client.get(catalog, headers=headers(kiosk_token)).json()["items"][0]
        assert [item["entrypoint_id"] for item in kiosk_item["entrypoints"]] == ["registration"]
        assert kiosk_item["entrypoints"][0]["application_audience"] == "kiosk"
    finally:
        db.close()
        engine.dispose()
