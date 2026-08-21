import base64
import hashlib
import io
import json
import zipfile
from types import SimpleNamespace

import pytest
import backend.database  # noqa: F401 - register the complete model graph
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.db.user import User
from backend.routes.extension_projects import router
import backend.routes.extension_projects as project_routes
from backend.schemas.ai_extension_builder import BuildWarning
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "test-only-key-with-at-least-32-bytes")


def _client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    admin = User(username="admin-projects", email="projects@example.com", hashed_password=hash_password("test"), role="admin")
    user = User(username="user-projects", email="user-projects@example.com", hashed_password=hash_password("test"), role="user")
    db.add_all([admin, user]); db.commit()
    app = FastAPI(); app.include_router(router); app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    admin_headers = {"Authorization": f"Bearer {create_access_token(str(admin.id), {'role': 'admin'})}"}
    user_headers = {"Authorization": f"Bearer {create_access_token(str(user.id), {'role': 'user'})}"}
    return client, db, admin_headers, user_headers


def _compiled_artifact(version: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps({
            "manifest_version": 2,
            "module_id": "clock.project",
            "version": version,
            "entrypoints": {"ui": "compiled-ui.json"},
        }))
        archive.writestr("compiled-ui.json", "{}")
    return output.getvalue()


def test_project_source_is_persistent_and_build_versions_are_server_managed(monkeypatch, tmp_path):
    monkeypatch.setattr(project_routes, "get_settings", lambda: SimpleNamespace(
        backend=SimpleNamespace(uploads_dir=tmp_path)
    ))
    client, db, headers, _ = _client()
    created = client.post("/api/v1/extension-projects", headers=headers, json={
        "name": "Clock Project", "project_type": "widget", "spec": {"goal": "Clock"},
        "files": [{"path": "source/frontend/Widget.vue", "content": "<template>Clock</template>"}],
    })
    assert created.status_code == 201
    project = created.json()
    assert project["slug"] == "clock-project"
    assert project["current_version"] == "0.0.0"
    assert project["files"][0]["sha256"]
    assert client.get(
        f"/api/v1/extension-projects/{project['project_id']}/next-version?change_kind=minor",
        headers=headers,
    ).json()["next_version"] == "0.1.0"

    first_artifact = _compiled_artifact("0.0.1")
    first = client.post(f"/api/v1/extension-projects/{project['project_id']}/builds", headers=headers, json={
        "expected_revision": 1, "change_kind": "patch", "status": "built", "change_request": "Initial build",
        "artifact_base64": base64.b64encode(first_artifact).decode(),
    })
    assert first.status_code == 201
    assert first.json()["version"] == "0.0.1"
    assert first.json()["has_artifact"] is True
    assert first.json()["package_kind"] == "compiled"
    assert first.json()["files_snapshot"]["source/frontend/Widget.vue"] == "<template>Clock</template>"

    updated = client.get(f"/api/v1/extension-projects/{project['project_id']}", headers=headers).json()
    second_artifact = _compiled_artifact("0.1.0")
    second = client.post(f"/api/v1/extension-projects/{project['project_id']}/builds", headers=headers, json={
        "expected_revision": updated["revision"], "change_kind": "minor", "status": "built",
        "artifact_base64": base64.b64encode(second_artifact).decode(),
    })
    assert second.status_code == 201
    assert second.json()["version"] == "0.1.0"
    installed = client.post(
        f"/api/v1/extension-projects/{project['project_id']}/builds/{second.json()['build_id']}/installed",
        headers=headers,
        json={"artifact_sha256": hashlib.sha256(second_artifact).hexdigest()},
    )
    assert installed.status_code == 200
    assert installed.json()["status"] == "installed"
    downloaded = client.get(
        f"/api/v1/extension-projects/{project['project_id']}/builds/{second.json()['build_id']}/artifact",
        headers=headers,
    )
    assert downloaded.content == second_artifact

    rolled_back = client.post(
        f"/api/v1/extension-projects/{project['project_id']}/builds/{first.json()['build_id']}/installed",
        headers=headers,
        json={"artifact_sha256": hashlib.sha256(first_artifact).hexdigest()},
    )
    assert rolled_back.status_code == 200
    history = client.get(f"/api/v1/extension-projects/{project['project_id']}/builds", headers=headers).json()
    assert next(item for item in history if item["build_id"] == first.json()["build_id"])["status"] == "installed"
    assert next(item for item in history if item["build_id"] == second.json()["build_id"])["status"] == "built"
    assert len(client.get(f"/api/v1/extension-projects/{project['project_id']}/builds", headers=headers).json()) == 2
    db.close()


