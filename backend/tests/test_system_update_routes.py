from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401 - register complete model metadata
from backend.db.base import Base
from backend.db.audit_log import AuditLog
from backend.db.user import User
from backend.services.update_staging import (
    PreflightCheck,
    StagedUpdate,
    StagedUpdateResponse,
    UpdateOperationStatus,
)
from backend.routes.system_updates import router
from backend.services.system_updates import (
    CurrentRelease,
    UpdateCheckResponse,
)
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


def response_payload(status: str = "not_checked") -> UpdateCheckResponse:
    return UpdateCheckResponse(
        status=status,
        message="Catalog state",
        repository="ldobranov/3mm",
        repository_url="https://github.com/ldobranov/3mm",
        architecture="aarch64",
        current=CurrentRelease(
            release_id="test-release",
            commit="a" * 40,
            metadata_available=True,
        ),
        update_available=None,
    )


def test_update_status_requires_an_administrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db, admin_token, viewer_token = make_client()
    monkeypatch.setattr(
        "backend.routes.system_updates.read_local_update_status",
        lambda _settings: response_payload(),
    )
    try:
        assert client.get("/api/v1/system-updates/status").status_code == 401
        assert (
            client.get(
                "/api/v1/system-updates/status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            ).status_code
            == 403
        )

        response = client.get(
            "/api/v1/system-updates/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "not_checked"
    finally:
        db.close()


def test_update_check_is_read_only_and_admin_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db, admin_token, viewer_token = make_client()
    selected_channels: list[str] = []

    def check(_settings, *, channel):
        selected_channels.append(channel)
        return response_payload("no_release")

    monkeypatch.setattr("backend.routes.system_updates.check_update_catalog", check)
    try:
        assert (
            client.post(
                "/api/v1/system-updates/check",
                headers={"Authorization": f"Bearer {viewer_token}"},
            ).status_code
            == 403
        )

        response = client.post(
            "/api/v1/system-updates/check",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"channel": "beta"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "no_release"
        assert selected_channels == ["beta"]
    finally:
        db.close()


def staged_response() -> StagedUpdateResponse:
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    return StagedUpdateResponse(
        staged=StagedUpdate(
            release_id="v1.2.0",
            version="1.2.0",
            commit="b" * 40,
            architecture="aarch64",
            artifact_filename="3mm-1.2.0-aarch64.tar.gz",
            artifact_sha256="c" * 64,
            artifact_size_bytes=1234,
            dependencies=["python3"],
            frontend_origin="http://192.168.1.88:8080",
            staged_at=now,
            approval_expires_at=now + timedelta(minutes=30),
            approval_nonce="d" * 64,
            preflight=[
                PreflightCheck(name="archive.identity", passed=True, detail="ok")
            ],
        )
    )


def test_stage_is_admin_only_and_records_a_reviewable_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db, admin_token, viewer_token = make_client()
    monkeypatch.setattr(
        "backend.routes.system_updates.stage_latest_update",
        lambda *_arguments, **_kwargs: staged_response(),
    )
    try:
        forbidden = client.post(
            "/api/v1/system-updates/stage",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert forbidden.status_code == 403

        response = client.post(
            "/api/v1/system-updates/stage",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 201
        assert response.json()["staged"]["release_id"] == "v1.2.0"
        audit = db.execute(select(AuditLog)).scalar_one()
        assert audit.action == "SYSTEM_UPDATE_STAGED"
        assert "approval_nonce" not in audit.changes
        assert audit.changes["channel"] == "stable"
    finally:
        db.close()


def test_apply_requires_admin_and_passes_only_the_explicit_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db, admin_token, viewer_token = make_client()
    calls = []

    def approve(_settings, payload, *, requested_by_user_id, scheduler):
        calls.append((payload, requested_by_user_id, scheduler))
        return UpdateOperationStatus(
            state="queued",
            message="queued",
            release_id="v1.2.0",
            version="1.2.0",
            commit="b" * 40,
            requested_by_user_id=requested_by_user_id,
        )

    monkeypatch.setattr("backend.routes.system_updates.approve_staged_update", approve)
    payload = {
        "release_id": "v1.2.0",
        "approval_nonce": "d" * 64,
        "confirmation": "INSTALL 1.2.0",
    }
    try:
        forbidden = client.post(
            "/api/v1/system-updates/apply",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json=payload,
        )
        assert forbidden.status_code == 403

        response = client.post(
            "/api/v1/system-updates/apply",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=payload,
        )

        assert response.status_code == 202
        assert response.json()["state"] == "queued"
        assert calls[0][0].confirmation == "INSTALL 1.2.0"
        assert calls[0][1] > 0
    finally:
        db.close()
