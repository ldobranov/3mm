"""Version changes through the public admin APIs, with real seals and logins.

Only runtime helper I/O and the compiler are doubles. Package bytes, database,
consent, authority fences and request replay checks are real; no device is used.
"""
import io
import json
import os
import zipfile
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action, ApplicationAuthorityGrant as Grant
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage, ApplicationJobState
from backend.db.application_task import ApplicationTaskRun
from backend.db.session import UserSession
from backend.db.user import User
from backend.applications.management import api as routes
from backend.applications.management import access_api as application_authority
from backend.artifacts import api as modules
from backend.artifacts import compiled_ui
from backend.applications.management.staging import registration_id
from backend.artifacts.packages import validate_module_package
from backend.tests.test_application_ui_authority import ui_app, managed_installed, source_subject, source_installed
from backend.tests.test_application_authority_management import identity
from backend.storage.sessions import get_db

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Real protected Core seals and SQLite authority locks')


def add_version(s, version, change_definition=None):
    output = io.BytesIO()
    with zipfile.ZipFile(s.archive) as original, zipfile.ZipFile(output, 'w') as target:
        for name in original.namelist():
            value = original.read(name)
            if name in {'manifest.json', 'application-extension.json', 'compiled-ui.json'}:
                data = json.loads(value); data['version'] = version
                if name == 'application-extension.json' and change_definition:
                    change_definition(data)
                value = json.dumps(data).encode()
            target.writestr(name, value)
    blob = output.getvalue()
    package = validate_module_package(blob)
    path = s.root / 'modules' / (package.sha256 + '.zip'); path.write_bytes(blob)
    with Session(s.engine) as db, db.begin():
        record = ModulePackage(module_id=package.manifest.module_id, version=version,
            manifest=package.manifest.model_dump(mode='json'), sha256=package.sha256,
            size_bytes=len(blob), file_path=str(path), registrations=[])
        db.add(record); db.flush(); identifier = record.id
    compiled_ui.compile_ui_package(blob, package)
    return SimpleNamespace(id=identifier, package=package, sha256=package.sha256)


@pytest.fixture
def staged(ui_app, monkeypatch):
    s = ui_app
    s.target = add_version(s, '1.0.1')
    s.calls = []
    s.module_id = s.validated.manifest.module_id
    s.base = '/api/v1/application-extensions'
    s.access = s.base + '/' + s.module_id + '/authority'
    s.headers = {'Authorization': 'Bearer ' + s.token}
    settings = SimpleNamespace(applications=SimpleNamespace(helper_socket=s.root / 'helper.sock'))
    monkeypatch.setattr(routes, 'get_settings', lambda: settings)
    def activate(_helper, sha256, _actor, configuration, _lifecycle):
        with Session(s.engine) as db:
            current = db.get(Installation, 1)
            assert current.status == 'activating' and not current.enabled
            package = db.scalar(select(ModulePackage).where(ModulePackage.sha256 == sha256))
            s.calls.append(('activate', sha256))
            return dict(module_id=package.module_id, version=package.version, sha256=sha256,
                instance_id=current.instance_id, socket_path='service.sock')
    def disable(_helper, _instance, _actor, _lifecycle):
        with Session(s.engine) as db:
            assert db.get(Installation, 1).status == 'disabling'
        s.calls.append(('disable', None))
    monkeypatch.setattr(routes.UpdateHelperClient, 'activate_application_extension', activate)
    monkeypatch.setattr(routes.UpdateHelperClient, 'disable_application_extension', disable)
    app = FastAPI(); app.include_router(routes.router); app.include_router(application_authority.router); app.include_router(modules.router)
    def database():
        with Session(s.engine) as db: yield db
    app.dependency_overrides[get_db] = database
    with TestClient(app, raise_server_exceptions=False) as client:
        s.http = client
        yield s


def post(s, path, body=None, *, status=200, headers=None):
    response = s.http.post(path, json=body, headers=s.headers if headers is None else headers)
    assert response.status_code == status, response.text
    return response.json()


