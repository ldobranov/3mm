"""Prepared, bounded native display transport; no device I/O at activation/probe."""
from datetime import UTC, datetime
import json
import logging
import math
import os
from pathlib import Path
import select
import stat
import subprocess
import sys
import time

from packages.protocol.character_display import CharacterDisplayProfileV1
from agent.character_display_worker import hd44780_rows, validate_frame

WRITE_TIMEOUT_SECONDS = 3
PREPARE_TIMEOUT_SECONDS = 5
RECOVERY_BACKOFF_SECONDS = 10
logger = logging.getLogger(__name__)
_BOOTSTRAP = """import sys
sys.path.insert(0,sys.argv[1])
from agent.character_display_worker import serve
serve()
"""


class NativeCharacterDisplay:
    def __init__(self, profile: CharacterDisplayProfileV1, lock_dir: Path):
        hd44780_rows(profile.columns, profile.rows)
        if (profile.controller != 'hd44780' or profile.pin_map != 'rs0_rw1_e2_bl3_d4_7'
                or not 0x20 <= profile.address <= 0x27):
            raise ValueError('Unsupported PCF8574T hardware profile')
        self.profile = profile
        self.lock_dir = lock_dir.resolve()
        self._child = None
        self._initialized = False
        self._prepared = False
        self._in_flight = False
        self._closed = False
        self._retired = False
        self._retry_at = 0.0
        self._previous = None  # Only a fully acknowledged frame may seed a diff.

    def device_available(self) -> bool:
        """Path/permissions only, not an I2C transaction or LCD readback."""
        if sys.platform != "linux" or self._closed:
            return False
        path = f"/dev/i2c-{self.profile.bus}"
        try:
            return stat.S_ISCHR(os.stat(path, follow_symlinks=False).st_mode) and os.access(path, os.W_OK)
        except OSError:
            return False

    def is_available(self) -> bool:
        """Non-mutating readiness: an accessible bus and a prepared live child."""
        return (self.device_available() and not self._retired and self._prepared
                and self._child is not None and self._child.poll() is None)

    def maintain(self) -> bool:
        """Prepare code only, outside command execution; never replay a frame.

        A killed child can remain in uninterruptible kernel I/O. Keep its Popen
        identity and refuse a replacement until poll() proves its actual exit.
        """
        if self._closed:
            return False
        if self.is_available():
            return True
        if self._prepared:  # An idle prepared worker died between commands.
            self._retire_worker()
        if time.monotonic() < self._retry_at:
            return False
        if self._child is not None and self._child.poll() is None:
            return False
        if not self.device_available():
            return False
        self._child = None
        self._in_flight = False
        self._retired = False
        try:
            self.prepare()
        except Exception as exc:
            logger.warning("Character display worker preparation failed: %s", type(exc).__name__)
            return False
        logger.info("Character display worker prepared; no frame restored")
        return self.is_available()

    def _read_ack(self, deadline):
        data = bytearray()
        while len(data) < 2:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self._child.stdout], [], [], remaining)[0]:
                raise TimeoutError('Display worker acknowledgement deadline exceeded')
            chunk = os.read(self._child.stdout.fileno(), 2 - len(data))
            if not chunk:
                raise OSError('Display worker exited before acknowledgement')
            data.extend(chunk)
        if time.monotonic() >= deadline:
            raise TimeoutError('Display worker acknowledgement arrived too late')
        return bytes(data)

    @staticmethod
    def _deadline(budget, *, not_after=None, monotonic_deadline=None):
        now = time.monotonic()
        if monotonic_deadline is not None and (
                type(monotonic_deadline) not in (int, float)
                or not 0 < monotonic_deadline <= 2**53 - 1
                or not math.isfinite(monotonic_deadline)):
            raise ValueError('Invalid display monotonic deadline')
        deadline = now + budget
        if not_after is not None:
            if not isinstance(not_after, datetime) or not_after.utcoffset() is None:
                raise ValueError('Display command requires an aware UTC deadline')
            deadline = min(deadline, now + (not_after - datetime.now(UTC)).total_seconds())
        if monotonic_deadline is not None:
            deadline = min(deadline, monotonic_deadline)
        if deadline <= now:
            raise TimeoutError('Display command deadline expired')
        return deadline

    def prepare(self, *, not_after=None, monotonic_deadline=None) -> None:
        """Warm Agent code only. No frame, saved content or I2C is sent here."""
        if self._closed or self._retired or self._in_flight:
            raise RuntimeError('Display worker is closed or unresolved')
        deadline = self._deadline(PREPARE_TIMEOUT_SECONDS, not_after=not_after,
                                  monotonic_deadline=monotonic_deadline)
        if self._prepared:
            if self._child.poll() is not None:
                raise OSError('Prepared display worker exited')
            return
        # An immutable service.pyz is also a valid import root. Keep the child
        # private to this provider; it waits on its pipe and never polls I2C.
        code_root = Path(__file__).resolve().parents[2]
        try:
            self._child = subprocess.Popen([sys.executable, "-I", "-c", _BOOTSTRAP, str(code_root)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
                close_fds=True, env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"})
            if self._read_ack(deadline) != b'R\n':
                raise OSError('Display worker preparation failed')
        except Exception:
            self._retire_worker()
            raise
        self._prepared = True

    def write_frame(self, lines: list[str], backlight: bool, *, not_after=None,
                    monotonic_deadline=None) -> None:
        if self._in_flight or self._closed or self._retired:
            raise RuntimeError("Previous I2C worker is unresolved or closed; no new attempt is permitted")
        validate_frame(lines, backlight, columns=self.profile.columns, rows=self.profile.rows)
        # Validate the trusted monotonic bound before any process/pipe work.
        self._deadline(WRITE_TIMEOUT_SECONDS, not_after=not_after,
                       monotonic_deadline=monotonic_deadline)
        self.prepare(not_after=not_after, monotonic_deadline=monotonic_deadline)
        deadline = self._deadline(WRITE_TIMEOUT_SECONDS, not_after=not_after,
                                  monotonic_deadline=monotonic_deadline)
        payload = json.dumps({"bus": self.profile.bus, "address": self.profile.address,
            "columns": self.profile.columns, "rows": self.profile.rows,
            "backlight_active_high": self.profile.backlight_active_high, "lock_dir": str(self.lock_dir),
            "lines": lines, "backlight": backlight,
            "initialize": not self._initialized, "deadline": deadline,
            "previous": self._previous})
        raw = payload.encode()
        if len(raw) > 2048:
            raise ValueError("Display worker input exceeds its fixed budget")
        self._in_flight = True
        try:
            if self._child.stdin.write(raw + b'\n') != len(raw) + 1:
                raise OSError('Short display worker request')
            acknowledgement = self._read_ack(deadline)
            if acknowledgement == b'T\n':
                raise TimeoutError('Display worker deadline exceeded')
            if acknowledgement != b'O\n':
                raise OSError('Display worker failed')
        except TimeoutError as exc:
            self._retire_worker()
            logger.warning("Character display frame outcome unknown: timeout")
            raise TimeoutError("Display write deadline exceeded; outcome unknown") from exc
        except Exception as exc:
            self._retire_worker()
            logger.warning("Character display frame outcome unknown: %s", type(exc).__name__)
            raise OSError("Display worker failed; outcome unknown, no automatic retry") from exc
        self._in_flight = False
        self._initialized = True
        self._previous = {'lines': list(lines), 'backlight': backlight}

    def close(self) -> None:
        self._closed = True
        self._retire_worker()

    def _retire_worker(self) -> None:
        self._retired = True
        self._retry_at = time.monotonic() + RECOVERY_BACKOFF_SECONDS
        self._initialized = False
        self._previous = None
        self._prepared = False
        child = self._child
        if child is not None and child.poll() is None:
            try:
                child.kill()
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                # Never block the Agent on an uninterruptible kernel I/O. The
                # child's resource lock survives until that process actually exits.
                pass
        if child is not None:
            for stream in (child.stdin, child.stdout):
                if stream is not None:
                    stream.close()
