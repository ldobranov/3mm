"""No hardware: encoder, device API doubles, bounded worker supervision."""
from datetime import UTC, datetime, timedelta
import json
import io
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from agent.character_display_worker import Pcf8574Lcd, write_once, hd44780_rows, serve
from agent.hardware.character_display import NativeCharacterDisplay
from three_mm_protocol.character_display import CharacterDisplayProfileV1


def decode(raw):
    # Every nibble has low/high/low E writes; RW is never raised.
    assert len(raw) % 3 == 0
    result = []
    for offset in range(0, len(raw), 3):
        low, high, end = raw[offset:offset + 3]
        assert high == low | 4 and end == low and not low & 6
        result.append((low & 0xF0, bool(low & 1)))
    return result


@pytest.mark.parametrize("backlight,active_high", [(True, True), (False, True), (True, False), (False, False)])
@pytest.mark.parametrize('columns', [16, 20, 24, 40])
def test_hd44780_initialization_ddram_rows_and_backlight(backlight, active_high, columns):
    sent, delays = [], []
    Pcf8574Lcd(sent.append, sleep=delays.append, backlight_active_high=active_high, columns=columns).write_frame(
        ["ABC".ljust(columns), "123".ljust(columns)], backlight)
    nibbles = decode(sent)
    assert [value for value, _ in nibbles[:4]] == [0x30, 0x30, 0x30, 0x20]
    assert all(not data for _, data in nibbles[:4])
    pairs = [(nibbles[i][0] | (nibbles[i + 1][0] >> 4), nibbles[i][1])
             for i in range(4, len(nibbles), 2)]
    assert pairs[:5] == [(0x28, False), (0x08, False), (0x01, False), (0x06, False), (0x80, False)]
    assert pairs[5:5+columns] == [(ord(c), True) for c in "ABC".ljust(columns)]
    assert pairs[5+columns] == (0xC0, False)
    assert pairs[6+columns:6+2*columns] == [(ord(c), True) for c in "123".ljust(columns)]
    assert pairs[-1] == (0x0C, False)
    assert all(bool(byte & 8) == (backlight == active_high) for byte in sent)
    assert 0.05 in delays and 0.005 in delays and 0.002 in delays


def test_subsequent_frames_do_not_clear_or_reinitialize_the_lcd():
    sent = []
    Pcf8574Lcd(sent.append, sleep=lambda _: None).write_frame(["A" * 20, "B" * 20], True, initialize=False)
    nibbles = decode(sent)
    assert len(nibbles) == 84  # Two DDRAM addresses and exactly forty characters.
    assert nibbles[:2] == [(0x80, False), (0, False)]


def byte_pairs(raw):
    nibbles = decode(raw)
    return [(nibbles[index][0] | (nibbles[index + 1][0] >> 4), nibbles[index][1])
            for index in range(0, len(nibbles), 2)]


def test_seconds_update_writes_only_changed_clock_cells_without_clear():
    old = ['12:34:59'.ljust(20), 'BTC 123.45'.ljust(20)]
    new = ['12:35:00'.ljust(20), old[1]]
    sent = []
    Pcf8574Lcd(sent.append, sleep=lambda _: None).write_frame(new, True,
        initialize=False, previous={'lines': old, 'backlight': True})
    # Minute and seconds are disjoint dirty spans; unchanged colon is not sent.
    assert byte_pairs(sent) == [(0x84, False), (ord('5'), True),
                                (0x86, False), (ord('0'), True), (ord('0'), True)]


@pytest.mark.parametrize('columns,rows', [(16, 2), (20, 4)])
def test_diffs_respect_every_physical_row_boundary(columns, rows):
    old = [' ' * columns for _ in range(rows)]
    new = [line[:-1] + chr(65 + index) for index, line in enumerate(old)]
    sent = []
    Pcf8574Lcd(sent.append, sleep=lambda _: None, columns=columns, rows=rows).write_frame(
        new, True, initialize=False, previous={'lines': old, 'backlight': True})
    expected = []
    for index, offset in enumerate(hd44780_rows(columns, rows)):
        expected.extend([(0x80 | (offset + columns - 1), False), (65 + index, True)])
    assert byte_pairs(sent) == expected


