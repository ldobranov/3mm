"""Process-local, bounded HTTP failure metadata. No bodies, credentials or I/O."""
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass, field
import hashlib
import json
import math
import re
import sqlite3
import threading
import time
import uuid

from backend.system.diagnostics.catalog import CASE_REASONS as _REASONS, CASE_STAGES as _STAGES, DEVICE_STAGES


TRACE_HEADER = b'x-3mm-trace-id'
_TRACE = re.compile(r'invoke_[0-9a-f]{32}\Z')
_ROUTE = re.compile(r'/[A-Za-z0-9_./{}:-]{0,255}\Z')
_METHODS = {'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'}
_PHASES = {'unknown': 0, 'not_dispatched': 1, 'execution_unconfirmed': 2, 'completed': 3}
# Local management diagnostics; these are not SDK/application-host wire labels.
_DB_FAILURES = {
    sqlite3.SQLITE_CONSTRAINT: 'database_constraint',
    sqlite3.SQLITE_BUSY: 'database_busy', sqlite3.SQLITE_LOCKED: 'database_busy',
    sqlite3.SQLITE_READONLY: 'database_read_only', sqlite3.SQLITE_FULL: 'database_full',
    sqlite3.SQLITE_CANTOPEN: 'database_cannot_open', sqlite3.SQLITE_IOERR: 'database_io_error',
}
_current = ContextVar('core_http_failure', default=None)


@dataclass
class _RequestState:
    trace_id: str
    phase: str = 'unknown'
    details: list = field(default_factory=list)
    active: bool = True
    instance_id: str | None = None
    artifact_binding: tuple[str, str] | None = None
    ambiguous_instance: bool = False
    handled_refusal: bool = False
    last_passed: str | None = None
    step_timing: tuple | None = None
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


def database_reason(driver_error):
    """Never inspect the statement, parameters or message, including for other drivers."""
    code = getattr(driver_error, 'sqlite_errorcode', None) if isinstance(driver_error, sqlite3.Error) else None
    reason = _DB_FAILURES.get(code & 0xff) if type(code) is int else None
    return reason or 'database_operation_failed'


def note_database_error(stage, driver_error):
    reason = database_reason(driver_error)
    note_failure(stage, reason)
    return reason


def finish_device_step(stage, started, reason=None):
    state = _current.get()
    if state is None or stage not in DEVICE_STAGES or not state.lock.acquire(blocking=False):
        return
    try:
        if not state.active:
            return
        if reason is None:
            state.last_passed = stage
        elif not state.details and reason in _REASONS:
            state.details.append((stage, reason))
            state.step_timing = (state.last_passed, round((time.monotonic() - started) * 1000, 3))
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


def note_handled_refusal(stage, reason):
    """Retain an explicit read-side refusal without changing its HTTP response.

    Trusted Core code supplies closed labels, never client metadata. Other caught
    exceptions do not implicitly opt a successful response into the failure ring.
    """
    state = _current.get()
    if (state is None or type(stage) is not str or stage not in _STAGES or
            type(reason) is not str or reason not in _REASONS or reason == 'ok'):
        return
    if not state.lock.acquire(blocking=False):
        return
    try:
        if state.active:
            if len(state.details) < 6 and (stage, reason) not in state.details:
                state.details.append((stage, reason))
            state.handled_refusal = True
    finally:
        state.lock.release()


def observation_revision(instance_id, incarnation, artifact):
    """Not an authority token. Only equal for the same installation generation and package."""
    if (type(instance_id) is not str or not re.fullmatch(r'[0-9a-f]{24}', instance_id)
            or type(incarnation) is not str or not re.fullmatch(r'[0-9a-f]{32}', incarnation)
            or type(artifact) is not str or not re.fullmatch(r'[0-9a-f]{64}', artifact)):
        return None
    return hashlib.sha256(f'app-case-v1:{instance_id}:{incarnation}:{artifact}'.encode('ascii')).hexdigest()


