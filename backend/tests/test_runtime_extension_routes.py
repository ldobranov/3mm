import backend.database  # noqa: F401
import hashlib
import io
import json
import zipfile
import pytest
from backend.db.base import Base
from backend.db.user import User
from backend.db.module import ModulePackage
from backend.db.runtime_extension import RuntimeEntityRecord
from backend.routes.runtime_extensions import router
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "test-only-key-with-at-least-32-bytes")


def definition(version="1.0.0", *, module_id="org.3mm.contacts", path="/contacts"):
    return {
        "runtime_extension_version": 1,
        "module_id": module_id,
        "version": version,
        "name": {"en": "Contacts"},
        "description": {"en": "Manage contacts"},
        "entities": [{
            "entity_id": "contact",
            "label": {"en": "Contact"},
            "fields": [
                {"field_id": "name", "label": {"en": "Name"}, "kind": "text", "required": True},
                {"field_id": "age", "label": {"en": "Age"}, "kind": "integer"},
            ],
        }],
        "pages": [{
            "page_id": "contacts",
            "path": path,
            "title": {"en": "Contacts"},
            "entity_id": "contact",
            "view": "table",
            "actions": ["create", "read", "update", "delete"],
        }],
        "navigation": [{"navigation_id": "contacts_menu", "page_id": "contacts", "label": {"en": "Contacts"}}],
        "permissions": ["runtime.data.read", "runtime.data.write"],
    }


def make_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    admin = User(username="admin", email="admin@example.com", hashed_password=hash_password("test-password"), role="admin")
    user = User(username="user", email="user@example.com", hashed_password=hash_password("test-password"), role="user")
    db.add_all([admin, user]); db.commit()
    app = FastAPI(); app.include_router(router); app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    admin_headers = {"Authorization": f"Bearer {create_access_token(str(admin.id), {'role': 'admin'})}"}
    user_headers = {"Authorization": f"Bearer {create_access_token(str(user.id), {'role': 'user'})}"}
    return client, db, engine, admin_headers, user_headers


def test_definition_publish_is_admin_only_and_versions_are_immutable():
    client, db, engine, admin_headers, user_headers = make_client()
    try:
        assert client.post("/api/v1/runtime-extensions/definitions", headers=user_headers, json=definition()).status_code == 403
        created = client.post("/api/v1/runtime-extensions/definitions", headers=admin_headers, json=definition())
        assert created.status_code == 201 and created.json()["enabled"] is True
        changed = definition(); changed["description"] = {"en": "Changed"}
        assert client.post("/api/v1/runtime-extensions/definitions", headers=admin_headers, json=changed).status_code == 409
    finally:
        db.close(); engine.dispose()


def test_authenticated_crud_is_validated_against_the_runtime_contract():
    client, db, engine, admin_headers, user_headers = make_client()
    try:
        client.post("/api/v1/runtime-extensions/definitions", headers=admin_headers, json=definition())
        base = "/api/v1/runtime-extensions/org.3mm.contacts/entities/contact/records"
        assert client.post(base, headers=user_headers, json={"age": 10}).status_code == 422
        assert client.post(base, headers=user_headers, json={"name": "Ada", "unknown": True}).status_code == 422
        created = client.post(base, headers=user_headers, json={"name": "Ada", "age": 36})
        assert created.status_code == 201
        record_id = created.json()["record_id"]
        assert client.get(base, headers=user_headers).json()[0]["data"]["name"] == "Ada"
        updated = client.patch(f"{base}/{record_id}", headers=user_headers, json={"age": 37})
        assert updated.status_code == 200 and updated.json()["data"]["age"] == 37
        assert client.delete(f"{base}/{record_id}", headers=user_headers).status_code == 204
        assert client.get(base, headers=user_headers).json() == []
    finally:
        db.close(); engine.dispose()


def test_page_role_is_enforced_by_the_data_api():
    client, db, engine, admin_headers, user_headers = make_client()
    try:
        value = definition(); value["pages"][0]["requires_role"] = "admin"
        client.post("/api/v1/runtime-extensions/definitions", headers=admin_headers, json=value)
        base = "/api/v1/runtime-extensions/org.3mm.contacts/entities/contact/records"
        assert client.get(base, headers=user_headers).status_code == 403
        assert client.get(base, headers=admin_headers).status_code == 200
    finally:
        db.close(); engine.dispose()


