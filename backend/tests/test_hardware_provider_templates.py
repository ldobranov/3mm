"""Admin preparation uses the existing immutable catalog, never device effects."""
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from backend.db.device import DeviceCommand
from backend.db.module import ModuleInstallation, ModulePackage
from backend.routes import modules
from backend.tests.test_hardware_profile_installation import native  # noqa: F401
from backend.tests.test_module_lifecycle_idempotency import lifecycle, DEVICE_ID  # noqa: F401
from agent.tests.test_character_display import builder  # noqa: F401
from backend.services.hardware_provider_templates import prepare_provider, provider_templates, sources
from backend.services.module_packages import validate_module_package
from backend.utils.auth_dep import require_admin
from three_mm_protocol.character_display import CharacterDisplayProfileV1

PATH = f'/api/v1/modules/devices/{DEVICE_ID}/hardware-profiles'
TEMPLATE = 'character-display.pcf8574-2row'


def template_id(name=TEMPLATE):
    return next(source.identity for source in sources().values() if source.descriptor.template_id == name)


@pytest.fixture
def preparation(lifecycle, tmp_path, monkeypatch):
    monkeypatch.setattr(modules, 'get_settings', lambda: SimpleNamespace(
        backend=SimpleNamespace(uploads_dir=tmp_path / 'uploads')))
    return lifecycle


