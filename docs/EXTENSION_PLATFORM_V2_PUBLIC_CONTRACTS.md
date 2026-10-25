# M20 — public extension schema catalog, first WP1 contract slice

Date: 2026-10-08. Local implementation; no deployment or release. This follows
the accepted read-only Package Inspection slice. It does not complete WP1/WP4
or enable remote/untrusted execution.

## Current Core–Runtime transport boundary, 2026-10-23 (P3c/P4b)

The local SDK/Core share the discovery model in `three_mm_protocol.platform_transport`.
Framing and limits live in stdlib-only `three_mm_platform_wire`, also used by the
independent Runtime; Runtime imports no Core, SDK or Pydantic.
`PlatformDiscoveryV1` describes transport contract **1**, separately from SDK
**1.3**, manifest v2 and the descriptor versions below. This transport result is
not a package descriptor or an additional entry in the structural schema catalog.
The authoritative discovery model is used by both the server and SDK.

`ApplicationPlatformClient.discover_platform()` sends one authenticated
`platform.discover` call through the Runtime socket below. Its only request fields
are `version`, `request_id`, `timestamp`, `instance_id`, `action`, `signature`.
The installation must currently be active. The response contains the supported
operation names, bounds, authority mode and current transport/recovery/application
metadata. Discovery initializes no identity, key, grant or worker. It reads no
private authority key and creates no reusable permission. Unsupported discovery
or a malformed response is an explicit failure; there is no legacy fallback.

| Boundary | Current enforced contract |
| --- | --- |
| Framing | One UTF-8 JSON object plus newline per connection; at most 6 MiB including newline in either direction; unique keys, finite canonical JSON; no frame batching |
| Authentication | Instance HMAC-SHA256 over canonical JSON, integer wire version 1, bounded request ID, integer timestamp within 30 seconds; unauthenticated requests get no signed response |
| Active connections | At most 16 handlers, no unbounded executor queue; excess anonymous connections close before dispatch |
| Read deadline | Five seconds for the entire incoming frame, including trickled bytes |
| SDK deadline | 35 seconds across connect, send and read; progress does not reset the deadline |
| Duplicate requests | At most 4096 recent `(instance_id, request_id)` entries for 60 seconds; duplicate IDs refuse dispatch, full capacity refuses admission without eviction of live entries |
| Response | Existing signed success envelope remains unchanged, including boot-startup consumers; a signed failure adds a fixed `reason` |
| Admission | Every operation uses its existing current Core authority adapter; discovery cache allowance is zero, and supported operation names are not granted scopes |

Failures use fixed reasons: `request_invalid`, `authentication_failed`,
`installation_unavailable`, `operation_unsupported`, `operation_denied`,
`operation_failed`, `deadline_exceeded`, `response_too_large`, `request_replayed`
and `overloaded`. Local SDK failures also distinguish `transport_unavailable`
and `response_invalid`. Unexpected internal exceptions return a generic message;
family validation refusals retain their bounded existing message. Pre-authentication
failure or pre-authentication overload can only be observed as a transport/invalid
response failure, since no authenticated identity exists to sign a refusal.

The SDK exposes conservative `phase` and `retryable=False`. Before sending any
bytes, a local failure is `not_dispatched`; after a possible partial send, a lost,
invalid or late reply is `execution_unconfirmed`. There is no automatic retry,
replacement operation ID, fallback effect or outbox drain. A caller must use the
original durable domain ID and that family's status/receipt protocol. A duplicate
transport refusal does not prove that the first operation failed. The bounded
in-memory replay set is not durable exactly-once execution and resets on restart.

Generation semantics:

- `transport_generation` changes with the Runtime process generation; it is a connection
  observation, not an authority token or permission to resume an operation.
- `recovery_generation` and `authority_revision` reflect the current Core authority
  guard. `application_incarnation`, `authority_epoch` and `authority_mode` reflect
  the current installation. Changes require discarding remembered discovery/state;
  unchanged values still do not authorize an effect. Every effect re-resolves the
  existing sealed grant, resource, lifecycle and recovery fences inside Core.
- Core/authority unavailability never grants new work. Existing family-specific
  receipt/status paths remain responsible for observing already-admitted work.
  Disconnect/timeout cannot roll back or prove cancellation of an external effect.

P4b completes the independent **signed SDK transport** boundary:

| Operation/path | Current owner and routing |
| --- | --- |
| All 25 current signed SDK operations | One SDK `socket_path`; host activation writes `THREE_MM_PLATFORM_RUNTIME_SOCKET`, default `/run/3mm-platform/runtime.sock`, into its `platform_socket` metadata |
| Core SDK entry | Private `/run/3mm-core-authority/authority.sock`, ABI **2**; Runtime SO_PEERCRED UID verified before frame reading/authentication |
| Relational boot original caller | Exactly one original accepted AF_UNIX stream FD passed with SCM_RIGHTS; Core reads its real kernel SO_PEERCRED and configured application root |
| Runtime component | `/opt/3mm-platform-runtime/releases/<build-id>`, own `.venv`, atomic `current`/`previous`, independent health/update/rollback |

The old public Core SDK listener/configuration is removed. SDK no longer accepts
`runtime_socket_path`, and `platform_runtime_socket` metadata is removed. Current
host metadata uses one endpoint; old local metadata must be regenerated through
reactivation. There is no automatic fallback, retry or signed-request rewriting.
This coordinated prototype change does not alter manifest v2, SDK wire/discovery
version 1 or SDK 1.3. The private ABI 2 explicitly rejects old ABI 1 components.

