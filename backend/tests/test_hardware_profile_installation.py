"""Generic package-bound consent; existing admin/control/lifecycle authority."""
import hashlib
from datetime import UTC, datetime
from pathlib import Path
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from backend.db.device import DeviceCommand, DeviceCredential, DeviceRuntimeFeatures
from backend.db.module import ModuleInstallation
from backend.tests.test_module_lifecycle_idempotency import lifecycle, DEVICE_ID  # noqa: F401
from backend.utils.auth_dep import require_admin
from three_mm_protocol.node_features import MANDATORY_NODE_FEATURES
from three_mm_protocol.hardware_profiles import HARDWARE_PROFILE_FEATURE
from agent.tests.test_character_display import builder  # noqa: F401
from three_mm_protocol.character_display import CharacterDisplayProfileV1


@pytest.fixture
def native(lifecycle, builder):
    ctx = lifecycle
    profile = CharacterDisplayProfileV1(driver='pcf8574')
    blob = builder.build_package(profile)
    package = ctx.package
    package.manifest = builder.manifest(profile)
    package.module_id = package.manifest['module_id']
    package.sha256 = hashlib.sha256(blob).hexdigest()
    package.registrations = package.manifest['registrations']
    package.size_bytes = len(blob)
    Path(package.file_path).write_bytes(blob)
    ctx.db.add(DeviceRuntimeFeatures(device_id=ctx.device.id, revision=1, received_at=datetime.now(UTC),
        declaration={'schema_version': 1, 'protocol_version': '1.0', 'device_id': DEVICE_ID,
                     'runtime_name': 'test-agent', 'runtime_version': '1.0',
                     'features': sorted(MANDATORY_NODE_FEATURES | {'module_lifecycle', HARDWARE_PROFILE_FEATURE}),
                     'command_types': ['capability.invoke', 'module.install', 'module.disable']}))
    ctx.db.commit()
    ctx.install = f'/api/v1/modules/packages/{package.sha256}/devices/{DEVICE_ID}/install'
    ctx.disable = f'/api/v1/modules/{package.module_id}/devices/{DEVICE_ID}/disable'
    ctx.approval = {'device_id': DEVICE_ID, 'package_sha256': package.sha256, 'profile_sha256': profile.digest()}
    return ctx


@pytest.mark.parametrize('field', ['missing', 'device_id', 'package_sha256', 'profile_sha256', 'extra'])
def test_unapproved_or_changed_binding_never_queues_a_module(native, field):
    ctx = native
    approval = dict(ctx.approval)
    if field == 'extra': approval['write_now'] = True
    elif field != 'missing': approval[field] = ('dev_' if field == 'device_id' else '') + 'f'*(32 if field == 'device_id' else 64)
    response = ctx.client.post(ctx.install, json={} if field == 'missing' else {'hardware_profile_approval': approval})
    assert response.status_code == (422 if field == 'extra' else 409), response.text
    assert list(ctx.db.scalars(select(DeviceCommand))) == []
    assert ctx.db.scalar(select(ModuleInstallation)) is None


def test_readonly_catalog_exact_consent_and_duplicate_share_one_command(native):
    ctx = native
    path = f'/api/v1/modules/devices/{DEVICE_ID}/hardware-profiles'
    before = ctx.client.get(path).json()
    assert before['approval_supported'] and before['items'][0]['installation'] is None
    assert before['items'][0]['profile']['profile_sha256'] == ctx.approval['profile_sha256']
    assert list(ctx.db.scalars(select(DeviceCommand))) == []
    key = 'a'*32
    response = ctx.client.post(ctx.install, json={'hardware_profile_approval': ctx.approval}, headers={'Idempotency-Key': key})
    assert response.status_code == 200, response.text
    replay = ctx.client.post(ctx.install, json={'hardware_profile_approval': ctx.approval}, headers={'Idempotency-Key': key})
    assert replay.status_code == 200 and replay.json()['command_id'] == response.json()['command_id']
    commands = list(ctx.db.scalars(select(DeviceCommand)))
    assert len(commands) == 1 and commands[0].command_type == 'module.install'
    assert commands[0].payload['hardware_profile_approval']['package_sha256'] == ctx.package.sha256
    after = ctx.client.get(path).json()['items'][0]
    assert after['request_id'] == key and after['installed_exact']
    # Installation is queued, not proof that a display frame executed.
    assert after['installation']['status'] == 'queued'


@pytest.mark.parametrize('change', ['feature', 'credential', 'device'])
def test_withdrawn_agent_support_or_control_cannot_accept_installation(native, change):
    ctx = native
    if change == 'feature':
        row = ctx.db.scalar(select(DeviceRuntimeFeatures)); row.declaration = {**row.declaration, 'features': []}
    elif change == 'credential': ctx.db.scalar(select(DeviceCredential)).revoked_at = datetime.now(UTC)
    else: ctx.device.revoked_at = datetime.now(UTC)
    ctx.db.commit()
    response = ctx.client.post(ctx.install, json={'hardware_profile_approval': ctx.approval})
    assert response.status_code == 409, response.text
    assert list(ctx.db.scalars(select(DeviceCommand))) == []


def test_non_admin_cannot_inspect_or_grant_hardware_profile(native):
    ctx = native
    def denied(): raise HTTPException(403, 'administrator required')
    app = ctx.client.app
    original = app.dependency_overrides[require_admin]
    app.dependency_overrides[require_admin] = denied
    try:
        assert ctx.client.get(f'/api/v1/modules/devices/{DEVICE_ID}/hardware-profiles').status_code == 403
        assert ctx.client.post(ctx.install, json={'hardware_profile_approval': ctx.approval}).status_code == 403
        assert list(ctx.db.scalars(select(DeviceCommand))) == []
    finally:
        app.dependency_overrides[require_admin] = original


def test_disable_does_not_implicitly_approve_reinstallation(native):
    ctx = native
    response = ctx.client.post(ctx.install, json={'hardware_profile_approval': ctx.approval},
                               headers={'Idempotency-Key': 'a'*32})
    assert response.status_code == 200, response.text
    ctx.complete(response.json()['command_id'])
    disabled = ctx.client.post(ctx.disable, headers={'Idempotency-Key': 'b'*32})
    assert disabled.status_code == 200, disabled.text
    ctx.complete(disabled.json()['command_id'])
    assert ctx.db.scalar(select(ModuleInstallation)).enabled is False
    assert ctx.client.post(ctx.install, json={}, headers={'Idempotency-Key': 'c'*32}).status_code == 409
    assert len(list(ctx.db.scalars(select(DeviceCommand)))) == 2
