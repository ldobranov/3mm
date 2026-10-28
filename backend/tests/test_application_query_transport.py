"""Real Core admission, independent Runtime wait and real SDK application host.

All processes/sockets/keys are disposable and use the test UID; no OS isolation
or native-code purity claim. Query result revocation is tested during the wait.
"""
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services.application_platform import CoreRuntimeAuthorityServer
from backend.services.application_query_transport import QueryBroker
from backend.tests.test_application_composition_authority import (
    pair, installed, source_subject, source_installed, approve, grant, identity, SCOPE,
)
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Real POSIX FD/peer/process transport')


class QueryService:
    def __init__(self, seen, release): self.seen, self.release = seen, release

    def handle(self, operation, payload, context):
        self.seen.put(dict(operation=operation, payload=payload,
            caller=context.application_caller.model_dump(mode='json'),
            actor=context.actor.kind, user_id=context.user_id,
            permissions=context.permission_ids, executor=context.executor.instance_id))
        if payload['reference'] == 'pause':
            assert self.release.wait(8), 'Test did not release its provider'
        if payload['reference'] == 'bad-output': return {'found': 'not a boolean', 'label': 'PRIVATE'}
        return {'found': True, 'label': 'Здравей · ' + payload['reference']}


def host_process(metadata, root, key, seen, release):
    from three_mm_runtime.application_host import _serve_requests
    _serve_requests(metadata, Path(root), key, QueryService(seen, release), None)


def wait_socket(path, process):
    end = time.monotonic() + 8
    while time.monotonic() < end:
        if Path(path).exists(): return
        assert (process.poll() is None if hasattr(process, 'poll') else process.is_alive()), 'Disposable process stopped before listening'
        time.sleep(.01)
    pytest.fail('Disposable socket did not become ready')


@pytest.fixture
def stack(pair, monkeypatch):
    from backend import database
    s = pair
    approve(s, scopes=[SCOPE])
    monkeypatch.setattr(database, 'SessionLocal', sessionmaker(s.engine))
    # Fork the provider before starting Core threads. Runtime is an exec'd
    # stdlib-only process, with no inherited Core DB/keys/Python object graph.
    context = multiprocessing.get_context('fork')
    with tempfile.TemporaryDirectory(prefix='3mm-query-', dir='/tmp') as directory:
        root = Path(directory); keys = root/'keys'; keys.mkdir()
        consumer_key, provider_key = b'c'*32, b'p'*32
        (keys/('a'*24+'.key')).write_bytes(provider_key)
        (keys/('b'*24+'.key')).write_bytes(consumer_key)
        app = root/'app'; (app/'run').mkdir(parents=True); (app/'data').mkdir()
        path = app/'run/service.sock'
        with Session(s.engine) as db, db.begin():
            db.execute(update(Installation).where(Installation.id == 1).values(socket_path=str(path)))
        seen, release = context.Queue(), context.Event()
        definition = s.provider.application_extension.model_dump(mode='json')
        metadata = dict(instance_id='a'*24, module_id=s.provider.manifest.module_id,
            sha256=s.provider.sha256, operations=definition['operations'], storage=definition['storage'])
        host = context.Process(target=host_process, args=(metadata, str(app), provider_key, seen, release))
        core = CoreRuntimeAuthorityServer(root/'authority.sock', keys, runtime_uid=os.getuid())
        runtime = None
        try:
            host.start(); wait_socket(path, host)
            core.start()
            runtime = subprocess.Popen([sys.executable, '-m', 'three_mm_platform_runtime',
                '--socket', str(root/'runtime.sock'), '--authority-socket', str(core.socket_path),
                '--core-uid', str(os.getuid())], close_fds=True)
            wait_socket(root/'runtime.sock', runtime)
            client = ApplicationPlatformClient(root/'runtime.sock', 'b'*24, consumer_key, timeout_seconds=10)
            yield SimpleNamespace(s=s, client=client, core=core, runtime=runtime, host=host,
                seen=seen, release=release, keys=keys, root=root)
        finally:
            release.set()
            if runtime is not None:
                if runtime.poll() is None: runtime.terminate()
                try: runtime.wait(5)
                except subprocess.TimeoutExpired: runtime.kill(); runtime.wait(2)
            if host.pid is not None:
                if host.is_alive(): host.terminate()
                host.join(5)
                if host.is_alive(): host.kill(); host.join(2)
            core.stop()
            seen.close(); seen.join_thread()


def test_query_real_sdk_runtime_and_host_return_unicode_with_application_not_human_actor(stack):
    x = stack
    answer = x.client.query('directory', arguments={'reference': 'alpha'})
    assert answer['output'] == {'found': True, 'label': 'Здравей · alpha'}
    assert answer['provider_instance_id'] == 'a'*24
    assert answer['contract_digest'] == x.s.consumer.application_extension.query_dependencies[0].contract.digest()
    observed = x.seen.get(timeout=1)
    assert observed == dict(operation='lookup', payload={'reference': 'alpha'},
        caller=dict(instance_id='b'*24, module_id=x.s.consumer.manifest.module_id,
            artifact_sha256=x.s.consumer.sha256, binding_id='directory', contract_digest=answer['contract_digest']),
        actor='application', user_id=None, permissions=(), executor='a'*24)
    assert x.core.query_broker.pending == {}


