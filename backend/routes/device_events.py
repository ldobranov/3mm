from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.db.device import Device, DeviceEvent
from backend.utils.db_utils import get_db
from backend.utils.device_auth import require_device

router=APIRouter(prefix="/api/v1/devices",tags=["device-events"])
class DeviceEventPayload(BaseModel):
    event_id:str=Field(pattern=r"^evt_[0-9a-f]{32}$")
    device_id:str=Field(pattern=r"^dev_[0-9a-f]{32}$")
    event_type:str=Field(min_length=1,max_length=120)
    payload:dict=Field(default_factory=dict)
    occurred_at:datetime
    model_config=ConfigDict(extra="forbid")
@router.post("/{device_id}/events",status_code=status.HTTP_202_ACCEPTED)
def ingest_event(device_id:str,payload:DeviceEventPayload,device:Device=Depends(require_device),db:Session=Depends(get_db)):
    if device.device_id!=device_id or payload.device_id!=device_id: raise HTTPException(403,"Device identity mismatch")
    existing=db.scalar(select(DeviceEvent).where(DeviceEvent.event_id==payload.event_id))
    if existing: return {"status":"accepted","duplicate":True}
    db.add(DeviceEvent(device_id=device.id,event_id=payload.event_id,event_type=payload.event_type,payload=payload.payload,occurred_at=payload.occurred_at)); db.commit()
    return {"status":"accepted","duplicate":False}
