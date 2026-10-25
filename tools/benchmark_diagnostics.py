"""Linux microbenchmark of two reserved diagnostic allocations, without services.

Loads only the stdlib recorder, not the protocol package or installed 3mm. Output
is evidence for this primitive, not for full Core/SDK deployment or fault recovery.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import sys
import time
from types import SimpleNamespace


def rss_bytes():
    return int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")


def measure(source, seconds=15):
    if sys.platform != "linux" or os.geteuid() == 0 or not 1 <= seconds <= 30:
        raise ValueError("Use an unprivileged Linux process and a 1–30 s phase")
    initial_rss = rss_bytes()
    namespace = {}
    exec(compile(source, "diagnostic-recorder", "exec"), namespace)
    sessions = [namespace["DiagnosticSession"](name, "1.3") for name in ("core", "sdk")]
    before = time.process_time()
    time.sleep(seconds)
    idle_cpu = time.process_time() - before
    for session in sessions:
        session.start()
    before_cpu, before_wall = time.process_time(), time.monotonic()
    for index in range(seconds * 10):
        target = before_wall + index / 10
        time.sleep(max(0, target - time.monotonic()))
        for session, stage in zip(sessions, ("core.request", "sdk.call")):
            session.record(trace_id="platform_" + "a" * 32, stage=stage,
                           result="ok", reason="ok", duration_ms=1.0)
    time.sleep(max(0, before_wall + seconds - time.monotonic()))
    active_cpu = time.process_time() - before_cpu
    active_wall = time.monotonic() - before_wall
    paced = [session.status() for session in sessions]
    # Fill both buffers with a synthetic clock, without an unbounded event rate
    # on the device or waiting several minutes to reach the same memory state.
    clock = [time.monotonic()]
    namespace["time"] = SimpleNamespace(monotonic=lambda: clock[0], time=time.time)
    for session in sessions:
        session.stop()
        session.start(1800)
    origin = clock[0]
    for index in range(4000):
        clock[0] = origin + index // 10
        for session, stage in zip(sessions, ("core.request", "sdk.call")):
            session.record(trace_id="platform_" + "a" * 32, stage=stage,
                           result="ok", reason="ok", duration_ms=1.0)
    full = [session.status() for session in sessions]
    export_bytes = []
    for session in sessions:
        with session.export() as chunks:
            export_bytes.append(sum(len(chunk) for chunk in chunks))
    return {
        "schema_version": 1, "scope": "stdlib recorder; two allocations in one process",
        "module_sha256": hashlib.sha256(source).hexdigest(),
        "machine": platform.machine(), "python": platform.python_version(),
        "phase_seconds": seconds, "aggregate_events_per_second": 20,
        "idle_cpu_seconds": round(idle_cpu, 6),
        "active_cpu_seconds": round(active_cpu, 6),
        "extra_cpu_percentage_points": round(max(0, active_cpu - idle_cpu) / active_wall * 100, 3),
        "rss_increase_bytes": max(0, rss_bytes() - initial_rss),
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "paced": paced, "full": full, "export_bytes": export_bytes,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=15)
    parser.add_argument("--module", type=Path,
                        default=Path(__file__).resolve().parents[1] / "three_mm_protocol/diagnostics.py")
    args = parser.parse_args()
    print(json.dumps(measure(args.module.read_bytes(), args.seconds), indent=2))
