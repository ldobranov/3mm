"""Real sealed event grants, installed ZIPs and gateway admission; no live hardware."""

from datetime import UTC, datetime
import io
import json
import os
import zipfile

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from backend.db.base import Base
from backend.db.device import Device, DeviceCredential, DeviceEvent, DeviceCapabilityProvider, DeviceRuntimeFeatures
from backend.db.module import ApplicationEventCursor, ApplicationEventDelivery, ApplicationExtensionInstallation as Installation, ModulePackage, ModuleInstallation
from backend.services import application_events as broker, application_extensions as gateway
from backend.services import application_authority_management as authority
from backend.services.application_authority_context import AuthoritySelectionV1, review_authority_context
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_authority_management import (
    installed as core_installed, source_subject, source_installed, native, decide, identity,
)
from backend.tests.test_application_authority_sources import DEVICE, PRIVATE
from backend.tests.test_application_events import application_definition
from backend.config import ApplicationRuntimeSettings
from three_mm_runtime.application_transport import ApplicationTransportError


pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Real POSIX review key ownership/locking required')
SCOPES = ['command:pulse', 'connector:business_api', 'event:changes']


def replace_package(s, definition, manifest):
    stream = io.BytesIO()
    with zipfile.ZipFile(s.archive) as previous, zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('application-extension.json', json.dumps(definition))
        artifact = definition['service']['artifact']
        archive.writestr(artifact, previous.read(artifact))
    blob = stream.getvalue()
    s.validated = validate_module_package(blob)
    s.archive = s.root / 'modules' / (s.validated.sha256 + '.zip')
    s.archive.write_bytes(blob)
    with s.engine.begin() as db:
        db.execute(update(ModulePackage).where(ModulePackage.id == 1).values(
            sha256=s.validated.sha256, size_bytes=len(blob), manifest=manifest, file_path=str(s.archive)))


@pytest.fixture
def events(core_installed, tmp_path, monkeypatch):
    s = core_installed
    manifest = s.validated.manifest.model_dump(mode='json')
    manifest['permissions'].append('events.consume')
    definition = s.validated.application_extension.model_dump(mode='json')
    definition['operations'].append(application_definition().operations[1].model_dump(mode='json'))
    definition['event_subscriptions'] = [{
        'subscription_id': 'changes', 'event_type': 'device.changed.v1',
        'capability_id': 'gpio.digital.control', 'handler_operation_id': 'process_scan',
        'device_scope_config_key': 'TARGET_DEVICE_ID', 'max_backlog': 2,
    }]
    replace_package(s, definition, manifest)
    Base.metadata.create_all(s.engine, tables=[DeviceEvent.__table__, ApplicationEventCursor.__table__, ApplicationEventDelivery.__table__])
    keys = tmp_path / 'transport-keys'
    keys.mkdir()
    (keys / ('a' * 24 + '.key')).write_bytes(b's' * 32)
    s.settings = ApplicationRuntimeSettings(key_root=keys)
    s.calls = []

    class Client:
        def __init__(self, *_args):
            pass

        def invoke(self, operation_id, payload, context):
            # Independent connection observes the durable attempt. A new key
            # lease succeeds: neither Core DB nor private-key lock spans IPC.
            with s.keys.locked(), Session(s.engine) as observer:
                delivery = observer.scalar(select(ApplicationEventDelivery).where(
                    ApplicationEventDelivery.subscription_id == 'changes'))
                assert delivery.attempts >= 1 and delivery.status == 'pending'
            s.calls.append((operation_id, payload, context))
            return {}

    monkeypatch.setattr(gateway, 'ApplicationServiceClient', Client)
    return s


def review(s, n=None, scopes=None):
    return s.manager.create_review(1, actor_token=s.token, request_id=identity(),
        native_review_id=(n or native(s))['native_review_id'], scopes=SCOPES if scopes is None else scopes)


def activate(s):
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status='disabled'))
    n = native(s)
    decide(s, decide(s, review(s, n), 'approve'), 'apply')
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=True, status='active', authority_epoch=identity()))
    return decide(s, decide(s, review(s, n), 'approve'), 'apply')


def event(s, *, event_type='device.changed.v1', capability='gpio.digital.control', device=1):
    with Session(s.engine) as db:
        row = DeviceEvent(device_id=device, event_id='evt_' + identity(), occurred_at=datetime.now(UTC),
            event_type=event_type, payload={'capability_id': capability, 'value': True})
        db.add(row)
        db.commit()
        return row.id


def deliver(s, identifier):
    with Session(s.engine) as db:
        broker.enqueue_application_event(db, db.get(DeviceEvent, identifier), s.settings)


def retry(s):
    with Session(s.engine) as db:
        broker.retry_application_events(db, s.settings)


