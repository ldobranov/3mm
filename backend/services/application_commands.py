"""Signed-installation command broker using the existing device queue."""
from datetime import UTC, datetime
import hashlib
import json
import uuid
from sqlalchemy import select, update
from backend.db.application_command import ApplicationCommandEpoch, ApplicationCommandRequest
from backend.db.device import Device, DeviceCommand
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.services.application_extensions import load_application_definition
from backend.services.application_configuration import _validate_value
from backend.services.device_commands import queue_command, commit_queued_command, _utc
from backend.services.device_capability_registry import has_registered_capability
from three_mm_protocol.application_commands import ApplicationCommandLookupV1, ApplicationCommandSubmitV1

COMMAND_TYPE = 'application.capability.invoke'


def current_authority(record):
    """SQL predicates evaluated with the write, not a stale ORM snapshot."""
    return (
        select(ApplicationCommandEpoch.installation_id).where(
            ApplicationCommandEpoch.installation_id == record.installation_id,
            ApplicationCommandEpoch.generation == record.generation).exists(),
        select(ApplicationExtensionInstallation.id).where(
            ApplicationExtensionInstallation.id == record.installation_id,
            ApplicationExtensionInstallation.enabled.is_(True),
            ApplicationExtensionInstallation.status == 'active',
            ApplicationExtensionInstallation.module_package_id == record.package_id).exists(),
    )


def invalidate_commands(db, installation_id):
    epoch = db.get(ApplicationCommandEpoch, installation_id)
    if epoch is not None:
        epoch.generation = uuid.uuid4().hex
    ids = select(ApplicationCommandRequest.command_id).where(ApplicationCommandRequest.installation_id == installation_id)
    db.execute(update(DeviceCommand).where(DeviceCommand.command_id.in_(ids), DeviceCommand.status.in_(['queued', 'delivered']))
        .values(status='failed', error='Application lifecycle invalidated this physical authorization', result={'execution_state': 'unknown'}))


def _definition(db, installation):
    if not installation or not installation.enabled or installation.status != 'active':
        raise ValueError('Application command authority is inactive')
    package = db.get(ModulePackage, installation.module_package_id)
    if package is None or package.module_id != installation.module_id or package.version != installation.active_version:
        raise ValueError('Application version is inconsistent')
    return load_application_definition(package)


def _binding(db, installation, binding_id, arguments, ttl):
    definition = _definition(db, installation)
    binding = next((b for b in definition.command_bindings if b.binding_id == binding_id), None)
    if binding is None or ttl > binding.max_ttl_seconds:
        raise ValueError('Command binding or TTL is not authorized')
    _validate_value(arguments, binding.arguments_schema, 'arguments')
    json.dumps(arguments, allow_nan=False)
    target = (installation.configuration or {}).get(binding.target_device_config_key)
    device = db.scalar(select(Device).where(Device.device_id == target, Device.revoked_at.is_(None)))
    if device is None or device.approved_at is None or not has_registered_capability(db, device, binding.capability_id):
        raise ValueError('Bound device or capability is unavailable')
    return binding, device


def submit_command(db, installation, payload):
    request = ApplicationCommandSubmitV1.model_validate(payload)
    binding, device = _binding(db, installation, request.binding_id, request.arguments, request.ttl_seconds)
    epoch = db.get(ApplicationCommandEpoch, installation.id)
    if epoch is None:
        epoch = ApplicationCommandEpoch(installation_id=installation.id, generation=uuid.uuid4().hex)
        db.add(epoch); db.flush()
    identity = hashlib.sha256(f'{installation.id}:{device.device_id}:{request.request_id}'.encode()).hexdigest()
    command_payload = {'capability_id': binding.capability_id, 'action': binding.action, 'arguments': request.arguments,
        'binding_id': binding.binding_id, 'direction': request.direction, 'ttl_seconds': request.ttl_seconds}
    if request.not_after is not None:
        command_payload['not_after'] = request.not_after.isoformat()
    command = queue_command(db, device=device, command_type=COMMAND_TYPE, payload=command_payload,
        idempotency_key='app:' + identity, ttl_seconds=request.ttl_seconds, not_after=request.not_after)
    record = db.get(ApplicationCommandRequest, command.command_id)
    if record is None:
        record = ApplicationCommandRequest(command_id=command.command_id, installation_id=installation.id,
            generation=epoch.generation, package_id=installation.module_package_id, claimed=False)
        db.add(record)
    if record.generation != epoch.generation or record.package_id != installation.module_package_id:
        raise ValueError('Request belongs to an invalidated generation; it cannot be replayed')
    commit_queued_command(db, device=device, command=command)
    return command_status(db, installation, command.command_id)