def test_identical_acknowledged_frame_emits_no_encoder_writes():
    lines, sent = ['A' * 20, 'B' * 20], []
    Pcf8574Lcd(sent.append, sleep=lambda _: None).write_frame(lines, True,
        initialize=False, previous={'lines': list(lines), 'backlight': True})
    assert not sent


@pytest.mark.parametrize('active_high,backlight', [(True, True), (True, False), (False, True), (False, False)])
def test_backlight_only_edit_is_one_enable_low_control_byte(active_high, backlight):
    lines, sent = ['A' * 20, 'B' * 20], []
    Pcf8574Lcd(sent.append, backlight_active_high=active_high).write_frame(lines, backlight,
        initialize=False, previous={'lines': lines, 'backlight': not backlight})
    assert sent == [8 if backlight == active_high else 0]


def test_initialization_ignores_valid_previous_for_complete_first_frame():
    lines, fresh, previous = ['A' * 20, 'B' * 20], [], []
    Pcf8574Lcd(fresh.append, sleep=lambda _: None).write_frame(lines, True)
    Pcf8574Lcd(previous.append, sleep=lambda _: None).write_frame(lines, True,
        previous={'lines': list(lines), 'backlight': True})
    assert previous == fresh


@pytest.mark.parametrize('previous', [
    [], {}, {'lines': ['A' * 20, 'B' * 20], 'backlight': 1},
    {'lines': ['short', 'B' * 20], 'backlight': True},
    {'lines': ['\x00' * 20, 'B' * 20], 'backlight': True},
    {'lines': ['A' * 20], 'backlight': True},
    {'lines': ['A' * 20, 'B' * 20], 'backlight': True, 'address': 39},
])
def test_malformed_previous_is_rejected_before_encoder_initialization(previous):
    sent = []
    with pytest.raises(ValueError):
        Pcf8574Lcd(sent.append).write_frame(['A' * 20, 'B' * 20], True, previous=previous)
    assert not sent


@pytest.mark.parametrize('columns,rows',[(16,4),(20,4),(24,2),(40,2)])
def test_native_geometry_is_driver_data_not_a_core_size_catalog(columns,rows):
    sent=[]
    Pcf8574Lcd(sent.append,sleep=lambda _:None,columns=columns,rows=rows).write_frame(
        [chr(65+n)*columns for n in range(rows)],True,initialize=False)
    nibbles=decode(sent)
    pairs=[(nibbles[i][0]|(nibbles[i+1][0]>>4),nibbles[i][1]) for i in range(0,len(nibbles),2)]
    assert [value for value,data in pairs if not data] == [0x80|v for v in hd44780_rows(columns,rows)]
    assert len([v for v,data in pairs if data]) == columns*rows


@pytest.mark.parametrize('columns,rows',[(41,2),(21,4),(80,1),(20,3),(True,2)])
def test_unsupported_driver_topology_never_initializes(columns,rows):
    sent=[]
    with pytest.raises(ValueError):Pcf8574Lcd(sent.append,columns=columns,rows=rows)
    assert not sent


@pytest.mark.parametrize("line", ["short", "x" * 21, "\x00" * 20, "Ж" * 20])
def test_encoder_rejects_before_initializing(line):
    sent = []
    with pytest.raises(ValueError):
        Pcf8574Lcd(sent.append, sleep=lambda _: None).write_frame([line, " " * 20], True)
    assert sent == []


