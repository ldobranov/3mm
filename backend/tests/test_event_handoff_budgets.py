"""Event phase/lease deadlines with disposable sockets and a deterministic clock."""
import os
import socket
from types import SimpleNamespace

import pytest

from components.platform_runtime import events
from packages.platform_wire import event_delivery


pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Unix event FD handoff')


@pytest.mark.parametrize('claim_seconds', [0, 4.5, 9.5])
def test_handler_wait_starts_after_core_handoff_and_reserves_completion(monkeypatch, claim_seconds):
    clock = [100.0]
    monkeypatch.setattr(events, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    left, right = socket.socketpair()
    calls = []
    worker = events.EventDeliveryWorker('unused', core_uid=os.geteuid())
    lease_deadline = 140.0

    def authority(request, deadline):
        calls.append((request, deadline))
        if request.get('claim'):
            assert request['claim_deadline_ms'] == 110_000
            assert deadline == 110
            clock[0] += claim_seconds
            # This models the concrete old failure: a 4.5s Core preparation
            # cannot hand its response FD to a caller with a four-second wait.
            if clock[0] >= deadline:
                left.close()
                raise TimeoutError('claim handoff was abandoned')
            return {'event_delivery_contract': 1, 'ok': True, 'idle': False,
                'receipt': {'delivery_id': 7, 'dispatch_id': 'a' * 32},
                'timeout_seconds': 30, 'lease_boot_id': 'boot',
                'lease_deadline_ms': int(lease_deadline * 1000)}, left
        assert request['response'] == {'ok': True}
        assert deadline == min(clock[0] + events.COMPLETION_SECONDS, lease_deadline)
        return {'event_delivery_contract': 1, 'ok': True}, None

    def read(origin, deadline, **_bounds):
        assert origin is left
        expected = min(30, lease_deadline - clock[0] - events.COMPLETION_SECONDS)
        assert deadline == clock[0] + expected
        clock[0] = deadline
        return {'ok': True}

    monkeypatch.setattr(worker, '_authority', authority)
    monkeypatch.setattr(events, 'read_frame', read)
    monkeypatch.setattr(events, 'lease_remaining', lambda boot, until: lease_deadline - clock[0])
    try:
        assert worker.step() is False
        assert len(calls) == 2 and left.fileno() == -1
        assert not worker.connections
    finally:
        left.close(); right.close()


@pytest.mark.parametrize('remaining', [0, 1, 4])
def test_expired_or_exhausted_handoff_closes_fd_without_read_or_replay(monkeypatch, remaining):
    left, right = socket.socketpair()
    worker = events.EventDeliveryWorker('unused', core_uid=os.geteuid())
    calls = []
    def authority(request, deadline):
        calls.append(request)
        return {'event_delivery_contract': 1, 'ok': True, 'idle': False,
            'receipt': {'delivery_id': 7, 'dispatch_id': 'a' * 32}, 'timeout_seconds': 30,
            'lease_boot_id': 'boot', 'lease_deadline_ms': 1000}, left
    monkeypatch.setattr(worker, '_authority', authority)
    monkeypatch.setattr(events, 'lease_remaining', lambda *_args: remaining)
    monkeypatch.setattr(events, 'read_frame', lambda *_a, **_kw: pytest.fail('Expired handler read'))
    try:
        with pytest.raises(ValueError, match='result budget'):
            worker.step()
        assert len(calls) == 1 and left.fileno() == -1
        assert not worker.connections
    finally:
        left.close(); right.close()


@pytest.mark.parametrize('error,category', [(TimeoutError, 'deadline_exceeded'),
    (OSError, 'handler_unavailable'), (ValueError, 'response_invalid')])
def test_handler_failure_is_completed_once_within_lease(monkeypatch, error, category):
    left, right = socket.socketpair()
    worker = events.EventDeliveryWorker('unused', core_uid=os.geteuid())
    calls = []
    def authority(request, deadline):
        calls.append(request)
        if request.get('claim'):
            return {'event_delivery_contract': 1, 'ok': True, 'idle': False,
                'receipt': {'delivery_id': 7, 'dispatch_id': 'a' * 32}, 'timeout_seconds': 2,
                'lease_boot_id': 'boot', 'lease_deadline_ms': 1000}, left
        assert request['failure'] == category and 'response' not in request
        raise TimeoutError('lost completion acknowledgement')
    def fail(*_args, **_kwargs):
        raise error('owned test peer')
    monkeypatch.setattr(worker, '_authority', authority)
    monkeypatch.setattr(events, 'lease_remaining', lambda *_args: 20)
    monkeypatch.setattr(events, 'read_frame', fail)
    try:
        with pytest.raises(TimeoutError, match='completion'):
            worker.step()
        assert len(calls) == 2 and left.fileno() == -1
        assert not worker.connections
    finally:
        left.close(); right.close()


@pytest.mark.parametrize('boot,deadline', [('other', 1100), ('boot', 1000),
    ('boot', 41001), ('boot', True), (None, 1100)])
def test_authoritative_lease_rejects_other_boot_expiry_and_unbounded_values(monkeypatch, boot, deadline):
    monkeypatch.setattr(event_delivery, 'boot_clock', lambda: ('boot', 1000))
    with pytest.raises(ValueError, match='lease'):
        event_delivery.lease_remaining(boot, deadline)


def test_authoritative_lease_accounts_for_suspend_without_extending(monkeypatch):
    now = [1000]
    monkeypatch.setattr(event_delivery, 'boot_clock', lambda: ('boot', now[0]))
    assert event_delivery.lease_remaining('boot', 41000) == 40
    now[0] = 40_900
    assert event_delivery.lease_remaining('boot', 41000) == pytest.approx(.1)
    now[0] = 41000
    with pytest.raises(ValueError, match='expired'):
        event_delivery.lease_remaining('boot', 41000)


def test_claim_caller_peek_is_nonblocking_and_restores_its_timeout():
    from backend.applications.events.broker import _connected_caller
    left,right=socket.socketpair()
    left.settimeout(2)
    try:
        assert _connected_caller(left) is True
        assert left.gettimeout()==2
        right.close()
        assert _connected_caller(left) is False
        assert left.gettimeout()==2
    finally:left.close();right.close()
