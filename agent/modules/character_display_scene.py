"""Volatile local clock scenes admitted once, renewed only by fresh commands.

No Core/SDK/HTTP calls occur on a tick. The normal command path authorizes each
finite scene; it does not authorize restoring one at restart or renewing receipts.
"""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import threading
import time

from agent.modules.character_display import CharacterDisplayService, approved_display_profile
from three_mm_protocol.character_display import DISPLAY_CAPABILITY
from three_mm_protocol.character_clock import render_clock_fields
from three_mm_protocol.character_display_scene import CharacterDisplaySceneProfileV1, MAX_SCENE_LEASE_SECONDS
from three_mm_protocol.capability_contracts import CapabilityContractError

MAX_SCENE_IDENTITIES = 64
IDENTITY_RETENTION_SECONDS = 2 * MAX_SCENE_LEASE_SECONDS


@dataclass(frozen=True)
class _Scene:
    identity: str
    sequence: int
    lines: tuple
    fields: tuple
    zone: object
    backlight: bool
    valid_until_ms: int
    deadline: float


class CharacterDisplaySceneService(CharacterDisplayService):
    def __init__(self, profile, *, lock_dir, wall_clock=None, monotonic=None, background=True):
        super().__init__(profile, lock_dir=lock_dir)
        self._wall_clock = wall_clock or time.time
        self._monotonic = monotonic or time.monotonic
        self._condition = threading.Condition(self._lock)
        self._scene = None
        self._identities = {}
        self._next_tick = None
        self._thread = None
        if background:
            self._thread = threading.Thread(target=self._worker, name='3mm-display-clock', daemon=True)
            self._thread.start()

    def _expire(self):
        if self._scene is not None and self._monotonic() >= self._scene.deadline:
            self._scene = None
            self._next_tick = None

    def _record(self, identity, sequence, *, closed=False):
        now = self._monotonic()
        self._identities = {key: value for key, value in self._identities.items() if value[2] > now}
        old = self._identities.get(identity)
        if old is not None and (old[1] or sequence <= old[0]):
            # A fresh duplicate command cannot refresh an old lease. The command
            # journal returns its existing receipt without calling this method.
            raise CapabilityContractError('Scene identity was stopped or sequence is stale')
        if old is None and len(self._identities) >= MAX_SCENE_IDENTITIES:
            raise CapabilityContractError('Local scene identity budget is full')
        self._identities[identity] = (sequence, closed, now + IDENTITY_RETENTION_SECONDS)

    def _cancel_active(self, *, retire=False):
        if self._scene is not None and retire:
            old = self._scene
            self._identities[old.identity] = (old.sequence, True,
                self._monotonic() + IDENTITY_RETENTION_SECONDS)
        self._scene = None
        self._next_tick = None
        self._condition.notify_all()

    def validate_invocation(self, action, arguments):
        with self._lock:
            if self._closed or self._failed and action != 'stop_scene':
                raise CapabilityContractError('Display runtime is unavailable')
            if action == 'write_frame':
                self.profile.frame(arguments)
            elif action == 'set_scene':
                self.profile.scene(arguments, now_ms=int(self._wall_clock() * 1000))
            elif action == 'stop_scene':
                self.profile.stop(arguments)
            else:
                raise CapabilityContractError('Unknown display scene action')

    def _write(self, scene, *, not_after=None):
        remaining = scene.deadline - self._monotonic()
        if remaining <= 0:
            raise TimeoutError('Local scene lease expired before a write')
        instant = self._wall_clock()
        lines = render_clock_fields(scene.lines, scene.fields, scene.zone, instant)
        if self.profile.driver == 'mock':
            self._driver.write_frame(lines, scene.backlight)
        else:
            # The private child bounds every byte by the monotonic lease even
            # if wall time changes during its normal per-frame I/O budget.
            ceiling = datetime.now(UTC) + timedelta(seconds=remaining)
            self._driver.write_frame(lines, scene.backlight,
                not_after=min(not_after, ceiling) if not_after is not None else ceiling,
                monotonic_deadline=scene.deadline)
        if self._monotonic() >= scene.deadline:
            raise TimeoutError('Local scene lease expired during a write')
        self._last = (lines, scene.backlight)
        self._written_at = datetime.fromtimestamp(self._wall_clock(), UTC).isoformat()
        # Align to the next real second; delayed ticks render now, never replay
        # missed seconds or spin through a catch-up queue.
        self._next_tick = self._monotonic() + max(0.001, 1.0 - self._wall_clock() % 1.0)

    def invoke(self, action, arguments, *, not_after=None):
        with self._condition:
            self.validate_invocation(action, arguments)
            if not_after is not None and not_after <= datetime.now(UTC):
                raise TimeoutError('Scene command expired before execution')
            if action == 'write_frame':
                self._cancel_active(retire=True)
                return super().invoke(action, arguments, not_after=not_after)
            identity, sequence = arguments['scene_id'], arguments['sequence']
            if action == 'stop_scene':
                self._record(identity, sequence, closed=True)
                if self._scene is not None and self._scene.identity == identity:
                    self._cancel_active()
                return {'display_id': self.profile.display_id, 'profile_sha256': self.profile.digest(),
                    'scene_id': identity, 'scene_sequence': sequence, 'scene_stopped': True,
                    'simulated': self.profile.driver == 'mock'}
            frame, fields, zone, remaining = self.profile.scene(arguments, now_ms=int(self._wall_clock() * 1000))
            scene = _Scene(identity, sequence, tuple(frame[0]), fields, zone, frame[1],
                arguments['valid_until_ms'], self._monotonic() + remaining)
            self._record(identity, sequence)
            self._cancel_active(retire=self._scene is not None and self._scene.identity != identity)
            try:
                self._write(scene, not_after=not_after)
            except Exception:
                self._failed = True
                self._last = None
                self._written_at = ''
                raise
            self._scene = scene
            self._condition.notify_all()
            return {**self.state_for(DISPLAY_CAPABILITY), 'scene_accepted': True}

    def tick(self):
        """One local due tick; also an injectable-clock boundary for tests."""
        with self._condition:
            self._expire()
            if self._closed or self._failed or self._scene is None:
                return
            if self._next_tick is not None and self._monotonic() < self._next_tick:
                return
            if not self._scene.fields:
                self._next_tick = None
                return
            try:
                self._write(self._scene)
            except Exception:
                # The native driver retires its child. No tick, maintain() or
                # restart may replay the failed scene or claim its old text.
                self._cancel_active()
                self._failed = True
                self._last = None
                self._written_at = ''

    def _worker(self):
        while True:
            with self._condition:
                if self._closed:
                    return
                self._expire()
                if self._scene is None:
                    self._condition.wait()
                    continue
                due = self._scene.deadline
                if self._next_tick is not None:
                    due = min(due, self._next_tick)
                delay = max(0, due - self._monotonic())
                if delay > 0:
                    self._condition.wait(timeout=delay)
                    continue
            self.tick()

    def state_for(self, capability_id):
        if capability_id != DISPLAY_CAPABILITY:
            return {}
        with self._lock:
            self._expire()
            state = super().state_for(capability_id)
            scene = self._scene
            return {**state, 'scene_id': scene.identity if scene is not None else '',
                'scene_sequence': scene.sequence if scene is not None else 0,
                'scene_active': scene is not None,
                'scene_valid_until_ms': scene.valid_until_ms if scene is not None else 0}

    def maintain(self):
        if not self._lock.acquire(blocking=False):
            return
        try:
            if self._failed or (self.profile.driver != 'mock' and not self._driver.is_available()):
                self._cancel_active()
            super().maintain()  # Code preparation only; no scene restoration.
        finally:
            self._lock.release()

    def close(self):
        with self._condition:
            self._cancel_active(retire=True)
            super().close()
            self._condition.notify_all()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=0.5)


def character_display_scene_handler(*, native_allowed=False, lock_dir):
    def activate(manifest, _data_dir):
        profile = approved_display_profile(manifest, CharacterDisplaySceneProfileV1, native_allowed=native_allowed)
        return {DISPLAY_CAPABILITY: CharacterDisplaySceneService(profile, lock_dir=lock_dir)}
    return activate
