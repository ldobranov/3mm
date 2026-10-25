"""Same app: human UI access -> signed service IPC -> scoped SDK command.

Real Linux files/keys/DB guards and two signed Unix boundaries. The in-test
service uses only the public SDK; no live VM, helper, Agent or hardware changes.
"""
from three_mm_platform_wire import COMPATIBILITY_ACTIONS

import json
import os
from pathlib import Path
import socketserver
import sys
import tempfile
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

import backend.database
from backend.config import ApplicationRuntimeSettings
from backend.db.base import Base
from backend.db.device import DeviceCommand
from backend.db.application_authority_grant import ApplicationAuthorityGrant
from backend.db.module import ApplicationExtensionInstallation as Installation, ApplicationPermissionGrant, ModulePackage
from backend.routes import application_extensions as routes, modules
from backend.services import application_authority_management as authority, compiled_ui
from backend.services.application_authority_policy import evaluate_authority_policy
from backend.services.application_platform import ApplicationPlatformServer
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_authority_management import (
    identity, installed as managed_installed, source_subject, source_installed, decide, command,
)
from backend.services.application_commands import submit_command
from backend.tests.test_application_authority_policy import inputs
from backend.tests.test_application_access import fake_compiler
from backend.tests.test_module_packages import application_definition, application_package
from backend.utils.db_utils import get_db
from three_mm_application_sdk import ApplicationPlatformClient
from three_mm_runtime.application_transport import read_message, send_message, sign_message, verify_message


def test_ui_policy_needs_both_build_pin_and_separate_reviewed_profile():
    subject, evidence = inputs()
    subject['has_executable_frontend'] = True
    subject['binding']['candidate']['built_ui_sha256'] = 'a' * 64
    evidence['binding'] = subject['binding']
    assert not evaluate_authority_policy(subject, evidence).policy_resolved
    evidence['execution_profile'] = 'supervised_reviewed_native_ui_v1'
    assert evaluate_authority_policy(subject, evidence).policy_resolved
    subject['binding']['candidate']['built_ui_sha256'] = None
    assert not evaluate_authority_policy(subject, evidence).policy_resolved


posix = pytest.mark.skipif(os.name != 'posix', reason='Real Linux protected keys and signed Unix IPC')


@pytest.fixture
def ui_app(managed_installed, monkeypatch):
    s = managed_installed
    manifest = s.validated.manifest.model_dump(mode='json')
    manifest.update(runtimes=['core', 'ui'], entrypoints={'core': 'application-extension.json', 'ui': 'compiled-ui.json'})
    definition = s.validated.application_extension.model_dump(mode='json')
    original = application_definition()
    definition.update(routes=original['routes'], permissions=original['permissions'])
    definition['operations'].append({'operation_id': 'pulse_ui', 'kind': 'command',
        'audiences': ['operator'], 'required_permission': 'records_manage', 'idempotency': 'required'})
    blob = application_package(definition=definition, manifest_value=manifest)
    s.validated = validate_module_package(blob)
    s.archive = s.root / 'modules' / (s.validated.sha256 + '.zip')
    s.archive.write_bytes(blob)
    Base.metadata.create_all(s.engine)
    with s.engine.begin() as db:
        db.execute(update(ModulePackage).values(manifest=manifest, sha256=s.validated.sha256,
            size_bytes=len(blob), file_path=str(s.archive)))
        db.execute(update(Installation).values(enabled=False, status='disabled'))
    monkeypatch.setenv('COMPILED_UI_ARTIFACTS_DIR', str(s.root / 'compiled'))

    def compiler(command, **kwargs):
        result = fake_compiler(command, **kwargs)
        (Path(command[3]) / 'build-toolchain.json').write_text(json.dumps(
            {'node': '24.19.0', 'vite': '6.4.3', 'vue_plugin': '5.2.4'}))
        return result

    monkeypatch.setattr(compiled_ui.subprocess, 'run', compiler)
    s.build = compiled_ui.compile_ui_package(blob, s.validated)
    return s


def native(s, **overrides):
    return s.manager.record_native_review(1, actor_token=s.token, request_id=identity(),
        artifact_sha256=s.validated.sha256, review_document_sha256='b' * 64,
        native_code_review_completed=True, accepts_native_host_risk=True,
        **{'accepts_same_origin_ui_risk': True, 'built_ui_sha256': s.build.built_ui_sha256, **overrides})


def grant(s, n):
    plan = s.manager.create_review(1, actor_token=s.token, request_id=identity(),
        native_review_id=n['native_review_id'], scopes=['command:pulse', 'connector:business_api'])
    return decide(s, decide(s, plan, 'approve'), 'apply')


