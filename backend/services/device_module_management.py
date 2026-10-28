"""Shared Agent-module lifecycle; HTTP callers supply their authority scope."""
import base64
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.db.device import Device, DeviceCommand, DeviceInventorySnapshot
from backend.db.module import ModuleInstallation, ModulePackage
from backend.db.user import User
from backend.services.device_commands import DeviceCommandError, queue_command
from backend.services.device_command_notifier import device_command_notifier
from backend.services.device_authority import device_authority_write, require_device_authority_session
from backend.services.authority_metadata import AuthorityMetadataError
from backend.services.device_module_authority import module_control_snapshot, record_module_transition
from backend.services.module_packages import ModulePackageError, validate_module_package
from three_mm_protocol.device_inventory import inventory_value

class InstallationResponse(BaseModel):
    module_id:str; desired_version:str; installed_version:str|None; status:str; enabled:bool; command_id:str|None; data_retained:bool; error:str|None
    model_config=ConfigDict(from_attributes=True)

@contextmanager
def _write_scope(db, device):
    with device_authority_write(db, device) as (mutation, current):
        yield db, mutation, current

def _device_architecture(db,device):
    snapshot=db.scalar(select(DeviceInventorySnapshot).where(DeviceInventorySnapshot.device_id==device.id).order_by(DeviceInventorySnapshot.received_at.desc()).limit(1))
    return inventory_value(snapshot.inventory, "architecture") if snapshot else None


def _lifecycle_idempotency_key(
    db: Session, *, device: Device, command_type: str, module_id: str,
    legacy_key: str, client_key: str | None, admin_id: int,
) -> str:
    if client_key is not None:
        identity = json.dumps([admin_id, command_type, module_id, client_key])
        digest = hashlib.sha256(identity.encode()).hexdigest()
        suffix = ":" + client_key if len(client_key) <= 48 else ""
        return "module.client:" + digest + suffix
    opposite = "module.disable" if command_type == "module.install" else "module.install"
    completed = db.scalar(
        select(DeviceCommand).where(
            DeviceCommand.device_id == device.id,
            DeviceCommand.command_type == opposite,
            DeviceCommand.payload["module_id"].as_string() == module_id,
            DeviceCommand.status == "succeeded",
            DeviceCommand.completed_at.is_not(None),
        ).order_by(DeviceCommand.completed_at.desc(), DeviceCommand.id.desc()).limit(1)
    )
    # Retain existing initial-episode keys, including requests queued by older Core versions.
    if completed is None and len(legacy_key) <= 128:
        return legacy_key
    identity = json.dumps([legacy_key, completed.command_id if completed else None])
    return "module.lifecycle.legacy:" + hashlib.sha256(identity.encode()).hexdigest()


def _queue_lifecycle_command(db: Session, *, device: Device, **values):
    existing = db.scalar(select(DeviceCommand).where(
        DeviceCommand.device_id == device.id,
        DeviceCommand.idempotency_key == values["idempotency_key"],
    ))
    try:
        command = queue_command(db, device=device, **values)
    except DeviceCommandError as exc:
        raise HTTPException(409, str(exc)) from exc
    return command, existing is not None


