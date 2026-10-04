from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.db.device import Device, DeviceEvent
from backend.db.user import User
from backend.config import get_settings
from backend.services.application_events import process_application_event
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from backend.utils.device_auth import require_device
from three_mm_protocol import DeviceEventV1, IdentifierScanEventV1
from three_mm_protocol.passage import PassageEventV1
from backend.services.device_protocol import DeviceOperations
from backend.utils.device_protocol_http import call

router=APIRouter(prefix="/api/v1/devices",tags=["device-events"])
class DeviceEventPayload(DeviceEventV1):
    # Keep the existing API component name/mutability and specialized validation.
    model_config=ConfigDict(extra="forbid", frozen=False)

    @model_validator(mode="after")
    def validate_known_event_contract(self):
        if self.event_type == "identifier.scan.v1":
            IdentifierScanEventV1.model_validate(self.model_dump())
        if self.event_type == 'access.passage.v1':
            PassageEventV1.model_validate(self.model_dump())
        return self


class DeviceEventResponse(BaseModel):
    event_id: str
    device_id: str
    event_type: str
    payload: dict
    occurred_at: datetime
    received_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.post("/{device_id}/events",status_code=status.HTTP_202_ACCEPTED)
def ingest_event(device_id:str,payload:DeviceEventPayload,background_tasks:BackgroundTasks,device:Device=Depends(require_device),db:Session=Depends(get_db)):
    if device.device_id!=device_id or payload.device_id!=device_id: raise HTTPException(403,"Device identity mismatch")
    event_id, duplicate = call(DeviceOperations(db, device).event, payload)
    background_tasks.add_task(
        process_application_event,
        event_id,
        get_settings().applications,
    )
    return {"status":"accepted","duplicate":duplicate}


@router.get("/{device_id}/events", response_model=list[DeviceEventResponse])
def list_events(
    device_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if device is None:
        raise HTTPException(404, "Device was not found")
    events = db.scalars(
        select(DeviceEvent)
        .where(DeviceEvent.device_id == device.id)
        .order_by(DeviceEvent.occurred_at.desc())
        .limit(50)
    )
    return [
        DeviceEventResponse(
            event_id=event.event_id,
            device_id=device.device_id,
            event_type=event.event_type,
            payload=event.payload,
            occurred_at=event.occurred_at,
            received_at=event.received_at,
        )
        for event in events
    ]
