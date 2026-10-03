"""One Core capability query for module and device-advertised providers.

Module installations remain authoritative through a live compatibility adapter;
non-module providers do not need packages, Fleet or a particular runtime.
"""

from collections import Counter
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from backend.db.audit_log import AuditLog
from backend.db.device import (
    Device,
    DeviceCapabilityProvider,
    DeviceCapabilityState,
    DeviceEvent,
)
from backend.db.module import ModuleInstallation, ModulePackage
from three_mm_protocol import CapabilityProviderReportV1, CapabilityProviderSnapshotV1


class CapabilityRegistryError(ValueError):
    """A conflicting registration or stale provider revision."""


def _module_capabilities(db: Session, device: Device) -> list[dict]:
    result = []
    packages = db.scalars(
        select(ModulePackage)
        .join(
            ModuleInstallation, ModuleInstallation.module_package_id == ModulePackage.id
        )
        .where(
            ModuleInstallation.device_id == device.id,
            ModuleInstallation.enabled.is_(True),
            ModuleInstallation.status == "succeeded",
        )
    )
    for package in packages:
        for item in package.registrations or []:
            if item.get("kind") == "capability":
                result.append(
                    {
                        "capability_id": item["registration_id"],
                        "provider_type": "agent_module",
                        "provider_id": package.module_id,
                        "provider_version": package.version,
                        "metadata": item.get("metadata", {}),
                        "status": "active",
                    }
                )
    return result


def _providers(db: Session, device: Device) -> list[DeviceCapabilityProvider]:
    return list(
        db.scalars(
            select(DeviceCapabilityProvider)
            .where(DeviceCapabilityProvider.device_id == device.id)
            .execution_options(populate_existing=True)
        )
    )


def registered_capabilities(db: Session, device: Device) -> list[dict]:
    """Effective registrations. Ambiguous capability IDs fail closed."""
    if device.approved_at is None or device.revoked_at is not None:
        return []
    result = _module_capabilities(db, device)
    for provider in _providers(db, device):
        if not provider.enabled:
            continue
        for item in provider.capabilities:
            result.append(
                {
                    **item,
                    "provider_type": provider.provider_type,
                    "provider_id": provider.provider_id,
                    "provider_version": provider.provider_version,
                    "status": "active",
                }
            )
    counts = Counter(item["capability_id"] for item in result)
    return sorted(
        (item for item in result if counts[item["capability_id"]] == 1),
        key=lambda item: (
            item["capability_id"],
            item["provider_type"],
            item["provider_id"],
        ),
    )


def has_registered_capability(db: Session, device: Device, capability_id: str) -> bool:
    return any(
        item["capability_id"] == capability_id
        for item in registered_capabilities(db, device)
    )


def provider_snapshot(
    device: Device, provider: DeviceCapabilityProvider
) -> CapabilityProviderSnapshotV1:
    reported_at = provider.reported_at
    if reported_at.tzinfo is None:
        reported_at = reported_at.replace(tzinfo=UTC)
    return CapabilityProviderSnapshotV1(
        device_id=device.device_id,
        provider_type=provider.provider_type,
        provider_id=provider.provider_id,
        provider_version=provider.provider_version,
        revision=provider.revision,
        enabled=provider.enabled,
        capabilities=tuple(provider.capabilities),
        reported_at=reported_at,
    )


def read_provider(db: Session, device: Device, provider_type: str, provider_id: str):
    return next(
        (
            row
            for row in _providers(db, device)
            if (row.provider_type, row.provider_id) == (provider_type, provider_id)
        ),
        None,
    )


def provider_snapshots(
    db: Session, device: Device
) -> list[CapabilityProviderSnapshotV1]:
    """Administrator diagnostics include disabled/withdrawn provider revisions."""
    return [
        provider_snapshot(device, row)
        for row in sorted(
            _providers(db, device), key=lambda row: (row.provider_type, row.provider_id)
        )
    ]


def _lock_device(db: Session, device: Device):
    # Serialize replacements/controls for this device in SQLite and PostgreSQL.
    changed = db.execute(
        update(Device)
        .where(
            Device.id == device.id,
            Device.approved_at.is_not(None),
            Device.revoked_at.is_(None),
        )
        .values(updated_at=Device.updated_at)
        .execution_options(synchronize_session=False)
    ).rowcount
    if changed != 1:
        raise CapabilityRegistryError("Device authority is inactive")


