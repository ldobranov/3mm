"""Latest authenticated state for enabled device capabilities."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.device import Device, DeviceCapabilityState
from backend.db.user import User
from backend.devices.capabilities.registry import has_registered_capability
from backend.accounts.dependencies import require_admin
from backend.storage.sessions import get_db
from backend.devices.auth import require_device
from packages.protocol import CapabilityStateReportV1, CapabilityStateSnapshotV1
from backend.devices.operations import DeviceOperations, capability_snapshot
from backend.devices.http import call


router = APIRouter(prefix="/api/v1/devices", tags=["device-capability-state"])


def _device(db: Session, device_id: str) -> Device:
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if device is None:
        raise HTTPException(404, "Device was not found")
    return device


def _snapshot(device: Device, row: DeviceCapabilityState) -> CapabilityStateSnapshotV1:
    return capability_snapshot(device, row)


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
    return call(DeviceOperations(db, device).capability_state, payload)


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
