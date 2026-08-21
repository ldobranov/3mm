"""Validated module catalog and per-device lifecycle API."""
import base64
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from backend.config import get_settings
from backend.db.device import Device, DeviceInventorySnapshot
from backend.db.module import ModuleInstallation, ModulePackage
from backend.db.widget import Widget
from backend.db.user import User
from backend.services.device_commands import queue_command
from backend.services.module_packages import ModulePackageError, validate_module_package
from backend.services.compiled_ui import (
    CompiledUiBuildError,
    compile_ui_package,
    compiled_artifacts_dir,
    load_compiled_ui_artifact,
)
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db

router=APIRouter(prefix="/api/v1/modules",tags=["modules"])

class PackageResponse(BaseModel):
    module_id:str; version:str; sha256:str; size_bytes:int; manifest:dict; registrations:list[dict]
    model_config=ConfigDict(from_attributes=True)
class InstallationResponse(BaseModel):
    module_id:str; desired_version:str; installed_version:str|None; status:str; enabled:bool; command_id:str|None; data_retained:bool; error:str|None
    model_config=ConfigDict(from_attributes=True)


def _validated_compiled_package(package: ModulePackage):
    try:
        blob = Path(package.file_path).read_bytes()
        validated = validate_module_package(blob)
    except (OSError, ModulePackageError) as exc:
        raise HTTPException(409, "compiled UI package is no longer valid") from exc
    if validated.sha256 != package.sha256 or validated.compiled_ui is None:
        raise HTTPException(409, "compiled UI package identity is invalid")
    return validated


def _compiled_catalog_item(package: ModulePackage) -> dict:
    validated = _validated_compiled_package(package)
    try:
        artifact = load_compiled_ui_artifact(validated)
    except CompiledUiBuildError as exc:
        raise HTTPException(409, str(exc)) from exc
    base = f"/api/v1/modules/compiled-ui/assets/{package.module_id}/{package.version}/{package.sha256}"
    return {
        "module_id": package.module_id,
        "name": package.manifest.get("name") or package.module_id,
        "version": package.version,
        "source_sha256": package.sha256,
        "styles": [f"{base}/{path}" for path in artifact.styles],
        "entrypoints": [
            {
                **entrypoint.model_dump(mode="json"),
                "asset_url": f"{base}/{artifact.entrypoints[entrypoint.entrypoint_id]}",
            }
            for entrypoint in validated.compiled_ui.entrypoints
        ],
    }

@router.post("/packages",response_model=PackageResponse)
async def upload_package(package:UploadFile=File(...),_admin:User=Depends(require_admin),db:Session=Depends(get_db)):
    blob=await package.read(10*1024*1024+1)
    try: validated=validate_module_package(blob)
    except ModulePackageError as exc: raise HTTPException(422,str(exc)) from exc
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
        if record.sha256!=validated.sha256: raise HTTPException(409,"published module versions are immutable")
    return record

@router.get("/packages",response_model=list[PackageResponse])
def list_packages(_admin:User=Depends(require_admin),db:Session=Depends(get_db)):
    return list(db.scalars(select(ModulePackage).order_by(ModulePackage.module_id,ModulePackage.version)))


