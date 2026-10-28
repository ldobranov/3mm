# M20 — public extension schema catalog, first WP1 contract slice

Date: 2026-10-08. Local implementation; no deployment or release. This follows
the accepted read-only Package Inspection slice. It does not complete WP1/WP4
or enable remote/untrusted execution.

C3 declarative CRUD extraction (local, 2026-10-26): the old Core CRUD API, ORM,
renderer and `runtime-extension.v1` export are retired. The optional shared CRUD
library is bundled by ordinary applications with own scoped relational storage
and compiled UI. `storage.retention_policy: until_explicit_erasure` is an inert
personal-data retention choice, mutually exclusive with a retention handler;
administrator export/erasure operations remain required. It issues no grant,
timer or task, and does not broaden the CAP08 task+storage execution profile.
Historical data remains in explicit recovery archives; no old authority is
automatically transferred. See [shared CRUD](../libraries/three_mm_crud/README.md).

## Adapter providers and unavailable optional resources (CAP01/CAP07, 2026-10-28)

The Core administrator UI at **Devices -> Capabilities** completes the explicit
owner step: inspect each reported provider, select current offers, save selection,
or enable/disable the provider using its current revision. Selected capabilities,
enabled state and current readiness are shown separately. Installation-managed
and inventory-only sources remain descriptive. A retained choice that is no
longer offered must be explicitly cleared before saving another selection.
Conflicts or an unconfirmed write require a fresh read; writes are not replayed.
This screen grants no application access: refresh the application's consent and
explicitly approve the newly resolvable scopes afterward. It is generic device
administration and has no application/provider-name branch.

Implemented locally; device rollout is separate. Agent adapters share
`agent.capability_providers.ProviderAdapter`: `provider_declaration()` returns a
bounded `AdapterProvider`, and `provider_health()` returns current
`CapabilityHealthV1` observations for exactly its declared capabilities.
`AgentProviderRegistry` is injected into `CorePublisher`; the normal Agent factory
includes the enabled identifier mock. Inventory names remain observations, never
effective registration or permission evidence.

The registry uses the existing authenticated provider GET/PUT v2 and ephemeral
availability reports. The optional logical port is `DeviceProviderTransport`;
`HttpDeviceTransport.provider()` and `report_provider()` validate response device
and provider identities. No device-management URL or credential is exposed to an
application. Another adapter supplies declarations/health through the same port;
Core needs no condition for its vendor, module, reader ID or consuming application.
This does not add new execution privileges, schema dialects or hardware drivers.

Onboarding is **offer -> explicit capability selection -> fresh application
consent -> fresh event -> admitted native handler**. New v2 offers start with no
selected capabilities. Synchronization preserves Core-owned enabled/selection
state, uses current revisions, and reconciles a lost acknowledgement by reading
the current provider. A bounded device-bound `adapter-providers.json` remembers
only adapter ownership/declarations before reporting; after a restart, removed
adapters withdraw their capabilities without adopting or withdrawing unrelated
providers. Health is never replayed through an outbox. One adapter health/report
failure does not starve the remaining providers or terminate the Agent heartbeat
loop; invalid declarations/journals fail closed without automatic repair.

For events, source resolution now uses the existing capability availability
policy in addition to selected provider/control identity. C14/v2 sources require
current health and online evidence. Disabled/unselected, stale, unhealthy,
revoked, withdrawn or conflicting sources cannot acquire or reuse event access.
Existing stricter event validation, operation schemas, grants and delivery
receipts remain authoritative. No historical scan is backfilled by onboarding
or consent; retry/dedup retains the original event identity.

The current administrator consent preview adds required redacted metadata:

```typescript
unavailable_resources: Array<{ scope: string; reason: string }>
```

Only declared optional scopes omitted from `scopes` may appear, once each, up to
16. This is diagnostic information, never selectable authority. Source reasons
include configuration/device/runtime failure, `capability_unresolved` (missing,
disabled, unselected or conflicting provider), `capability_unavailable` (current
availability refusal), connector failure and command-contract/schema mismatch.
The Core frontend validates the coordinated DTO and shows the explanation
outside the collapsed permission details, with EN fallback/BG source labels.
Required failures still block the existing profile. Unresolved optional bindings
do not invalidate unrelated required work or silently grant newly appearing
resources. Existing selections and current human permission choices retain their
normal consent rules.

