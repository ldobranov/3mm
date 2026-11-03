"""Lazy, bounded native display transport; no device I/O at activation/probe."""
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

from three_mm_protocol.character_display import CharacterDisplayProfileV1
from agent.character_display_worker import hd44780_rows

WRITE_TIMEOUT_SECONDS = 3
_BOOTSTRAP = """import sys
sys.path.insert(0,sys.argv[1])
from agent.character_display_worker import write_once
write_once(sys.argv[2])
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

    def is_available(self) -> bool:
        """Path/permissions only, not an I2C transaction or LCD readback."""
        if sys.platform != "linux":
            return False
        path = f"/dev/i2c-{self.profile.bus}"
        try:
            return stat.S_ISCHR(os.stat(path, follow_symlinks=False).st_mode) and os.access(path, os.W_OK)
        except OSError:
            return False

    def write_frame(self, lines: list[str], backlight: bool, *, not_after=None) -> None:
        if self._child is not None and self._child.poll() is None:
            raise RuntimeError("Previous I2C worker is unresolved; no new attempt is permitted")
        budget = WRITE_TIMEOUT_SECONDS
        if not_after is not None:
            budget = min(budget, (not_after - datetime.now(UTC)).total_seconds())
        if budget <= 0:
            raise TimeoutError("Display command expired before worker creation")
        deadline = time.monotonic() + budget
        # This path also resolves inside immutable Agent service.pyz. The child
        # imports only stdlib/Agent worker code, no Pydantic/Core/vendor startup.
        code_root = Path(__file__).resolve().parents[2]
        payload = json.dumps({"bus": self.profile.bus, "address": self.profile.address,
            "columns": self.profile.columns, "rows": self.profile.rows,
            "backlight_active_high": self.profile.backlight_active_high, "lock_dir": str(self.lock_dir),
            "lines": lines, "backlight": backlight,
            "initialize": not self._initialized, "deadline": deadline})
        if len(payload.encode()) > 2048:
            raise ValueError("Display worker input exceeds its fixed budget")
        child = subprocess.Popen([sys.executable, "-I", "-c", _BOOTSTRAP, str(code_root), payload],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True, env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"})
        self._child = child
        try:
            status = child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            self.close()
            raise TimeoutError("Display write deadline exceeded; outcome unknown") from exc
        if status != 0:
            raise OSError("Display worker failed; outcome unknown, no automatic retry")
        self._initialized = True

    def close(self) -> None:
        self._initialized = False
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
