"""Theme catalog and lifecycle using the existing immutable module package store."""

import logging
import io
import re
import zipfile
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.audit_log import AuditLog
from backend.db.module import (
    ApplicationExtensionInstallation,
    ModuleInstallation,
    ModulePackage,
    ThemeExtensionInstallation,
)
from backend.db.user import User
from backend.services.theme_customization import read_customization
from backend.services.module_packages import (
    MAX_PACKAGE_BYTES,
    ModulePackageError,
    ValidatedModulePackage,
    validate_module_package,
)


logger = logging.getLogger(__name__)


def is_theme_package(package: ModulePackage) -> bool:
    return (package.manifest.get("entrypoints") or {}).get(
        "ui"
    ) == "theme-extension.json"


def theme_package(db: Session, sha256: str) -> ModulePackage:
    package = db.scalar(select(ModulePackage).where(ModulePackage.sha256 == sha256))
    if package is None or not is_theme_package(package):
        raise HTTPException(404, "Theme package was not found")
    return package


def validate_stored_theme(package: ModulePackage, contents: bytes | None = None) -> ValidatedModulePackage:
    try:
        if contents is None:
            with Path(package.file_path).open("rb") as source:
                contents = source.read(MAX_PACKAGE_BYTES + 1)
        validated = validate_module_package(contents)
    except (OSError, ModulePackageError) as exc:
        raise HTTPException(
            409, "Theme package is missing or could not be validated"
        ) from exc
    if (
        validated.theme_extension is None
        or validated.sha256 != package.sha256
        or validated.manifest.module_id != package.module_id
        or validated.manifest.version != package.version
        or validated.manifest.model_dump(mode="json") != package.manifest
    ):
        raise HTTPException(409, "Theme package identity or checksum is invalid")
    return validated


def installation_for(
    db: Session, package: ModulePackage
) -> ThemeExtensionInstallation | None:
    return db.scalar(
        select(ThemeExtensionInstallation).where(
            ThemeExtensionInstallation.module_package_id == package.id,
        )
    )


def catalog_item(
    package: ModulePackage,
    installation: ThemeExtensionInstallation | None,
    validated: ValidatedModulePackage | None = None,
) -> dict:
    error = None
    if validated is None:
        try:
            validated = validate_stored_theme(package)
        except HTTPException as exc:
            error = exc.detail
    theme = validated.theme_extension if validated is not None else None
    enabled = installation is not None and bool(installation.enabled)
    selected = installation is not None and bool(installation.is_selected)
    return {
        "module_id": package.module_id,
        "version": package.version,
        "sha256": package.sha256,
        "size_bytes": package.size_bytes,
        "name": (
            theme.name.model_dump(mode="json")
            if theme
            else {"en": package.manifest.get("name") or package.module_id}
        ),
        "is_installed": installation is not None,
        "enabled": enabled,
        "is_selected": selected,
        "is_available": enabled and theme is not None,
        "status": (
            "unavailable"
            if error
            else (
                "staged"
                if installation is None
                else "enabled" if enabled else "disabled"
            )
        ),
        "error": error,
        "definition": (
            theme.model_dump(mode="json", exclude_none=True) if theme else None
        ),
    }


def theme_catalog(db: Session) -> dict:
    installations = {
        row.module_package_id: row
        for row in db.scalars(select(ThemeExtensionInstallation))
    }
    packages = db.scalars(
        select(ModulePackage).order_by(ModulePackage.module_id, ModulePackage.version)
    )
    return {
        "items": [
            catalog_item(package, installations.get(package.id))
            for package in packages
            if is_theme_package(package)
        ]
    }


