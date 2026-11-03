"""Process-local, bounded HTTP failure metadata. No bodies, credentials or I/O."""
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
import math
import re
import threading
import time
import uuid

from three_mm_protocol.diagnostics import REASONS, STAGES


TRACE_HEADER = b'x-3mm-trace-id'
_TRACE = re.compile(r'invoke_[0-9a-f]{32}\Z')
_ROUTE = re.compile(r'/[A-Za-z0-9_./{}:-]{0,255}\Z')
_METHODS = {'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'}
_PHASES = {'unknown': 0, 'not_dispatched': 1, 'execution_unconfirmed': 2, 'completed': 3}
_REASONS = REASONS | {'unclassified_conflict', 'server_error'}
_STAGES = set(STAGES) | {'http.response'}
_current = ContextVar('core_http_failure', default=None)


@dataclass
class _RequestState:
    trace_id: str
    phase: str = 'unknown'
    details: list = field(default_factory=list)
    active: bool = True
    lock: object = field(default_factory=threading.Lock, repr=False)


def current_trace_id(fallback):
    state = _current.get()
    return state.trace_id if state is not None and state.active else fallback


def note_failure(stage, reason):
    """Keep original typed causes before adapters redact them. Best effort only."""
    state = _current.get()
    if (state is None or type(stage) is not str or stage not in _STAGES or
            type(reason) is not str or reason not in _REASONS or reason == 'ok'):
        return
    if not state.lock.acquire(blocking=False):
        return
    try:
        if state.active and len(state.details) < 6 and (stage, reason) not in state.details:
            state.details.append((stage, reason))
    finally:
        state.lock.release()


def note_dispatch(phase):
    state = _current.get()
    if state is None or type(phase) is not str or phase not in _PHASES:
        return
    if not state.lock.acquire(blocking=False):
        return
    try:
        # A later refusal cannot turn a possibly dispatched request into an
        # unsent one. These are observations, never a permit or replay decision.
        if state.active and _PHASES[phase] > _PHASES[state.phase]:
            state.phase = phase
    finally:
        state.lock.release()


class RecentHttpFailures:
    MAX_RECORDS = 100
    MAX_BYTES = 128 * 1024  # Serialized metadata; fixed Python object overhead is bounded too.
    RETENTION_SECONDS = 15 * 60
    RATE = 10

    def __init__(self, *, clock=time.monotonic, wall=time.time):
        self._clock, self._wall = clock, wall
        self._lock = threading.Lock()
        self._records = deque()
        self._bytes = self._window_count = 0
        self._window = None
        self._dropped = dict.fromkeys(('rate', 'busy', 'invalid', 'evicted', 'expired'), 0)

    def _drop(self, kind):
        self._dropped[kind] = min(2**63 - 1, self._dropped[kind] + 1)

    def _expire(self, now):
        while self._records and now - self._records[0][0] >= self.RETENTION_SECONDS:
            _, size, _ = self._records.popleft()
            self._bytes -= size
            self._drop('expired')

    def record(self, *, trace_id, method, route, status, duration_ms, phase='unknown', details=()):
        if (type(trace_id) is not str or not _TRACE.fullmatch(trace_id) or
                type(method) is not str or method not in _METHODS or
                type(route) is not str or route != '[unmatched]' and not _ROUTE.fullmatch(route) or
                type(status) is not int or not (status == 409 or 500 <= status <= 599) or
                type(phase) is not str or phase not in _PHASES or
                type(duration_ms) not in (int, float) or not math.isfinite(duration_ms) or
                not 0 <= duration_ms <= 86400000 or type(details) not in (list, tuple) or len(details) > 6):
            self._drop('invalid')
            return
        if any(type(item) not in (list, tuple) or len(item) != 2 or
               type(item[0]) is not str or item[0] not in _STAGES or
               type(item[1]) is not str or item[1] not in _REASONS or item[1] == 'ok' for item in details):
            self._drop('invalid')
            return
        if not self._lock.acquire(blocking=False):
            self._drop('busy')
            return
        try:
            now = self._clock()
            self._expire(now)
            window = int(now)
            if window != self._window:
                self._window, self._window_count = window, 0
            if self._window_count >= self.RATE:
                self._drop('rate')
                return
            stage, reason = details[0] if details else (
                'http.response', 'unclassified_conflict' if status == 409 else 'server_error')
            value = dict(trace_id=trace_id, timestamp=self._wall(), method=method, route=route,
                status=status, duration_ms=round(duration_ms, 3), stage=stage, reason=reason,
                phase=phase, retryable=False,
                details=[dict(stage=stage, reason=reason) for stage, reason in details])
            size = len(json.dumps(value, separators=(',', ':'), allow_nan=False).encode('utf-8'))
            if size > 2048:
                self._drop('invalid')
                return
            while self._records and (len(self._records) >= self.MAX_RECORDS or self._bytes + size > self.MAX_BYTES):
                _, removed, _ = self._records.popleft()
                self._bytes -= removed
                self._drop('evicted')
            self._records.append((now, size, value))
            self._bytes += size
            self._window_count += 1
        finally:
            self._lock.release()

    def snapshot(self):
        if not self._lock.acquire(blocking=False):
            return dict(schema_version=1, status='busy', records=[])
        try:
            self._expire(self._clock())
            return dict(schema_version=1, status='ready', scope='core_process_memory',
                retention_seconds=self.RETENTION_SECONDS, max_records=self.MAX_RECORDS,
                max_bytes=self.MAX_BYTES, buffer_bytes=self._bytes, dropped=dict(self._dropped),
                records=[{**value, 'details': [dict(item) for item in value['details']]}
                         for _, _, value in reversed(self._records)])
        finally:
            self._lock.release()


recent_http_failures = RecentHttpFailures()


class HttpFailureMiddleware:
    """Observe final response status, including handled HTTPException responses.

    Only a router-owned template enters the ring; never scope.path/raw_path,
    query strings, request/response bodies, headers, exceptions or actor data.
    Incoming trace headers are ignored. The server ID is not an authority token.
    """
    def __init__(self, app, *, store=None):
        self.app, self.store = app, store if store is not None else recent_http_failures

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        state = _RequestState('invoke_' + uuid.uuid4().hex)
        token = _current.set(state)
        started = time.monotonic()
        status = None
        raised = False
        async def response(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
                headers = [(name, value) for name, value in message.get('headers', ())
                           if name.lower() != TRACE_HEADER]
                message = {**message, 'headers': [*headers, (TRACE_HEADER, state.trace_id.encode('ascii'))]}
            await send(message)
        try:
            await self.app(scope, receive, response)
        except Exception:
            raised = True
            raise  # Preserve the existing exception/response handling contract.
        finally:
            # A failure after a 200 has started is NOT relabelled as an HTTP500.
            observed = status if status is not None else 500 if raised else None
            try:
                if observed == 409 or observed is not None and 500 <= observed <= 599:
                    route = getattr(scope.get('route'), 'path', None)
                    if type(route) is not str or not _ROUTE.fullmatch(route):
                        route = '[unmatched]'
                    details, phase = (), 'unknown'
                    if state.lock.acquire(blocking=False):
                        try:
                            details, phase = tuple(state.details), state.phase
                            state.active = False
                        finally:
                            state.lock.release()
                    self.store.record(trace_id=state.trace_id, method=scope.get('method'), route=route,
                        status=observed, duration_ms=(time.monotonic() - started) * 1000,
                        phase=phase, details=details)
            except Exception:
                pass  # A failed optional recorder cannot fail a Core request.
            finally:
                state.active = False
                _current.reset(token)