Both public and private frames use the six-MiB ceiling. Runtime has 16 handlers,
the private Core gate four; frame reads have a five-second absolute deadline.
SDK and Runtime transport use a 35-second budget, including partial progress;
health probes use a three-second private hop. A timeout/lost response remains
unconfirmed and never proves that a domain effect did not happen.

ABI 2 sends a one-byte origin marker, optional SCM_RIGHTS FD, then the original
signed JSON. Only SDK boot requests accept/require an original-client FD.
P4d1 public begin replies carry a separate admitted service socket (see below). Multiple/truncated/unexpected,
non-Unix, non-stream, listening or unconnected descriptors refuse admission.
Core closes received duplicates on every exit and uses MSG_CMSG_CLOEXEC. Closing
that duplicate does not shut down the original application's socket. Forwarded
PID/UID fields never substitute for the original kernel peer, signed request or
current boot/resource authority. Original-peer transport tests do not claim full
root-helper/installed-device boot acceptance.

Core authenticates the original app HMAC/current installation and uses existing
family-specific grants, revocation/recovery fences and durable receipts. Runtime
receives no Core DB/private keys, signs no response and caches no authority.
Identity read remains the initialized scoped adapter even for compatibility;
compatibility cannot initialize identity or use its private key through this path.
Other families keep their existing authority modes and unsupported-action refusals.
Discovery is metadata, never a grant; retired scheduled jobs stay refused.

Core derives `transport_generation` from the verified Runtime peer's kernel boot
ID, PID/start ticks and effective UID. Core/recovery/application generations retain
their existing meaning. OS-peer-verified nonce probes report Core process/build
binding without application authority. Both peers verify their expected nonroot UID.

Runtime's service has no shared global environment, Core state access or app/key
supplementary group. Root prepares the setgid client directory; socket inheritance
permits clients without granting Runtime their key-file access. Archives validate
exact executable hashes/private ABI before activation. Compatible update/rollback
restarts only Runtime and checks unchanged Core process/release; failed candidates
revert. Pending transactions reconcile on the next explicit `recover`/update,
without application replay. Root-owned host service policy stays outside the
executable archive. [Current commands](CORE_STABILIZATION_ACTION_PLAN.md).

Current Core domain adapters still perform admission/execution. Public response
waiting is extracted in P4d1, durable event response I/O in P4d2 and connector
network execution in P4d3 below. Application-host
artifact independence is implemented below. This
transport delivery is neither complete execution isolation nor installed acceptance.

The Python deadline rejects late admission/results and bounds transport waits. It
cannot kill an adapter stuck inside native/database work. That handler retains its
capacity slot; shutdown closes sockets and waits at most five seconds, reporting
unfinished work and refusing an in-process listener restart while a handler lives.
P4a/P4b supply the independent signed-transport process and service policy. This is
not installed-device/cgroup acceptance, full provider isolation or full CI.
Coordinated changes to this contract must update Core, SDK/Runtime consumers and
real wire/authority/negative/recovery tests together, with an explicit contract
revision for incompatible semantics; no compatibility proxy is added.

Scheduled application jobs are retired from the current package/execution path.
The old compatibility-only scheduler is removed, all job operations/schedules are
rejected during package validation, and direct gateway job dispatch is refused in
all authority modes. Historical records and stopped-admin resolution remain for
outcome review; they cannot schedule or retry work. No new scoped job authority
profile is inferred. See [historical job handling](APPLICATION_JOB_SCHEDULER.md).

## Public response handoff, 2026-10-23 (P4d1)

Public feature contract **1** uses private ABI **2** framing and the existing
UID-authenticated Core authority endpoint. Its feature probe must echo that
contract before an enabled public Runtime reports ready. It adds no SDK action
or public execution grant. Core's old public listener/settings are removed.

Runtime owns `/run/3mm-public-web/runtime.sock`, group `3mm-public`, in a separate
8-slot pool. No app/key supplementary group is added. The external HTTP adapter
uses `--runtime-socket` and still has common-release delivery in this bounded step.
Public JSON frames are <=1 MiB, initial read <=5 s, operation <=30 s and total
<=35 s with absolute deadlines. SDK transport keeps its separate 16-slot pool.

Core validates the current route, package, active state and compatibility mode,
uses existing payload/audience admission, signs/sends once and commits, then
passes that connected Unix socket to Runtime. The connect/send budget is <=3 s;
Core never reads the handler response or retains a pending socket/transaction.
Unsupported scoped public/relational execution refuses before host metadata I/O.
Runtime waits/frames only; no key, authority cache or automatic retry is added.

A Core-signed `public-web-result-only` receipt binds the original request ID,
instance, artifact hash, authority epoch, route and current Core/Runtime
generations. Its only operation is result validation. Core finish checks its
expiry/signature/bindings, current state/key/package, original response signature
and request ID, schema and declared content/header/byte limits. A receipt cannot
start or replay a handler. Already admitted application effects are not undone by
revocation, Runtime loss or code rollback. Loss/late/invalid responses fail closed.

Matching initial Core policy/unit installation is required; older P4a/P4b Runtime
archives must be rebuilt. Compatible updates after that boundary stop only Runtime
and verify Core continuity. Local process/UID tests are recorded in the action
plan; installed-device/cgroup/ARM acceptance and event/domain extraction remain open.

## Durable event response worker, 2026-10-23 (P4d2)

Event-delivery feature **1** is negotiated over private ABI **2** and the same
expected Runtime UID. It is not an SDK action or execution grant. Core performs
matching/persistence, current source/subscription/grant/epoch admission and one
bounded send; Runtime owns the already-sent connection and reads the response.
Core's old event executor/retry task is removed. The worker starts only after
Runtime owns its SDK socket. A successful queue handshake establishes readiness
before optional application work completes; absent feature/schema is not ready.

