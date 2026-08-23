"""Latest authenticated state for enabled device capabilities."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.device import Device, DeviceCapabilityState
from backend.db.user import User
from backend.services.device_capability_registry import has_registered_capability
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from backend.utils.device_auth import require_device
from three_mm_protocol import CapabilityStateReportV1, CapabilityStateSnapshotV1


router = APIRouter(prefix="/api/v1/devices", tags=["device-capability-state"])


def _device(db: Session, device_id: str) -> Device:
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if device is None:
        raise HTTPException(404, "Device was not found")
    return device


def _snapshot(device: Device, row: DeviceCapabilityState) -> CapabilityStateSnapshotV1:
    observed_at = row.observed_at
    received_at = row.received_at
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=timezone.utc)
    return CapabilityStateSnapshotV1(
        device_id=device.device_id,
        capability_id=row.capability_id,
        values=row.values,
        observed_at=observed_at,
        received_at=received_at,
    )


@router.post(
    "/{device_id}/capabilities/{capability_id}/state",
    response_model=CapabilityStateSnapshotV1,
)
def report_capability_state(
    device_id: str,
    capability_id: str,
    payload: CapabilityStateReportV1,
    device: Device = Depends(require_device),
    db: Session = Depends(get_db),
) -> CapabilityStateSnapshotV1:
    if device.device_id != device_id or payload.device_id != device_id:
        raise HTTPException(403, "Device identity mismatch")
    if payload.capability_id != capability_id:
        raise HTTPException(409, "Capability identity mismatch")
    if not has_registered_capability(db, device, capability_id):
        raise HTTPException(409, "Capability is not enabled on this device")
    row = db.scalar(select(DeviceCapabilityState).where(
        DeviceCapabilityState.device_id == device.id,
        DeviceCapabilityState.capability_id == capability_id,
    ))
    if row is None:
        row = DeviceCapabilityState(
            device_id=device.id,
            capability_id=capability_id,
            values=payload.values,
            observed_at=payload.observed_at,
            received_at=datetime.now(timezone.utc),
        )
        db.add(row)
    elif payload.observed_at >= row.observed_at.replace(tzinfo=payload.observed_at.tzinfo):
        row.values = payload.values
        row.observed_at = payload.observed_at
        row.received_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _snapshot(device, row)


@router.get(
    "/{device_id}/capabilities/{capability_id}/state",
    response_model=CapabilityStateSnapshotV1,
)
def read_capability_state(
    device_id: str,
    capability_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CapabilityStateSnapshotV1:
    device = _device(db, device_id)
    if not has_registered_capability(db, device, capability_id):
        raise HTTPException(409, "Capability is not enabled on this device")
    row = db.scalar(select(DeviceCapabilityState).where(
        DeviceCapabilityState.device_id == device.id,
        DeviceCapabilityState.capability_id == capability_id,
    ))
    if row is None:
        raise HTTPException(404, "Capability state has not been reported yet")
    return _snapshot(device, row)
