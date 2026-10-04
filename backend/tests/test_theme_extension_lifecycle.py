"""Theme staging/lifecycle, immutable packages and administrator boundary."""

from importlib import import_module
from datetime import UTC, datetime
from pathlib import Path

import backend.database  # noqa: F401 - register the existing metadata
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.audit_log import AuditLog
from backend.db.base import Base
from backend.db.device import Device, DeviceCommand
from backend.db.module import ModulePackage, ThemeExtensionInstallation
from backend.db.settings import Settings
from backend.db.user import User
from backend.routes import modules
from backend.services import theme_extensions
from backend.tests.test_theme_extension_packages import definition, manifest, package
from backend.utils import jwt_utils
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token


BASE = "/api/v1/modules/themes"


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(
        jwt_utils, "SECRET_KEY", "test-only-theme-key-at-least-32-bytes"
    )
    config = type(
        "Config",
        (),
        {"backend": type("Backend", (), {"uploads_dir": tmp_path / "uploads"})()},
    )()
    monkeypatch.setattr(modules, "get_settings", lambda: config)
    monkeypatch.setattr(theme_extensions, "get_settings", lambda: config)
    monkeypatch.setattr(
        modules,
        "compile_ui_package",
        lambda *_args: pytest.fail("A theme must not invoke the Vue compiler"),
    )
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    admin = User(
        username="admin",
        email="admin@example.test",
        hashed_password="unused",
        role="admin",
    )
    user = User(
        username="user",
        email="user@example.test",
        hashed_password="unused",
        role="user",
    )
    db.add_all([admin, user])
    db.commit()
    app = FastAPI()
    app.include_router(modules.router)
    app.dependency_overrides[get_db] = lambda: db
    admin_headers = {
        "Authorization": f"Bearer {create_access_token(str(admin.id), {'role': 'admin'})}"
    }
    # A signed role claim cannot override the real user's role in the database.
    user_headers = {
        "Authorization": f"Bearer {create_access_token(str(user.id), {'role': 'admin'})}"
    }
    with TestClient(app) as client:
        yield client, db, admin_headers, user_headers, admin, config
    db.close()
    engine.dispose()


def upload(client, headers, *, version="1.0.0", color=None):
    metadata, theme = manifest(), definition()
    metadata["version"] = theme["version"] = version
    if color:
        theme["light"]["body_bg"] = color
    return client.post(
        "/api/v1/modules/packages",
        headers=headers,
        files={
            "package": (
                "theme.zip",
                package(theme=theme, metadata=metadata),
                "application/zip",
            ),
        },
    )


def test_upload_is_staged_and_enable_is_pinned_idempotent_and_audited(runtime):
    client, db, admin, _, _, _ = runtime
    response = upload(client, admin)
    assert response.status_code == 200
    digest = response.json()["sha256"]
    staged = client.get(f"{BASE}/catalog", headers=admin).json()["items"][0]
    assert staged["status"] == "staged"
    assert staged["enabled"] is False and staged["is_installed"] is False
    assert staged["name"]["translations"]["bg"] == "Пример"
    assert staged["definition"]["light"]["radius_sm"] == 0
    assert "file_path" not in staged
    enabled = client.post(f"{BASE}/packages/{digest}/enable", headers=admin)
    assert enabled.status_code == 200
    assert enabled.json()["is_available"] is True
    assert enabled.json()["is_selected"] is False  # install does not change appearance
    assert (
        client.post(f"{BASE}/packages/{digest}/enable", headers=admin).status_code
        == 200
    )
    assert len(list(db.scalars(select(ThemeExtensionInstallation)))) == 1
    audit = list(db.scalars(select(AuditLog)))
    assert len(audit) == 1 and audit[0].changes["sha256"] == digest
    assert list(db.scalars(select(DeviceCommand))) == []


def test_theme_lifecycle_is_admin_only_and_revoked_users_are_rejected(runtime):
    client, db, admin, user, actor, _ = runtime
    digest = upload(client, admin).json()["sha256"]
    endpoints = [
        ("get", f"{BASE}/catalog"),
        ("post", f"{BASE}/packages/{digest}/enable"),
        ("post", f"{BASE}/packages/{digest}/disable"),
        ("delete", f"{BASE}/packages/{digest}"),
    ]
    for method, url in endpoints:
        assert getattr(client, method)(url).status_code == 401
        assert getattr(client, method)(url, headers=user).status_code == 403
    assert upload(client, user).status_code == 403
    actor.is_blocked = True
    db.commit()
    assert client.get(f"{BASE}/catalog", headers=admin).status_code == 401
    assert list(db.scalars(select(ThemeExtensionInstallation))) == []


