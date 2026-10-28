"""Shared device projections. Callers must authorize access before reading."""

from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.device import Device, DeviceHeartbeat, DeviceInventorySnapshot
from backend.db.module import ModuleInstallation
from backend.services.device_registry import as_utc, is_device_online
from three_mm_protocol.device_inventory import normalized_inventory


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

class DeviceModuleItem(BaseModel):
    module_id: str
    installed_version: str | None
    desired_version: str
    status: str
    enabled: bool
    error: str | None

    model_config = ConfigDict(extra="forbid")


class DeviceDetailResponse(DeviceRegistryItem):
    modules: list[DeviceModuleItem]

    model_config = ConfigDict(extra="forbid")

def read_devices(
    db: Session,
    inventory_schema_version: int = 1,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> DeviceRegistryResponse:
    now = datetime.now(timezone.utc)
    offline_after = timedelta(
        seconds=get_settings().backend.device_offline_after_seconds
    )
    query = select(Device).order_by(Device.created_at, Device.id).offset(offset)
    if limit is not None:
        query = query.limit(limit)
    devices = list(db.scalars(query))
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
                latest_inventory=(
                    normalized_inventory(inventory.inventory)
                    if inventory_schema_version == 2 else inventory.inventory
                ) if inventory else None,
            )
        )
    return DeviceRegistryResponse(items=items, total=db.scalar(select(func.count()).select_from(Device)))

def read_device(
    device_id: str,
    db: Session,
    inventory_schema_version: int = 1,
) -> DeviceDetailResponse:
    now = datetime.now(timezone.utc)
    offline_after = timedelta(
        seconds=get_settings().backend.device_offline_after_seconds
    )

    device = db.scalar(
        select(Device).where(Device.device_id == device_id)
    )

    if device is None:
        raise HTTPException(404, "Device was not found")

    heartbeat = db.scalar(
        select(DeviceHeartbeat)
        .where(DeviceHeartbeat.device_id == device.id)
        .order_by(
            DeviceHeartbeat.received_at.desc(),
            DeviceHeartbeat.id.desc(),
        )
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

    modules = list(
        db.scalars(
            select(ModuleInstallation)
            .where(ModuleInstallation.device_id == device.id)
            .order_by(ModuleInstallation.module_id)
        )
    )

    last_seen_at = as_utc(
        heartbeat.received_at if heartbeat else None
    )

    return DeviceDetailResponse(
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
        latest_inventory=(
            normalized_inventory(inventory.inventory)
            if inventory_schema_version == 2 else inventory.inventory
        ) if inventory else None,
        modules=[
            DeviceModuleItem(
                module_id=item.module_id,
                installed_version=item.installed_version,
                desired_version=item.desired_version,
                status=item.status,
                enabled=item.enabled,
                error=item.error,
            )
            for item in modules
        ],
    )
