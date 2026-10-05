"""Settings assets must survive immutable updates and portable recovery."""

import shutil
from pathlib import Path

import backend.database  # noqa: F401 - register existing database metadata
import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.config import AppSettings, BackendSettings
from backend.db.base import Base
from backend.db.user import User
from backend.routes import settings as routes
from backend.services import asset_storage
from backend.services.asset_storage import (
    AssetPathError,
    AssetStorage,
    get_asset_storage,
)
from backend.services.backups import build_backup_preview
from backend.tests.test_backup_preview import _settings
from backend.utils import jwt_utils
from backend.utils.db_utils import get_db
from deployment.create_backup import create_backup
from deployment.portable_backup import create_portable_export, import_portable_backup
from deployment.restore_backup import restore_backup


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    config = AppSettings(
        backend=BackendSettings(uploads_dir=tmp_path / "state/uploads")
    )
    monkeypatch.setattr(routes, "get_settings", lambda: config)
    monkeypatch.setattr(
        jwt_utils, "SECRET_KEY", "test-only-assets-key-at-least-32-bytes"
    )
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    user = User(
        username="user",
        email="user@example.test",
        hashed_password="unused",
        role="user",
    )
    db.add(user)
    db.commit()
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.mount(
        "/uploads",
        StaticFiles(directory=get_asset_storage(config).directory(create=True)),
    )
    headers = {"Authorization": f"Bearer {jwt_utils.create_access_token(str(user.id))}"}
    with TestClient(app) as client:
        yield client, headers, config, db, user
    db.close()
    engine.dispose()


def upload(client, headers, endpoint="/api/settings/upload-image", **kwargs):
    return client.post(
        endpoint,
        headers=headers,
        files={"file": ("logo.png", b"image-data", "image/png")},
        **kwargs,
    )


def test_upload_uses_persistent_storage_independent_of_release(
    runtime, monkeypatch, tmp_path
):
    client, headers, config, *_ = runtime
    release = tmp_path / "releases/beta.38"
    release.mkdir(parents=True)
    monkeypatch.chdir(release)
    monkeypatch.setattr(routes, "__file__", str(release / "backend/routes/settings.py"))
    response = upload(client, headers)
    assert response.status_code == 200
    asset = response.json()
    stored = config.backend.uploads_dir / "settings" / asset["filename"]
    assert stored.read_bytes() == b"image-data"
    assert client.get(asset["url"]).content == b"image-data"
    assert (
        client.get("/api/settings/images/list").json()["images"][0]["url"]
        == asset["url"]
    )
    assert (
        client.get("/api/images/list?directory=uploads/settings").json()["count"] == 1
    )
    next_release = tmp_path / "releases/beta.39"
    next_release.mkdir()
    monkeypatch.chdir(next_release)
    monkeypatch.setattr(
        routes, "__file__", str(next_release / "backend/routes/settings.py")
    )
    assert client.get(asset["url"]).content == b"image-data"
    assert not list(release.iterdir())
    assert not list(next_release.iterdir())


def test_legacy_logo_upload_preserves_stable_url(runtime):
    client, headers, config, *_ = runtime
    response = upload(client, headers, "/upload/settings-image")
    assert response.status_code == 200
    assert response.json()["url"] == "/uploads/settings/logo.png"
    response = client.post(
        "/upload/settings-image",
        headers=headers,
        files={"file": ("logo.png", b"replacement", "image/png")},
    )
    assert response.status_code == 200
    assert (
        config.backend.uploads_dir / "settings/logo.png"
    ).read_bytes() == b"replacement"


def test_read_only_listing_does_not_create_settings_directory(runtime):
    client, _, config, *_ = runtime
    response = client.get("/api/settings/images/list")
    assert response.status_code == 200
    assert response.json()["images"] == []
    assert not (config.backend.uploads_dir / "settings").exists()


def test_form_directory_and_query_directory_use_same_settings_namespace(runtime):
    client, headers, config, *_ = runtime
    response = client.post(
        "/api/settings/images/folder",
        headers=headers,
        json={"folder_name": "Brand logos", "directory": "settings"},
    )
    assert response.status_code == 200
    for arguments in (
        {"data": {"directory": "settings/Brand logos"}},
        {"params": {"directory": "settings/Brand logos"}},
    ):
        response = upload(client, headers, **arguments)
        assert response.status_code == 200
        assert (
            config.backend.uploads_dir
            / "settings/Brand logos"
            / response.json()["filename"]
        ).is_file()
        assert client.get(response.json()["url"]).content == b"image-data"
    assert (
        client.get(
            "/api/settings/images/list", params={"directory": "settings/Brand logos"}
        ).json()["total"]
        == 2
    )


def test_rename_and_delete_use_persistent_root(runtime):
    client, headers, config, *_ = runtime
    original = upload(client, headers).json()["filename"]
    response = client.post(
        "/api/settings/images/rename",
        headers=headers,
        json={"current_name": original, "new_name": "Brand logo.png"},
    )
    assert response.status_code == 200
    assert client.get(response.json()["new_url"]).content == b"image-data"
    response = client.request(
        "DELETE",
        "/api/settings/images/delete",
        headers=headers,
        json={"image_name": "Brand logo.png"},
    )
    assert response.status_code == 200
    assert not list((config.backend.uploads_dir / "settings").iterdir())


@pytest.mark.parametrize(
    "endpoint", ["/upload/settings-image", "/api/settings/upload-image"]
)
def test_upload_requires_active_user(runtime, endpoint):
    client, headers, _, db, user = runtime
    assert upload(client, {}, endpoint).status_code == 401
    user.is_blocked = True
    db.commit()
    assert upload(client, headers, endpoint).status_code == 401