def adopt(s):
    n = native(s)
    grant(s, n)
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=True, status='active', authority_epoch=identity()))
    grant(s, n)
    assert s.manager.inspect(1)['grant_effective']
    return n


@posix
@pytest.mark.parametrize('fault', ['missing_ack', 'wrong_build', 'legacy_build', 'dirty_build'])
def test_no_ui_native_review_without_exact_build_and_explicit_risk(ui_app, fault):
    s = ui_app
    options = {}
    if fault == 'missing_ack':
        options.update(accepts_same_origin_ui_risk=False, built_ui_sha256=None)
    elif fault == 'wrong_build':
        options['built_ui_sha256'] = 'f' * 64
    elif fault == 'legacy_build':
        (s.build.path / 'build-provenance.json').unlink()
    else:
        (s.build.path / 'assets/operations.mjs').write_text('changed')
    with pytest.raises(authority.AuthorityManagementError):
        native(s, **options)
    assert not s.manager.inspect(1)['grant_effective']


@posix
@pytest.mark.parametrize('change', ['asset', 'coherent_rebuild', 'disable'])
def test_active_ui_grants_refuse_changed_build_or_lifecycle_before_effect(ui_app, change):
    s = ui_app
    adopt(s)
    if change == 'asset':
        (s.build.path / 'assets/operations.mjs').write_text('changed')
    elif change == 'coherent_rebuild':
        # Even another internally consistent build of the SAME source ZIP is
        # not the reviewed executable. Native/grant records remain untouched.
        metadata = s.build.path / 'build-provenance.json'
        value = json.loads(metadata.read_bytes())
        value['compiler_sha256'] = 'f' * 64
        metadata.write_text(json.dumps(value))
    else:
        with s.engine.begin() as db:
            db.execute(update(Installation).values(enabled=False, status='disabled'))
    with Session(s.engine) as db:
        with pytest.raises(ValueError):
            submit_command(db, db.get(Installation, 1), command())
        assert not db.scalars(select(DeviceCommand)).all()
        assert modules._compiled_catalog_item(db.get(ModulePackage, 1), db, 'Bearer ' + s.token) is None


@posix
def test_local_ui_inspection_and_explicit_code_review_never_approve_rights(ui_app, monkeypatch, capsys):
    from backend.services import application_authority_admin as admin
    s = ui_app
    monkeypatch.setattr(admin, 'configured_manager', lambda _engine: s.manager)
    monkeypatch.setattr(backend.database, 'engine', s.engine)
    monkeypatch.setattr(admin.getpass, 'getpass', lambda _prompt: s.token)
    monkeypatch.setattr(sys, 'argv', ['authority', 'inspect-ui-build', '--installation-id', '1'])
    admin.main()
    inspected = json.loads(capsys.readouterr().out)
    assert inspected['built_ui_sha256'] == s.build.built_ui_sha256
    assert inspected['permission_approval'] == 'not_evaluated'
    document = s.root / 'manual-review.md'
    document.write_text('Fixture code reviewed; same-origin native risk explicitly accepted.')
    arguments = ['authority', 'native-review', '--installation-id', '1',
        '--artifact-sha256', s.validated.sha256, '--review-document', str(document),
        '--code-review-completed', '--accept-native-host-risk']
    monkeypatch.setattr(sys, 'argv', arguments)
    with pytest.raises(SystemExit, match='no permission fallback'):
        admin.main()
    monkeypatch.setattr(sys, 'argv', arguments + ['--accept-same-origin-ui-risk',
        '--built-ui-sha256', inspected['built_ui_sha256']])
    admin.main()
    recorded = json.loads(capsys.readouterr().out)
    assert recorded['native_review_id']
    assert recorded['permission_approval'] == 'not_evaluated'
    with Session(s.engine) as db:
        assert not db.scalars(select(ApplicationAuthorityGrant)).all()