def approve(s):
    reviewed = post(s, s.access + '/consent/preview', {'request_id': identity()})
    saved = post(s, s.access + '/consent/allow', dict(request_id=identity(),
        preview_id=reviewed['preview_id'], expected_revision=reviewed['revision'],
        fingerprint=reviewed['fingerprint'], scopes=reviewed['selected_scopes'],
        user_permissions=reviewed['selected_user_permissions'], accept_native_code=True))
    assert saved['saved']
    return reviewed


def stage_body(s, **overrides):
    status = s.manager.inspect(1)
    return {**dict(request_id=identity(), expected_artifact_sha256=status['artifact_sha256'],
        expected_revision=status['grant_record_revision'], configuration={}), **overrides}


@pytest.mark.parametrize("initial", ["recovery_required", "disabled"])
def test_first_activation_recovery_restores_review_not_execution(staged, monkeypatch, initial):
    s = staged
    approve(s)  # A previously approved grant must not be revived by recovery.
    with Session(s.engine) as db, db.begin():
        app = db.get(Installation, 1)
        app.status, app.enabled, app.active_version = initial, False, None
        configuration = dict(app.configuration)

    def recover(_self, instance_id, _actor, context):
        s.calls.append(('recover', instance_id))
        return dict(status='disabled', instance_id=instance_id, lifecycle=context, quiescent=True)

    monkeypatch.setattr(routes.UpdateHelperClient, 'recover_application_extension', recover)
    path = s.base + '/' + s.module_id + '/lifecycle/recover'
    catalog = s.http.get(s.base, headers=s.headers).json()
    assert catalog[0]['recovery_preparation_required'] is (initial == 'disabled')
    post(s, s.access+'/consent/preview', {'request_id': identity()}, status=409)
    post(s, path, {'confirmed_external_outcome_reviewed': True}, headers={}, status=401)
    assert not s.calls
    recovered = post(s, path, {'confirmed_external_outcome_reviewed': True})
    assert recovered['status'] == 'disabled' and recovered['active_version'] is None
    with Session(s.engine) as db:
        assert db.get(Installation, 1).configuration == configuration
        assert db.get(Action, registration_id(db, 1, 1, s.validated.sha256)) is not None
    assert not s.http.get(s.base, headers=s.headers).json()[0]['recovery_preparation_required']
    assert not s.manager.inspect(1)['grant_effective']
    activation = s.base + '/packages/' + s.validated.sha256 + '/activate'
    post(s, activation, status=409)
    post(s, path, {'confirmed_external_outcome_reviewed': True}, status=409)
    assert [call[0] for call in s.calls] == ['recover']
    assert approve(s)['artifact_sha256'] == s.validated.sha256
    assert post(s, activation)['status'] == 'active'
    assert [call[0] for call in s.calls] == ['recover', 'activate']


@pytest.mark.parametrize('approved_device', [False, True])
def test_complete_inert_device_choice_before_consent(staged, approved_device):
    from backend.applications.authority import management as authority
    from backend.applications.authority import sources
    from backend.applications.management import provenance

    s = staged
    with s.manager.keys.locked() as key, Session(s.engine) as db, db.begin():
        app = db.get(Installation, 1)
        device = app.configuration['TARGET_DEVICE_ID']
        original = {name: value for name, value in app.configuration.items() if name != 'TARGET_DEVICE_ID'}
        app.configuration = original
        app.active_version = None
        app.enabled = False
        app.status = 'disabled'
        app.authority_mode = 'review_required'
        db.flush()
        marker = provenance.registration_id(db, 1)
        pin = SimpleNamespace(module_package_id=app.module_package_id,
            version=s.validated.manifest.version, sha256=s.validated.sha256)
        binding = provenance._binding(db, key, 1, pin, s.validated)
        authority._save(db, key, 'action', Action(request_id=marker, installation_id=1),
            authority._envelope('action', marker, 1, 'connector_registered_not_started',
                {'operation': 'connector_first_registration', 'binding': binding}))
        assert sources._package_pin(db, 1).active_version is None

    url = s.base+'/packages/'+s.validated.sha256
    fields = s.http.get(url+'/configuration', headers=s.headers)
    assert fields.status_code == 200
    assert fields.json()['missing_required_device_keys'] == ['TARGET_DEVICE_ID']
    post(s, s.access+'/consent/preview', {'request_id': identity()}, status=409)
    selected = device if approved_device else 'dev_'+'f'*32
    result = post(s, url+'/stage', dict(request_id=identity(),
        expected_artifact_sha256=s.validated.sha256, complete_device_configuration=True,
        configuration={'TARGET_DEVICE_ID': selected}), status=200 if approved_device else 409)
    assert s.calls == []
    with Session(s.engine) as db:
        app = db.get(Installation, 1)
        assert app.status == 'disabled' and app.active_version is None and not app.enabled
        assert app.authority_mode == 'review_required'
        assert app.configuration == ({**original, 'TARGET_DEVICE_ID': device} if approved_device else original)
        assert db.get(Grant, 1) is None
    if approved_device:
        assert result['execution'] == 'not_started'
        preview = post(s, s.access+'/consent/preview', {'request_id': identity()})
        assert not preview['access_saved'] and not preview['installation_enabled']