@pytest.mark.parametrize('fault', ['provider-revoke', 'consumer-revoke', 'provider-config', 'consumer-disable', 'provider-renew', 'provider-key'])
def test_changes_during_runtime_wait_fence_output_without_retry_or_long_core_transaction(stack, fault):
    x = stack
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(x.client.query, 'directory', arguments={'reference': 'pause'})
        assert x.seen.get(timeout=3)['operation'] == 'lookup'
        start = time.monotonic()
        if fault.endswith('revoke'):
            identifier = 1 if fault.startswith('provider') else 2
            x.s.manager.revoke(identifier, actor_token=x.s.token, request_id=identity(),
                expected_revision=grant(x.s, identifier)['revision'])
        elif fault == 'provider-renew': approve(x.s, 1)
        elif fault == 'provider-key': (x.keys/('a'*24+'.key')).write_bytes(b'z'*32)
        else:
            with Session(x.s.engine) as db, db.begin():
                db.execute(update(Installation).where(Installation.id == (1 if fault.startswith('provider') else 2))
                    .values(**({'configuration': {'changed': 'value'}} if fault == 'provider-config' else {'enabled': False})))
        assert time.monotonic()-start < 1  # No provider wait holds SQLite/authority guard.
        assert not future.done()
        x.release.set()
        with pytest.raises(ApplicationPlatformError) as refused: future.result(timeout=3)
        assert refused.value.reason == 'operation_denied' and 'PRIVATE' not in str(refused.value)
    assert x.core.query_broker.pending == {}
    assert x.seen.empty()  # Exactly one handler call, no replay after fresh refusal.


def test_bad_input_is_not_dispatched_and_bad_output_is_not_disclosed(stack):
    x = stack
    with pytest.raises(ApplicationPlatformError): x.client.query('directory', arguments={'reference': 'x', 'extra': True})
    assert x.seen.empty()
    with pytest.raises(ApplicationPlatformError, match='Query result unavailable'):
        x.client.query('directory', arguments={'reference': 'bad-output'})
    assert x.seen.get(timeout=1)['payload'] == {'reference': 'bad-output'}
    assert x.core.query_broker.pending == {}


@pytest.mark.parametrize('mode', ['empty-selection', 'compatibility'])
def test_no_selection_or_compatibility_mode_never_dispatches_a_query(stack, mode):
    x = stack
    if mode == 'empty-selection': approve(x.s, scopes=[])
    else:
        with Session(x.s.engine) as db, db.begin():
            db.execute(update(Installation).where(Installation.id == 2).values(authority_mode='compatibility'))
    with pytest.raises(ApplicationPlatformError): x.client.query('directory', arguments={'reference': 'x'})
    assert x.seen.empty() and x.core.query_broker.pending == {}


def test_status_and_discovery_probe_runtime_but_do_not_claim_provider_execution_or_reveal_unapproved_pins(stack, monkeypatch):
    import pwd
    from backend import config
    x = stack
    settings = config.get_settings()
    selected = settings.applications.model_copy(update=dict(runtime_socket=x.root/'runtime.sock', runtime_user=pwd.getpwuid(os.getuid()).pw_name))
    monkeypatch.setattr(config, 'get_settings', lambda: settings.model_copy(update={'applications': selected}))
    status = x.s.manager.inspect(2)
    assert status['grant_effective'] and not status.get('runtime_blockers')
    observed, = x.client.discover_resources([SCOPE])['resources']
    assert observed['access'] == 'granted' and observed['readiness'] == 'unknown'
    assert observed['reasons'] == ['provider_not_observed']
    assert observed['selected_resource_id'] == 'a'*24
    assert x.seen.empty()  # Metadata-only Runtime probe, never a business query.
    approve(x.s, scopes=[])
    redacted, = x.client.discover_resources([SCOPE])['resources']
    assert redacted['access'] != 'granted' and redacted['provider'] is None and redacted['selected_resource_id'] is None


def test_hanging_provider_deadline_leaves_core_available_and_does_not_retry(stack):
    x = stack
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(x.client.query, 'directory', arguments={'reference': 'pause'})
        x.seen.get(timeout=3)
        from three_mm_platform_runtime.server import probe_runtime
        assert probe_runtime(x.root/'runtime.sock', expected_uid=os.getuid(), require_queries=True)['ready']
        assert x.core.active_connections == 0
        with pytest.raises(ApplicationPlatformError): future.result(timeout=7)
    assert time.monotonic()-start < 7
    x.release.set()
    assert x.seen.empty() and x.core.query_broker.pending == {}


