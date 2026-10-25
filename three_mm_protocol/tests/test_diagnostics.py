import json
import threading

import pytest

from three_mm_protocol import diagnostics as diagnostic_module
from three_mm_protocol.diagnostics import (
    DiagnosticBusy, DiagnosticSession, DiagnosticSpan, MAX_EVENT_BYTES,
    MAX_EXPORT_BYTES,
)


TRACE = "platform_" + "a" * 32


def emit(session, **changes):
    session.record(**{
        "trace_id": TRACE, "stage": "core.request", "result": "ok",
        "reason": "ok", "duration_ms": 1.25, **changes,
    })


def records(session):
    with session.export() as chunks:
        return [json.loads(line) for line in chunks][1:]


def test_opt_in_ttl_stop_restart_and_no_persistent_state(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(diagnostic_module.time, "monotonic", lambda: clock[0])
    session = DiagnosticSession("core", "0.3.0-beta.57")
    emit(session)
    assert records(session) == []
    first = session.start(10)
    assert first["remaining_seconds"] == 10
    with pytest.raises(DiagnosticBusy):
        session.start()
    emit(session)
    assert session.stop()["active"] is False
    emit(session)
    assert len(records(session)) == 1
    clock[0] = 111
    assert records(session) == []
    assert session.status()["buffer_bytes"] == 0
    assert session.start()["session_id"] != first["session_id"]
    assert session.status()["remaining_seconds"] == 600
    assert session.status()["spool_bytes"] == 0
    assert DiagnosticSession("core", "unknown").status()["active"] is False


@pytest.mark.parametrize("ttl", [0, -1, 1801, True, 3.5, "10"])
def test_session_ttl_rejects_unbounded_or_coerced_values(ttl):
    with pytest.raises(ValueError):
        DiagnosticSession("core", "1.0").start(ttl)


@pytest.mark.parametrize("changes", [
    {"reason": "password=must-not-leak"},
    {"stage": "Bearer must-not-leak"},
    {"trace_id": "must-not-leak" * 1000},
    {"result": {"password": "must-not-leak"}},
    {"duration_ms": float("nan")},
    {"duration_ms": float("inf")},
    {"duration_ms": -1},
])
def test_only_bounded_allowlisted_metadata_enters_buffer(changes):
    session = DiagnosticSession("core", "1.0")
    session.start()
    emit(session, **changes)
    assert records(session) == []
    assert session.status()["dropped"]["invalid"] == 1
    emit(session)
    record, = records(session)
    assert record["trace_id"] == TRACE
    assert record["parent_span_id"] == "sdk.call"
    assert record["operation"] == "installation.identity.get"
    with pytest.raises(TypeError):
        session.record(payload={"secret": "must-not-leak"})
    with session.export() as chunks:
        content = b"".join(chunks)
    assert b"must-not-leak" not in content


def test_overflow_rate_limits_and_lock_contention_never_wait(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(diagnostic_module.time, "monotonic", lambda: clock[0])
    session = DiagnosticSession("core", "1.0", max_bytes=1024, events_per_second=2)
    session.start()
    emit(session)
    emit(session)
    emit(session)
    assert session.status()["dropped"]["rate"] == 1
    clock[0] += 1
    for _ in range(2):
        emit(session)
    assert session.status()["dropped"]["full"] >= 1
    assert session.status()["buffer_bytes"] <= 1024
    # Hold the management lock until the producer has returned: a blocking
    # producer fails this check instead of merely looking fast on a quiet host.
    with session._lock:
        returned = threading.Event()
        worker = threading.Thread(target=lambda: (emit(session), returned.set()), daemon=True)
        worker.start()
        completed = returned.wait(1)
    worker.join(1)
    assert completed
    assert session.status()["dropped"]["busy"] >= 1


def test_export_is_bounded_and_slow_failed_or_duplicate_consumers_are_isolated():
    session = DiagnosticSession("core", "1.0")
    session.start()
    with session.export() as slow_consumer:
        next(slow_consumer)
        emit(session)
        with pytest.raises(DiagnosticBusy):
            with session.export():
                pass
        session.stop()
        with pytest.raises(DiagnosticBusy):
            session.start()
    with pytest.raises(OSError):
        with session.export():
            raise OSError("collector unavailable")
    with session.export() as chunks:
        lines = list(chunks)
    assert len(lines) == 2
    assert all(len(line) <= MAX_EVENT_BYTES for line in lines[1:])
    assert sum(map(len, lines)) <= MAX_EXPORT_BYTES
    session.start()
    assert records(session) == []


def test_diagnostic_failure_never_replaces_business_result_or_exception(monkeypatch):
    session = DiagnosticSession("core", "1.0")
    session.start()
    monkeypatch.setattr(diagnostic_module.json, "dumps", lambda *a, **kw: (_ for _ in ()).throw(ValueError()))
    with DiagnosticSpan(session, TRACE, "identity.read"):
        result = 42
    assert result == 42
    with pytest.raises(RuntimeError, match="business error"):
        with DiagnosticSpan(session, TRACE, "identity.read"):
            raise RuntimeError("business error")


@pytest.mark.parametrize("kwargs", [{"max_bytes": 1048577}, {"events_per_second": 11}])
def test_process_cannot_exceed_its_reserved_node_allocation(kwargs):
    with pytest.raises(ValueError):
        DiagnosticSession("sdk", "1.3", **kwargs)
