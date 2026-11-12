"""Code-only recovery after real child death; no physical device access."""
from datetime import UTC, datetime, timedelta
import io
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

import agent.hardware.character_display as native
from agent.hardware.character_display import NativeCharacterDisplay
from agent.module_runtime import AgentModuleRuntime
from packages.protocol.character_display import CharacterDisplayProfileV1


@pytest.mark.parametrize('reaped', [False, True])
def test_fault_waits_for_actual_exit_and_backoff_without_replaying(tmp_path, monkeypatch, reaped):
    clock, children = [0.0], []
    class Child:
        def __init__(self):
            self.stdin, self.stdout = io.BytesIO(), io.BytesIO()
            self.exited = False
        def poll(self): return 1 if self.exited else None
        def kill(self): self.exited = reaped
        def wait(self, *, timeout):
            if not self.exited: raise subprocess.TimeoutExpired('worker', timeout)
            return 1
    monkeypatch.setattr(native, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(NativeCharacterDisplay, 'device_available', lambda _: True)
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **kw: children.append(Child()) or children[-1])
    replies = iter([b'R\n', b'T\n', b'R\n', b'O\n'])
    monkeypatch.setattr(NativeCharacterDisplay, '_read_ack', lambda *a: next(replies))
    driver = NativeCharacterDisplay(CharacterDisplayProfileV1(driver='pcf8574'), tmp_path)
    with pytest.raises(TimeoutError): driver.write_frame(['A'*20, 'B'*20], True)
    assert not driver.is_available() and not driver.maintain() and len(children) == 1
    clock[0] = 11
    if not reaped:
        assert not driver.maintain() and len(children) == 1
        children[0].exited = True  # Kill/pipe-close is not proof of child exit.
    assert driver.maintain() and len(children) == 2
    assert children[1].stdin.getvalue() == b''  # Code-only preparation, never the old frame.
    driver.write_frame(['C'*20, 'D'*20], False)
    frame = json.loads(children[1].stdin.getvalue())
    assert frame['initialize'] is True and frame['lines'] == ['C'*20, 'D'*20]
    driver.close()
    clock[0] = 100
    assert not driver.maintain() and len(children) == 2


def test_idle_child_death_and_repeated_prepare_faults_are_bounded(tmp_path, monkeypatch):
    clock, children = [0.0], []
    class Child:
        def __init__(self): self.stdin, self.stdout, self.exited = io.BytesIO(), io.BytesIO(), False
        def poll(self): return 1 if self.exited else None
        def kill(self): self.exited = True
        def wait(self, **kw): return 1
    monkeypatch.setattr(native, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(NativeCharacterDisplay, 'device_available', lambda _: True)
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **kw: children.append(Child()) or children[-1])
    replies = iter([b'R\n', b'E\n', b'R\n'])
    monkeypatch.setattr(NativeCharacterDisplay, '_read_ack', lambda *a: next(replies))
    driver = NativeCharacterDisplay(CharacterDisplayProfileV1(driver='pcf8574'), tmp_path)
    driver.prepare()
    children[0].exited = True
    assert not driver.is_available() and not driver.maintain() and len(children) == 1
    clock[0] = 11
    assert not driver.maintain() and len(children) == 2
    for _ in range(20): assert not driver.maintain()
    assert len(children) == 2
    clock[0] = 22
    assert driver.maintain() and len(children) == 3
    assert children[2].stdin.getvalue() == b''
    driver.close()


def test_missing_bus_or_failed_spawn_never_produces_a_frame_or_busy_retry(tmp_path, monkeypatch):
    clock, present, calls = [0.0], [False], []
    monkeypatch.setattr(native, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(NativeCharacterDisplay, 'device_available', lambda _: present[0])
    def failed(*a, **kw):
        calls.append(1)
        raise OSError('process unavailable')
    monkeypatch.setattr(subprocess, 'Popen', failed)
    driver = NativeCharacterDisplay(CharacterDisplayProfileV1(driver='pcf8574'), tmp_path)
    assert not driver.maintain() and calls == []
    present[0] = True
    assert not driver.maintain() and calls == [1]
    for _ in range(20): assert not driver.maintain()
    assert calls == [1]
    driver.close()


def test_provider_maintenance_is_explicit_deduplicated_and_isolates_optional_failures(tmp_path):
    calls = []
    def fail():
        calls.append('fault')
        raise OSError('optional service')
    shared = SimpleNamespace(maintain=lambda: calls.append('prepared'))
    runtime = AgentModuleRuntime(tmp_path, architecture='armv6l')
    runtime._services = {'first': SimpleNamespace(maintain=fail), 'second': shared, 'third': shared}
    runtime.maintain_services()
    assert calls == ['fault', 'prepared']


@pytest.mark.skipif(sys.platform != 'linux', reason='Actual private worker recovery with no I2C')
def test_real_child_recovers_after_timeout_and_continues_many_fresh_frames(tmp_path, monkeypatch):
    recorded = tmp_path/'frames.jsonl'
    bootstrap = '''import sys,json
sys.path.insert(0,sys.argv[1])
import agent.character_display_worker as worker
def record(raw):
    value=json.loads(raw)
    with open(%r,'a') as stream:stream.write(raw+'\\n')
    if value['lines'][0].startswith('FAIL'):raise TimeoutError('injected')
worker.write_once=record
worker.serve()
''' % str(recorded)
    monkeypatch.setattr(native, '_BOOTSTRAP', bootstrap)
    monkeypatch.setattr(native, 'RECOVERY_BACKOFF_SECONDS', 0)
    monkeypatch.setattr(NativeCharacterDisplay, 'device_available', lambda _: True)
    driver = NativeCharacterDisplay(CharacterDisplayProfileV1(driver='pcf8574', columns=16), tmp_path/'locks')
    try:
        driver.prepare()
        for phase in range(3):
            with pytest.raises(TimeoutError): driver.write_frame(['FAIL'.ljust(16), ' '*16], True)
            assert driver._child.poll() is not None and driver.maintain()
            assert len(recorded.read_text().splitlines()) == phase*21 + 1
            for number in range(phase*20, (phase+1)*20):
                driver.write_frame([str(number).ljust(16), 'NEW'.ljust(16)], True,
                                   not_after=datetime.now(UTC)+timedelta(seconds=2))
        frames = [json.loads(row) for row in recorded.read_text().splitlines()]
        assert len(frames) == 63
        for offset in (0, 21, 42):
            assert frames[offset+1]['initialize'] is True
            assert all(not frame['initialize'] for frame in frames[offset+2:offset+21])
        assert frames[-1]['lines'][0].strip() == '59'
    finally:
        driver.close()