Conformance uses actual Agent factory wiring, authenticated provider/configuration
and event HTTP routes, sealed explicit consent, a signed native process and the
public own-SQLite SDK. Two unrelated adapter/consumer pairs use the same Core
paths; duplicate subscriptions produce one SDK receipt for the original event.
The second adapter is a test implementation, not a shipped sensor driver.
Core and the independently delivered Agent must both be updated for this path;
unchanged compatible application ZIPs do not need rebuilding. No manifest,
device protocol or application SDK version change is introduced by this slice.

## Current Core–Runtime transport boundary, 2026-10-23 (P3c/P4b)

The CAP08 addition is documented in [Scoped tasks, intervals and calendars](APPLICATION_TASKS.md):
dedicated `tasks`/`kind: task`, exact sealed `task:<id>` consent and an optional
separate worker. The first one-shot profile is owner-tested on VM; the completed
bounded interval/IANA calendar and task-bound command profile is deployed with
SDK/VM acceptance, retained-data upgrade and restart/revocation checks.
It does not enable the retired job/schedule contract. Host support uses the separate
`three_mm.task.info` contract; existing `three_mm.host.info` metadata is unchanged.

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

## Core-owned connector settings, 2026-10-27

The current administrator opens the gear on an application card in `/extensions`.
Core derives its availability from the validated artifact's `connectors`, exposed
as `has_connector_settings` in its protected package catalog. Packages without
connector declarations have no connector settings entry. An uploaded new package
can be configured before installation/consent; another version of an existing
installation must first follow its existing stopped candidate/preparation flow.
The gear never changes the selected immutable artifact by itself.

Applications declare ordinary manifest v2 configuration fields and connectors:

```json
{
  "connector_id": "service_api",
  "destination_config_key": "API_URL",
  "allowed_schemes": ["https"],
  "path_prefix": "/api/",
  "authentication": "basic",
  "credential_ref_config_key": "API_CREDENTIAL"
}
```

The manifest's configuration schema declares `API_URL` as a string and
`API_CREDENTIAL` as a string with `"x-3mm-secret-reference": true`. Credentials
belong in neither ZIP defaults nor application SQLite. The Core form supports
Basic username/password, Bearer token, API key with its safe X-* header, and
unauthenticated connectors, based only on the declaration. It offers only
compatible, non-revoked credentials of this installation. Rotation/revocation
requires explicit confirmation and shows all affected same-installation bindings.
No plaintext/ciphertext/username/token is returned in inspect or outcome metadata.

Save persists only the declaration-owned origin/reference configuration keys,
the binding, an optional new encrypted credential and a sealed request receipt in
one guarded transaction. Other configuration is preserved. Cancel performs no
write. Invalid origin, credential/schema/key or stale snapshot rolls back the
whole operation, including first registration and any new credential. Encryption
uses the existing installer-provisioned Core key; absence refuses credential
writes and is shown in the dialog. Error bodies are fixed codes and never echo
the credential-bearing validation input. The Core-private request body is bounded
at 48 KiB; existing configuration keeps its 32 KiB budget.

The CAS snapshot binds the exact artifact, Core recovery generation, installation
incarnation/mode/epoch/configuration and binding/credential identities/revisions.
Reads and writes verify a real current administrator session; writes recheck it
again before commit. Configuration, rotation and revocation withdraw application
authority. A running application must be switched off, its access reviewed and
then activated again with the new settings. A stopped unreviewed installation can
complete setup before native consent; a running compatibility installation must
first be stopped. No old grant is restored or namespace reset. Already admitted
external operations are not undone by a configuration change.

A first successful setup creates an inert `disabled` / `review_required`
installation, without loading its wheel, starting a host, creating its SQLite
namespace or approving any permission. Multiple connectors can be configured in
separate explicit saves; missing required configuration still blocks consent.
Original inert registration/adoption records remain immutable. Configuration-only
transitions are separately sealed against their exact original record/revision;
all nonconfiguration provenance still must match. Own-SQLite preparation,
migrations, recovery and activation retain their existing protected lifecycle.

Request IDs are 32 lowercase hex characters. The existing sealed Action journal
records redacted applied receipts, scoped to artifact, installation incarnation,
administrator and login session. A valid token refresh within the same login can
recover a receipt; another account/login/incarnation cannot. Repeating an admitted
ID returns its original historical outcome, without another secret or rotation;
changing its target/snapshot/nonsecret input conflicts. Neither credential values
nor their digests form the request identity or stored receipt. Applied means
configured at that point, not currently granted, reachable or commercially enabled.