def test_templates_and_preparation_are_inert_deterministic_and_visible(preparation):
    ctx = preparation
    before = ctx.client.get(PATH)
    assert before.status_code == 200
    assert before.headers['cache-control'] == 'no-store'
    assert before.json()['templates'] == provider_templates()
    assert len(list(ctx.db.scalars(select(ModulePackage)))) == 1
    body = {'template_id': template_id(), 'configuration': {'columns': 16}}
    response = ctx.client.post(PATH + '/prepare', json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['activation'] == 'not_requested' and result['device_id'] == DEVICE_ID
    assert response.headers['cache-control'] == 'no-store'
    assert ctx.client.post(PATH + '/prepare', json=body).json() == result
    catalog = ctx.client.get(PATH).json()
    item = next(item for item in catalog['items'] if item['sha256'] == result['package_sha256'])
    assert item['profile']['profile_sha256'] == result['profile_sha256']
    assert item['profile']['configuration']['columns'] == 16
    assert item['installation'] is None and not item['installed_exact']
    assert list(ctx.db.scalars(select(DeviceCommand))) == []
    assert list(ctx.db.scalars(select(ModuleInstallation))) == []
    records = list(ctx.db.scalars(select(ModulePackage)))
    assert len(records) == 2
    record = next(p for p in records if p.sha256 == result['package_sha256'])
    assert hashlib.sha256(Path(record.file_path).read_bytes()).hexdigest() == record.sha256
    assert record.manifest['permissions'] == ['hardware.display']
    assert validate_module_package(Path(record.file_path).read_bytes()).manifest.registrations[0].contract == CharacterDisplayProfileV1(
        driver='pcf8574', columns=16, rows=2).contract()
    # Existing admin inventory exposes prepared packages, including deletion.
    assert any(i['sha256'] == record.sha256 for i in ctx.client.get('/api/v1/modules/agent-catalog').json()['items'])


@pytest.mark.parametrize('configuration', [
    {'driver': 'shell'}, {'entrypoint': 'python:run'}, {'module_id': 'override'},
    {'path': '/dev/i2c-1'}, {'permissions': ['root.full']}, {'write_now': True},
    {'address': 0x28}, {'columns': 0}, {'columns': 41}, {'rows': 3},
    {'columns': 21, 'rows': 4}, {'bus': '../i2c-1'}, {'columns': '16'},
    {'backlight_active_high': 'true'}, {'display_id': '../display'},
])
def test_invalid_or_executable_settings_never_write_catalog_or_commands(preparation, configuration):
    ctx = preparation
    response = ctx.client.post(PATH + '/prepare', json={'template_id': template_id(), 'configuration': configuration})
    assert response.status_code == 422, response.text
    assert len(list(ctx.db.scalars(select(ModulePackage)))) == 1
    assert list(ctx.db.scalars(select(DeviceCommand))) == []
    assert not (Path(modules.get_settings().backend.uploads_dir) / 'modules').exists()


@pytest.mark.parametrize('template_id', ['not-installed.driver', '../../payload'])
def test_unknown_templates_are_not_loaded_or_executed(preparation, template_id):
    response = preparation.client.post(PATH + '/prepare', json={'template_id': template_id, 'configuration': {}})
    assert response.status_code == 422


@pytest.mark.parametrize('change', ['revoked', 'unknown'])
def test_invalid_device_cannot_prepare_a_profile(preparation, change):
    ctx = preparation
    path = PATH
    if change == 'revoked': ctx.device.revoked_at = datetime.now(UTC)
    else: path = PATH.replace(DEVICE_ID, 'dev_' + 'f' * 32)
    ctx.db.commit()
    response = ctx.client.post(path + '/prepare', json={'template_id': template_id(), 'configuration': {}})
    assert response.status_code == (404 if change == 'unknown' else 409)
    assert len(list(ctx.db.scalars(select(ModulePackage)))) == 1


def test_preparation_requires_admin_and_an_exact_request_shape(preparation):
    ctx = preparation
    body = {'template_id': template_id(), 'configuration': {}}
    assert ctx.client.post(PATH + '/prepare', json={**body, 'install': True}).status_code == 422
    def denied(): raise HTTPException(403, 'administrator required')
    ctx.client.app.dependency_overrides[require_admin] = denied
    assert ctx.client.get(PATH).status_code == 403
    assert ctx.client.post(PATH + '/prepare', json=body).status_code == 403
    assert len(list(ctx.db.scalars(select(ModulePackage)))) == 1


def test_existing_immutable_version_conflict_is_not_overwritten(preparation):
    ctx = preparation
    body = {'template_id': template_id(), 'configuration': {}}
    result = ctx.client.post(PATH + '/prepare', json=body).json()
    package = ctx.db.scalar(select(ModulePackage).where(ModulePackage.sha256 == result['package_sha256']))
    package.sha256 = 'f' * 64
    ctx.db.commit()
    response = ctx.client.post(PATH + '/prepare', json=body)
    assert response.status_code == 409
    ctx.db.refresh(package)
    assert package.sha256 == 'f' * 64
    assert list(ctx.db.scalars(select(DeviceCommand))) == []


def test_prepared_package_still_requires_exact_device_profile_consent(native, tmp_path, monkeypatch):
    ctx = native
    monkeypatch.setattr(modules, 'get_settings', lambda: SimpleNamespace(backend=SimpleNamespace(uploads_dir=tmp_path)))
    result = ctx.client.post(PATH + '/prepare', json={'template_id': template_id(),
        'configuration': {'columns': 16}}).json()
    install = f'/api/v1/modules/packages/{result["package_sha256"]}/devices/{DEVICE_ID}/install'
    assert ctx.client.post(install, json={}).status_code == 409
    assert list(ctx.db.scalars(select(DeviceCommand))) == []
    approval = {'device_id': DEVICE_ID, 'package_sha256': result['package_sha256'],
                'profile_sha256': result['profile_sha256']}
    response = ctx.client.post(install, json={'hardware_profile_approval': approval},
                               headers={'Idempotency-Key': 'b' * 32})
    assert response.status_code == 200, response.text
    commands = list(ctx.db.scalars(select(DeviceCommand)))
    assert len(commands) == 1 and commands[0].command_type == 'module.install'
    assert commands[0].payload['hardware_profile_approval']['profile_sha256'] == result['profile_sha256']


@pytest.mark.parametrize('columns,rows', [(16, 2), (20, 2), (24, 2), (40, 2), (20, 4)])
def test_driver_template_accepts_geometry_parameters_not_an_application_size_list(columns, rows):
    source = TEMPLATE if rows == 2 else 'character-display.pcf8574-4row'
    blob = prepare_provider(template_id(source), {'columns': columns})
    package = validate_module_package(blob)
    assert package.manifest.configuration_defaults['columns'] == columns
    assert package.manifest.configuration_defaults['rows'] == rows
    assert package.manifest.registrations[0].contract == CharacterDisplayProfileV1(
        driver='pcf8574', columns=columns, rows=rows).contract()


def test_four_row_template_keeps_its_distinct_controller_limit():
    with pytest.raises(ValueError):
        prepare_provider(template_id('character-display.pcf8574-4row'), {'columns':21})