@pytest.mark.parametrize(
    "endpoint", ["/upload/settings-image", "/api/settings/upload-image"]
)
def test_upload_limits_are_validation_errors_not_500(runtime, endpoint):
    client, headers, *_ = runtime
    for content, media_type in [
        (b"text", "text/plain"),
        (b"x" * (2 * 1024 * 1024 + 1), "image/png"),
    ]:
        response = client.post(
            endpoint,
            headers=headers,
            files={"file": ("logo.png", content, media_type)},
        )
        assert response.status_code == 400


def test_settings_operations_reject_namespace_escape(runtime):
    client, headers, config, *_ = runtime
    outside = config.backend.uploads_dir.parent / "keep.png"
    outside.write_bytes(b"do-not-change")
    assert (
        upload(client, headers, data={"directory": "settings/../../"}).status_code
        == 400
    )
    assert upload(client, headers, params={"directory": "store"}).status_code == 400
    assert client.get("/api/settings/images/list?directory=../").status_code == 400
    assert (
        client.post(
            "/api/settings/images/folder",
            headers=headers,
            json={"directory": "../", "folder_name": "bad"},
        ).status_code
        == 400
    )
    assert (
        client.request(
            "DELETE",
            "/api/settings/images/delete",
            headers=headers,
            json={"image_name": "../../keep.png"},
        ).status_code
        == 400
    )
    original = upload(client, headers).json()["filename"]
    assert (
        client.post(
            "/api/settings/images/rename",
            headers=headers,
            json={"current_name": original, "new_name": "../../keep.png"},
        ).status_code
        == 400
    )
    assert outside.read_bytes() == b"do-not-change"


@pytest.mark.parametrize(
    "relative",
    [
        "../settings",
        "/settings",
        "settings/../store",
        "settings\\bad",
        "C:/outside",
        "settings//bad",
    ],
)
def test_storage_rejects_unsafe_paths(tmp_path, relative):
    with pytest.raises(AssetPathError):
        AssetStorage(tmp_path / "uploads").directory(relative, create=True)


def test_storage_extension_namespace_and_atomic_failure(tmp_path, monkeypatch):
    storage = AssetStorage(tmp_path / "uploads")
    assert (
        storage.extension_dir("org.example.asset", create=True)
        == storage.root / "extensions/org.example.asset"
    )
    with pytest.raises(AssetPathError):
        storage.extension_dir("../escape")
    path = storage.write_bytes("settings", "logo.png", b"original")

    def reject_replace(*_args):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(asset_storage.os, "replace", reject_replace)
    with pytest.raises(OSError, match="simulated disk failure"):
        storage.write_bytes("settings", "logo.png", b"replacement")
    assert path.read_bytes() == b"original"
    assert list(storage.settings_dir().iterdir()) == [path]


def test_storage_rejects_symlink_escape(tmp_path):
    storage = AssetStorage(tmp_path / "uploads")
    outside = tmp_path / "outside"
    outside.mkdir()
    settings_dir = storage.settings_dir(create=True)
    try:
        (settings_dir / "escape").symlink_to(outside, target_is_directory=True)
        (outside / "keep.png").write_bytes(b"keep")
        (settings_dir / "logo.png").symlink_to(outside / "keep.png")
    except OSError:
        pytest.skip("Symlink creation is unavailable on this host")
    with pytest.raises(AssetPathError):
        storage.directory("settings/escape", create=True)
    with pytest.raises(AssetPathError):
        storage.write_bytes("settings", "logo.png", b"bad")
    assert (outside / "keep.png").read_bytes() == b"keep"


def test_settings_logo_survives_portable_backup_restore_with_new_key(tmp_path):
    config = _settings(tmp_path)
    storage = get_asset_storage(config)
    storage.write_bytes("settings", "logo.png", b"original-logo")
    preview = build_backup_preview(config)
    assert preview.ready
    assert any(
        entry.area == "core" and entry.path == "uploads/settings/logo.png"
        for entry in preview.manifest.entries
    )

    class BackupController:
        def stop(self, _services):
            pass

        def start(self, _services):
            pass

    key = tmp_path / "keys/backup.key"
    backup = create_backup(
        config, key_file=key, requested_by_user_id=7, controller=BackupController()
    )
    exported = create_portable_export(
        config.backups.storage_dir, key, backup.backup_id, "recovery-password"
    )
    imported_file = tmp_path / "uploaded.3mmrecovery"
    shutil.copyfile(exported.path, imported_file)
    new_key = tmp_path / "fresh-keys/backup.key"
    new_catalog = tmp_path / "fresh-backups"
    new_catalog.mkdir()
    imported_id = import_portable_backup(
        imported_file,
        new_catalog,
        new_key,
        "recovery-password",
        max_archive_bytes=32 * 1024 * 1024,
    )
    storage.file("settings", "logo.png").unlink()
    recovered_config = config.model_copy(
        update={
            "backups": config.backups.model_copy(update={"storage_dir": new_catalog})
        }
    )

    class RestoreController:
        def stop(self, _services):
            pass

        def migrate(self):
            pass

        def activate_and_verify(self):
            pass

    result = restore_backup(
        recovered_config,
        backup_id=imported_id,
        key_file=new_key,
        requested_by_user_id=7,
        runtime=RestoreController(),
        service_ids=(1000, 1000),
        state_root=tmp_path,
        host_config=config.backups.host_config_file,
        apply_ownership=False,
    )
    assert result.state == "completed"
    assert storage.file("settings", "logo.png").read_bytes() == b"original-logo"