def test_event_review_is_exact_redacted_and_approval_is_not_apply(events):
    s = events
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status='disabled'))
    plan = review(s)
    resource = plan['resources']['events'][0]
    assert resource['source_device_id'] == DEVICE
    assert resource['declaration']['event_type'] == 'device.changed.v1'
    assert resource['handler']['operation_id'] == 'process_scan'
    assert resource['declaration']['max_backlog'] == 2
    assert PRIVATE not in json.dumps(plan)
    approved = decide(s, plan, 'approve')
    assert not s.manager.inspect(1)['grant_effective']
    decide(s, approved, 'apply')
    assert s.manager.inspect(1)['scopes'] == sorted(SCOPES)
    assert not s.manager.inspect(1)['grant_effective']  # Still stopped.


def test_event_scope_admin_api_requires_real_admin_and_separate_apply(events):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routes.application_authority import router
    from backend.utils.db_utils import get_db
    s = events
    app = FastAPI()
    app.include_router(router)
    def database():
        with Session(s.engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status='disabled'))
    n = native(s)
    body = {'request_id': identity(), 'native_review_id': n['native_review_id'], 'scopes': SCOPES}
    base = '/api/v1/application-extensions/' + s.validated.manifest.module_id + '/authority'
    headers = {'Authorization': 'Bearer ' + s.token}
    with TestClient(app) as client:
        assert client.post(base + '/reviews', json=body).status_code == 401
        assert client.post(base + '/reviews', json=body,
            headers={'Authorization': 'Bearer ' + s.user_token}).status_code == 403
        assert client.post(base + '/reviews', json={**body, 'source_device_id': DEVICE},
            headers=headers).status_code == 422  # The caller cannot author resolved resources.
        response = client.post(base + '/reviews', json=body, headers=headers)
        assert response.status_code == 200, response.text
        plan = response.json()
        assert response.headers['cache-control'] == 'no-store'
        assert plan['resources']['events'][0]['source_device_id'] == DEVICE
        assert PRIVATE not in response.text
        response = client.post(base + '/reviews/' + plan['plan_id'] + '/approve', headers=headers,
            json={'request_id': identity(), 'expected_revision': plan['revision'], 'fingerprint': plan['fingerprint']})
        assert response.status_code == 200, response.text
        assert s.manager.inspect(1)['grant_state'] != 'active'
        plan = response.json()
        response = client.post(base + '/reviews/' + plan['plan_id'] + '/apply', headers=headers,
            json={'request_id': identity(), 'expected_revision': plan['revision'], 'fingerprint': plan['fingerprint']})
        assert response.status_code == 200, response.text
        assert s.manager.inspect(1)['grant_state'] == 'active'
        assert not s.manager.inspect(1)['grant_effective']  # Disabled is never admission.


@pytest.mark.parametrize('scopes', [SCOPES[:-1], SCOPES + ['event:other'], SCOPES + ['event:changes']])
def test_required_event_scope_cannot_be_omitted_widened_or_duplicated(events, scopes):
    with pytest.raises((authority.AuthorityManagementError, ValueError)):
        review(events, scopes=scopes)


@pytest.mark.parametrize('provider,role', [('native', 'standalone'), ('embedded_firmware', 'hub'), ('agent_module', 'node')])
def test_applied_event_grant_delivers_once_via_real_gateway_for_generic_providers(events, provider, role):
    s = events
    with s.engine.begin() as db:
        db.execute(update(Device).values(role=role))
    with Session(s.engine) as db, db.begin():
        if provider == 'agent_module':
            registration = db.scalar(select(DeviceCapabilityProvider)).capabilities[0]
            db.execute(delete(DeviceCapabilityProvider))
            db.add(ModulePackage(id=2, module_id='org.example.source', version='1.0.0',
                sha256='b' * 64, size_bytes=1, file_path='unused', manifest={}, registrations=[{
                    'kind': 'capability', 'registration_id': registration['capability_id'],
                    'metadata': registration['metadata'], 'contract': registration['contract'],
                }]))
            db.flush()
            db.add(ModuleInstallation(device_id=1, module_package_id=2, module_id='org.example.source',
                installed_version='1.0.0', desired_version='1.0.0', enabled=True, status='succeeded'))
        else:
            db.execute(update(DeviceCapabilityProvider).values(provider_type=provider))
    activate(s)
    identifier = event(s)
    deliver(s, identifier)
    deliver(s, identifier)
    retry(s)
    assert len(s.calls) == 1
    assert s.calls[0][0] == 'process_scan' and s.calls[0][1]['device_id'] == DEVICE
    assert s.calls[0][2]['idempotency_key'] == s.calls[0][1]['event_id']
    with Session(s.engine) as db:
        row = db.scalar(select(ApplicationEventDelivery))
        assert row.authority_epoch == db.get(Installation, 1).authority_epoch
        assert row.status == 'acknowledged' and row.attempts == 1
        assert db.scalar(select(ApplicationEventCursor)).acknowledged_count == 1


