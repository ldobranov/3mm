"""Preview is read-only, exact-version and admin-only; public assets stay selected-only."""

from pathlib import Path

import pytest
from sqlalchemy import select

from backend.db.audit_log import AuditLog
from backend.db.module import ModulePackage, ThemeExtensionInstallation
from backend.db.settings import Settings
from backend.tests.test_theme_extension_lifecycle import BASE, runtime, upload  # noqa: F401
from backend.tests.test_theme_extension_v2 import install_v2, png


def test_preview_does_not_change_selection_or_audit_and_public_assets_stay_private(runtime):
    client, db, admin, _, _, _ = runtime
    old = upload(client, admin).json()["sha256"]
    client.post(f"{BASE}/packages/{old}/enable", headers=admin)
    client.post(f"{BASE}/selection", headers=admin, json={"sha256": old})
    digest = install_v2(client, admin)
    before = client.get(f"{BASE}/appearance").json()
    audit_count = len(list(db.scalars(select(AuditLog))))
    response = client.get(f"{BASE}/preview", params={"sha256": digest}, headers=admin)
    assert response.status_code == 200
    assert response.json()["package_sha256"] == digest
    assert response.json()["theme"]["version"] == "2.0.0"
    assert "file_path" not in str(response.json())
    assert response.headers["cache-control"] == "no-store"
    resource = client.get(f"{BASE}/packages/{digest}/preview/assets/logo", headers=admin)
    assert resource.content == png() and resource.headers["content-type"] == "image/png"
    assert resource.headers["cache-control"] == "no-store"
    assert resource.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"{BASE}/packages/{digest}/assets/logo", headers=admin).status_code == 404
    assert client.get(f"{BASE}/appearance").json() == before
    assert len(list(db.scalars(select(AuditLog)))) == audit_count
    assert db.scalar(select(ThemeExtensionInstallation).where(ThemeExtensionInstallation.is_selected)).module_package_id == db.scalar(select(ModulePackage.id).where(ModulePackage.sha256 == old))
    # Apply still goes through the existing validated selection boundary.
    assert client.post(f"{BASE}/selection", headers=admin, json={"sha256": digest}).status_code == 200
    assert client.get(f"{BASE}/packages/{digest}/assets/logo").content == png()


def test_preview_authority_includes_builtin_assets_and_revocation(runtime):
    client, db, admin, user, actor, _ = runtime
    digest = install_v2(client, admin)
    urls = [f"{BASE}/preview", f"{BASE}/preview?sha256={digest}", f"{BASE}/packages/{digest}/preview/assets/logo"]
    for url in urls:
        assert client.get(url).status_code == 401
        assert client.get(url, headers=user).status_code == 403
    actor.is_blocked = True
    db.commit()
    for url in urls:
        assert client.get(url, headers=admin).status_code == 401


def test_preview_uses_own_saved_preferences_including_builtin(runtime):
    client, db, admin, _, _, _ = runtime
    digest = install_v2(client, admin)
    preferences = '{"navigation":"top","density":"comfortable","button":"outline","card":"raised","header_style":"theme","header_background_color":"#ffffff","header_text_color":"#000000"}'
    db.add_all([
        Settings(key=f"ui_theme_customization:{digest}", value=preferences),
        Settings(key="ui_theme_customization:builtin", value=preferences),
    ])
    db.commit()
    for params in ({"sha256": digest}, {}):
        result = client.get(f"{BASE}/preview", params=params, headers=admin).json()
        assert result["customization"]["navigation"] == "top"
    assert client.get(f"{BASE}/preview", headers=admin).json()["theme"] is None


@pytest.mark.parametrize("state", ["staged", "disabled", "missing", "corrupt", "outside"])
def test_preview_rejects_unavailable_packages_and_never_replaces_active_appearance(runtime, tmp_path, state):
    client, db, admin, _, _, _ = runtime
    digest = install_v2(client, admin)
    row = db.scalar(select(ModulePackage).where(ModulePackage.sha256 == digest))
    installation = db.scalar(select(ThemeExtensionInstallation).where(ThemeExtensionInstallation.module_package_id == row.id))
    if state == "staged":
        db.delete(installation)
    elif state == "disabled":
        installation.enabled = False
    elif state == "missing":
        Path(row.file_path).unlink()
    elif state == "corrupt":
        Path(row.file_path).write_bytes(b"corrupt")
    else:
        outside = tmp_path / "outside.zip"
        outside.write_bytes(Path(row.file_path).read_bytes())
        row.file_path = str(outside)
    db.commit()
    assert client.get(f"{BASE}/packages/{digest}/preview/assets/logo", headers=admin).status_code in (404, 409)
    assert client.get(f"{BASE}/preview", params={"sha256": digest}, headers=admin).status_code == 409
    assert client.get(f"{BASE}/preview", params={"sha256": "../unsafe"}, headers=admin).status_code == 422
    assert client.get(f"{BASE}/preview", params={"sha256": "f" * 64}, headers=admin).status_code == 404
    assert client.get(f"{BASE}/appearance").json()["theme"] is None