One serial response worker, <=1 MiB frame, <=30 s selected operation and <=35 s
whole step. Durable claim lease **40 s** uses Linux boot ID/CLOCK_BOOTTIME; retries
wait **30 s**, at most **5 attempts**, including pre-dispatch failures. An opaque
result-only receipt points to Core-stored attempt/request/instance/package/
operation and kernel Runtime generation. Core verifies its ownership/deadline,
original app HMAC/request ID and admitted operation output. No DB/key/grant cache
is passed to Runtime. Completion/outcome/cursor accounting uses CAS exactly once;
a receipt never starts another invocation.

Lost Runtime/Core/FD handoff leaves an unconfirmed attempt. Expiry/reboot permits
a fresh currently authorized retry, with the original event ID as idempotency
key. There is no exactly-once application-effect promise or blind Runtime replay.
An already admitted successful operation may be accounted after disable/revocation;
that bookkeeping creates no new right. Changed epoch/reapproval cannot renew old
backlog. Key/response faults fail closed. FIFO persists per subscription, while
paused pending heads do not block eligible heads from other applications.

Admin `POST /api/v1/application-events/drain` remains admin-only and now returns
`status: queued`. It clears pending retry delay without executing code, resetting
attempts or stealing an active lease. Existing status backlog includes delivering.

Initial Core/schema/unit installation requires additive migration **1bf67d2435e6**
(four nullable delivery fields, preserved queue/history, no reset/backfilled rights).
Unresolved delivering rows refuse schema downgrade before DDL. Full artifacts
must include the migration and Runtime worker. Old Runtime archives are rebuilt;
subsequent compatible component updates remain independent. Local evidence does
not close installed-device/ARM/cgroup/power acceptance or remaining domain adapters.

## Connector network execution, 2026-10-23 (P4d3)

Connector execution feature **1** runs over private ABI **2**. Core and Runtime
readiness negotiate it; an older ABI-2 peer alone is insufficient. SDK action,
signatures and connector request IDs stay unchanged. The old synchronous Core
HTTP client is removed. Core keeps current declarations/binding/secret/grant
admission and commits a unique durable attempt before sending anything outward.

A distinct `3mm-connectors` process accepts only the actual Core UID (root may
probe readiness only). Core checks its kernel UID before sending the one selected
HTTP plan/credential and a per-attempt result-only HMAC key, using <=3 s total
Unix connect/send. The connected FD and opaque signed receipt go to Runtime.
Runtime waits and submits a separate short completion; it never receives the
credential, result key, DB or Core/app signing keys. Core validates the signed
receipt, stored attempt/instance/owner/deadline/limit and worker result signature,
then CAS records the outcome once. Completion can account an admitted effect
after revocation/disable; another dispatch still requires current authority.

The network service has **4 slots**, each using one disposable subprocess. An
absolute declared **1-30 s** deadline kills a child stuck in DNS, TLS, reads or
trickle traffic. TLS uses default certificate verification; no redirect, proxy
environment or automatic HTTP/SDK retry is added. The manifest response maximum
is now **4 MiB**, fitting the existing **6 MiB** signed SDK frame after base64.
Selected smaller limits still apply. Only Content-Type is returned, <=256 chars.
Runtime's full SDK request remains <=35 s and its network namespace stays closed.

The durable **40 s** lease uses Linux boot ID/CLOCK_BOOTTIME. Lost/late/invalid
results leave mutations **ambiguous**, reads **retryable**, without resending.
Expired attempts are reconciled on connector/status access; duplicate lookup also
settles its own expired attempt beyond the bounded 100-row status batch. Reusing
a connector request ID returns its recorded outcome and no body, never another
HTTP call. These are outcome receipts, not exactly-once remote effects.

Additive migration **2c078e3546f7** adds nullable JSON dispatch metadata, with no
request bodies/headers/target credentials and no reset/backfilled permission.
An unresolved new dispatch prevents downgrade before DDL. A rebound connector
cannot receive the previous binding's late telemetry.

The small stdlib artifact includes both process roles. Each pins its own
`current`/`previous` under `/opt/3mm-platform-runtime` or
`/opt/3mm-connector-worker`, with separate venv, service and update journal.
`python -m deployment.platform_runtime_component --component connector-worker
update --artifact <tar> --sha256 <sha>` updates only the network service;
`rollback` uses the same selector. Its unit has outbound IP access and no Core
state/environment; SDK Runtime remains AF_UNIX/PrivateNetwork-only. Initial
Core/schema/unit/component activation must be coordinated; an old incompatible
set fails readiness. This local package does not perform that installed rollout.

## Admin operational-status response relay, 2026-10-23 (P4d4)

`GET /api/v1/application-extensions/{module_id}/operational-status` keeps its
admin-only policy and existing data fields. It now awaits Runtime asynchronously;
it does not retain a Core thread or DB transaction while the application replies.
Core still selects/validates the current package, signs the single reserved host
`three_mm.platform.status` query and validates the original response HMAC/request.
The old direct synchronous ApplicationServiceClient path in this endpoint is removed.
P4d5 routes declared admin health through this relay; P4d6/P4d7 also route
human/kiosk operations and peer callbacks through the same eight response slots.

The response-only Unix listener `/run/3mm-application-responses/runtime.sock`
uses **application_response_contract 1**, negotiated in enabled Runtime readiness
on private ABI **2**. It accepts only the actual Core OS UID before reading
metadata/FDs. Core checks the expected Runtime UID before reserving. Eight slots
are separate from SDK/public/event capacity. A slot must be reserved before any
application send; overload/absence cannot dispatch an unobserved extra query.
Core has <=1 s reservation and <=2 s remaining handoff budget. Runtime accepts one
already-connected Unix FD, half-closed for writing by Core before transfer,
and reads one <=1 MiB frame with an absolute selected
1-30 s deadline; this status path uses **5 s**, Core relay receive <=6 s. Trickle
traffic cannot renew the budget. No replay, key, DB, grant or original signed
invocation is forwarded to Runtime; it only reads the supplied connection.

