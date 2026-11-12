"""Packaged starter through actual Core permission, consent and SDK boundaries.

Disposable database/native instance/Runtime; external systemd launch/response
transport are doubled. No physical effects or device deployment.
"""
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from backend.config import ApplicationRuntimeSettings
from backend.db.device import Device, DeviceCapabilityHealth, DeviceCapabilityProvider, DeviceCommand
from backend.db.module import ApplicationExtensionInstallation as Installation, ApplicationPermissionGrant, ModulePackage
from backend.applications.management import api as routes
from backend.artifacts import compiled_ui
from backend.applications.runtime import gateway
from backend.devices.capabilities.registry import capability_catalog
from backend.artifacts.packages import validate_module_package
from backend.version import core_version
from backend.tests.test_application_command_discovery import installed, source_subject, source_installed, vertical, identity
from backend.tests.test_application_consent import allow, preview
from backend.tests.test_command_probe_application import builder
from backend.tests.response_helpers import install_response_transport
from packages.application_sdk import OperationContext, ApplicationPlatformError
from components.system_runtime.application_host import _load_service
from components.system_runtime.application_transport import ApplicationTransportError
from tools.application_project import build_package

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Actual POSIX native trust and signed SDK Runtime')
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def starter(vertical, monkeypatch, tmp_path):
    s = vertical
    s.manager.core_version = core_version()
    blob = build_package(ROOT/'modules/application-starter')
    assert blob == build_package(ROOT/'modules/application-starter')
    s.validated = validate_module_package(blob)
    s.archive = s.root/'modules'/(s.validated.sha256+'.zip')
    s.archive.write_bytes(blob)
    definition = s.validated.application_extension
    contract = builder('starter_gpio_fixture', ROOT/'modules/digital-output/build_package.py').versioned_manifest()['registrations'][0]['contract']
    s.configuration = {'RESOURCE_DEVICE_ID': 'dev_'+'3'*32}
    with s.engine.begin() as db:
        db.execute(update(ModulePackage).where(ModulePackage.id == 1).values(module_id=s.validated.manifest.module_id,
            version=s.validated.manifest.version, manifest=s.validated.manifest.model_dump(mode='json'),
            sha256=s.validated.sha256, size_bytes=len(blob), file_path=str(s.archive)))
        db.execute(update(Installation).where(Installation.id == 1).values(module_id=s.validated.manifest.module_id,
            active_version=s.validated.manifest.version, configuration=s.configuration))
        db.execute(update(DeviceCapabilityProvider).values(provider_type='native', provider_id='org.example.starter-resource',
            capabilities=[{'capability_id': 'gpio.digital.control', 'metadata': {}, 'contract': contract}]))
        db.execute(delete(DeviceCapabilityHealth))
    with Session(s.engine) as db, db.begin():
        offer = capability_catalog(db, db.get(Device, 1))[0]
        db.add(DeviceCapabilityHealth(device_id=1, provider_type=offer.provider_type, provider_id=offer.provider_id,
            observed_at=datetime.now(UTC), expires_at=datetime.now(UTC)+timedelta(minutes=5), report={
                'declaration_digest': offer.declaration_digest, 'capabilities': [{'capability_id': offer.capability_id, 'healthy': True}]}))
    monkeypatch.setenv('COMPILED_UI_ARTIFACTS_DIR', str(s.root/'compiled'))
    s.build = compiled_ui.compile_ui_package(blob, s.validated)
    allow(s, preview(s), scopes=['command:resource'], user_permissions=['note_read', 'note_write'])
    with Session(s.engine) as db, db.begin():
        db.add_all([ApplicationPermissionGrant(application_installation_id=1, user_id=2, permission_id=p)
                    for p in ['note_read', 'note_write']])
    instance = tmp_path/'starter-instance'
    release = instance/'releases'/s.validated.sha256
    release.mkdir(parents=True)
    wheel = Path(definition.service.artifact).name
    with zipfile.ZipFile(s.archive) as archive:
        (release/wheel).write_bytes(archive.read(definition.service.artifact))
    metadata = {'module_id': s.validated.manifest.module_id, 'version': s.validated.manifest.version,
        'sha256': s.validated.sha256, 'wheel': wheel, 'entrypoint': definition.service.entrypoint,
        'storage': definition.storage.model_dump(mode='json'), 'configuration': s.configuration,
        'platform_socket': str(s.runtime_socket), 'instance_id': 'a'*24}
    s.service = _load_service(metadata, instance, b's'*32)
    s.ui = {'host_version': 1, 'entrypoint_id': 'note', 'artifact_sha256': s.validated.sha256,
            'built_ui_sha256': s.build.built_ui_sha256}
    s.base = '/api/v1/application-extensions/'+s.validated.manifest.module_id

    class ServiceClient:
        def __init__(self, *_): pass
        def invoke(self, operation, payload, context):
            try:
                return s.service.handle(operation, payload, OperationContext.from_platform(context))
            except (ValueError, ApplicationPlatformError) as error:
                raise ApplicationTransportError('Starter operation refused') from error

    monkeypatch.setattr(gateway, 'ApplicationServiceClient', ServiceClient)
    monkeypatch.setattr(routes, 'get_settings', lambda: SimpleNamespace(applications=ApplicationRuntimeSettings(
        enabled=True, key_root=s.runtime_socket.parent)))
    install_response_transport(monkeypatch)
    return s


def invoke(s, name, payload=None, key=None):
    body = {'payload': payload or {}, 'ui_context': s.ui}
    if key:
        body['idempotency_key'] = key
    return s.http.post(s.base+'/operator/operations/'+name, json=body,
        headers={'Authorization': 'Bearer '+s.user_token})


def test_real_starter_permissions_revocation_unavailable_and_owned_data(starter):
    s = starter
    assert invoke(s, 'observe_resource').json() == {'state': 'ready'}
    assert invoke(s, 'read_note').json() == {'text': '', 'revision': 0}
    saved = invoke(s, 'save_note', {'text': 'Own data', 'revision': 0}, identity())
    assert saved.status_code == 200, saved.text
    assert saved.json() == {'text': 'Own data', 'revision': 1}
    with s.engine.begin() as db:
        db.execute(delete(ApplicationPermissionGrant).where(ApplicationPermissionGrant.user_id == 2,
            ApplicationPermissionGrant.permission_id == 'note_write'))
    assert invoke(s, 'save_note', {'text': 'denied', 'revision': 1}, identity()).status_code == 403
    assert invoke(s, 'read_note').json() == saved.json()
    # A current sealed service grant is not the same as current provider health.
    with s.engine.begin() as db:
        db.execute(update(DeviceCapabilityHealth).values(expires_at=datetime.now(UTC)-timedelta(seconds=1)))
    assert invoke(s, 'observe_resource').json()['state'] == 'unavailable'
    assert invoke(s, 'read_note').json() == saved.json()
    current = s.manager.inspect(1)
    s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=current['grant_record_revision'])
    assert invoke(s, 'observe_resource').json() == {'state': 'access_required'}
    assert invoke(s, 'read_note').json() == saved.json()
    with Session(s.engine) as db:
        assert not db.scalars(select(DeviceCommand)).all()  # This example has no physical command operation.