def test_runtime_death_loses_result_not_core_health_or_permission_to_retry(stack):
    x = stack
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(x.client.query, 'directory', arguments={'reference': 'pause'})
        x.seen.get(timeout=3)
        x.runtime.kill(); x.runtime.wait(3)
        with pytest.raises(ApplicationPlatformError): future.result(timeout=3)
        assert x.core.is_running and x.core.active_connections == 0
        # Lost completion remains bounded in memory, never a replay worker.
        assert len(x.core.query_broker.pending) == 1
        x.release.set()
    assert x.seen.empty()


def test_completion_is_one_use_runtime_generation_bound_and_capacity_is_bounded():
    broker = QueryBroker()
    token, pending = broker._reserve(2, 'runtime', 'core', b'c'*32, 'request')
    with pytest.raises(ValueError):
        broker.finish(None, token, None, runtime_generation='other', core_generation='core', key_root=Path('/nonexistent'))
    assert token in broker.pending
    answer = broker.finish(None, token, None, runtime_generation='runtime', core_generation='core', key_root=Path('/nonexistent'))
    assert answer['ok'] is False and token not in broker.pending
    with pytest.raises(ValueError):
        broker.finish(None, token, None, runtime_generation='runtime', core_generation='core', key_root=Path('/nonexistent'))
    for _ in range(4): broker._reserve(2, 'runtime', 'core', b'c'*32, 'request')
    with pytest.raises(ValueError): broker._reserve(2, 'runtime', 'core', b'c'*32, 'request')
    for _ in range(4): broker._reserve(3, 'runtime', 'core', b'c'*32, 'request')
    with pytest.raises(ValueError): broker._reserve(4, 'runtime', 'core', b'c'*32, 'request')


def test_absent_query_feature_preserves_general_runtime_health_but_never_query_readiness(tmp_path):
    import threading
    from three_mm_platform_runtime.server import probe_runtime
    from three_mm_platform_wire import read_frame
    # An older, healthy immutable Runtime may be selected by independent rollback.
    # Its general health is NOT evidence for the newly optional query feature.
    with tempfile.TemporaryDirectory(prefix='3mm-q-probe-', dir='/tmp') as directory:
        path = Path(directory)/'runtime.sock'
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(path)); server.listen(2); server.settimeout(3)
            def serve():
                import json
                for _ in range(2):
                    connection, _ = server.accept()
                    with connection:
                        request = read_frame(connection, time.monotonic()+2)
                        connection.sendall(json.dumps(dict(runtime_probe=request['runtime_probe'],
                            pid=os.getpid(), ready=True, authority_contract=2, connector_execution_contract=1)).encode()+b'\n')
            worker = threading.Thread(target=serve, daemon=True); worker.start()
            try:
                assert probe_runtime(path, expected_uid=os.getuid())['ready']
                with pytest.raises(ValueError, match='readiness'):
                    probe_runtime(path, expected_uid=os.getuid(), require_queries=True)
            finally: worker.join(4)
            assert not worker.is_alive()


@pytest.mark.parametrize('fault', ['signature', 'request-id', 'expired', 'provider-error', 'schema', 'oversized', 'wire-version'])
def test_authenticated_result_boundary_refuses_invalid_provider_envelopes(stack, fault):
    from three_mm_runtime.application_transport import read_message, sign_message
    x = stack
    request = dict(version=1, request_id='platform_'+identity(), timestamp=int(time.time()),
        instance_id='b'*24, action='query.request', signature='not-used-by-internal-admission',
        binding_id='directory', arguments={'reference': 'direct'})
    broker = x.core.query_broker
    with Session(x.s.engine) as db:
        dispatch = broker.begin(db, db.get(Installation, 2), request, secret=b'c'*32,
            runtime_generation='runtime-test', core_generation='core-test', key_root=x.keys)
    with dispatch.connection as connection:
        # The FD handed to Runtime is response-only, not a credential-bearing
        # proxy through which it can append another provider invocation.
        with pytest.raises(OSError): connection.send(b'additional-provider-request\n')
        response = read_message(connection)
    x.seen.get(timeout=1)
    if fault == 'request-id': response['request_id'] = identity()
    elif fault == 'expired': response['timestamp'] -= 100
    elif fault == 'provider-error': response.update(ok=False, error='PRIVATE', result=None)
    elif fault == 'schema': response['result'] = {'found': 1, 'label': 'PRIVATE'}
    elif fault == 'oversized': response['result'] = {'found': True, 'label': 'PRIVATE'*800}
    elif fault == 'wire-version': response['version'] = True
    response = sign_message(response, b'p'*32)
    if fault == 'signature': response['signature'] = '0'*64
    answer = broker.finish(x.s.engine, dispatch.receipt, response, runtime_generation='runtime-test',
        core_generation='core-test', key_root=x.keys)
    assert answer['ok'] is False and 'PRIVATE' not in str(answer)
    assert broker.pending == {}