@pytest.mark.parametrize('columns', [16, 20])
def test_native_child_receives_fixed_parameters_and_deadline_not_a_shell(tmp_path, monkeypatch, columns):
    calls, acknowledgements = [], []
    class Child:
        def __init__(self):self.stdin, self.stdout = io.BytesIO(), io.BytesIO()
        def poll(self): return None
        def kill(self):pass
        def wait(self, *, timeout):
            assert timeout == .2
            return 0
    def start(args, **kwargs):
        child = Child()
        calls.append((args, kwargs, child))
        return child
    def acknowledge(self, deadline):
        acknowledgements.append(deadline-time.monotonic())
        return b'R\n' if len(acknowledgements) == 1 else b'O\n'
    monkeypatch.setattr(subprocess, "Popen", start)
    monkeypatch.setattr(NativeCharacterDisplay, '_read_ack', acknowledge)
    driver = NativeCharacterDisplay(CharacterDisplayProfileV1(driver="pcf8574", columns=columns), tmp_path)
    driver.prepare()  # Warm worker, but no frame payload/I2C operation.
    assert calls[0][2].stdin.getvalue() == b''
    deadline = datetime.now(UTC) + timedelta(seconds=0.5)
    driver.write_frame(["A" * columns, "B" * columns], True, not_after=deadline)
    driver.write_frame(["C" * columns, "D" * columns], False, not_after=deadline)
    assert len(calls) == 1
    args, options, child = calls[0]
    assert args[:3] == [sys.executable, "-I", "-c"] and not options.get("shell")
    frames = [json.loads(raw) for raw in child.stdin.getvalue().splitlines()]
    value = frames[0]
    assert value["bus"] == 1 and value["address"] == 0x27 and value["initialize"] is True
    assert frames[1]['initialize'] is False
    assert value['previous'] is None
    assert frames[1]['previous'] == {'lines': ['A' * columns, 'B' * columns], 'backlight': True}
    assert value['columns'] == columns
    assert 0 < value["deadline"] - time.monotonic() <= 0.5
    assert options['stdin'] == options['stdout'] == subprocess.PIPE
    assert options["stderr"] == subprocess.DEVNULL
    assert 0 < acknowledgements[0] <= 5 and all(0 < value <= .5 for value in acknowledgements[1:])
    assert Path(args[4]) == Path(__file__).resolve().parents[2]
    driver.close()


def test_native_timeout_is_bounded_and_cannot_spawn_over_an_unresolved_child(tmp_path, monkeypatch):
    events = []
    class Stuck:
        stdin, stdout = io.BytesIO(), io.BytesIO()
        def poll(self): return None
        def wait(self, *, timeout):
            events.append(timeout)
            raise subprocess.TimeoutExpired("display-worker", timeout)
        def kill(self): events.append("kill")
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: Stuck())
    replies = iter([b'R\n', TimeoutError()])
    def acknowledge(self, deadline):
        reply = next(replies)
        if isinstance(reply, Exception):raise reply
        return reply
    monkeypatch.setattr(NativeCharacterDisplay, '_read_ack', acknowledge)
    driver = NativeCharacterDisplay(CharacterDisplayProfileV1(driver="pcf8574"), tmp_path)
    with pytest.raises(TimeoutError, match="unknown"):
        driver.write_frame([" " * 20, " " * 20], False)
    assert events == ["kill", 0.2]
    assert driver._previous is None
    with pytest.raises(RuntimeError, match="unresolved"):
        driver.write_frame([" " * 20, " " * 20], False)


@pytest.mark.skipif(sys.platform != 'linux', reason='Native private pipe worker')
def test_prepared_real_child_does_not_repeat_cold_start_for_frames(tmp_path, monkeypatch):
    import agent.hardware.character_display as native
    recorded = tmp_path/'frames.jsonl'
    # Exercise the actual import/pipe/ack loop, with only the hardware writer
    # replaced in the child. No physical device or module installation.
    bootstrap = '''import sys,json,time
sys.path.insert(0,sys.argv[1])
import agent.character_display_worker as worker
time.sleep(.25)
def record(raw):
    with open(%r,'a') as stream:stream.write(raw+'\\n')
worker.write_once=record
worker.serve()
''' % str(recorded)
    monkeypatch.setattr(native, '_BOOTSTRAP', bootstrap)
    driver = NativeCharacterDisplay(CharacterDisplayProfileV1(driver='pcf8574',columns=16),tmp_path/'locks')
    try:
        driver.prepare()
        assert not recorded.exists() and not (tmp_path/'locks').exists()
        pid = driver._child.pid
        for text in ('A','B'):
            driver.write_frame([text*16,' '*16], True,
                not_after=datetime.now(UTC)+timedelta(seconds=2))
            assert driver._child.pid == pid
        frames=[json.loads(raw) for raw in recorded.read_text().splitlines()]
        assert len(frames)==2 and [row['initialize'] for row in frames]==[True,False]
        assert frames[0]['lines'][0]=='A'*16 and frames[1]['lines'][0]=='B'*16
    finally:
        driver.close()
    assert driver._child.poll() is not None


