"""M21 session discovery over the real device capability registry (M21.5).

Builds ``SessionDiscoveryV1`` from the existing ``device_capability_registry``
(``registered_capabilities``) plus the remote session router. A device is
listed only when it actually offers a session capability; availability is
reported separately (an offline device with the provider is listed as
unavailable, never offered as a working session).

This is read-only: no grants, no state mutation, no user-scoped visibility
(that remains M20/WP4 work). The route exposes it admin-only for now.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.device import Device, DeviceHeartbeat
from backend.services.device_capability_registry import registered_capabilities
from backend.services.device_registry import as_utc, is_device_online
from three_mm_protocol.interactive_session import (
    SessionDiscoveryV1,
    SessionTargetV1,
)


def _latest_heartbeat_at(db: Session, device: Device) -> datetime | None:
    latest = db.scalar(
        select(DeviceHeartbeat)
        .where(DeviceHeartbeat.device_id == device.id)
        .order_by(
            DeviceHeartbeat.received_at.desc(), DeviceHeartbeat.id.desc()
        )
        .limit(1)
    )
    return latest.received_at if latest else None


def build_session_discovery(
    db: Session,
    *,
    session_capability_ids: set[str],
    remote_targets: list[SessionTargetV1] | None = None,
    now: datetime | None = None,
) -> SessionDiscoveryV1:
    """List devices that offer session capabilities, with availability."""
    now = now or datetime.now(UTC)
    settings = get_settings()
    targets: list[SessionTargetV1] = []
    devices = db.scalars(
        select(Device).where(
            Device.approved_at.is_not(None), Device.revoked_at.is_(None)
        )
    )
    for device in devices:
        rows = registered_capabilities(db, device)
        offered = sorted(
            {
                row["capability_id"]
                for row in rows
                if row["capability_id"] in session_capability_ids
            }
        )
        if not offered:
            continue
        online = is_device_online(
            last_seen_at=_latest_heartbeat_at(db, device),
            now=now,
            offline_after=timedelta(
                seconds=settings.backend.device_offline_after_seconds
            ),
            revoked_at=device.revoked_at,
        )
        targets.append(
            SessionTargetV1(
                device_id=device.device_id,
                display_name=device.display_name or device.device_id,
                local=False,
                sessions=tuple(offered),
                available=online,
                unavailable_reason=None if online else "device_offline",
            )
        )
    for target in remote_targets or ():
        targets.append(target)
    return SessionDiscoveryV1(schema_version=1, targets=tuple(targets))


__all__ = ["build_session_discovery"]
