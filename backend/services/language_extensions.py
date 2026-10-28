"""Language lifecycle is data projection, never an extension code loader."""
import asyncio
import io
import zipfile
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select
from backend.db.audit_log import AuditLog
from backend.db.language_extension import LanguageExtensionInstallation
from backend.db.module import ModulePackage
from backend.services.module_packages import MAX_PACKAGE_BYTES, ModulePackageError, validate_module_package


def language_package(db, sha256):
    package = db.scalar(select(ModulePackage).where(ModulePackage.sha256 == sha256))
    if package is None or (package.manifest.get("entrypoints") or {}).get("ui") != "language-extension.json":
        raise HTTPException(404, "Language package was not found")
    return package


def validated_language(package):
    try:
        with Path(package.file_path).open("rb") as source:
            validated = validate_module_package(source.read(MAX_PACKAGE_BYTES + 1))
    except (OSError, ModulePackageError) as exc:
        raise HTTPException(409, "Language package is missing or invalid") from exc
    if (validated.sha256 != package.sha256 or validated.language_extension is None
            or validated.manifest.model_dump(mode="json") != package.manifest):
        raise HTTPException(409, "Language package identity is invalid")
    return validated.language_extension


def projection(db, package):
    return db.scalar(select(LanguageExtensionInstallation).where(LanguageExtensionInstallation.module_package_id == package.id))


def set_enabled(db, package, enabled, admin=None):
    definition = validated_language(package) if enabled else None
    row = (db.scalar(select(LanguageExtensionInstallation).where(LanguageExtensionInstallation.code == definition.code))
           if definition is not None else projection(db, package))
    if enabled:
        if row is None:
            row = LanguageExtensionInstallation(code=definition.code, module_package_id=package.id)
            db.add(row)
        row.module_package_id = package.id
        row.enabled = True
    elif row is not None and row.module_package_id == package.id:
        row.enabled = False
    if admin is not None:
        db.add(AuditLog(user_id=admin.id, action="UPDATE", entity_type="language_extension",
                        entity_name=package.module_id, changes={"sha256":package.sha256,"enabled":enabled}))
    db.commit()
    return {"module_id":package.module_id,"enabled":enabled,"code":definition.code if definition else row.code if row else None}


def available_languages(db):
    result = ["en"]
    for package, row in db.execute(select(ModulePackage, LanguageExtensionInstallation).join(
            LanguageExtensionInstallation, LanguageExtensionInstallation.module_package_id == ModulePackage.id).where(LanguageExtensionInstallation.enabled.is_(True))):
        try:
            definition = validated_language(package)
            if definition.code == row.code:
                result.append(row.code)
        except HTTPException:
            continue
    return sorted(set(result))


def translations(db, code):
    row = db.scalar(select(LanguageExtensionInstallation).where(LanguageExtensionInstallation.code == code, LanguageExtensionInstallation.enabled.is_(True)))
    package = db.get(ModulePackage, row.module_package_id) if row and row.module_package_id else None
    if package is not None:
        try:
            definition = validated_language(package)
            if definition.code == code:
                return {"language_code":code,"frontend":definition.frontend,"backend":definition.backend,"extensions":{}}
        except HTTPException:
            pass
    return {"language_code":code,"frontend":{},"backend":{},"extensions":{}}


def catalog(db):
    result = []
    for package in db.scalars(select(ModulePackage).order_by(ModulePackage.module_id, ModulePackage.version)):
        if (package.manifest.get("entrypoints") or {}).get("ui") != "language-extension.json":
            continue
        row = projection(db, package)
        definition = None
        try:
            definition = validated_language(package)
        except HTTPException:
            pass
        result.append({"module_id":package.module_id,"version":package.version,"sha256":package.sha256,
                       "name":definition.native_name if definition else package.manifest.get("name",package.module_id),
                       "code":definition.code if definition else None,
                       "enabled":bool(row and row.enabled),"is_installed":row is not None,
                       "status":"unavailable" if definition is None else "active" if row and row.enabled else "inactive"})
    return {"items":result}