def theme_appearance(db: Session) -> dict:
    """Public projection: only the selected, revalidated design; never a catalog."""
    package = db.scalar(
        select(ModulePackage)
        .join(ThemeExtensionInstallation)
        .where(
            ThemeExtensionInstallation.is_selected.is_(True),
            ThemeExtensionInstallation.enabled.is_(True),
        )
    )
    if package is not None:
        try:
            theme = validate_stored_theme(package).theme_extension
            result = {"theme": theme.model_dump(mode="json", exclude_none=True)}
            if theme.theme_extension_version == 2:
                result["package_sha256"] = package.sha256
            customization = read_customization(db, package.sha256, theme)
            if customization is not None:
                result["customization"] = customization
            return result
        except HTTPException:
            # A damaged package must not prevent login or recovery controls.
            logger.warning("Selected theme unavailable: %s", package.sha256)
    result = {"theme": None}
    # Do not apply built-in overrides when recovering from a damaged package.
    if package is None:
        customization = read_customization(db, None)
        if customization is not None:
            result["customization"] = customization
    return result


def preview_theme_appearance(db: Session, sha256: str | None) -> dict:
    """Read-only admin projection; never select, enable or write preferences."""
    theme = None
    if sha256 is not None:
        package = theme_package(db, sha256)
        installation = installation_for(db, package)
        if installation is None or not installation.enabled:
            raise HTTPException(409, "Enable the theme before previewing it")
        expected = get_settings().backend.uploads_dir.resolve() / "modules" / f"{sha256}.zip"
        if expected.resolve() != expected or Path(package.file_path).resolve() != expected:
            raise HTTPException(409, "Theme preview is unavailable")
        theme = validate_stored_theme(package).theme_extension
    result = {"theme": theme.model_dump(mode="json", exclude_none=True) if theme else None}
    if theme is not None and theme.theme_extension_version == 2:
        result["package_sha256"] = sha256
    customization = read_customization(db, sha256, theme)
    if customization is not None:
        result["customization"] = customization
    return result


def selected_theme_asset(db: Session, sha256: str, asset_id: str) -> tuple[bytes, str]:
    """Public appearance assets only; never expose staged/catalog or arbitrary paths."""
    return _theme_asset(db, sha256, asset_id, selected_only=True)


def preview_theme_asset(db: Session, sha256: str, asset_id: str) -> tuple[bytes, str]:
    """Admin-only preview uses the same bounded, revalidated immutable bytes."""
    return _theme_asset(db, sha256, asset_id, selected_only=False)


def _theme_asset(db: Session, sha256: str, asset_id: str, *, selected_only: bool) -> tuple[bytes, str]:
    if not re.fullmatch(r"[0-9a-f]{64}", sha256) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", asset_id):
        raise HTTPException(404, "Theme asset was not found")
    query = select(ModulePackage).join(ThemeExtensionInstallation).where(
        ModulePackage.sha256 == sha256,
        ThemeExtensionInstallation.enabled.is_(True),
    )
    if selected_only:
        query = query.where(ThemeExtensionInstallation.is_selected.is_(True))
    package = db.scalar(query)
    if package is None or not is_theme_package(package):
        raise HTTPException(404, "Theme asset was not found")
    root = get_settings().backend.uploads_dir.resolve() / "modules"
    expected = root / f"{sha256}.zip"
    if expected.resolve() != expected or Path(package.file_path).resolve() != expected:
        raise HTTPException(409, "Theme asset is unavailable")
    try:
        with expected.open("rb") as source:
            contents = source.read(MAX_PACKAGE_BYTES + 1)
        if len(contents) > MAX_PACKAGE_BYTES:
            raise HTTPException(409, "Theme asset is unavailable")
        validated = validate_stored_theme(package, contents)
        theme = validated.theme_extension
        asset = next((asset for asset in getattr(theme, "assets", ()) if asset.asset_id == asset_id), None)
        if asset is None:
            raise HTTPException(404, "Theme asset was not found")
        # Same validated bytes: no extract/reopen race or loose file serving.
        with zipfile.ZipFile(io.BytesIO(contents)) as archive:
            return archive.read(asset.path), asset.media_type
    except OSError as exc:
        raise HTTPException(409, "Theme asset is unavailable") from exc


