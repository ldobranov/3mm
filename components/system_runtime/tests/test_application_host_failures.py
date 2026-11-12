"""Real host/socket negative replies retain only safe typed failure metadata."""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import uuid

import pytest

from packages.application_sdk import ApplicationPlatformError
from packages.protocol.diagnostics import validated_host_failure
from components.system_runtime.application_host import _operation_failure
from components.system_runtime.application_transport import read_message, send_message, sign_message, verify_message


PRIVATE = 'Bearer DO_NOT_EXPORT application business data /private/path'


@pytest.mark.parametrize('kind,reason', [
    (ValueError, 'host_value_error'), (TypeError, 'host_type_error'),
    (KeyError, 'host_key_error'), (IndexError, 'host_index_error'),
    (AttributeError, 'host_attribute_error'), (AssertionError, 'host_assertion_error'),
    (RuntimeError, 'host_runtime_error'), (PermissionError, 'host_permission_error'),
    (TimeoutError, 'host_timeout'), (OSError, 'host_os_error'),
    (sqlite3.OperationalError, 'host_sqlite_error'),
])
def test_fixed_exception_categories_do_not_format_messages(kind, reason):
    value = _operation_failure(kind(PRIVATE), 'application.host_handler', time.monotonic())
    assert validated_host_failure(value) == value and value['reason'] == reason
    assert PRIVATE not in json.dumps(value)


@pytest.mark.parametrize('code', [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_BUSY | (2 << 8)])
def test_sqlite_busy_uses_numeric_code_not_exception_text(code):
    error = sqlite3.OperationalError(PRIVATE)
    error.sqlite_errorcode = code
    assert _operation_failure(error, 'application.host_handler', time.monotonic())['reason'] == 'host_sqlite_busy'


@pytest.mark.parametrize('code,expected', [
    ('operation_denied', 'host_sdk_operation_denied'),
    ('transport_unavailable', 'host_sdk_transport_unavailable'),
    ('response_invalid', 'host_sdk_response_invalid'),
    (PRIVATE, 'host_sdk_operation_failed'), ([], 'host_sdk_operation_failed'),
])
def test_sdk_reason_is_closed_and_its_phase_never_becomes_a_replay_permit(code, expected):
    error = ApplicationPlatformError(PRIVATE, reason=code, phase='not_dispatched')
    value = _operation_failure(error, 'application.host_handler', time.monotonic())
    assert value['reason'] == expected and set(value) == {'version', 'stage', 'reason', 'duration_ms'}
    assert PRIVATE not in json.dumps(value)


DRIVER = r'''
import sys
import time
from pathlib import Path
from packages.application_sdk import ApplicationPlatformError
from components.system_runtime import application_host as host
from components.system_runtime.application_host import _serve_requests
root = Path(sys.argv[1])
original_send = host.send_message
def gated_send(connection, response):
    # A real disconnected socket, with only scheduling doubled so every reply
    # branch is tested after the caller has conclusively closed its peer.
    if response.get('request_id', '').startswith('disconnect-'):
        (root / 'reply-ready').write_text('ready')
        deadline = time.monotonic() + 5
        while not (root / 'release-reply').exists():
            if time.monotonic() >= deadline:
                raise TimeoutError('Owned disconnect fixture was not released')
            time.sleep(.005)
    return original_send(connection, response)
host.send_message = gated_send
class UnprintablePrivateException(Exception):
    def __str__(self):
        raise AssertionError('The host must not format application exceptions')
class Service:
    calls = 0
    def handle(self, operation, payload, context):
        self.calls += 1
        if payload.get('fault') == 'sdk':
            raise ApplicationPlatformError('Bearer SECRET business data', reason='operation_denied')
        if payload.get('fault') == 'custom':
            raise UnprintablePrivateException()
        if payload.get('fault') == 'result': return []
        return {'calls': self.calls}
metadata = {'instance_id': '1'*24, 'module_id': 'org.example.host-failure',
    'sha256': 'a'*64, 'storage': {}, 'operations': [
        {'operation_id': 'inspect', 'audiences': ['internal'], 'idempotency': 'forbidden'}]}
_serve_requests(metadata, Path(sys.argv[1]), b's'*32, Service(), None)
'''


