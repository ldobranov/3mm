"""V2 shares immutable ZIP lifecycle, authority and restore artifact boundaries."""

import copy
import hashlib
import io
import json
import struct
import zipfile
import zlib

import pytest
from sqlalchemy import select

from backend.db.module import ModulePackage
from backend.services.module_packages import ModulePackageError, validate_module_package
from backend.tests.test_theme_extension_packages import manifest, package
from backend.tests.test_theme_extension_lifecycle import BASE, runtime, upload  # noqa: F401
from three_mm_protocol.theme_extension_v2 import DESIGN_DEFAULTS


def png(width=1, height=1, pixels=None):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(pixels if pixels is not None else b"\0\0\x80\x80\xff")) + chunk(b"IEND", b""))


def definition_v2():
    return {"theme_extension_version": 2, "design_api_version": 2, "module_id": "org.example.theme",
            "version": "2.0.0", "name": {"en": "Example v2", "translations": {"bg": "Пример v2"}},
            "base_theme": "builtin.default", "design": {"design_api_version": 2, "scale": {"radius_sm": 0}}, "assets": []}


def v2_package(theme=None, assets=None, extra=None):
    theme = copy.deepcopy(theme or definition_v2())
    assets = assets or {"logo": png()}
    if not theme["assets"]:
        theme["assets"] = [{"asset_id": key, "path": f"assets/{key}.png", "role": "logo_light",
                            "media_type": "image/png", "sha256": hashlib.sha256(data).hexdigest()} for key, data in assets.items()]
    metadata = manifest()
    metadata["version"] = theme["version"]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(metadata))
        archive.writestr("theme-extension.json", json.dumps(theme))
        for asset, data in zip(theme["assets"], assets.values()):
            archive.writestr(asset["path"], data)
        if extra:
            archive.writestr(extra, "forbidden")
    return output.getvalue()


def install_v2(client, admin, blob=None):
    response = client.post("/api/v1/modules/packages", headers=admin,
                           files={"package": ("theme.zip", blob or v2_package(), "application/zip")})
    assert response.status_code == 200, response.text
    digest = response.json()["sha256"]
    assert client.post(f"{BASE}/packages/{digest}/enable", headers=admin).status_code == 200
    return digest


def test_v2_defaults_zero_radius_and_v1_coexistence():
    result = validate_module_package(v2_package(), architecture="armv6l")
    assert result.theme_extension.design["light"] == DESIGN_DEFAULTS["light"]
    assert result.theme_extension.design["scale"]["radius_sm"] == 0
    assert result.compiled_ui is result.application_extension is None
    assert validate_module_package(package()).theme_extension.theme_extension_version == 1


@pytest.mark.parametrize("design", [
    {"design_api_version": 3}, {"design_api_version": True},
    {"design_api_version": 2, "css": "*{}"}, {"design_api_version": 2, "light": {"text": "#ffffff"}},
    {"design_api_version": 2, "scale": {"radius_sm": True}}, {"design_api_version": 2, "typography": {"font": "https://example.test"}},
    {"design_api_version": 2, "layout": {"sidebar_width": 10000}}, {"design_api_version": 2, "light": None},
])
def test_closed_design_rejected_before_install(design):
    theme = definition_v2()
    theme["design"] = design
    with pytest.raises(ModulePackageError):
        validate_module_package(v2_package(theme))


@pytest.mark.parametrize("change", [
    {"path": "../logo.png"}, {"path": "assets/./logo.png"}, {"path": "assets\\logo.png"},
    {"path": "assets/logo.svg"}, {"path": "https://example.test/logo.png"}, {"asset_id": "../../logo"},
    {"sha256": "0" * 64}, {"media_type": "font/woff2"}, {"role": "arbitrary"}, {"url": "https://example.test"},
])
def test_asset_declarations_fail_closed(change):
    theme = definition_v2()
    theme["assets"] = [{"asset_id": "logo", "path": "assets/logo.png", "role": "logo_light",
                        "media_type": "image/png", "sha256": hashlib.sha256(png()).hexdigest(), **change}]
    with pytest.raises(ModulePackageError):
        validate_module_package(v2_package(theme))