def test_published_theme_versions_are_immutable_and_conflicting_upload_is_cleaned(
    runtime,
):
    client, db, admin, _, _, config = runtime
    original = upload(client, admin).json()
    assert upload(client, admin).json()["sha256"] == original["sha256"]
    assert upload(client, admin, color="#123456").status_code == 409
    assert len(list(db.scalars(select(ModulePackage)))) == 1
    assert [
        path.name for path in (config.backend.uploads_dir / "modules").iterdir()
    ] == [f"{original['sha256']}.zip"]


def test_theme_versions_are_separate_without_silently_upgrading_selection(runtime):
    client, db, admin, _, _, _ = runtime
    digest = upload(client, admin).json()["sha256"]
    client.post(f"{BASE}/packages/{digest}/enable", headers=admin)
    record = db.scalar(select(ThemeExtensionInstallation))
    record.is_selected = True  # simulate the separate T3 selection boundary
    db.commit()
    new_digest = upload(client, admin, version="1.1.0").json()["sha256"]
    client.post(f"{BASE}/packages/{new_digest}/enable", headers=admin)
    items = {
        item["version"]: item
        for item in client.get(f"{BASE}/catalog", headers=admin).json()["items"]
    }
    assert items["1.0.0"]["is_selected"] is True
    assert items["1.1.0"]["is_selected"] is False
    assert items["1.0.0"]["sha256"] == digest
    assert items["1.1.0"]["sha256"] == new_digest


@pytest.mark.parametrize("damage", ["missing", "checksum", "metadata", "crc"])
def test_broken_package_cannot_enable_but_can_disable_and_does_not_break_catalog(
    runtime, damage
):
    client, db, admin, _, _, _ = runtime
    digest = upload(client, admin).json()["sha256"]
    client.post(f"{BASE}/packages/{digest}/enable", headers=admin)
    installation = db.scalar(select(ThemeExtensionInstallation))
    installation.is_selected = True
    stored = db.scalar(select(ModulePackage))
    if damage == "missing":
        Path(stored.file_path).unlink()
    elif damage == "checksum":
        Path(stored.file_path).write_bytes(package() + b"tampered")
    elif damage == "crc":
        Path(stored.file_path).write_bytes(package().replace(b"#FFFFFF", b"#123456", 1))
    else:
        stored.manifest = {**stored.manifest, "name": "Changed metadata"}
    db.commit()
    assert (
        client.post(f"{BASE}/packages/{digest}/enable", headers=admin).status_code
        == 409
    )
    catalog = client.get(f"{BASE}/catalog", headers=admin)
    assert catalog.status_code == 200
    assert catalog.json()["items"][0]["status"] == "unavailable"
    assert catalog.json()["items"][0]["is_available"] is False
    result = client.post(f"{BASE}/packages/{digest}/disable", headers=admin)
    assert result.status_code == 200
    assert result.json()["is_selected"] is False and result.json()["enabled"] is False
    assert client.delete(f"{BASE}/packages/{digest}", headers=admin).status_code == 200


@pytest.mark.parametrize(
    "needle,replacement", [(b"#FFFFFF", b"#123456"), (b"Example", b"Changed")]
)
def test_corrupt_zip_members_are_rejected_during_upload(runtime, needle, replacement):
    client, db, admin, _, _, _ = runtime
    result = client.post(
        "/api/v1/modules/packages",
        headers=admin,
        files={
            "package": (
                "theme.zip",
                package().replace(needle, replacement, 1),
                "application/zip",
            ),
        },
    )
    assert result.status_code == 422
    assert list(db.scalars(select(ModulePackage))) == []


def test_disable_delete_clear_selection_and_preserve_unrelated_settings(runtime):
    client, db, admin, _, _, config = runtime
    digest = upload(client, admin).json()["sha256"]
    client.post(f"{BASE}/packages/{digest}/enable", headers=admin)
    record = db.scalar(select(ThemeExtensionInstallation))
    record.is_selected = True
    db.add(Settings(key="light_body_bg", value="#ABCDEF", language_code="bg"))
    db.commit()
    disabled = client.post(f"{BASE}/packages/{digest}/disable", headers=admin)
    assert disabled.json()["status"] == "disabled"
    assert disabled.json()["is_selected"] is False
    assert (
        client.post(f"{BASE}/packages/{digest}/disable", headers=admin).status_code
        == 200
    )
    client.post(f"{BASE}/packages/{digest}/enable", headers=admin)
    record.is_selected = True
    db.commit()
    assert client.delete(f"{BASE}/packages/{digest}", headers=admin).status_code == 200
    assert client.get(f"{BASE}/catalog", headers=admin).json()["items"] == []
    assert list(db.scalars(select(ThemeExtensionInstallation))) == []
    assert list(db.scalars(select(ModulePackage))) == []
    assert not (config.backend.uploads_dir / "modules" / f"{digest}.zip").exists()
    assert db.scalar(select(Settings)).value == "#ABCDEF"
    assert list(db.scalars(select(AuditLog)))[-1].changes["selection_cleared"] is True