Core's short admission commits before app connect/send. Completion freshly checks
instance/incarnation/epoch/package/lifecycle/current key and original response
signature/request ID. A changed or unverifiable result is not disclosed. Revision
and bounded numeric outbox counts are observations, not authority or permission.
`runtime_observation.status` is `available`, `unavailable` or `inactive`, with
`outbox_inspected`; unknown/relational-uninspected queues are not reported as
observed empty queues. Missing/failed Runtime returns available Core metadata
with unknown runtime revision and no observed outbox. Disabled applications are
not probed. A new explicit admin read may make a new read-only query; loss never
causes an automatic resend of an existing one.

The stdlib Runtime artifact includes `responses.py`. The existing isolated unit
adds its protected setgid Core-group socket directory without adding Runtime to
Core's group. It stays AF_UNIX/PrivateNetwork-only, with TasksMax 48/NOFILE 192 for
the extra eight readers. Production health requires the configured listener and
feature; compatible updates/rollback stop only Runtime. Initial Core/unit/artifact
activation must be coordinated. No schema, SDK action, permission or installed
account/service/network change is performed by this local package.

## Admin declared health through the response relay, 2026-10-23 (P4d5)

`POST /api/v1/application-extensions/{module_id}/health` keeps its actual-admin
policy and returns the declared health result object on success. Core selects
only `service.health_operation_id`, a manifest-validated internal query, with
empty payload and no idempotency key. Shared package/audience/key/native UI trust
admission remains in Core and is refreshed after reserving Runtime capacity.

It uses **application_response_contract 1**, private ABI **2** and the same eight
slots as operational-status. No additional SDK operation, permission, worker or
schema exists. Core commits admission before bounded Unix connect/send/handoff;
Runtime only receives the connected write-half-closed FD and reads one <=1 MiB
original app response. The health operation's declared **1–30 s absolute** timeout
is selected; Core awaits IPC asynchronously for at most that budget +1 s. No Core
thread or DB transaction is retained during response wait.

Core freshly verifies lifecycle/authority incarnation and epoch/mode/package/
version/socket/current key and native UI trust, then original HMAC/request/time,
result object and declared schema. `health_checked_at` is committed with a
conditional current-state/package fence. A stale, lost, malformed or unavailable
result returns **409** and does not write a successful health timestamp. Full or
missing Runtime refuses before app dispatch. There is no retry or direct fallback;
a later explicit admin request can perform a fresh readiness query.

Relational health acquires **no** relational invocation ticket, host-metadata IPC,
business DB read or outbox permission. The host explicitly rejects SQL authority
on health. Resource revoke can leave a fresh readiness query available while
resource effects stay denied; an in-flight result from a changed epoch is rejected.
Independent Runtime kill/update/rollback preserves Core and never resends a health
query. P4d4's exact Runtime artifact is reused; P4d5 changes only Core's health
path and full-release required-file contract, plus tests and documentation.

## Operation/callback relay and independent services, 2026-10-23 (P4 completion)

Current administrator/public/operator/kiosk operation HTTP routes preserve result
shape, operation policy, UI binding, idempotency and outcome rules. Peer bootstrap/
report callbacks preserve nonce/consent/owner/generation/receipt rules. One Core
prepare/finish gateway surrounds an asynchronous response-only Runtime wait;
these HTTP paths have no direct synchronous handler-response fallback or retry.

Core refreshes human token/session/role/permissions, kiosk terminal, UI trust and
peer pending/live state before dispatch and before disclosure. It reserves before
send, rechecks after reservation/relational metadata, commits before app I/O,
signs/sends once and transfers a write-half-closed connected FD. Runtime only reads
the original signed frame; it gets no key, DB, dispatch request or authority.
Existing eight shared slots, <=1 MiB frame and absolute declared 1–30 s response
budget remain. Core verifies HMAC/request/time/schema and current state behind a
conditional completion fence. A post-dispatch policy refusal is **409/unconfirmed**;
it cannot prove that effects did not happen and must not cause automatic replay.
No Core thread/DB transaction spans handler-response waiting. Relational metadata
remains Core admission with one absolute **2 s** connect/send/read deadline and
no DB/key lease. Health still gets no relational ticket. No SDK/schema/ABI changes.

Agent/public HTTP/session-worker artifacts have their own code/vendor/venv and
current/previous under `/opt/3mm-{agent,public-web,session-worker}`, with journals
at `/var/lib/3mm-<role>-updates`. Shared stdlib transactions validate closed role,
source/vendor digests, exact native target and contracts before switching. Service
contract set 1: Agent device contract 1, public-web contract 1, session profile
`isolated_session_v1`. Unknown combinations and boolean/float aliases refuse.

Update/rollback requires an active component and the common release mutation lock;
it only controls that role, preserves Core PID/generation/source and never enables
an inactive service or replays effects. Journal recovery is explicit, without an
automatic boot-reconciliation claim. Recovery resets only that role's systemd
failure counter. First Core/unit/artifact installation is coordinated; compatible
bootstrap keeps existing pins and refuses unresolved journals.

