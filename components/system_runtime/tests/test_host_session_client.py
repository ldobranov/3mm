"""Host-only bootstrap/lease framing; no live accounts, services or OS claims."""
import asyncio
import sys
from types import SimpleNamespace

import pytest

from components.system_runtime import host_session_worker as worker, host_session_policy
from components.system_runtime.session_worker_client import HostAccountSessionProvider, SandboxedSessionProvider
from components.system_runtime.tests.test_session_worker import wheel


def provider():
    return HostAccountSessionProvider(wheel=wheel(), factory='worker_fixture:create_provider',
        provider_id='org.example.counter', policy_sha256='a'*64)


@pytest.mark.parametrize('change', [
    {'profile': 'isolated_session_v1'}, {'policy_sha256': 'b'*64}, {'uid': 997},
    {'cgroup': '/system.slice/system-test.slice/3mm-session-worker@fixture.service'},
    {'cgroup': '/system.slice/../../3mm-host-session-worker@fixture.service'},
    {'state': 'ready'}, {'session_id': 'ses_'+'b'*32}, {'worker_ipc': 1},
])
def test_host_client_never_accepts_an_isolated_or_different_policy_startup(change):
    value = provider()
    value.session_id = 'ses_'+'a'*32
    ready = {'worker_ipc': 2, 'state': 'owned', 'session_id': value.session_id,
        'cgroup': '/system.slice/system-test.slice/3mm-host-session-worker@fixture.service',
        'profile': 'host_account_session_v1', 'policy_sha256': 'a'*64}
    with pytest.raises(RuntimeError):
        value._owned_cgroup({**ready, **change})
    assert value.cgroup is None
    isolated = SandboxedSessionProvider(wheel=wheel(), factory='worker_fixture:create_provider', provider_id='org.example.counter')
    with pytest.raises(RuntimeError):
        isolated._owned_cgroup(ready)


def test_exact_host_client_preserves_bounded_output_input_controls_and_cleanup(monkeypatch):
    async def run():
        policy = SimpleNamespace(sha256='a'*64)
        monkeypatch.setattr(host_session_policy, 'read_host_session_policy', lambda: policy)
        monkeypatch.setattr(worker, 'read_host_session_policy', lambda: policy)
        tasks = []
        async def connected(reader, writer):
            tasks.append(asyncio.current_task())
            await worker.serve(reader, writer,
                cgroup='/system.slice/system-test.slice/3mm-host-session-worker@fixture.service')
        server = await asyncio.start_server(connected, '127.0.0.1', 0)
        port = server.sockets[0].getsockname()[1]
        value = provider()
        monkeypatch.setattr(value, '_connect', lambda: asyncio.open_connection('127.0.0.1', port))
        async def os_cleanup_double():
            pass  # No systemd process exists in this transport-only test.
        monkeypatch.setattr(value, '_wait_empty', os_cleanup_double)
        sid = 'ses_'+'a'*32
        try:
            await value.open({'session_id': sid, 'device_id': 'dev_'+'a'*32,
                'capability_id': 'example.counter', 'access_mode': 'write', 'options': {}})
            assert b''.join([await value.read_output(sid) for _ in range(4)]) == b'ready'*10000
            assert await value.receive(sid, b'next') == b'2'
            await value.control(sid, {'action': 'reset', 'arguments': {'value': 10}})
            assert await value.receive(sid, b'next') == b'11'
            await asyncio.sleep(3.1)  # Host lease is acknowledged without input replay.
            assert not value.heartbeat.done() and not value.receiving.done()
            waiting = asyncio.create_task(value.read_output(sid))
            await asyncio.sleep(0)
            await value.close(sid, 'test')
            await asyncio.gather(waiting, return_exceptions=True)
            await asyncio.gather(*tasks)
            assert value.heartbeat.done()
            with pytest.raises(RuntimeError, match='already attempted'):
                await value.open({'session_id': sid})
        finally:
            server.close()
            await server.wait_closed()
            sys.modules.pop('worker_fixture', None)
    asyncio.run(asyncio.wait_for(run(), 8))
