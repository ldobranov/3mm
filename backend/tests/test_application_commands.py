from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import sqlite3
import pytest
from sqlalchemy import select
from backend.tests.test_application_access import environment
from backend.tests.test_module_packages import application_package, application_manifest, application_definition
from backend.db.device import Device, DeviceCommand
from backend.db.module import ModulePackage, ModuleInstallation
from backend.db.application_command import ApplicationCommandEpoch, ApplicationCommandRequest
from backend.services.application_commands import submit_command, command_status, authorize_execution, invalidate_commands
from backend.services.device_commands import deliver_next_command, command_envelope, DeviceCommandError
from backend.services.passage import validate_passage, passage_delivery_allowed
from agent.physical_command_journal import PhysicalCommandJournal
from three_mm_protocol.passage import PassageEventV1


@pytest.fixture
def setup(monkeypatch, tmp_path):
    definition = application_definition(command_bindings=[{
        'binding_id': 'gate', 'target_device_config_key': 'OUTPUT_DEVICE_ID',
        'capability_id': 'gpio.digital.output', 'action': 'pulse_output',
        'sensor_device_config_key': 'SENSOR_DEVICE_ID', 'sensor_id': 'sensor.1',
        'arguments_schema': {'type': 'object', 'properties': {
            'channel': {'type': 'string', 'maxLength': 32, 'enum': ['gpio.output.1']},
            'duration_ms': {'type': 'integer', 'minimum': 50, 'maximum': 500}},
            'required': ['channel', 'duration_ms'], 'additionalProperties': False}}])
    manifest = application_manifest()
    manifest['permissions'].append('capabilities.invoke')
    manifest['capabilities']['consumes'].append('gpio.digital.output')
    manifest['configuration_schema']['properties'].update(OUTPUT_DEVICE_ID={'type': 'string'}, SENSOR_DEVICE_ID={'type': 'string'})
    values = environment(monkeypatch, tmp_path, application_package(definition=definition, manifest_value=manifest))
    client, db, engine, _, _, installation, package, *_ = values
    devices = [Device(device_id='dev_' + c*32, display_name=c, role='node', protocol_version='1.0', approved_at=datetime.now(UTC)) for c in ('1', '2')]
    db.add_all(devices); db.flush()
    hardware = ModulePackage(module_id='org.example.hardware', version='1.0.0', manifest={}, sha256='e'*64, size_bytes=1, file_path='unused', registrations=[{'kind': 'capability', 'registration_id': c} for c in ('gpio.digital.output', 'access.passage.v1')])
    db.add(hardware); db.flush()
    for device in devices:
        db.add(ModuleInstallation(device_id=device.id, module_package_id=hardware.id, module_id=hardware.module_id, desired_version='1.0.0', status='succeeded', enabled=True))
    installation.configuration = {'OUTPUT_DEVICE_ID': devices[0].device_id, 'SENSOR_DEVICE_ID': devices[1].device_id}
    db.commit()
    yield SimpleNamespace(db=db, app=installation, devices=devices, client=client, package=package)
    client.close(); db.close(); engine.dispose()


def payload(request_id='request-1'):
    return {'binding_id': 'gate', 'request_id': request_id, 'arguments': {'channel': 'gpio.output.1', 'duration_ms': 100}, 'ttl_seconds': 10}


def test_signed_platform_command_transport(setup, monkeypatch, tmp_path):
    import json
    import hmac
    import hashlib
    import time
    import backend.database
    from backend.services.application_platform import ApplicationPlatformServer
    s = setup
    server = ApplicationPlatformServer(tmp_path / 'unused.sock', tmp_path)
    secret = b's' * 32
    (tmp_path / f'{s.app.instance_id}.key').write_bytes(secret)
    monkeypatch.setattr(backend.database, 'SessionLocal', lambda: s.db)
    request = {'version': 1, 'instance_id': s.app.instance_id, 'timestamp': int(time.time()),
        'request_id': 'transport-1', 'action': 'command.submit', 'command': payload()}

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def recv(self, size): return json.dumps(request).encode() + b'\n'
        def sendall(self, response): self.response = json.loads(response)

    request['signature'] = 'invalid'
    connection = Connection(); server._handle(connection)
    assert connection.response['ok'] is False
    assert not s.db.scalars(select(DeviceCommand)).all()
    request['signature'] = hmac.new(secret, server._canonical(request), hashlib.sha256).hexdigest()
    server._handle(connection)
    assert connection.response['ok'] is True
    assert connection.response['result']['status'] == 'queued'