@pytest.mark.parametrize('selected',[{}, {'TARGET_DEVICE_ID':'dev_'+'f'*32}])
def test_optional_device_omission_is_saved_but_unknown_supplied_device_cannot_stage(staged,selected):
    s=staged
    def declaration(value):
        value['service']['sdk_version']='1.3'
        value['optional_resources']=['command:pulse']
    target=add_version(s,'1.0.4',declaration)
    approve(s);post(s,s.base+'/'+s.module_id+'/disable')
    body=stage_body(s);body['configuration']=selected
    result=s.http.post(s.base+'/packages/'+target.sha256+'/stage',json=body,headers=s.headers)
    assert result.status_code==(409 if selected else 200),result.text
    assert s.calls==[('disable',None)]
    with Session(s.engine) as db:
        app=db.get(Installation,1)
        if not selected:
            assert 'TARGET_DEVICE_ID' not in app.configuration
        else:assert app.module_package_id==1


def test_optional_missing_provider_can_be_staged_consented_and_activated(staged):
    from backend.db.module import ApplicationConnectorBinding
    s = staged
    def declaration(value):
        value['service']['sdk_version'] = '1.3'
        value['optional_resources'] = ['connector:business_api']
    target = add_version(s, '1.0.3', declaration)
    approve(s)
    post(s, s.base+'/'+s.module_id+'/disable')
    body = stage_body(s)
    with s.engine.begin() as db: db.execute(update(ApplicationConnectorBinding).values(enabled=False))
    result = post(s, s.base+'/packages/'+target.sha256+'/stage', body)
    assert result['execution'] == 'not_started'
    reviewed = approve(s)
    assert 'connector:business_api' not in reviewed['scopes']
    post(s, s.base+'/packages/'+target.sha256+'/activate')
    assert s.manager.inspect(1)['grant_effective']


def optional_candidate(s):
    def declaration(value):
        value['service']['sdk_version'] = '1.3'
        value['optional_resources'] = ['command:pulse', 'connector:business_api']
    target = add_version(s, '1.0.7', declaration)
    post(s, s.base+'/packages/'+target.sha256+'/stage', stage_body(s))
    return target