@pytest.fixture
def host_socket(tmp_path):
    if os.name != 'posix':
        pytest.skip('Real native host Unix-socket process')
    (tmp_path / 'run').mkdir()
    process = subprocess.Popen([sys.executable, '-u', '-c', DRIVER, str(tmp_path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    path = tmp_path / 'run/service.sock'
    try:
        deadline = time.monotonic() + 5
        while True:
            assert process.poll() is None, process.communicate(timeout=1)
            if path.exists():
                try:
                    ready = exchange(path, operation_id='three_mm.host.info')
                    assert ready['ok'] is True and ready['result']['host_contract'] == 1
                    break
                except (ConnectionRefusedError, FileNotFoundError):
                    pass  # bind creates the pathname before listen is ready.
            assert time.monotonic() < deadline, 'Owned host fixture did not create its socket'
            time.sleep(.01)
        yield path, process
    finally:
        process.terminate()
        try:
            process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=3)


def exchange(path, **changes):
    identifier = changes.pop('request_id', uuid.uuid4().hex)
    request = {'version': 1, 'timestamp': int(time.time()), 'request_id': identifier,
        'operation_id': 'inspect', 'payload': {}, 'context': {'audience': 'internal'}, **changes}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        connection.connect(str(path))
        send_message(connection, sign_message(request, b's'*32))
        response = read_message(connection)
    return verify_message(response, b's'*32, expected_request_id=identifier)


@pytest.mark.parametrize('changes,stage,reason,calls', [
    ({'payload': []}, 'application.host_request', 'host_transport_error', 1),
    ({'context': {'audience': 'public'}}, 'application.host_context', 'host_transport_error', 1),
    ({'relational_invocation': {}}, 'application.host_storage', 'host_transport_error', 1),
    ({'payload': {'fault': 'sdk'}}, 'application.host_handler', 'host_sdk_operation_denied', 2),
    ({'payload': {'fault': 'custom'}}, 'application.host_handler', 'host_exception', 2),
    ({'payload': {'fault': 'result'}}, 'application.host_result', 'host_transport_error', 2),
])
def test_signed_failure_from_real_host_does_not_replay_or_kill_next_request(host_socket, changes, stage, reason, calls):
    path, process = host_socket
    response = exchange(path, **changes)
    assert response['ok'] is False
    assert response['error'] == 'Application operation failed; outcome may be unconfirmed'
    detail = validated_host_failure(response['failure'])
    assert detail is not None and detail['stage'] == stage and detail['reason'] == reason
    assert 'SECRET' not in json.dumps(response) and 'UnprintablePrivateException' not in json.dumps(response)
    assert 'retryable' not in response and 'phase' not in response
    # A failure can follow an effect (counter increment). Inspect, do not replay.
    ready = exchange(path)
    assert ready['ok'] is True and ready['result'] == {'calls': calls}
    assert 'failure' not in ready and process.poll() is None


@pytest.mark.parametrize('changes,handled', [
    ({}, 1),
    ({'operation_id': 'three_mm.host.info'}, 0),
    ({'operation_id': 'three_mm.platform.status'}, 0),
    ({'payload': []}, 0),
    ({'payload': {'fault': 'sdk'}}, 1),
])
def test_disconnected_reply_keeps_host_alive_without_replaying_handler(host_socket, changes, handled):
    path, process = host_socket
    root = path.parent.parent
    identifier = 'disconnect-' + uuid.uuid4().hex
    request = {'version': 1, 'timestamp': int(time.time()), 'request_id': identifier,
        'operation_id': 'inspect', 'payload': {}, 'context': {'audience': 'internal'}, **changes}
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(2)
    try:
        connection.connect(str(path))
        send_message(connection, sign_message(request, b's' * 32))
        deadline = time.monotonic() + 3
        while not (root / 'reply-ready').exists():
            assert process.poll() is None, process.communicate(timeout=1)
            assert time.monotonic() < deadline, 'Owned host did not reach reply boundary'
            time.sleep(.005)
    finally:
        connection.close()
        (root / 'release-reply').write_text('released')
    # Lost acknowledgement is not a replay permit. The next distinct request
    # must succeed in the same process and observe the original effect once.
    ready = exchange(path)
    assert ready['ok'] is True and ready['result'] == {'calls': handled + 1}
    assert process.poll() is None
    duplicate = exchange(path, request_id=identifier)
    assert duplicate['ok'] is False
    assert exchange(path)['result'] == {'calls': handled + 2}


def test_disconnected_incomplete_request_does_not_kill_host_or_call_handler(host_socket):
    path, process = host_socket
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        connection.connect(str(path))
        connection.sendall(b'{"version":')
    # EOF is a malformed request, never a handler admission. Its negative reply
    # can no longer reach the peer, but the next client still uses this process.
    ready = exchange(path)
    assert ready['ok'] is True and ready['result'] == {'calls': 1}
    assert process.poll() is None
