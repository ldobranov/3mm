"""Unused application/UI retirement never executes obsolete package contents."""
import backend.database  # noqa: F401
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.db.device import Device
from backend.db.module_reference import ModulePackageRetainedReference
from backend.db.module import ApplicationExtensionInstallation, ModuleInstallation, ModulePackage
from backend.db.user import User
from backend.routes import modules
from backend.services.module_packages import validate_module_package
from backend.tests.test_module_packages import (
    application_package, compiled_ui_definition, compiled_ui_package,
)
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token
from datetime import UTC, datetime


def service_only_package():
    with zipfile.ZipFile(io.BytesIO(application_package())) as source:
        manifest = json.loads(source.read('manifest.json'))
        definition = json.loads(source.read('application-extension.json'))
        manifest.update(runtimes=['core'], entrypoints={'core': 'application-extension.json'})
        definition['routes'] = []
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as target:
            target.writestr('manifest.json', json.dumps(manifest))
            target.writestr('application-extension.json', json.dumps(definition))
            artifact = definition['service']['artifact']
            target.writestr(artifact, source.read(artifact))
    return output.getvalue()


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add_all([User(id=1, username='admin', role='admin'), User(id=2, username='operator', role='user')])
    db.commit()
    uploads, artifacts = tmp_path/'uploads', tmp_path/'compiled'
    (uploads/'modules').mkdir(parents=True)
    artifacts.mkdir()
    monkeypatch.setattr(modules, 'get_settings', lambda: SimpleNamespace(backend=SimpleNamespace(uploads_dir=uploads)))
    monkeypatch.setattr(modules, 'compiled_artifacts_dir', lambda: artifacts)
    app = FastAPI(); app.include_router(modules.router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        state = SimpleNamespace(db=db, client=client, uploads=uploads, artifacts=artifacts, root=tmp_path,
            admin={'Authorization': 'Bearer '+create_access_token('1', {'role': 'admin'})},
            user={'Authorization': 'Bearer '+create_access_token('2', {'role': 'user'})})
        def add(blob):
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:manifest = json.loads(archive.read('manifest.json'))
            digest = hashlib.sha256(blob).hexdigest(); path = uploads/'modules'/f'{digest}.zip'; path.write_bytes(blob)
            row = ModulePackage(module_id=manifest['module_id'], version=manifest['version'], sha256=digest,
                size_bytes=len(blob), manifest=manifest, registrations=[], file_path=str(path))
            db.add(row); db.commit()
            artifact = artifacts/row.module_id/row.version/digest; artifact.mkdir(parents=True)
            (artifact/'old-build.txt').write_text('owned obsolete build')
            state.row, state.archive, state.artifact = row, path, artifact
            state.url = '/api/v1/modules/compiled-ui/packages/'+quote(row.module_id,safe='')+'/'+quote(row.version,safe='')
            return state
        state.add = add
        yield state
    db.close(); engine.dispose()


@pytest.mark.parametrize('kind', ['service_only', 'application_ui', 'compiled_ui'])
def test_unused_catalog_package_can_be_retired_without_installation(catalog, kind, monkeypatch):
    blob = {'service_only': service_only_package, 'application_ui': application_package,
            'compiled_ui': compiled_ui_package}[kind]()
    validated = validate_module_package(blob)
    if kind == 'service_only':assert validated.application_extension is not None and validated.compiled_ui is None
    s = catalog.add(blob)
    monkeypatch.setattr(modules, '_validated_compiled_package', lambda *_: pytest.fail('Retirement parsed executable contents'))
    response = s.client.delete(s.url, headers=s.admin)
    assert response.status_code == 200, response.text
    assert response.json() == {'status': 'deleted', 'module_id': validated.manifest.module_id, 'version': '1.0.0'}
    assert s.db.get(ModulePackage, s.row.id) is None and not s.archive.exists() and not s.artifact.exists()


@pytest.mark.parametrize('damage', ['missing', 'corrupt', 'unsupported'])
def test_obsolete_or_damaged_archive_does_not_trap_unused_catalog_entry(catalog, damage):
    blob = (compiled_ui_package(definition=compiled_ui_definition(compiled_ui_version=99))
            if damage == 'unsupported' else compiled_ui_package())
    s = catalog.add(blob)
    if damage == 'missing':s.archive.unlink()
    elif damage == 'corrupt':s.archive.write_bytes(b'not a zip anymore')
    response = s.client.delete(s.url, headers=s.admin)
    assert response.status_code == 200, response.text
    assert s.db.get(ModulePackage, s.row.id) is None and not s.archive.exists() and not s.artifact.exists()


@pytest.mark.parametrize('reference', ['application', 'application_previous', 'device', 'retained_resource'])
def test_referenced_package_is_not_retired_even_when_archive_is_invalid(catalog, reference):
    s = catalog.add(compiled_ui_package())
    if reference == 'application':
        s.db.add(ApplicationExtensionInstallation(module_id=s.row.module_id, module_package_id=s.row.id,
            instance_id='a'*24, socket_path='pending', active_version=None, status='recovery_required', enabled=False))
    elif reference == 'application_previous':
        current = ModulePackage(module_id=s.row.module_id, version='2.0.0', sha256='d'*64,
            manifest={'entrypoints': {'core': 'application-extension.json'}}, size_bytes=1,
            file_path=str(s.uploads/'modules'/('d'*64+'.zip')), registrations=[])
        s.db.add(current);s.db.flush()
        s.db.add(ApplicationExtensionInstallation(module_id=s.row.module_id, module_package_id=current.id,
            previous_package_id=s.row.id, instance_id='b'*24, socket_path='pending', active_version='2.0.0',
            status='disabled', enabled=False))
    elif reference == 'device':
        device = Device(device_id='dev_'+'1'*32, role='node', protocol_version='1.0', approved_at=datetime.now(UTC))
        s.db.add(device);s.db.flush()
        s.db.add(ModuleInstallation(device_id=device.id, module_package_id=s.row.id, module_id=s.row.module_id, desired_version=s.row.version))
    else:
        s.db.add(ModulePackageRetainedReference(reference_id='1'*64, package_id=s.row.id,
            source='retained-resource', resource_ref='resource:example'))
    s.db.commit();s.archive.write_bytes(b'invalid')
    response = s.client.delete(s.url, headers=s.admin)
    assert response.status_code == 409
    assert s.db.get(ModulePackage, s.row.id) is not None and s.archive.read_bytes()==b'invalid' and s.artifact.exists()


def test_retirement_requires_admin(catalog):
    s = catalog.add(service_only_package())
    assert s.client.delete(s.url).status_code == 401
    assert s.client.delete(s.url, headers=s.user).status_code == 403
    assert s.archive.exists() and s.db.get(ModulePackage, s.row.id) is not None


def test_generic_retained_reference_projection_is_bounded(catalog):
    s=catalog.add(compiled_ui_package())
    s.db.add_all(ModulePackageRetainedReference(reference_id=hashlib.sha256(str(index).encode()).hexdigest(),
        package_id=s.row.id,source='retained-data',resource_ref='resource:'+str(index)) for index in range(257))
    s.db.commit()
    response=s.client.get(s.url+'/retained-references',headers=s.admin)
    assert response.status_code==200
    assert len(response.json()['references'])==256 and response.json()['truncated'] is True
    assert s.client.delete(s.url,headers=s.admin).status_code==409


@pytest.mark.parametrize('field,value', [('module_id', 'org.example\\escape'), ('version', '..\\escape'), ('sha256', '../escape')])
def test_invalid_catalog_identity_never_selects_a_cleanup_path(catalog, field, value):
    s = catalog.add(compiled_ui_package());setattr(s.row,field,value);s.db.commit()
    url = '/api/v1/modules/compiled-ui/packages/'+quote(s.row.module_id,safe='')+'/'+quote(s.row.version,safe='')
    response = s.client.delete(url, headers=s.admin)
    assert response.status_code == 409
    assert s.archive.exists() and s.artifact.exists() and s.db.get(ModulePackage,s.row.id) is not None


def test_unmanaged_archive_path_is_rejected_without_touching_either_file(catalog):
    s = catalog.add(compiled_ui_package());outside=s.root/'outside.txt';outside.write_text('keep')
    s.row.file_path=str(outside);s.db.commit()
    assert s.client.delete(s.url,headers=s.admin).status_code==409
    assert outside.read_text()=='keep' and s.archive.exists() and s.artifact.exists()
    assert s.db.get(ModulePackage,s.row.id) is not None


@pytest.mark.skipif(os.name!='posix',reason='Actual POSIX symbolic links')
@pytest.mark.parametrize('linked', ['archive', 'archive_parent', 'artifact', 'artifact_parent'])
def test_cleanup_never_follows_a_link_outside_managed_paths(catalog, linked):
    s=catalog.add(compiled_ui_package());outside=s.root/'outside';outside.mkdir();sentinel=outside/'keep';sentinel.write_text('keep')
    if linked=='archive':s.archive.unlink();s.archive.symlink_to(sentinel)
    elif linked=='archive_parent':
        s.archive.unlink();s.archive.parent.rmdir();s.archive.parent.symlink_to(outside,target_is_directory=True)
    elif linked=='artifact':
        (s.artifact/'old-build.txt').unlink();s.artifact.rmdir();s.artifact.symlink_to(outside,target_is_directory=True)
    else:
        (s.artifact/'old-build.txt').unlink();s.artifact.rmdir();s.artifact.parent.rmdir();s.artifact.parent.symlink_to(outside,target_is_directory=True)
    assert s.client.delete(s.url,headers=s.admin).status_code==409
    assert sentinel.read_text()=='keep' and s.db.get(ModulePackage,s.row.id) is not None


def test_retirement_does_not_make_unsupported_archives_uploadable_or_executable(catalog):
    blob=compiled_ui_package(definition=compiled_ui_definition(compiled_ui_version=99));s=catalog.add(blob)
    uploaded=s.client.post('/api/v1/modules/packages',headers=s.admin,files={'package':('unsupported.zip',blob,'application/zip')})
    assert uploaded.status_code==422
    asset=s.client.get(f'/api/v1/modules/compiled-ui/assets/{s.row.module_id}/{s.row.version}/{s.row.sha256}/assets/old.mjs')
    assert asset.status_code==409
    assert s.archive.exists() and s.db.get(ModulePackage,s.row.id) is not None