@pytest.mark.parametrize('previously_activated', [False, True])
@pytest.mark.parametrize('first_registration', ['staged', 'connector'])
def test_same_package_optional_selection_prepares_exact_configuration_without_reviving_consent(staged, previously_activated, first_registration):
    s = staged
    target = optional_candidate(s)
    from backend.applications.management import provenance
    if first_registration == 'connector':
        from backend.applications.authority import management as authority
        # The first connector setup has its own immutable proof, no package
        # staging marker and no previous version. Optional selection must work
        # here too, without changing the old proof's previous-package binding.
        with s.manager.keys.locked() as key, Session(s.engine) as db, db.begin():
            app = db.get(Installation, 1)
            db.delete(db.get(Action, registration_id(db, 1, target.id, target.sha256)))
            app.previous_package_id = None
            db.flush()
            pin = SimpleNamespace(module_package_id=target.id, version='1.0.7', sha256=target.sha256)
            marker = provenance.registration_id(db, 1)
            authority._save(db, key, 'action', Action(request_id=marker, installation_id=1),
                authority._envelope('action', marker, 1, 'connector_registered_not_started',
                    {'operation': 'connector_first_registration',
                     'binding': provenance._binding(db, key, 1, pin, target.package)}))
    approve(s)
    activate = s.base+'/packages/'+target.sha256+'/activate'
    if previously_activated:
        post(s, activate)
        post(s, s.base+'/'+s.module_id+'/disable')
    data = s.root/'application-owned.txt'
    data.write_text('retained business records')
    with Session(s.engine) as db:
        app = db.get(Installation, 1)
        retained = (app.instance_id, app.authority_incarnation, app.previous_package_id)
        marker = (provenance.registration_id(db, 1) if first_registration == 'connector'
                  else registration_id(db, 1, target.id, target.sha256))
        original_proof = tuple(db.execute(select(*Action.__table__.c).where(Action.request_id == marker)).one())
        device = db.scalar(select(routes.Device.device_id))
    before_calls = list(s.calls)
    # Returning to the originally approved empty selection must not revive its
    # old grant; every changed configuration gets a fresh execution epoch.
    for selected in ({'TARGET_DEVICE_ID': device}, {}, {'TARGET_DEVICE_ID': device}):
        post(s, s.base+'/packages/'+target.sha256+'/stage', stage_body(s, configuration=selected))
        assert s.calls == before_calls
        status = s.manager.inspect(1)
        assert status['review_available'] and not status['access_saved'] and not status['grant_effective']
        post(s, activate, status=409)
        assert s.calls == before_calls
        with Session(s.engine) as db:
            app = db.get(Installation, 1)
            assert app.configuration.get('TARGET_DEVICE_ID') == selected.get('TARGET_DEVICE_ID')
            assert app.status == 'disabled' and not app.enabled and app.active_version is None
            assert (app.instance_id, app.authority_incarnation, app.previous_package_id) == retained
            assert tuple(db.execute(select(*Action.__table__.c).where(Action.request_id == marker)).one()) == original_proof
    assert data.read_text() == 'retained business records'
    approve(s)
    post(s, activate)
    assert s.manager.inspect(1)['grant_effective'] and data.read_text() == 'retained business records'


def test_same_package_configuration_request_replay_is_historical_and_changed_payload_is_refused(staged):
    s = staged
    target = optional_candidate(s)
    with Session(s.engine) as db:
        device = db.scalar(select(routes.Device.device_id))
    path = s.base+'/packages/'+target.sha256+'/stage'
    body = stage_body(s, configuration={'TARGET_DEVICE_ID': device})
    first = post(s, path, body)
    with Session(s.engine) as db:
        before = tuple(db.scalars(select(Action.request_id).order_by(Action.request_id)))
        epoch = db.get(Installation, 1).authority_epoch
    replay = post(s, path, body)
    assert replay['historical'] and replay['replayed']
    assert {key: replay[key] for key in first} == first
    post(s, path, {**body, 'configuration': {}}, status=409)
    with Session(s.engine) as db:
        assert tuple(db.scalars(select(Action.request_id).order_by(Action.request_id))) == before
        assert db.get(Installation, 1).authority_epoch == epoch
    assert s.calls == []


