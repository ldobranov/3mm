# Application job scheduler (0.3.0-beta.17)

The generic Core scheduler honors declared `interval_seconds` without the previous
fixed 30-second pause. The event retry worker remains unchanged at 30 seconds.
Physical command deadlines are unchanged. This is not a hard-real-time service.

## Scheduling and concurrency

- Read-only discovery is separate from invocation. The main worker waits until
  the nearest future due time, capped at one second for installation changes.
  Idle/occupied polling is bounded; there is no busy-wait loop.
- Each Core process has two executor threads, at most two outstanding futures,
  and separate database sessions per invocation. Validated immutable definitions
  are cached (maximum 128); the gateway still validates the package at invocation.
- The installation-row write lock makes claim acquisition atomic across Core
  processes. All jobs for one installation serialize, including different job IDs.
  A second application can run while the first application's job is slow.
  The extension host retains its existing serial operation execution; event and
  user requests can still occupy that host and affect latency.
- Each acquisition reads current time after obtaining the database lock. Queued
  executors check active instance/package and shutdown state before invocation.
  Lifecycle changes after dispatch cannot retract an already-running external action.

## Intervals and missed runs

- First discovery schedules one immediate execution.
- Successful short jobs retain their scheduled cadence. If completion has reached
  or passed the following scheduled time, the next run is one interval after
  completion, with no overlapping run or burst of missed executions.
- `catch_up: once` executes one overdue scheduled run, preserving that scheduled
  timestamp in its existing `job:<instance>:<job>:<scheduled timestamp>` identity.
- `catch_up: skip` advances an execution overdue by at least one full interval
  without invoking it. Smaller scheduling delays do not cause skips.
- Restart preserves schedules. Upgrade rejects claims for an inactive package.
  Removed jobs are not dispatched; retained completed jobs are reinitialized when
  their package changes. An unresolved claim blocks that installation's jobs even
  after an upgrade: changing versions is not proof that its side effect did not occur.

## Lease, errors and recovery

Migration `2f37e8f9a0b1` adds an ownership token, original instance/package,
scheduled time, duration and lateness to existing job state. Legacy in-flight
claims become `unknown` rather than being replayed.

The lease is 60 seconds (not the job interval) and is renewed every 20 seconds
while an executor remains active. Expiry after process loss marks the outcome
`unknown`; it does **not** authorize another invocation. A timeout, gateway error
or other unconfirmed exception also retains the claim and blocks new jobs for
that installation. There is no automatic retry of an uncertain external mutation.
The original executor may finish and record a confirmed result only while its
ownership token still matches.

Shutdown stops new submissions and waits for dispatched work; cancelled futures
that never started release their claims. Python threads cannot forcibly cancel
external side effects. Operation transport timeouts still apply, and forcibly
killing Core leaves durable claims for conservative recovery.

Restore replaces tokens of all in-flight/unresolved jobs before activating any
application. This fences old completions and preserves unknown state without
replaying the stored execution. Normal schedules retain catch-up policy; the
extension remains responsible for reviewing its restored domain data/intents.

For an unresolved outcome:

1. Disable the application using its existing lifecycle action (stops its host).
2. Review/reconcile the actual external outcome; a timeout is not evidence of failure.
3. An administrator may call
   `POST /api/v1/application-extensions/{module_id}/jobs/{job_id}/resolve` with
   `{"confirmed_external_outcome_reviewed": true}`. Core requires the application
   to be disabled, invalidates the old token and records an audit event.
4. Re-enable only after reconciliation. Resolution schedules a **new** occurrence,
   not a retry under the uncertain occurrence's identity.

This endpoint is not a new automatic retry policy; no resolution UI is added here.

## Diagnostics and evidence

The existing admin-only `operational-status` response exposes each job's scheduled
and actual start time, duration/lateness in milliseconds, lease deadline, last
outcome and a fixed safe error category. No operation result body, credentials,
request body or arbitrary exception text is logged or exposed as job diagnostics.

Tests cover two concurrent claimers, long-running jobs, expiry/restart quarantine,
once/skip catch-up, disable/upgrade/shutdown, restore fencing, administrator-only
resolution and the actual asynchronous worker in `backend/main.py`.

On Raspberry (2026-09-15), an isolated temporary database and mock invocations
ran for 17.244 seconds. One application took six seconds per job while another
had a five-second interval:

- fast-job gaps: 4.980, 4.992, 5.034 seconds;
- four fast-job starts, seventeen scheduler ticks;
- process CPU: 0.559 seconds, average 3.24% of one core;
- whole benchmark Python process peak RSS: 70.65 MiB (not incremental Core RAM).

`deployment/benchmark_application_jobs.py` reproduces this isolated Linux test.
No installed service, live database, extension or GPIO was changed. These brief
measurements are not production-load or hardware timing certification. Multi-Core
contention and many installed applications can increase latency.

Apply the migration before starting the new Core. Stop old Core processes during
upgrade so an old scheduler cannot bypass the new claims. Before rolling back to
an older scheduler, stop producers and reconcile in-flight jobs; older code lacks
these ownership and unknown-outcome safeguards.
