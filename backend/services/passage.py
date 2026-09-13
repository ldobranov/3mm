"""Validate correlation and authenticated sensor ownership before event delivery."""
from datetime import UTC, datetime
from sqlalchemy import select, update
from backend.db.device import DeviceCommand
from backend.db.module import ApplicationExtensionInstallation
from backend.db.application_command import ApplicationCommandEpoch, ApplicationCommandRequest
from backend.services.application_commands import _binding, current_authority
from backend.services.device_commands import _utc
from backend.services.device_capability_registry import has_registered_capability
from three_mm_protocol.passage import PassageEventV1


def validate_passage(db, device, event: PassageEventV1):
    payload = event.payload
    record = db.get(ApplicationCommandRequest, payload.command_id)
    command = db.scalar(select(DeviceCommand).where(DeviceCommand.command_id == payload.command_id))
    if record is None or command is None or not record.claimed:
        raise ValueError('Passage has no claimed command correlation')
    installation = db.get(ApplicationExtensionInstallation, record.installation_id)
    epoch = db.get(ApplicationCommandEpoch, record.installation_id)
    binding, target = _binding(db, installation, payload.binding_id, command.payload['arguments'], command.payload['ttl_seconds'])
    if (epoch is None or epoch.generation != record.generation or payload.generation != record.generation
        or installation.module_package_id != record.package_id
        or command.payload['binding_id'] != payload.binding_id or command.payload['direction'] != payload.direction
        or target.id != command.device_id
        or not binding.sensor_device_config_key
        or installation.configuration.get(binding.sensor_device_config_key) != device.device_id
        or binding.sensor_id != payload.sensor_id or event.device_id != device.device_id
        or device.revoked_at is not None or payload.device_health != 'ok'
        or not has_registered_capability(db, device, 'access.passage.v1')):
        raise ValueError('Passage authority, binding or sensor does not match')
    now = datetime.now(UTC)
    if not _utc(command.created_at) <= event.occurred_at <= now or now >= _utc(command.expires_at):
        raise ValueError('Passage is late or has an invalid timestamp; manual review is required')
    changed = db.execute(update(ApplicationCommandRequest).where(
        ApplicationCommandRequest.command_id == payload.command_id,
        ApplicationCommandRequest.passage_event_id.is_(None),
        *current_authority(record)).values(passage_event_id=event.event_id)
        .execution_options(synchronize_session=False)).rowcount
    if changed != 1:
        raise ValueError('This command already has a passage confirmation')


def passage_delivery_allowed(db, installation, event):
    """Never distribute correlated physical evidence to another installation/epoch."""
    if event.event_type != 'access.passage.v1':
        return True
    record = db.get(ApplicationCommandRequest, event.payload.get('command_id'))
    if record is None or record.installation_id != installation.id or record.passage_event_id != event.event_id:
        return False
    return bool(db.scalar(select(ApplicationCommandRequest.command_id).where(
        ApplicationCommandRequest.command_id == record.command_id,
        *current_authority(record))))
