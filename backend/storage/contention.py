"""One on-demand sample of Core's SQLite write transactions; no SQL or payload recording."""

import sys
import threading
import time

from sqlalchemy import event
from backend.storage.observation_format import SOURCE_PREFIXES


def _source():
    # Module names in Core's currently executing stack only. Never retain frames,
    # function names, SQL text/parameters, request paths, device IDs or identities.
    frame = sys._getframe(1)
    try:
        for _ in range(48):
            if frame is None:
                break
            name = frame.f_globals.get("__name__")
            if type(name) is str:
                for prefix, group in SOURCE_PREFIXES:
                    if name.startswith(prefix):
                        return group
            frame = frame.f_back
        return "other"
    finally:
        del frame


class ObservationBusy(Exception):
    def __init__(self, retry_after):
        self.retry_after = retry_after


class _Window:
    def __init__(self, clock):
        self.clock = clock
        self.start = clock()
        self.lock = threading.Lock()
        self.active = True
        self.limited = False
        self.open = {}
        self.totals = {}

    def write(self, token):
        if not self.active or token in self.open:
            return
        if not self.lock.acquire(False):
            self.limited = True
            return
        try:
            if not self.active or token in self.open:
                return
            if len(self.open) >= 64:
                self.limited = True
                return
            group = _source()
            self.open[token] = (group, self.clock())
            summary = self.totals.setdefault(group, {"observed": 0, "longest_ms": 0, "open_at_end": 0})
            summary["observed"] += 1
        finally:
            self.lock.release()

    def end(self, token):
        if not self.active or token not in self.open:
            return
        if not self.lock.acquire(False):
            self.limited = True
            return
        try:
            entry = self.open.pop(token, None)
            if entry is not None:
                self._elapsed(*entry, self.clock())
        finally:
            self.lock.release()

    def _elapsed(self, group, start, end):
        summary = self.totals[group]
        summary["longest_ms"] = max(summary["longest_ms"], round(1000 * (end - start)))

    def finish(self):
        with self.lock:
            self.active = False
            end = self.clock()
            for group, start in self.open.values():
                self._elapsed(group, start, end)
                self.totals[group]["open_at_end"] += 1
            self.open.clear()
            return {
                "schema_version": 1, "kind": "sqlite_write_sample",
                "coverage": "new_core_engine_connections", "window_ms": round(1000 * (end - self.start)),
                "limited": self.limited, "families": [
                    {"source": group, **summary} for group, summary in
                    sorted(self.totals.items(), key=lambda item: (-item[1]["longest_ms"], item[0]))
                ],
            }


class SQLiteWriteObserver:
    def __init__(self, *, clock=time.monotonic):
        self.clock = clock
        self.gate = threading.Lock()
        self.window = None
        self.next_allowed = 0
        self.available = False

    def install(self, engine):
        if engine.dialect.name == "sqlite" and not self.available:
            event.listen(engine, "engine_connect", self._connect)
            self.available = True

    def _connect(self, conn):
        window = self.window
        if window is None or not window.active:
            return  # Normal operation: no per-statement hook, IO, clock or sampling thread.
        token = object()

        def executed(_conn, _cursor, statement, _parameters, context, _many):
            if not window.active:
                return
            try:
                if (context.isinsert or context.isupdate or context.isdelete
                    or statement in ("BEGIN IMMEDIATE", "BEGIN IMMEDIATE;")):
                    window.write(token)
            except Exception:  # Optional statistics must not fail a real application write.
                window.limited = True

        def ending(_conn):
            try:
                window.end(token)
            except Exception:
                window.limited = True

        try:
            # Connection-local, not mutable global listeners on a running engine.
            event.listen(conn, "after_cursor_execute", executed)
            event.listen(conn, "commit", ending)
            event.listen(conn, "rollback", ending)
        except Exception:
            window.limited = True

    def observe(self, *, wait=time.sleep):
        if not self.available:
            raise RuntimeError("SQLite write observation is unavailable")
        if not self.gate.acquire(False):
            raise ObservationBusy(5)
        try:
            remaining = self.next_allowed - self.clock()
            if remaining > 0:
                raise ObservationBusy(max(1, int(remaining) + 1))
            window = self.window = _Window(self.clock)
            try:
                wait(5)
            finally:
                self.window = None
                result = window.finish()
                self.next_allowed = self.clock() + 30
            return result
        finally:
            self.gate.release()


write_observer = SQLiteWriteObserver()
