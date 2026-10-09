"""DB-only Agent-module authority changes inside the owning device guard."""

from datetime import UTC, datetime
from uuid import uuid4

from backend.db.audit_log import AuditLog
from backend.db.device import DeviceEvent
from backend.services.authority_metadata import read_device_control


def module_control_snapshot(installation):
    if installation is None:
        return None
    return {name: getattr(installation, name) for name in (
        "module_package_id", "module_id", "desired_version", "installed_version",
        "status", "enabled", "command_id", "data_retained",
    )}


def record_module_transition(db, mutation, device, installation, before, *, source,
                             admin_id=None):
    """Advance once per effective transition; never audit package bytes/results."""
    mutation.require_session(db)
    after = module_control_snapshot(installation)
    if before == after:
        return False
    control = mutation.advance_device_control(read_device_control(db, device.id))
    payload = {
        "source": source, "before": before, "after": after,
        "control_generation": control.generation,
    }
    db.add(DeviceEvent(
        device_id=device.id, event_id="evt_" + uuid4().hex,
        event_type="device.module.lifecycle.updated", payload=payload,
        occurred_at=datetime.now(UTC),
    ))
    if admin_id is not None:
        db.add(AuditLog(
            user_id=admin_id, action="UPDATE", entity_type="device_module",
            entity_id=device.id, entity_name=installation.module_id, changes=payload,
        ))
    db.flush()
    return True
