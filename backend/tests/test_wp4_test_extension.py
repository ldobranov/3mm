"""Delivered neutral ZIP, real reviewed file grants and signed SDK transport."""
from three_mm_platform_wire import COMPATIBILITY_ACTIONS
import hashlib
import importlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import zipfile

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.services.module_packages import validate_module_package
from three_mm_application_sdk import ApplicationContext, ApplicationStorage, OperationContext
from three_mm_application_sdk import ApplicationFileLimits, ApplicationPlatformClient, ApplicationScopedFileStorage
from backend.tests.test_application_file_execution import (
    file_app, managed_installed, source_subject, source_installed, grant, revoke, identity,
)

ROOT = Path(__file__).parents[2] / "modules" / "wp4-test"


def builder():
    spec = importlib.util.spec_from_file_location("wp4_test_builder", ROOT / "build_test_package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def delivered(tmp_path):
    payload = builder().build_package()
    package = validate_module_package(payload)
    wheel = tmp_path / "fixture.whl"
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        wheel.write_bytes(archive.read(package.application_extension.service.artifact))
    sys.path.insert(0, str(wheel))
    try:
        yield payload, package, importlib.import_module("wp4_test.service"), importlib.import_module("wp4_test.migrations")
    finally:
        sys.path.remove(str(wheel))
        for name in list(sys.modules):
            if name == "wp4_test" or name.startswith("wp4_test."):
                sys.modules.pop(name)


@pytest.mark.parametrize('architecture', ['armv6l', 'aarch64', 'x86_64'])
def test_delivered_zip_is_reproducible_headless_manifest_v2(architecture):
    payload = builder().build_package()
    assert payload == builder().build_package()
    package = validate_module_package(payload, architecture=architecture)
    assert package.manifest.manifest_version == 2
    assert package.manifest.module_id == 'org.3mm.wp4-test'
    assert package.compiled_ui is None
    app = package.application_extension
    assert app.service.sdk_version == '1.3'
    assert not (app.jobs or app.connectors or app.command_bindings or app.event_subscriptions or app.public_http_routes or app.routes)
    assert not package.manifest.capabilities.provides and not package.manifest.capabilities.consumes
    assert app.storage.relational is None
    assert app.storage.private_files.max_file_bytes == 1024
    assert app.storage.private_files.max_total_bytes == 4096
    assert app.storage.private_files.max_files == 4


def context(data, service, files=None):
    return service.create_service(ApplicationContext('org.3mm.wp4-test', '1.0.0', data,
        {}, ApplicationStorage(data), file_storage=files))


def admin(request_id=None):
    return OperationContext('administrator', 'test', user_id=1, idempotency_key=request_id)


def test_factory_health_echo_never_touch_files_and_direct_fallback_is_refused(delivered, tmp_path):
    _, _, module, _ = delivered
    data = tmp_path / 'data'
    service = context(data, module)
    assert service.handle('health', {}, OperationContext('internal', 'test')) == {'status': 'ready'}
    assert service.handle('echo', {'message': 'hello'}, admin()) == {'message': 'hello'}
    assert not data.exists()
    with pytest.raises(ValueError, match='scoped private-file adapter'):
        service.handle('file_get', {}, admin())
    with pytest.raises(ValueError, match='administrator'):
        service.handle('echo', {'message': 'hello'}, OperationContext('public', 'test'))
    assert not data.exists()


def test_declared_files_without_platform_authority_do_not_write(delivered, tmp_path):
    _, _, module, migrations = delivered
    data = tmp_path / 'data'
    storage = ApplicationStorage(data)
    storage.migrate(migrations.get_migrations(), '0001')
    files = ApplicationScopedFileStorage(data, limits=ApplicationFileLimits(1024, 4096, 4))
    service = context(data, module, files)
    assert service.handle('file_get', {}, admin())['status'] == 'blocked'
    rid = '1' * 32
    request = {'request_id': rid, 'text': 'test', 'expected_sha256': None}
    assert service.handle('file_put', request, admin(rid))['status'] == 'blocked'
    assert service.handle('file_receipt', {'request_id': rid}, admin())['status'] == 'blocked'
    with pytest.raises(ValueError, match='same file request ID'):
        service.handle('file_put', request, admin('2' * 32))
    assert not (data / 'sdk-files').exists()


@pytest.mark.skipif(os.name != 'posix', reason='Actual Core-owned keys and Unix transport')
def test_exact_delivered_zip_real_grants_sdk_file_receipts_and_revocation(delivered, file_app, monkeypatch):
    import backend.database
    from backend.db.module import ModulePackage, ApplicationExtensionInstallation as Installation
    from backend.services.application_platform import ApplicationPlatformServer
    from three_mm_runtime.application_file_executor import ApplicationFileExecutor
    payload, package, module, _ = delivered
    s = file_app
    s.validated = package
    s.archive = s.root / 'modules' / (package.sha256 + '.zip')
    s.archive.write_bytes(payload)
    s.metadata['sha256'] = package.sha256
    s.metadata['storage'] = package.application_extension.storage.model_dump(mode='json')
    with s.engine.begin() as db:
        db.execute(update(ModulePackage).where(ModulePackage.id == 1).values(
            module_id=package.manifest.module_id, version=package.manifest.version,
            sha256=package.sha256, size_bytes=len(payload), manifest=package.manifest.model_dump(mode='json')))
        db.execute(update(Installation).where(Installation.id == 1).values(
            module_id=package.manifest.module_id, configuration={}))
    assert s.manager.inspect(1)['review_available']
    assert s.manager.inspect(1)['scopes'] == ['storage:private_files_read', 'storage:private_files_write']
    monkeypatch.setattr(backend.database, 'SessionLocal', lambda: Session(s.engine))
    keys = s.runtime.parent / 'keys'
    keys.mkdir()
    (keys / (s.metadata['instance_id'] + '.key')).write_bytes(s.secret)
    gateway = ApplicationPlatformServer(s.runtime.parent / 'platform.sock', keys, allowed_actions=COMPATIBILITY_ACTIONS)
    gateway.start()
    files = ApplicationScopedFileStorage(s.runtime / 'data', limits=ApplicationFileLimits(1024, 4096, 4),
        platform=ApplicationPlatformClient(gateway.socket_path, s.metadata['instance_id'], s.secret))
    service = context(s.runtime / 'data', module, files)
    try:
        with ApplicationFileExecutor(s.runtime, s.metadata, s.secret):
            assert service.handle('file_get', {}, admin())['status'] == 'blocked'
            assert not (s.runtime / 'data/sdk-files').exists()
            grant(s)  # Real local native review, disabled adoption, approval, apply.
            rid = identity()
            request = {'request_id': rid, 'text': 'WP4 test', 'expected_sha256': None}
            stored = service.handle('file_put', request, admin(rid))
            assert stored['status'] == 'stored'
            assert stored['sha256'] == hashlib.sha256(b'WP4 test').hexdigest()
            assert service.handle('file_get', {}, admin()) == {'status': 'found', 'text': 'WP4 test', 'sha256': stored['sha256']}
            receipt = service.handle('file_receipt', {'request_id': rid}, admin())
            assert receipt['status'] == 'available' and receipt['receipt']['receipt']['outcome'] == 'completed'
            assert service.handle('file_put', request, admin(rid)) == stored
            assert service.handle('file_put', {**request, 'text': 'changed'}, admin(rid))['status'] == 'unconfirmed'
            revoke(s)
            assert service.handle('file_get', {}, admin())['status'] == 'blocked'
            denied_id = identity()
            assert service.handle('file_put', {**request, 'request_id': denied_id}, admin(denied_id))['status'] == 'unconfirmed'
            assert service.handle('file_receipt', {'request_id': rid}, admin())['status'] == 'available'
    finally:
        gateway.stop()