def test_records_survive_activation_of_a_new_definition_version():
    client, db, engine, admin_headers, user_headers = make_client()
    try:
        client.post("/api/v1/runtime-extensions/definitions", headers=admin_headers, json=definition())
        base = "/api/v1/runtime-extensions/org.3mm.contacts/entities/contact/records"
        client.post(base, headers=user_headers, json={"name": "Ada"})

        upgraded = definition("1.1.0")
        assert client.post("/api/v1/runtime-extensions/definitions", headers=admin_headers, json=upgraded).status_code == 201
        records = client.get(base, headers=user_headers)
        assert records.status_code == 200
        assert records.json()[0]["data"]["name"] == "Ada"
    finally:
        db.close(); engine.dispose()


def test_catalog_package_activation_uses_the_reviewed_archive(tmp_path):
    client, db, engine, admin_headers, user_headers = make_client()
    try:
        manifest = {
            "manifest_version": 2, "module_id": "org.3mm.contacts", "name": "Contacts", "version": "1.0.0",
            "runtimes": ["ui"], "entrypoints": {"ui": "runtime-extension.json"},
            "compatibility": {"protocol": "1.0", "architectures": ["any"]},
            "capabilities": {"provides": [], "consumes": []}, "permissions": ["data.read", "data.write"],
            "health_check": {"type": "json_file", "path": "runtime-extension.json"}, "registrations": [],
        }
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("runtime-extension.json", json.dumps(definition()))
        blob = output.getvalue(); path = tmp_path / "contacts.zip"; path.write_bytes(blob)
        digest = hashlib.sha256(blob).hexdigest()
        db.add(ModulePackage(module_id="org.3mm.contacts", version="1.0.0", manifest=manifest, sha256=digest, size_bytes=len(blob), file_path=str(path), registrations=[])); db.commit()

        activated = client.post(f"/api/v1/runtime-extensions/packages/{digest}/activate", headers=admin_headers)
        assert activated.status_code == 201
        assert activated.json()["definition"]["pages"][0]["path"] == "/contacts"

        client.delete(
            "/api/v1/runtime-extensions/definitions/org.3mm.contacts",
            headers=admin_headers,
        )
        uninstalled = client.get(
            "/api/v1/runtime-extensions/catalog", headers=user_headers
        ).json()[0]
        assert uninstalled["status"] == "uninstalled"
        assert uninstalled["package_sha256"] == digest
        assert uninstalled["is_installed"] is False
        assert client.post(
            f"/api/v1/runtime-extensions/packages/{digest}/activate",
            headers=admin_headers,
        ).status_code == 201
    finally:
        db.close(); engine.dispose()


def test_catalog_exposes_active_runtime_extensions():
    client, db, engine, admin_headers, user_headers = make_client()
    try:
        client.post("/api/v1/runtime-extensions/definitions", headers=admin_headers, json=definition())

        response = client.get("/api/v1/runtime-extensions/catalog", headers=user_headers)

        assert response.status_code == 200
        assert response.json() == [{
            "id": "runtime:org.3mm.contacts",
            "source": "runtime",
            "name": "Contacts",
            "type": "runtime",
            "version": "1.0.0",
            "description": "Manage contacts",
            "author": None,
            "status": "active",
            "is_enabled": True,
            "created_at": response.json()[0]["created_at"],
            "can_manage": False,
            "available_versions": ["1.0.0"],
            "package_sha256": None,
            "is_installed": True,
        }]
    finally:
        db.close(); engine.dispose()


def test_catalog_localizes_runtime_metadata_and_limits_management_to_admins():
    client, db, engine, admin_headers, user_headers = make_client()
    try:
        value = definition()
        value["name"]["translations"] = {"bg": "Контакти"}
        value["description"]["translations"] = {"bg": "Управление на контакти"}
        client.post("/api/v1/runtime-extensions/definitions", headers=admin_headers, json=value)

        user_item = client.get(
            "/api/v1/runtime-extensions/catalog?language=bg", headers=user_headers
        ).json()[0]
        admin_item = client.get(
            "/api/v1/runtime-extensions/catalog?language=bg", headers=admin_headers
        ).json()[0]

        assert user_item["name"] == "Контакти"
        assert user_item["description"] == "Управление на контакти"
        assert user_item["can_manage"] is False
        assert admin_item["can_manage"] is True
    finally:
        db.close(); engine.dispose()


