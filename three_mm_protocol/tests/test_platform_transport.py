"""Malformed and trickled frames cannot evade the shared local boundary."""
from contextlib import contextmanager
import socket
import threading
import time

import pytest
import three_mm_platform_wire as wire


@contextmanager
def sockets():
    left,right=socket.socketpair()
    try: yield left,right
    finally: left.close();right.close()


@pytest.mark.parametrize("frame", [b'{"x":1,"x":2}', b'{"nested":{"a":1,"a":2}}',
    b'{"n":NaN}', b'{"n":Infinity}', b'[]', b'null', b'\xff'])
def test_invalid_json_frames_are_rejected(frame):
    with pytest.raises(ValueError): wire.decode_frame(frame)


def test_frame_budget_includes_terminator_and_rejects_multiple_frames(monkeypatch):
    monkeypatch.setattr(wire,"MAX_MESSAGE_BYTES",8)
    for payload,valid in [(b'{"x":1}\n',True),(b'{"xx":1}\n',False),(b'{}\n{}\n',False)]:
        with sockets() as (left,right):
            left.sendall(payload)
            if valid:
                assert wire.read_frame(right,time.monotonic()+1)=={"x":1}
            else:
                with pytest.raises(ValueError): wire.read_frame(right,time.monotonic()+1)


def test_absolute_read_deadline_is_not_extended_by_progress():
    with sockets() as (left,right):
        def trickle():
            for _ in range(20):
                try: left.sendall(b" ")
                except OSError: return
                time.sleep(.02)
        worker=threading.Thread(target=trickle)
        worker.start()
        started=time.monotonic()
        try:
            with pytest.raises(TimeoutError): wire.read_frame(right,started+.08)
            assert time.monotonic()-started < .3
        finally:
            right.close();worker.join(timeout=1)


def test_canonical_rejects_overflowing_nonfinite_numbers():
    with pytest.raises(ValueError): wire.canonical(wire.decode_frame(b'{"n":1e9999}'))