def test_delete_never_follows_an_unmanaged_database_path(runtime, tmp_path):
    client, db, admin, _, _, _ = runtime
    digest = upload(client, admin).json()["sha256"]
    outside = tmp_path / "unrelated.txt"
    outside.write_text("keep me")
    stored = db.scalar(select(ModulePackage))
    stored.file_path = str(outside)
    db.commit()
    assert client.delete(f"{BASE}/packages/{digest}", headers=admin).status_code == 409
    assert outside.read_text() == "keep me"
    assert db.scalar(select(ModulePackage)) is not None


def test_theme_is_not_an_agent_module_and_other_packages_are_not_themes(runtime):
    client, db, admin, _, _, _ = runtime
    digest = upload(client, admin).json()["sha256"]
    device = Device(
        device_id="dev_" + "1" * 32,
        display_name="Agent",
        role="standalone",
        protocol_version="1.0",
        approved_at=datetime.now(UTC),
    )
    db.add(device)
    db.commit()
    result = client.post(
        f"/api/v1/modules/packages/{digest}/devices/{device.device_id}/install",
        headers=admin,
    )
    assert result.status_code == 409 and "not on an Agent" in result.json()["detail"]
    assert list(db.scalars(select(DeviceCommand))) == []
    assert (
        client.post(f"{BASE}/packages/{'f' * 64}/enable", headers=admin).status_code
        == 404
    )
    stored = db.scalar(select(ModulePackage))
    stored.manifest = {**stored.manifest, "entrypoints": {"agent": "something.py"}}
    db.commit()
    assert (
        client.post(f"{BASE}/packages/{digest}/enable", headers=admin).status_code
        == 404
    )
    assert client.get(f"{BASE}/catalog", headers=admin).json()["items"] == []


def test_theme_migration_is_additive_reversible_and_enforces_selection_constraints():
    migration = import_module(
        "backend.alembic.versions.a7bf06b7c8d9_theme_extension_lifecycle"
    )
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        ModulePackage.__table__.create(connection)
        connection.execute(
            ModulePackage.__table__.insert(),
            [
                {
                    "id": index,
                    "module_id": "org.example.theme",
                    "version": f"{index}.0.0",
                    "manifest": {},
                    "sha256": str(index) * 64,
                    "size_bytes": 1,
                    "file_path": "preserved.zip",
                    "registrations": [],
                }
                for index in (1, 2)
            ],
        )
        original = migration.op
        migration.op = Operations(MigrationContext.configure(connection))
        try:
            migration.upgrade()
            assert (
                connection.execute(
                    text("SELECT COUNT(*) FROM module_packages")
                ).scalar_one()
                == 2
            )
            assert (
                connection.execute(
                    text("SELECT COUNT(*) FROM theme_extension_installations")
                ).scalar_one()
                == 0
            )
            indexes = {
                item["name"]
                for item in inspect(connection).get_indexes(
                    "theme_extension_installations"
                )
            }
            assert "uq_theme_extension_selected" in indexes
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "INSERT INTO theme_extension_installations (module_package_id, enabled, is_selected) VALUES (1, 0, 1)"
                    )
                )
            connection.execute(
                text(
                    "INSERT INTO theme_extension_installations (module_package_id, enabled, is_selected) VALUES (1, 1, 1)"
                )
            )
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "INSERT INTO theme_extension_installations (module_package_id, enabled, is_selected) VALUES (2, 1, 1)"
                    )
                )
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "INSERT INTO theme_extension_installations (module_package_id) VALUES (1)"
                    )
                )
            migration.downgrade()
            assert (
                "theme_extension_installations"
                not in inspect(connection).get_table_names()
            )
            assert (
                connection.execute(
                    text("SELECT COUNT(*) FROM module_packages")
                ).scalar_one()
                == 2
            )
        finally:
            migration.op = original
    engine.dispose()
    root = Path(__file__).parents[2]
    assert (
        ScriptDirectory(str(root / "backend/alembic")).get_current_head()
        == migration.revision
    )
    baseline = import_module(
        "backend.alembic.versions.0f1e2d3c4b5a_legacy_schema_baseline"
    )
    assert "theme_extension_installations" not in baseline._baseline_metadata().tables