def note_instance(instance_id, *, incarnation=None, artifact=None):
    """Only trusted Core admission can bind a request to an instance and its code."""
    state = _current.get()
    if state is None or type(instance_id) is not str or not re.fullmatch(r'[0-9a-f]{24}', instance_id):
        return
    if not state.lock.acquire(blocking=False):
        return
    try:
        if state.active and not state.ambiguous_instance:
            binding = (incarnation, artifact) if incarnation and artifact else None
            if (state.instance_id not in (None, instance_id) or
                    (binding and state.artifact_binding and binding != state.artifact_binding)):
                # A request which traverses two identities belongs in global support
                # only. A later observation cannot silently attribute it to either.
                state.ambiguous_instance = True
                state.instance_id = state.artifact_binding = None
            else:
                state.instance_id = instance_id
                state.artifact_binding = binding or state.artifact_binding
    finally:
        state.lock.release()


class RecentHttpFailures:
    MAX_RECORDS = 100
    MAX_BYTES = 128 * 1024  # Serialized metadata; fixed Python object overhead is bounded too.
    RETENTION_SECONDS = 15 * 60
    RATE = 10
    COALESCE_SECONDS = 30

    def __init__(self, *, clock=time.monotonic, wall=time.time):
        self._clock, self._wall = clock, wall
        self._lock = threading.Lock()
        self._records = deque()
        self._bytes = self._window_count = 0
        self._window = None
        self.process_id = uuid.uuid4().hex
        self._history_id = uuid.uuid4().hex
        self._dropped = dict.fromkeys(('rate', 'busy', 'invalid', 'evicted', 'expired'), 0)

    def _drop(self, kind):
        self._dropped[kind] = min(2**63 - 1, self._dropped[kind] + 1)

    def _expire(self, now):
        while self._records and now - self._records[0][0] >= self.RETENTION_SECONDS:
            _, size, _ = self._records.popleft()
            self._bytes -= size
            self._drop('expired')

    def record(self, *, trace_id, method, route, status, duration_ms, phase='unknown', details=(), transport='http', instance_id=None, handled_refusal=False, application_revision=None, step_timing=None):
        if (type(trace_id) is not str or not _TRACE.fullmatch(trace_id) or
                type(method) is not str or method not in _METHODS or
                type(route) is not str or route != '[unmatched]' and not _ROUTE.fullmatch(route) or
                type(transport) is not str or transport not in {'http', 'websocket'} or
                type(handled_refusal) is not bool or
                not (transport == 'http' and type(status) is int and (
                         400 <= status <= 599 and not handled_refusal or
                         status == 200 and handled_refusal and method == 'GET'
                         and phase == 'not_dispatched' and bool(details))
                     or transport == 'websocket' and status is None and not handled_refusal) or
                type(phase) is not str or phase not in _PHASES or
                type(duration_ms) not in (int, float) or not math.isfinite(duration_ms) or
                not 0 <= duration_ms <= 86400000 or type(details) not in (list, tuple) or len(details) > 6):
            self._drop('invalid')
            return
        if instance_id is not None and (type(instance_id) is not str or not re.fullmatch(r'[0-9a-f]{24}', instance_id)):
            self._drop('invalid')
            return
        if application_revision is not None and (instance_id is None or type(application_revision) is not str
                                                or not re.fullmatch(r'[0-9a-f]{64}', application_revision)):
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
            stage, reason = details[0] if details else ('http.response',
                'authentication_failed' if status == 401 else
                'operation_denied' if status == 403 else
                'request_invalid' if status == 422 else
                'overloaded' if status == 429 else
                'unclassified_conflict' if status == 409 else
                'server_error' if status is not None and status >= 500 else 'client_refused')
            value = dict(trace_id=trace_id, timestamp=self._wall(), method=method, route=route,
                status=status, duration_ms=round(duration_ms, 3), stage=stage, reason=reason,
                phase=phase, retryable=False, transport=transport, instance_id=instance_id,
                details=[dict(stage=stage, reason=reason) for stage, reason in details])
            if handled_refusal:
                value['handled_refusal'] = True  # HTTP success, not successful resource admission.
            if (stage in DEVICE_STAGES and type(step_timing) is tuple and len(step_timing) == 2
                    and (step_timing[0] is None or type(step_timing[0]) is str and step_timing[0] in DEVICE_STAGES)
                    and type(step_timing[1]) in (int, float) and 0 <= step_timing[1] <= duration_ms):
                value.update(last_passed_stage=step_timing[0], failed_step_ms=step_timing[1])
            if application_revision is not None:
                value['application_revision'] = application_revision
            fingerprint = (method, route, status, stage, reason, phase, transport, instance_id,
                           application_revision, tuple(tuple(item) for item in details))
            previous = None
            for item in reversed(self._records):
                if now - item[0] > self.COALESCE_SECONDS:
                    break
                row = item[2]
                if fingerprint == (row['method'], row['route'], row['status'], row['stage'],
                                   row['reason'], row['phase'], row['transport'], row['instance_id'],
                                   row.get('application_revision'), tuple((d['stage'], d['reason']) for d in row['details'])):
                    previous = item
                    break
            value.update(occurrences=1, first_timestamp=value['timestamp'], trace_ids=[trace_id])
            if previous is not None:
                old = previous[2]
                value.update(occurrences=min(2**63 - 1, old['occurrences'] + 1),
                             first_timestamp=old['first_timestamp'],
                             trace_ids=[trace_id, *[t for t in old['trace_ids'] if t != trace_id]][:8])
            size = len(json.dumps(value, separators=(',', ':'), allow_nan=False).encode('utf-8'))
            if size > 2048:
                self._drop('invalid')
                return
            if previous is not None:
                self._records.remove(previous)
                self._bytes -= previous[1]
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
        return self._snapshot(None)

    def clear_history(self, history_id):
        """Clear only recent HTTP metadata, once for this observed history epoch."""
        if not self._lock.acquire(blocking=False):
            return 'busy'
        try:
            if history_id != self._history_id:
                return 'changed'
            self._records.clear()
            self._bytes = 0
            self._dropped = dict.fromkeys(self._dropped, 0)
            self._history_id = uuid.uuid4().hex
            # Keep the rate window: clearing history must not bypass collection limits.
            return 'cleared'
        finally:
            self._lock.release()

    def application_snapshot(self, instance_id, incarnation, artifact):
        revision = observation_revision(instance_id, incarnation, artifact)
        if revision is None:
            raise ValueError('Verified installation binding required')
        return self._snapshot(revision)

    def _snapshot(self, revision):
        if not self._lock.acquire(blocking=False):
            return dict(schema_version=1, status='busy', records=[])
        try:
            self._expire(self._clock())
            records = [{**value, 'trace_ids': list(value['trace_ids']), 'details': [dict(item) for item in value['details']]}
                       for _, _, value in reversed(self._records)
                       if revision is None or value.get('application_revision') == revision]
            if revision is not None:
                return dict(status='ready', retention_seconds=self.RETENTION_SECONDS,
                            scope='matched_installation_and_package_only', records=records)
            return dict(schema_version=2, status='ready', scope='core_process_memory', process_id=self.process_id, history_id=self._history_id,
                retention_seconds=self.RETENTION_SECONDS, max_records=self.MAX_RECORDS,
                coalesce_seconds=self.COALESCE_SECONDS, max_retained_traces_per_group=8,
                max_bytes=self.MAX_BYTES, buffer_bytes=self._bytes, dropped=dict(self._dropped),
                records=records)
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
                details, phase, instance_id, binding, handled, step_timing = (), 'unknown', None, None, False, None
                if state.lock.acquire(blocking=False):
                    try:
                        details, phase = tuple(state.details), state.phase
                        instance_id, handled = state.instance_id, state.handled_refusal
                        binding = state.artifact_binding
                        step_timing = state.step_timing
                        state.active = False
                    finally:
                        state.lock.release()
                handled = handled and observed == 200 and scope.get('method') == 'GET' and phase == 'not_dispatched'
                if observed is not None and (400 <= observed <= 599 or handled):
                    route = getattr(scope.get('route'), 'path', None)
                    if type(route) is not str or not _ROUTE.fullmatch(route):
                        route = '[unmatched]'
                    self.store.record(trace_id=state.trace_id, method=scope.get('method'), route=route,
                        status=observed, duration_ms=(time.monotonic() - started) * 1000,
                        phase=phase, details=details, instance_id=instance_id, handled_refusal=handled, step_timing=step_timing,
                        application_revision=observation_revision(instance_id, *binding) if binding else None)
            except Exception:
                pass  # A failed optional recorder cannot fail a Core request.
            finally:
                state.active = False
                _current.reset(token)