@pytest.mark.parametrize("content", [b"<svg onload='bad()'/>", png(2049), png(pixels=b"\0" * 50000), png() + b"extra", png()[:-1], b"x" * (1024 * 1024 + 1)],
                         ids=["wrong-type", "dimensions", "expanded-budget", "trailing-bytes", "truncated", "file-budget"])
def test_image_signature_dimensions_expansion_and_size_budget(content):
    with pytest.raises(ModulePackageError):
        validate_module_package(v2_package(assets={"logo": content}))


@pytest.mark.parametrize("extra", ["theme.css", "theme.js", "assets/extra.png", "assets/./logo.png"])
def test_no_undeclared_files_even_with_assets(extra):
    with pytest.raises(ModulePackageError):
        validate_module_package(v2_package(extra=extra))


@pytest.mark.parametrize("media,content", [
    ("font/woff2", b"not a font"), ("font/woff2", b"wOF2" + b"\0" * 100),
    ("image/webp", b"not webp"), ("image/webp", b"RIFF\x04\0\0\0WEBP"),
], ids=["font-signature", "font-budget", "webp-signature", "webp-no-image"])
def test_font_and_webp_container_validation(media, content):
    suffix = "woff2" if media == "font/woff2" else "webp"
    theme = definition_v2()
    theme["assets"] = [{"asset_id": "asset", "path": f"assets/asset.{suffix}",
                        "sha256": hashlib.sha256(content).hexdigest(), "media_type": media,
                        "role": "font" if suffix == "woff2" else "logo_light", "license": "Test-only"}]
    with pytest.raises(ModulePackageError):
        validate_module_package(v2_package(theme, assets={"asset": content}))


def test_font_license_is_required_and_duplicate_roles_are_rejected():
    theme = definition_v2()
    theme["assets"] = [{"asset_id": "font", "path": "assets/font.woff2", "sha256": "a" * 64,
                        "media_type": "font/woff2", "role": "font"}]
    with pytest.raises(ModulePackageError, match="license"):
        validate_module_package(v2_package(theme, assets={"font": b"font"}))
    with pytest.raises(ModulePackageError, match="unique"):
        validate_module_package(v2_package(assets={"one": png(), "two": png()}))


def test_public_assets_require_selected_enabled_exact_package_and_rollback(runtime):
    client, db, admin, user, _, _ = runtime
    old = upload(client, admin).json()["sha256"]
    client.post(f"{BASE}/packages/{old}/enable", headers=admin)
    digest = install_v2(client, admin)
    url = f"{BASE}/packages/{digest}/assets/logo"
    assert client.get(url).status_code == 404  # enabled is not public
    assert client.get(url, headers=admin).status_code == 404
    assert client.post(f"{BASE}/selection", headers=user, json={"sha256": digest}).status_code == 403
    assert client.post(f"{BASE}/selection", json={"sha256": digest}).status_code == 401
    assert client.post(f"{BASE}/selection", headers=admin, json={"sha256": digest}).status_code == 200
    appearance = client.get(f"{BASE}/appearance").json()
    assert appearance["package_sha256"] == digest and "file_path" not in json.dumps(appearance)
    asset = client.get(url)
    assert asset.content == png() and asset.headers["content-type"] == "image/png"
    assert asset.headers["cache-control"] == "no-store" and asset.headers["x-content-type-options"] == "nosniff"
    assert client.get(url.replace("/logo", "/other")).status_code == 404
    # Portable artifact remains one ZIP with its definition and resources, not loose files.
    row = db.scalar(select(ModulePackage).where(ModulePackage.sha256 == digest))
    with zipfile.ZipFile(row.file_path) as archive:
        assert archive.read("assets/logo.png") == png()
    client.post(f"{BASE}/selection", headers=admin, json={"sha256": old})
    assert client.get(url).status_code == 404
    assert client.get(f"{BASE}/appearance").json()["theme"]["theme_extension_version"] == 1
    client.post(f"{BASE}/selection", headers=admin, json={"sha256": digest})
    client.post(f"{BASE}/packages/{digest}/disable", headers=admin)
    assert client.get(url).status_code == 404
    assert client.get(f"{BASE}/appearance").json() == {"theme": None}


