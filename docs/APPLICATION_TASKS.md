# Scoped tasks, intervals and calendars

The current CAP08 profile is `bounded_task_v1`: one-shot, interval and IANA calendar
tasks, with a bounded command-effect adapter. The already accepted
`bounded_result_once_v1` declaration remains result-only and one-shot. Both use one
execution journal and worker, not parallel implementations. Legacy descriptor
`jobs`, schedules and `kind: job` remain refused; new recurrence is explicit SDK
admission under a declared `task:<id>` grant.

## Declaration and authority

An application descriptor declares `tasks`, each with `task_id`,
`handler_operation_id`, the exact profile, `max_runtime_seconds` (1–10),
`max_delay_seconds` (0–3600) and `max_pending` (1–8). Each dedicated handler is
`kind: task`, internal-only, idempotency-required and has the same timeout budget.
Input and result schemas contain at most eight bounded scalar fields. Wire data
uses finite JSON-safe numbers, strings up to512 characters, field names up to128
characters, and at most8192 encoded bytes per object. No nested/opaque payload.

The existing native package consent approves exact `task:<task_id>` scopes in
sealed authority context11. Compatibility mode cannot schedule work. Scope
selection, code approval, configuration, artifact, installation incarnation and
execution epoch remain Core decisions. Migration creates no trust or grants.

The `bounded_task_v1` artifact may combine tasks with exact command bindings.
Its sealed context11 approves the task and command scopes separately. The
result-only declaration cannot acquire command effects. Connectors, event/
publication, session, checkpoint, peer/platform, public HTTP and scoped file/
relational composition use their own other capability profiles; they are not
implicitly granted by a task. A trusted native host can keep its own local data
and attempt journal. This is not a hostile native-code sandbox.

## SDK and identity

```python
receipt = platform.submit_task(
    "calculate", request_id=persisted_uuid,
    payload={"upper": 100, "pause_ms": 0},
    due_at=aware_utc_due, not_after=aware_utc_deadline,
)
observed = platform.lookup_task("calculate", request_id=persisted_uuid)
```

Persist the UUID before sending. Admission returns `queued`, not execution.
Repeating the same installation-incarnation/task/request with exactly the same
input and UTC-normalized timing returns its original journal entry. Changed data
or timing is refused. A lost reply is resolved by lookup, never automatic submit
replay or a replacement UUID. The SDK has no automatic mutation retry.

The caller supplies no device, path, owner, human identity or worker generation.
Its authenticated instance selects its owner. Lookup remains a historical read
after grant withdrawal/disable, but a different installation or incarnation cannot
read the receipt. An application exposing scheduling to humans must separately
authorize its users, as for the existing command SDK.

`due_at` and `not_after` require timezone-aware timestamps, normalized to UTC.
Future delay cannot exceed the declaration. The deadline must permit the declared
runtime after due time and must be within30 seconds of due time. An already-due
request can be admitted only while its original deadline remains open.

## Recurrence and clock policy

```python
receipt = platform.create_task_schedule(
    "calculate", request_id=persisted_schedule_uuid,
    payload={"upper": 100, "pause_ms": 0},
    rule={"kind": "interval", "every_seconds": 60},
    start_at=aware_utc_start, end_at=aware_utc_end,
    max_occurrences=1000, history_limit=16, start_window_seconds=5,
)
state = platform.lookup_task_schedule("calculate", request_id=persisted_schedule_uuid)
platform.cancel_task_schedule("calculate", request_id=persisted_schedule_uuid)
```