@posix
def test_human_ui_and_service_resource_grants_are_independent_over_actual_ipc(ui_app, monkeypatch):
    s = ui_app
    n = adopt(s)
    monkeypatch.setattr(backend.database, 'SessionLocal', sessionmaker(s.engine))
    calls = []
    errors = []
    with tempfile.TemporaryDirectory(prefix='ui-grant-', dir='/tmp') as temporary:
        root = Path(temporary)
        secret = b's' * 32
        (root / ('a' * 24 + '.key')).write_bytes(secret)
        platform = ApplicationPlatformServer(root / 'p.sock', root, group='missing-test-group', allowed_actions=COMPATIBILITY_ACTIONS)
        platform.start()
        sdk = ApplicationPlatformClient(platform.socket_path, 'a' * 24, secret)

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                request = verify_message(read_message(self.request), secret)
                calls.append(request)
                try:
                    sdk.submit_command('pulse', request_id=request['context']['idempotency_key'],
                        arguments={'channel': 'output.1', 'duration_ms': 50}, ttl_seconds=5)
                    reply = {'ok': True, 'result': {}}
                except Exception as error:
                    errors.append(repr(error))
                    reply = {'ok': False, 'error': 'Scoped resource refused'}
                send_message(self.request, sign_message({'version': 1, 'request_id': request['request_id'],
                    'timestamp': int(time.time()), **reply}, secret))

        server = socketserver.ThreadingUnixStreamServer(str(root / 's.sock'), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        with s.engine.begin() as db:
            db.execute(update(Installation).values(socket_path=str(root / 's.sock')))
        settings = ApplicationRuntimeSettings(root=root, key_root=root, helper_socket=root / 'unused.sock')
        from backend.tests.response_helpers import install_response_transport
        install_response_transport(monkeypatch)
        monkeypatch.setattr(routes, 'get_settings', lambda: type('Settings', (), {'applications': settings})())
        app = FastAPI()
        app.include_router(routes.router)
        app.include_router(modules.router)

        def session():
            with Session(s.engine) as db:
                yield db

        app.dependency_overrides[get_db] = session
        binding = {'host_version': 1, 'entrypoint_id': 'operations', 'artifact_sha256': s.validated.sha256,
            'built_ui_sha256': s.build.built_ui_sha256}
        base = '/api/v1/application-extensions/' + s.validated.manifest.module_id
        info = base + '/ui-host/operations?artifact_sha256=' + s.validated.sha256 + '&built_ui_sha256=' + s.build.built_ui_sha256
        auth = {'Authorization': 'Bearer ' + s.user_token}

        def invoke(client, key, context=None):
            return client.post(base + '/operator/operations/pulse_ui', headers=auth,
                json={'payload': {}, 'idempotency_key': key, 'ui_context': context or binding})

        try:
            with TestClient(app) as client:
                # Resource rights cannot supply missing human UI rights.
                assert client.get(info, headers=auth).status_code == 403
                assert invoke(client, 'ui-denied-001').status_code == 403
                assert not calls
                with Session(s.engine) as db, db.begin():
                    db.add(ApplicationPermissionGrant(application_installation_id=1, user_id=2, permission_id='records_manage'))
                catalog = client.get('/api/v1/modules/compiled-ui/catalog', headers=auth)
                assert catalog.status_code == 200, catalog.text
                item = catalog.json()['items'][0]
                assert item['built_ui_sha256'] == s.build.built_ui_sha256
                asset_url = item['entrypoints'][0]['asset_url']
                assert '/build/' + s.build.built_ui_sha256 + '/' in asset_url
                assert client.get(asset_url).status_code == 200
                assert client.get(info, headers=auth).status_code == 200
                result = invoke(client, 'ui-test-0001')
                assert result.status_code == 200, (result.text, errors)
                assert invoke(client, 'ui-stale-001', {**binding, 'built_ui_sha256': 'f' * 64}).status_code == 409
                assert len(calls) == 1
                assert 'ui_context' not in calls[0]['context']
                with Session(s.engine) as db:
                    assert len(db.scalars(select(DeviceCommand)).all()) == 1
                status = s.manager.inspect(1)
                s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=status['grant_record_revision'])
                # Native UI remains reviewed, but human access cannot restore
                # revoked SERVICE resource grants. Signed SDK denies the effect.
                assert client.get(info, headers=auth).status_code == 200
                assert invoke(client, 'ui-revoked-1').status_code == 409
                assert len(calls) == 2
                with Session(s.engine) as db:
                    assert len(db.scalars(select(DeviceCommand)).all()) == 1
                grant(s, n)
                assert s.manager.inspect(1)['grant_effective']
                with s.engine.begin() as db:
                    db.execute(delete(ApplicationPermissionGrant))
                assert invoke(client, 'ui-user-lost').status_code == 403
                assert len(calls) == 2
                # Local native review revocation blocks code even for Core admin.
                s.manager.revoke_native_review(1, actor_token=s.token, request_id=identity(),
                    native_review_id=n['native_review_id'], expected_revision=n['native_revision'])
                assert client.get(asset_url).status_code == 404
                assert client.get('/api/v1/modules/compiled-ui/catalog', headers={'Authorization': 'Bearer ' + s.token}).json()['items'] == []
                assert len(calls) == 2
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
            platform.stop()
