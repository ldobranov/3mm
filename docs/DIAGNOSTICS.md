# Redacted diagnostics

The Milestone 11 diagnostics bundle is an administrator-only JSON download for
troubleshooting one Standalone device. It is generated in memory and is not
persisted by Core.

Included information is deliberately narrow:

- installed version, release metadata and shared protocol version;
- operating system, architecture, Python version, CPU count, load and memory;
- total, used and free storage;
- SQLite integrity and migration revision;
- loopback Agent health and a one-way device fingerprint;
- latest non-secret backup operation state.

The generator does not read environment values, NetworkManager profiles,
application logs, database rows, uploaded files, extension payloads or backup
contents. Password, passphrase, secret, token, API-key, credential,
authorization, cookie and private-key fields are recursively replaced with
`[REDACTED]`. Common inline bearer, assignment and URL-userinfo forms are also
redacted before deterministic JSON serialization.

The API is restricted to administrators:

- `GET /api/v1/diagnostics/preview` returns the checks and expected size;
- `GET /api/v1/diagnostics/bundle` downloads the redacted JSON document.

The Settings page uses the authenticated API client, so diagnostic data is not
placed in a public URL or browser navigation history.

For an unconfirmed outgoing installation report, use the [local receipt
lookup](INSTALLATION_PEER_V1.md#consent-and-trust-flow). The command
`python -m tools.diagnostics explain peer-report.json` explains the saved observation
offline using fixed labels. A missing record is not evidence that the receiver
never acted; this command and the admin lookup never send the report again.

### Can this host enforce application RAM limits? (CAP20)

In **Settings → Support diagnostics**, look for `resources.cgroup-memory` on
Linux. The first-boot installer and this check read the same kernel data.
The downloaded JSON includes `system.cgroup_v2_memory_controller`:

- `available`: the visible cgroup v2 root offers the memory controller.
  This does **not** mean any particular application has a finite limit.
- `absent`: the controller list was read, but it does not include memory.
  Do not rely on a configured application RAM limit through cgroup v2.
- `unknown`: the observation could not be made. This is not evidence of
  enforcement, or of unlimited memory.
- `not_applicable`: the host is not Linux; no cgroup check was made.

A warning does not change Core readiness or the device's boot configuration.
For one installed application, open **Extensions → its card → Resource
limits** as an administrator. Opening the dialog or choosing **Refresh**
reads the local service's RAM cap, CPU quota (100% = one logical CPU)
and task cap (including threads). A separate section shows the current memory
and task counters for the same service. A missing counter is not zero. CPU
is a quota, not a utilization estimate; there is no sampling loop.
“No limit set at this level” does not rule out a stricter parent group.
A smaller visible parent ceiling is shown separately. That capacity is shared
with siblings, not guaranteed to this app. A partial hierarchy is labelled as
such. **More limits and restart settings** shows the running main process's
soft/hard open-file limits, and the manager's start budget, delays and network
policy. Configuration is not proof of a connector grant or of a running process.
If the service is stopped or changes during the reading, no old limits are
shown. A disabled application is not started to obtain a measurement.
When the service can be identified consistently, the same reading also shows
its state, last result and current automatic restart count, even if it is
stopped or has no measurable limits. A missing count is unknown, not zero.
An out-of-memory result does not establish that the application's own RAM cap
was reached. A running service is not an application health check.

The same on-demand observation is available at
`GET /api/v1/application-extensions/{module_id}/resource-limits`; no SSH
or application permission grant is needed for the administrator. The
[command-line report](../deployment/systemd/README.md#read-an-application-hosts-supervision-and-resource-limits-cap20)
uses the same collector, including on a minimal Node (Agent-only mode).

### Troubleshoot one application without collecting other applications

In **Extensions → Resource limits → Save app diagnostics**, an administrator
can download one fresh service reading plus recent Core refusals that were
bound to this installation generation and package. It also works for a stopped
service. The file is generated on demand, not stored on the device. There is
no polling, restart, application call, permission change or new recording.
The endpoint is `GET /api/v1/application-extensions/{module_id}/support-snapshot`.
Optionally paste one generated task or device command ID before downloading
(`?reference=task_…` or `cmd_…`). This is a primary-key read, not a search
of the device, not a replay and not a new grant. A task reports its journal
state and progress for the exact installation generation and package. A command
reports its queue state for the same owner, package and current command epoch;
only a verified link to a task or a retained correlated sensor event is shown.
The sensor need not be the command target. No payload, raw result, lease,
device name or sensor identifier is selected. A foreign, expired-scope or
absent reference gives the same “not found in scope” answer. A reported
successful command alone is not independent proof of a physical outcome.
New support records also show the number of recorded offers and the approximate
whole seconds from queuing to the **latest** offer. On redelivery this includes
the earlier wait; it is not a first-offer or device-execution time. Missing or
inconsistent clocks produce an unknown interval, not zero. Core deliberately
does not subtract a device-reported completion time from its own clock. A task
shows the last recorded boundary (dispatch, or consumption of its one-use start
permit); a permit alone is not a successful result. Older saved summaries
remain readable without supplying timing that was never recorded.
An installation change or lost admin access discards the download. A busy failure
ring or unavailable service observation is labelled partial. Empty history does
not establish health. Unbound failures, other versions, browser memory,
application data/logs and global history are deliberately excluded.

Open the JSON directly or use `python -m tools.diagnostics explain application-support.json`
(add `--json` for automation). The offline reader uses the same fixed Core case
catalog and never executes imported text. An ordinary managed HTTP application
operation now receives the same `OperationContext.correlation_id` as the
server-generated `X-3mm-Trace-Id`. It is a support reference, not an
idempotency key, transport nonce, permission, or evidence of execution.
For a group of repeated refusals the timestamp and duration belong only to
`timing_trace_id` (the latest occurrence), even when looking up an earlier ID.

For a database error during sign-in, **Support diagnostics → Diagnostic cases**
and the recent HTTP failures export identify whether it happened while reading
the account or session settings, writing the session, or writing the audit.
A busy/locked database is reported only when the driver supplies that code;
read-only, full, open and I/O errors are separate. Unknown causes stay unknown.
The sign-in response stays generic and nothing retries automatically. An audit
write error can follow a committed session; it is not proof of a failed password
check. No SQL text, parameters, account identifiers or tokens enter this record.

## Diagnostic cases: one workflow for people and tools

Settings → Support diagnostics → **Diagnostic cases** collects the current
bounded failure history, matching detailed stages and component observations.
**Save diagnostic bundle** exports the same collected evidence, including this
page's safe browser observations. An explicitly imported producer timeline is
included as a separate unverified snapshot; it is never represented as live or
authenticated provider state. Collection is read-only: it does not invoke an
application, open a terminal, grant access, reconnect, restart or replay an action.

The always-on Core ring observes router-template HTTP **4xx and 5xx** failures,
not just conflicts/server errors. It retains at most100 groups /128KiB for15min
since the group's last observation, at most10 events/s. Identical failures within
30s coalesce into a count, first/latest time and the latest8 request identifiers;
different causes, phases and verified application instances stay separate.
Eviction, expiry, invalid inputs and contention are counted. A new Core process
has a different history identity and an empty ring. No disk spool is introduced.

Session target discovery, ticket admission and WebSocket failures now participate
in the same vocabulary. Stages distinguish UI trust, reviewed resource, executor,
current authority, capacity, handshake, opening, streaming and cleanup. Fixed
categories distinguish missing/current grants, human permission, mismatched
requests, unavailable executors, used IDs, capacity and an occupied binding.
Public refusals remain generic; detailed explanations require a current admin.
When discovery handles a per-resource refusal and returns HTTP200, the same ring
retains its closed original stage/reason with `handled_refusal=true` and the
response's Core trace, even with detailed recording off. HTTP200 describes only
the transport response: a denied resource remains absent from the public list,
while other authorized targets can still be returned. No hidden binding/device
identity or options are recorded. Ordinary successful reads are not recorded.
No exception messages, tickets, JWTs, origins, terminal input/output or request
bodies enter this metadata. A WebSocket observation has `transport=websocket`
and no invented HTTP status; after ticket redemption it shares the ticket's Core
trace. Unknown or possibly executed work is never relabelled as safe to replay.

Startup failures distinguish `session.opening.authority_initial` and
`authority_recheck`, process guard, connection, bootstrap, ownership, artifact
transfer/verification, provider load/open, ready and browser acceptance. The
always-on case retains the failed closed stage/reason and elapsed attempt time;
opt-in detail also records the failing step's duration. Worker reports contain
only validated labels and bounded timing, never exception messages or terminal
contents. A trusted early worker acknowledgment pins its exact session/profile
and cleanup cgroup before code transfer; it does not mean provider readiness or
permit I/O. Current authority is still required before acceptance. Cleanup still
requires actual OS evidence for that pinned worker; EOF, a ready label, absent
ownership or an old process exit is not by itself proof of cleanup. Diagnosis
never releases a reservation or reconnects automatically. Private IPC changes
require a coordinated Core/executor update; the application SDK provider contract
is unchanged.

Every HTTP response carries the Core-generated `X-3mm-Trace-Id`; client-supplied
values cannot choose that identity. The Core UI preserves a valid reference in
`ApplicationHostError.requestId`. Its bounded in-memory browser ring records
only fixed operation/transport labels, observed HTTP status and a validated Core
reference when present. It does not collect URLs, headers, bodies or exception
text, and does not transmit observations in the background. Reload/logout clears
browser history. An absent response does **not** establish DNS failure or prove
that a request never reached Core. Browser observations cannot authorize anything.

The browser ring also records local refusals before HTTP and contract checks after
a successful HTTP response: missing injected host/build, mismatched host features,
invalid/duplicate targets, missing or ambiguous resolution, an exact-request
mismatch, invalid ticket response and socket construction/protocol failure. Fixed
`stage`, `cause` and optional `last_passed_stage` identify the first refused check;
`response_observed` distinguishes a received response followed by local refusal
from an unrecorded HTTP outcome. A validated trace is associated with its specific
response, not a shared last-request variable. Wrapped errors retain their first
observation instead of producing misleading duplicate causes. These labels do not
change public errors, ticket dispatch, timeouts, current access checks or replay
fences. The exported JSON and offline CLI expose this separate untrusted evidence;
they never include target options, addresses, exception text or session contents.
`targets_empty` distinguishes an empty accepted list from `target_not_found`
(a nonempty list with no matching caller ID). Neither label proves which rights
or provider check failed; correlate its Core trace with the retained discovery
case. Discovery and its diagnostic collection never open an executor session.

To capture a terminal refusal: keep the failing tab open, attempt **Connect once**,
then navigate within the same application page to Settings → Support diagnostics →
**Collect observations**, and save the bundle promptly. Do not hard-reload or log
out first: browser history is page-local and expires after15min. Core-only API/CLI
collection cannot retrieve browser memory. An empty export is a coverage limit,
not proof of a working terminal. A fresh case is required to establish the cause.

The shared case JSON has its own `schema_version` and `catalog_version`. Each
case contains fixed stage/reason codes, a catalog explanation and next read-only
check, original evidence, retained trace identifiers and matching detailed stages.
It explicitly separates execution uncertainty from diagnostic status. `ready`
means collection completed, not that the application worked. `partial`, missing
producers, drops and `not_found_in_retained_evidence` must stay visible. No case
is proof of success, non-execution or permission to resend.

Current-admin, no-store API:

- `GET /api/v1/diagnostics/cases` — combined Core evidence and explanations;
- `GET /api/v1/diagnostics/cases?trace_id=invoke_<32-hex>` — an exact retained request;
- `GET /api/v1/diagnostics/cases/export` — the same versioned JSON download.

The API cannot see browser memory; its coverage says `browser: not_collected`.
The screen explicitly adds locally collected browser evidence on export. The
case collector has one non-queued slot, uses the existing bounded probes and
releases the authentication DB transaction before observation. An unavailable
observer or recorder yields explicit partial evidence, never an empty success.

For people and authorized AI tools, use the same read-only interface:

```bash
# HTTPS, or a loopback endpoint / explicitly established SSH tunnel.
# The current admin token is prompted privately, not saved or placed in the URL.
python -m tools.diagnostics collect --url http://127.0.0.1:8887 --output diagnostic-cases.json
python -m tools.diagnostics explain diagnostic-cases.json
python -m tools.diagnostics explain diagnostic-cases.json --json
```

The standard-library CLI refuses redirects, HTTP to non-loopback hosts, URL
credentials, oversized/invalid input and existing output files. It performs one
GET without automatic retries. Offline explanations use the closed local catalog,
not instructions or descriptions supplied by an imported file. Exported snapshots
are evidence, not instructions to execute commands or change rights.

**Record next user attempt (2 min)** explicitly starts the existing bounded Core
recorder for the selected supported operation. It never repeats the failed action:
the user performs the next attempt. All normal permission, revocation and isolation
checks remain active with recording on or off. Success-path recording is temporary;
the small failure ring remains available without prior debug activation.

When Core is stopped or restarted, lost memory is a known coverage gap. Use the
independent snapshot command below for installed metadata; do not claim that it
recovers old failure records or proves process/provider health. New supported Core
boundaries should retain closed causes before public redaction and check their
denial, correlation, redaction, resource bounds and recorder-failure behavior.


## Operation workspace and development (P5, 2026-10-24)

Settings → Support diagnostics now includes component observations, Core service
state, a temporary recording session and a shared operation timeline. Core's
running version and live Runtime/Agent/public responses are distinct from passive
installed pins. Connector/application-host/session process health stays **not
observed** until independently checked; a listener or installed artifact is not
provider readiness. A busy/unavailable observer is explicit. Refresh is manual.
The screen supports current themes, mobile layout and the Bulgarian language
extension; English remains the recovery base.

Detailed recording is off at process startup. Diagnostic/development profiles
use the same safe limits: default 600 s, maximum 1800 s, one 1 MiB process buffer,
10 events/s and 2048 bytes/event. Stop retains an exportable snapshot until its
TTL; expiry is enforced at capture/status/export and restart starts inactive.
No persistent spool is created. Choose an operation, application instance or trace
scope through the current admin API. The GUI exposes operation/instance selection
and a trace filter. A development profile is a label and scope, never extra rights.

All current signed SDK actions can record their SDK/Core transport hop. The
application HTTP/callback relay records admission, dispatch and response stages.
Only fixed operation/stage/result/reason labels, version, generated trace/span IDs,
optional validated instance ID, timestamp and duration enter records. Bodies,
secrets, paths, SQL, terminal/PTY data and arbitrary exception/log strings are
excluded. The support bundle remains separate from detailed records.

For a verified negative application-host response, Core also records one
failure-only `application.host_request/context/storage/handler/result` stage and
a fixed `host_*` category. These labels distinguish request/context checks, SDK
refusals/transport failures, SQLite contention, built-in error families and invalid
handler results. They contain no exception text, arbitrary class names or stack
traces. The host sends a generic error instead of the caught exception's message.
The same Core-generated trace ID connects this observation with the HTTP409 and
the enclosing invocation; the detailed record also retains the instance and
host-reported elapsed milliseconds. The bounded recent-HTTP-failures ring retains
the stage/category even when the opt-in session is off. Invalid, unknown or
unsigned detail is not imported. Healthy calls add no host record.

This requires both the updated Core and the independently pinned application
host. Replacing only Core does not make an older host produce this information.
Host detail is an observation, not a physical execution receipt or proof of
non-execution. HTTP409, current policy checks and the no-replay boundary are
unchanged; a nested SDK refusal never makes the outer call safe to replay.

The timeline combines current Core records with **one explicitly imported producer
NDJSON export**. It labels imported records as snapshots, shows producer drop
counters, missing producers and truncation, and can save the merged JSON snapshot.
Core does not silently enable recording in other processes. Runtime/Agent/session
traces absent from the selected exports remain missing. Imported metadata is an
observation, not authenticated authority or live state. Producer wall clocks can
differ; a shared trace ID correlates one transport hop, not a whole business
transaction. Current-format imports require the current scope/instance fields.

All endpoints below require a current admin login and use no-store responses:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/diagnostics/workspace` | Fixed component pins/versions, bounded local observations and Core services |
| `POST /api/v1/diagnostics/session` | Explicit TTL/profile/operation/instance/trace scope |
| `GET` / `DELETE /api/v1/diagnostics/session` | Inspect / stop the Core recording |
| `GET /api/v1/diagnostics/session/records` | Bounded Core NDJSON download |
| `GET /api/v1/diagnostics/timeline` | Current bounded Core timeline |
| `POST /api/v1/diagnostics/timeline/merge` | Validate one NDJSON export and return a combined snapshot |

The observer has one non-queued slot, including metadata reads, and fixed loopback/
Unix probes with absolute deadlines (Runtime 0.4 s, Agent/public 0.3 s each).
No auth DB transaction spans those probes. Merge has one non-queued slot, a 4 MiB
input cap and five-second upload deadline; decoding runs outside the Core event
loop. The response displays at most 500 records. Imports are not retained in Core.
Malformed labels, extra fields, duplicate JSON keys, non-finite values and foreign
formats are refused. Collector failure cannot replace an operation's result.

For interactive input latency, record `session.stream` during one already-approved
session. Closed stages separate `session.input.before`, `.provider`, `.after` and
`.ack`; `session.authority.queue`, `.thread_queue` and `.lock_queue` distinguish
per-session, thread-pool and shared-authority waits from the actual current check.
Output-send/queue and current-runtime timings are separate. Timings contain no
input/output bytes or commands. Successful timings require the explicit recorder
and retain its existing TTL/rate/buffer limits, so inspect drop counters before
assuming a complete trace. Failed stream steps retain their first closed phase
and safe inner authority category even without recording. Failure-history duration
is the complete session attempt; detailed step duration is not keystroke latency
unless it covers that particular input phase. Diagnostics never disable current
login, grant, revocation, resource or runtime checks.
The ACK phase includes its send-lock wait and fresh post-provider input check.
For an empty provider response this is one check immediately before ACK, not a
second identical check before waiting for that lock. Nonempty output is still
checked before output and again before ACK. Nested/concurrent spans must not be
summed to infer one keystroke's duration.

For an independently started SDK recorder, use the normal client credentials;
diagnostics neither supply nor change them:

```python
from packages.application_sdk import SDK_VERSION, ApplicationPlatformClient
from packages.protocol.diagnostics import DiagnosticSession

records = DiagnosticSession("sdk", SDK_VERSION)
records.start(300, profile="development", operation="installation.identity.get",
              instance_id=instance_id)
client = ApplicationPlatformClient(socket_path, instance_id, secret, diagnostics=records)
# Perform the already authorized operation, then export explicitly.
with records.export() as chunks, open("sdk-records.ndjson", "xb") as output:
    for chunk in chunks:
        output.write(chunk)
```

## Offline and independent development commands

The installed local path works with Core stopped. From the current deployment
folder, using its Python environment (or the Node protocol environment):

```bash
python -m packages.protocol.diagnostic_snapshot --output /tmp/device-observations.json
python -m packages.protocol.diagnostic_snapshot --records sdk-records.ndjson --output /tmp/with-sdk-records.json
```

It reads only fixed component metadata and the explicit bounded export, imports
neither backend nor SQLAlchemy, and never contacts Core, starts services, reads
logs or changes networking. An absent Core is listed as missing. Installed pins
are passive observations with unknown process health. Output uses exclusive create
and cannot overwrite an existing report. `python -m tools.debug_snapshot` is the
source-tree alias.

The development CLI uses existing validation/upload/activation APIs. Select an
**explicit owned isolated Core URL**; the command does not start a lab server.
Tokens are prompted hidden and never saved, placed in URLs or retried. HTTPS uses
normal certificate verification; HTTP is restricted to loopback, redirects/proxies
are disabled, and a mutation timeout is unconfirmed. Current native review, UI
trust, grants, lifecycle and data rules remain mandatory.

```bash
python modules/public-web-reference/build_reference_package.py --output .runtime/public-a.zip
python -m tools.extension_dev validate .runtime/public-a.zip
# Run affected checks with tools/dev_lab.py before local activation.
python -m tools.extension_dev --url http://127.0.0.1:18887 upload .runtime/public-a.zip
python -m tools.extension_dev --url http://127.0.0.1:18887 activate <exact-archive-sha256>
python -m tools.extension_dev --url http://127.0.0.1:18887 trace-start --operation application.invoke --ttl 300
python -m tools.extension_dev --url http://127.0.0.1:18887 trace-export --output .runtime/core-records.ndjson
python -m tools.extension_dev --url http://127.0.0.1:18887 trace-stop
python -m tools.extension_dev --url http://127.0.0.1:18887 rollback <previous-archive-sha256>
```

Port 18887 is an example for a separately started disposable Core. Activation and
rollback each explicitly select exact uploaded bytes. Rollback requests the old
package through the same lifecycle rules; it is not permission to reset data,
downgrade a schema or replay effects. Keep each package's own data and outcome
receipts. Source builds, local tests and compatible component/package iteration
require no Core release or global development mode.

Local P5 acceptance runs two existing neutral packages (application-reference and
public-web-reference) with real native hosts, signed HTTP/Runtime calls, a fixed
Core/Runtime process, A→B→A and failed-candidate recovery. The compatibility package
fixtures are explicitly prepared in the disposable lab; they do not replace native
review acceptance. A separate current scoped SDK read succeeds then remains denied
after revocation while diagnostics is active. Read-only restored-host readiness is
observed before explicit outcome review. See WORKING_STATE.md for exact source,
artifacts and targeted evidence; installed/ARM/ARMv6/full-CI acceptance remains P6.
## A login says storage is busy

A genuine SQLite busy/locked result during login returns **503** with
`Retry-After: 2`. It is not a wrong-password response. Session creation and
its login audit entry commit together; the server does not retry the login or
return a token after a failed commit. Copy the request ID to inspect the stage
of that specific request. Other database errors are not labelled busy.

To look at **current** activity, open the administrator's operation diagnostics
and choose **Who is writing to the Core database? → Measure for 5 seconds**.
Only an explicit request starts observation; the page never polls. Core releases
the administrator's read transaction during the measurement, checks access again
before returning the result, and allows only one observation plus a 30-second
cooldown. A busy/unavailable measurement is different from a completed one with
no observations. **Save measurement** exports the fixed counters for
`python -m tools.diagnostics explain core-database-sample.json --json`.

The duration starts at the first successful ORM write or explicit
`BEGIN IMMEDIATE` on a **newly opened connection** to Core's main SQLite engine;
it ends at the commit/rollback request or the sample boundary. Repeated writes
in that transaction count once. SQL text, parameters, data, accounts, paths and
request IDs are not collected. An already open connection, untyped raw write,
another process, a failed lock attempt or time spent inside the final commit
may be invisible. A long observation is a lead for investigation, **not** the
proven owner of a previous lock or a reason to stop/restart a service.

## Which backup check was performed?

**Settings → Backup and recovery → Check readiness → Save check summary**
exports the last observation's fixed reasons and counts. It does not export
the archive, the administrator's per-app inventory or the original issue text.
Use `python -m tools.diagnostics explain backup-readiness.json` to distinguish
a blocked capture from a warning about automatic application reactivation.

A `portable_recovery_check` is a different observation: an operator checked
the bytes of a chosen portable file against the intended Core release and
architecture in [private offline staging](BACKUP_AND_RESTORE.md#checking-an-exported-file-without-importing-it).
The same reader accepts its JSON and regenerates guidance from fixed reason
codes. Treat both as unsigned observations; neither proves that the replacement
device has booted or that a restored app has been activated. Do not send a
recovery password, portable backup or raw manifest to explain these results.

## Preserved application data

In **Extensions → Preserved application data**, a review warning means at
least one stored cleanup identity could not be verified. The panel still
lists other verified, uninstalled owners. It never guesses the unknown owner
or offers that record as an erase target. A failed request is different from
a successful empty inventory. Listing or refreshing never erases anything;
permanent removal of a verified row still requires separate confirmation.
Local removal does not delete previously exported files or backups.
