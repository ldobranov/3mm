import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401
from backend.config import AppSettings, BackendSettings, BackupSettings, UpdateCatalogSettings
from backend.db.base import Base
from backend.db.user import User
from backend.routes.diagnostics import router
from backend.services.diagnostics import (
    DiagnosticBundle,
    DiagnosticCheck,
    build_diagnostic_bundle,
    redact_diagnostic_data,
    serialize_diagnostic_bundle,
)
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token


def _settings(tmp_path: Path) -> AppSettings:
    database = tmp_path / "3mm.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(64))")
        connection.execute("INSERT INTO alembic_version VALUES ('18d2e3f4a5b6')")
        connection.commit()
    finally:
        connection.close()
    release = tmp_path / "release.json"
    release.write_text(
        json.dumps({"release_id": "beta-test", "commit": "abc123", "branch": "main", "api_token": "must-not-leak"}),
        encoding="utf-8",
    )
    host_config = tmp_path / "3mm.env"
    host_config.write_text("GROQ_API_KEY=must-not-leak\n", encoding="utf-8")
    return AppSettings(
        backend=BackendSettings(database_url=f"sqlite:///{database.as_posix()}"),
        updates=UpdateCatalogSettings(release_metadata_file=release),
        backups=BackupSettings(
            storage_dir=tmp_path / "backups",
            host_config_file=host_config,
        ),
    )


def test_diagnostic_redaction_is_recursive_and_deterministic() -> None:
    source = {
        "password": "plain",
        "nested": {"api_key": "provider-key", "message": "Bearer abc.def"},
        "line": "GROQ_API_KEY=value",
        "url": "https://user:pass@example.com/path",
    }

    first = redact_diagnostic_data(source)
    second = redact_diagnostic_data(source)

    assert first == second
    serialized = json.dumps(first, sort_keys=True)
    assert "plain" not in serialized
    assert "provider-key" not in serialized
    assert "abc.def" not in serialized
    assert "GROQ_API_KEY=value" not in serialized
    assert "user:pass" not in serialized


def test_diagnostic_bundle_contains_health_metadata_but_not_secret_sources(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    bundle = build_diagnostic_bundle(
        settings,
        now=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
        agent_health=lambda: (
            DiagnosticCheck(name="agent", status="ok", summary="Agent health endpoint is ready"),
            {"agent_protocol_version": "1.0", "device_fingerprint": "0123456789ab"},
        ),
    )
    content = serialize_diagnostic_bundle(bundle).decode("utf-8")

    assert bundle.application["database_revision"] == "18d2e3f4a5b6"
    assert bundle.application["device_fingerprint"] == "0123456789ab"
    assert "must-not-leak" not in content
    assert "GROQ_API_KEY" not in content
    assert "passwords, provider keys" in content


@pytest.fixture(autouse=True)
def use_test_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "test-only-key-with-at-least-32-bytes")


def _client() -> tuple[TestClient, Session, str, str]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    admin = User(username="admin", email="admin@example.com", hashed_password=hash_password("test-password"), role="admin")
    viewer = User(username="viewer", email="viewer@example.com", hashed_password=hash_password("test-password"), role="user")
    db.add_all((admin, viewer))
    db.commit()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app), db, create_access_token(str(admin.id), {"role": "admin"}), create_access_token(str(viewer.id), {"role": "user"})


def _bundle() -> DiagnosticBundle:
    return DiagnosticBundle(
        generated_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
        application={"version": "0.3.0-beta.9"},
        system={"architecture": "aarch64"},
        storage={"total_bytes": 100, "used_bytes": 20, "free_bytes": 80},
        operations={"backup_state": "idle"},
        checks=(DiagnosticCheck(name="database", status="ok", summary="healthy"),),
        excluded=("secrets",),
    )


def test_diagnostic_bundle_download_is_admin_only(monkeypatch: pytest.MonkeyPatch) -> None:
    client, db, admin_token, viewer_token = _client()
    monkeypatch.setattr("backend.routes.diagnostics.build_diagnostic_bundle", lambda _settings: _bundle())
    try:
        assert client.get("/api/v1/diagnostics/bundle").status_code == 401
        assert client.get(
            "/api/v1/diagnostics/bundle",
            headers={"Authorization": f"Bearer {viewer_token}"},
        ).status_code == 403
        response = client.get(
            "/api/v1/diagnostics/bundle",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.headers["content-disposition"].startswith("attachment;")
        assert response.json()["schema_version"] == 1
    finally:
        db.close()
