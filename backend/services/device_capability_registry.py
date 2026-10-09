"""One Core capability query for module and device-advertised providers.

Module installations remain authoritative through a live compatibility adapter;
non-module providers do not need packages, Fleet or a particular runtime.
"""

from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from backend.db.audit_log import AuditLog
from backend.db.device import (
    Device,
    DeviceCapabilityProvider,
    DeviceCapabilityState,
    DeviceEvent,
    DeviceCapabilityHealth,
    DeviceHeartbeat,
    DeviceInventorySnapshot,
    DevicePlatformState,
    DeviceCredential,
)
from backend.db.module import ModuleInstallation, ModulePackage
from three_mm_protocol import CapabilityProviderReportV1, CapabilityProviderSnapshotV1
from three_mm_protocol.capability_contracts import CONTRACT_FEATURE, registration_contract
from backend.services.device_runtime_features import read_runtime_features
from backend.services.device_registry import as_utc, is_device_online
from backend.services.device_authority import device_authority_write
from backend.services.authority_metadata import read_device_control
from three_mm_protocol.device_capabilities import CapabilityProviderSnapshotV2
from three_mm_protocol.capability_availability import (
    AVAILABILITY_FEATURE, CapabilityDiscoveryV3, declaration_digest,
)


class CapabilityRegistryError(ValueError):
    """A conflicting registration or stale provider revision."""


def _module_capabilities(db: Session, device: Device, *, include_inactive=False) -> list[dict]:
    result = []
    query = (
        select(ModulePackage, ModuleInstallation)
        .join(
            ModuleInstallation, ModuleInstallation.module_package_id == ModulePackage.id
        )
        .where(
            ModuleInstallation.device_id == device.id,
        )
    )
    if not include_inactive:
        query = query.where(ModuleInstallation.enabled.is_(True), ModuleInstallation.status == "succeeded")
    for package, installation in db.execute(query):
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
                        **({"configured": installation.enabled and installation.status == "succeeded"} if include_inactive else {}),
                        **({"contract": item["contract"]} if item.get("contract") is not None else {}),
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
            if provider.configured_capability_ids is not None and item["capability_id"] not in provider.configured_capability_ids:
                continue
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
    for item in result:
        contract = registration_contract(item["capability_id"], item.get("contract"))
        if contract is not None:
            item["contract"] = contract.model_dump(mode="json")
            item["contract_version"] = contract.contract_version
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


def validate_invocation(db, device, payload, *, prepare=False):
    """One pre-dispatch contract boundary, also for application/raw queue APIs.

    Unknown legacy contracts retain previous behavior. An explicit request must
    never be downgraded to legacy. The digest pins schema contents at queue time.
    """
    registration = next((item for item in registered_capabilities(db, device)
                         if item["capability_id"] == payload.get("capability_id")), None)
    if registration is None:
        raise CapabilityRegistryError("Capability is not configured on this device")
    contract = registration_contract(payload.get("capability_id"), registration.get("contract") if registration else None)
    if contract is None:
        if payload.get("contract_version") is not None or payload.get("contract_digest") is not None:
            raise CapabilityRegistryError("Requested versioned capability is unavailable")
        return dict(payload)
    support = read_runtime_features(db, device)
    if support is None or CONTRACT_FEATURE not in support.declaration["features"]:
        raise CapabilityRegistryError("Device runtime does not advertise capability contract enforcement")
    contract.invocation(payload, require_digest=not prepare)
    return {**payload, "contract_digest": contract.digest()}


