"""Real packages/admin authorization; preflight refuses before any lifecycle effect."""
import io
import json
from pathlib import Path
import zipfile

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.module import ModulePackage, ApplicationExtensionInstallation
from backend.services.module_packages import validate_module_package
from backend.services.application_requirements import inspect_platform_requirements
from backend.tests.test_application_lifecycle_authority import lifecycle, snapshot, request
from backend.utils.jwt_utils import create_access_token
from backend.services.application_requirements import ApplicationRequirementsError
from three_mm_protocol import ApplicationExtensionV1
from three_mm_protocol.tests.test_application_extension import definition


def candidate(s, requirements, *, fresh=False):
    with Session(s.engine) as db:
        source = db.get(ModulePackage, 1)
        blob = Path(source.file_path).read_bytes()
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(blob)) as old, zipfile.ZipFile(output, 'w') as new:
        for name in old.namelist():
            data = old.read(name)
            if name in {'manifest.json','application-extension.json','compiled-ui.json'}:
                value = json.loads(data); value['version'] = '1.0.1'
                if fresh: value['module_id'] = 'org.example.requirement-consumer'
                if name == 'application-extension.json':
                    value['service']['sdk_version'] = '1.3'
                    value['platform_requirements'] = requirements
                data = json.dumps(value).encode()
            new.writestr(name, data)
    payload = output.getvalue(); package = validate_module_package(payload)
    target = Path(source.file_path).with_name(package.sha256+'.zip'); target.write_bytes(payload)
    with Session(s.engine) as db, db.begin():
        db.add(ModulePackage(module_id=package.manifest.module_id, version=package.manifest.version,
            manifest=package.manifest.model_dump(mode='json'), sha256=package.sha256,
            size_bytes=len(payload), file_path=str(target), registrations=[]))
    return package, target


def need(**changes):
    return {'requirement_id':'missing_feature', 'operations':['future.not_implemented'], **changes}


@pytest.mark.parametrize('fresh', [False, True])
@pytest.mark.parametrize('fault', ['operation', 'version', 'compatibility_only'])
def test_missing_required_support_preserves_state_and_never_calls_helper(lifecycle, fresh, fault):
    s = lifecycle
    declaration = need()
    if fault == 'version': declaration.update(operations=['event.publish'], transport_contract_version=2)
    elif fault == 'compatibility_only': declaration['operations'] = ['installation.peers.enroll']
    package, _ = candidate(s, [declaration], fresh=fresh)
    before = snapshot(s)
    url = '/api/v1/application-extensions/packages/'+package.sha256
    observed = s.client.get(url+'/platform-requirements', headers=s.auth)
    assert observed.status_code == 200, observed.text
    assert observed.headers['cache-control'] == 'no-store'
    report = observed.json()
    assert report['status'] == 'blocked' and report['artifact_sha256'] == package.sha256
    assert report['permission_approval'] == report['resource_bindings'] == report['runtime_readiness'] == 'not_evaluated'
    result = s.client.post(url+'/activate', headers=s.auth, json=s.body)
    assert result.status_code == 409 and 'missing_feature' in result.json()['detail']
    assert snapshot(s) == before and not s.calls


def test_optional_missing_support_allows_normal_activation_without_resource_authority(lifecycle):
    s = lifecycle
    package, _ = candidate(s, [need(required=False)])
    # Use the fixture's ordinary helper, retaining its exact lifecycle fence.
    s.result.update(version='1.0.1', sha256=package.sha256)
    s.activate = '/api/v1/application-extensions/packages/'+package.sha256+'/activate'
    observed = s.client.get(s.activate.removesuffix('/activate')+'/platform-requirements', headers=s.auth)
    assert observed.json()['status'] == 'degraded'
    result = request(s, 'activating')
    assert result.status_code == 200, result.text
    assert s.calls == ['activating']
    assert result.json()['active_version'] == '1.0.1'
    assert inspect_platform_requirements(package.application_extension).permission_approval == 'not_evaluated'


def test_observation_and_activation_do_not_accept_a_client_supplied_assessment(lifecycle):
    s = lifecycle
    package, path = candidate(s, [need()])
    before = snapshot(s)
    base = '/api/v1/application-extensions/packages/'+package.sha256
    assert s.client.get(base+'/platform-requirements').status_code == 401
    user = {'Authorization':'Bearer '+create_access_token('2', {'role':'user'})}
    assert s.client.get(base+'/platform-requirements', headers=user).status_code == 403
    assert s.client.get('/api/v1/application-extensions/packages/'+'f'*64+'/platform-requirements', headers=s.auth).status_code == 404
    result = s.client.post(base+'/activate', headers=s.auth,
        json={**s.body, 'platform_requirements': {'status':'satisfied'}})
    assert result.status_code == 422
    path.write_bytes(b'changed after inspection')
    assert s.client.get(base+'/platform-requirements', headers=s.auth).status_code == 409
    assert s.client.post(base+'/activate', headers=s.auth, json=s.body).status_code == 409
    assert snapshot(s) == before and not s.calls


@pytest.mark.parametrize('operation', ['disabling', 'uninstalling'])
def test_unsupported_installed_app_stays_administrable(lifecycle, operation):
    # Represents an existing installation after Core support changes; dependency
    # failure must not lock its operator out of stop/removal/recovery.
    s = lifecycle
    package, _ = candidate(s, [need()])
    with Session(s.engine) as db, db.begin():
        target = db.scalar(select(ModulePackage).where(ModulePackage.sha256 == package.sha256))
        app = db.get(ApplicationExtensionInstallation, 1)
        app.module_package_id = target.id; app.active_version = target.version
    report = s.client.get('/api/v1/application-extensions/packages/'+package.sha256+'/platform-requirements', headers=s.auth)
    assert report.json()['status'] == 'blocked'
    result = request(s, operation)
    assert result.status_code == 200, result.text
    assert s.calls == [operation]


@pytest.mark.parametrize('operation', ['prepare', 'migrate', 'activate', 'upgrade'])
def test_prepared_profiles_refuse_before_issuing_any_durable_permission(operation):
    from types import SimpleNamespace
    from backend.services.application_relational_lifecycle import issue_existing_schema_preparation, issue_migrated_schema_preparation
    from backend.services.application_relational_activation import issue_prepared_activation
    from backend.services.application_relational_upgrade import issue_prepared_database_upgrade
    value = definition(); value['service']['sdk_version'] = '1.3'; value['platform_requirements'] = [need()]
    app = ApplicationExtensionV1.model_validate(value)
    def forbidden(*args, **kwargs): pytest.fail('Unsupported requirement reached the authority writer')
    manager = SimpleNamespace(_prepare=lambda _: (None, SimpleNamespace(application_extension=app)), _write=forbidden)
    arguments = dict(actor_token='not-consumed', request_id='a'*32,
        expected_grant_record_revision='b'*32, transport_secret=b's'*32)
    if operation == 'prepare':
        method = issue_existing_schema_preparation; arguments['confirm_owned_metadata_preparation'] = True
    elif operation == 'migrate':
        method = issue_migrated_schema_preparation; arguments['confirm_owned_business_migrations'] = True
    elif operation == 'activate':
        method = issue_prepared_activation
        arguments.update(source_preparation_id='c'*32, confirm_start_prepared_service=True,
            service_uid=1001, service_gid=1001, coordinator_uid=1002)
    else:
        method = issue_prepared_database_upgrade
        arguments.update(source_preparation_id='c'*32, expected_source_revision='d'*32, confirm_owned_forward_upgrade=True)
    with pytest.raises(ApplicationRequirementsError, match='missing_feature'): method(manager, 1, **arguments)