def test_corrupt_package_and_unmanaged_asset_path_cannot_block_recovery(runtime, tmp_path):
    client, db, admin, _, _, _ = runtime
    digest = install_v2(client, admin)
    client.post(f"{BASE}/selection", headers=admin, json={"sha256": digest})
    row = db.scalar(select(ModulePackage).where(ModulePackage.sha256 == digest))
    original_path = row.file_path
    row.file_path = str(tmp_path / "outside.zip")
    db.commit()
    assert client.get(f"{BASE}/packages/{digest}/assets/logo").status_code == 409
    row.file_path = original_path
    db.commit()
    from pathlib import Path
    Path(original_path).write_bytes(b"corrupt artifact")
    assert client.get(f"{BASE}/appearance").json() == {"theme": None}
    assert client.get(f"{BASE}/packages/{digest}/assets/logo").status_code == 409
    assert client.post(f"{BASE}/selection", headers=admin, json={"sha256": None}).status_code == 200
    assert client.delete(f"{BASE}/packages/{digest}", headers=admin).status_code == 200


def test_portable_restore_preserves_v2_selection_and_asset_zip(tmp_path, monkeypatch):
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from backend.db.module import ThemeExtensionInstallation
    from backend.services import theme_extensions
    from backend.tests.test_backup_preview import _settings
    from deployment.create_backup import create_backup
    from deployment.portable_backup import create_portable_export, import_portable_backup
    from deployment.restore_backup import restore_backup

    settings = _settings(tmp_path)
    database = tmp_path / "core/3mm.db"
    database.unlink()
    monkeypatch.setattr("backend.config.get_settings", lambda: settings)
    monkeypatch.setattr(theme_extensions, "get_settings", lambda: settings)
    monkeypatch.setattr("logging.config.fileConfig", lambda *args, **kwargs: None)
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    command.upgrade(config, "head")
    blob = v2_package()
    validated = validate_module_package(blob)
    artifact = settings.backend.uploads_dir / "modules" / f"{validated.sha256}.zip"
    artifact.parent.mkdir()
    artifact.write_bytes(blob)
    engine = create_engine(settings.backend.database_url)
    with Session(engine) as db:
        row = ModulePackage(module_id=validated.manifest.module_id, version=validated.manifest.version,
                            manifest=validated.manifest.model_dump(mode="json"), sha256=validated.sha256,
                            size_bytes=len(blob), file_path=str(artifact), registrations=[])
        db.add(row)
        db.flush()
        db.add(ThemeExtensionInstallation(module_package_id=row.id, enabled=True, is_selected=True))
        db.commit()
    engine.dispose()

    class Controller:
        def stop(self, services): pass
        def start(self, services): pass
        def migrate(self): command.upgrade(config, "head")
        def activate_and_verify(self): pass  # No real systemd or devices in this test.

    controller = Controller()
    old_key, new_key = tmp_path / "old.key", tmp_path / "fresh.key"
    backup = create_backup(settings, key_file=old_key, requested_by_user_id=1, controller=controller)
    exported = create_portable_export(settings.backups.storage_dir, old_key, backup.backup_id, "test-password")
    imported = tmp_path / "fresh-backups"
    backup_id = import_portable_backup(exported.path, imported, new_key, "test-password", max_archive_bytes=32 * 1024 * 1024)
    artifact.write_bytes(b"broken after reset")
    target = settings.model_copy(update={"backups": settings.backups.model_copy(update={"storage_dir": imported})})
    result = restore_backup(target, backup_id=backup_id, key_file=new_key, requested_by_user_id=1,
                            runtime=controller, service_ids=(1000, 1000), state_root=tmp_path,
                            host_config=settings.backups.host_config_file, apply_ownership=False)
    assert result.state == "completed" and artifact.read_bytes() == blob
    engine = create_engine(settings.backend.database_url)
    with Session(engine) as db:
        appearance = theme_extensions.theme_appearance(db)
        assert appearance["package_sha256"] == validated.sha256
        assert theme_extensions.selected_theme_asset(db, validated.sha256, "logo") == (png(), "image/png")
    engine.dispose()
