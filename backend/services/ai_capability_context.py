"""Read-only capability context supplied to AI automation planning."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.device import Device
from backend.services.device_capability_registry import registered_capabilities
from three_mm_protocol.automation import (
    AutomationCapabilityContextV1,
    AutomationCapabilityContextV2,
    CapabilityContextEntry,
    ProviderCapabilityContextEntry,
)


def build_automation_capability_context(db: Session) -> AutomationCapabilityContextV1:
    """Expose only approved devices and successful enabled registrations."""

    devices = db.scalars(
        select(Device)
        .where(Device.approved_at.is_not(None), Device.revoked_at.is_(None))
        .order_by(Device.device_id)
    ).all()
    entries: list[ProviderCapabilityContextEntry] = []

    for device in devices:
        for registration in registered_capabilities(db, device):
            entries.append(
                ProviderCapabilityContextEntry(
                    device_id=device.device_id,
                    device_name=device.display_name or device.device_id,
                    device_role=device.role,
                    capability_id=registration["capability_id"],
                    provider_type=registration["provider_type"],
                    provider_id=registration["provider_id"],
                    provider_version=registration["provider_version"],
                    metadata=registration["metadata"],
                )
            )

    entries.sort(
        key=lambda item: (item.device_id, item.capability_id, item.provider_id)
    )
    if any(item.provider_type != "agent_module" for item in entries):
        return AutomationCapabilityContextV2(capabilities=tuple(entries))
    # Existing module-only consumers retain their exact version-1 response.
    return AutomationCapabilityContextV1(
        capabilities=tuple(
            CapabilityContextEntry(
                device_id=item.device_id,
                device_name=item.device_name,
                device_role=item.device_role,
                capability_id=item.capability_id,
                module_id=item.provider_id,
                module_version=item.provider_version,
                metadata=item.metadata,
            )
            for item in entries
        )
    )