Agent has a filtered own environment and keeps the trusted `3mm` OS principal;
this is not hostile-code Agent isolation. `/component-health` and public adapter's
reserved `/__3mm_component__/health` return only component/build/PID; the updater
checks MainPID under an absolute probe deadline. The reserved public path belongs
to infrastructure. Public adapter has no Core Requires/PartOf. Session keeps its
Core lifecycle, DynamicUser/cgroup/namespace/no-network/private-peer restrictions;
readiness checks listener/artifact, while provider execution is separately admitted.

Native host/services target Linux x86_64/CPython 3.14; other targets require native
builds/acceptance. Runtime/connector executable is unchanged from P4d4, host changes
its private metadata deadline. Core authority/domain/control-plane, outbound peer
HTTPS and existing M21 broker remain Core. Local P4 completion does not imply full
CI, installed rollout, ARM/ARMv6 resource, clean-image/reboot/power, P2 Wi-Fi/AP or
P5 debug acceptance. [Exact builds/admin commands](CORE_STABILIZATION_ACTION_PLAN.md).

## Independent application-host component, 2026-10-23 (P4c)

Host-contract **1** and private authority ABI **2** are separate from application
manifest v2/SDK 1.3. Existing application wheels and Core authority adapters are
unchanged. Host code/SDK/protocol models plus eight locked native dependency
packages are delivered in a content-addressed native artifact with its own venv;
no Core imports/site-packages/provisioning runtime or Core environment fallback.
Root candidate self-check runs as the application user and loads native crypto/CFFI.

Releases live under `/opt/3mm-application-hosts/releases/<build-id>`; each instance
has `instances/<24-hex-id>/current` and `previous`. Compatible default bootstrap
preserves existing pins. All generic enable/start/restart paths bind/validate the
host first, including prepared/relational starts. Existing wheel, schema,
configuration, grant and active metadata are not changed by host update. Host
units no longer depend on the Core release path or Core PartOf/Requires; their
existing shared `3mm-app` principal remains a reviewed-native trust boundary.

The signed internal `three_mm.host.info` RPC takes empty payload/exact internal
audience and returns host build/contract, kernel PID/UID, instance and active
metadata hash. It creates no permission. The root updater verifies SO_PEERCRED
on the same connection, HMAC and the expected build/metadata; metadata frames are
at most 16 KiB with a two-second absolute deadline. Application health response
keeps the one-MiB ceiling and the same absolute deadline. Peer progress cannot
extend either wait. General operation authority and receipts remain current.

Per-instance update/rollback only controls that already active unit and
checks unchanged Core/Platform Runtime process/build plus active metadata. It
cannot enable an inactive application. Failed candidates revert host code;
interruption journals reconcile on explicit `recover`/next update. Host rollback
does not undo application effects/data or replay invocations. Existing reviewed
application lifecycle governs wheel/schema/authority changes and ordinary restart
factory/health effects. No automatically installed boot-journal recovery is claimed.

Archives bind exact source/vendor hashes, platform/Python target and contracts;
wrong targets/ABIs/paths/links/duplicate files or altered native payloads refuse
before pointer/service switching. A candidate's isolated native self-check must
also pass. The delivered local artifact targets Linux x86_64/CPython 3.14; other
architectures/Python versions require native builds and their own acceptance.
No full installer/device/boot/cgroup or hostile multi-tenant isolation is implied.
[Build/admin commands and evidence](CORE_STABILIZATION_ACTION_PLAN.md).

## Optional operation diagnostics (P5, 2026-10-24)

Diagnostics is an administrator-controlled observation contract, separate from
SDK actions, Core private ABI 2, host contract 1 and all resource grants. Current
records add explicit operation/instance metadata and session scope to schema 1;
current-format exports are validated as a closed format. SDK 1.3 clients without
an explicitly supplied recorder keep their normal behavior and signed wire bytes.
Detailed recording starts inactive and remains bounded by TTL/bytes/rate/drop rules.

All current signed SDK actions can produce matching SDK/Core hop records; human/
callback relay admission/dispatch/response is also observed. Only fixed safe labels,
validated IDs/version and timings enter records. No payload, token, path, arbitrary
log/exception text or terminal data is accepted. Debug never grants current authority,
changes consent/leases, enables a service or retries an operation.

The Settings workspace can merge one bounded current producer NDJSON snapshot with
Core records, label provenance/missing data/drop counters/truncation and export that
view. Imported observations are not cryptographically authenticated live state or
execution authority. Wall clocks may differ; IDs correlate one hop. Other processes
are explicitly opted in; missing Runtime/Agent/session exports remain absent.
Collection/import/probes have bounded non-queued work and no auth DB lease across
I/O. The offline command imports no backend/SQLAlchemy and controls no services.
[Current API, operator/dev commands and budgets](DIAGNOSTICS.md).

## One source of truth

Public entry point: `three_mm_protocol.extension_schemas.extension_schema_catalog()`.
It exports JSON Schema Draft 2020-12, in **validation** mode, directly from the
existing Pydantic models. There are no duplicated manifest definitions, new
package formats, Core imports, publisher assumptions or SDK version changes.

Developer command (from a checkout with the existing Python dependencies):

```text
python -m three_mm_protocol.extension_schemas
```

The command emits one JSON document to stdout; it does not inspect/import package
payloads, download, build, install or write generated source files. Consumers may
save the stdout themselves. Nothing is automatically added to a package/release.

`catalog_version: 1` versions this export format, **not** Core, the manifest,
SDK or a distribution envelope. `contracts` maps stable contract IDs to:

- `document`: package-root filename (candidate only for contract-only entries);
- `version_field` and `contract_version`, derived from the model's literal;
- `source_model`: authoritative public Python model;
- `schema`: standalone JSON Schema with a URN `$id` and local `$defs` references.
- `runtime_support: contract_only`, when present: declaration/authoring model
  only, not a currently accepted ZIP activation or runtime transport feature.