The Core adapter uses no automatic HTTP refresh/retry/replay. It saves only the
pending request ID and any definite Core rejection code in session storage, before
dispatch/lookup, never the form or credentials. After lost/malformed responses,
reopening the dialog looks up that original request. A bare HTTP conflict is not
proof of rollback. Only a definite pre-dispatch refusal or recognised Core rejection,
followed by successful outcome lookup, can release an attempt for a new explicit edit; a genuinely unknown result
stays pending. Receipt lookup survives a Core process restart.

The form inherits Core tokens/variants and initial/live language with English
fallback. It is rendered by Core, outside application components and `invoke`;
this does not claim isolation from already trusted same-origin executable code.
Saving and granting perform no external HTTP check. The application may explicitly
check its connection/catalog through the existing native SDK connector broker
after approval and activation; there is no automatic commercial call on Save.

This delivery is the Core entry from Extensions. The proposed public application
`administration.connectors` facade, its route connector allowlist and feature
advertisement are **not implemented or advertised**. Applications need no private
Core imports to use this settings workflow. Manifest v2, native SDK 1.3 and
application frontend host v1 retain their independent version axes. No database
migration, device deployment or application-package version change is implicit.

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
peer pending/live state before dispatch and before disclosure. Expensive admission
and relational metadata precede the short response reservation. The final current
policy/lifecycle fence commits admission before reserving response capacity;
reservation then immediately precedes bounded app connect/send/FD handoff, with
no DB or artifact preparation inside that budget. Revocation after the admission
commit fences result disclosure; it cannot promise cancellation of an admitted
command. Core signs/sends once and transfers a write-half-closed connected FD. Runtime only reads
the original signed frame; it gets no key, DB, dispatch request or authority.
Existing eight shared slots, <=1 MiB frame and absolute declared 1–30 s response
budget remain. Core verifies HMAC/request/time/schema and current state behind a
conditional completion fence. A post-dispatch policy refusal is **409/unconfirmed**;
it cannot prove that effects did not happen and must not cause automatic replay.
No Core thread/DB transaction spans handler-response waiting. Relational metadata
remains Core admission with one absolute **2 s** connect/send/read deadline and
no DB/key lease. Health still gets no relational ticket. No SDK/schema/ABI changes.

CAP04 correction, 2026-10-27: preparation on a slow/concurrent ARM machine must
not consume the 2-second response handoff window. The 1-second reservation,
2-second Core / 3-second Runtime handoff and eight-slot limit are unchanged.
Reservation/connect/deadline failure before sending is `not_dispatched`; partial
send, failed FD handoff or missing/unverifiable response remains unconfirmed.
Neither classification triggers an automatic operation retry. Admin health and
host-status probes retain their separate reservation/current-state checks.

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

## CAP02 operation actor and human application permissions, 2026-10-27

For the current Core HTTP application gateway, identity comes from the validated
current user/session or kiosk terminal, never from application payload fields.
Public operation ingress remains anonymous even when a user supplies a login.
Core rechecks the actor, installation, route and effective permissions before
dispatch and at completion. Revocation after dispatch withholds the result as
unconfirmed; it does not claim that an external effect was cancelled or replay it.

An `operator` route needs its declared `required_permissions`; an `operator`
operation needs its declared `required_permission`. This applies to platform
administrators too. Current direct grants and role/group grants are additive
and scoped to one application installation. Custom business role names never
make a user a platform administrator. An author's explicitly declared
`administrator` audience still requires the actual platform role; it is a
separate endpoint, not a fallback when an operator check fails. Authors must put
business operations behind operator/application permissions and their own record
ACL instead of inferring business ownership from platform administration.

The existing authenticated `GET /api/v1/application-extensions/{module_id}/access`
returns the caller's `user_id`, stable `subject_id`, `platform_administrator` and sorted `permission_ids`
along with the existing route/operation IDs. Permissions include only declarations
of the current artifact. No user ID parameter can select another principal, and
the response is `no-store`. The operation ID list spans the explicitly supported
audiences: an administrator operation ID is not permission to call its operator
endpoint. Service resource grants are separate and are not inferred from these
human permissions or from an allowed operation ID.

