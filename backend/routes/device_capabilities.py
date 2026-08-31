"""Capability-driven commands for installed, enabled Agent modules."""
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.db.device import Device
from backend.db.user import User
from backend.services.device_capability_registry import registered_capabilities
from backend.services.device_commands import commit_queued_command, queue_command
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db

router=APIRouter(prefix="/api/v1/devices",tags=["device-capabilities"])

class CapabilityRegistration(BaseModel):
    capability_id:str; module_id:str; version:str; metadata:dict
    model_config=ConfigDict(extra="forbid")
class InvokeCapabilityRequest(BaseModel):
    capability_id:str=Field(min_length=1,max_length=160)
    action:str=Field(min_length=1,max_length=100)
    arguments:dict=Field(default_factory=dict)
    model_config=ConfigDict(extra="forbid")
class CapabilityCommandResponse(BaseModel):
    command_id:str; status:str
    model_config=ConfigDict(extra="forbid")

def _device(db:Session,device_id:str)->Device:
    device=db.scalar(select(Device).where(Device.device_id==device_id))
    if device is None: raise HTTPException(404,"Device was not found")
    return device

def _capabilities(db:Session,device:Device)->list[CapabilityRegistration]:
    return [CapabilityRegistration.model_validate(item) for item in registered_capabilities(db,device)]

@router.get("/{device_id}/capabilities",response_model=list[CapabilityRegistration])
def list_capabilities(device_id:str,_admin:User=Depends(require_admin),db:Session=Depends(get_db)):
    return _capabilities(db,_device(db,device_id))

@router.post("/{device_id}/capabilities/invoke",response_model=CapabilityCommandResponse)
def invoke_capability(device_id:str,payload:InvokeCapabilityRequest,_admin:User=Depends(require_admin),db:Session=Depends(get_db)):
    device=_device(db,device_id)
    if payload.capability_id not in {item.capability_id for item in _capabilities(db,device)}:
        raise HTTPException(409,"Capability is not enabled on this device")
    command=queue_command(db,device=device,command_type="capability.invoke",payload=payload.model_dump(),idempotency_key=f"capability:{payload.capability_id}:{uuid4().hex}",ttl_seconds=300)
    commit_queued_command(db,device=device,command=command)
    return CapabilityCommandResponse(command_id=command.command_id,status=command.status)