- `runtime_support: reviewed_native_scoped`: accepted optional application ZIP
  declaration plus signed runtime publication; exact installed-artifact native
  review and applied local resource grants remain mandatory. Not a sandbox.
- `declaration_support`, when present: support for an optional nested authoring
  declaration. `runtime_authority: reviewed_native_scoped_local` indicates bounded
  installed headless execution with exact applied grants. `core_admin_review_api`
  exposes those exact resources in the existing admin review dialog; native code
  trust remains `local_core_only`. Its narrower runtime bound is explicit; this is
  not feature negotiation, general installer support or hostile-code isolation.

Each schema can be extracted and used independently. URNs are identifiers, not
network locations or publisher identities; no network resolution is needed.
Repeated exports from the same models/dependencies are deterministic, with no
timestamps or host paths. Each call returns independent dictionaries. Consumers
must reject unsupported catalog/contract versions rather than guess a format.

## Existing contracts and compatibility matrix

Every supported module-v2 ZIP retains `manifest.json` / ModuleManifestV2.
The descriptor does not replace that envelope or the whole-package validator.

| Package / contract ID | Descriptor | Current runtime / remaining checks |
| --- | --- | --- |
| Agent module / `module-manifest.v2` | Manifest v2; no new Agent descriptor | Agent runtime; architecture, Agent version, permissions and lifecycle remain enforced by the existing Agent |
| Application / `application-extension.v1` | `application-extension.json`, version 1 | Supervised service; SDK 1.0–1.3 remains supported; optional UI also requires compiled-ui v1 and matching access policies |
| Application publication / `application-event-publications.v1` | Optional `application-event-publications.json`, version 1 | Installed reviewed-native publication through SDK 1.3's additive signed call and exact applied grants; no inferred device identity or cross-application consumer access |
| Declarative runtime UI / `runtime-extension.v1` | `runtime-extension.json`, version 1 | UI runtime only; existing entity/reference/action/permission rules still apply |
| Compiled UI / `compiled-ui.v1` | `compiled-ui.json`, version 1 | Existing source/build/host contract; reviewed native integration, not an untrusted frontend sandbox |
| Theme / `theme-extension.v1` | `theme-extension.json`, version 1; design API 1 | Declarative, UI-only; existing token/manifest restrictions |
| Theme / `theme-extension.v2` | `theme-extension.json`, version 2; design API 2 | Declarative, UI-only; existing design, contrast, customization and asset validators |
| Language / `language-extension.v1` | `language-extension.json` in manifest v2; not yet part of this schema catalog | Generic data-only lifecycle; Bulgarian is a separate package, English is the recovery base |
| Legacy backend Python | Retired in P3b | No in-Core loader or legacy lifecycle endpoints |

This is a structural-contract matrix, not a claim that any particular hardware,
installed version, package or role can install/activate every type. It is common
to Standalone and Hub/Fleet consumers; schema export requires neither running.
Device capabilities remain provider-neutral and separate from runtime features.

## Mandatory validation boundary

The catalog explicitly declares `validation_scope: structural_only` and
`requires_authoritative_validation: true`. JSON Schema does **not** encode every
Python model validator or ZIP/host policy. Examples:

- safe artifact/source paths, unique IDs and cross-entry references;
- operation/audience/grant semantics and SDK feature gates;
- descriptor identity, configuration/permission/capability agreement with manifest;
- theme v2 `design` is structurally an object: its closed keys, ranges and contrast
  remain enforced by the authoritative theme validator, not this exported shape;
- ZIP bounds, traversal, symlinks, asset bytes/digests, files and build availability;
- target architecture, running versions/features, dependency resolution and rights.

Therefore authoring tools/generators use these schemas for structural guidance,
then the existing Python models and read-only ZIP inspection for authoritative
checks within their documented scope. Upload/activation must still revalidate.
Schema validity is never a publisher signature, a dependency plan, permission
approval, installation guarantee or isolation proof. No new remote validation
service, install bypass or Core endpoint is introduced.

## Evidence and next boundary

The original focused tests compare all six existing exports to their authoritative models, resolve all
local refs, check deterministic independent outputs, real CLI JSON output,
SDK 1.3 compatibility and explicit semantic limitations. A subprocess blocks
Core/Agent/runtime/SDK imports to verify this remains a shared-protocol tool.
Existing descriptor and ZIP inspection tests remain the regression baseline.

This step: **71 focused tests passed** (10 new schema-export checks and 61 existing
descriptor/package/SDK checks; 6 warnings). Frontend production build also passed;
there are no visual changes in this step. Full release suite and live-device
acceptance were not repeated, and no dependency was added.

Remaining WP1: publisher namespace/key ownership and general target/dependency
compatibility planning. WP4 scoped grants and WP5 proven execution isolation
remain separate gates; this catalog does not authorize their implementation.

2026-10-09 additive publication delivery: seven contracts are exported. The first
slice was contract-only; the subsequent package/broker/authority/SDK integration
marks it `reviewed_native_scoped`. The six existing models, supported SDK versions
and catalog version are unchanged. Schema validity still grants no rights,
publisher trust, executable isolation or automatic installation. See the
[approved publication scope and evidence](EXTENSION_PLATFORM_V2_EVENT_PUBLICATION.md).

