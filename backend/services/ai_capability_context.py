"""Read-only capability context supplied to AI automation planning."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.device import Device
from backend.db.module import ModuleInstallation, ModulePackage
from three_mm_protocol.automation import (
    AutomationCapabilityContextV1,
    CapabilityContextEntry,
)


def build_automation_capability_context(db: Session) -> AutomationCapabilityContextV1:
    """Expose only approved devices and successful enabled registrations."""

    devices = db.scalars(
        select(Device)
        .where(Device.approved_at.is_not(None), Device.revoked_at.is_(None))
        .order_by(Device.device_id)
    ).all()
    entries: list[CapabilityContextEntry] = []

    for device in devices:
        installations = db.scalars(
            select(ModuleInstallation).where(
                ModuleInstallation.device_id == device.id,
                ModuleInstallation.enabled.is_(True),
                ModuleInstallation.status == "succeeded",
            )
        ).all()
        for installation in installations:
            package = db.get(ModulePackage, installation.module_package_id)
            if package is None:
                continue
            for registration in package.registrations or []:
                if registration.get("kind") != "capability":
                    continue
                entries.append(CapabilityContextEntry(
                    device_id=device.device_id,
                    device_name=device.display_name or device.device_id,
                    device_role=device.role,
                    capability_id=registration["registration_id"],
                    module_id=package.module_id,
                    module_version=package.version,
                    metadata=registration.get("metadata", {}),
                ))

    return AutomationCapabilityContextV1(
        capabilities=tuple(sorted(
            entries,
            key=lambda item: (item.device_id, item.capability_id, item.module_id),
        ))
    )
