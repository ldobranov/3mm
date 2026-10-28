"""A projection of current declarations, selections and grants, never a registry.

Administrators inspect candidates; an SDK caller sees only its exact currently
granted selection. Discovery neither admits work nor creates keys or grants.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from backend.db.device import Device
from backend.db.module import ApplicationExtensionInstallation
from backend.services import application_authority_sources as sources
from backend.services.application_authority_context import _canonical_bytes, _command_schema_data
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_authority_management import AuthorityManagementError
from backend.services.device_capability_registry import capability_catalog
from three_mm_protocol.application_command_discovery import (
    CommandCandidateV1, CommandDiscoveryRequestV1, CommandDiscoveryV1,
)
from three_mm_protocol.capability_contracts import registration_contract


def _binding(definition, binding_id):
    CommandDiscoveryRequestV1(binding_id=binding_id)
    binding = next((item for item in definition.command_bindings if item.binding_id == binding_id), None)
    if binding is None:
        raise ValueError("Command requirement is not declared")
    return binding


def _candidate(db, binding, device, now):
    offers = [item for item in capability_catalog(db, device, now=now)
              if item.capability_id == binding.capability_id]
    # The existing registry permits one effective provider per capability/device.
    # Conflicts are not a reason to pick an arbitrary provider.
    effective = [item for item in offers if item.registered]
    offer = effective[0] if len(effective) == 1 else offers[0] if len(offers) == 1 else None
    blockers = []
    contract = registration_contract(binding.capability_id, offer.contract) if offer else None
    if len(offers) > 1 and not effective:
        blockers.append("provider_ambiguous")
    elif contract is None:
        blockers.append("contract_missing")
    elif binding.contract_version != contract.contract_version:
        blockers.append("contract_version_mismatch")
    elif binding.action not in contract.actions:
        blockers.append("action_missing")
    elif (_canonical_bytes(_command_schema_data(binding.arguments_schema)) !=
          _canonical_bytes(_command_schema_data(contract.actions[binding.action].arguments_schema))):
        # Same conservative rule as actual sealed authority: no inferred schema
        # containment, version upgrades or guarantees from matching names alone.
        blockers.append("command_schema_containment_not_evaluated")
    compatible = not blockers
    if binding.sensor_device_config_key is not None:
        blockers.append("sensor_contract_unresolved")
    if offer is None or not offer.registered:
        blockers.append("resource_not_configured")
    elif not blockers:
        try:
            sources._command(db, binding, {binding.target_device_config_key: device.device_id})
        except sources._Unavailable as exc:
            blockers.append(exc.issue.reason)
    reason = offer.unavailable_reason if offer else "provider_missing"
    readiness = ("unknown" if reason in {"health_missing", "health_stale", "legacy_health_unknown"}
                 else "ready" if offer and offer.available is True else "unavailable")
    return CommandCandidateV1(
        device_id=device.device_id,
        provider_type=offer.provider_type if offer else None,
        provider_id=offer.provider_id if offer else None,
        provider_version=offer.provider_version if offer else None,
        contract_version=offer.contract_version if offer else None,
        compatible=compatible, selectable=not blockers, blockers=blockers,
        readiness=readiness, readiness_reason=reason,
    )


def _result(binding, *, now, selected=None, candidates=(), access="not_evaluated", next_after=None):
    return CommandDiscoveryV1(
        binding_id=binding.binding_id, capability_id=binding.capability_id,
        contract_version=binding.contract_version, action=binding.action,
        observed_at=now, access=access, selected_device_id=selected,
        candidates=list(candidates), next_after_device_id=next_after,
    ).model_dump(mode="json")


def discover_candidates(db, definition, binding_id, *, configuration=None, after_device_id=None):
    """Admin-only, bounded device pages; no execution or permission evaluation."""
    binding = _binding(definition, binding_id)
    now = datetime.now(UTC)
    query = select(Device).where(Device.approved_at.is_not(None), Device.revoked_at.is_(None))
    if after_device_id is not None:
        query = query.where(Device.device_id > after_device_id)
    with db.no_autoflush:
        devices = list(db.scalars(query.order_by(Device.device_id).limit(33)))
        candidates = [_candidate(db, binding, device, now) for device in devices[:32]]
    return _result(binding, now=now, candidates=candidates,
                   selected=(configuration or {}).get(binding.target_device_config_key),
                   next_after=devices[31].device_id if len(devices) > 32 else None)


def discover_selected_command(engine, installation_id, instance_id, binding_id):
    """Observe one sealed grant in a DB-enforced read-only snapshot.

No compatibility authority: missing/revoked/stale access reveals the declared
need, without resource identities or alternatives from another installation.
The actual submit/permit paths independently recheck current authority.
"""
    from backend.services.application_authority_management import configured_manager

    manager = configured_manager(engine)
    prepared = manager._prepare(installation_id)
    binding = _binding(prepared.package.application_extension, binding_id)
    now = datetime.now(UTC)
    denied = _result(binding, now=now, access="required")
    try:
        with manager.keys.locked() as key, sources._read_snapshot(engine) as db:
            app = db.get(ApplicationExtensionInstallation, installation_id)
            if (app is None or app.instance_id != instance_id or not app.enabled
                    or app.status != "active"):
                return denied
            manager._require_grant(db, key, installation_id, prepared, "command:" + binding_id)
            target = (app.configuration or {}).get(binding.target_device_config_key)
            device = db.scalar(select(Device).where(Device.device_id == target))
            if device is None:
                return denied
            return _result(binding, now=now, selected=device.device_id, access="granted",
                           candidates=[_candidate(db, binding, device, now)])
    except (AuthorityManagementError, AuthorityReviewKeyError, sources._Unavailable):
        return denied