def test_broker_to_durable_agent_and_correlated_sensor(setup, tmp_path):
    s = setup
    submitted = submit_command(s.db, s.app, payload())
    assert submit_command(s.db, s.app, payload())['command_id'] == submitted['command_id']
    other = payload(); other['arguments']['duration_ms'] = 200
    with pytest.raises(DeviceCommandError, match='different content'):
        submit_command(s.db, s.app, other)
    s.db.rollback()
    command = deliver_next_command(s.db, device=s.devices[0])
    with pytest.raises(ValueError):
        authorize_execution(s.db, s.devices[1], command.command_id)
    envelope = command_envelope(command, s.devices[0].device_id)
    effects = []
    def invoke():
        effects.append('pulse'); return {}
    journal = PhysicalCommandJournal(tmp_path / 'agent')
    result = journal.execute(envelope, invoke, authorize=lambda: authorize_execution(s.db, s.devices[0], command.command_id))
    assert result.status == 'succeeded'
    assert journal.execute(envelope, invoke).status == 'succeeded'
    assert effects == ['pulse']
    with pytest.raises(ValueError, match='consumed'):
        authorize_execution(s.db, s.devices[0], command.command_id)
    event = PassageEventV1(event_id='evt_' + 'a'*32, device_id=s.devices[1].device_id,
        event_type='access.passage.v1', occurred_at=datetime.now(UTC), payload={
        'binding_id': 'gate', 'direction': 'forward', 'command_id': command.command_id,
        'generation': submitted['generation'], 'sensor_id': 'sensor.1', 'device_health': 'ok'})
    with pytest.raises(ValueError):
        validate_passage(s.db, s.devices[0], event)
    validate_passage(s.db, s.devices[1], event); s.db.commit()
    stored_event = SimpleNamespace(event_type=event.event_type, event_id=event.event_id, payload=event.payload.model_dump())
    assert passage_delivery_allowed(s.db, s.app, stored_event)
    assert not passage_delivery_allowed(s.db, SimpleNamespace(id=s.app.id + 1), stored_event)
    with pytest.raises(ValueError, match='already'):
        validate_passage(s.db, s.devices[1], event.model_copy(update={'event_id': 'evt_' + 'b'*32}))
    s.db.rollback()
    assert command_status(s.db, s.app, command.command_id)['passage_event_id'] == event.event_id
    invalidate_commands(s.db, s.app.id); s.db.commit()
    assert not passage_delivery_allowed(s.db, s.app, stored_event)


@pytest.mark.parametrize('change', ['direction', 'generation', 'sensor', 'late', 'degraded', 'unclaimed'])
def test_invalid_passage_cannot_confirm(setup, change):
    s = setup
    submitted = submit_command(s.db, s.app, payload())
    command = deliver_next_command(s.db, device=s.devices[0])
    if change != 'unclaimed': authorize_execution(s.db, s.devices[0], command.command_id)
    data = {'binding_id': 'gate', 'direction': 'forward', 'command_id': command.command_id,
        'generation': submitted['generation'], 'sensor_id': 'sensor.1', 'device_health': 'ok'}
    if change == 'direction': data['direction'] = 'reverse'
    if change == 'generation': data['generation'] = 'f'*32
    if change == 'sensor': data['sensor_id'] = 'sensor.2'
    if change == 'degraded': data['device_health'] = 'degraded'
    if change == 'late': command.expires_at = datetime.now(UTC); s.db.commit()
    event = PassageEventV1(event_id='evt_' + 'a'*32, device_id=s.devices[1].device_id,
        event_type='access.passage.v1', occurred_at=datetime.now(UTC), payload=data)
    with pytest.raises(ValueError): validate_passage(s.db, s.devices[1], event)
    assert s.db.get(ApplicationCommandRequest, command.command_id).passage_event_id is None


@pytest.mark.parametrize('change', ['unknown_binding', 'channel', 'range', 'extra', 'ttl', 'revoked', 'disabled'])
def test_partial_or_invalid_authority_never_queues(setup, change):
    s = setup; request = payload()
    if change == 'unknown_binding': request['binding_id'] = 'other'
    if change == 'channel': request['arguments']['channel'] = 'gpio.output.2'
    if change == 'range': request['arguments']['duration_ms'] = 501
    if change == 'extra': request['arguments']['extra'] = True
    if change == 'ttl': request['ttl_seconds'] = 11
    if change == 'revoked': s.devices[0].revoked_at = datetime.now(UTC); s.db.commit()
    if change == 'disabled': s.app.enabled = False; s.db.commit()
    with pytest.raises(ValueError): submit_command(s.db, s.app, request)
    assert not s.db.scalars(select(DeviceCommand)).all()


def test_expiry_disable_and_restore_invalidate_pending_authority(setup, tmp_path, monkeypatch):
    s = setup
    submitted = submit_command(s.db, s.app, payload())
    command = deliver_next_command(s.db, device=s.devices[0])
    command.expires_at = datetime.now(UTC)-timedelta(seconds=1); s.db.commit()
    with pytest.raises(ValueError): authorize_execution(s.db, s.devices[0], command.command_id)
    submitted = submit_command(s.db, s.app, payload('new-request'))
    command = deliver_next_command(s.db, device=s.devices[0])
    invalidate_commands(s.db, s.app.id); s.db.commit()
    with pytest.raises(ValueError): authorize_execution(s.db, s.devices[0], command.command_id)
    with pytest.raises(ValueError, match='invalidated'):
        submit_command(s.db, s.app, payload('new-request'))
    s.db.rollback()
    # Restore the actual schema into another DB and exercise the deployment hook.
    submitted = submit_command(s.db, s.app, payload('restore-request'))
    database = tmp_path / 'restore.db'
    s.db.commit()
    with sqlite3.connect(database) as dest:
        s.db.connection().connection.driver_connection.backup(dest)
        dest.execute("UPDATE application_extension_installations SET enabled=0")
    from deployment import restore_application_extensions as restore
    monkeypatch.setattr(restore, 'WANTS_ROOT', tmp_path / 'missing')
    restore.restore_application_extensions(database, service_ids=(1, 1))
    with sqlite3.connect(database) as restored:
        assert restored.execute('SELECT generation FROM application_command_epochs').fetchone()[0] != submitted['generation']
        assert restored.execute('SELECT status FROM device_commands WHERE command_id=?', (submitted['command_id'],)).fetchone()[0] == 'failed'