def _check_conflicts(db: Session, device: Device, providers, provider, declarations):
    reserved = {item["capability_id"] for item in _module_capabilities(db, device)}
    for other in providers:
        if other is not provider:
            # Disabled providers retain ownership until they withdraw declarations.
            reserved.update(item["capability_id"] for item in other.capabilities)
    if reserved.intersection(item["capability_id"] for item in declarations):
        raise CapabilityRegistryError(
            "Capability is already declared by another provider"
        )


def _clear_state(db: Session, device: Device, declarations):
    ids = {item["capability_id"] for item in declarations}
    if ids:
        db.execute(
            delete(DeviceCapabilityState).where(
                DeviceCapabilityState.device_id == device.id,
                DeviceCapabilityState.capability_id.in_(ids),
            )
        )


def replace_provider(db: Session, device: Device, report: CapabilityProviderReportV1):
    """Replace one provider atomically, never Core-owned enabled or module state.

    Caller commits with the response or rolls back CapabilityRegistryError.
    Empty declarations withdraw capabilities but retain the revision tombstone.
    """
    if report.device_id != device.device_id:
        raise CapabilityRegistryError("Provider report identity does not match device")
    _lock_device(db, device)
    providers = _providers(db, device)
    provider = next(
        (
            row
            for row in providers
            if (row.provider_type, row.provider_id)
            == (report.provider_type, report.provider_id)
        ),
        None,
    )
    declarations = [
        item.model_dump()
        for item in sorted(report.capabilities, key=lambda item: item.capability_id)
    ]
    revision = provider.revision if provider else 0
    same = (
        provider is not None
        and provider.provider_version == report.provider_version
        and provider.capabilities == declarations
    )
    if report.expected_revision != revision:
        if same and report.expected_revision == revision - 1:
            return provider  # Exact retry after a lost acknowledgement.
        raise CapabilityRegistryError(
            "Provider revision changed; read the current revision"
        )
    if same:
        return provider
    if revision >= 2_147_483_646:
        raise CapabilityRegistryError("Provider revision limit reached")
    if provider is None and len(providers) >= 16:
        raise CapabilityRegistryError("Device provider limit reached")
    total = len(declarations) + sum(
        len(row.capabilities) for row in providers if row is not provider
    )
    if total > 256:
        raise CapabilityRegistryError("Device advertised capability limit reached")
    _check_conflicts(db, device, providers, provider, declarations)
    _clear_state(
        db, device, [*(provider.capabilities if provider else []), *declarations]
    )
    now = datetime.now(UTC)
    if provider is None:
        provider = DeviceCapabilityProvider(
            device_id=device.id,
            provider_type=report.provider_type,
            provider_id=report.provider_id,
            enabled=True,
        )
        db.add(provider)
    provider.provider_version = report.provider_version
    provider.capabilities = declarations
    provider.revision = revision + 1
    provider.reported_at = now
    db.add(
        DeviceEvent(
            device_id=device.id,
            event_id=f"evt_{uuid4().hex}",
            event_type="capability.provider.updated",
            occurred_at=now,
            payload={
                "provider_type": provider.provider_type,
                "provider_id": provider.provider_id,
                "provider_version": provider.provider_version,
                "revision": provider.revision,
                "capability_ids": [item["capability_id"] for item in declarations],
            },
        )
    )
    db.flush()
    return provider


def set_provider_enabled(
    db: Session,
    device: Device,
    provider_type: str,
    provider_id: str,
    *,
    expected_revision: int,
    enabled: bool,
    actor_user_id: int,
):
    _lock_device(db, device)
    providers = _providers(db, device)
    provider = next(
        (
            row
            for row in providers
            if (row.provider_type, row.provider_id) == (provider_type, provider_id)
        ),
        None,
    )
    if provider is None:
        raise CapabilityRegistryError("Provider was not found")
    if provider.revision != expected_revision:
        raise CapabilityRegistryError(
            "Provider revision changed; read the current revision"
        )
    if provider.enabled == enabled:
        return provider
    if provider.revision >= 2_147_483_646:
        raise CapabilityRegistryError("Provider revision limit reached")
    if enabled:
        _check_conflicts(db, device, providers, provider, provider.capabilities)
    _clear_state(db, device, provider.capabilities)
    provider.enabled = enabled
    provider.revision += 1
    db.add(
        AuditLog(
            user_id=actor_user_id,
            action="UPDATE",
            entity_type="device_capability_provider",
            entity_id=provider.id,
            entity_name=device.device_id,
            changes={
                "provider_type": provider_type,
                "provider_id": provider_id,
                "enabled": enabled,
                "revision": provider.revision,
            },
        )
    )
    db.flush()
    return provider