def command_status(db, installation, command_id):
    _definition(db, installation)
    record = db.get(ApplicationCommandRequest, command_id)
    if record is None or record.installation_id != installation.id:
        raise ValueError('Command is not owned by this application')
    return _command_snapshot(db, installation, record)


def _command_snapshot(db, installation, record):
    command_id = record.command_id
    command = db.scalar(select(DeviceCommand).where(DeviceCommand.command_id == command_id))
    epoch = db.get(ApplicationCommandEpoch, installation.id)
    valid = installation.enabled and installation.status == 'active' and epoch is not None and epoch.generation == record.generation and installation.module_package_id == record.package_id
    state = command.status
    if not valid:
        state = 'invalidated'
    elif state in {'queued', 'delivered', 'expired'} and _utc(command.expires_at) <= datetime.now(UTC):
        state = 'unknown' if record.claimed else 'expired'
    return {'command_id': command_id, 'status': state, 'claimed': record.claimed,
        'generation': record.generation, 'expires_at': _utc(command.expires_at).isoformat(),
        'result': command.result, 'error': command.error, 'passage_event_id': record.passage_event_id}


def command_lookup(db, installation, payload):
    """Read existing immutable request identities; never resolve current bindings."""
    request = ApplicationCommandLookupV1.model_validate(payload)
    if installation is None or installation.id is None:
        raise ValueError('Application installation is unavailable')
    with db.no_autoflush:
        rows = db.execute(select(ApplicationCommandRequest, DeviceCommand.idempotency_key, Device.device_id)
            .join(DeviceCommand, DeviceCommand.command_id == ApplicationCommandRequest.command_id)
            .join(Device, Device.id == DeviceCommand.device_id)
            .where(ApplicationCommandRequest.installation_id == installation.id,
                DeviceCommand.command_type == COMMAND_TYPE,
                DeviceCommand.payload['binding_id'].as_string() == request.binding_id)
            .execution_options(yield_per=100))
        matches = []
        for record, key, device_id in rows:
            identity = hashlib.sha256(f'{installation.id}:{device_id}:{request.request_id}'.encode()).hexdigest()
            if key == 'app:' + identity:
                matches.append(record)
                if len(matches) > 1:
                    raise ValueError('Command lookup is ambiguous across original target devices; manual review is required')
        if not matches:
            return {'status': 'not_found'}
        return {'status': 'found', 'command': _command_snapshot(db, installation, matches[0])}


def authorize_execution(db, device, command_id):
    """One live permit, never redelivered. A missing response is not retryable."""
    record = db.get(ApplicationCommandRequest, command_id)
    command = db.scalar(select(DeviceCommand).where(DeviceCommand.command_id == command_id, DeviceCommand.device_id == device.id))
    if record is None or command is None or command.command_type != COMMAND_TYPE or command.status != 'delivered':
        raise ValueError('Physical command is not available for this device')
    installation = db.get(ApplicationExtensionInstallation, record.installation_id)
    epoch = db.get(ApplicationCommandEpoch, record.installation_id)
    binding, target = _binding(db, installation, command.payload['binding_id'], command.payload['arguments'], command.payload['ttl_seconds'])
    if target.id != device.id or epoch is None or epoch.generation != record.generation or installation.module_package_id != record.package_id or _utc(command.expires_at) <= datetime.now(UTC):
        raise ValueError('Physical command authority expired or changed')
    changed = db.execute(update(ApplicationCommandRequest).where(
        ApplicationCommandRequest.command_id == command_id,
        ApplicationCommandRequest.claimed.is_(False),
        *current_authority(record),
        select(DeviceCommand.id).where(DeviceCommand.command_id == command_id,
            DeviceCommand.status == 'delivered',
            DeviceCommand.expires_at > datetime.now(UTC)).exists(),
        select(Device.id).where(Device.id == device.id, Device.revoked_at.is_(None),
            Device.approved_at.is_not(None)).exists(),
    ).values(claimed=True).execution_options(synchronize_session=False)).rowcount
    if changed != 1:
        db.rollback()
        raise ValueError('Physical command permit has already been consumed')
    db.commit()
    return {'command_id': command_id, 'authorized': True, 'generation': record.generation}
