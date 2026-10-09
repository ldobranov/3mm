# M20 — explicit application lifecycle reconciliation

Date: 2026-10-08. Status: **implemented locally; bounded administrator recovery**.
Extends [lifecycle authority fences](EXTENSION_PLATFORM_V2_LIFECYCLE_AUTHORITY.md).
This is not full WP3/WP4 completion, data rollback, grant authorization or a
release/deployment approval.

## Administrator contract

Additive Core API:

`POST /api/v1/application-extensions/{module_id}/lifecycle/recover`

Body: `{"confirmed_external_outcome_reviewed": true}`. Administrator authentication
and explicit confirmation are required; extra fields are rejected. This endpoint
does not accept client-authored runtime evidence or a request to enable an app.
No frontend recovery button is included in this backend slice.

Only `activating`, `disabling`, `uninstalling`, `recovering` and `recovery_required`
installations can enter recovery. An ordinary active/disabled installation uses
the existing lifecycle endpoints instead. Recovery may be explicitly retried
after a lost recovery response; it always creates a fresh fenced ticket.

1. Capture the actual guard and installation incarnation/epoch/resource state.
2. In a short guard-first transaction, compare that exact pending state, advance
   the general epoch/guard revision, mark `recovering`/disabled, invalidate old
   physical-command authorizations and commit the start audit.
3. Without an open route database transaction, ask the privileged helper to
   quiesce that instance. Never repeat activation, migration or uninstall.
4. Accept only helper evidence bound to this instance and exact recovery ticket.
   Under the guard, recheck guard generation, incarnation, epoch and complete
   pending resource state, advance the epoch/revision and commit a redacted
   `APPLICATION_EXTENSION_LIFECYCLE_RECOVERED` audit with `stopped_disabled`.

Success leaves `status=disabled`, `enabled=false`, `active_version=null` and no
health assertion. Package pointers/configuration are retained as candidate and
diagnostic state, **not proof of which artifact/data migration succeeded**.
Next activation or uninstall is a separate explicit operation through the normal
validated path. Recovery does not delete files/data, complete an uncertain
uninstall, restore old grants, un-revoke peers or claim a healthy runtime.

Missing, stale or unbound evidence stays quarantined. Start/final audit failure
rolls back that entire database phase. A late original completion cannot replace
the recovery result. A lost recovery response is not permission to mark success
without a new explicit verified reconciliation.

## Helper fencing and positive evidence

The private local helper requests for activation, disable and uninstall now carry
the committed lifecycle ticket: Core guard generation, installation ID, module ID,
runtime locator, incarnation and epoch. SDK 1.3 and existing public lifecycle
request/response shapes remain unchanged. Core and its helper must update
together; unfenced old private requests fail closed, with no legacy fallback.

Within the helper's existing root-owned StateDirectory:

- A Linux `flock` excludes overlapping application helper mutations, including
  different helper processes. Busy means unconfirmed, not permission to overlap.
- After taking the lock, the helper reads its installed SQLite database in
  `mode=ro`. Missing metadata/database is never initialized. It checks the fresh
  guard generation, exact installation identity/epoch, expected pending status,
  disabled flag and, for activation, candidate digest/resolved configuration.
- Before any effect it atomically writes/fsyncs a root-private one-use receipt
  (`lifecycle-<instance>.json`) and fsyncs the directory. It stores only private
  identifiers and a request digest, not configuration/credential values.
- Duplicate tickets are refused, including after helper restart or action failure.
  Changed action/payload cannot reuse a consumed ticket. The lock is held through
  runtime work, not merely during the database read.
- Recovery runs fixed `systemctl disable --now`, then reads the unit's state.
  Evidence requires a loaded unit, inactive/failed + dead/failed state,
  disabled/masked unit file, no main PID and no pending systemd job. Missing,
  active, enabled, running, unknown or unreadable state fails closed.

Thus original work already admitted must finish/release the helper lock before
recovery can verify quiescence. Delayed original work checks the newer Core
ticket after the lock and is rejected. No `active.json` pointer is accepted as
rollback/health evidence. The receipt is an admission barrier, **not a complete
queryable operation/stage journal** or a claim of external-effect completion.

A partial request has a bounded socket read timeout. A disconnected caller or
broken response pipe no longer terminates the helper or causes an automatic retry.
Malformed/corrupt receipts and inaccessible storage fail closed.

## Preserved evidence and remaining gates

Unknown scheduler claims/leases, connector attempts, event cursors, command
results and peer tombstones are not cleared by recovery. The existing separate
reviewed job-resolution API remains available once the installation is disabled;
uninstall still refuses outstanding claims. Quiescing a process cannot undo an
already admitted physical action, payment or external POST.

The helper uses the existing immutable-host SQLite layout, not an arbitrary
database URL or caller-selected database. There is no schema change beyond the
existing authority-metadata migration; that migration must precede use.

Remaining release/acceptance gates include Linux live activation/rollback/timeout
recovery, recovery UX, integration of restore/reset/erasure and other raw writers,
fresh recovery generations, journal backup/retention and global release/restore
serialization. The helper-local lock does not yet coordinate those other writers.
Do not deploy this pending M20 work as completed end-to-end recovery or allow raw
SQL/receipt deletion to bypass quarantine. OS isolation, the trusted resolver,
approved grants and effect-admission enforcement are separate open gates.

## Verification

Clean combined focused run: **120 passed, 1 skipped**, 350 warnings, 122.15 seconds
(lifecycle/recovery HTTP, existing access and authority writers, helper and runtime
activation). After the final read-snapshot tightening, runtime/helper cases were
rerun: **40 passed, 1 skipped**. The skip is native Linux `flock` on Windows, not passing
Windows lock evidence. No full release suite or frontend change/build was needed.

Focused HTTP tests cover admin/confirmation restrictions, every recoverable status,
positive/invalid evidence, phase audit rollback, preserved unknown jobs/cursors/
peers, explicit later activation and stale original/recovery completions.
Runtime tests cover fresh read-only metadata, missing/replaced guards, one-use
durable receipts, delayed/replayed requests, systemd evidence rejection,
disconnected callers and unchanged fixed worker paths.

Native Linux smoke proof also ran in WSL with root-owned temporary fixtures only:
real `flock` exclusion, fsynced receipt, replay rejection, explicit new-ticket
recovery and rejection of the superseded original request. A read-only systemd
query confirmed the actual property format. No existing service or live data was
modified. Systemd stop/effects in automated tests are mocked, not live acceptance.
