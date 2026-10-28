"""Shared Core lifecycle tickets, consumed by the existing privileged helper."""

from copy import deepcopy
from dataclasses import dataclass

from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationExtensionInstallation
from backend.services.application_commands import invalidate_commands
from backend.services.authority_metadata import ApplicationAuthoritySnapshot, read_application_authority


@dataclass(frozen=True)
class _LifecycleTicket:
    application: ApplicationAuthoritySnapshot
    operation: str
    state: tuple
    guard_generation: str


def _helper_lifecycle(ticket):
    return {
        "installation_id": ticket.application.installation_id,
        "module_id": ticket.application.module_id,
        "instance_id": ticket.state[2],
        "incarnation": ticket.application.incarnation,
        "epoch": ticket.application.epoch,
        "guard_generation": ticket.guard_generation,
    }


def _lifecycle_state(installation):
    return (
        installation.module_package_id, installation.previous_package_id,
        installation.instance_id, installation.active_version,
        installation.status, installation.enabled, installation.socket_path,
        deepcopy(installation.configuration),
    )


def _package_state(package):
    return (package.id, package.module_id, package.version, package.sha256,
        package.file_path, deepcopy(package.manifest))


def _lifecycle_audit(db, actor_id, module_id, action, **changes):
    db.add(AuditLog(user_id=actor_id, action=action, entity_type="application_extension",
        entity_name=module_id, changes=changes))


def _start_lifecycle(db, authority, installation, operation, actor_id):
    current = authority.advance_application_epoch(read_application_authority(db, installation.id))
    installation.status = operation
    installation.enabled = False
    installation.error = None
    invalidate_commands(db, installation.id)
    _lifecycle_audit(db, actor_id, installation.module_id, "APPLICATION_EXTENSION_LIFECYCLE_STARTED",
        operation=operation, version=installation.active_version)
    db.flush()
    return _LifecycleTicket(current, operation, _lifecycle_state(installation), authority.guard.generation)


def _lock_lifecycle(db, authority, ticket):
    if authority.guard.generation != ticket.guard_generation:
        authority.reject()
    authority.lock_application(ticket.application, lifecycle_status=ticket.operation)
    installation = db.get(ApplicationExtensionInstallation, ticket.application.installation_id,
        populate_existing=True)
    if installation is None or _lifecycle_state(installation) != ticket.state:
        authority.reject()
    authority.advance_application_epoch(ticket.application)
    return installation
