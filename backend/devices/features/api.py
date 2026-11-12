"""Negotiation and diagnostics on the common device API, not Fleet."""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select

from backend.db.device import Device
from backend.devices.features.service import (
    runtime_features_snapshot,
)
from backend.accounts.dependencies import require_admin
from backend.storage.sessions import get_db
from backend.devices.auth import require_device
from backend.devices.operations import DeviceOperations
from backend.devices.http import call
from packages.protocol.node_features import (
    CoreNodeProtocolV1,
    DeviceRuntimeFeaturesReportV1,
    DeviceRuntimeFeaturesSnapshotV1,
)

router = APIRouter(prefix="/api/v1/devices", tags=["device-runtime"])


def _own(device, device_id):
    if device.device_id != device_id:
        raise HTTPException(403, "Device identity mismatch")


@router.get("/{device_id}/protocol", response_model=CoreNodeProtocolV1)
def protocol(device_id: str, device=Depends(require_device), db=Depends(get_db)):
    _own(device, device_id)
    return call(DeviceOperations(db, device).protocol)


@router.put(
    "/{device_id}/runtime-features", response_model=DeviceRuntimeFeaturesSnapshotV1
)
def report_features(
    device_id: str,
    payload: DeviceRuntimeFeaturesReportV1,
    authorization: str | None = Header(default=None),
    device=Depends(require_device),
    db=Depends(get_db),
):
    _own(device, device_id)
    _own(device, payload.device_id)
    credential_id = (authorization or "").removeprefix("Device ").strip().partition(":")[0]
    return call(DeviceOperations(db, device, credential_id=credential_id).features, payload)


@router.get(
    "/{device_id}/runtime-features", response_model=DeviceRuntimeFeaturesSnapshotV1
)
def get_features(device_id: str, _admin=Depends(require_admin), db=Depends(get_db)):
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if device is None:
        raise HTTPException(404, "Device was not found")
    return runtime_features_snapshot(db, device)