Native SDK `OperationContext.from_platform` is used by the trusted host only after
authenticating the Core envelope. It preserves an immutable tuple `permission_ids`
and exposes frozen `context.actor` with `kind`, `user_id`, `subject_id`, `terminal_id`,
`installation_id` and `platform_administrator`. User, kiosk, anonymous, internal
service, existing task-worker and installation-peer contexts remain distinct.
Wrong-type/missing human IDs, invalid terminal IDs, duplicate/invalid application
permissions and human claims on nonhuman ingress are rejected, not silently
converted to an anonymous actor. A service/platform account does not become a
human administrator. `context.machine` and `context.task_execution` keep their
existing exact contracts; this actor view adds no machine scope or delegated user.

```python
def handle(self, operation_id, payload, context):
    actor = context.actor  # Do not construct this from payload or a browser form.
    if actor.kind != "user" or not context.has_application_permission("visits_manage"):
        raise ValueError("Application permission required")
    # Stable subject for the application's own customer/record ACL.
    return self.list_visible_visits(actor.subject_id)
```

`has_application_permission` tests only this invocation's human application
permission; platform administration never makes it return true implicitly. These
values are snapshots, not future execution permits, capability/connector grants
or bearer delegation tokens. They contain no JWT, session token, Core credentials
or customer memberships. Business organisations, roles and ownership remain
application-owned. The supported CAP02 browser/resource/delegation profile is
defined below. Host rollout and device acceptance remain explicit later steps.

### Stable actor, browser access and finite operation delegation

`subject_id` is an opaque `usr_<32hex>` account identity. Use it for lasting
business references; numeric `user_id` remains the Core grant-management key.
The additive `af85a6d71e75` migration backfills distinct subjects without changing
account IDs, passwords, roles, sessions or grants. Downgrade refuses before any
DDL when accounts exist, preserving subjects already used by business records;
an empty database remains reversible. A newly created account gets
a new subject even if its numeric ID was reused. An absent/invalid subject fails
closed; identity is never created while admitting a request.

Application logins require a current tracked session and a signed random login
nonce (`jti`). Refresh preserves that nonce; a replacement login cannot revive
an earlier intent by reusing a session row. Pre-nonce prototype logins require a
fresh login. Public ingress stays anonymous; a kiosk retains its enrolled
terminal identity, with no borrowed user permissions. Named guests/customers and
organisations are application identities, not additional Core account types.

`await host.access.getInfo()` returns a frozen, current-route snapshot:
`actor`, `executor`, `permission_ids`, `allowed_operation_ids`,
`delegated_operation_ids`, route/audience/build binding, `service_authority:
"separate"` and `admission_required: true`. The underlying no-store read is
`GET /api/v1/application-extensions/{module}/ui-host/{entrypoint}/access` with
the exact artifact/build query. It accepts no selected actor. Browser private
files and interactive sessions require their declared human permissions in
addition to separate service consent; platform administration does not supply
those business permissions implicitly. Connector administration remains an
explicit administrator path; its receipt owner is the exact current login.

Finite delegation is an **opt-in operator operation in the same application**:

```json
{"route_id":"visits","entrypoint_id":"visits","audience":"operator","layout":"application",
 "required_permissions":["visits_manage"],
 "delegated_operations":["confirm_visit"]}
```

The existing operation declaration must name an operator query/command, its
required application permission and a timeout of at most 10 seconds. SDK 1.3 and
ordinary own SQLite storage are required; scoped relational operations, tasks,
public/kiosk/admin delegation and cross-installation execution are refused.
Cross-installation composition belongs to CAP14. This profile introduces no
generic bearer, administrator impersonation or redelegation.

```typescript
const requestId = Array.from(crypto.getRandomValues(new Uint8Array(16)),
  n => n.toString(16).padStart(2, '0')).join('')
const intent = await host.delegations.create(
  'confirm_visit', { visit_id: 'visit_123' }, requestId, 60)
// Hand intent.delegation_id to your application's explicit queue operation.
// Return from that handler before the worker executes the delegation.
```

```python
# Owning application's worker, outside the synchronous native host handler:
receipt = platform.execute_delegation(delegation_id)
# On a lost reply, read the outcome; do not resubmit an effect automatically.
receipt = platform.lookup_delegation(delegation_id)
```