def test_runtime_extension_can_be_disabled_and_reenabled_without_losing_records():
    client, db, engine, admin_headers, user_headers = make_client()
    try:
        client.post("/api/v1/runtime-extensions/definitions", headers=admin_headers, json=definition())
        records_url = "/api/v1/runtime-extensions/org.3mm.contacts/entities/contact/records"
        assert client.post(records_url, headers=user_headers, json={"name": "Ada"}).status_code == 201

        toggle_url = "/api/v1/runtime-extensions/definitions/org.3mm.contacts"
        disabled = client.patch(toggle_url, headers=admin_headers, json={"enabled": False})
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False
        assert client.get("/api/v1/runtime-extensions/definitions", headers=user_headers).json() == []
        assert client.get(records_url, headers=user_headers).status_code == 404
        assert client.get("/api/v1/runtime-extensions/catalog", headers=user_headers).json()[0]["status"] == "inactive"

        enabled = client.patch(toggle_url, headers=admin_headers, json={"enabled": True})
        assert enabled.status_code == 200
        assert enabled.json()["enabled"] is True
        records = client.get(records_url, headers=user_headers)
        assert records.status_code == 200
        assert records.json()[0]["data"]["name"] == "Ada"
    finally:
        db.close(); engine.dispose()


def test_disable_and_enable_preserves_the_selected_rollback_version():
    client, db, engine, admin_headers, _user_headers = make_client()
    try:
        client.post("/api/v1/runtime-extensions/definitions", headers=admin_headers, json=definition("1.0.0"))
        client.post("/api/v1/runtime-extensions/definitions", headers=admin_headers, json=definition("1.1.0"))
        base = "/api/v1/runtime-extensions/definitions/org.3mm.contacts"
        client.post(f"{base}/versions/1.0.0/activate", headers=admin_headers)

        client.patch(base, headers=admin_headers, json={"enabled": False})
        enabled = client.patch(base, headers=admin_headers, json={"enabled": True})

        assert enabled.status_code == 200
        assert enabled.json()["version"] == "1.0.0"
    finally:
        db.close(); engine.dispose()


def test_runtime_activation_rejects_core_and_active_extension_route_conflicts():
    client, db, engine, admin_headers, _user_headers = make_client()
    try:
        reserved = client.post(
            "/api/v1/runtime-extensions/definitions",
            headers=admin_headers,
            json=definition(path="/settings/runtime"),
        )
        assert reserved.status_code == 409

        assert client.post(
            "/api/v1/runtime-extensions/definitions",
            headers=admin_headers,
            json=definition(),
        ).status_code == 201
        conflict = client.post(
            "/api/v1/runtime-extensions/definitions",
            headers=admin_headers,
            json=definition(module_id="org.3mm.people"),
        )
        assert conflict.status_code == 409
    finally:
        db.close(); engine.dispose()


def test_previous_runtime_version_can_be_reactivated_without_losing_records():
    client, db, engine, admin_headers, user_headers = make_client()
    try:
        client.post("/api/v1/runtime-extensions/definitions", headers=admin_headers, json=definition("1.0.0"))
        records_url = "/api/v1/runtime-extensions/org.3mm.contacts/entities/contact/records"
        client.post(records_url, headers=user_headers, json={"name": "Ada"})
        client.post("/api/v1/runtime-extensions/definitions", headers=admin_headers, json=definition("1.1.0"))

        rollback = client.post(
            "/api/v1/runtime-extensions/definitions/org.3mm.contacts/versions/1.0.0/activate",
            headers=admin_headers,
        )

        assert rollback.status_code == 200
        assert rollback.json()["version"] == "1.0.0"
        catalog = client.get("/api/v1/runtime-extensions/catalog", headers=user_headers).json()[0]
        assert catalog["version"] == "1.0.0"
        assert catalog["available_versions"] == ["1.0.0", "1.1.0"]
        assert client.get(records_url, headers=user_headers).json()[0]["data"]["name"] == "Ada"
    finally:
        db.close(); engine.dispose()


def test_runtime_uninstall_preserves_data_by_default_and_can_delete_it_explicitly():
    client, db, engine, admin_headers, user_headers = make_client()
    try:
        client.post("/api/v1/runtime-extensions/definitions", headers=admin_headers, json=definition())
        records_url = "/api/v1/runtime-extensions/org.3mm.contacts/entities/contact/records"
        client.post(records_url, headers=user_headers, json={"name": "Ada"})
        uninstall_url = "/api/v1/runtime-extensions/definitions/org.3mm.contacts"

        preserved = client.delete(uninstall_url, headers=admin_headers)
        assert preserved.status_code == 200
        assert preserved.json()["data_preserved"] is True
        assert db.query(RuntimeEntityRecord).count() == 1

        client.post("/api/v1/runtime-extensions/definitions", headers=admin_headers, json=definition())
        assert client.get(records_url, headers=user_headers).json()[0]["data"]["name"] == "Ada"

        deleted = client.delete(f"{uninstall_url}?delete_data=true", headers=admin_headers)
        assert deleted.status_code == 200
        assert deleted.json()["deleted_records"] == 1
        assert deleted.json()["data_preserved"] is False
        assert db.query(RuntimeEntityRecord).count() == 0
    finally:
        db.close(); engine.dispose()
