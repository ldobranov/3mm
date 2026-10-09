"""Real installed publication grants and signed SDK transport, not live data."""

from datetime import UTC, datetime
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import threading
import zipfile

import pytest
from sqlalchemy import select, update, func
from sqlalchemy.orm import Session, sessionmaker

import backend.database
from backend.db.base import Base
from backend.db.authority import CoreAuthorityGuard
from backend.db.device import DeviceEvent, Device
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage, ApplicationEventDelivery
from backend.services import application_authority_management as authority
from backend.services.application_event_publication import publish_application_event
from backend.services.application_platform import ApplicationPlatformServer
from backend.services.device_protocol import DeviceOperations
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_authority_management import (
    installed as core_installed, source_subject, source_installed, native, decide, identity,
)
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError
from three_mm_protocol import DeviceEventV1
from three_mm_protocol.transport import DeviceProtocolError


pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Real POSIX review key ownership and socket required')
SCOPES = ['command:pulse', 'connector:business_api', 'publication:record_changed']


@pytest.fixture
def publications(core_installed, monkeypatch, tmp_path):
    s = core_installed
    manifest = s.validated.manifest.model_dump(mode='json')
    manifest['permissions'].append('events.publish')
    manifest['capabilities']['provides'] = ['example.record.changed.v1']
    definition = s.validated.application_extension.model_dump(mode='json')
    definition['operations'].append({'operation_id': 'record', 'kind': 'command',
        'audiences': ['internal'], 'idempotency': 'required', 'emitted_events': ['example.record.changed.v1']})
    s.contract = {'publication_contract_version': 1, 'module_id': definition['module_id'],
        'version': definition['version'], 'service_artifact_sha256': definition['service']['artifact_sha256'],
        'publications': [{'publication_id': 'record_changed', 'operation_id': 'record',
            'event_type': 'example.record.changed.v1', 'max_payload_bytes': 128,
            'payload_schema': {'type': 'object', 'properties': {'value': {'type': 'number', 'minimum': 0, 'maximum': 10}},
                'required': ['value'], 'additionalProperties': False}}]}
    stream = io.BytesIO()
    with zipfile.ZipFile(s.archive) as previous, zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('application-extension.json', json.dumps(definition))
        archive.writestr('application-event-publications.json', json.dumps(s.contract))
        artifact = definition['service']['artifact']
        archive.writestr(artifact, previous.read(artifact))
    s.validated = validate_module_package(stream.getvalue())
    s.archive = s.root / 'modules' / (s.validated.sha256 + '.zip')
    s.archive.write_bytes(stream.getvalue())
    with s.engine.begin() as db:
        db.execute(update(ModulePackage).where(ModulePackage.id == 1).values(sha256=s.validated.sha256,
            manifest=manifest, size_bytes=len(stream.getvalue()), file_path=str(s.archive)))
    Base.metadata.create_all(s.engine, tables=[DeviceEvent.__table__, ApplicationEventDelivery.__table__])
    monkeypatch.setattr(backend.database, 'SessionLocal', sessionmaker(bind=s.engine))
    s.transport_keys = tmp_path / 'transport-keys'
    s.transport_keys.mkdir()
    (s.transport_keys / ('a' * 24 + '.key')).write_bytes(b's' * 32)
    return s


def review(s, n=None, scopes=SCOPES):
    return s.manager.create_review(1, actor_token=s.token, request_id=identity(),
        native_review_id=(n or native(s))['native_review_id'], scopes=scopes)


def activate(s):
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status='disabled'))
    n = native(s)
    decide(s, decide(s, review(s, n), 'approve'), 'apply')
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=True, status='active', authority_epoch=identity()))
    return decide(s, decide(s, review(s, n), 'approve'), 'apply')


def request(**changes):
    return {'publication_request_version': 1, 'event_id': 'evt_' + identity(),
        'publication_id': 'record_changed', 'payload': {'value': 1},
        'occurred_at': datetime.now(UTC).isoformat(), **changes}


def publish(s, body, installation_id=1):
    with Session(s.engine) as db:
        return publish_application_event(db, db.get(Installation, installation_id), body)


def count(s):
    with Session(s.engine) as db:
        return db.scalar(select(func.count()).select_from(DeviceEvent))


def test_review_binds_exact_schema_wheel_operation_and_approve_is_not_apply(publications):
    s = publications
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status='disabled'))
    plan = review(s)
    declaration = plan['resources']['publications'][0]
    assert declaration['declaration'] == s.contract['publications'][0]
    assert declaration['operation']['operation_id'] == 'record'
    assert declaration['service_artifact_sha256'] == s.contract['service_artifact_sha256']
    assert plan['scopes'] == SCOPES
    approved = decide(s, plan, 'approve')
    with pytest.raises(ValueError):
        publish(s, request())
    assert count(s) == 0
    decide(s, approved, 'apply')
    with pytest.raises(ValueError):
        publish(s, request())  # Applied but disabled.


