import pytest
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401
from backend.db.base import Base
from backend.db.user import User
from backend.routes.backups import router
from backend.services.backups import BackupCatalogResponse, BackupPreviewResponse
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token
from deployment.portable_backup import PORTABLE_MAGIC


@pytest.fixture(autouse=True)
def use_test_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "test-only-key-with-at-least-32-bytes")


def _client() -> tuple[TestClient, Session, str, str]:
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
    db.add_all((admin, viewer))
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


def test_backup_preview_is_admin_only(monkeypatch: pytest.MonkeyPatch) -> None:
    client, db, admin_token, viewer_token = _client()
    monkeypatch.setattr(
        "backend.routes.backups.build_backup_preview",
        lambda _settings: BackupPreviewResponse(
            ready=False,
            manifest=None,
            entry_count=0,
            estimated_backup_bytes=0,
            available_bytes=100,
            minimum_free_after_backup_bytes=64,
            required_available_bytes=64,
            sufficient_space=True,
            storage_path="/var/lib/3mm/backups",
            issues=(),
        ),
    )
    try:
        assert client.get("/api/v1/backups/preview").status_code == 401
        assert (
            client.get(
                "/api/v1/backups/preview",
                headers={"Authorization": f"Bearer {viewer_token}"},
            ).status_code
            == 403
        )
        response = client.get(
            "/api/v1/backups/preview",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["storage_path"] == "/var/lib/3mm/backups"
    finally:
        db.close()


def test_backup_catalog_is_admin_only(monkeypatch: pytest.MonkeyPatch) -> None:
    client, db, admin_token, viewer_token = _client()
    monkeypatch.setattr(
        "backend.routes.backups.list_backup_catalog",
        lambda _path: BackupCatalogResponse(retention_count=5),
    )
    try:
        assert client.get("/api/v1/backups").status_code == 401
        assert client.get(
            "/api/v1/backups",
            headers={"Authorization": f"Bearer {viewer_token}"},
        ).status_code == 403
        response = client.get(
            "/api/v1/backups",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["retention_count"] == 5
    finally:
        db.close()


def test_backup_creation_requires_admin_and_exact_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db, admin_token, viewer_token = _client()
    requested = []
    monkeypatch.setattr(
        "three_mm_runtime.update_helper_client.UpdateHelperClient.request_backup",
        lambda _client, user_id: requested.append(user_id),
    )
    try:
        assert (
            client.post(
                "/api/v1/backups",
                json={"confirmation": "CREATE BACKUP"},
                headers={"Authorization": f"Bearer {viewer_token}"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/backups",
                json={"confirmation": "create"},
                headers={"Authorization": f"Bearer {admin_token}"},
            ).status_code
            == 409
        )
        response = client.post(
            "/api/v1/backups",
            json={"confirmation": "CREATE BACKUP"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 202
        assert response.json() == {"status": "queued"}
        assert len(requested) == 1
    finally:
        db.close()


def test_restore_requires_exact_backup_id_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db, admin_token, _viewer_token = _client()
    requested = []
    monkeypatch.setattr(
        "three_mm_runtime.update_helper_client.UpdateHelperClient.request_restore",
        lambda _client, backup_id, user_id: requested.append((backup_id, user_id)),
    )
    backup_id = "bkp_20260828T120000Z_0123abcd"
    try:
        rejected = client.post(
            "/api/v1/backups/restore",
            json={"backup_id": backup_id, "confirmation": "RESTORE"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        accepted = client.post(
            "/api/v1/backups/restore",
            json={
                "backup_id": backup_id,
                "confirmation": f"RESTORE {backup_id}",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert rejected.status_code == 409
        assert accepted.status_code == 202
        assert requested and requested[0][0] == backup_id
    finally:
        db.close()


def test_portable_export_is_admin_only_and_downloads_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    client, db, admin_token, viewer_token = _client()
    export_id = "a" * 32
    backup_id = "bkp_20260828T120000Z_0123abcd"
    storage = tmp_path / "backups"
    export_dir = storage / "exports"
    export_dir.mkdir(parents=True)
    exported_file = export_dir / f"{export_id}.3mmrecovery"
    exported_file.write_bytes(PORTABLE_MAGIC + b"encrypted")
    settings = SimpleNamespace(
        backups=SimpleNamespace(storage_dir=storage),
        updates=SimpleNamespace(helper_socket=tmp_path / "helper.sock"),
    )
    monkeypatch.setattr("backend.routes.backups.get_settings", lambda: settings)
    monkeypatch.setattr(
        "three_mm_runtime.update_helper_client.UpdateHelperClient.request_portable_export",
        lambda _client, selected, _passphrase, _user_id: {
            "ok": True,
            "status": "ready",
            "export_id": export_id,
            "backup_id": selected,
            "filename": f"{selected}.3mmrecovery",
        },
    )
    payload = {
        "passphrase": "recovery-password",
        "confirmation": f"DOWNLOAD {backup_id}",
    }
    try:
        assert client.post(
            f"/api/v1/backups/{backup_id}/export",
            json=payload,
            headers={"Authorization": f"Bearer {viewer_token}"},
        ).status_code == 403
        prepared = client.post(
            f"/api/v1/backups/{backup_id}/export",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert prepared.status_code == 200
        downloaded = client.get(
            f"/api/v1/backups/exports/{export_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert downloaded.status_code == 200
        assert downloaded.content.startswith(PORTABLE_MAGIC)
        assert not exported_file.exists()
    finally:
        db.close()


def test_portable_restore_upload_is_bounded_and_queued(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    client, db, admin_token, _viewer_token = _client()
    backup_id = "bkp_20260828T120000Z_0123abcd"
    import_dir = tmp_path / "imports"
    settings = SimpleNamespace(
        backups=SimpleNamespace(
            import_dir=import_dir,
            max_import_bytes=1024 * 1024,
        ),
        updates=SimpleNamespace(helper_socket=tmp_path / "helper.sock"),
    )
    monkeypatch.setattr("backend.routes.backups.get_settings", lambda: settings)

    def queue_restore(_client, upload_id, _passphrase, _user_id):
        (import_dir / f"{upload_id}.3mmrecovery").unlink()
        return backup_id

    monkeypatch.setattr(
        "three_mm_runtime.update_helper_client.UpdateHelperClient.request_portable_restore",
        queue_restore,
    )
    try:
        response = client.post(
            "/api/v1/backups/restore-file",
            data={
                "passphrase": "recovery-password",
                "confirmation": "RESTORE FILE",
            },
            files={
                "file": (
                    "device.3mmrecovery",
                    PORTABLE_MAGIC + b"encrypted",
                    "application/octet-stream",
                )
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 202
        assert response.json()["backup_id"] == backup_id
        assert list(import_dir.iterdir()) == []
    finally:
        db.close()