def delete_package(db, package, admin):
    # Never delete a shared artifact still used on a device or by another feature.
    from backend.db.module import ModuleInstallation
    if db.scalar(select(ModuleInstallation.id).where(ModuleInstallation.module_package_id == package.id).limit(1)) is not None:
        raise HTTPException(409,"Uninstall the package from devices before deleting it")
    row = projection(db, package)
    if row is not None:
        db.delete(row)
    db.add(AuditLog(user_id=admin.id,action="DELETE",entity_type="language_extension",entity_name=package.module_id))
    db.delete(package)
    db.commit()
    # The immutable content-addressed ZIP is retained as an unreferenced backup;
    # ordinary lifecycle operations never delete arbitrary database file paths.
    return {"status":"deleted","module_id":package.module_id}


class BundledLanguagePackages:
    """Seed shipped data packages once; never re-enable or override a selection."""
    def __init__(self, sessions, settings, root=None):
        self.sessions, self.settings = sessions, settings
        self.root = root or Path(__file__).resolve().parents[2] / "modules"

    async def start(self):
        await asyncio.to_thread(self.seed)

    def stop(self):
        pass

    def seed(self):
        candidates = sorted(self.root.glob("*/language-extension.json"))
        if len(candidates) > 32:
            raise ValueError("too many bundled language packages")
        from backend.db.settings import Settings
        for definition_path in candidates:
            stream = io.BytesIO()
            with zipfile.ZipFile(stream,"w",compression=zipfile.ZIP_DEFLATED) as archive:
                for name in ("manifest.json","language-extension.json"):
                    path = definition_path.parent / name
                    with path.open("rb") as source:
                        data = source.read(512 * 1024 + 1)
                    if len(data) > 512 * 1024:
                        raise ValueError("bundled language package exceeds limits")
                    # Deterministic archive bytes make seeding idempotent.
                    info = zipfile.ZipInfo(name, date_time=(2020,1,1,0,0,0))
                    archive.writestr(info,data)
            blob = stream.getvalue()
            validated = validate_module_package(blob)
            definition = validated.language_extension
            if definition is None:
                raise ValueError("invalid bundled language package")
            databases = self.sessions()
            db = next(databases)
            try:
                marker_key = "bundled_language_package:" + definition.module_id + ":" + definition.version
                marker = db.scalar(select(Settings).where(Settings.key == marker_key, Settings.user_id.is_(None)))
                if marker is not None:
                    continue
                package = db.scalar(select(ModulePackage).where(ModulePackage.module_id == validated.manifest.module_id,
                                                                ModulePackage.version == validated.manifest.version))
                if package is not None:
                    db.add(Settings(key=marker_key,value=validated.sha256))
                    db.commit()
                    continue
                directory = self.settings.backend.uploads_dir.resolve() / "modules"
                directory.mkdir(parents=True,exist_ok=True)
                path = directory / f"{validated.sha256}.zip"
                path.write_bytes(blob)
                package = ModulePackage(module_id=validated.manifest.module_id,version=validated.manifest.version,
                    manifest=validated.manifest.model_dump(mode="json"),sha256=validated.sha256,
                    size_bytes=validated.size_bytes,file_path=str(path),registrations=[])
                db.add(package)
                db.flush()
                row = db.scalar(select(LanguageExtensionInstallation).where(LanguageExtensionInstallation.code == definition.code))
                previous_seed = db.scalar(select(Settings.id).where(
                    Settings.key.startswith("bundled_language_package:" + definition.module_id + ":"),
                    Settings.user_id.is_(None)).limit(1))
                db.add(Settings(key=marker_key,value=validated.sha256))
                if previous_seed is None and row is None:
                    set_enabled(db,package,True)
                else:
                    db.commit()
            finally:
                databases.close()
