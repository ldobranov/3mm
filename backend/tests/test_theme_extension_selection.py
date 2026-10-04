"""Public appearance, pinned admin selection and broken-package recovery."""

from pathlib import Path
from dataclasses import replace

import pytest
from sqlalchemy import select

from backend.db.audit_log import AuditLog
from backend.db.module import ModulePackage, ThemeExtensionInstallation
from backend.db.settings import Settings
from backend.routes import modules
from backend.services.module_packages import validate_module_package
from backend.tests.test_theme_extension_packages import package
from backend.tests.test_theme_extension_lifecycle import BASE, runtime, upload


def select_package(client, admin, digest):
    return client.post(f"{BASE}/selection", headers=admin, json={"sha256": digest})


def test_theme_screen_rejects_wrong_package_kind_before_storage_or_compilation(
    runtime, monkeypatch
):
    client, db, admin, _, _, config = runtime
    validated = replace(validate_module_package(package()), theme_extension=None)
    monkeypatch.setattr(modules, "validate_module_package", lambda _blob: validated)
    response = client.post(
        "/api/v1/modules/packages?expected_kind=theme",
        headers=admin,
        files={"package": ("not-a-theme.zip", package(), "application/zip")},
    )
    assert response.status_code == 422
    assert not list(db.scalars(select(ModulePackage)))
    assert not (config.backend.uploads_dir / "modules").exists()


def test_public_appearance_is_small_and_does_not_expose_catalog_or_auth(runtime):
    client, db, admin, user, _, _ = runtime
    assert client.get(f"{BASE}/appearance").json() == {"theme": None}
    digest = upload(client, admin).json()["sha256"]
    assert client.get(f"{BASE}/appearance").json() == {"theme": None}
    client.post(f"{BASE}/packages/{digest}/enable", headers=admin)
    assert select_package(client, admin, digest).status_code == 200
    public = client.get(f"{BASE}/appearance")
    assert public.headers["cache-control"] == "no-store"
    assert set(public.json()) == {"theme"}
    theme = public.json()["theme"]
    assert theme["version"] == "1.0.0"
    assert theme["light"]["radius_sm"] == 0
    assert not any(
        key in theme
        for key in ("file_path", "sha256", "enabled", "configuration", "error")
    )
    assert client.get(f"{BASE}/appearance", headers=user).json() == public.json()
    assert client.get(f"{BASE}/catalog").status_code == 401


def test_selection_is_admin_only_requires_enable_and_is_validated(runtime):
    client, db, admin, user, actor, _ = runtime
    digest = upload(client, admin).json()["sha256"]
    assert select_package(client, admin, digest).status_code == 409
    assert select_package(client, {}, digest).status_code == 401
    assert select_package(client, user, digest).status_code == 403
    assert select_package(client, admin, "not-a-hash").status_code == 422
    assert select_package(client, admin, "f" * 64).status_code == 404
    assert (
        client.post(
            f"{BASE}/selection", headers=admin, json={"sha256": None, "enabled": True}
        ).status_code
        == 422
    )
    actor.is_blocked = True
    db.commit()
    assert select_package(client, admin, None).status_code == 401
    assert client.get(f"{BASE}/appearance", headers=admin).json() == {"theme": None}
    assert not list(db.scalars(select(ThemeExtensionInstallation)))


def test_selection_switch_rollback_idempotency_and_legacy_settings(runtime):
    client, db, admin, _, _, _ = runtime
    db.add(Settings(key="light_body_bg", value="#ABCDEF", language_code="bg"))
    db.commit()
    digests = [
        upload(client, admin, version=version).json()["sha256"]
        for version in ("1.0.0", "1.1.0")
    ]
    for digest in digests:
        client.post(f"{BASE}/packages/{digest}/enable", headers=admin)
    for digest in (*digests, digests[0]):
        assert select_package(client, admin, digest).status_code == 200
        selected = [
            item
            for item in client.get(f"{BASE}/catalog", headers=admin).json()["items"]
            if item["is_selected"]
        ]
        assert len(selected) == 1 and selected[0]["sha256"] == digest
    audit_count = len(list(db.scalars(select(AuditLog))))
    assert select_package(client, admin, digests[0]).status_code == 200
    assert len(list(db.scalars(select(AuditLog)))) == audit_count
    assert select_package(client, admin, None).json() == {"theme": None}
    assert db.scalar(select(Settings)).value == "#ABCDEF"
    assert not any(
        item.is_selected for item in db.scalars(select(ThemeExtensionInstallation))
    )


@pytest.mark.parametrize("damage", ["missing", "checksum", "metadata"])
def test_broken_selection_falls_back_publicly_and_can_be_cleared(runtime, damage):
    client, db, admin, _, _, _ = runtime
    digest = upload(client, admin).json()["sha256"]
    client.post(f"{BASE}/packages/{digest}/enable", headers=admin)
    select_package(client, admin, digest)
    stored = db.scalar(select(ModulePackage))
    if damage == "missing":
        Path(stored.file_path).unlink()
    elif damage == "checksum":
        with Path(stored.file_path).open("ab") as source:
            source.write(b"bad")
    else:
        stored.manifest = {**stored.manifest, "name": "tampered"}
        db.commit()
    assert client.get(f"{BASE}/appearance").json() == {"theme": None}
    assert select_package(client, admin, digest).status_code == 409
    assert select_package(client, admin, None).json() == {"theme": None}


@pytest.mark.parametrize("action", ["disable", "delete"])
def test_active_disable_or_delete_updates_public_appearance(runtime, action):
    client, _, admin, _, _, _ = runtime
    digest = upload(client, admin).json()["sha256"]
    client.post(f"{BASE}/packages/{digest}/enable", headers=admin)
    select_package(client, admin, digest)
    if action == "disable":
        client.post(f"{BASE}/packages/{digest}/disable", headers=admin)
    else:
        client.delete(f"{BASE}/packages/{digest}", headers=admin)
    assert client.get(f"{BASE}/appearance").json() == {"theme": None}
