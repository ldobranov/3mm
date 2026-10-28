"""Delivered public reference -> real host -> signed SDK -> current Core grants.

Local disposable Core/device-role/provider fixtures, NOT live Hub/Node transport,
Root/systemd isolation or portable recovery acceptance.
"""
from three_mm_platform_wire import COMPATIBILITY_ACTIONS

import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

import backend.database
from backend.config import ApplicationRuntimeSettings
from backend.db.base import Base
from backend.db.device import Device, DeviceCapabilityProvider, DeviceCapabilityHealth, DeviceCommand
from backend.db.module import ApplicationExtensionInstallation as Installation, ApplicationKioskTerminal, ModulePackage
from backend.routes import application_extensions as routes
from backend.services import application_authority_management as authority, compiled_ui
from backend.services.application_platform import ApplicationPlatformServer
from backend.services.device_capability_registry import capability_catalog
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_access import fake_compiler,kiosk_enrollment,kiosk_claim
from backend.tests.test_application_authority_management import (
    installed as managed_installed, source_subject, source_installed, identity, decide,
)
from backend.tests.test_application_reference import _builder_module, REFERENCE_ROOT
from backend.utils.db_utils import get_db
from three_mm_application_sdk import ApplicationPlatformClient
from three_mm_runtime.application_transport import ApplicationServiceClient, ApplicationTransportError


def specification():
    return json.loads((REFERENCE_ROOT / 'scoped-command.example.json').read_text())


def package(device_id='dev_' + '3' * 32):
    builder = _builder_module()
    return builder.build_package(device_id, '', version=builder.SCOPED_VERSION,
                                 scoped_command=specification())


def test_same_reference_scoped_package_is_deterministic_and_explicit():
    blob = package()
    assert blob == package()
    assert blob == _builder_module().build_package('dev_' + '3' * 32, '', scoped_command=specification())
    validated = validate_module_package(blob)
    assert validated.manifest.module_id == 'org.3mm.application-reference'
    assert validated.manifest.version == '1.1.0'
    definition = validated.application_extension
    assert definition.service.sdk_version == '1.3'
    assert not definition.jobs and not definition.connectors and not definition.event_subscriptions
    assert definition.storage.relational is None
    assert [binding.binding_id for binding in definition.command_bindings] == ['acceptance']
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        assert 'source/frontend/Capability.vue' in archive.namelist()
        source = archive.read('source/frontend/Capability.vue').decode()
        assert '@3mm/application-ui/v1' in source
        assert 'fetch(' not in source and 'localStorage' not in source
    legacy = _builder_module().build_package('dev_' + '3' * 32, 'http://127.0.0.1:9911')
    assert validate_module_package(legacy).manifest.version == '1.0.1'
    with zipfile.ZipFile(io.BytesIO(legacy)) as archive:
        assert 'source/frontend/Capability.vue' not in archive.namelist()
        with zipfile.ZipFile(io.BytesIO(archive.read('service/reference_application-1.0.1-py3-none-any.whl'))) as wheel:
            assert 'reference_application/scoped.py' not in wheel.namelist()


def test_scoped_package_is_identical_across_windows_and_linux_checkouts(tmp_path):
    builder = _builder_module()
    shutil.copytree(REFERENCE_ROOT, tmp_path / 'reference')
    builder.ROOT = tmp_path / 'reference'
    text_sources = [*(builder.ROOT / 'service/reference_application').glob('*.py'),
                    *(builder.ROOT / 'source/frontend').glob('*.vue')]
    for source in text_sources:
        source.write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
    linux = builder.build_package('dev_' + '3' * 32, '', scoped_command=specification())
    for source in text_sources:
        source.write_bytes(source.read_bytes().replace(b'\n', b'\r\n'))
    windows = builder.build_package('dev_' + '3' * 32, '', scoped_command=specification())
    assert windows == linux
    with zipfile.ZipFile(io.BytesIO(windows)) as archive:
        assert all(item.create_system == 3 for item in archive.infolist())
        with zipfile.ZipFile(io.BytesIO(archive.read('service/reference_application-1.1.0-py3-none-any.whl'))) as wheel:
            assert all(item.create_system == 3 for item in wheel.infolist())


