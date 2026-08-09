"""Validated module catalog and per-device lifecycle API."""
import base64
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from backend.config import get_settings
from backend.db.device import Device, DeviceInventorySnapshot
from backend.db.module import ModuleInstallation, ModulePackage
from backend.db.user import User
from backend.services.device_commands import queue_command
from backend.services.module_packages import ModulePackageError, validate_module_package
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db

router=APIRouter(prefix="/api/v1/modules",tags=["modules"])

class PackageResponse(BaseModel):
    module_id:str; version:str; sha256:str; size_bytes:int; manifest:dict; registrations:list[dict]
    model_config=ConfigDict(from_attributes=True)
class InstallationResponse(BaseModel):
    module_id:str; desired_version:str; installed_version:str|None; status:str; enabled:bool; command_id:str|None; data_retained:bool; error:str|None
    model_config=ConfigDict(from_attributes=True)

@router.post("/packages",response_model=PackageResponse)
async def upload_package(package:UploadFile=File(...),_admin:User=Depends(require_admin),db:Session=Depends(get_db)):
    blob=await package.read(10*1024*1024+1)
    try: validated=validate_module_package(blob)
    except ModulePackageError as exc: raise HTTPException(422,str(exc)) from exc
    root=get_settings().backend.uploads_dir.resolve()/"modules"; root.mkdir(parents=True,exist_ok=True)
    path=root/f"{validated.sha256}.zip"
    if not path.exists(): path.write_bytes(blob)
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
        for item in package.registrations or []: result.append({"module_id":package.module_id,"version":package.version,**item})
    return result