def select_theme(db: Session, sha256: str | None, actor: User) -> dict:
    target = None
    package = None
    if sha256 is not None:
        package = theme_package(db, sha256)
        target = installation_for(db, package)
        if target is None or not target.enabled:
            raise HTTPException(409, "Enable the theme before selecting it")
        validate_stored_theme(package)
    selected = list(
        db.scalars(
            select(ThemeExtensionInstallation).where(
                ThemeExtensionInstallation.is_selected.is_(True)
            )
        )
    )
    if selected == ([target] if target else []):
        return theme_appearance(db)
    for record in selected:
        previous = db.get(ModulePackage, record.module_package_id)
        record.is_selected = False
        audit_theme(db, actor, previous, "UPDATE", {"is_selected": False})
    # Release the unique selected slot before setting another version in the
    # same transaction. Conflicting concurrent selections return a safe 409.
    db.flush()
    if target is not None:
        target.is_selected = True
        audit_theme(db, actor, package, "UPDATE", {"is_selected": True})
    db.commit()
    return theme_appearance(db)


def audit_theme(
    db: Session, actor: User, package: ModulePackage, action: str, changes: dict
) -> None:
    db.add(
        AuditLog(
            user_id=actor.id,
            action=action,
            entity_type="theme_extension",
            entity_id=package.id,
            entity_name=f"{package.module_id}@{package.version}",
            changes={"sha256": package.sha256, **changes},
        )
    )


def enable_theme(db: Session, package: ModulePackage, actor: User) -> dict:
    validated = validate_stored_theme(package)
    record = installation_for(db, package)
    if record is None:
        record = ThemeExtensionInstallation(
            module_package_id=package.id, enabled=True, is_selected=False
        )
        db.add(record)
        audit_theme(db, actor, package, "CREATE", {"enabled": True})
    elif not record.enabled:
        record.enabled = True
        audit_theme(db, actor, package, "UPDATE", {"enabled": True})
    db.commit()
    return catalog_item(package, record, validated)


def disable_theme(db: Session, package: ModulePackage, actor: User) -> dict:
    # Do not require the ZIP to be healthy in order to recover from a broken theme.
    record = installation_for(db, package)
    if record is not None and (record.enabled or record.is_selected):
        was_selected = bool(record.is_selected)
        record.enabled = False
        record.is_selected = False
        audit_theme(
            db,
            actor,
            package,
            "UPDATE",
            {"enabled": False, "selection_cleared": was_selected},
        )
        db.commit()
    return catalog_item(package, record)


def delete_theme(db: Session, package: ModulePackage, actor: User) -> dict:
    # Never follow a damaged/tampered database path outside the existing upload store.
    root = get_settings().backend.uploads_dir.resolve() / "modules"
    expected = root / f"{package.sha256}.zip"
    if (
        expected.parent.resolve() != root
        or Path(package.file_path).resolve() != expected
    ):
        raise HTTPException(409, "Theme package is outside the managed upload store")
    if (
        db.scalar(
            select(ModuleInstallation.id)
            .where(
                ModuleInstallation.module_package_id == package.id,
            )
            .limit(1)
        )
        is not None
        or db.scalar(
            select(ApplicationExtensionInstallation.id)
            .where(
                or_(
                    ApplicationExtensionInstallation.module_package_id == package.id,
                    ApplicationExtensionInstallation.previous_package_id == package.id,
                )
            )
            .limit(1)
        )
        is not None
    ):
        raise HTTPException(409, "Theme package is referenced by another installation")
    record = installation_for(db, package)
    was_selected = record is not None and bool(record.is_selected)
    audit_theme(db, actor, package, "DELETE", {"selection_cleared": was_selected})
    if record is not None:
        db.delete(record)
        db.flush()
    result = {
        "status": "deleted",
        "module_id": package.module_id,
        "version": package.version,
        "sha256": package.sha256,
    }
    db.delete(package)
    db.commit()
    try:
        expected.unlink(missing_ok=True)
    except OSError:
        logger.warning(
            "Theme package metadata removed; artifact cleanup pending for %s",
            result["sha256"],
        )
        result["artifact_cleanup_pending"] = True
    return result