2026-10-09 bounded file-request follow-up: application descriptor v1 optionally
accepts `storage.private_files` contract v1 with explicit read/read-write mode and
bounded file/count limits, requiring SDK 1.3. It selects one installation-owned
logical namespace, never a host path. Existing undeclared SDK 1.0–1.3 packages
remain valid; no manifest/SDK/catalog version or contract count is changed.
JSON Schema describes its structure; coherent limits and SDK gating also require
the authoritative validator. The initial slice marked storage authority **not
implemented**. The subsequent bounded execution supports installed reviewed-native
local grants through the existing manager, signed SDK gateway and target-owned
worker. The catalog marks `reviewed_native_scoped_local` with
`authority_administration: core_admin_review_api`, local-only native attestation
and `runtime_max_file_bytes: 1048576`; larger requests remain unsupported, not
silently clamped. The existing admin HTTP review/dialog now exposes exact file
read/write resources, owner/package pins and limits with separate approve/apply.
It refuses incomplete or foreign bindings, not silently hiding rights. Inspection
never infers a grant, even for unchanged declarations. See
[file execution, evidence and remaining gates](EXTENSION_PLATFORM_V2_PRIVATE_FILES.md).

## Public application frontend host v1 (2026-10-17)

Compiled **application routes** can import `useApplicationHost`,
`ApplicationHostError` and the public TypeScript types from
`@3mm/application-ui/v1`. The build emits a versioned import-map entry. The
install-time compiler allows this exact import, not its private subpaths.
Existing `@3mm/ui/v1` presentation exports and SDK 1.0–1.3 are unchanged.

```typescript
import { useApplicationHost } from '@3mm/application-ui/v1'
const host = useApplicationHost() // during the route component's setup
const access = await host.getInfo()
const record = await host.invoke('get_record', { record_id: selectedId })
// Commands require the caller's stable key for this exact logical request:
const result = await host.invoke('register', { label }, { idempotencyKey: requestId })
```

The only host methods are `getInfo()` and `invoke(operationId, payload, options)`.
No caller-selected module, audience, URL, headers, token, HTTP client, router or
Core store is exposed. The dynamic route loader binds module, package SHA-256,
version, entrypoint and audience from the existing server catalog. Non-application
widgets/editors and components mounted outside that boundary get no host.

`getInfo()` makes a fresh, no-store request to
`/api/v1/application-extensions/{module_id}/ui-host/{entrypoint_id}` with the
bound `artifact_sha256`. Its closed public projection includes `host_version: 1`,
the matching binding, and permitted query/command IDs with their idempotency
requirements. Internal jobs and other audiences are not offered. The feature
flags are `operations: true`, `resource_authority: "separate"` and
`browser_isolation: false`: human operation access is **not** a resource grant.
Resource authority remains enforced by the existing service/platform adapters.
The original delivery did not lift the headless-only limitation. The separate
reviewed UI profile below now binds executable output before admitting it.

Each invocation rechecks this information and sends exactly one POST through the
existing audience-specific operation route. Its additive `ui_context` has the
exact host version, entrypoint and artifact hash. Core revalidates the installed
ZIP, active state, route/audience and current user permissions or kiosk terminal;
the existing operation and payload checks still apply. Legacy callers without
`ui_context` keep their existing API behavior. There is no browser-selected actor
or upgrade from kiosk/operator to administrator. Public calls send no bearer;
kiosk calls use only the kiosk session, even if a human is logged in too.

Host v1 accepts JSON object payloads up to 512 KiB UTF-8, 10,000 values and depth
32, and access descriptions up to 256 operation entries. Cycles, non-JSON values,
path-like operation IDs and invalid command/query keys fail before dispatch.
Unknown/unavailable host versions do not fall back to a generic HTTP client.
The Core origin is pinned for the mounted host lifetime. Unmount aborts pending
transport and invalidates retained handles; cancellation does not prove rollback.

Errors expose only `ApplicationHostError.code`: `invalid_request`,
`access_denied`, `unavailable`, `unconfirmed` or `disposed`, never raw HTTP errors,
request headers or backend responses. Failed POSTs have **no automatic retry,
token-refresh replay, fallback audience or inferred rollback**. On an unconfirmed
mutation, retain its original key/payload for the application's explicit outcome
review; do not generate a new key and resubmit. The neutral reference's kiosk
screen stops further submission and displays that key for review.

This is a public API for reviewed same-origin code, **not a security sandbox**.
It does not prevent such code from accessing browser globals directly. WP5's
untrusted browser/OS isolation and the broader WP4 owner/layout acceptance remain
separate gates. Current evidence and queue: [WP4 closeout](EXTENSION_PLATFORM_V2_WP4_CLOSEOUT.md).

## Administrator application access (2026-10-25)

The normal application access flow now uses authenticated administrator approval
of the exact installed package and emitted UI build. It does not require a manual
source-code audit or a review document. The older manual-review CLI below remains
an optional, distinct attestation path; it is no longer a normal user prerequisite.
Neither approval type claims publisher provenance or an OS/browser sandbox.

Fresh Core application installations explicitly use `review_required`, with no
implicit compatibility resource access. Uploading or starting a service does not
grant its SDK resource scopes. After initial activation, Extensions opens
Application access when no current saved consent exists. First-use choices default
to all declared resources and the current administrator's declared application
permissions; Details exposes the actual devices, destinations, data profiles and
limits. Saved subsets are loaded on subsequent visits. The relational read/write
profile remains an atomic pair and can be selected together or omitted together.

`POST /api/v1/application-extensions/{module_id}/authority/consent/preview`
requires a current tracked administrator login. It may provision a missing first
Core-owned sealing key, with an infrastructure audit, and persists a bounded
preview. It creates no native trust or resource grant. Existing corrupt, foreign
or recovery-stale key material is never silently replaced. GET status remains
read-only, and the key is never exported to the browser/application.

