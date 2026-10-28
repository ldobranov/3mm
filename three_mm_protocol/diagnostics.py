"""Bounded, opt-in local operation records shared by Core and SDK.

Only fixed metadata enters the buffer. Producers never call a collector, perform
I/O or wait for a lock. Export is a separate pull operation. This is deliberately
independent of business/security audit and of the signed application wire format.
"""

from three_mm_platform_wire import RUNTIME_ACTIONS

from collections import deque
from contextlib import contextmanager
import json
import math
import re
import threading
import time
import uuid


MAX_EVENT_BYTES = 2048
MAX_BUFFER_BYTES = 1024 * 1024  # One allocation; Core + one SDK = 2 MiB.
MAX_EVENTS_PER_SECOND = 10     # Core + one SDK = 20/s.
MAX_EXPORT_BYTES = 4 * 1024 * 1024
DEFAULT_TTL_SECONDS = 600
MAX_TTL_SECONDS = 1800
IDENTITY_OPERATION = "installation.identity.get"
TRACE_ID = re.compile(r"(?:platform|invoke)_[0-9a-f]{32}\Z")
INSTANCE_ID = re.compile(r"[0-9a-f]{24}\Z")
OPERATIONS = RUNTIME_ACTIONS | {"application.invoke", "device.setup"}
COMPONENTS = {"core", "sdk", "agent", "setup", "runtime", "application-host", "public-web", "session-worker"}
SETUP_TRACE_ID = re.compile(r"setup_[0-9a-f]{32}\Z")
SETUP_STAGES = {"setup.attempt": None, "setup.network": "setup.attempt",
                "setup.persist": "setup.attempt", "setup.activation": "setup.attempt"}
VERSION = re.compile(r"(?:[0-9][a-zA-Z0-9.+_-]{0,63}|unknown)\Z")
STAGES = {
    "sdk.call": None,
    "core.request": "sdk.call",
    "authority.admission": "core.request",
    "identity.read": "authority.admission",
    "application.admission": None,
    "application.dispatch": "application.admission",
    "application.response": "application.dispatch",
}
RESULTS = {"ok", "denied", "error"}
REASONS = {
    "ok", "authentication_failed", "installation_unavailable",
    "authority_unavailable", "operation_failed", "transport_unavailable",
    "response_invalid", "operation_denied", "deadline_exceeded", "request_invalid",
    "operation_unsupported", "response_too_large", "request_replayed", "overloaded",
}


class DiagnosticBusy(ValueError):
    """A session or export already owns this optional diagnostic allocation."""