Browser lookup/cancel are `host.delegations.lookup(id)` and `.cancel(id)`. HTTP
create is `POST .../ui-host/{entrypoint}/delegations`; lookup is
`GET .../delegations/{id}`; cancel is `POST .../delegations/{id}/cancel`.
Create accepts only the route binding, `request_id` (32 lower-case hex), declared
`operation_id`, bounded JSON object `payload` and `ttl_seconds` (5–300, default
60; admission also requires operation timeout + 5 seconds remaining). The browser
cannot select initiator, executor or audience. Service SDK actions send only the
ID over the existing signed `delegation.execute` / `delegation.lookup` transport.
The ID alone grants no authority. No login nonce, JWT or resource grant is exposed
in the receipt or operation context.

Core seals the exact input, original human/login, permissions at issuance,
executor, artifact, route/build, configuration, grant revisions, recovery/boot
generation and expiry in the existing action journal. Lifetime is capped by the
original session and access-token expiry; refresh cannot extend an issued intent.
Input is at most 16 KiB, result 32 KiB, counted as compact ASCII-escaped JSON for
the sealed journal. Both use depth ≤12, ≤2048 value nodes, strings/keys ≤4096
Unicode scalars without lone surrogates and finite numbers in the safe 53-bit
range. These limits apply before execution and to returned results.
Each app has at most 8 pending/running intents and 4096 retained records. Only
never-dispatched expired records leave the active budget automatically; uncertain
running outcomes retain evidence and are never evicted to permit replay.

Before dispatch, Core verifies current human AND service rights, pins the
capability-advertising native host's real OS process, and durably consumes the
intent. Completion checks current policy again. `context.initiator` is the human;
`context.executor` is the application; `context.delegation` fixes the operation,
payload digest, required permission and expiry. The host verifies those bindings
before the handler. Delegated `platform_administrator` is always false and human
permissions are intersected with the issuance snapshot, so later grants cannot
increase the delegated authority.

Receipts distinguish pending/running/succeeded/cancelled/expired/unknown and contain
a result only on confirmed success (`automatic_retry: false`). Rights lost after
dispatch or lost execution replies produce unknown, never an inferred rollback.
Restarted Core cannot execute a consumed intent again. Reusing an ID for a changed
request/login is refused; concurrent contention can fail busy and cannot dispatch
twice. Lookup is observational; cancel only applies before consumption. An
unsupported old host is refused before app execution. Rollout must explicitly
update independent pinned hosts together with Core; matching an SDK version is
not proof of that host capability. Current local acceptance does not claim an
ARM/device rollout or all future execution profiles.

## Core-owned kiosk pairing and optional device selection, 2026-10-27

CAP02/CAP09 now include a generic Core administrator dialog in Extensions for
installed artifacts declaring both kiosk routes and kiosk operations. Metadata
comes from the exact validated ZIP (`has_kiosk_interface`), not a product name or
the newest uploaded version. The dialog lists terminals, issues a one-use code
and revokes access. Listing/revocation need only a current administrator and the
installation record; a broken optional UI/key cannot prevent those operations.
There is no automatic header menu entry.

The static `/kiosk/connect` route belongs to Core. A connection link contains only
`#module=<module-id>&code=<one-use-code>`; Core captures/removes the fragment before
bootstrap. It accepts no return URL. After claim Core renews authentication,
refreshes the compiled catalog **with the kiosk token**, and selects only the
current matching artifact/build's kiosk route. No administrator login is needed
on the terminal. EN/BG labels follow Core locale and the shared appearance;
changing locale does not remount an entered application form.

Only Core frontend code calls these transport endpoints, relative to
`/api/v1/application-extensions/{module_id}`:

| Method/path | Body | Authority/result |
| --- | --- | --- |
| POST `kiosk/enrollments` | `{request_id,label,expires_in_minutes}` | Current administrator; original code/expiry on an exact live-login retry. |
| POST `kiosk/enrollments/claim` | `{request_id,recovery_proof,code}` | Code possession; one terminal, recoverable only with the original proof/request. |
| POST `kiosk/sessions` | `{terminal_id,credential}` | Enabled owned terminal; a new 900-second access token. |
| GET `kiosk/terminals` | None | Current administrator; safe metadata including `needs_pairing`, never credentials/codes. |
| DELETE `kiosk/terminals/{terminal_id}` | None | Current administrator; idempotent revocation of an owned terminal. |

