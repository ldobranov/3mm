"""Read enabled capability registrations without knowing concrete modules."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.device import Device
from backend.db.module import ModuleInstallation, ModulePackage


def registered_capabilities(db: Session, device: Device) -> list[dict]:
    result: list[dict] = []
    installations = db.scalars(select(ModuleInstallation).where(
        ModuleInstallation.device_id == device.id,
        ModuleInstallation.enabled.is_(True),
        ModuleInstallation.status == "succeeded",
    ))
    for installation in installations:
        package = db.get(ModulePackage, installation.module_package_id)
        if package is None:
            continue
        for item in package.registrations or []:
            if item.get("kind") == "capability":
                result.append({
                    "capability_id": item["registration_id"],
                    "module_id": package.module_id,
                    "version": package.version,
                    "metadata": item.get("metadata", {}),
                })
    return result


def has_registered_capability(db: Session, device: Device, capability_id: str) -> bool:
    return any(item["capability_id"] == capability_id for item in registered_capabilities(db, device))