def provider_snapshot(
    device: Device, provider: DeviceCapabilityProvider
) -> CapabilityProviderSnapshotV1:
    reported_at = provider.reported_at
    if reported_at.tzinfo is None:
        reported_at = reported_at.replace(tzinfo=UTC)
    model = CapabilityProviderSnapshotV2 if provider.configured_capability_ids is not None else CapabilityProviderSnapshotV1
    return model(
        device_id=device.device_id,
        provider_type=provider.provider_type,
        provider_id=provider.provider_id,
        provider_version=provider.provider_version,
        revision=provider.revision,
        enabled=provider.enabled,
        capabilities=tuple(provider.capabilities),
        reported_at=reported_at,
        **({"configured_capability_ids": tuple(provider.configured_capability_ids)}
           if provider.configured_capability_ids is not None else {}),
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
    # Serialize health evidence with device changes, without advancing authority.
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


def replace_provider(db: Session, device: Device, report: CapabilityProviderReportV1, *, credential_id=None):
    """Replace one provider atomically, never Core-owned enabled or module state.

    Own the resource/control-generation/audit commit; callers enter with only
    read-only preflight, not pending work. Device adapters pass authenticated ID.
    Empty declarations withdraw capabilities but retain the revision tombstone.
    """
    with device_authority_write(db, device, credential_id=credential_id) as (mutation, current):
        return _replace_provider(db, current, report, mutation)


def _replace_provider(db, device, report, mutation):
    mutation.require_session(db)
    if report.device_id != device.device_id:
        raise CapabilityRegistryError("Provider report identity does not match device")
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
    runtime = read_runtime_features(db, device)
    explicit_mode = (report.schema_version == 2
                     or (runtime is not None and AVAILABILITY_FEATURE in runtime.declaration["features"])
                     or any(row.configured_capability_ids is not None for row in providers))
    transition = explicit_mode and (provider is None or provider.configured_capability_ids is None)
    same = (
        provider is not None
        and provider.provider_version == report.provider_version
        and provider.capabilities == declarations
        and not transition
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
    mutation.advance_device_control(read_device_control(db, device.id))
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
    if transition:
        # Existing approved v1 selections survive opt-in. New v2 providers start
        # with no selection. A device can never downgrade this Core-owned mode.
        provider.configured_capability_ids = [item["capability_id"] for item in (provider.capabilities or [])]
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


def configure_provider(db, device, provider_type, provider_id, request, *, actor_user_id):
    with device_authority_write(db, device) as (mutation, current):
        return _configure_provider(db, current, provider_type, provider_id, request,
                                   actor_user_id=actor_user_id, mutation=mutation)


def _configure_provider(db, device, provider_type, provider_id, request, *, actor_user_id, mutation):
    mutation.require_session(db)
    provider = read_provider(db, device, provider_type, provider_id)
    if provider is None or provider.configured_capability_ids is None:
        raise CapabilityRegistryError("Explicit configuration requires a v2 provider")
    if provider.revision != request.expected_revision or provider.revision >= 2147483646:
        raise CapabilityRegistryError("Provider revision changed; read and retry")
    ids = set(request.capability_ids)
    if not ids <= {item["capability_id"] for item in provider.capabilities}:
        raise CapabilityRegistryError("Configuration must select current provider offers, not inventory")
    if sorted(ids) == sorted(provider.configured_capability_ids):
        return provider
    _check_conflicts(db, device, _providers(db, device), provider, provider.capabilities)
    mutation.advance_device_control(read_device_control(db, device.id))
    provider.configured_capability_ids = sorted(ids)
    provider.revision += 1
    db.add(AuditLog(user_id=actor_user_id, action="UPDATE", entity_type="device_capability_configuration",
                    entity_id=provider.id, entity_name=device.device_id,
                    changes={"provider_type": provider_type, "provider_id": provider_id,
                             "capability_ids": sorted(ids), "revision": provider.revision}))
    db.flush()
    return provider


def _offers(db, device):
    rows = _module_capabilities(db, device, include_inactive=True)
    for provider in _providers(db, device):
        for item in provider.capabilities:
            rows.append({**item, "provider_type": provider.provider_type, "provider_id": provider.provider_id,
                         "provider_version": provider.provider_version, "configured": provider.enabled and
                         (provider.configured_capability_ids is None or item["capability_id"] in provider.configured_capability_ids),
                         "requires_health": provider.configured_capability_ids is not None})
    return rows


def _group_digest(rows, row):
    declarations = [{key: item[key] for key in ("capability_id", "metadata", "contract") if key in item}
                    for item in rows if (item["provider_type"], item["provider_id"]) == (row["provider_type"], row["provider_id"])]
    return declaration_digest(row["provider_type"], row["provider_id"], row["provider_version"], declarations)


def report_availability(db, device, report, *, now=None):
    if report.device_id != device.device_id:
        raise CapabilityRegistryError("Availability identity mismatch")
    _lock_device(db, device)
    rows = _offers(db, device)
    offers = [row for row in rows if (row["provider_type"], row["provider_id"]) == (report.provider_type, report.provider_id)]
    if (not offers or report.provider_version != offers[0]["provider_version"]
            or report.declaration_digest != _group_digest(rows, offers[0])
            or not {item.capability_id for item in report.capabilities} <= {item["capability_id"] for item in offers}):
        raise CapabilityRegistryError("Availability must match a current provider declaration")
    now = now or datetime.now(UTC)
    observed = as_utc(report.observed_at)
    if observed > now + timedelta(seconds=30) or observed + timedelta(seconds=report.valid_for_seconds) <= now:
        raise CapabilityRegistryError("Availability timestamp is stale or in the future")
    row = db.scalar(select(DeviceCapabilityHealth).where(DeviceCapabilityHealth.device_id == device.id,
        DeviceCapabilityHealth.provider_type == report.provider_type, DeviceCapabilityHealth.provider_id == report.provider_id)
        .execution_options(populate_existing=True))
    payload = report.model_dump(mode="json")
    if row is not None:
        if observed < as_utc(row.observed_at) or (observed == as_utc(row.observed_at) and row.report != payload):
            raise CapabilityRegistryError("Availability evidence is stale or conflicting")
        if observed == as_utc(row.observed_at):
            return row  # Lost-response retry never extends the health lease.
    else:
        row = DeviceCapabilityHealth(device_id=device.id, provider_type=report.provider_type, provider_id=report.provider_id)
        db.add(row)
    row.report, row.observed_at = payload, observed
    row.expires_at = min(now, observed) + timedelta(seconds=report.valid_for_seconds)
    db.flush()
    return row


def capability_catalog(db, device, *, now=None):
    """One registry boundary: discovery is descriptive, configuration is authority."""
    from backend.config import get_settings
    now = now or datetime.now(UTC)
    rows = _offers(db, device)
    registered = {(row["capability_id"], row["provider_type"], row["provider_id"]): row
                  for row in registered_capabilities(db, device)}
    latest = db.scalar(select(DeviceHeartbeat).where(DeviceHeartbeat.device_id == device.id)
                       .order_by(DeviceHeartbeat.received_at.desc(), DeviceHeartbeat.id.desc()).limit(1))
    online = is_device_online(last_seen_at=latest.received_at if latest else None, now=now,
        offline_after=timedelta(seconds=get_settings().backend.device_offline_after_seconds), revoked_at=device.revoked_at)
    platform = db.get(DevicePlatformState, device.id, populate_existing=True)
    credentials = list(db.scalars(select(DeviceCredential).where(DeviceCredential.device_id == device.id)))
    authority = (device.approved_at is not None and device.revoked_at is None
                 and (not credentials or any(item.revoked_at is None for item in credentials))
                 and (platform is None or (platform.authority_status == "bound" and platform.lifecycle not in
                       {"recovery", "revoked", "unowned", "enrollment_pending"})))
    runtime = read_runtime_features(db, device)
    strict = runtime is not None and AVAILABILITY_FEATURE in runtime.declaration["features"]
    health = {(item.provider_type, item.provider_id): item for item in db.scalars(
        select(DeviceCapabilityHealth).where(DeviceCapabilityHealth.device_id == device.id).execution_options(populate_existing=True))}
    result = []
    for row in rows:
        key = row["capability_id"], row["provider_type"], row["provider_id"]
        configured = key in registered
        digest = _group_digest(rows, row)
        report = health.get((row["provider_type"], row["provider_id"]))
        entry = next((item for item in (report.report["capabilities"] if report else [])
                      if item["capability_id"] == row["capability_id"]), None)
        reason = None
        if not configured:
            reason = "not_configured" if not row["configured"] else "provider_conflict_or_inactive"
        elif not authority:
            reason = "authority_inactive"
        elif not online:
            reason = "device_offline"
        elif report is not None and report.report["declaration_digest"] != digest:
            reason = "provider_changed"
        elif report is not None and as_utc(report.expires_at) <= now:
            reason = "health_stale"
        elif entry is not None and entry["healthy"] is not True:
            reason = entry.get("reason") or "provider_unhealthy"
        elif entry is None:
            reason = "health_missing" if strict or row.get("requires_health") else "legacy_health_unknown"
        effective = registered.get(key, row)
        contract = registration_contract(row["capability_id"], effective.get("contract"))
        result.append(CapabilityDiscoveryV3(capability_id=row["capability_id"], provider_type=row["provider_type"],
            provider_id=row["provider_id"], provider_version=row["provider_version"], metadata=row.get("metadata", {}),
            contract=contract.model_dump(mode="json") if contract else None,
            contract_version=contract.contract_version if contract else None,
            supported=True, registered=configured, available=None if reason == "legacy_health_unknown" else reason is None,
            unavailable_reason=reason, declaration_digest=digest))
    inventory = db.scalar(select(DeviceInventorySnapshot).where(DeviceInventorySnapshot.device_id == device.id)
        .order_by(DeviceInventorySnapshot.received_at.desc(), DeviceInventorySnapshot.id.desc()).limit(1))
    known = {item.capability_id for item in result}
    for capability_id in (inventory.inventory.get("capabilities", []) if inventory else []):
        if isinstance(capability_id, str) and capability_id not in known:
            known.add(capability_id)
            result.append(CapabilityDiscoveryV3(capability_id=capability_id, supported=True,
                registered=False, available=False, unavailable_reason="inventory_only"))
    return sorted(result, key=lambda item: (item.capability_id, item.provider_type or "", item.provider_id or ""))


def can_dispatch_capability(db, device, capability_id, *, now=None):
    """Legacy compatibility, explicit health reports and new v2 providers fail closed."""
    registration = next((row for row in registered_capabilities(db, device) if row["capability_id"] == capability_id), None)
    if registration is None:
        return False
    runtime = read_runtime_features(db, device)
    provider = read_provider(db, device, registration["provider_type"], registration["provider_id"])
    health = db.scalar(select(DeviceCapabilityHealth.id).where(DeviceCapabilityHealth.device_id == device.id,
        DeviceCapabilityHealth.provider_type == registration["provider_type"], DeviceCapabilityHealth.provider_id == registration["provider_id"]))
    strict = ((runtime is not None and AVAILABILITY_FEATURE in runtime.declaration["features"])
              or (provider is not None and provider.configured_capability_ids is not None) or health is not None)
    if not strict:
        return True  # Old runtimes keep existing queue/receipt semantics, not a healthy claim.
    return any(row.capability_id == capability_id and row.registered and row.available is True
               for row in capability_catalog(db, device, now=now))


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
    with device_authority_write(db, device) as (mutation, current):
        return _set_provider_enabled(db, current, provider_type, provider_id,
            expected_revision=expected_revision, enabled=enabled,
            actor_user_id=actor_user_id, mutation=mutation)


def _set_provider_enabled(db, device, provider_type, provider_id, *, expected_revision,
                          enabled, actor_user_id, mutation):
    mutation.require_session(db)
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
    mutation.advance_device_control(read_device_control(db, device.id))
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
