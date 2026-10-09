"""Inspection uses real HTTP/auth/validation, never build or install paths."""

import hashlib
import io
import json
import stat
import subprocess
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import backend.database  # noqa: F401 -- register the existing ORM models
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.db.module import ModulePackage
from backend.db.session import UserSession
from backend.db.user import User
from backend.routes import modules
from backend.tests.test_module_packages import (
    application_definition, application_manifest, application_package,
    compiled_ui_package, manifest, package, runtime_package,
)
from backend.tests.test_theme_extension_packages import package as theme_package
from backend.tests.test_theme_extension_v2 import v2_package
from backend.utils.db_utils import get_db
from backend.utils.auth_dep import require_admin
from backend.utils.jwt_utils import create_access_token


URL = "/api/v1/modules/packages/inspect"


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add_all([
        User(id=1, username="inspector", role="admin"),
        User(id=2, username="viewer", role="user"),
        User(id=3, username="blocked", role="admin", is_blocked=True),
    ])
    db.add(UserSession(id=1, user_id=1, token="test-session", is_active=False))
    db.commit()
    app = FastAPI()
    app.include_router(modules.router)
    app.dependency_overrides[get_db] = lambda: db

    def headers(subject=1, **claims):
        return {"Authorization": "Bearer " + create_access_token(str(subject), claims),
                "Content-Type": "application/zip"}

    with TestClient(app) as client:
        yield SimpleNamespace(app=app, client=client, db=db, engine=engine, headers=headers)
    db.close()
    engine.dispose()


@pytest.mark.parametrize("builder,kind,descriptor", [
    (package, "agent_module", None),
    (runtime_package, "runtime_ui", "runtime_extension"),
    (compiled_ui_package, "compiled_ui", "compiled_ui"),
    (application_package, "application", "application_extension"),
    (theme_package, "theme", "theme_extension"),
    (v2_package, "theme", "theme_extension"),
])
def test_inspects_existing_types_without_catalog_changes(api, builder, kind, descriptor):
    blob = builder()
    response = api.client.post(URL, content=blob, headers=api.headers())
    assert response.status_code == 200, response.text
    result = response.json()
    assert response.headers["cache-control"] == "no-store"
    assert result["inspection_version"] == 1
    assert result["package_kind"] == kind
    assert result["sha256"] == hashlib.sha256(blob).hexdigest()
    assert result["size_bytes"] == len(blob)
    assert result["catalog"] == {"status": "new", "existing_sha256": None}
    assert result["trust"] == {"publisher": "not_verified", "signature": "not_verified"}
    assert result["dependency_resolution"] == "not_resolved"
    assert result["permission_approval"] == "not_evaluated"
    assert result["compatibility"]["protocol"] == "matched"
    assert result["compatibility"]["target_device"] == "not_checked"
    assert result["compatibility"]["agent"] == "not_checked"
    assert result["compatibility"]["architecture"] == "not_checked"
    assert result["compatibility"]["core"] == ("matched" if kind == "application" else "not_checked")
    if descriptor:
        assert result["descriptors"][descriptor]["module_id"] == result["module_id"]
    assert list(api.db.scalars(select(ModulePackage))) == []


def test_declarations_are_not_a_dependency_or_configuration_plan(api):
    value = manifest(dependencies={"org.example.other": ">=2.0.0"}, conflicts=["org.example.conflict"],
                     configuration_schema={"type": "object", "required": ["DEVICE_ID"]})
    result = api.client.post(URL, content=package(value), headers=api.headers()).json()
    assert result["manifest"]["dependencies"] == value["dependencies"]
    assert result["manifest"]["conflicts"] == value["conflicts"]
    assert result["manifest"]["configuration_schema"]["required"] == ["DEVICE_ID"]
    assert result["dependency_resolution"] == "not_resolved"


@pytest.mark.parametrize("existing_sha256,status", [(None, "exact_artifact"), ("f" * 64, "version_conflict")])
def test_catalog_comparison_does_not_replace_or_read_existing_archive(api, existing_sha256, status):
    blob = package()
    sha256 = existing_sha256 or hashlib.sha256(blob).hexdigest()
    record = ModulePackage(module_id="org.3mm.demo", version="1.0.0", sha256=sha256,
                           manifest=manifest(), size_bytes=1, file_path="/does-not-exist.zip", registrations=[])
    api.db.add(record)
    api.db.commit()
    results = [api.client.post(URL, content=blob, headers=api.headers()).json() for _ in range(2)]
    assert results[0] == results[1]
    assert results[0]["catalog"] == {"status": status, "existing_sha256": sha256}
    assert list(api.db.scalars(select(ModulePackage))) == [record]
    assert record.sha256 == sha256
    assert record.file_path == "/does-not-exist.zip"


