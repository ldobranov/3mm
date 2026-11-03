"""Opt-in character display on the existing Agent command path."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from agent.module_runtime import ModuleLifecycleError
from agent.hardware.character_display import NativeCharacterDisplay
from three_mm_protocol.character_display import (
    CharacterDisplayProfileV1, DISPLAY_CAPABILITY,
)
from three_mm_protocol.capability_contracts import CapabilityContractError


class MockCharacterDisplay:
    """Memory only: construction, writes and close never access /dev or GPIO."""

    def __init__(self):
        self.frame: tuple[list[str], bool] | None = None

    def write_frame(self, lines: list[str], backlight: bool) -> None:
        self.frame = (list(lines), backlight)

    def close(self) -> None:
        self.frame = None


class CharacterDisplayService:
    def __init__(self, profile: CharacterDisplayProfileV1, *, lock_dir: Path):
        self.profile = profile
        self._driver = (MockCharacterDisplay() if profile.driver == "mock"
                        else NativeCharacterDisplay(profile, lock_dir))
        self._lock = RLock()
        self._closed = False
        self._failed = False
        self._last: tuple[list[str], bool] | None = None
        self._written_at = ""

    def validate_invocation(self, action: str, arguments: dict) -> None:
        with self._lock:
            if self._closed or self._failed:
                raise CapabilityContractError("Display runtime is unavailable")
            if action != "write_frame":
                raise CapabilityContractError("Unknown display action")
            self.profile.frame(arguments)

    def invoke(self, action: str, arguments: dict, *, not_after=None) -> dict:
        with self._lock:
            self.validate_invocation(action, arguments)
            frame = self.profile.frame(arguments)
            try:
                if self.profile.driver == "mock":
                    self._driver.write_frame(*frame)
                else:
                    self._driver.write_frame(*frame, not_after=not_after)
            except Exception:
                # A driver failure is not permission to replay or report an old
                # frame as current. The existing physical journal records unknown.
                self._failed = True
                self._last = None
                self._written_at = ""
                raise
            self._last = frame
            self._written_at = datetime.now(UTC).isoformat()
            return self.state_for(DISPLAY_CAPABILITY)

    def state_for(self, capability_id: str) -> dict:
        if capability_id != DISPLAY_CAPABILITY:
            return {}
        with self._lock:
            frame = self._last or ([" " * self.profile.columns] * self.profile.rows, False)
            return {"display_id": self.profile.display_id,
                    "profile_sha256": self.profile.digest(),
                    "text": '\n'.join(frame[0]), "backlight": frame[1],
                    "columns": self.profile.columns, "rows": self.profile.rows,
                    "last_write_at": self._written_at,
                    "has_frame": self._last is not None, "simulated": self.profile.driver == "mock"}

    def is_available(self) -> bool:
        with self._lock:
            return (not self._closed and not self._failed
                    and (not hasattr(self._driver, "is_available") or self._driver.is_available()))

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._last = None
            self._written_at = ""
            self._driver.close()


def character_display_handler(*, native_allowed: bool = False, lock_dir: Path):
    """Module runtime admits exact installation consent; never application rights."""
    def activate(manifest, _data_dir):
        profile = CharacterDisplayProfileV1.model_validate(manifest.configuration_defaults)
        if profile.driver not in {'mock', 'pcf8574'}:
            raise ModuleLifecycleError('Display driver is not installed in this Agent')
        if profile.driver == "pcf8574" and not native_allowed:
            raise ModuleLifecycleError("Physical display requires the native Agent hardware profile")
        registrations = [item for item in manifest.registrations if item.kind == "capability"]
        if (set(manifest.permissions) != {"hardware.display"}
                or len(registrations) != 1
                or registrations[0].registration_id != DISPLAY_CAPABILITY
                or registrations[0].contract != profile.contract()
                or registrations[0].metadata.get('profile_sha256') != profile.digest()
                or registrations[0].metadata.get('simulated') is not (profile.driver == 'mock')):
            raise ModuleLifecycleError("Display requires its exact profile-bound capability contract")
        return {DISPLAY_CAPABILITY: CharacterDisplayService(profile, lock_dir=lock_dir)}

    return activate