@pytest.mark.parametrize('event_type,capability', [('other.event.v1', 'gpio.digital.control'), ('device.changed.v1', 'other.capability.v1')])
def test_grant_does_not_authorize_other_event_or_capability(events, event_type, capability):
    activate(events)
    deliver(events, event(events, event_type=event_type, capability=capability))
    assert not events.calls
    with Session(events.engine) as db:
        assert db.scalar(select(ApplicationEventDelivery)) is None


def test_grant_does_not_authorize_same_event_from_another_device(events):
    s = events
    activate(s)
    with Session(s.engine) as db, db.begin():
        db.add(Device(id=2, device_id='dev_' + 'f' * 32, role='node', protocol_version='1.0', approved_at=datetime.now(UTC)))
    deliver(s, event(s, device=2))
    assert not s.calls
    with Session(s.engine) as db:
        assert db.scalar(select(ApplicationEventDelivery)) is None


@pytest.mark.parametrize('change', ['revoke', 'device', 'credential', 'provider', 'runtime', 'configuration', 'artifact', 'missing_provider'])
def test_event_grant_denies_after_actual_source_or_authority_drift(events, change):
    s = events
    activate(s)
    if change == 'revoke':
        s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=s.manager.inspect(1)['grant_record_revision'])
    else:
        with s.engine.begin() as db:
            if change == 'device':
                db.execute(update(Device).values(revoked_at=datetime.now(UTC)))
            elif change == 'credential':
                db.execute(update(DeviceCredential).values(revoked_at=datetime.now(UTC)))
            elif change == 'provider':
                db.execute(update(DeviceCapabilityProvider).values(revision=99))
            elif change == 'runtime':
                db.execute(update(DeviceRuntimeFeatures).values(revision=99))
            elif change == 'configuration':
                db.execute(update(Installation).values(configuration={**s.configuration, 'PRIVATE_NOTE': 'changed'}))
            elif change == 'artifact':
                db.execute(update(ModulePackage).values(sha256='f' * 64))
            else:
                db.execute(delete(DeviceCapabilityProvider))
    deliver(s, event(s))
    assert not s.calls
    with Session(s.engine) as db:
        assert db.scalar(select(ApplicationEventDelivery)) is None


def test_revoke_after_gateway_preflight_denies_dispatch_without_consuming_attempt(events, monkeypatch):
    s = events
    activate(s)
    original = gateway.load_application_definition
    def preflight(package):
        definition = original(package)
        s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=s.manager.inspect(1)['grant_record_revision'])
        return definition
    monkeypatch.setattr(gateway, 'load_application_definition', preflight)
    deliver(s, event(s))
    assert not s.calls
    with Session(s.engine) as db:
        row = db.scalar(select(ApplicationEventDelivery))
        assert row.status == 'dead_letter' and row.attempts == 0
        assert db.scalar(select(ApplicationEventCursor)).dead_letter_count == 1


def test_lost_response_and_fresh_reapproval_cannot_replay_old_backlog(events, monkeypatch):
    s = events
    activate(s)
    class Client:
        def __init__(self, *_args): pass
        def invoke(self, *args):
            s.calls.append(args)
            raise ApplicationTransportError('lost response')
    monkeypatch.setattr(gateway, 'ApplicationServiceClient', Client)
    deliver(s, event(s))
    assert len(s.calls) == 1
    status = s.manager.inspect(1)
    s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=status['grant_record_revision'])
    decide(s, decide(s, review(s), 'approve'), 'apply')
    assert s.manager.inspect(1)['grant_effective']
    retry(s)
    retry(s)
    assert len(s.calls) == 1
    with Session(s.engine) as db:
        row = db.scalar(select(ApplicationEventDelivery))
        assert row.status == 'dead_letter' and row.attempts == 1


def test_legacy_backlog_cannot_acquire_event_rights_by_adoption(events):
    s = events
    identifier = event(s)
    with Session(s.engine) as db:
        db.add(ApplicationEventDelivery(application_installation_id=1, subscription_id='changes',
            device_event_id=identifier, status='pending', attempts=0))
        db.commit()
    activate(s)
    retry(s)
    assert not s.calls
    with Session(s.engine) as db:
        assert db.scalar(select(ApplicationEventDelivery)).status == 'dead_letter'


def test_v2_context_cannot_downgrade_selection_to_v1(events):
    from backend.db.application_authority_grant import ApplicationAuthorityPlan
    s = events
    p = review(s)
    with Session(s.engine) as db:
        context = json.loads(db.get(ApplicationAuthorityPlan, p['plan_id']).payload)['data']['context']
    assert context['context_version'] == 2
    result = review_authority_context(context, AuthoritySelectionV1(selection_version=1, scopes=tuple(SCOPES[:-1])), now_ms=context['issued_at_ms'])
    assert not result.reviewable and result.issues[0].reason == 'invalid_selection'
