"""Administrator read API for real registered devices."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.device import Device, DeviceHeartbeat, DeviceInventorySnapshot
from backend.db.user import User
from backend.services.device_registry import as_utc, is_device_online
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


class DeviceRegistryItem(BaseModel):
    device_id: str
    display_name: str | None
    role: str
    protocol_version: str
    approved_at: datetime
    revoked_at: datetime | None
    online: bool
    last_seen_at: datetime | None
    latest_inventory: dict | None

    model_config = ConfigDict(extra="forbid")


class DeviceRegistryResponse(BaseModel):
    items: list[DeviceRegistryItem]
    total: int

    model_config = ConfigDict(extra="forbid")


@router.get("", response_model=DeviceRegistryResponse)
def list_devices(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DeviceRegistryResponse:
    now = datetime.now(timezone.utc)
    offline_after = timedelta(
        seconds=get_settings().backend.device_offline_after_seconds
    )
    devices = list(db.scalars(select(Device).order_by(Device.created_at, Device.id)))
    items: list[DeviceRegistryItem] = []
    for device in devices:
        heartbeat = db.scalar(
            select(DeviceHeartbeat)
            .where(DeviceHeartbeat.device_id == device.id)
            .order_by(DeviceHeartbeat.received_at.desc(), DeviceHeartbeat.id.desc())
            .limit(1)
        )
        inventory = db.scalar(
            select(DeviceInventorySnapshot)
            .where(DeviceInventorySnapshot.device_id == device.id)
            .order_by(
                DeviceInventorySnapshot.received_at.desc(),
                DeviceInventorySnapshot.id.desc(),
            )
            .limit(1)
        )
        last_seen_at = as_utc(heartbeat.received_at if heartbeat else None)
        items.append(
            DeviceRegistryItem(
                device_id=device.device_id,
                display_name=device.display_name,
                role=device.role,
                protocol_version=device.protocol_version,
                approved_at=as_utc(device.approved_at),
                revoked_at=as_utc(device.revoked_at),
                online=is_device_online(
                    last_seen_at=last_seen_at,
                    now=now,
                    offline_after=offline_after,
                    revoked_at=device.revoked_at,
                ),
                last_seen_at=last_seen_at,
                latest_inventory=inventory.inventory if inventory else None,
            )
        )
    return DeviceRegistryResponse(items=items, total=len(items))