@pytest.mark.parametrize('scopes', [SCOPES[:-1], SCOPES + ['publication:other'], SCOPES * 2])
def test_publication_scope_cannot_be_omitted_widened_or_duplicated(publications, scopes):
    with pytest.raises((authority.AuthorityManagementError, ValueError)):
        review(publications, scopes=scopes)


@pytest.mark.parametrize('role', ['standalone', 'hub'])
def test_one_common_journal_owned_receipt_and_no_device_or_consumer_inference(publications, role):
    s = publications
    with s.engine.begin() as db:
        db.execute(update(Device).values(role=role))
    activate(s)
    body = request()
    receipt = publish(s, body)
    assert publish(s, body) == receipt
    assert count(s) == 1
    with Session(s.engine) as db:
        row = db.scalar(select(DeviceEvent))
        assert row.producer_kind == 'application' and row.device_id is None
        assert receipt['producer']['application_installation_id'] == '1'
        assert row.authority_epoch == db.get(Installation, 1).authority_epoch
        assert db.scalar(select(func.count()).select_from(ApplicationEventDelivery)) == 0
        from backend.services.application_events import enqueue_application_event
        from backend.config import ApplicationRuntimeSettings
        enqueue_application_event(db, row, ApplicationRuntimeSettings())
        assert db.scalar(select(func.count()).select_from(ApplicationEventDelivery)) == 0


@pytest.mark.parametrize('changes', [
    {'publication_id': 'unknown'}, {'payload': {'value': 11}},
    {'payload': {'value': True}}, {'payload': {'value': 1, 'foreign': 'secret'}},
    {'producer': {'kind': 'device'}}, {'event_type': 'core.audit'},
    {'operation_id': 'record'}, {'payload': {'value': 'x' * 70000}},
])
def test_bounded_declared_only_requests_fail_without_durable_ack(publications, changes):
    s = publications
    activate(s)
    with pytest.raises(ValueError):
        publish(s, request(**changes))
    assert count(s) == 0


def test_typed_changed_content_foreign_owner_device_id_and_reincarnation_conflict(publications):
    s = publications
    activate(s)
    body = request()
    publish(s, body)
    for changes in ({'payload': {'value': 1.0}}, {'publication_id': 'other'},
            {'occurred_at': datetime.now(UTC).isoformat()}):
        with pytest.raises(ValueError, match='different owner or content'):
            publish(s, {**body, **changes})
    with Session(s.engine) as db, db.begin():
        db.add(Installation(id=2, module_id='org.example.foreign', module_package_id=1,
            instance_id='b' * 24, active_version='1.0.0', status='disabled', enabled=False, socket_path='unused'))
    with pytest.raises(ValueError, match='different owner or content'):
        publish(s, body, 2)
    with Session(s.engine) as db:
        device = db.get(Device, 1)
        with pytest.raises(DeviceProtocolError):
            DeviceOperations(db, device).event(DeviceEventV1(event_id=body['event_id'], device_id=device.device_id,
                event_type='example.record.changed.v1', payload=body['payload'], occurred_at=body['occurred_at']))
    with s.engine.begin() as db:
        db.execute(update(Installation).where(Installation.id == 1).values(authority_incarnation=identity()))
    with pytest.raises(ValueError):
        publish(s, body)
    assert count(s) == 1


def test_original_receipt_survives_revoke_disable_changed_archive_and_restart(publications):
    s = publications
    activate(s)
    body = request()
    receipt = publish(s, body)
    status = s.manager.inspect(1)
    s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=status['grant_record_revision'])
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status='disabled'))
    s.archive.write_bytes(b'current package is no longer the original schema')
    s.engine.dispose()  # New connections; receipt isn't an in-memory cache.
    assert publish(s, body) == receipt
    with pytest.raises(ValueError):
        publish(s, request())
    assert count(s) == 1


def test_failed_commit_does_not_mint_receipt(publications, monkeypatch):
    s = publications
    activate(s)
    body = request()
    with Session(s.engine) as db:
        installation = db.get(Installation, 1)
        def fail():
            raise ValueError('test commit failure')
        monkeypatch.setattr(db, 'commit', fail)
        with pytest.raises(ValueError):
            publish_application_event(db, installation, body)
    assert count(s) == 0
    publish(s, body)
    assert count(s) == 1