Request IDs are 32 lowercase hex characters; the claim proof is independent
32-byte random canonical base64url without padding. Codes use 24 random bytes.
Labels are trimmed 1–120 characters without controls; lifetime is 1–1440 minutes,
default 15. Extra fields fail. Claim/session responses include module,
installation incarnation, terminal, artifact/build and token lifetime; only claim
includes the long credential. Core checks those bindings before storing them.

Core persists the original browser proof/request **before** claim, and a finite,
purpose-encrypted response receipt inside the existing sealed authority journal.
Enrollment retries are bound to the exact human subject/login, request, artifact
and incarnation. Claim retries compare original code/proof hashes, return the
same terminal/credential and recheck current authority. Recovery lasts at most
five minutes and never beyond the original code expiry; both issuance and claim
recovery also require the original boot/monotonic deadline and private key.
Concurrent different claims cannot create a second terminal. Codes/proofs,
credentials and tokens never appear as plaintext in the audit/journal metadata.
After unrecoverable pairing, an administrator reviews/revokes and issues a new
code; Core never guesses success or silently creates another terminal.

The private Core browser controller owns one kiosk identity separately from the
human login (`unpaired/claiming/ready/renewing/offline/revoked`). Renewal is
single-flight and refreshes authentication only. It never retries an application
invoke. Transient loss retains the identity; confirmed revocation removes the
mounted application and denies subsequent dispatch. Mounted surfaces recheck on
focus/visibility and every 30 seconds, while every server operation retains fresh
admission/completion checks. A changed build requires current catalog navigation.
Menu/Command Palette use the checked module identity rather than the obsolete
`applicationKioskToken` flag. Forgetting the browser connection does not log out
a human or revoke a server terminal.

Additive migration `b096b7e82f86` binds new enrollments/terminals to the installation
incarnation. Historical null-bound rows remain preserved, unavailable for use,
and visible for administrative revocation/re-pairing. There is no automatic
credential adoption or requested reset. Populated identity downgrade requires
explicitly reviewed recovery. Ordinary approved application updates may retain
terminals; uninstall/reinstall, disable/revoke and native/UI trust still fence
their access. This remains reviewed same-origin code, not a browser sandbox.

Applications continue to use `useApplicationHost()` and declared kiosk operations;
the public SDK exposes neither a token store nor pairing/renewal methods. Named
business guests and terminal-scoped business outcome receipts stay app-owned.

For CAP01/CAP03 device setup, a schema-valid optional event/command/session
binding may be omitted even when there are zero available devices. Each supplied
device must still be approved and not revoked, including under the final
activation/staging writer. Missing required/schema-required bindings still fail.
Omitted `configuration` preserves the saved choice; explicit `configuration: {}`
clears optional device keys. Required bindings and non-device configuration keep
their normal schema/default rules. Cleared optional bindings cannot reappear
from package defaults on review/restart. The selector permits an empty optional
choice; no implicit device selection, provider grant or weakened consent follows.

Local automated/visual acceptance is recorded in WORKING_STATE. ARM rollout,
actual reader hardware and Child Center end-to-end acceptance remain a later
owner-run deployment step. General web lifecycle recovery remains separate CAP03
work; kiosk claim recovery does not implement it.

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
| Declarative CRUD | Optional `libraries/three_mm_crud` inside an ordinary application package | Old `runtime-extension.v1` Core endpoints/schema export are retired; records belong to the application's scoped relational storage and UI uses the public host |
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

2026-10-26 CAP11 follow-up adds streaming file profile 2, raw bounded browser
transfers, resumable uploads, exact checksummed finalization, metadata/quotas,
separate publication/transform authority, expiring revision-bound capability
downloads and an optional bounded image worker. Small native file profile 1
keeps its own limit; browser access explicitly requires profile 2. Source/build,
live human session and service grants remain separate. There is no Core DB
reset or device deployment implicit in this result. See the complete
[files/media contract and lifecycle](APPLICATION_FILES.md).

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