`POST .../authority/consent/allow` accepts the exact preview ID, revision,
fingerprint, selected resource scopes, selected current-user permission IDs and
explicit native-code consent. In one key/authority transaction it rechecks the
current actor/session, boot/expiry, Core guard, package/build, configuration,
resources and human grants, then records `administrator_approved` native consent
and applies the selected grants. Native evidence uses
`administrator_approved_artifact` / `administrator_approved_native`, with profile
`supervised_administrator_approved_native_v1` or its `_ui_v1` counterpart. It never
fabricates a completed manual audit. Existing typed resource review/unsupported
feature/whole-profile checks continue to apply. No other user's grants or roles
are assigned. Preview/result distinguish saved choice from current runtime
availability. Uncertain operations are not automatically replayed.

Confirmed disable/enable of the same exact code/build/configuration/resources
preserves human consent and its numeric approval revision. Each transition still
rotates execution epochs, invalidates old commands/sessions/tickets and reseals
only the current execution binding. Revocation, changed resources/code/identity,
uninstall/reinstall, missing key or an unconfirmed lifecycle cannot silently
resume old authority. Stopping remains available when permission metadata is
broken. These changes add no SDK/manifest version or database schema.

## Execution-profile coverage (2026-10-17)

The application entry now includes additive `execution_profiles` describing
compatibility, installed reviewed-native scoped authority and the public frontend
host. These are authoring facts, **not** live negotiation, an approval or a claim
that arbitrary combinations work. The original scoped profile remains headless;
the separate reviewed UI profile below additionally requires exact build evidence.

Identity possession proofs, peer mutations/receiver/unfiltered listing, scheduled
jobs and public HTTP handlers have no scoped grant adapter. They are explicitly
listed as unsupported, not inferred from the descriptor's structural validity.
The signed gateway refuses proof/peer actions before private-key or network
access. Jobs are excluded from scoped discovery, refused at claim and rechecked
before dispatch; the shared invocation gateway also refuses direct job/public
HTTP handler calls outside compatibility. Public HTTP keeps route ownership but
returns unavailable without invoking unsupported code or disabling unrelated
compatibility applications. Unknown/expired job claims remain quarantined,
including across a later compatibility restart; a mode refusal proves no rollback.

Existing SDK compatibility behavior remains subject to its existing declaration,
audience and consent checks. Exact event publications can supply their declared
event types; arbitrary capability `provides` are not scoped registration authority.
Relational/peer combinations are still unsupported. Missing features never
select compatibility as a fallback for an already opted-in installation.

The stale relational catalog entry has been corrected to
`reviewed_native_scoped_prepared`: exact local review/grants plus protected
preparation and explicit local-admin/helper activation are required. Generic
activation remains blocked, and `cooperative_v1` is not an OS resource quota.
No descriptor, SDK version, contract count or publisher/permission policy changed.

## Reviewed UI with scoped service resources (2026-10-18)

`supervised_reviewed_native_ui_v1` reuses the installed manager, sealed native
review, exact resource scopes and `AuthorityArtifact.built_ui_sha256`. No new
subject version, database model, SDK version, publisher trust or sandbox exists.
Human/kiosk route and operation access is independent of service resource grants.

New install-time builds record a Core-owned `build-provenance.json`: source ZIP
SHA-256, compiler script SHA-256, Node/Vite/Vue-plugin versions and a complete
output inventory (including chunks, CSS, descriptors and entrypoint index).
The bounded reader checks ownership/protection, regular paths, hashes and sizes;
the canonical record has a domain-separated SHA-256. This is local build
provenance, not a publisher signature or proof of reproducible/untrusted builds.
Validation happens outside the authority key/DB guard. Published output remains
immutable; replacing it requires new explicit trust and resource review.

Local Core administration, using the normal service account/environment:

```text
python -m backend.services.application_authority_admin inspect-ui-build --installation-id <id>
python -m backend.services.application_authority_admin native-review --installation-id <id> --artifact-sha256 <source-sha> --built-ui-sha256 <build-sha> --review-document <review.md> --code-review-completed --accept-native-host-risk --accept-same-origin-ui-risk
```

Tokens are still prompted hidden, not passed on the command line. The reviewer
must review the exact source AND emitted executable output/toolchain, and
explicitly accept same-origin browser code risk as well as native host risk.
Inspection/manual review never starts a service or approves permissions. The
current administrator flow above combines consent and apply in one action;
confirmed same-artifact stop/start retains consent with fresh execution bindings.
The native review seals the build pin and UI-risk acknowledgment; headless calls
and historical request hashes keep their previous behavior.

The catalog carries optional `built_ui_sha256`; new assets use
`.../<source-sha>/build/<build-sha>/assets/...`. Host info and `ui_context` carry
that exact optional pin. A missing/changed pin cannot dispatch a reviewed UI
request. The server checks current native UI trust for catalog/assets and the
shared service gateway, including raw legacy operation callers. Verified asset
bytes are read before constructing the response, not opened lazily afterwards.
Removing service rights blocks resource effects but does not revoke native code
trust or supply missing human rights; revoking native trust also blocks new UI
catalog/asset/service admission. Already-loaded browser code cannot be recalled
or sandboxed by a grant change; operation/effect checks remain current.

Old cached outputs with no build evidence are **compatibility-only**. Loading
them does not rebuild, promote or fabricate provenance. Use a new package version
through the normal install/review flow to produce a reviewed build. A valid new
compiler build alone is still neither native trust nor a resource grant.
Jobs, public HTTP handlers, proof/peer mutations and other explicitly unsupported
families remain refused. This delivery proves a neutral UI→signed service→signed
SDK command path; it does not claim every resource/layout combination has live
owner acceptance. See the current [closeout checklist](EXTENSION_PLATFORM_V2_WP4_CLOSEOUT.md).