def install_module(sha256:str,device_id:str,_admin:User,db:Session,
                   idempotency_key:str|None=None, *, write_scope=None, on_queued=None):
    try:
        require_device_authority_session(db)
    except AuthorityMetadataError as exc:
        raise HTTPException(409, str(exc)) from exc
    package=db.scalar(select(ModulePackage).where(ModulePackage.sha256==sha256)); device=db.scalar(select(Device).where(Device.device_id==device_id))
    if not package or not device: raise HTTPException(404,"package or device was not found")
    # Read and validate immutable bytes before the short DB-only write scope.
    package_identity = (package.id, package.module_id, package.version, package.sha256)
    runtime_identity = (_device_architecture(db, device), device.protocol_version)
    admin_id = _admin.id
    try:
        blob = Path(package.file_path).read_bytes()
        validated = validate_module_package(blob, architecture=runtime_identity[0], protocol_version=runtime_identity[1])
    except ModulePackageError as exc:
        raise HTTPException(409, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(409, "Module package could not be read") from exc
    if (validated.manifest.module_id, validated.manifest.version, validated.sha256) != package_identity[1:]:
        raise HTTPException(409, "Module package identity changed")
    if validated.application_extension is not None:
        raise HTTPException(409, "Application extensions run on Core, not on an Agent")
    if validated.theme_extension is not None:
        raise HTTPException(409, "Theme extensions run in the UI, not on an Agent")
    if "agent" not in validated.manifest.runtimes:
        raise HTTPException(409, "Package does not declare an Agent runtime")
    encoded = base64.b64encode(blob).decode()
    try:
        with (write_scope or _write_scope)(db, device) as (db, mutation, current):
            package = db.get(ModulePackage, package_identity[0], populate_existing=True)
            if (package is None or (package.id, package.module_id, package.version, package.sha256) != package_identity
                    or (_device_architecture(db, current), current.protocol_version) != runtime_identity):
                raise HTTPException(409, "Module package or device runtime changed; retry")
            installation = db.scalar(select(ModuleInstallation).where(
                ModuleInstallation.device_id == current.id, ModuleInstallation.module_id == package.module_id,
            ).execution_options(populate_existing=True))
            before = module_control_snapshot(installation)
            key = _lifecycle_idempotency_key(db, device=current, command_type="module.install", module_id=package.module_id,
                legacy_key=f"module.install:{package.module_id}:{package.sha256}", client_key=idempotency_key, admin_id=admin_id)
            command, replay = _queue_lifecycle_command(db, device=current, command_type="module.install",
                payload={"package_base64": encoded, "sha256": package.sha256, "module_id": package.module_id, "version": package.version},
                idempotency_key=key, ttl_seconds=900)
            if replay and installation is None:
                raise HTTPException(409, "Module installation requires recovery")
            if not replay:
                if installation is None:
                    installation = ModuleInstallation(device_id=current.id, module_id=package.module_id, data_retained=True)
                    db.add(installation)
                installation.module_package_id = package.id
                installation.desired_version = package.version
                installation.status, installation.command_id = command.status, command.command_id
                installation.enabled, installation.error = True, None
                record_module_transition(db, mutation, current, installation, before, source="install_requested", admin_id=admin_id)
            response = InstallationResponse.model_validate(installation)
            if on_queued is not None:
                on_queued(command)
            device_pk = current.id
    except AuthorityMetadataError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not replay:
        device_command_notifier.notify(device_pk)
    return response

def disable_module(module_id:str,device_id:str,_admin:User,db:Session,
                   idempotency_key:str|None=None, *, write_scope=None, on_queued=None):
    try:
        require_device_authority_session(db)
    except AuthorityMetadataError as exc:
        raise HTTPException(409, str(exc)) from exc
    device=db.scalar(select(Device).where(Device.device_id==device_id)); installation=db.scalar(select(ModuleInstallation).where(ModuleInstallation.device_id==device.id,ModuleInstallation.module_id==module_id)) if device else None
    if not installation: raise HTTPException(404,"module installation was not found")
    admin_id = _admin.id
    try:
        with (write_scope or _write_scope)(db, device) as (db, mutation, current):
            installation = db.scalar(select(ModuleInstallation).where(
                ModuleInstallation.device_id == current.id, ModuleInstallation.module_id == module_id,
            ).execution_options(populate_existing=True))
            if installation is None:
                raise HTTPException(404, "module installation was not found")
            before = module_control_snapshot(installation)
            key = _lifecycle_idempotency_key(db, device=current, command_type="module.disable", module_id=module_id,
                legacy_key=f"module.disable:{module_id}:{installation.installed_version}", client_key=idempotency_key, admin_id=admin_id)
            command, replay = _queue_lifecycle_command(db, device=current, command_type="module.disable",
                payload={"module_id": module_id}, idempotency_key=key, ttl_seconds=300)
            if not replay:
                installation.command_id, installation.status = command.command_id, command.status
                record_module_transition(db, mutation, current, installation, before, source="disable_requested", admin_id=admin_id)
            response = InstallationResponse.model_validate(installation)
            if on_queued is not None:
                on_queued(command)
            device_pk = current.id
    except AuthorityMetadataError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not replay:
        device_command_notifier.notify(device_pk)
    return response
