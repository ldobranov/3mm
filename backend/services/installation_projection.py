"""Consent-first status projection. No credentials/config/capability serializer."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, update

from backend.config import get_settings
from backend.db.device import Device, DeviceHeartbeat, DeviceInventorySnapshot
from backend.db.installation_peer import InstallationPeerOutbound
from backend.services.device_registry import as_utc, is_device_online
from backend.services.installation_identity import _load_or_create
from backend.version import core_version
from three_mm_application_sdk import SDK_VERSION
from three_mm_protocol.installation_peer import (
    InstallationProjectionV1,
    ProjectionConsentV1,
    ProjectionValueV1,
    ProjectedNodeV1,
)
from three_mm_protocol.models import PROTOCOL_VERSION
from three_mm_protocol.device_inventory import inventory_value


def _value(value=None, *, source=None, observed=None, received=None, revision=None):
    if (
        type(value) not in (str, bool, int)
        or isinstance(value, str)
        and len(value) > 255
    ):
        value = None
    return ProjectionValueV1(
        status="known" if value is not None else "unknown",
        value=value,
        source=source,
        observed_at=as_utc(observed),
        received_at=as_utc(received),
        revision=revision,
    )


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
        return as_utc(parsed) if isinstance(parsed, datetime) else None
    except ValueError:
        return None


def installation_projection(
    db, application, link_id: str, *, now=None
) -> InstallationProjectionV1:
    now = now or datetime.now(UTC)
    if not application.enabled or application.status != "active":
        raise ValueError("Application installation is not active")
    # A database write lock serializes withdrawal with the complete projection.
    changed = db.execute(
        update(InstallationPeerOutbound)
        .where(
            InstallationPeerOutbound.link_id == link_id,
            InstallationPeerOutbound.module_id == application.module_id,
            InstallationPeerOutbound.application_instance_id == application.instance_id,
            InstallationPeerOutbound.state != "revoked",
        )
        .values(consent_revision=InstallationPeerOutbound.consent_revision)
    ).rowcount
    if changed != 1:
        raise ValueError("Local reporting consent is unavailable or withdrawn")
    link = db.scalar(
        select(InstallationPeerOutbound)
        .where(InstallationPeerOutbound.link_id == link_id)
        .execution_options(populate_existing=True)
    )
    consent = ProjectionConsentV1.model_validate(link.consent)
    identity, _ = _load_or_create(db)
    if identity.model_dump(mode="json") != link.sender_identity:
        raise ValueError("Local installation identity changed")
    summary = {}
    root = Path(__file__).resolve().parents[2]
    sources = {
        "core_version": root / "VERSION",
        "protocol_version": root / "three_mm_protocol/models.py",
        "sdk_version": root / "three_mm_application_sdk/__init__.py",
    }
    for field in consent.summary_fields:
        try:
            value = (
                core_version()
                if field == "core_version"
                else PROTOCOL_VERSION if field == "protocol_version" else SDK_VERSION
            )
            modified = datetime.fromtimestamp(sources[field].stat().st_mtime, UTC)
            summary[field] = _value(
                value,
                source="core.runtime",
                observed=modified,
                revision=f"{field}:{value}",
            )
        except (ValueError, OSError):
            summary[field] = _value(source="core.runtime")

    # Scope is applied in SQL, before touching inventory or constructing output.
    devices = (
        {
            device.device_id: device
            for device in db.scalars(
                select(Device).where(
                    Device.device_id.in_(consent.node_ids), Device.revoked_at.is_(None)
                )
            )
        }
        if consent.node_ids
        else {}
    )
    nodes = []
    for device_id in consent.node_ids:
        device = devices.get(device_id)
        if device is None:
            nodes.append(
                ProjectedNodeV1(
                    device_id=device_id,
                    fields={field: _value() for field in consent.node_fields},
                )
            )
            continue
        need_heartbeat = bool({"online", "last_seen_at"} & set(consent.node_fields))
        heartbeat = (
            db.scalar(
                select(DeviceHeartbeat)
                .where(DeviceHeartbeat.device_id == device.id)
                .order_by(DeviceHeartbeat.received_at.desc(), DeviceHeartbeat.id.desc())
                .limit(1)
            )
            if need_heartbeat
            else None
        )
        need_inventory = bool(
            {"architecture", "memory_total_bytes", "root_free_bytes"}
            & set(consent.node_fields)
        )
        inventory = (
            db.scalar(
                select(DeviceInventorySnapshot)
                .where(DeviceInventorySnapshot.device_id == device.id)
                .order_by(
                    DeviceInventorySnapshot.received_at.desc(),
                    DeviceInventorySnapshot.id.desc(),
                )
                .limit(1)
            )
            if need_inventory
            else None
        )
        fields = {}
        for field in consent.node_fields:
            if field in {"display_name", "role", "protocol_version"}:
                fields[field] = _value(
                    getattr(device, field),
                    source="device.registry",
                    observed=device.updated_at,
                    revision=(
                        f"registry:{as_utc(device.updated_at).isoformat()}"
                        if device.updated_at
                        else None
                    ),
                )
            elif field in {"online", "last_seen_at"}:
                if heartbeat is None:
                    fields[field] = _value(source="device.heartbeat")
                    continue
                seen = as_utc(heartbeat.received_at)
                observed = (
                    _timestamp(heartbeat.payload.get("sent_at"))
                    if isinstance(heartbeat.payload, dict)
                    else None
                )
                value = (
                    is_device_online(
                        last_seen_at=seen,
                        now=now,
                        offline_after=timedelta(
                            seconds=get_settings().backend.device_offline_after_seconds
                        ),
                    )
                    if field == "online"
                    else seen.isoformat()
                )
                fields[field] = _value(
                    value,
                    source="device.heartbeat",
                    observed=observed,
                    received=seen,
                    revision=f"heartbeat:{heartbeat.id}",
                )
            elif field == "agent_version":
                # The current inventory/heartbeat contracts do not report an
                # actual Agent version. Desired/module/update versions aren't it.
                fields[field] = _value(source="device.reported")
            else:
                data = (
                    inventory.inventory
                    if inventory and isinstance(inventory.inventory, dict)
                    else {}
                )
                value = inventory_value(data, field)
                if field in {"memory_total_bytes", "root_free_bytes"} and (
                    type(value) is not int or value < 0
                ):
                    value = None
                fields[field] = _value(
                    value,
                    source="device.inventory",
                    observed=_timestamp(data.get("collected_at")),
                    received=inventory.received_at if inventory else None,
                    revision=f"inventory:{inventory.id}" if inventory else None,
                )
        nodes.append(ProjectedNodeV1(device_id=device_id, fields=fields))
    return InstallationProjectionV1(
        installation_id=identity.installation_id,
        consent_revision=link.consent_revision,
        generated_at=now,
        summary=summary,
        nodes=tuple(nodes),
    )