def test_signed_sdk_lost_ack_retries_exact_receipt_and_revoke_denies_new_events(publications, monkeypatch, tmp_path):
    s = publications
    activate(s)
    server = ApplicationPlatformServer(tmp_path / 'publication.sock', s.transport_keys, group='missing-test-group')
    original_handle = server._handle
    class DroppedAck:
        def __init__(self, connection):
            self.connection = connection
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.connection.close()
        def recv(self, size):
            return self.connection.recv(size)
        def sendall(self, _payload):
            pass  # Commit succeeded, but first response is lost.
    server._handle = lambda connection: original_handle(DroppedAck(connection))
    server.start()
    client = ApplicationPlatformClient(server.socket_path, 'a' * 24, b's' * 32)
    body = request()
    kwargs = {'event_id': body['event_id'], 'payload': body['payload'],
        'occurred_at': datetime.fromisoformat(body['occurred_at'])}
    try:
        with pytest.raises(ApplicationPlatformError, match='response is invalid'):
            client.publish_event('record_changed', **kwargs)
        assert count(s) == 1
        server._handle = original_handle
        receipt = client.publish_event('record_changed', **kwargs)
        assert publish(s, body) == receipt and count(s) == 1
        status = s.manager.inspect(1)
        s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=status['grant_record_revision'])
        assert client.publish_event('record_changed', **kwargs) == receipt
        with pytest.raises(ApplicationPlatformError):
            client.publish_event('record_changed', **{**kwargs, 'event_id': 'evt_' + identity()})
    finally:
        server.stop()


def test_revoke_before_guarded_admission_denies_new_record(publications, monkeypatch):
    s = publications
    activate(s)
    prepare = s.manager._prepare
    def raced(installation_id):
        prepared = prepare(installation_id)
        monkeypatch.setattr(s.manager, '_prepare', prepare)
        status = s.manager.inspect(1)
        s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=status['grant_record_revision'])
        return prepared
    monkeypatch.setattr(s.manager, '_prepare', raced)
    with pytest.raises(ValueError):
        publish(s, request())
    assert count(s) == 0


@pytest.mark.parametrize('change', ['configuration', 'artifact', 'key', 'recovery'])
def test_publication_grant_drift_denies_new_events_but_keeps_exact_receipt(publications, change):
    s = publications
    activate(s)
    body = request()
    receipt = publish(s, body)
    if change == 'key':
        s.keys.rotate(expected_key_id=s.keys.identity().key_id)
    else:
        with s.engine.begin() as db:
            if change == 'configuration':
                db.execute(update(Installation).values(configuration={**s.configuration, 'PRIVATE_NOTE': 'changed'}))
            elif change == 'artifact':
                db.execute(update(ModulePackage).values(sha256='e' * 64))
            else:
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
    assert publish(s, body) == receipt
    with pytest.raises(ValueError):
        publish(s, request())
    assert count(s) == 1


def test_real_offline_restore_fence_preserves_receipt_without_reopening_publication(publications):
    from deployment.authority_recovery import fence_recovered_authority
    s = publications
    activate(s)
    body = request()
    receipt = publish(s, body)
    s.engine.dispose()  # Disposable fixture; no running services or live recovery.
    fence = fence_recovered_authority(Path(s.engine.url.database), reason='backup_restore')
    assert fence.generation and fence.applications == 1
    assert publish(s, body) == receipt
    with pytest.raises(ValueError):
        publish(s, request())
    assert count(s) == 1


@pytest.mark.parametrize('changed_content', [False, True])
def test_concurrent_same_id_has_one_record_and_never_a_foreign_content_receipt(publications, monkeypatch, changed_content):
    import backend.services.application_event_publication as publication_service
    s = publications
    activate(s)
    body = request()
    barrier, observed = threading.Barrier(2), threading.local()
    original = publication_service._historical
    def rendezvous(db, producer, request):
        result = original(db, producer, request)
        if not getattr(observed, 'done', False):
            observed.done = True
            barrier.wait(timeout=10)
        return result
    monkeypatch.setattr(publication_service, '_historical', rendezvous)
    def send(value):
        try:
            return publish(s, {**body, 'payload': {'value': value}})
        except ValueError as error:
            return ('conflict', str(error))
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(send, [1, 2 if changed_content else 1]))
    monkeypatch.setattr(publication_service, '_historical', original)
    assert count(s) == 1
    committed = [result for result in receipts if isinstance(result, dict)]
    assert committed and all(result == committed[0] for result in committed)
    if changed_content:
        assert sum(isinstance(result, tuple) and result[0] == 'conflict' for result in receipts) == 1
    else:
        # Nonblocking key contention can fail closed while the first admission
        # is still in flight. It must not mint an ACK or retry publication.
        assert all(isinstance(result, dict) or result == (
            'conflict', 'Application resource grant is unavailable or stale') for result in receipts)
    with Session(s.engine) as db:
        payload = db.scalar(select(DeviceEvent.payload))
    assert publish(s, {**body, 'payload': payload}) == committed[0]
    with pytest.raises(ValueError, match='different owner or content'):
        publish(s, {**body, 'payload': {'value': 2 if payload['value'] == 1 else 1}})
    assert count(s) == 1