@pytest.mark.parametrize('fault', ['missing', 'tampered', 'missing_transition'])
def test_same_package_configuration_never_repairs_missing_or_tampered_provenance(staged, fault):
    s = staged
    target = optional_candidate(s)
    path = s.base+'/packages/'+target.sha256+'/stage'
    if fault == 'missing_transition':
        with Session(s.engine) as db:
            device = db.scalar(select(routes.Device.device_id))
        post(s, path, stage_body(s, configuration={'TARGET_DEVICE_ID': device}))
    body = stage_body(s, configuration={})
    with Session(s.engine) as db, db.begin():
        marker = registration_id(db, 1, target.id, target.sha256)
        if fault == 'missing_transition':
            transitions = list(db.scalars(select(Action).where(Action.installation_id == 1)))
            for row in transitions:
                if json.loads(row.payload).get('state') == 'configuration_prepared_not_started':
                    db.delete(row)
        elif fault == 'missing':
            db.delete(db.get(Action, marker))
        else:
            db.get(Action, marker).payload = '{}'
    with Session(s.engine) as db:
        original = tuple(db.execute(select(*Installation.__table__.c)).one())
        proofs = tuple(db.execute(select(*Action.__table__.c).order_by(Action.request_id)))
    post(s, path, body, status=409)
    with Session(s.engine) as db:
        assert tuple(db.execute(select(*Installation.__table__.c)).one()) == original
        assert tuple(db.execute(select(*Action.__table__.c).order_by(Action.request_id))) == proofs
    assert s.calls == []


@pytest.mark.parametrize('fault', ['active', 'revision', 'artifact', 'nonadmin', 'revoked', 'blocked', 'device', 'bad_grant'])
def test_same_package_configuration_requires_current_actor_stopped_state_and_review(staged, fault):
    s = staged
    target = optional_candidate(s)
    approve(s)
    body = stage_body(s, configuration={})
    headers = s.headers
    if fault == 'revision': body['expected_revision'] = 'f'*32
    if fault == 'artifact': body['expected_artifact_sha256'] = 'f'*64
    if fault == 'nonadmin': headers = {'Authorization': 'Bearer '+s.user_token}
    if fault == 'device': body['configuration'] = {'TARGET_DEVICE_ID': 'dev_'+'f'*32}
    with Session(s.engine) as db, db.begin():
        if fault == 'active': db.execute(update(Installation).values(status='active', enabled=True))
        if fault == 'revoked': db.execute(update(UserSession).where(UserSession.id == 1).values(is_active=False))
        if fault == 'blocked': db.execute(update(User).where(User.id == 1).values(is_blocked=True))
        if fault == 'bad_grant': db.get(Grant, 1).payload = '{}'
    with Session(s.engine) as db:
        before = tuple(db.execute(select(*Installation.__table__.c)).one())
        proofs = tuple(db.execute(select(*Action.__table__.c).order_by(Action.request_id)))
    response = s.http.post(s.base+'/packages/'+target.sha256+'/stage', json=body, headers=headers)
    assert response.status_code in {401, 403, 409}, response.text
    with Session(s.engine) as db:
        assert tuple(db.execute(select(*Installation.__table__.c)).one()) == before
        assert tuple(db.execute(select(*Action.__table__.c).order_by(Action.request_id))) == proofs
    assert s.calls == []


@pytest.mark.parametrize('required', [True, False])
def test_declared_platform_support_is_checked_before_inert_staging(staged, required):
    s = staged
    def declaration(value):
        value['service']['sdk_version'] = '1.3'
        value['platform_requirements'] = [{'requirement_id':'future_feature',
            'operations':['future.not_implemented'], 'required':required}]
    target = add_version(s, '1.0.2', declaration)
    approve(s)
    post(s, s.base+'/'+s.module_id+'/disable')
    body = stage_body(s)
    with Session(s.engine) as db:
        original = tuple(db.execute(select(*Installation.__table__.c)).one())
        actions = tuple(db.scalars(select(Action.request_id)))
        grant = tuple(db.execute(select(*Grant.__table__.c)).one())
    before_calls = list(s.calls)
    url = s.base+'/packages/'+target.sha256
    result = s.http.post(url+'/stage', headers=s.headers, json=body)
    assert result.status_code == (409 if required else 200), result.text
    assert s.calls == before_calls
    if required:
        assert 'future_feature' in result.json()['detail']
        with Session(s.engine) as db:
            assert tuple(db.execute(select(*Installation.__table__.c)).one()) == original
            assert tuple(db.scalars(select(Action.request_id))) == actions
            assert tuple(db.execute(select(*Grant.__table__.c)).one()) == grant
    else:
        assert s.http.get(url+'/platform-requirements', headers=s.headers).json()['status'] == 'degraded'
        # Dependency metadata does not replace the ordinary fresh consent gate.
        post(s, url+'/activate', status=409)
        approve(s)
        post(s, url+'/activate')