@router.get("/compiled-ui/catalog")
def compiled_ui_catalog(db:Session=Depends(get_db)):
    packages = db.scalars(select(ModulePackage).order_by(ModulePackage.module_id, ModulePackage.version))
    return {
        "items": [
            _compiled_catalog_item(package)
            for package in packages
            if (package.manifest.get("entrypoints") or {}).get("ui") == "compiled-ui.json"
        ]
    }


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
    if package is None or (package.manifest.get("entrypoints") or {}).get("ui") != "compiled-ui.json":
        raise HTTPException(404, "compiled UI package was not found")
    widget_prefix = f"compiled:{module_id}:{version}:"
    referenced = db.scalar(select(Widget.id).where(Widget.type.startswith(widget_prefix)).limit(1))
    if referenced is not None:
        raise HTTPException(409, "Remove this extension's widgets from all dashboards before deleting it")
    if db.scalar(select(ModuleInstallation.id).where(ModuleInstallation.module_package_id == package.id).limit(1)) is not None:
        raise HTTPException(409, "Uninstall this package from devices before deleting it")

    validated = _validated_compiled_package(package)
    artifact_dir = (
        compiled_artifacts_dir().resolve()
        / package.module_id / package.version / package.sha256
    )
    package_path = Path(package.file_path)
    db.delete(package)
    db.commit()
    shutil.rmtree(artifact_dir, ignore_errors=True)
    package_path.unlink(missing_ok=True)
    return {"status": "deleted", "module_id": validated.manifest.module_id, "version": version}


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
    validated = _validated_compiled_package(package)
    try:
        artifact = load_compiled_ui_artifact(validated)
    except CompiledUiBuildError as exc:
        raise HTTPException(404, str(exc)) from exc
    target = (artifact.path / asset_path).resolve()
    if artifact.path.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "compiled UI asset was not found")
    media_type = {
        ".mjs": "text/javascript; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json",
    }.get(target.suffix.lower())
    return FileResponse(
        target,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )

def _device_architecture(db,device):
    snapshot=db.scalar(select(DeviceInventorySnapshot).where(DeviceInventorySnapshot.device_id==device.id).order_by(DeviceInventorySnapshot.received_at.desc()).limit(1))
    return (snapshot.inventory or {}).get("architecture") if snapshot else None

@router.post("/packages/{sha256}/devices/{device_id}/install",response_model=InstallationResponse)
def install_module(sha256:str,device_id:str,_admin:User=Depends(require_admin),db:Session=Depends(get_db)):
    package=db.scalar(select(ModulePackage).where(ModulePackage.sha256==sha256)); device=db.scalar(select(Device).where(Device.device_id==device_id))
    if not package or not device: raise HTTPException(404,"package or device was not found")
    blob=Path(package.file_path).read_bytes()
    try: validate_module_package(blob,architecture=_device_architecture(db,device),protocol_version=device.protocol_version)
    except ModulePackageError as exc: raise HTTPException(409,str(exc)) from exc
    command=queue_command(db,device=device,command_type="module.install",payload={"package_base64":base64.b64encode(blob).decode(),"sha256":package.sha256,"module_id":package.module_id,"version":package.version},idempotency_key=f"module.install:{package.module_id}:{package.sha256}",ttl_seconds=900)
    installation=db.scalar(select(ModuleInstallation).where(ModuleInstallation.device_id==device.id,ModuleInstallation.module_id==package.module_id))
    if installation is None:
        installation=ModuleInstallation(device_id=device.id,module_package_id=package.id,module_id=package.module_id,desired_version=package.version,status="queued",enabled=True,data_retained=True); db.add(installation)
    installation.module_package_id=package.id; installation.desired_version=package.version; installation.status=command.status; installation.command_id=command.command_id; installation.enabled=True; installation.error=None
    db.commit(); db.refresh(installation); return installation

@router.post("/{module_id}/devices/{device_id}/disable",response_model=InstallationResponse)
def disable_module(module_id:str,device_id:str,_admin:User=Depends(require_admin),db:Session=Depends(get_db)):
    device=db.scalar(select(Device).where(Device.device_id==device_id)); installation=db.scalar(select(ModuleInstallation).where(ModuleInstallation.device_id==device.id,ModuleInstallation.module_id==module_id)) if device else None
    if not installation: raise HTTPException(404,"module installation was not found")
    command=queue_command(db,device=device,command_type="module.disable",payload={"module_id":module_id},idempotency_key=f"module.disable:{module_id}:{installation.installed_version}",ttl_seconds=300)
    installation.command_id=command.command_id; installation.status=command.status; db.commit(); db.refresh(installation); return installation

@router.get("/registrations",response_model=list[dict])
def registrations(_admin:User=Depends(require_admin),db:Session=Depends(get_db)):
    result=[]
    for package in db.scalars(select(ModulePackage)):
        if (package.manifest.get("entrypoints") or {}).get("ui") == "runtime-extension.json":
            continue
        for item in package.registrations or []: result.append({"module_id":package.module_id,"version":package.version,**item})
    return result
