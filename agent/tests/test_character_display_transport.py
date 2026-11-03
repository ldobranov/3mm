"""No hardware: encoder, device API doubles, bounded worker supervision."""
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from agent.character_display_worker import Pcf8574Lcd, write_once, hd44780_rows
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
    calls = []
    class Child:
        def poll(self): return 0
        def wait(self, *, timeout):
            assert 0 < timeout <= 0.5
            return 0
    def start(args, **kwargs):
        calls.append((args, kwargs))
        return Child()
    monkeypatch.setattr(subprocess, "Popen", start)
    driver = NativeCharacterDisplay(CharacterDisplayProfileV1(driver="pcf8574", columns=columns), tmp_path)
    deadline = datetime.now(UTC) + timedelta(seconds=0.5)
    driver.write_frame(["A" * columns, "B" * columns], True, not_after=deadline)
    driver.write_frame(["C" * columns, "D" * columns], False, not_after=deadline)
    args, options = calls[0]
    assert args[:3] == [sys.executable, "-I", "-c"] and not options.get("shell")
    value = json.loads(args[-1])
    assert value["bus"] == 1 and value["address"] == 0x27 and value["initialize"] is True
    assert json.loads(calls[1][0][-1])["initialize"] is False
    assert value['columns'] == columns
    assert 0 < value["deadline"] - time.monotonic() <= 0.5
    assert options["stdout"] == subprocess.DEVNULL and options["stderr"] == subprocess.DEVNULL
    assert Path(args[4]) == Path(__file__).resolve().parents[2]
    driver.close()


def test_native_timeout_is_bounded_and_cannot_spawn_over_an_unresolved_child(tmp_path, monkeypatch):
    events = []
    class Stuck:
        def poll(self): return None
        def wait(self, *, timeout):
            events.append(timeout)
            raise subprocess.TimeoutExpired("display-worker", timeout)
        def kill(self): events.append("kill")
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: Stuck())
    driver = NativeCharacterDisplay(CharacterDisplayProfileV1(driver="pcf8574"), tmp_path)
    with pytest.raises(TimeoutError, match="unknown"):
        driver.write_frame([" " * 20, " " * 20], False)
    assert events[1:] == ["kill", 0.2]
    with pytest.raises(RuntimeError, match="unresolved"):
        driver.write_frame([" " * 20, " " * 20], False)


def worker_input(tmp_path, **changes):
    return {"bus": 1, "address": 0x27, "backlight_active_high": True, "columns": 20,
            "lines": ["A" * 20, "B" * 20], "rows":2, "backlight": True,
            "initialize": True, "deadline": time.monotonic() + 3,
            "lock_dir": str(tmp_path), **changes}


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