@pytest.mark.parametrize('failure', [b'E\n', b'T\n', b'R\n'])
def test_bad_frame_ack_closes_worker_without_another_request(tmp_path, monkeypatch, failure):
    child=SimpleNamespace(stdin=io.BytesIO(),stdout=io.BytesIO(),poll=lambda:None,
        kill=lambda:None,wait=lambda **kw:None)
    calls=[]
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**kw:calls.append(1) or child)
    replies=iter([b'R\n',failure])
    monkeypatch.setattr(NativeCharacterDisplay,'_read_ack',lambda *a:next(replies))
    driver=NativeCharacterDisplay(CharacterDisplayProfileV1(driver='pcf8574'),tmp_path)
    with pytest.raises((OSError,TimeoutError)):
        driver.write_frame(['A'*20,'B'*20],True)
    with pytest.raises(RuntimeError):driver.write_frame(['A'*20,'B'*20],True)
    assert calls==[1]


def test_expired_frame_never_starts_a_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**kw:pytest.fail('No worker after command expiry'))
    driver=NativeCharacterDisplay(CharacterDisplayProfileV1(driver='pcf8574'),tmp_path)
    with pytest.raises(TimeoutError):
        driver.write_frame(['A'*20,'B'*20],True,not_after=datetime.now(UTC)-timedelta(seconds=1))


@pytest.mark.parametrize('deadline', [True, '1', 0, -1, float('nan'), float('inf'), 2**53,
                                    pytest.param(10**1000, id='oversized-integer')])
def test_invalid_monotonic_deadline_precedes_worker_or_pipe_io(tmp_path, monkeypatch, deadline):
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('No worker for invalid deadline'))
    driver = NativeCharacterDisplay(CharacterDisplayProfileV1(driver='pcf8574'), tmp_path)
    with pytest.raises(ValueError):
        driver.write_frame(['A' * 20, 'B' * 20], True, monotonic_deadline=deadline)


def test_expired_monotonic_deadline_precedes_worker_io(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('No worker after scene expiry'))
    driver = NativeCharacterDisplay(CharacterDisplayProfileV1(driver='pcf8574'), tmp_path)
    with pytest.raises(TimeoutError):
        driver.write_frame(['A' * 20, 'B' * 20], True, monotonic_deadline=time.monotonic() - 1)


def test_monotonic_scene_bound_cannot_be_extended_by_wall_clock_rollback(tmp_path, monkeypatch):
    import agent.hardware.character_display as native
    current = [200.0]
    monkeypatch.setattr(native, 'time', SimpleNamespace(monotonic=lambda: current[0]))
    class Clock:
        calls = 0
        @classmethod
        def now(cls, _zone):
            cls.calls += 1
            return datetime(2026 if cls.calls == 1 else 2000, 1, 1, tzinfo=UTC)
    # Keep isinstance(deadline, datetime) validation while replacing its clock.
    class JumpingDatetime(datetime):
        @classmethod
        def now(cls, zone):
            return Clock.now(zone)
    monkeypatch.setattr(native, 'datetime', JumpingDatetime)
    child = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(), poll=lambda: None,
        kill=lambda: None, wait=lambda **kwargs: None)
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: child)
    replies = iter([b'R\n', b'O\n'])
    monkeypatch.setattr(NativeCharacterDisplay, '_read_ack', lambda *args: next(replies))
    driver = NativeCharacterDisplay(CharacterDisplayProfileV1(driver='pcf8574'), tmp_path)
    driver.write_frame(['A' * 20, 'B' * 20], True,
        not_after=JumpingDatetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC), monotonic_deadline=200.5)
    frame = json.loads(child.stdin.getvalue())
    assert frame['deadline'] == 200.5
    size = len(child.stdin.getvalue())
    current[0] = 200.5
    with pytest.raises(TimeoutError):
        driver.write_frame(['C' * 20, 'D' * 20], True, monotonic_deadline=200.5)
    assert len(child.stdin.getvalue()) == size
    driver.close()


