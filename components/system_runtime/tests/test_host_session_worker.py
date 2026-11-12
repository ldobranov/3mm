"""Host profile refusal, root policy pinning and bounded stream lifecycle.

OS identity/mounts are doubled here. Real systemd and filesystem acceptance is a
separate installed-device gate; these checks never create an account or a shell.
"""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from types import SimpleNamespace
import io
import zipfile

import pytest

from components.system_runtime import host_session_policy as policy
from components.system_runtime import host_session_worker as worker
from components.system_runtime import session_worker as common_worker
from components.system_runtime.session_worker import read_packet, write_packet, SessionStartupError
from components.system_runtime.tests.test_session_worker import wheel
from packages.application_sdk import session as sdk


@pytest.mark.parametrize('raw', [b'{}', b'[]', b'{"schema_version":true,"enabled":true}',
    b'{"schema_version":2,"enabled":true}', b'{"schema_version":1,"enabled":1}',
    b'{"schema_version":1,"enabled":true,"uid":1000}',
    b'{"schema_version":1,"enabled":true,"enabled":false}'])
def test_policy_is_exact_root_configuration_not_an_account_selector(raw):
    with pytest.raises(ValueError):
        policy._configuration(raw)


def test_policy_accepts_disabled_boolean_without_authorizing_it():
    assert policy._configuration(b'{"schema_version":1,"enabled":false}') == {'schema_version': 1, 'enabled': False}


@pytest.fixture
def process_profile(monkeypatch):
    identity = SimpleNamespace(pw_name=sdk.HOST_SESSION_ACCOUNT, pw_uid=997, pw_gid=996,
        pw_dir=sdk.HOST_SESSION_HOME, pw_shell='/usr/sbin/nologin')
    monkeypatch.setitem(sys.modules, 'pwd', SimpleNamespace(getpwnam=lambda name: identity,
        getpwall=lambda: [identity]))
    monkeypatch.setitem(sys.modules, 'grp', SimpleNamespace(
        getgrgid=lambda gid: SimpleNamespace(gr_name=sdk.HOST_SESSION_ACCOUNT), getgrall=lambda: []))
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(os, 'geteuid', lambda: identity.pw_uid, raising=False)
    monkeypatch.setattr(os, 'getegid', lambda: identity.pw_gid, raising=False)
    monkeypatch.setattr(os, 'getgroups', lambda: [identity.pw_gid], raising=False)
    monkeypatch.setenv('THREE_MM_SESSION_PROFILE', sdk.HOST_SESSION_PROFILE)
    monkeypatch.setenv('INVOCATION_ID', '1'*32)
    values = {
        '/proc/self/cgroup': '0::/system.slice/3mm-host-session-worker@fixture.service\n',
        '/proc/self/status': 'NoNewPrivs:\t1\nCapInh:\t0\nCapPrm:\t0\nCapEff:\t0\nCapAmb:\t0\n',
    }
    monkeypatch.setattr(Path, 'read_text', lambda path, *a, **kw: values[path.as_posix()])
    monkeypatch.setattr(Path, 'lstat', lambda path: SimpleNamespace(
        st_mode=stat.S_IFDIR | 0o700, st_uid=identity.pw_uid, st_gid=identity.pw_gid))
    monkeypatch.setattr(os, 'access', lambda *a: False)

    def no_network(*a, **kw):
        raise OSError('Address family not supported by installed profile')
    monkeypatch.setattr('socket.socket', no_network)
    return identity, values


def test_host_guard_accepts_exact_account_and_does_not_accept_isolated_profile(process_profile, monkeypatch):
    sdk.require_host_account_session_process()
    monkeypatch.setenv('THREE_MM_SESSION_PROFILE', 'isolated_session_v1')
    with pytest.raises(RuntimeError):
        sdk.require_host_account_session_process()


@pytest.mark.parametrize('fault', ['root', 'group', 'home', 'login_shell', 'profile', 'cgroup', 'invocation', 'privileges', 'capability', 'private_path', 'network'])
def test_host_guard_refuses_identity_and_os_boundary_faults(process_profile, monkeypatch, fault):
    account, values = process_profile
    if fault == 'root': account.pw_uid = 0
    elif fault == 'group': monkeypatch.setattr(os, 'getgroups', lambda: [996, 27])
    elif fault == 'home': account.pw_dir = '/home/raspberry'
    elif fault == 'login_shell': account.pw_shell = '/bin/bash'
    elif fault == 'profile': monkeypatch.setenv('THREE_MM_SESSION_PROFILE', 'isolated_session_v1')
    elif fault == 'cgroup': values['/proc/self/cgroup'] = '0::/system.slice/3mm-session-worker@fake.service\n'
    elif fault == 'invocation': monkeypatch.delenv('INVOCATION_ID')
    elif fault == 'privileges': values['/proc/self/status'] = values['/proc/self/status'].replace('NoNewPrivs:\t1', 'NoNewPrivs:\t0')
    elif fault == 'capability': values['/proc/self/status'] = values['/proc/self/status'].replace('CapPrm:\t0', 'CapPrm:\t1')
    elif fault == 'private_path': monkeypatch.setattr(os, 'access', lambda *a: True)
    else: monkeypatch.setattr('socket.socket', lambda *a: SimpleNamespace(close=lambda: None))
    with pytest.raises(RuntimeError):
        sdk.require_host_account_session_process()


