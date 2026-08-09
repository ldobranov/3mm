"""Authenticated Agent-to-Core inventory and liveness ingestion."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.db.device import Device, DeviceHeartbeat, DeviceInventorySnapshot
from backend.utils.db_utils import get_db
from backend.utils.device_auth import require_device
from three_mm_protocol import AgentHeartbeat, AgentInventory

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


class HeartbeatAcceptedResponse(BaseModel):
    status: str = "accepted"

    model_config = ConfigDict(extra="forbid")


class InventoryAcceptedResponse(BaseModel):
    status: str = "accepted"

    model_config = ConfigDict(extra="forbid")


@router.post(
    "/{device_id}/heartbeat",
    response_model=HeartbeatAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_heartbeat(
    payload: AgentHeartbeat,
    device_id: Annotated[str, Path(pattern=r"^dev_[0-9a-f]{32}$")],
    device: Device = Depends(require_device),
    db: Session = Depends(get_db),
) -> HeartbeatAcceptedResponse:
    if device.device_id != device_id or payload.device_id != device_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device identity mismatch",
        )
    db.add(
        DeviceHeartbeat(
            device_id=device.id,
            protocol_version=payload.protocol_version,
            payload=payload.model_dump(mode="json"),
        )
    )
    db.commit()
    return HeartbeatAcceptedResponse()


@router.post(
    "/{device_id}/inventory",
    response_model=InventoryAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_inventory(
    payload: AgentInventory,
    device_id: Annotated[str, Path(pattern=r"^dev_[0-9a-f]{32}$")],
    device: Device = Depends(require_device),
    db: Session = Depends(get_db),
) -> InventoryAcceptedResponse:
    if device.device_id != device_id or payload.device_id != device_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device identity mismatch",
        )
    db.add(
        DeviceInventorySnapshot(
            device_id=device.id,
            inventory=payload.model_dump(mode="json"),
        )
    )
    db.commit()
    return InventoryAcceptedResponse()
