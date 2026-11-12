"""Administrator read API for real registered devices."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.db.user import User
from backend.devices.registry.read import (
    DeviceRegistryResponse, DeviceDetailResponse,
    read_devices, read_device,
)
from backend.accounts.dependencies import require_admin
from backend.storage.sessions import get_db

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


@router.get("", response_model=DeviceRegistryResponse)
def list_devices(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    inventory_schema_version: int = Query(default=1, ge=1, le=2),
) -> DeviceRegistryResponse:
    return read_devices(db, inventory_schema_version)


@router.get("/{device_id}", response_model=DeviceDetailResponse)
def get_device(
    device_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    inventory_schema_version: int = Query(default=1, ge=1, le=2),
) -> DeviceDetailResponse:
    return read_device(device_id, db, inventory_schema_version)