def test_host_guard_refuses_ipv6_even_if_ipv4_is_denied(process_profile, monkeypatch):
    import socket
    def ipv6_only(family, *a):
        if family == socket.AF_INET: raise OSError('IPv4 denied')
        return SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(socket, 'socket', ipv6_only)
    with pytest.raises(RuntimeError, match='network boundary'):
        sdk.require_host_account_session_process()


def test_fixed_account_rejects_extra_groups_and_insecure_home(process_profile, monkeypatch):
    account, _ = process_profile
    # Account metadata and root ancestors are separate from current process UID.
    original = policy._trusted_path
    checked = []
    monkeypatch.setattr(policy, '_trusted_path', lambda path, **kw: checked.append((path, kw)))
    assert policy._account()[1] == (account.pw_gid,)
    assert any(kw.get('private') and kw.get('uid') == account.pw_uid for path, kw in checked)
    import grp
    monkeypatch.setattr(grp, 'getgrall', lambda: [SimpleNamespace(gr_gid=27, gr_mem=[sdk.HOST_SESSION_ACCOUNT])])
    with pytest.raises(ValueError): policy._account()
    monkeypatch.setattr(policy, '_trusted_path', original)
    monkeypatch.setattr(Path, 'lstat', lambda path: SimpleNamespace(
        st_mode=stat.S_IFDIR | 0o770, st_uid=account.pw_uid, st_gid=account.pw_gid))
    with pytest.raises(ValueError): policy._trusted_path(Path(sdk.HOST_SESSION_HOME), directory=True, uid=account.pw_uid, private=True)


def test_fixed_account_refuses_a_second_login_name_with_the_same_uid(process_profile, monkeypatch):
    account, _ = process_profile
    import pwd
    alias = SimpleNamespace(pw_name='other-login', pw_uid=account.pw_uid)
    monkeypatch.setattr(pwd, 'getpwall', lambda: [account, alias])
    with pytest.raises(ValueError, match='shared UID'):
        policy._account()


@pytest.mark.parametrize('fault', ['symlink', 'group_write', 'owner', 'hardlink'])
def test_policy_path_rejects_untrusted_files(monkeypatch, fault):
    info = SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_uid=0, st_gid=0, st_nlink=1)
    if fault == 'symlink': info.st_mode = stat.S_IFLNK | 0o777
    elif fault == 'group_write': info.st_mode |= 0o020
    elif fault == 'owner': info.st_uid = 997
    else: info.st_nlink = 2
    monkeypatch.setattr(Path, 'lstat', lambda path: info)
    with pytest.raises(ValueError): policy._trusted_path(Path('/etc/3mm-host-sessions.json'))


def test_policy_digest_pins_actual_account_not_just_enabled_flag(tmp_path, monkeypatch):
    if sys.platform != 'linux': pytest.skip('Linux descriptor flags')
    path = tmp_path/'policy.json'
    path.write_text('{"schema_version":1,"enabled":true}')
    monkeypatch.setattr(policy, 'HOST_SESSION_POLICY_PATH', path)
    real_stat = path.stat()
    trusted = SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_uid=0, st_nlink=1,
        st_dev=real_stat.st_dev, st_ino=real_stat.st_ino, st_ctime_ns=1, st_mtime_ns=1,
        st_size=real_stat.st_size)
    monkeypatch.setattr(policy, '_trusted_path', lambda *a, **kw: trusted)
    monkeypatch.setattr(os, 'fstat', lambda fd: trusted)
    identity = SimpleNamespace(pw_name=sdk.HOST_SESSION_ACCOUNT, pw_uid=997, pw_gid=996,
        pw_dir=sdk.HOST_SESSION_HOME, pw_shell='/usr/sbin/nologin')
    monkeypatch.setattr(policy, '_account', lambda: (identity, (identity.pw_gid,)))
    first = policy.read_host_session_policy()
    trusted.st_ctime_ns += 1
    assert policy.read_host_session_policy().sha256 != first.sha256
    first = policy.read_host_session_policy()
    identity.pw_uid = 998
    assert policy.read_host_session_policy().sha256 != first.sha256
    path.write_text('{"schema_version":1,"enabled":false}')
    with pytest.raises(ValueError): policy.read_host_session_policy()
    assert policy.read_host_session_policy(require_enabled=False).enabled is False