@pytest.mark.parametrize('fault', ['unversioned', 'bad_example', 'extra'])
def test_builder_cannot_guess_or_widen_the_selected_contract(fault):
    spec = specification()
    if fault == 'unversioned': spec['contract_version'] = None
    elif fault == 'bad_example': spec['arguments']['duration_ms'] = 999
    else: spec['provider'] = 'assumed'
    with pytest.raises(ValueError):
        _builder_module().build_package('dev_' + '3' * 32, '', scoped_command=spec)


@pytest.mark.parametrize('value', ['null', '[]', '"not a specification"'])
def test_explicit_scoped_cli_never_falls_back_to_compatibility(tmp_path, monkeypatch, value):
    spec = tmp_path / 'spec.json'
    spec.write_text(value)
    output = tmp_path / 'package.zip'
    monkeypatch.setattr(sys, 'argv', ['builder', '--output', str(output),
        '--reader-device-id', 'dev_' + '3' * 32, '--scoped-command', str(spec)])
    with pytest.raises(ValueError, match='JSON object'):
        _builder_module().main()
    assert not output.exists()


@pytest.mark.skipif(os.name != 'posix', reason='Actual Linux keys, host process and signed sockets')
@pytest.mark.parametrize('layout,provider', [('standalone', 'native'), ('hub_node', 'firmware')])
def test_delivered_reference_ui_sdk_authority_and_lifecycle(managed_installed, monkeypatch, layout, provider):
    s = managed_installed
    blob = package()
    s.validated = validate_module_package(blob)
    s.archive = s.root / 'modules' / (s.validated.sha256 + '.zip')
    s.archive.write_bytes(blob)
    definition = s.validated.application_extension
    configuration = s.validated.manifest.configuration_defaults
    Base.metadata.create_all(s.engine)
    with s.engine.begin() as db:
        db.execute(update(ModulePackage).where(ModulePackage.id == 1).values(
            module_id=s.validated.manifest.module_id, version='1.1.0',
            manifest=s.validated.manifest.model_dump(mode='json'), sha256=s.validated.sha256,
            size_bytes=len(blob), file_path=str(s.archive)))
        db.execute(update(Installation).values(module_id=s.validated.manifest.module_id,
            configuration=configuration, active_version='1.1.0', enabled=False, status='disabled'))
        db.execute(update(Device).values(role='standalone' if layout == 'standalone' else 'node'))
        db.execute(update(DeviceCapabilityProvider).values(provider_type=provider))
        db.execute(update(DeviceCapabilityHealth).values(provider_type=provider))
    monkeypatch.setenv('COMPILED_UI_ARTIFACTS_DIR', str(s.root / 'compiled'))

    def compiler(command, **kwargs):
        result = fake_compiler(command, **kwargs)
        (Path(command[3]) / 'build-toolchain.json').write_text(json.dumps(
            {'node': '24.19.0', 'vite': '6.4.3', 'vue_plugin': '5.2.4'}))
        return result

    with monkeypatch.context() as compiling:
        compiling.setattr(compiled_ui.subprocess, 'run', compiler)
        build = compiled_ui.compile_ui_package(blob, s.validated)
    with Session(s.engine) as db, db.begin():
        declaration = capability_catalog(db, db.get(Device, 1))[0]
        db.execute(update(DeviceCapabilityHealth).values(report={
            'declaration_digest': declaration.declaration_digest,
            'capabilities': [{'capability_id': 'gpio.digital.control', 'healthy': True}],
        }))
    native = s.manager.record_native_review(1, actor_token=s.token, request_id=identity(),
        artifact_sha256=s.validated.sha256, review_document_sha256='b' * 64,
        native_code_review_completed=True, accepts_native_host_risk=True,
        accepts_same_origin_ui_risk=True, built_ui_sha256=build.built_ui_sha256)

    def plan():
        return s.manager.create_review(1, actor_token=s.token, request_id=identity(),
            native_review_id=native['native_review_id'], scopes=['command:acceptance'])

    approved = decide(s, plan(), 'approve')
    assert not s.manager.inspect(1)['grant_effective']
    decide(s, approved, 'apply')
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=True, status='active', authority_epoch=identity()))
    decide(s, decide(s, plan(), 'approve'), 'apply')
    assert s.manager.inspect(1)['grant_effective']
    monkeypatch.setattr(backend.database, 'SessionLocal', sessionmaker(s.engine))

    with tempfile.TemporaryDirectory(prefix='reference-', dir='/tmp') as temporary:
        root = Path(temporary)
        key_root = root / 'keys'; key_root.mkdir()
        secret = b's' * 32
        (key_root / ('a' * 24 + '.key')).write_bytes(secret)
        platform = ApplicationPlatformServer(root / 'p.sock', key_root, group='missing-test-group', allowed_actions=COMPATIBILITY_ACTIONS)
        platform.start()
        app_root = root / 'apps'
        instance = app_root / ('a' * 24)
        release = instance / 'releases' / s.validated.sha256
        release.mkdir(parents=True)
        (instance / 'run').mkdir()
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            artifact = definition.service.artifact
            (release / Path(artifact).name).write_bytes(archive.read(artifact))
        (instance / 'active.json').write_text(json.dumps({
            'instance_id': 'a' * 24, 'sha256': s.validated.sha256,
            'module_id': s.validated.manifest.module_id, 'version': '1.1.0',
            'wheel': Path(artifact).name, 'entrypoint': definition.service.entrypoint,
            'storage': definition.storage.model_dump(mode='json'),
            'operations': [item.model_dump(mode='json') for item in definition.operations],
            'health_operation_id': 'health', 'configuration': configuration,
            'platform_socket': str(platform.socket_path),
        }))
        processes = []

        def start_host():
            process = subprocess.Popen([sys.executable, '-m', 'three_mm_runtime.application_host',
                '--instance', 'a' * 24, '--root', str(app_root), '--key-root', str(key_root)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            processes.append(process)
            deadline = time.monotonic() + 8
            while not (instance / 'run/service.sock').exists() and time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail(process.communicate()[1].decode())
                time.sleep(.025)
            assert (instance / 'run/service.sock').exists()
            return process

        host = start_host()
        with s.engine.begin() as db:
            db.execute(update(Installation).values(socket_path=str(instance / 'run/service.sock')))
        settings = ApplicationRuntimeSettings(root=app_root, key_root=key_root, helper_socket=root / 'unused')
        from backend.tests.response_helpers import install_response_transport
        install_response_transport(monkeypatch)
        monkeypatch.setattr(routes, 'get_settings', lambda: type('Settings', (), {'applications': settings})())
        app = FastAPI(); app.include_router(routes.router)

        def session():
            with Session(s.engine) as db: yield db

        app.dependency_overrides[get_db] = session
        base = '/api/v1/application-extensions/' + s.validated.manifest.module_id
        auth = {'Authorization': 'Bearer ' + s.user_token}
        admin = {'Authorization': 'Bearer ' + s.token}
        bindings = {entry: {'host_version': 1, 'entrypoint_id': entry,
            'artifact_sha256': s.validated.sha256, 'built_ui_sha256': build.built_ui_sha256}
            for entry in ('registration', 'operations')}

        def probe(client, key, arguments=None, headers=None, context=None, audience='operator'):
            return client.post(base + '/' + audience + '/operations/probe', headers=headers or auth,
                json={'payload': {'arguments': arguments or specification()['arguments']},
                      'idempotency_key': key, 'ui_context': context or bindings['operations']})

        def count():
            with Session(s.engine) as db: return len(db.scalars(select(DeviceCommand)).all())

        try:
            with TestClient(app) as client:
                assert probe(client, 'no-human').status_code == 403
                assert count() == 0
                assert s.manager.inspect(1)['grant_effective']
                assert client.post(base + '/permissions/grants', headers=auth,
                    json={'user_id': 2, 'permission_id': 'probe_use'}).status_code == 403
                assert client.post(base + '/permissions/grants', headers=admin,
                    json={'user_id': 2, 'permission_id': 'probe_use'}).status_code == 201
                code = client.post(base + '/kiosk/enrollments', headers=admin, json=kiosk_enrollment('Mock reference')).json()['code']
                claimed = client.post(base + '/kiosk/enrollments/claim', json=kiosk_claim(code)).json()
                kiosk = {'Authorization': 'Bearer ' + claimed['access_token']}
                first = probe(client, 'kiosk-001', headers=kiosk, context=bindings['registration'], audience='kiosk')
                assert first.status_code == 200, first.text
                with Session(s.engine) as db:
                    assert db.scalar(select(ApplicationKioskTerminal.last_seen_at).where(
                        ApplicationKioskTerminal.terminal_id == claimed['terminal_id'])) is not None
                assert probe(client, 'operator-001').status_code == 200
                assert count() == 2
                assert probe(client, 'operator-001').status_code == 200
                assert count() == 2
                assert probe(client, 'operator-001', {**specification()['arguments'], 'duration_ms': 51}).status_code == 409
                assert probe(client, 'foreign-channel', {'channel': 'output.2', 'duration_ms': 50}).status_code in (409, 422)
                assert probe(client, 'stale-build', context={**bindings['operations'], 'built_ui_sha256': 'f' * 64}).status_code == 409
                assert probe(client, 'public-001', audience='public').status_code in (401, 403)
                assert count() == 2
                sdk = ApplicationPlatformClient(platform.socket_path, 'a' * 24, secret)
                with pytest.raises(Exception):
                    sdk.submit_command('foreign', request_id='undeclared-001', arguments={}, ttl_seconds=5)
                with pytest.raises(Exception): sdk.get_checkpoint('foreign')
                assert count() == 2
                original = ApplicationServiceClient.invoke

                def lose_reply(self, operation, payload, context, **kwargs):
                    value = original(self, operation, payload, context, **kwargs)
                    if operation == 'probe': raise ApplicationTransportError('Injected lost ACK')
                    return value

                with monkeypatch.context() as lost:
                    lost.setattr(ApplicationServiceClient, 'invoke', lose_reply)
                    assert probe(client, 'uncertain-001').status_code == 409
                assert count() == 3
                outcome = client.post(base + '/operator/operations/lookup', headers=auth,
                    json={'payload': {'request_id': 'uncertain-001'}, 'ui_context': bindings['operations']})
                assert outcome.status_code == 200 and outcome.json()['status'] == 'found'
                host.terminate(); host.communicate(timeout=5)
                (instance / 'run/service.sock').unlink()
                host = start_host()
                assert count() == 3  # Restart/health never replay business work.
                assert probe(client, 'operator-001').status_code == 200
                assert count() == 3
                assert client.delete(base + '/kiosk/terminals/' + claimed['terminal_id'], headers=admin).status_code == 200
                assert probe(client, 'revoked-kiosk', headers=kiosk, context=bindings['registration'], audience='kiosk').status_code == 401
                assert client.delete(base + '/permissions/grants/2/probe_use', headers=admin).status_code == 200
                assert probe(client, 'revoked-human').status_code == 403
                assert s.manager.inspect(1)['grant_effective']  # Human revocation is not SDK revocation.
                assert count() == 3
                assert client.post(base + '/permissions/grants', headers=admin,
                    json={'user_id': 2, 'permission_id': 'probe_use'}).status_code == 201
                status = s.manager.inspect(1)
                s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=status['grant_record_revision'])
                access = client.get(base + '/access', headers=auth)
                assert access.status_code == 200 and 'operations' in access.json()['allowed_route_ids']
                assert probe(client, 'revoked-001').status_code == 409
                assert count() == 3
                with s.engine.begin() as db:
                    db.execute(update(Installation).values(enabled=False, status='disabled'))
                assert probe(client, 'disabled-001').status_code == 409
                with s.engine.begin() as db:
                    db.execute(update(Installation).values(enabled=True, status='active', authority_epoch=identity()))
                assert probe(client, 'reenabled-no-grant').status_code == 409
                assert count() == 3
        finally:
            for process in processes:
                if process.poll() is None: process.terminate()
                process.communicate(timeout=5)
            platform.stop()
