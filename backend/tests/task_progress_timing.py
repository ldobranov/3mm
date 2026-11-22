"""Failure diagnostics for the real worker test, never used in Core.

Only fixed phase names, a bounded lease result and millisecond timings may leave this observer.
Phase times are inclusive; the SQLite and GC timings may overlap them.
"""
import gc
import threading
import time
from contextlib import contextmanager
from functools import wraps

from sqlalchemy import event
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from backend.applications.authority import management, sources
from backend.applications.authority.keys import CoreReviewKeyStore
from backend.applications.tasks import broker


@contextmanager
def observe_progress(patch, engine, totals):
    """Attach before scheduling; time selected boundaries, not every function call."""
    handler = None
    sql_started = gc_started = 0
    elapsed = {"guard_sql": 0, "other_sql": 0}
    gc_time = 0

    def watch(owner, name, label):
        original = getattr(owner, name)
        @wraps(original)
        def timed(*args, **kwargs):
            if threading.get_ident() != handler:
                return original(*args, **kwargs)
            start = time.perf_counter_ns()
            try:
                result = original(*args, **kwargs)
                if label == "lease":
                    state, reason = result
                    totals["lease_result"] = (reason if reason in {
                        "authority_changed", "execution_unconfirmed", "not_dispatched", "deadline_exceeded",
                    } else "running" if state == "running" else "not_running")
                return result
            finally:
                elapsed[label] = elapsed.get(label, 0) + time.perf_counter_ns() - start
        patch.setattr(owner, name, timed)

    manager = management.ApplicationAuthorityManager
    for owner, name, label in (
        (manager, "_prepare", "package"), (sources, "_read_baseline", "package_bytes"),
        (manager, "_require_grant", "grant"), (manager, "_subject", "current_subject"),
        (manager, "_policy", "policy"), (broker, "_derived", "lease"),
        (QueuePool, "_do_get", "connection"), (Session, "commit", "commit"),
        (Session, "rollback", "rollback"),
    ):
        watch(owner, name, label)

    original_key = CoreReviewKeyStore._locked
    @contextmanager
    def key_lease(store, *, read_only):
        start = time.perf_counter_ns()
        with original_key(store, read_only=read_only) as key:
            if threading.get_ident() == handler:
                elapsed["review_key"] = time.perf_counter_ns() - start
            yield key
    patch.setattr(CoreReviewKeyStore, "_locked", key_lease)

    def before_sql(conn, cursor, statement, params, context, many):
        nonlocal sql_started
        if threading.get_ident() == handler:
            sql_started = time.perf_counter_ns()

    def after_sql(conn, cursor, statement, params, context, many):
        if threading.get_ident() == handler:
            phase = "guard_sql" if statement.startswith("UPDATE core_authority_guard ") else "other_sql"
            elapsed[phase] += time.perf_counter_ns() - sql_started

    def collection(phase, info):
        nonlocal gc_started, gc_time
        if handler is not None:
            if phase == "start":
                gc_started = time.perf_counter_ns()
            elif gc_started:
                gc_time += time.perf_counter_ns() - gc_started
                gc_started = 0

    @contextmanager
    def measure():
        nonlocal handler
        handler = threading.get_ident()
        started, cpu, process = time.perf_counter_ns(), time.thread_time_ns(), time.process_time_ns()
        try:
            yield
        finally:
            handler = None
            totals.update(wall=round((time.perf_counter_ns() - started) / 1e6),
                          thread_cpu=round((time.thread_time_ns() - cpu) / 1e6),
                          process_cpu=round((time.process_time_ns() - process) / 1e6),
                          gc=round(gc_time / 1e6))
            totals.update({phase: round(duration / 1e6) for phase, duration in elapsed.items()})

    event.listen(engine, "before_cursor_execute", before_sql)
    event.listen(engine, "after_cursor_execute", after_sql)
    gc.callbacks.append(collection)
    try:
        yield measure
    finally:
        gc.callbacks.remove(collection)
        event.remove(engine, "after_cursor_execute", after_sql)
        event.remove(engine, "before_cursor_execute", before_sql)