def context():
    return {'session_id': 'ses_'+'a'*32, 'device_id': 'dev_'+'a'*32,
        'capability_id': 'example.counter', 'access_mode': 'write', 'options': {}}


@pytest.mark.parametrize('key', ['uid', 'account', 'shell', 'cwd', 'env', 'executable'])
def test_context_cannot_select_host_process_policy(key):
    value = context()
    value['options'][key] = 'forbidden'
    with pytest.raises(ValueError): worker._context(value)


def test_stream_rejects_wrong_policy_before_provider_import(monkeypatch):
    async def run():
        writer = SimpleNamespace(close=lambda: None, wait_closed=lambda: asyncio.sleep(0))
        reader = asyncio.StreamReader()
        data = wheel()
        hello = {'version': 2, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'factory': 'worker_fixture:create_provider', 'provider_id': 'org.example.counter',
            'context': context(), 'profile': sdk.HOST_SESSION_PROFILE, 'policy_sha256': 'f'*64}
        encoded = json.dumps(hello).encode()
        reader.feed_data(struct.pack('!I', len(encoded))+encoded+data)
        expected = SimpleNamespace(sha256='a'*64)
        monkeypatch.setattr(worker, 'read_host_session_policy', lambda: expected)
        monkeypatch.setattr(common_worker.importlib, 'import_module', lambda name: pytest.fail('Unapproved provider import'))
        with pytest.raises(SessionStartupError) as failure:
            await worker.serve(reader, writer, cgroup='unused')
        assert failure.value.diagnostic_stage == 'session.opening.bootstrap'
    asyncio.run(run())


def test_policy_revocation_closes_idle_output_and_provider_without_input_replay(monkeypatch):
    async def run():
        expected = SimpleNamespace(sha256='a'*64)
        current = [expected]
        monkeypatch.setattr(worker, 'read_host_session_policy', lambda: current[0])
        tasks = []
        closed = asyncio.Event()
        original_sleep = asyncio.sleep
        async def fast_watch(seconds):
            await original_sleep(0.01 if seconds == 3 else seconds)
        monkeypatch.setattr(worker.asyncio, 'sleep', fast_watch)
        async def connected(reader, writer):
            tasks.append(asyncio.current_task())
            try: await worker.serve(reader, writer, cgroup='/system.slice/3mm-host-session-worker@fixture.service')
            except ValueError: closed.set()
        server = await asyncio.start_server(connected, '127.0.0.1', 0)
        reader, writer = await asyncio.open_connection('127.0.0.1', server.sockets[0].getsockname()[1])
        with zipfile.ZipFile(io.BytesIO(wheel())) as original:
            source = original.read('worker_fixture.py').decode()
        data = wheel('closed = []\n' + source.replace(
            'async def close(self, sid, reason): pass', 'async def close(self, sid, reason): closed.append(reason)'))
        try:
            await write_packet(writer, {'version': 2, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                'factory': 'worker_fixture:create_provider', 'provider_id': 'org.example.counter', 'context': context(),
                'profile': sdk.HOST_SESSION_PROFILE, 'policy_sha256': expected.sha256})
            ready = await read_packet(reader)
            assert ready['profile'] == sdk.HOST_SESSION_PROFILE and ready['policy_sha256'] == expected.sha256
            assert ready['state'] == 'owned'
            writer.write(data); await writer.drain()
            assert (await read_packet(reader))['state'] == 'ready'
            await write_packet(writer, {'id': 1, 'op': 'input', 'data': 'bmV4dA=='})
            assert (await read_packet(reader))['data'] == 'MQ=='
            await write_packet(writer, {'id': 2, 'op': 'read'})
            current[0] = SimpleNamespace(sha256='b'*64)
            await asyncio.wait_for(closed.wait(), 2)
            assert await reader.read() == b''
            await asyncio.gather(*tasks)
            assert sys.modules['worker_fixture'].closed == ['link_closed']
        finally:
            writer.close(); await writer.wait_closed()
            server.close(); await server.wait_closed()
            sys.modules.pop('worker_fixture', None)
    asyncio.run(asyncio.wait_for(run(), 5))