@pytest.mark.parametrize('ui_app', ['administration_actions', None], indirect=True)
def test_update_and_return_to_previous_version_require_fresh_consent_and_keep_data(staged):
    s = staged
    data = s.root / 'application-owned.txt'; data.write_text('keep my records')
    with Session(s.engine) as db:
        initial = db.get(Installation, 1)
        identity_before = (initial.instance_id, initial.authority_incarnation, initial.configuration)
    approve(s)
    old = s.validated.sha256
    activate = lambda sha: s.base + '/packages/' + sha + '/activate'
    post(s, activate(old))
    assert s.manager.inspect(1)['grant_effective']
    post(s, s.base + '/' + s.module_id + '/disable')
    prior_calls = list(s.calls)
    body = stage_body(s)
    path = s.base + '/packages/' + s.target.sha256 + '/stage'
    prepared = post(s, path, body)
    assert prepared['execution'] == 'not_started' and prepared['permission_approval'] == 'required'
    assert s.calls == prior_calls and not s.manager.inspect(1)['grant_effective']
    replay = post(s, path, body)
    assert replay['historical'] and replay['replayed'] and s.calls == prior_calls
    post(s, activate(s.target.sha256), status=409)
    assert s.calls == prior_calls
    catalog = s.http.get(s.base, headers=s.headers).json()
    assert catalog[0]['package_sha256'] == s.target.sha256 and catalog[0]['active_version'] is None
    packages = s.http.get('/api/v1/modules/packages', headers=s.headers).json()
    assert next(package for package in packages if package['sha256'] == catalog[0]['package_sha256'])['version'] == s.target.package.manifest.version
    reviewed = approve(s)
    assert reviewed['artifact_sha256'] == s.target.sha256 and s.calls == prior_calls
    post(s, activate(s.target.sha256))
    assert s.manager.inspect(1)['grant_effective']
    with Session(s.engine) as db:
        current = db.get(Installation, 1)
        assert (current.instance_id, current.authority_incarnation, current.configuration) == identity_before
        assert current.previous_package_id == 1
    assert data.read_text() == 'keep my records'
    post(s, s.base + '/' + s.module_id + '/disable')
    post(s, s.base + '/packages/' + old + '/stage', stage_body(s))
    post(s, activate(old), status=409)  # Old consent cannot be resurrected by rollback.
    approve(s); post(s, activate(old))
    assert s.manager.inspect(1)['grant_effective'] and data.read_text() == 'keep my records'


@pytest.mark.parametrize('fault', ['active', 'revision', 'artifact', 'nonadmin', 'revoked', 'blocked', 'unapproved', 'bad_grant'])
def test_preparation_checks_current_actor_exact_package_and_grant(staged, fault):
    s = staged
    if fault != 'unapproved': approve(s)
    body = stage_body(s)
    headers = s.headers
    if fault == 'revision': body['expected_revision'] = 'f' * 32
    if fault == 'artifact': body['expected_artifact_sha256'] = 'f' * 64
    if fault == 'nonadmin': headers = {'Authorization': 'Bearer ' + s.user_token}
    with Session(s.engine) as db, db.begin():
        if fault == 'active': db.execute(update(Installation).values(status='active', enabled=True))
        if fault == 'revoked': db.execute(update(UserSession).where(UserSession.id == 1).values(is_active=False))
        if fault == 'blocked': db.execute(update(User).where(User.id == 1).values(is_blocked=True))
        if fault == 'bad_grant': db.get(Grant, 1).payload = '{}'
    response = s.http.post(s.base + '/packages/' + s.target.sha256 + '/stage', json=body, headers=headers)
    if fault == 'unapproved':
        assert response.status_code == 200, response.text
        approve(s)  # Inert preparation grants nothing but allows the new exact review.
    else:
        assert response.status_code in {401, 403, 409}, response.text
        with Session(s.engine) as db: assert db.get(Installation, 1).module_package_id == 1
    assert s.calls == []