An interval is UTC-anchored, 5–31536000 seconds. A calendar rule declares `kind:
calendar`, an installed IANA `timezone`, `hour`, `minute` and distinct `weekdays`
(Monday0 through Sunday6). Defaults are every weekday, `misfire: skip`, `gap: skip`
and `fold: earliest`. These policies are fixed, not alternate unchecked modes.
Calendar conversions use Python [ZoneInfo](https://docs.python.org/3/library/zoneinfo.html).
Nonexistent local instants, including half-hour gaps or skipped civil dates, do
not move to another business time. An ambiguous local time executes at its earliest
UTC instant only. Interval rules retain their UTC duration across DST.

Every schedule has an exclusive end, at most 366 days after its start, and a
1–1000000 admission limit. Its initial start cannot exceed the declaration's delay
budget. Each worker poll proposes only the latest due occurrence. Core verifies
the rule/instant and advances a durable cursor in the same transaction as the
shared task admission. A restart/forward clock jump skips old occurrences without
a catch-up burst; clock rollback cannot reopen an already-consumed cursor. An
occurrence outside its 1–20 second start window is skipped. Its deadline includes
the bounded runtime and is at most the schedule end. One occurrence per schedule
can be pending/running; busy slots are skipped rather than piled up.

The worker owns polling and waiting. Core has no scheduler loop, app execution or
timer registration. Its metadata responses contain only admitted rules/cursors;
workers cannot choose owners, payloads or handlers. Failed/lost admission replies
are followed by a fresh cursor read, never replay of an uncertain handler.

Schedule states are active, cancelled, exhausted or blocked. Lookup remains owned
by installation and incarnation after revocation/disable. Grant/epoch/artifact
drift cancels the old schedule permanently; fresh consent requires a fresh
schedule intent. Cancellation stops future and queued work, including a final
queued occurrence after its admission limit, while issued starts remain unchanged.
An unknown task/issued effect blocks further owner executions and schedule
admission until explicit stopped-app reconciliation; no implicit resume/retry.

There are at most eight live schedules per owner,32 live schedule owners and128
schedule identities per incarnation. Periodic history retains the explicit last
1–64 known terminal occurrences. Pending/unknown records and manual one-shot
receipts are never pruned. Occurrence request IDs use reserved `occ_<32 hex>`;
lookup can return not_found after retention, but manual submit refuses that
namespace, and the cursor prevents readmission. A full manual-history budget
blocks the schedule with `history_full` instead of discarding other receipts.

## Command effects from a task

```python
receipt = platform.submit_task_command(
    context.task_execution, "output", request_id=persisted_effect_id,
    arguments={"channel": "gpio.output.1", "value": True}, ttl_seconds=5,
)
# After a lost reply, query the same logical request. Never submit a replacement.
observed = platform.lookup_task_command(
    context.task_execution.task_run_id, "output", request_id=persisted_effect_id,
)
```

This reuses command admission, provider/declaration pinning, device queue and the
one-use physical execution permit. Core rechecks the separately approved task
and command scopes, exact started task token and UTC/boot-monotonic lease both at
admission and before the physical permit. A task-bearing artifact cannot bypass
this by using ordinary submit_command. IDs are namespaced by task run/binding;
at most eight command intents are admitted per run. Their deadlines cannot exceed
the task lease. A completed/stopped/stale task cannot issue a later physical permit.

Handlers observe their original command outcome before returning success. A
signed handler result does not manufacture a confirmed device result. An issued
but unconfirmed command makes the task unknown and holds the owner slot even if
the handler claims success or fails. Later periodic occurrences cannot silently
repeat it. Already-issued physical permits cannot be recalled. No automatic
handler/effect retries are implemented; a new intended occurrence is distinct from
retrying an unknown old effect. External delivery through other resource families
needs that family's explicit composition contract.

## Execution and failure states

1. Core durably admits the task under the existing key/authority guard. The task
   journal pins its exact incarnation, package, epoch and sealed grant revision.
2. An optional, separate unprivileged worker polls Core. A claim is durably marked
   `running` before any IPC; this state means a lease, not proof code has begun.
3. The worker performs a signed `three_mm.task.info` probe outside Core. Core
   verifies support for the live start gate, instance, artifact and configuration,
   then rechecks current task authority and exposes one signed invocation. The
   old `three_mm.host.info` contract retains its exact existing shape.
4. Immediately before plugin code, the application host consumes a one-use
   `task.start` permit through the signed SDK. Core rechecks the current grant,
   owner, dispatch token and deadline. The host checks reply duration and both
   absolute and remaining lease time before entry. A consumed permit cannot start
   again after native-host/Core/worker restart.
5. Core verifies the application's signed response, original invocation identity,
   result schema and live lease before recording `succeeded`/`failed`. The worker
   has no Core imports, DB, signing keys or permission to choose another handler.

Core performs neither application execution nor host/network waiting. Host probes
and execution sockets belong to the worker. The lease ends at the earliest UTC
deadline or monotonic budget; a different Linux boot makes a running task unknown.
The handoff/start exchanges consume the lease budget too. Wall-clock rollback
cannot extend execution authority. These are bounded software leases, not a hard
real-time or hostile native-code CPU termination guarantee.

Progress is monotonic0–99 through `task.progress` and the current execution token.
Only a valid confirmed result yields progress100/success. `cancel_task` cancels
queued work; running work is returned unchanged. Cancellation cannot recall a
consumed start permit or pretend that code stopped.

Before an execution request was exposed, a failed handoff is `failed/not_dispatched`.
After exposure, lost replies, worker loss, deadline/lease expiry or lifecycle drift
remain `unknown` unless a valid in-time response was recorded. There is no automatic
redispatch, even if a claim probably did not execute. An unknown task holds that
installation's execution slot; already-issued local code may still need stopping.
Queued work from a retired grant/epoch/package is cancelled and is not resurrected
by fresh consent. Historic completed results remain historic results.

Reconciliation uses administrator
`POST /api/v1/application-extensions/{module_id}/tasks/{task_run_id}/resolve` with a
fresh32-hex `request_id` and `confirmed_external_outcome_reviewed: true`. Stop the
application through normal lifecycle first and review its actual outcome. The
existing current-administrator action ledger seals an idempotent resolution;
it clears the claim as `resolved`, never manufactures success or dispatches work.

## Updating a stopped task package

The generic native activation guard requires approval of the exact artifact.
Updating an existing task installation therefore first stops it through normal
lifecycle, then registers the uploaded immutable replacement without running code:

```text
POST /api/v1/application-extensions/packages/<new-sha256>/stage
{
  "request_id": "<persisted 32-hex intent>",
  "expected_artifact_sha256": "<old artifact SHA256>",
  "expected_revision": "<current grant_record_revision>",
  "configuration": {}
}
```

The current administrator is rechecked in the sealed action transaction. The
installation must be disabled with no unresolved task or historical job claims.
This is now the common stopped-package preparation path for ordinary native
applications, including command and administration UI applications; a task
declaration is not required. CAS binds the old
artifact/revision, incarnation, epoch, instance and candidate metadata. Only
declared device selections may change in this bounded adapter. Staging fences
old command rights and records the new package as disabled/review-required with
no active version. It preserves the incarnation, data and historical results.
No helper, wheel import, migration or application startup occurs during staging.

The inert registration is sealed against the Core identity, principal, exact
package/hash/version, instance and configuration fingerprint. Plain database
metadata or an altered registration marker cannot establish review authority.
An exact action replay returns its historical result without another effect.
Then use normal package consent preview/allow for the new artifact while stopped
(saved permission, not effective execution), followed by normal activation.
Existing native guards and lifecycle checks apply; fresh consent is required
before code can start. The shared preparation route does not replace relational
migration/session-provider prepared lifecycles or reopen old schedules after
upgrade. See [Extension lifecycle](EXTENSION_LIFECYCLE.md#preparing-another-native-application-version)
for the Extensions UI flow and preparation without an existing grant.

## Budgets, packaging and rollout

One running/unknown execution per installation; at most eight pending records per
installation and at most the declared number per task. There are at most32 live
owners globally and1024 run records per incarnation. The journal refuses
new work when full; only explicit periodic terminal-history retention prunes runs.
The worker processes one handoff at a time. Queuing does not guarantee starting
before a deadline; missed queued deadlines expire without code execution.

The additive Alembic revision is `4f29a071b819`, after `3e189f465708`. It creates
only `application_task_runs`; the legacy baseline excludes this later table.
Downgrade removes an empty journal only. The follow-up `5a30b182c920` adds schedule
ownership/cursors, reserved occurrence identities and command task provenance;
existing one-shot outcomes stay intact. It refuses downgrade with retained
schedule/occurrence/task-command evidence. Recovery uses a verified backup, not
destructive automatic downgrade. Uninstall also refuses unresolved running/unknown
task claims. Operational status exposes generic task journal counts and schedule
state, without business payloads. Old job rows remain historical recovery evidence;
their execution path is not restored.

Matching new Core, Platform Runtime and application-host artifacts are required.
The Runtime artifact includes an explicit optional `--task-worker` entry point.
`deployment/systemd/3mm-task-worker.service` is an opt-in unit; the normal installer
does not select or enable it automatically. The owner VM rollout explicitly
installed/enabled it with matching component pins. Stop this worker before a
Runtime pin change and restart it after verifying that artifact. Missing worker/
host support cannot grant a compatibility execution path.
Core administration remains independent of this optional executor.

Runtime artifact validation now checks the release's own bounded file map/hash,
allowed Runtime/wire source namespace and required entrypoint, rather than this
updater's build-input list. Adding a worker file does not invalidate an immutable
older artifact or independent component rollback. API additions still need matching
Core/Runtime/host rollout and explicit grants. Pins/backup evidence for the owner
VM live in `WORKING_STATE.md`; populated task history is never silently downgraded.

The neutral package is `modules/task-probe`, now0.2.0, with independent arithmetic
and command-consumer variants. The original0.1.0 package remains immutable.
`examples/task_probe` schedules a bounded arithmetic result using only the SDK.
The acceptance uses real sealed consent, signed SDK transport, a packaged Runtime,
a packaged worker, a self-contained native host (`-I -S`, no Core dependencies),
durable queue/start permits, and an application-local attempt journal. Owner VM
acceptance additionally exercises the real optional systemd worker and distinct
UID/namespace restrictions. The sample provides a terminal SDK exercise, not an
operator scheduler screen. See `modules/task-probe/README.md` for the ready command.
