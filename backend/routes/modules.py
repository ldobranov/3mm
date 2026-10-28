"""Validated module catalog and per-device lifecycle API."""
import hashlib
import json
import re
import shutil
import zipfile
import zlib
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from backend.config import get_settings
from backend.db.device import Device
from backend.db.module import (
    ApplicationExtensionInstallation,
    ModuleInstallation,
    ModulePackage,
)
from backend.db.module_reference import ModulePackageRetainedReference
from backend.db.user import User
from backend.services import device_module_management as module_management
from backend.services.device_module_management import InstallationResponse
from backend.services.module_packages import MAX_PACKAGE_BYTES, ModulePackageError, validate_module_package
from backend.services.module_inspection import PackageInspectionResponse, describe_module_package
from backend.services.application_authority_inspection import (
    AuthorityInspectionBaseline,
    inspect_application_authority,
)
from backend.version import core_version
from backend.services.compiled_ui import (
    CompiledUiBuildError,
    compile_ui_package,
    compiled_artifacts_dir,
    load_compiled_ui_artifact,
    application_ui_artifact,
)
from backend.services.application_access import (
    application_permission_ids,
    can_access_application_route,
    resolve_application_principal,
)
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from three_mm_protocol.module_manifest import MODULE_ID_PATTERN, SEMVER_PATTERN
from backend.routes.theme_extensions import router as theme_extensions_router

router=APIRouter(prefix="/api/v1/modules",tags=["modules"])
router.include_router(theme_extensions_router)

class PackageResponse(BaseModel):
    module_id:str; version:str; sha256:str; size_bytes:int; manifest:dict; registrations:list[dict]
    has_connector_settings: bool = False
    has_kiosk_interface: bool = False
    model_config=ConfigDict(from_attributes=True)