def test_corrupt_inert_proof_is_never_accepted_or_repaired(staged):
    s = staged
    post(s, s.base + '/packages/' + s.target.sha256 + '/stage', stage_body(s))
    with Session(s.engine) as db, db.begin():
        marker = registration_id(db, 1, s.target.id, s.target.sha256)
        record = db.get(Action, marker)
        proof = json.loads(record.payload); proof['data']['binding']['sha256'] = 'f' * 64
        record.payload = json.dumps(proof)
    post(s, s.access + '/consent/preview', {'request_id': identity()}, status=409)
    post(s, s.base + '/packages/' + s.target.sha256 + '/activate', status=409)
    assert not s.manager.inspect(1)['review_available'] and s.calls == []


@pytest.mark.parametrize('claim', ['task', 'historical_job'])
def test_unknown_execution_prevents_preparation_without_losing_its_evidence(staged, claim):
    s = staged
    with Session(s.engine) as db, db.begin():
        app = db.get(Installation, 1)
        now = datetime.now(UTC)
        if claim == 'historical_job':
            db.add(ApplicationJobState(application_installation_id=1, job_id='historical',
                next_run_at=now, lease_token=identity()))
        else:
            db.add(ApplicationTaskRun(task_run_id='task_' + identity(), installation_id=1,
                package_id=1, incarnation=app.authority_incarnation, authority_epoch=app.authority_epoch,
                grant_revision=1, task_id='historical', request_id=identity(), request_hash='a'*64,
                state='unknown', payload={}, due_at=now, not_after=now+timedelta(seconds=10)))
    post(s, s.base + '/packages/' + s.target.sha256 + '/stage', stage_body(s), status=409)
    with Session(s.engine) as db:
        assert db.get(Installation, 1).module_package_id == 1
        if claim == 'task': assert db.scalar(select(ApplicationTaskRun.state)) == 'unknown'
        else: assert db.scalar(select(ApplicationJobState.lease_token)) is not None
    assert s.calls == []


def test_relational_candidate_keeps_its_dedicated_prepared_migration_boundary(staged):
    from packages.protocol.tests.test_application_relational_storage import relational_request
    s = staged
    def change(definition):
        definition['service']['sdk_version'] = '1.3'
        definition['storage']['relational'] = relational_request()
    candidate = add_version(s, '1.0.2', change)
    post(s, s.base + '/packages/' + candidate.sha256 + '/stage', stage_body(s), status=409)
    with Session(s.engine) as db: assert db.get(Installation, 1).module_package_id == 1
    assert s.calls == []


@pytest.mark.parametrize('change', ['abandoned_update', 'revoked_approval'])
def test_prepared_package_never_reuses_a_previous_or_revoked_consent(staged, change):
    s = staged
    approve(s)
    old = s.validated.sha256
    activate = lambda sha: s.base + '/packages/' + sha + '/activate'
    post(s, activate(old))
    post(s, s.base + '/' + s.module_id + '/disable')
    post(s, s.base + '/packages/' + s.target.sha256 + '/stage', stage_body(s))
    if change == 'abandoned_update':
        # No consent was saved for the new version. Returning to old bytes must
        # not revive the still-sealed old grant or its native-code approval.
        post(s, s.base + '/packages/' + old + '/stage', stage_body(s))
        selected = old
    else:
        approve(s)
        revision = s.manager.inspect(1)['grant_record_revision']
        post(s, s.access + '/revoke', {'request_id': identity(), 'expected_revision': revision})
        selected = s.target.sha256
    prior_calls = list(s.calls)
    post(s, activate(selected), status=409)
    assert s.calls == prior_calls
    approve(s); post(s, activate(selected))
    assert s.manager.inspect(1)['grant_effective']