The operation methods are `getInfo()` and `invoke(operationId, payload, options)`.
The host also exposes typed `sessions` and the administrator reads below.
Its read-only `presentation.version === 1` provides a synchronous frozen
`getInfo(): { locale: string }` and `subscribe(listener): unsubscribe` for future
effective Core locale changes. Application roots also receive the same reactive
`locale` prop. Locale updates patch the mounted component without remounting;
Core disposes remaining subscriptions and invalidates retained handles on unmount.
The public feature advertisement includes `presentation_version: 1`. Theme tokens
remain owned by `@3mm/ui/v1`; no theme/language setter or credentials are exposed.
See [presentation and application catalogue rules](EXTENSION_UI_V1.md).
No caller-selected module, audience, URL, headers, token, HTTP client, router or
Core store is exposed. The dynamic route loader binds module, package SHA-256,
version, entrypoint and audience from the existing server catalog. Non-application
widgets/editors and components mounted outside that boundary get no host.

`getInfo()` makes a no-store request to
`/api/v1/application-extensions/{module_id}/ui-host/{entrypoint_id}` with the
bound `artifact_sha256`. Its closed public projection includes `host_version: 1`,
the matching binding, and permitted query/command IDs with their idempotency
requirements. Internal jobs and other audiences are not offered. The feature
flags are `operations: true`, `resource_authority: "separate"` and
`browser_isolation: false`: human operation access is **not** a resource grant.
Resource authority remains enforced by the existing service/platform adapters.
The original delivery did not lift the headless-only limitation. The separate
reviewed UI profile below now binds executable output before admitting it.

Concurrent `getInfo()` calls on the same mounted host, Core origin and current
credential share only their in-flight discovery request. Completion or failure
discards it; the next call reads again. An actor/origin change cannot reuse the
previous snapshot. Each operation still sends its own single POST and receives
fresh server authorization. No completed discovery or authorization is cached.

Each invocation rechecks this information and sends exactly one POST through the
existing audience-specific operation route. Its additive `ui_context` has the
exact host version, entrypoint and artifact hash. Core revalidates the installed
ZIP, active state, route/audience and current user permissions or kiosk terminal;
the existing operation and payload checks still apply. Legacy callers without
`ui_context` keep their existing API behavior. There is no browser-selected actor
or upgrade from kiosk/operator to administrator. Public calls send no bearer;
kiosk calls use only the kiosk session, even if a human is logged in too.

Core may reuse bounded verified package/descriptor/build objects within that
single invocation, across its worker phases. Every reuse rechecks file identity,
size, timestamps (including ctime), ownership/mode and the complete protected
build inventory. A changed entry is refused for the rest of the invocation;
request completion discards all entries. This never caches actors, code approval
or resource grants. Admission and completion still re-read the current package,
lifecycle, incarnation/recovery identity, human access and authenticated native
review. UI code trust validates that exact native binding without reconstructing
unrelated service-resource policy; resource use retains its own current checks.

Host v1 accepts JSON object payloads up to 512 KiB UTF-8, 10,000 values and depth
32, and access descriptions up to 256 operation entries. Cycles, non-JSON values,
path-like operation IDs and invalid command/query keys fail before dispatch.
Unknown/unavailable host versions do not fall back to a generic HTTP client.
The Core origin is pinned for the mounted host lifetime. Unmount aborts pending
transport and invalidates retained handles; cancellation does not prove rollback.

Errors expose only `ApplicationHostError.code`: `invalid_request`,
`access_denied`, `not_found` (missing read target), `unavailable`, `unconfirmed` or `disposed`, never raw HTTP errors,
request headers or backend responses. Failed POSTs have **no automatic retry,
token-refresh replay, fallback audience or inferred rollback**. On an unconfirmed
mutation, retain its original key/payload for the application's explicit outcome
review; do not generate a new key and resubmit. The neutral reference's kiosk
screen stops further submission and displays that key for review.

This is a public API for reviewed same-origin code, **not a security sandbox**.
It does not prevent such code from accessing browser globals directly. WP5's
untrusted browser/OS isolation and the broader WP4 owner/layout acceptance remain
separate gates. Current evidence and queue: [WP4 closeout](EXTENSION_PLATFORM_V2_WP4_CLOSEOUT.md).

## Current-administrator device reads (2026-10-25)

Application routes may declare `administration_reads: ["devices.list"]` and/or
`["devices.detail"]`. Only `administrator` routes can declare these unique,
closed identifiers. These are human UI reads, independent of service SDK resource
scopes and application operations. They do not grant background/service access.

