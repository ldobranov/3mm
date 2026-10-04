"""Revisioned desired/reported state endpoints."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from three_mm_protocol.node_security import bounded_node_message
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.device import Device, DeviceState
from backend.db.user import User
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from backend.utils.device_auth import require_device
from three_mm_protocol import AgentReportedState, DeviceDesiredState
from backend.services.device_protocol import DeviceOperations, state_row, desired_snapshot
from backend.utils.device_protocol_http import call

router = APIRouter(prefix="/api/v1/devices", tags=["device-state"])

class DesiredStateUpdate(BaseModel):
    _bounded = model_validator(mode="after")(bounded_node_message)
    expected_revision: int = Field(ge=0)
    state: dict
    model_config = ConfigDict(extra="forbid")

class StateSummary(BaseModel):
    desired: DeviceDesiredState
    reported_revision: int
    reported_state: dict
    reported_at: datetime | None
    synchronized: bool

def _row(db: Session, device: Device) -> DeviceState:
    return state_row(db, device)

def _desired(row: DeviceState, device_id: str) -> DeviceDesiredState:
    return call(desired_snapshot, row, device_id)

@router.get("/{device_id}/desired-state", response_model=DeviceDesiredState)
def get_desired_state(device_id: str, device: Device = Depends(require_device), db: Session = Depends(get_db)) -> DeviceDesiredState:
    if device.device_id != device_id: raise HTTPException(403, "Device identity mismatch")
    return call(DeviceOperations(db, device).desired_state)

@router.put("/{device_id}/desired-state", response_model=DeviceDesiredState)
def update_desired_state(device_id: str, payload: DesiredStateUpdate, _admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> DeviceDesiredState:
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if device is None: raise HTTPException(404, "Device was not found")
    row = _row(db, device)
    if row.desired_revision != payload.expected_revision: raise HTTPException(409, "Desired state revision conflict")
    # Validate the outgoing envelope too: its identity/time overhead is larger
    # than the update request. Never commit state the Node cannot receive.
    try:
        desired = DeviceDesiredState(device_id=device_id, revision=row.desired_revision + 1, state=payload.state, updated_at=datetime.now(timezone.utc))
    except ValueError as exc:
        raise HTTPException(422, "Desired state exceeds the Node message contract") from exc
    row.desired_revision = desired.revision; row.desired_state = desired.state; row.desired_updated_at = desired.updated_at
    db.commit(); db.refresh(row)
    return _desired(row, device_id)

@router.post("/{device_id}/reported-state", response_model=AgentReportedState)
def report_state(device_id: str, payload: AgentReportedState, device: Device = Depends(require_device), db: Session = Depends(get_db)) -> AgentReportedState:
    if device.device_id != device_id or payload.device_id != device_id: raise HTTPException(403, "Device identity mismatch")
    return call(DeviceOperations(db, device).reported_state, payload)

@router.get("/{device_id}/state", response_model=StateSummary)
def get_state(device_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> StateSummary:
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if device is None: raise HTTPException(404, "Device was not found")
    row = _row(db, device)
    return StateSummary(desired=_desired(row, device_id), reported_revision=row.reported_revision, reported_state=row.reported_state, reported_at=(row.reported_at.replace(tzinfo=timezone.utc) if row.reported_at is not None and row.reported_at.tzinfo is None else row.reported_at), synchronized=row.reported_revision == row.desired_revision)
