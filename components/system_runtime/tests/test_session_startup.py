"""Real stream startup ordering; OS cleanup observations are explicit doubles."""
import asyncio
from contextlib import asynccontextmanager
import sys

import pytest

from components.system_runtime import session_worker as worker
from components.system_runtime.session_worker_client import SandboxedSessionProvider
from components.system_runtime.tests.test_session_worker import wheel


CONTEXT = {'session_id': 'ses_'+'d'*32, 'device_id': 'dev_'+'a'*32,
           'capability_id': 'example.counter', 'access_mode': 'write', 'options': {}}
CGROUP = '/system.slice/system-test.slice/3mm-session-worker@startup.service'
SOURCE = '''
import asyncio
opened = asyncio.Event()
cancelled = False
closed = False
class Provider:
    provider_id = 'org.example.counter'
    contract_version = '1.0'
    capability_ids = ('example.counter',)
    async def open(self, context):
        global cancelled
        opened.set()
        try: await asyncio.Event().wait()
        finally: cancelled = True
    async def receive(self, sid, data): raise AssertionError('Premature input')
    async def read_output(self, sid): raise AssertionError('Premature output')
    async def control(self, sid, message): raise AssertionError('Premature control')
    async def close(self, sid, reason):
        global closed
        closed = True
def create_provider(): return Provider()
'''


@asynccontextmanager
async def channel(source):
    tasks, errors = [], []
    async def accepted(reader, writer):
        tasks.append(asyncio.current_task())
        try:
            await worker.serve(reader, writer, cgroup=CGROUP)
        except Exception as error:
            errors.append(error)
    server = await asyncio.start_server(accepted, '127.0.0.1', 0)
    value = SandboxedSessionProvider(wheel=wheel(source), factory='worker_fixture:create_provider',
                                    provider_id='org.example.counter')
    async def connect():
        return await asyncio.open_connection('127.0.0.1', server.sockets[0].getsockname()[1])
    value._connect = connect
    try:
        yield value, errors
    finally:
        if value.writer is not None:
            value.writer.close()
            await value.writer.wait_closed()
        await asyncio.wait_for(asyncio.gather(*tasks), 3)
        server.close()
        await server.wait_closed()
        sys.modules.pop('worker_fixture', None)


def test_early_ownership_survives_cancel_without_becoming_ready(monkeypatch):
    async def run():
        async with channel(SOURCE) as (value, errors):
            opening = asyncio.create_task(value.open(CONTEXT))
            while 'worker_fixture' not in sys.modules:
                await asyncio.sleep(0.001)
            module = sys.modules['worker_fixture']
            await module.opened.wait()
            assert value.cgroup == CGROUP and value.receiving is None
            with pytest.raises(RuntimeError, match='unavailable'):
                await value.receive(CONTEXT['session_id'], b'never sent')
            opening.cancel()
            with pytest.raises(asyncio.CancelledError):
                await opening
            # Actual stream EOF cancels and joins pending provider.open; no replay.
            while not module.closed:
                await asyncio.sleep(0.001)
            assert module.cancelled
            assert value.cgroup == CGROUP
            observed = []
            def read_events(path, *args, **kwargs):
                observed.append(path.as_posix())
                return 'populated 0\n'
            monkeypatch.setattr(worker.Path, 'is_file', lambda path: path.as_posix() == '/sys/fs/cgroup/cgroup.controllers')
            monkeypatch.setattr(worker.Path, 'read_text', read_events)
            await value.close(CONTEXT['session_id'], 'cancelled')
            assert observed == ['/sys/fs/cgroup'+CGROUP+'/cgroup.events']
            with pytest.raises(RuntimeError, match='already attempted'):
                await value.open(CONTEXT)
    asyncio.run(asyncio.wait_for(run(), 5))


@pytest.mark.parametrize('stage', ['provider_load', 'provider_open', 'artifact_verify'])
def test_worker_first_failure_is_closed_metadata_before_cleanup_failure(stage):
    async def run():
        source = SOURCE.replace('opened.set()', "raise RuntimeError('PRIVATE_PROVIDER_SECRET')")
        source = source.replace('closed = True\ndef', "raise RuntimeError('PRIVATE_CLOSE_SECRET')\ndef")
        if stage == 'provider_load':
            source = "raise RuntimeError('PRIVATE_IMPORT_SECRET')\n"
        async with channel(source) as (value, errors):
            if stage == 'artifact_verify':
                value.sha256 = 'f'*64
            with pytest.raises(worker.SessionStartupError) as failed:
                await value.open(CONTEXT)
            assert failed.value.diagnostic_stage == 'session.opening.'+stage
            assert failed.value.diagnostic_reason == 'session_runtime_failed'
            assert 0 <= failed.value.duration_ms <= 10000
            assert value.cgroup == CGROUP and value.receiving is None
            assert 'PRIVATE' not in str(failed.value)
        assert errors[0].diagnostic_stage == failed.value.diagnostic_stage
    asyncio.run(asyncio.wait_for(run(), 5))


@pytest.mark.parametrize('change', [
    {'session_id': 'ses_'+'e'*32}, {'worker_ipc': True}, {'worker_ipc': 1},
    {'stage': 'session.opening.authority_initial'}, {'stage': 'private'},
    {'reason': 'private'}, {'duration_ms': float('inf')}, {'duration_ms': True},
    {'duration_ms': -1}, {'exception': 'PRIVATE'},
])
def test_untrusted_startup_error_metadata_is_not_accepted(change):
    value = SandboxedSessionProvider(wheel=wheel(), factory='worker_fixture:create_provider',
                                    provider_id='org.example.counter')
    value.session_id = CONTEXT['session_id']
    packet = {'worker_ipc': 2, 'state': 'failed', 'session_id': value.session_id,
              'stage': 'session.opening.provider_open', 'reason': 'deadline_exceeded', 'duration_ms': 5}
    with pytest.raises(worker.SessionStartupError) as failed:
        value._startup_response({**packet, **change})
    assert failed.value.diagnostic_reason == 'response_invalid'
    assert 'PRIVATE' not in str(failed.value)


def test_guard_failure_without_session_cannot_claim_worker_ownership():
    value = SandboxedSessionProvider(wheel=wheel(), factory='worker_fixture:create_provider',
                                    provider_id='org.example.counter')
    value.session_id = CONTEXT['session_id']
    with pytest.raises(worker.SessionStartupError) as failed:
        value._startup_response({'worker_ipc': 2, 'state': 'failed', 'session_id': None,
            'stage': 'session.opening.process_guard', 'reason': 'session_runtime_failed', 'duration_ms': 10})
    assert failed.value.diagnostic_stage == 'session.opening.process_guard'
    assert value.cgroup is None and value.receiving is None