def _validated_compiled_package(package: ModulePackage):
    try:
        blob = Path(package.file_path).read_bytes()
        validated = validate_module_package(blob)
    except ModulePackageError as exc:
        raise HTTPException(409, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(409, "compiled UI package is no longer valid") from exc
    if validated.sha256 != package.sha256 or validated.compiled_ui is None:
        raise HTTPException(409, "compiled UI package identity is invalid")
    return validated


def _compiled_catalog_item(
    package: ModulePackage,
    db: Session,
    authorization: str | None,
) -> dict | None:
    validated = _validated_compiled_package(package)
    application = validated.application_extension
    if application is None:
        try:
            artifact = load_compiled_ui_artifact(validated)
        except CompiledUiBuildError as exc:
            raise HTTPException(409, str(exc)) from exc
    base = f"/api/v1/modules/compiled-ui/assets/{package.module_id}/{package.version}/{package.sha256}"
    entrypoints = []
    route_policies = (
        {item.entrypoint_id: item for item in application.routes}
        if application is not None
        else {}
    )
    principal = resolve_application_principal(authorization, db)
    installation = None
    permission_ids: frozenset[str] = frozenset()
    if application is not None:
        installation = db.scalar(
            select(ApplicationExtensionInstallation).where(
                ApplicationExtensionInstallation.module_package_id == package.id,
                ApplicationExtensionInstallation.enabled.is_(True),
                ApplicationExtensionInstallation.status == "active",
            )
        )
        if installation is None:
            return None
        try:
            artifact = application_ui_artifact(db, installation, validated)
        except CompiledUiBuildError:
            return None  # One unreviewed application must not hide unrelated UI.
        if principal.kind == "user" and principal.user_id is not None:
            permission_ids = application_permission_ids(
                db,
                installation.id,
                principal.user_id,
            )
    if artifact.built_ui_sha256:
        base += f'/build/{artifact.built_ui_sha256}'
    for entrypoint in validated.compiled_ui.entrypoints:
        policy = route_policies.get(entrypoint.entrypoint_id)
        if application is not None:
            if policy is None or not can_access_application_route(
                policy,
                principal,
                module_id=application.module_id,
                permission_ids=permission_ids,
            ):
                continue
        entrypoints.append(
            {
                **entrypoint.model_dump(mode="json"),
                "asset_url": f"{base}/{artifact.entrypoints[entrypoint.entrypoint_id]}",
                **(
                    {
                        "application_audience": policy.audience,
                        "required_permissions": list(policy.required_permissions),
                        "navigation": policy.navigation,
                        "menu_order": policy.order,
                    }
                    if policy is not None
                    else {}
                ),
            }
        )
    if application is not None and not entrypoints:
        return None
    return {
        "module_id": package.module_id,
        "name": package.manifest.get("name") or package.module_id,
        "version": package.version,
        "source_sha256": package.sha256,
        **({'built_ui_sha256': artifact.built_ui_sha256} if artifact.built_ui_sha256 else {}),
        "styles": [f"{base}/{path}" for path in artifact.styles],
        "entrypoints": entrypoints,
    }


def _application_package_is_active(package: ModulePackage, db: Session) -> bool:
    if (package.manifest.get("entrypoints") or {}).get("core") != "application-extension.json":
        return True
    return db.scalar(
        select(ApplicationExtensionInstallation.id).where(
            ApplicationExtensionInstallation.module_package_id == package.id,
            ApplicationExtensionInstallation.enabled.is_(True),
            ApplicationExtensionInstallation.status == "active",
        )
    ) is not None


@router.post(
    "/packages/inspect",
    response_model=PackageInspectionResponse,
    openapi_extra={"requestBody": {"required": True, "content": {
        "application/zip": {"schema": {"type": "string", "format": "binary"}}
    }}},
)
async def inspect_package(
    request: Request,
    response: Response,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    include_authority_review: bool = False,
):
    """Bounded in-memory ZIP review; deliberately not the multipart upload path."""
    response.headers["Cache-Control"] = "no-store"
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in {"application/zip", "application/octet-stream"}:
        raise HTTPException(415, "Send a manifest-v2 ZIP as the raw request body")
    length = request.headers.get("content-length")
    normalized_length = length.lstrip("0") if length else ""
    if length and length.isdecimal() and (
        len(normalized_length) > 8 or int(normalized_length or "0") > MAX_PACKAGE_BYTES
    ):
        raise HTTPException(413, "module package exceeds the 10 MiB size limit")
    blob = bytearray()
    async for chunk in request.stream():
        if len(blob) + len(chunk) > MAX_PACKAGE_BYTES:
            raise HTTPException(413, "module package exceeds the 10 MiB size limit")
        blob.extend(chunk)
    version = core_version()
    try:
        validated = await run_in_threadpool(
            validate_module_package, bytes(blob), core_version=version,
        )
    except (ModulePackageError, zipfile.BadZipFile, zlib.error, RuntimeError,
            NotImplementedError, RecursionError, UnicodeError) as exc:
        raise HTTPException(422, f"Package inspection failed (manifest v2 required): {str(exc)[:1000]}") from exc
    # Even a caller's pending ORM state must not be flushed by this read operation.
    with db.no_autoflush:
        existing_sha256 = db.scalar(select(ModulePackage.sha256).where(
            ModulePackage.module_id == validated.manifest.module_id,
            ModulePackage.version == validated.manifest.version,
        ))
    result = describe_module_package(
        validated, core_version=version, existing_sha256=existing_sha256,
    )
    if include_authority_review:
        baseline = None
        if validated.application_extension is not None:
            # Only the actual installation pointer selects the old artifact; never
            # a caller ID, uploaded version, or lexicographically newest catalog row.
            with db.no_autoflush:
                row = db.execute(select(
                    ModulePackage.module_id, ModulePackage.version, ModulePackage.sha256,
                    ApplicationExtensionInstallation.active_version,
                    ApplicationExtensionInstallation.status,
                    ApplicationExtensionInstallation.configuration,
                ).select_from(ApplicationExtensionInstallation).outerjoin(
                    ModulePackage,
                    ModulePackage.id == ApplicationExtensionInstallation.module_package_id,
                ).where(
                    ApplicationExtensionInstallation.module_id == validated.manifest.module_id,
                )).one_or_none()
                if row is not None:
                    baseline = AuthorityInspectionBaseline(*row)
        result.authority_review = await run_in_threadpool(
            inspect_application_authority, validated, baseline=baseline,
            uploads_root=get_settings().backend.uploads_dir, core_version=version,
        )
    return result


@router.post("/packages",response_model=PackageResponse)
async def upload_package(package:UploadFile=File(...),_admin:User=Depends(require_admin),db:Session=Depends(get_db),expected_kind:Literal["theme"]|None=None):
    blob=await package.read(10*1024*1024+1)
    try: validated=validate_module_package(blob)
    except ModulePackageError as exc: raise HTTPException(422,str(exc)) from exc
    if expected_kind == "theme" and validated.theme_extension is None:
        raise HTTPException(422, "Choose a theme-extension v1 package")
    root=get_settings().backend.uploads_dir.resolve()/"modules"; root.mkdir(parents=True,exist_ok=True)
    path=root/f"{validated.sha256}.zip"
    package_created = not path.exists()
    if package_created: path.write_bytes(blob)
    if validated.compiled_ui is not None:
        try:
            compile_ui_package(blob, validated)
        except CompiledUiBuildError as exc:
            if package_created:
                path.unlink(missing_ok=True)
            raise HTTPException(422, str(exc)) from exc
    record=ModulePackage(module_id=validated.manifest.module_id,version=validated.manifest.version,manifest=validated.manifest.model_dump(mode="json"),sha256=validated.sha256,size_bytes=validated.size_bytes,file_path=str(path),registrations=[x.model_dump(mode="json") for x in validated.manifest.registrations])
    db.add(record)
    try: db.commit()
    except IntegrityError:
        db.rollback(); record=db.scalar(select(ModulePackage).where(ModulePackage.module_id==validated.manifest.module_id,ModulePackage.version==validated.manifest.version))
        if record is None or record.sha256 != validated.sha256:
            if package_created:
                path.unlink(missing_ok=True)
            raise HTTPException(409,"published module versions are immutable")
    record.has_connector_settings = bool(validated.application_extension and validated.application_extension.connectors)
    record.has_kiosk_interface = bool(validated.application_extension and any(r.audience=='kiosk' for r in validated.application_extension.routes) and any('kiosk' in op.audiences for op in validated.application_extension.operations))
    return record

@router.get("/packages",response_model=list[PackageResponse])
def list_packages(_admin:User=Depends(require_admin),db:Session=Depends(get_db)):
    from backend.services.application_extensions import load_application_package, ApplicationGatewayError
    result = []
    for package in db.scalars(select(ModulePackage).order_by(ModulePackage.module_id,ModulePackage.version)):
        item = PackageResponse.model_validate(package)
        if (package.manifest.get('entrypoints') or {}).get('core') == 'application-extension.json':
            try:
                definition = load_application_package(package).application_extension
                item.has_connector_settings = bool(definition.connectors)
                item.has_kiosk_interface = any(r.audience=='kiosk' for r in definition.routes) and any('kiosk' in op.audiences for op in definition.operations)
            except (ApplicationGatewayError, ValueError, RuntimeError):
                pass  # Invalid/unavailable optional packages cannot hide Core administration.
        result.append(item)
    return result


@router.get("/compiled-ui/catalog")
def compiled_ui_catalog(
    authorization: str | None = Header(default=None),
    db:Session=Depends(get_db),
):
    packages = db.scalars(select(ModulePackage).order_by(ModulePackage.module_id, ModulePackage.version))
    items = []
    for package in packages:
        if (package.manifest.get("entrypoints") or {}).get("ui") != "compiled-ui.json":
            continue
        if not _application_package_is_active(package, db):
            continue
        item = _compiled_catalog_item(package, db, authorization)
        if item is not None:
            items.append(item)
    return {
        "items": items
    }


def _retired_package_paths(package: ModulePackage) -> tuple[Path, Path]:
    """Retire only catalog-owned paths; obsolete payloads need not execute/parse."""
    if any(type(value) is not str or re.fullmatch(pattern, value) is None
           for value, pattern in ((package.module_id, MODULE_ID_PATTERN),
                                  (package.version, SEMVER_PATTERN),
                                  (package.sha256, r"[0-9a-f]{64}"))):
        raise HTTPException(409, "Package catalog identity is invalid")
    try:
        uploads = get_settings().backend.uploads_dir.resolve()
        archive = uploads / "modules" / f"{package.sha256}.zip"
        artifacts = compiled_artifacts_dir().resolve()
        artifact = artifacts / package.module_id / package.version / package.sha256
        if Path(package.file_path) != archive:
            raise ValueError("Unmanaged package archive")
        # Configured roots may resolve through deployment links; descendants
        # must remain their exact managed identities, including missing files.
        for path in (archive.parent, archive, artifacts / package.module_id,
                     artifact.parent, artifact):
            if path.is_symlink() or path.resolve() != path:
                raise ValueError("Linked package retirement path")
        for path in (archive.parent, artifacts / package.module_id, artifact.parent, artifact):
            if path.exists() and not path.is_dir():
                raise ValueError("Invalid package artifact directory")
        if archive.exists() and not archive.is_file():
            raise ValueError("Invalid package archive file")
        return archive, artifact
    except (OSError, ValueError, RuntimeError, TypeError):
        raise HTTPException(409, "Package cleanup paths are outside the managed catalog or invalid") from None


@router.delete("/compiled-ui/packages/{module_id}/{version}")
def delete_compiled_ui_package(
    module_id: str,
    version: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    package = db.scalar(select(ModulePackage).where(
        ModulePackage.module_id == module_id,
        ModulePackage.version == version,
    ))
    entrypoints = package.manifest.get("entrypoints") if package is not None and isinstance(package.manifest, dict) else None
    if not isinstance(entrypoints, dict) or not (
        entrypoints.get("ui") == "compiled-ui.json"
        or entrypoints.get("core") == "application-extension.json"
    ):
        raise HTTPException(404, "Application or compiled UI package was not found")
    referenced = db.scalar(select(ModulePackageRetainedReference.reference_id).where(
        ModulePackageRetainedReference.package_id == package.id).limit(1))
    if referenced is not None:
        raise HTTPException(409, "Package has retained resource references; preserve or recover dependent data before retirement")
    if db.scalar(select(ModuleInstallation.id).where(ModuleInstallation.module_package_id == package.id).limit(1)) is not None:
        raise HTTPException(409, "Uninstall this package from devices before deleting it")
    if db.scalar(
        select(ApplicationExtensionInstallation.id).where(or_(
            ApplicationExtensionInstallation.module_package_id == package.id,
            ApplicationExtensionInstallation.previous_package_id == package.id,
        )).limit(1)
    ) is not None:
        raise HTTPException(409, "Disable and remove this application extension before deleting it")

    package_path, artifact_dir = _retired_package_paths(package)
    db.delete(package)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Package is still referenced; refresh before deleting it") from None
    shutil.rmtree(artifact_dir, ignore_errors=True)
    package_path.unlink(missing_ok=True)
    return {"status": "deleted", "module_id": module_id, "version": version}


@router.get("/compiled-ui/packages/{module_id}/{version}/retained-references")
def retained_package_references(module_id: str, version: str,
        _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    package = db.scalar(select(ModulePackage).where(ModulePackage.module_id == module_id, ModulePackage.version == version))
    if package is None: raise HTTPException(404, "Package was not found")
    rows = list(db.scalars(select(ModulePackageRetainedReference).where(
        ModulePackageRetainedReference.package_id == package.id)
        .order_by(ModulePackageRetainedReference.reference_id).limit(257)))
    return {"references": [{"reference_id": row.reference_id, "source": row.source,
        "resource_ref": row.resource_ref} for row in rows[:256]], "truncated": len(rows) > 256}


@router.get("/compiled-ui/assets/{module_id}/{version}/{sha256}/{asset_path:path}")
def compiled_ui_asset(module_id:str,version:str,sha256:str,asset_path:str,db:Session=Depends(get_db)):
    package = db.scalar(
        select(ModulePackage).where(
            ModulePackage.module_id == module_id,
            ModulePackage.version == version,
            ModulePackage.sha256 == sha256,
        )
    )
    if package is None:
        raise HTTPException(404, "compiled UI artifact was not found")
    if not _application_package_is_active(package, db):
        raise HTTPException(404, "compiled UI artifact was not found")
    validated = _validated_compiled_package(package)
    try:
        artifact = load_compiled_ui_artifact(validated)
        if validated.application_extension is not None:
            installation = db.scalar(select(ApplicationExtensionInstallation).where(
                ApplicationExtensionInstallation.module_package_id == package.id))
            artifact = application_ui_artifact(db, installation, validated)
    except CompiledUiBuildError as exc:
        raise HTTPException(404, str(exc)) from exc
    if artifact.built_ui_sha256:
        prefix = f'build/{artifact.built_ui_sha256}/'
        if not asset_path.startswith(prefix):
            raise HTTPException(404, 'compiled UI build changed')
        asset_path = asset_path[len(prefix):]
    target = (artifact.path / asset_path).resolve()
    if artifact.path.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "compiled UI asset was not found")
    media_type = {
        ".mjs": "text/javascript; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json",
    }.get(target.suffix.lower())
    if artifact.built_ui_sha256:
        from backend.services.compiled_ui_provenance import read_asset, UiBuildEvidenceError
        # Do not expose build/source metadata through an executable asset route.
        if not asset_path.startswith('assets/'):
            raise HTTPException(404, 'compiled UI asset was not found')
        try:
            content = read_asset(artifact, asset_path)
        except UiBuildEvidenceError:
            raise HTTPException(404, 'compiled UI asset changed') from None
        return Response(content, media_type=media_type, headers={
            'Cache-Control': 'public, max-age=31536000, immutable', 'X-Content-Type-Options': 'nosniff'})
    return FileResponse(
        target,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )

@router.post("/packages/{sha256}/devices/{device_id}/install", response_model=InstallationResponse)
def install_module(sha256: str, device_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_db),
                   idempotency_key: str | None = Header(default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")):
    return module_management.install_module(sha256, device_id, _admin, db, idempotency_key)


@router.post("/{module_id}/devices/{device_id}/disable", response_model=InstallationResponse)
def disable_module(module_id: str, device_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_db),
                   idempotency_key: str | None = Header(default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")):
    return module_management.disable_module(module_id, device_id, _admin, db, idempotency_key)


@router.get("/registrations",response_model=list[dict])
def registrations(_admin:User=Depends(require_admin),db:Session=Depends(get_db)):
    result=[]
    for package in db.scalars(select(ModulePackage)):
        if (package.manifest.get("entrypoints") or {}).get("ui") == "runtime-extension.json":
            continue
        if not _application_package_is_active(package, db):
            continue
        for item in package.registrations or []: result.append({"module_id":package.module_id,"version":package.version,**item})
    return result
