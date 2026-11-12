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
