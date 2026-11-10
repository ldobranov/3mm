"""Fixed HD44780/PCF8574 transport, outside the Core and bounded by a child.

No bus scan, SMBus register prefix, address override, I2C_SLAVE_FORCE, kernel
configuration or device access during construction/probing. The only physical
entry is write_once, called for an already-authorized frame in a private
Agent-code child. See modules/character-display/README.md for the wiring profile.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import time
import math


def serve():
    """One prepared provider child; no I/O until a bounded frame arrives.

    There is no queue/retry or saved frame. EOF closes the standby worker. A
    failure closes it too, preventing another request after uncertain output.
    """
    import sys
    incoming, outgoing = sys.stdin.buffer, sys.stdout.buffer
    outgoing.write(b'R\n')
    outgoing.flush()
    while True:
        raw = incoming.readline(2049)
        if not raw:
            return
        if len(raw) > 2049 or not raw.endswith(b'\n'):
            return
        try:
            write_once(raw[:-1].decode('utf-8'))
        except TimeoutError:
            outgoing.write(b'T\n')
            outgoing.flush()
            return
        except Exception:
            outgoing.write(b'E\n')
            outgoing.flush()
            return
        outgoing.write(b'O\n')
        outgoing.flush()


def hd44780_rows(columns, rows):
    """Driver-owned DDRAM layout for standard two/four-row single controllers.

    Two physical 40-character DDRAM banks; four-row modules split each bank.
    Other controllers/topologies require another driver, not Core changes.
    """
    if (type(columns) is not int or type(rows) is not int or rows not in (2, 4)
            or not 1 <= columns <= (40 if rows == 2 else 20)):
        raise ValueError("Unsupported single-controller HD44780 geometry")
    return (0, 0x40) if rows == 2 else (0, 0x40, columns, 0x40 + columns)


def validate_frame(lines, backlight, *, columns, rows, previous=None):
    """Validate current and acknowledged prior rows before any physical I/O."""
    def exact_rows(value):
        return (type(value) is list and len(value) == rows
                and all(type(line) is str and len(line) == columns
                        and all(0x20 <= ord(char) <= 0x7E for char in line)
                        for line in value))
    if type(backlight) is not bool or not exact_rows(lines):
        raise ValueError("LCD transport requires exact padded printable-ASCII rows")
    if previous is not None and (
            type(previous) is not dict or set(previous) != {'lines', 'backlight'}
            or type(previous['backlight']) is not bool or not exact_rows(previous['lines'])):
        raise ValueError("LCD transport requires an exact acknowledged previous frame")


class Pcf8574Lcd:
    """4-bit encoding with fixed P0=RS,P1=RW(low),P2=E,P3=BL,P4..7=D4..7."""

    def __init__(self, write_byte, *, sleep=None, backlight_active_high=True, columns=20, rows=2):
        self._offsets = hd44780_rows(columns, rows)
        self._columns = columns
        self._write = write_byte
        self._sleep = time.sleep if sleep is None else sleep
        self._active_high = backlight_active_high
        self._backlight = 0

    def _nibble(self, value: int, *, data: bool = False) -> None:
        low = (value & 0xF0) | self._backlight | int(data)
        self._write(low)
        self._sleep(0.00005)  # Data setup; E was low, RW stays low.
        self._write(low | 0x04)
        self._sleep(0.00005)
        self._write(low)
        self._sleep(0.00005)

    def _byte(self, value: int, *, data: bool = False) -> None:
        self._nibble(value, data=data)
        self._nibble(value << 4, data=data)
        self._sleep(0.002 if not data and value in (0x01, 0x02) else 0.00005)

    def write_frame(self, lines: list[str], backlight: bool, *, initialize: bool = True,
                    previous=None) -> None:
        # Validate before even initialization, including direct trusted callers.
        validate_frame(lines, backlight, columns=self._columns, rows=len(self._offsets),
                       previous=previous)
        if type(initialize) is not bool:
            raise ValueError("LCD initialization flag must be boolean")
        self._backlight = 0x08 if backlight == self._active_high else 0
        # Re-synchronize after an interrupted 4-bit transfer. Initialization is
        # part of this explicit write, never an activation/restart side effect.
        if initialize:
            self._sleep(0.05)
            for delay in (0.005, 0.0002, 0.0002):
                self._nibble(0x30)
                self._sleep(delay)
            self._nibble(0x20)
            self._byte(0x28)  # Four bits, two rows, 5x8 font.
            self._byte(0x08)  # Display off during initialization (not atomic).
            self._byte(0x01)  # Clear/reset shift according to initialization sequence.
            self._byte(0x06)  # Increment, no shift.
        if initialize or previous is None:
            for offset, line in zip(self._offsets, lines):
                self._byte(0x80 | offset)
                for char in line:
                    self._byte(ord(char), data=True)
        else:
            changed = False
            for offset, line, old in zip(self._offsets, lines, previous['lines']):
                index = 0
                while index < self._columns:
                    if line[index] == old[index]:
                        index += 1
                        continue
                    start = index
                    while index < self._columns and line[index] != old[index]:
                        index += 1
                    self._byte(0x80 | (offset + start))
                    for char in line[start:index]:
                        self._byte(ord(char), data=True)
                    changed = True
            if not changed and previous['backlight'] != backlight:
                # PCF8574 backlight bit changes with E/RW low; no LCD command,
                # clear or cursor movement is needed for a backlight-only edit.
                self._write(self._backlight)
        if initialize:
            self._byte(0x0C)  # Display on, cursor/blink off, only after the full write.


def write_once(raw: str) -> None:
    """Linux-only child entry. No endpoint or application-visible raw-I2C action."""
    import fcntl

    if len(raw.encode()) > 2048:
        raise ValueError("Display worker input is too large")
    value = json.loads(raw)
    if (not isinstance(value, dict) or set(value) != {"bus", "address", "backlight_active_high",
            "lines", "rows", "backlight", "initialize", "deadline", "lock_dir", "columns", "previous"}
            or type(value["bus"]) is not int or not 0 <= value["bus"] <= 255
            or type(value["address"]) is not int or not 0x20 <= value["address"] <= 0x27
            or any(type(value[key]) is not bool for key in ("backlight", "backlight_active_high", "initialize"))
            or type(value["deadline"]) not in (int, float) or not math.isfinite(value["deadline"])
            or type(value["lock_dir"]) is not str or not Path(value["lock_dir"]).is_absolute()):
        raise ValueError("Invalid fixed-profile display worker input")
    hd44780_rows(value['columns'], value['rows'])
    validate_frame(value['lines'], value['backlight'], columns=value['columns'], rows=value['rows'],
                   previous=value['previous'])
    def check_deadline():
        if time.monotonic() >= value["deadline"]:
            raise TimeoutError("Display command deadline expired")
    check_deadline()
    if (not value['initialize'] and value['previous'] is not None
            and value['previous']['lines'] == value['lines']
            and value['previous']['backlight'] == value['backlight']):
        return  # Even a bus open/lock is unnecessary for an identical frame.
    lock_dir = Path(value["lock_dir"])
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = lock_dir / f"i2c-{value['bus']}-{value['address']:02x}.lock"
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check_deadline()
        fd = os.open(f"/dev/i2c-{value['bus']}", os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            if not stat.S_ISCHR(os.fstat(fd).st_mode):
                raise ValueError("I2C path must be a character device")
            check_deadline()
            fcntl.ioctl(fd, 0x0703, value["address"])  # I2C_SLAVE, never FORCE.
            def write_byte(byte: int) -> None:
                check_deadline()
                if os.write(fd, bytes([byte])) != 1:
                    raise OSError("Short I2C write")
            Pcf8574Lcd(write_byte, backlight_active_high=value["backlight_active_high"],
                columns=value["columns"], rows=value['rows']).write_frame(
                value["lines"], value["backlight"], initialize=value["initialize"],
                previous=value['previous'])
        finally:
            os.close(fd)
    finally:
        os.close(lock_fd)