def test_project_writes_require_admin_and_reject_stale_or_unsafe_updates():
    client, db, admin_headers, user_headers = _client()
    payload = {"name": "Safe Widget", "project_type": "widget", "files": []}
    assert client.post("/api/v1/extension-projects", json=payload).status_code == 401
    assert client.post("/api/v1/extension-projects", headers=user_headers, json=payload).status_code == 403
    project = client.post("/api/v1/extension-projects", headers=admin_headers, json=payload).json()

    changed = client.patch(f"/api/v1/extension-projects/{project['project_id']}", headers=admin_headers, json={
        "expected_revision": 1, "name": "Safer Widget",
    })
    assert changed.status_code == 200
    stale = client.patch(f"/api/v1/extension-projects/{project['project_id']}", headers=admin_headers, json={
        "expected_revision": 1, "name": "Overwrite",
    })
    assert stale.status_code == 409
    unsafe = client.put(f"/api/v1/extension-projects/{project['project_id']}/files", headers=admin_headers, json={
        "expected_revision": 2, "files": [{"path": "../secret", "content": "no"}],
    })
    assert unsafe.status_code == 422
    db.close()


def test_modify_existing_returns_reviewable_diff_without_mutating_source(monkeypatch):
    client, db, headers, _ = _client()
    seen_files = {}

    def fake_refine(spec, instructions, files, *args):
        seen_files.update(files)
        assert instructions.startswith("Add seconds")
        return {
            "source/frontend/Widget.vue": "<template>Clock with seconds</template>"
        }, [BuildWarning(code="ai.updated_files", message="updated")]

    monkeypatch.setattr(project_routes, "_ai_refine_files", fake_refine)
    spec = {
        "name": "Clock", "version": "0.0.0", "type": "widget", "description": "Clock", "author": "AI",
        "api_prefix": "/api/clock", "backend_entry": "clock.py", "frontend_entry": "Widget.vue",
        "frontend_components": [], "frontend_routes": [],
        "locales": {"supported": ["en", "bg"], "default": "en", "directory": "locales/"},
        "permissions": [], "public_endpoints": [], "dependencies": {}, "config_schema": {}, "goal": "Clock",
    }
    created = client.post("/api/v1/extension-projects", headers=headers, json={
        "name": "Clock Modify", "project_type": "widget", "spec": {"extension_spec": spec},
        "files": [
            {"path": "manifest.json", "content": "{}"},
            {"path": "source/frontend/Widget.vue", "content": "<template>Clock</template>"},
        ],
    }).json()

    response = client.post(f"/api/v1/extension-projects/{created['project_id']}/modify", headers=headers, json={
        "expected_revision": 1, "change_request": "Add seconds", "ai_provider": "auto",
    })
    assert response.status_code == 200
    proposal = response.json()
    assert proposal["changed_files"] == ["source/frontend/Widget.vue"]
    assert "-<template>Clock</template>" in proposal["diffs"]["source/frontend/Widget.vue"]
    assert "manifest.json" not in seen_files
    unchanged = client.get(f"/api/v1/extension-projects/{created['project_id']}", headers=headers).json()
    assert {item["path"]: item["content"] for item in unchanged["files"]}["source/frontend/Widget.vue"] == "<template>Clock</template>"
    db.close()