def test_only_acknowledged_frames_seed_diffs_and_failure_discards_the_cache(tmp_path, monkeypatch):
    child = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(), poll=lambda: None,
        kill=lambda: None, wait=lambda **kwargs: None)
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: child)
    replies = iter([b'R\n', b'O\n', b'E\n'])
    monkeypatch.setattr(NativeCharacterDisplay, '_read_ack', lambda *args: next(replies))
    driver = NativeCharacterDisplay(CharacterDisplayProfileV1(driver='pcf8574'), tmp_path)
    lines = ['A' * 20, 'B' * 20]
    driver.write_frame(lines, True)
    lines[0] = 'Z' * 20  # Caller mutation cannot change the acknowledged cache.
    assert driver._previous == {'lines': ['A' * 20, 'B' * 20], 'backlight': True}
    with pytest.raises(OSError):
        driver.write_frame(lines, False)
    assert driver._previous is None and not driver._initialized


@pytest.mark.parametrize('failure',[None,'timeout','io'])
def test_worker_pipe_is_idle_until_frame_and_stops_after_failure(monkeypatch, failure):
    incoming=io.BytesIO(b'first\nsecond\n')
    outgoing=io.BytesIO()
    calls=[]
    monkeypatch.setattr(sys,'stdin',SimpleNamespace(buffer=incoming))
    monkeypatch.setattr(sys,'stdout',SimpleNamespace(buffer=outgoing))
    def write(raw):
        calls.append(raw)
        if failure=='timeout':raise TimeoutError
        if failure=='io':raise OSError
    monkeypatch.setattr('agent.character_display_worker.write_once',write)
    serve()
    assert outgoing.getvalue()==({'timeout':b'R\nT\n','io':b'R\nE\n'}.get(failure,b'R\nO\nO\n'))
    assert calls==(['first'] if failure else ['first','second'])


@pytest.mark.parametrize('content',[b'',b'x'*2050+b'\n',b'incomplete'])
def test_worker_eof_or_oversized_frame_never_reaches_hardware(monkeypatch, content):
    outgoing=io.BytesIO()
    monkeypatch.setattr(sys,'stdin',SimpleNamespace(buffer=io.BytesIO(content)))
    monkeypatch.setattr(sys,'stdout',SimpleNamespace(buffer=outgoing))
    monkeypatch.setattr('agent.character_display_worker.write_once',lambda *a:pytest.fail('No complete bounded frame'))
    serve()
    assert outgoing.getvalue()==b'R\n'


def worker_input(tmp_path, **changes):
    return {"bus": 1, "address": 0x27, "backlight_active_high": True, "columns": 20,
            "lines": ["A" * 20, "B" * 20], "rows":2, "backlight": True,
            "initialize": True, "deadline": time.monotonic() + 3,
            "lock_dir": str(tmp_path), "previous": None, **changes}


def fake_worker_os(monkeypatch, **methods):
    flags = {key: getattr(os, key) for key in ("O_CREAT", "O_RDWR", "O_CLOEXEC", "O_NOFOLLOW", "O_WRONLY")}
    monkeypatch.setattr("agent.character_display_worker.os", SimpleNamespace(**flags, **methods))