class DiagnosticSession:
    """One process-local allocation. Inactive until explicitly started.

    P1 reserves one allocation for Core and one for a single developer SDK
    process. Starting more SDK recorders requires dividing the node budget;
    automated multi-worker allocation belongs to the Runtime session controller.
    """

    def __init__(self, component, version, *, max_bytes=MAX_BUFFER_BYTES,
                 events_per_second=MAX_EVENTS_PER_SECOND):
        if component not in COMPONENTS:
            raise ValueError("Unknown diagnostic component")
        if type(version) is not str or not VERSION.fullmatch(version):
            raise ValueError("Invalid diagnostic version")
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BUFFER_BYTES:
            raise ValueError("Invalid diagnostic buffer allocation")
        if type(events_per_second) is not int or not 1 <= events_per_second <= MAX_EVENTS_PER_SECOND:
            raise ValueError("Invalid diagnostic rate allocation")
        self.component, self.version = component, version
        self.max_bytes, self.events_per_second = max_bytes, events_per_second
        self._lock = threading.Lock()
        self._export_lock = threading.Lock()
        self._records = deque()
        self._active = False
        self._deadline = 0.0
        self._ttl_seconds = 0
        self._session_id = None
        self._bytes = 0
        self._accepted = 0
        self._dropped = dict.fromkeys(("full", "rate", "invalid", "busy"), 0)
        self._window = 0
        self._window_count = 0
        self._scope = {"profile": "diagnostic", "operation": None, "instance_id": None, "trace_id": None}

    def _expire(self, now):
        if self._deadline and now >= self._deadline:
            self._active = False
            self._records.clear()
            self._bytes = 0

    def start(self, ttl_seconds=DEFAULT_TTL_SECONDS, *, profile="diagnostic", operation=None, instance_id=None, trace_id=None):
        if (profile not in {"diagnostic", "development"}
                or operation is not None and operation not in OPERATIONS
                or instance_id is not None and (type(instance_id) is not str or not INSTANCE_ID.fullmatch(instance_id))
                or trace_id is not None and (type(trace_id) is not str or not TRACE_ID.fullmatch(trace_id))):
            raise ValueError("Invalid diagnostic scope")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= MAX_TTL_SECONDS:
            raise ValueError("Invalid diagnostic TTL")
        with self._lock:
            now = time.monotonic()
            self._expire(now)
            if self._active or self._export_lock.locked():
                raise DiagnosticBusy("Diagnostic allocation is in use")
            self._records.clear()
            self._bytes = self._accepted = self._window_count = 0
            self._dropped = dict.fromkeys(self._dropped, 0)
            self._window = int(now)
            self._deadline = now + ttl_seconds
            self._ttl_seconds = ttl_seconds
            self._scope = {"profile": profile, "operation": operation, "instance_id": instance_id, "trace_id": trace_id}
            self._session_id = uuid.uuid4().hex
            self._active = True
            return self._status(now)

    def stop(self):
        with self._lock:
            self._active = False
            return self._status(time.monotonic())

    def _status(self, now):
        self._expire(now)
        return {
            "schema_version": 1, "session_id": self._session_id,
            "component": self.component, "version": self.version,
            "active": self._active, "scope": dict(self._scope),
            # Floating addition/subtraction across a binary exponent boundary
            # can round the initial difference just above the requested TTL.
            "remaining_seconds": min(self._ttl_seconds, max(0, math.ceil(self._deadline - now))),
            "buffer_bytes": self._bytes, "max_buffer_bytes": self.max_bytes,
            "records": len(self._records), "accepted": self._accepted,
            "dropped": dict(self._dropped),
            "events_per_second": self.events_per_second,
            "spool_bytes": 0,
        }

    def status(self):
        with self._lock:
            return self._status(time.monotonic())

    def _drop(self, reason):
        # Saturating, best-effort counters: lock contention must never make the
        # producer wait, including on Python implementations without a GIL.
        self._dropped[reason] = min(self._dropped[reason] + 1, 2**63 - 1)

    def record(self, *, trace_id, stage, result, reason, duration_ms, operation=IDENTITY_OPERATION, instance_id=None):
        if not self._active:
            return
        if not self._lock.acquire(blocking=False):
            self._drop("busy")
            return
        try:
            now = time.monotonic()
            self._expire(now)
            if not self._active:
                return
            # No arbitrary labels, bodies, exception text, caller dictionaries,
            # identities, paths or credentials are accepted, even temporarily.
            bootstrap = (self.component == "setup" and type(trace_id) is str
                         and SETUP_TRACE_ID.fullmatch(trace_id) and type(stage) is str and stage in SETUP_STAGES)
            identity = (type(trace_id) is str and TRACE_ID.fullmatch(trace_id)
                        and type(stage) is str and stage in STAGES)
            if (operation not in OPERATIONS
                    or instance_id is not None and (type(instance_id) is not str or not INSTANCE_ID.fullmatch(instance_id))
                    or not (bootstrap or identity)
                    or type(result) is not str or result not in RESULTS
                    or type(reason) is not str or reason not in REASONS
                    or type(duration_ms) not in (int, float)
                    or not math.isfinite(duration_ms) or not 0 <= duration_ms <= 86_400_000):
                self._drop("invalid")
                return
            operation = "device.setup" if bootstrap else operation
            if any(self._scope[k] is not None and self._scope[k] != value
                   for k, value in (("operation", operation), ("instance_id", instance_id), ("trace_id", trace_id))):
                return
            if int(now) != self._window:
                self._window, self._window_count = int(now), 0
            if self._window_count >= self.events_per_second:
                self._drop("rate")
                return
            self._window_count += 1
            record = {
                "schema_version": 1, "timestamp": round(time.time(), 6),
                "component": self.component, "version": self.version,
                "operation": operation, "instance_id": instance_id, "trace_id": trace_id,
                "span_id": stage, "parent_span_id": (SETUP_STAGES if bootstrap else STAGES)[stage],
                "result": result, "reason": reason,
                "duration_ms": round(duration_ms, 3),
            }
            encoded = json.dumps(record, separators=(",", ":"), allow_nan=False).encode() + b"\n"
            if len(encoded) > MAX_EVENT_BYTES or self._bytes + len(encoded) > self.max_bytes:
                self._drop("full")
                return
            self._records.append(encoded)
            self._bytes += len(encoded)
            self._accepted = min(self._accepted + 1, 2**63 - 1)
        except Exception:
            # Optional diagnostics cannot replace the outcome of the operation.
            self._drop("invalid")
        finally:
            self._lock.release()

    def snapshot(self, limit=200):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Invalid diagnostic snapshot limit")
        with self.export() as chunks:
            iterator = iter(chunks)
            status = json.loads(next(iterator))["session"]
            records = []
            for line in iterator:
                if len(records) >= limit: break
                records.append(json.loads(line))
            return {"session": status, "records": records, "truncated": status["records"] > len(records)}

    @contextmanager
    def export(self):
        """One bounded NDJSON snapshot; consumer I/O happens outside our lock.

        The caller must close this context on disconnect or export failure. An
        expired session has no exportable records. No persistent spool is used.
        """
        if not self._export_lock.acquire(blocking=False):
            raise DiagnosticBusy("Diagnostic export is in use")
        try:
            with self._lock:
                status = self._status(time.monotonic())
                records = tuple(self._records)  # Copy references, not payloads.
            header = json.dumps({"session": status}, separators=(",", ":")).encode() + b"\n"
            def chunks():
                size = len(header)
                yield header
                for record in records:
                    if size + len(record) > MAX_EXPORT_BYTES:
                        break
                    size += len(record)
                    yield record
            yield chunks()
        finally:
            self._export_lock.release()


class DiagnosticSpan:
    """Best-effort operation instrumentation; does not handle business errors."""

    def __init__(self, session, trace_id, stage, *, failure_result="error",
                 failure_reason="operation_failed", operation=IDENTITY_OPERATION, instance_id=None):
        self.session, self.trace_id, self.stage = session, trace_id, stage
        self.failure_result, self.failure_reason = failure_result, failure_reason
        self.operation, self.instance_id = operation, instance_id
        self._started = time.monotonic()
        self._ended = False

    def __enter__(self):
        return self

    def end(self, result="ok", reason="ok"):
        if self._ended:
            return
        self._ended = True
        if self.session is not None:
            try:
                self.session.record(trace_id=self.trace_id, stage=self.stage,
                    operation=self.operation, instance_id=self.instance_id,
                    result=result, reason=reason,
                    duration_ms=(time.monotonic() - self._started) * 1000)
            except Exception:
                pass

    def __exit__(self, exc_type, _exc, _tb):
        self.end(self.failure_result if exc_type else "ok",
                 self.failure_reason if exc_type else "ok")