@pytest.mark.parametrize("headers,status", [
    (lambda api: {"Content-Type": "application/zip"}, 401),
    (lambda api: api.headers(2), 403),
    (lambda api: api.headers(3), 401),
    (lambda api: api.headers(token_version=99), 401),
    (lambda api: api.headers(sid=1), 401),
    (lambda api: api.headers(token_type="device"), 401),
    (lambda api: api.headers(exp=int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())), 401),
])
def test_real_auth_rejects_non_admin_and_revoked_sessions_before_validation(api, monkeypatch, headers, status):
    def forbidden(*_args, **_kwargs):
        pytest.fail("unauthorized requests must not inspect archives")
    monkeypatch.setattr(modules, "validate_module_package", forbidden)
    response = api.client.post(URL, content=b"untrusted ZIP", headers=headers(api))
    assert response.status_code == status


@pytest.mark.parametrize("blob", [
    b"", b"not a ZIP", package(extra_name="../escape"),
    package(manifest(permissions=["root.full"])),
    application_package(definition=application_definition(version="2.0.0")),
    package(manifest(compatibility={"protocol": "9.0", "architectures": ["any"]})),
    application_package(manifest_value=application_manifest(
        compatibility={"protocol": "1.0", "architectures": ["any"], "core": ">=9.0.0"},
    )),
])
def test_invalid_or_incompatible_packages_fail_closed(api, blob):
    response = api.client.post(URL, content=blob, headers=api.headers())
    assert response.status_code == 422, response.text
    assert list(api.db.scalars(select(ModulePackage))) == []


@pytest.mark.parametrize("kind", ["legacy", "duplicate", "symlink", "expanded"])
def test_unsafe_archives_and_legacy_format_never_fall_back(api, kind):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps({"type": "language", "name": "Legacy"} if kind == "legacy" else manifest()))
        if kind == "duplicate":
            archive.writestr("manifest.json", json.dumps(manifest()))
        elif kind == "symlink":
            link = zipfile.ZipInfo("link")
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, "/outside")
        elif kind == "expanded":
            archive.writestr("huge.txt", b"0" * (40 * 1024 * 1024 + 1))
    response = api.client.post(URL, content=output.getvalue(), headers=api.headers())
    assert response.status_code == 422


def test_body_is_bounded_even_without_content_length_and_multipart_is_not_parsed(api):
    response = api.client.post(URL, content=iter([b"x" * (10 * 1024 * 1024), b"x"]), headers=api.headers())
    assert response.status_code == 413
    response = api.client.post(URL, content=b"", headers={**api.headers(), "Content-Length": str(10 * 1024 * 1024 + 1)})
    assert response.status_code == 413
    response = api.client.post(URL, content=b"", headers={**api.headers(), "Content-Length": "9" * 5000})
    assert response.status_code == 413
    response = api.client.post(URL, files={"package": ("review.zip", package())},
                               headers={"Authorization": api.headers()["Authorization"]})
    assert response.status_code == 415


def test_inspection_does_not_write_flush_build_spawn_or_extract(api, monkeypatch):
    blob = application_package()
    # Unrelated pending state must not be auto-flushed by the catalog lookup.
    api.db.add(ModulePackage(module_id="org.example.pending", version="1.0.0"))
    # Real authentication is covered above; isolate the read-only handler here.
    api.app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1)

    def forbidden(*_args, **_kwargs):
        pytest.fail("inspection must not write, build, execute or extract")

    def read_only_sql(_connection, _cursor, statement, *_args):
        assert statement.lstrip().upper().startswith("SELECT"), statement

    event.listen(api.engine, "before_cursor_execute", read_only_sql)
    monkeypatch.setattr(modules, "compile_ui_package", forbidden)
    for name in ("add", "commit", "flush", "delete"):
        monkeypatch.setattr(api.db, name, forbidden)
    for name in ("write_bytes", "write_text", "mkdir"):
        monkeypatch.setattr(Path, name, forbidden)
    for name in ("run", "Popen"):
        monkeypatch.setattr(subprocess, name, forbidden)
    for name in ("TemporaryFile", "NamedTemporaryFile", "SpooledTemporaryFile"):
        monkeypatch.setattr(tempfile, name, forbidden)
    monkeypatch.setattr(zipfile.ZipFile, "extractall", forbidden)
    try:
        for _ in range(2):
            response = api.client.post(URL, content=blob, headers=api.headers())
            assert response.status_code == 200, response.text
            assert response.json()["catalog"]["status"] == "new"
    finally:
        event.remove(api.engine, "before_cursor_execute", read_only_sql)