@pytest.mark.skipif(sys.platform != "linux", reason="Linux I2C syscall doubles")
@pytest.mark.parametrize("failure", [None, "short", "busy", "deadline", "not_device"])
@pytest.mark.parametrize('columns',[16,20])
def test_linux_worker_only_writes_the_fixed_device_and_never_forces_or_retries(tmp_path, monkeypatch, failure, columns):
    import fcntl
    opened, written, selected, closed = [], [], [], []
    def open_fd(path, flags, mode=0):
        opened.append(str(path))
        return 10 if len(opened) == 1 else 11
    def ioctl(fd, operation, address):
        selected.append((fd, operation, address))
        if failure == "busy": raise OSError("kernel owns address")
    def write(fd, value):
        written.append((fd, value))
        return 0 if failure == "short" else 1
    fake_worker_os(monkeypatch, open=open_fd, close=closed.append, write=write,
        fstat=lambda fd: SimpleNamespace(st_mode=stat.S_IFREG if failure == "not_device" else stat.S_IFCHR))
    monkeypatch.setattr(fcntl, "flock", lambda fd, flags: None)
    monkeypatch.setattr(fcntl, "ioctl", ioctl)
    monkeypatch.setattr("agent.character_display_worker.time", SimpleNamespace(monotonic=time.monotonic, sleep=lambda _: None))
    value = worker_input(tmp_path,columns=columns,lines=['A'*columns,'B'*columns])
    if failure == "deadline": value["deadline"] = time.monotonic() - 1
    if failure is None:
        write_once(json.dumps(value))
        assert written and closed == [11, 10]
    else:
        with pytest.raises((OSError, TimeoutError, ValueError)):
            write_once(json.dumps(value))
    if failure == "deadline":
        assert opened == [] and written == []
    else:
        assert opened == [str(tmp_path / "i2c-1-27.lock"), "/dev/i2c-1"]
        assert closed == [11, 10]
        assert selected == ([] if failure == "not_device" else [(11, 0x0703, 0x27)])
        if failure == "short": assert len(written) == 1
        if failure in {"busy", "not_device"}: assert written == []


@pytest.mark.skipif(sys.platform != "linux", reason="Linux I2C syscall doubles")
def test_kernel_lock_prevents_a_second_owner_without_opening_the_device(tmp_path, monkeypatch):
    import fcntl
    opens = []
    fake_worker_os(monkeypatch, open=lambda path, *args: opens.append(str(path)) or 10, close=lambda fd: None)
    def busy(*args): raise BlockingIOError("resource busy")
    monkeypatch.setattr(fcntl, "flock", busy)
    with pytest.raises(BlockingIOError):
        write_once(json.dumps(worker_input(tmp_path)))
    assert opens == [str(tmp_path / "i2c-1-27.lock")]


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux I2C syscall doubles')
def test_identical_worker_frame_does_not_open_lock_or_i2c(tmp_path, monkeypatch):
    value = worker_input(tmp_path, initialize=False,
        previous={'lines': ['A' * 20, 'B' * 20], 'backlight': True})
    fake_worker_os(monkeypatch, open=lambda *args: pytest.fail('Identical frame must not open hardware'))
    write_once(json.dumps(value))
    assert not tmp_path.joinpath('i2c-1-27.lock').exists()


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux I2C syscall doubles')
@pytest.mark.parametrize('initialize', [True, False])
def test_worker_validates_previous_before_any_lock_or_device_open(tmp_path, monkeypatch, initialize):
    fake_worker_os(monkeypatch, open=lambda *args: pytest.fail('Invalid prior frame must not open hardware'))
    with pytest.raises(ValueError):
        write_once(json.dumps(worker_input(tmp_path, initialize=initialize,
            previous={'lines': ['wrong'], 'backlight': True})))


@pytest.mark.skipif(sys.platform != "linux", reason="Linux I2C syscall doubles")
def test_deadline_mid_frame_stops_further_io_without_retry(tmp_path, monkeypatch):
    import fcntl
    value = worker_input(tmp_path, deadline=1.0)
    ticks = iter([0.0, 0.0, 0.0, 0.0, 2.0])
    calls = []
    monkeypatch.setattr("agent.character_display_worker.time", SimpleNamespace(monotonic=lambda: next(ticks), sleep=lambda _: None))
    fake_worker_os(monkeypatch, open=lambda *args: 10, close=lambda fd: None,
        fstat=lambda fd: SimpleNamespace(st_mode=stat.S_IFCHR), write=lambda fd, blob: calls.append(blob) or 1)
    monkeypatch.setattr(fcntl, "flock", lambda *args: None)
    monkeypatch.setattr(fcntl, "ioctl", lambda *args: None)
    with pytest.raises(TimeoutError):
        write_once(json.dumps(value))
    assert len(calls) == 1