```typescript
const host = useApplicationHost()
const page = await host.administration.devices.list({ offset: 0, limit: 50 })
const device = await host.administration.devices.detail(selectedDeviceId)
```

`getInfo().features.administration_reads` describes this entrypoint's declarations.
List returns `{ items, total }`, defaults to 50 rows and accepts limits 1–100 and
nonnegative safe-integer offsets. Detail adds installed modules. Both return the
Core-owned registry projection with normalized inventory schema 2, not enrollment
credentials or a duplicate registry. Missing inventory remains null; unknown device
IDs return `not_found`. No URL, request method, header, actor or generic proxy is
accepted from the application.

The Core-owned host binds both GETs under
`.../{module_id}/ui-host/{entrypoint_id}/devices[/{device_id}]` to the exact source
and executable UI hashes. Preflight is feature discovery only. Every GET rechecks
the live administrator login/session, enabled active installation, exact package,
current native UI approval and that route's declared read. Native trust, current
actor/route checks and the registry projection share one DB-enforced read-only
snapshot; immutable artifact preparation happens before that snapshot. Ordinary
users, public/kiosk/operator routes, undeclared reads, revoked/expired sessions,
blocked/demoted users, disabled applications and changed/unapproved UI are denied.
Compatibility authority mode cannot use these reads. Responses are `no-store`.
Read handles keep the mounted host's origin, cancellation and disposal rules.
There is no refresh/replay, token transfer or mutation interface.

This remains reviewed same-origin UI, not browser isolation. First consumer:
Fleet's device list/detail. Enrollment decisions, GPIO wiring configuration and Node updates remain later
contracts. Module/capability actions are described below.

## Current-administrator Agent module actions (2026-10-25)

Administrator routes can declare `administration_actions` from the closed set
`modules.install`, `modules.disable`, `capabilities.invoke`. Additional reads are
`modules.list`, `capabilities.list`, `capabilities.state`, `commands.get`.
`getInfo().features.administration_actions` advertises the exact current route.
These are human administrator operations, separate from service SDK grants.

```typescript
const id = crypto.randomUUID().replaceAll('-', '') // persist before dispatch
const receipt = await host.administration.modules.install(deviceId, packageSha256, id)
const status = await host.administration.commands.get(id) // read only; never resubmit
```

`modules.list()` exposes validated Agent packages already uploaded to Core;
installation selects their exact SHA256. `modules.disable()` uses the same shared
lifecycle as Core's device API, preserving module transition/audit behavior.
`capabilities.list/state()` reads the provider catalog and reported state.
`capabilities.invoke(deviceId, invocation, requestId)` requires provider identity,
declaration digest, contract version, declared action/arguments and a 5–30 second
TTL (default15). The Core queue pins the provider/control generation and contract;
changed providers/episodes are refused before first dispatch without rewriting
already delivered uncertainty as `not_dispatched`. New administration calls never
silently fall back to an unversioned capability.

Every mutation binds the current application/entrypoint, source and built UI
hashes, request UUID and exact body. Immutable input preparation precedes the
short key → Core authority guard → tracked current administrator/session →
application → device write transaction. Exact native UI approval, active package
and declared action are rechecked in that same transaction. Queueing, module
state, sealed action receipt and audit commit together. The existing authority
Action table owns request idempotency; no new schema or browser-selected actor.
A changed payload, route, application or actor cannot reuse a recorded request.
`commands.get()` verifies its sealed receipt and current native/route/user access;
it exposes that user's matching request outcome, not arbitrary command history.

A successful POST means accepted/queued, never physical completion. Confirm only
an Agent `succeeded` receipt and inspect the reported state. Accepted human work
is durable until completion/expiry; closing UI does not cancel it. Failed/expired
or lost replies are not proof of rollback and never trigger automatic resend.
Origin pinning, credential-free public transport and disposal remain host rules.
Fleet persists one pending identity per device before dispatch, blocks conflicting
controls while uncertain, reconciles after reload using GET, and requires a
separate explicit outcome review before clearing an unresolved request.

The first consumer installs Digital GPIO Output's versioned 1.1.0 package and
renders its boolean action from the declared schema. Core has no GPIO- or
Fleet-specific handler in this administrator interface. The acceptance is mock
simulation; the module uses the Agent's configured driver, not an implicit mock
fallback. Hardware wiring and Node updates are outside this bounded path.

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
