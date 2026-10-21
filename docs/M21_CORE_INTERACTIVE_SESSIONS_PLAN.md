# M21 — Core Interactive Sessions & Remote Streaming

Status: in progress. WP0/WP1 contracts and WP2/WP3 gateway/transport prototypes,
with a WP5 local test harness, are integrated into the current development tree
from the uncommitted `/opt/3mm-dev` work based on `v0.3.0-beta.51`.
The experimental HTTP/WebSocket router is deliberately **not mounted** by
`backend.main`; no live session service is enabled by an update.
WP4 (M20 integration/security), production Agent/Hub connectors and physical
acceptance remain open. This is a new,
independent milestone; it does not rename or reopen Milestone 20 or earlier
milestones.

Current local opt-in development profile and next-release test instructions are
in section 15 and `M21_LOCAL_TERMINAL_TEST.md`. Historical prototype/off notes
below do not authorize enabling the old unrestricted router.

## 1. Purpose

Add generic, secure, bidirectional interactive-session infrastructure between the
browser UI, 3mm Core, local Agent processes and remote devices. M21 provides the
common mechanisms for *future* extensions (Linux terminal, serial console, live
log/diagnostic streaming, interactive debuggers); it does **not** implement a
terminal. A second, independent interactive provider (a test echo session) must be
implementable without Core changes — that is the Definition of Done.

## 2. What we reuse (grounded in the current code, v0.3.0-beta.47)

| Existing mechanism | File | M21 use |
| --- | --- | --- |
| C10 device transport | `agent/device_transport.py` | kept for commands/reports; a separate session transport is added |
| C11–C14 capability contracts | `three_mm_protocol/capability_contracts.py` | contract versioning + digest discipline |
| Capability registry/discovery | `backend/services/device_capability_registry.py` | reuse `registered_capabilities` / `capability_catalog` for provider discovery (M21.5); registered ≠ available |
| Application SDK 1.3 | `three_mm_application_sdk/__init__.py` | additive session provider API, not a new runtime |
| M20 package/review/permissions | `docs/EXTENSION_PLATFORM_V2_*` | session providers declare and are reviewed through it |
| Browser auth | `backend/utils/jwt_utils.py` (HS256 access token) | WebSocket sessions authenticate by a short-lived ticket, never `session_id` alone |
| Message bounds | `three_mm_protocol/node_security.py` (`NODE_MESSAGE_BYTES` = 64 KiB) | payload/frame bounds |

Before M21 there was **no WebSocket** usage in this repository. WebSocket is
the experimental browser transport, added as a new primitive — not a change to the C10/C11
command queue. The JSON command queue must **not** carry PTY data.

## 3. Fixed contracts (WP0)

Independent version axes, consistent with M20:

- Session protocol: `interactive-session.v1`, `contract_version = 1`.
- Application SDK: stays `1.3`; session API is additive.
- Module manifest: stays `manifest_version: 2`.
- Application descriptor: stays `application-extension.v1`.

Operations: `open`, `attach`, `data`, `control`, `detach`, `close`, `status`,
`terminate`.

Session state machine (pure, no I/O):

```
requested ──open_accepted──▶ active
requested ──open_rejected──▶ error
active     ──detach───────▶ detached
detached   ──attach───────▶ active
active/detached ──close───▶ closed
any non-terminal ─terminate▶ terminated
active/detached ──fail────▶ error
```

Every session carries: unique `session_id`, resolved installation/user identity,
target device, provider + capability, granted rights/access mode, creation time and
expiry, transport and process state. Knowing a `session_id` grants nothing; Core
re-authenticates and re-checks current authority on every open/attach/use.

## 4. Security architecture (M21 invariants)

- Deny-by-default for all new permissions; separate authorization for local vs remote.
- Explicit review/apply of executing native providers through M20.
- Execution under a separate unprivileged Linux identity; no root, no Core DB/private
  secret access, no arbitrary shell through Core APIs.
- Bounded memory/process/file-descriptor/session counts.
- Session revocation on permission removal or provider removal.
- Cross-device and cross-installation session-hijacking protection.
- Audit on create/attach/deny/terminate/privilege transitions.
- Link-loss never implies a new session; reconnect re-authenticates; old messages are
  never replayed as new commands; Core rollback must not resurrect privileged sessions.

The boundary to M20 is explicit: `reviewed_native_scoped` is **not a sandbox**. M21
must not present it as untrusted-code isolation. Shell execution must not be able to
read/modify `/etc/3mm`, `/var/lib/3mm` or the active immutable release except under a
separate, strictly bounded maintenance mode.

## 5. Resource policy (configurable, not hardcoded in a terminal extension)

| Resource | Default |
| --- | --- |
| Active sessions (Zero W) | 1 |
| Active sessions (Hub) | 4 |
| Idle timeout | 900 s |
| Session maximum lifetime | 14400 s |
| Buffer per direction | 64 KiB, backpressure |

## 6. Work packages

- **WP0** — architecture audit + contract design (this document + source map).
- **WP1** — session protocol + SDK: typed models, state machine, provider SDK,
  independent versions, validation, unit tests. (current slice)
- **WP2** — local session gateway (WebSocket, browser auth, session management,
  bounded streaming, local Agent transport).
- **WP3** — remote Agent transport (Hub ↔ Node, discovery, multiplexing, revocation,
  disconnect/reconnect, resource control).
- **WP4** — M20 integration + security (manifest validation, native review, process
  isolation, permission grants, audit, rollback/recovery).
- **WP5** — acceptance + documentation (Standalone, Hub, Zero W; regression,
  upgrade/rollback, security negatives, public SDK contract).
- **WP6** — optional cloud relay (separately approved; only after cloud management
  has the shared identity/delegation contracts).

## 7. Definition of Done

M21 is done when a **second independent interactive provider** (e.g. a test echo
session) can be implemented against the public contracts without Core changes, not
when a terminal works. Local acceptance additionally requires: one protocol for
local and remote; real bidirectional binary stream (no command polling); every
operation through a real authorization boundary; no hardcoded terminal/Fleet names;
provider discoverable through the common registry; a Node without the provider
cannot be authorized to start a process; revocation terminates active access;
Zero W passes a real resource and reconnect test; M20 permissions/package
approval/recovery keep working; C10/C11 command protocol stays compatible; immutable
installer update/rollback preserves identity, pairing and persistent data.

## 8. Progress and remaining gates

Imported development prototypes (no commit/push, no live rollout):

- **WP0** — this plan + source map.
- **WP1** — `three_mm_protocol/interactive_session.py` (models, state machine,
  frame codec, provider declaration) and `three_mm_application_sdk/session.py`.
- **WP2 (core)** — `backend/services/interactive_sessions.py`: one-time ticket
  store and bounded local session manager with a reference echo provider.
- **WP3** — `backend/services/interactive_session_transport.py`: `SessionTransport`
  boundary, `RemoteSessionRouter` (multiplexing, authority re-check, fail-closed)
  and a loopback reference transport; discovery models `SessionTargetV1` /
  `SessionDiscoveryV1`.
- **WP2 (live)** — `backend/services/interactive_session_gateway.py` (composition
  root: ticket store + manager + reference provider) and
  `backend/routes/interactive_sessions.py` (HTTP one-time ticket endpoint bound to
  the existing JWT `require_user`, plus the ASGI WebSocket endpoint). Only the
  original development checkout mounted this in `backend/main.py`; that activation
  is **not imported**. The isolated Starlette `TestClient` exercises the endpoint,
  so no extra dependency is needed for verification; production uvicorn needs a
  WebSocket implementation (`uvicorn[standard]` / `websockets`).
- **M21.5 (discovery)** — `backend/services/interactive_session_discovery.py` +
  `GET /api/v1/interactive-sessions/discovery` (admin-only, read-only): builds
  `SessionDiscoveryV1` from the real `device_capability_registry`
  (`registered_capabilities`) plus remote router targets. A device is listed only
  when it offers a session capability; an offline device with the provider is
  listed as unavailable, never offered as a working session.
- **WP2 (live remainder: local Agent transport)** —
  `backend/services/interactive_session_agent.py` (`DeviceTicketStore`,
  `AgentSessionTransport` with per-operation correlation keys),
  `POST /api/v1/devices/{id}/session-ticket` (device-authenticated via
  `require_device`), `WS /api/v1/devices/{id}/session-ws` (hello declaration,
  transport registration into the shared `RemoteSessionRouter`), and
  `agent/session_transport.py` (`AgentSessionHost`, the Agent-side protocol
  handler hosting SDK `SessionProvider` implementations). The browser gateway
  routes sessions for devices with a connected transport through the Agent;
  routed sessions keep their own user binding. End-to-end
  browser→Core→Agent→provider is proven in-process through two concurrent
  TestClient WebSockets, including fail-closed after Agent disconnect.
- **WP5 (hardening)** — `backend/tests/test_interactive_session_hardening.py`:
  8 concurrent opens respect the limit, ticket store survives high volume with
  bounded tombstones, malformed/oversized frames and control messages are
  rejected, idle/lifetime/payload boundaries are exact.
- **WP5 (local harness)** — `backend/services/interactive_session_acceptance.py`:
  deterministic in-process acceptance proving the Definition of Done (a second,
  independent `CounterSessionProvider` works without Core changes) plus negative
  scenarios (cross-user, oversized, revocation, ticket replay, missing capability,
  disconnect without replay). The harness explicitly checks that the reference
  providers satisfy the **public SDK** `SessionProvider` protocol and metadata,
  not only the internal adapter.

Review fixes (2026-10-12, after external review):

- Protocol timestamps now accept ISO 8601 strings, so `SessionOpenAcceptanceV1`
  and `SessionStatusV1` round-trip through JSON.
- The public SDK `SessionProvider` is `runtime_checkable` and its `receive`
  returns outbound bytes; the Core adapter is structurally identical, so the
  independent-provider interface is proven locally against the public contract;
  the full Definition of Done remains subject to the production/live gates.
- `LocalSessionManager.open` is serialized (the session limit cannot be exceeded
  by concurrent requests); `control`/`deliver`/`close` fail closed after a
  terminal state; terminal sessions and ticket tombstones are bounded.
- `RemoteSessionRouter` re-checks authority generation and capability on every
  use, so a re-enrolled/revoked device or withdrawn capability cannot keep an
  old session alive.

Remaining gates:

- **Release integration gate (2026-10-18)** — the source and tests are carried
  forward, not enabled as a production feature. HTTP ticket/discovery and both
  browser/device WebSocket paths must stay absent from the production app until
  WP4 closes. There is no runtime switch to bypass this gate. Current reference
  ticket/user bindings and in-memory device generations are not current M20
  grants, live revocation checks, audit or OS isolation. Transport timeouts,
  cleanup/resource bounds, sequencing and connection replacement also need
  production hardening. Passing the local harness proves a bounded prototype,
  not the complete M21 Definition of Done or physical acceptance.

- **WP2 (live)** — production Agent connector: the Agent-side handler is
  transport-agnostic; a production connector needs a WebSocket client library
  (`websockets`), which is a deployment dependency decision, not a contract one.
- **WP3 (live)** — real Hub↔Node session transport.
- **WP4** — M20 manifest validation + native review + isolation + audit wiring
  (deferred; touches the actively developed M20 authority code).
- **WP5 (live)** — physical Zero W resource/reconnect and live security negatives.
- **WP6** — cloud relay only if separately approved.

## 9. Integration verification — 2026-10-18

The import preserves the parallel checkout unchanged. Its `backend/main.py`
router activation was intentionally excluded; the protocol exports were merged
additively, preserving the newer M20 checkpoint/peer exports. The Agent's SDK
type import is now under `TYPE_CHECKING`, so the minimal Node does not acquire
a runtime dependency on Core or the application SDK.

- **118 focused cases pass** (6.65 s): all imported session protocol/SDK,
  manager, routing, discovery, WebSocket, Agent and local harness tests, plus
  six release-boundary cases. Actual production HTTP routes return 404 and both
  WebSocket paths refuse connection; test apps mount the experimental router
  explicitly. The first two new gate checks assumed flat FastAPI route objects;
  the corrected full rerun exercises real routing, including lazy routers.
- **969 regression cases pass** (209.44 s): the full shared protocol/SDK suites,
  M20 relational-status/native-grant/UI authority, scheduler, device-platform,
  capability-route and pairing tests. Protocol/SDK session cases overlap the
  focused run; the counts are not additive coverage.
- **15 deployment cases pass** (0.84 s): reproducible minimal Node archive,
  wheel checks and the existing WP4 target-release contract. A subprocess imports
  the Agent session module from the extracted Node artifact with Core/SDK imports
  explicitly blocked; neither package is required or bundled for this prototype.
- Frontend production build passes (7.34 s). No frontend screen or runtime
  dependencies changed. Existing deprecation/test-key warnings remain visible.

Evidence: `.runtime/m21-import-{focused,regression,package}.{log,xml}`; disposable
Linux sources are under `/var/tmp/3mm-m21-import.*`. No live install, service,
grant, pairing, OS package, release version, branch, commit or push was changed.
These are targeted integration checks, not the complete next-release suite or
completion of M20/WP4 or M21. Consolidated release verification remains separate.

## 10. beta.53 prototype corrections

Agent controls now pass the validated action and arguments to the public provider
contract. Gateway output is type/size checked and encoding failures become bounded
errors: a maximum valid input may produce a refusal when its provider expands the
output beyond the limit, but the connection stays usable and no bytes are silently
truncated. An identity provider can still round-trip the maximum payload.

Device ticket issue/redeem is serialized; expired pending tickets are pruned
before the capacity check. The existing string API remains, with a separate exact
expiry result for the HTTP response. Its expiry is independent of device metadata.
The focused suite passes 127 cases, including nine new regression cases; existing
scope/production-off gates remain. Full release verification is separate below
and in CHANGELOG. This does not authorize enabling the experimental router.

## 11. Consolidated beta.53 verification — 2026-10-18

The complete local default Python collection passes 4,625 cases, with 602
platform-gated skips and five successful subtests (53m14s), without failures.
Deployment/Application SDK passes 382 cases. Two separate actual Root/helper
cases verify the delivered WP4 ZIP and signed SQL/status/revocation path; they
do not substitute for every privileged or physical acceptance case. Frontend
passes 455 tests across 52 files, type check and production build.

Focused M21 counts above overlap these runs and are not additive coverage.
Evidence: `.runtime/release-beta53-{full,extra,root}.{log,xml}`. Tests use disposable
Linux source/mount namespaces, not the installed VM. Exact tagged Python 3.13 CI
and reproducible full/Node builds additionally gate publication. The production
router remains absent; neither M21 production readiness nor M20/WP4 closure is
claimed by this integration.

## 12. Universal SDK output and disposable PTY slice — 2026-10-20

One Terminal extension consumes one M21 session contract. Local, Hub/Node and
future Cloud paths differ in platform routing/authorization, not extension
authentication, pairing or transport clients. Local-first acceptance does not
create a separate terminal API, a new authority subsystem or a Cloud relay.

Added the optional public `SessionOutputProvider.read_output(session_id)` contract
to SDK 1.3: await independent bounded bytes, or None at EOF. Request/response
providers remain compatible. No protocol/manifest/descriptor version changes.
`three_mm_runtime.session_output` supplies the generic output pump; the Agent
host exposes it only for an already admitted session with a mandatory explicit
checker. It awaits each send (one chunk, no unbounded output queue), checks while
reads/sends wait and again before delivering received bytes, and closes only the
owned session on failure/EOF/cancel. Duplicate consumers are refused. Unconfirmed
cleanup retains fenced ownership; it is not called a successful close. The minimal
Node includes this runtime module without Core or Application SDK dependencies.

The independent terminal checkout supplies its own PTY adapter and optional output
implementation. Core contains no concrete Terminal identifier. Real disposable
unprivileged Linux tests prove prompt-before-input, delayed output, resize, EOF,
cleanup with a blocked read, and process termination after the TEST authority
checker denies access. The adapter accepts an already owned child/PTY; it does
not start a shell or establish OS isolation. Temporary shell creation occurs in
the test harness only, with a scrubbed environment and temporary working directory.
No installed application/service, key, grant, pairing or hardware was changed.

This slice does NOT connect real current M20 grants/audit, production provider
registration/isolated process launch, browser host streaming, or the real
Agent/Hub connector. Unsolicited output must be integrated with transport
sequencing/response correlation and close notifications before a live connector
is enabled. Production M21 HTTP/WebSocket routes remain absent; Terminal Connect
remains disabled. It is neither full M21 acceptance nor permission to publish an
enabled terminal. The already accepted M20 restore/rollback work is preserved.

Verification for this slice: **216 targeted Core/protocol/SDK/runtime/deployment
cases pass**, no skips (20.49 s, nine existing warnings); report
`.runtime/m21-session-output-core.xml`. This includes M21 production-off gates,
minimal reproducible Node packaging/import without Core/SDK, and the accepted
backup/installer regression files. It is not the full release suite. The terminal
checkout passes **37 unprivileged native Linux tests** with five real PTY cases,
plus **24 frontend tests** and TypeScript checking. Formatter/import/whitespace
checks pass; no frontend screen, runtime dependency, version, branch, commit,
push, release, service configuration or installed permissions were changed.

## 13. Current M20 session-resource authority — 2026-10-20

The development backend now supports explicit `session_bindings` in the existing
application descriptor (SDK 1.3, descriptor v1, manifest v2). Each binding names a
saved device configuration reference, provider, capability, read/write mode,
allowed controls, exact open options and a separately declared human permission.
The package must consume that capability and request `sessions.open`; that coarse
manifest request alone grants nothing. No concrete extension name enters Core.

New internal authority context/subject/evidence/selection v10 adds
`session:<binding_id>:open`. The v1-v9 formats and policy adapter revisions remain
unchanged. The existing native review -> Review -> Approve -> Apply -> Revoke
coordinator seals and re-resolves session resources, including current device
control generation, active credentials, runtime feature revision and effective
provider registration/version/contract. Inventory offers or a transport hello
cannot substitute for that registration. Unsupported/missing session contracts
and missing `interactive_sessions.v1` runtime support fail closed. Session scopes
are explicitly selectable; older resource families retain required-scope rules.
No database schema change or new permission store is introduced.

`application_session_authority.M20SessionAuthority` is an INTERNAL Core permission
adapter, not a public authorization-token issuer or process launcher. It verifies
the current sealed service grant and the exact tracked human login, token expiry,
account state and live direct/role/group application permission. Administrators
also need the explicit human permission. Its binding fixes the login/session,
application incarnation/instance/artifact, request, provider and grant revision.
Input, controls, status and output have separate checks; read mode cannot admit
input. The output checker uses this real adapter with the bounded output pump,
including checks while the provider is idle. Observed revocation closes the owned
provider; fresh service approval cannot renew an old session binding.

Important remaining gates: production browser/Agent/Hub transport, authorized
discovery, session audit/lifecycle integration and isolated process launch are
NOT enabled by this change. The existing authority UI reader intentionally does
not accept the new session DTO yet; it needs explicit resource cards/validation
before owner-driven UI acceptance. The tested existing admin review HTTP API can
review the new resource, but it is not a session-open endpoint. Status reports
`session_runtime_not_connected`, never a green runnable-session claim. Generic
effect/compatibility admission refuses session scopes. M21 production HTTP/WS
routes remain absent, Terminal Connect remains disabled, and no installed keys,
permissions, services, application package or release version were changed.

Verification: **1,695 passed / 290 platform-gated skips** in the targeted Windows
regression run (276.44 s); **66 passed** in the native Linux authority/legacy
integration run (107.65 s), plus **two distinct mixed-resource cases passed**
(6.73 s), with no Linux skips. These counts overlap pure contract coverage and
are not additive release coverage. The unchanged frontend production build passes
(13.75 s). Reports: `.runtime/m21-authority-regression.xml`,
`.runtime/m21-authority-linux.xml`, `.runtime/m21-authority-mixed-linux.xml`.
Existing deprecation/test-key warnings remain visible. This is not the full
release suite, UI acceptance, hardware acceptance or completed M21.

## 14. M20 approval screen and browser host — 2026-10-20

This supersedes the UI/browser-pending notes in sections 12–13, not the
production execution gate. The admin dialog now validates and displays v10
session resources: exact owner/artifact, device, provider/version, mode, controls,
opening options and the separate current-user application permission. Session
and peer choices start unselected, remain visible when unselected, and changing
one invalidates the previous review and acknowledgment. Review, Approve and
Apply remain separate; missing runtime support never displays effective rights.
Older required resource-family semantics and signed formats are unchanged.

The additive public `ApplicationHost.sessions` API exposes target discovery,
open, binary input/output, controls, observe and owned close. Only the private
Core host knows backend URLs, login credentials, tickets and sockets. It pins the
exact application source/build/entrypoint, uses one dispatch without token
refresh/retry/reconnect, bounds pending work and initial output, checks ordered
frames/acknowledgments, and disposes connections with the dynamic route.

`application_sessions.application_session_router(service)` is an EXPLICIT
composition factory, still absent from `backend.main`. Its service requires an
exact reviewed runtime connection; no echo, bare hello, arbitrary device or
extension-name fallback. The existing compiled-UI/native/route checks and actual
M20 service AND tracked-human authority gates apply at ticket issue/redemption,
input/control/output and periodically during idle reads. Tickets expire after
15 seconds, are one-use and sent in the first WebSocket message, not URLs.
Exact browser Origins are mandatory. Read-only sessions cannot send input.
Device/provider/build/grant/login drift stops the owned stream; approval cannot
renew an existing binding. Lifecycle audit contains identifiers/outcomes only,
not tickets, credentials, input or output. Cleanup failure retains fenced
ownership rather than reporting success. In-memory request/ticket fences are
bounded and are NOT durable receipts or an exactly-once guarantee across restart.

The separate terminal checkout consumes this SAME public host and declares its
session binding and human permission. This host binding was built with a
plain-text transport preview; concurrent xterm renderer work in that checkout
is outside this verification slice. Core contains no Terminal identifiers.
Neither renderer demonstrates a working production target or OS isolation.
Existing package version/wheel snapshots have not been published or installed
by this change.

Still required before production activation: isolated unprivileged process
launch; a trusted provider connection over the real local/Agent/Hub boundary;
deployment WebSocket limits/dependencies and lifecycle/restart integration;
authority-key contention acceptance, complete denial/attach/terminate audit and
physical acceptance. The existing coordinator still refuses a busy key rather
than weakening its lock; the deterministic idle-revocation test serializes its
deliberate admin write against the in-process reader. Attach/detach,
Cloud relay and maintenance/root access are not enabled by this connector.
The old unrestricted prototype router must remain off. No installed keys,
grants, services, pairing, release version, Git branch/commit/push were changed.

Final browser/security and production-off verification: **32 Linux cases pass**
with no skips, recorded in `.runtime/m21-browser-linux-final.xml` (144.50 s).
The earlier larger Linux run passed 79 cases before its production-router check
found a missing `deployment` source folder in the disposable staging copy; the
final gate run includes that actual production routing check. Counts overlap
and must not be added. Existing dependency/deprecation/test-key warnings remain.

Frontend verification: **492 tests across 56 files pass** in the sequential
rerun (114.15 s), recorded in `.runtime/m21-browser-frontend.xml`. One earlier
parallel run hit an unrelated 5-second bootstrap-import timeout under concurrent
load; no timeout or assertion was relaxed. Type checking and the production
build pass. Browser visual checks cover EN/BG,
light/dark and narrow/desktop layouts using synthetic local fixtures, not real
permissions. Terminal host transport passes 28 frontend tests and its original
preview build/type check; subsequent concurrent renderer work is not included
in those results. None of this replaces owner-driven VM acceptance or a
consolidated release run.

## 15. Local isolated provider and next-release trial — 2026-10-20

This supersedes the local-launch/registration-pending notes above, NOT the full
M21 acceptance gate. The next Core release can carry an explicitly enabled
**local, self-provided, ephemeral** session profile. A VM-Hub uses its own local
Agent identity; no remote Node ID, inventory or SSH fallback selects a process.
There is still ONE public session contract/Terminal extension. Cross-application
provider code trust, Agent/Hub transport, Cloud and maintenance/root access are
not enabled by this local slice.

`session_providers` declares a capability, support contract and zero-argument
factory in the same reviewed pure-Python service wheel. Package checks require
matching manifest provides, SDK 1.3, bounded safe wheel contents and the factory
module. Core has no concrete Terminal ID or shell launcher. The existing device
registry gains a Core-owned local adapter, never an Agent-forgeable provider type.
The read-only declaration cache is bounded and populated only after authoritative
ZIP validation outside key/snapshot leases; it is not a grant. A cold cache is
unavailable until preparation, and every self-provider authority check revalidates
the calling installed artifact. Native review can inspect a disabled provider;
execution additionally requires its active installation, current M20 resource
grant, exact compiled UI and independent tracked-human permission.

The scoped browser router is mounted ONLY with `THREE_MM_LOCAL_SESSIONS=1`.
Old unrestricted prototype routes remain absent. The private runtime resolver
re-reads the exact reviewed wheel and supplies a per-session Unix-socket adapter,
not browser-selected paths/factories or a bearer token. The real server now pins
`websockets` and limits inbound frames, queues and compression independently of
the application's own frame validation. Provider control receives only the public
SDK action/arguments envelope; the former browser-wire envelope mismatch is fixed.

Socket activation accepts only the Core UID over a root-owned, Core-group socket.
Each connection gets a distinct systemd DynamicUser/cgroup, no Core environment
file, no capabilities, no network, inaccessible Core/home/Windows paths, bounded
memory/tasks/descriptors/file size, and bounded private tmpfs scratch space. The
worker verifies the existing OS boundary before loading the reviewed wheel.
Terminal's PTY factory depends only on the public SDK process-profile guard, not
private Core/runtime imports. That guard verifies OS facts; it never grants
permissions or creates isolation. Prompt/output/input/resize use the same SDK.
Closing waits for actual cgroup emptiness, including an escaped child process
group. Link loss and Core stop/update tear down owned workers; uncertain outcomes
are fenced, not automatically replayed/reopened. Root/sysadmin access is absent.

Configured authority stores allow at most 250 ms for lock acquisition BEFORE
admission, so an ordinary idle check does not routinely defeat an administrator's
write. This does not resend a mutation or weaken the key/guard order. Explicit
store users retain the existing fail-fast default. Actual service revocation is
tested without serializing the admin write artificially against the idle reader.

The immutable installer installs the optional units but does NOT enable the
feature, provision a key or approve rights. Workers are stopped before update
state copying; rolling back to a pre-profile release removes/disables the optional
units rather than resurrecting them. The target deployment contract now requires
the new route, resolver, SDK/runtime files and units. The Node payload stays
independent. Owner-driven setup and evidence are in `M21_LOCAL_TERMINAL_TEST.md`.

Verification is targeted, not the complete release suite:

- 604 shared-protocol cases pass; 198 Linux session/key/registry/browser/installer
  cases pass with two platform-gated skips. The actual Root ACL case is run
  separately and passes; the non-POSIX refusal case cannot run on Linux.
- Real TCP WebSocket tests cover the deployed server driver and pre-application
  rejection of oversized frames; they are included in the 198 Linux cases.
- Explicit Root systemd acceptance uses a disposable code/DB/identity fixture,
  with two actual M20→UI WebSocket→independent sandbox-provider scenarios: human
  revoke and service revoke while idle. Separately the real Terminal factory
  proves prompt-before-input, delayed output, resize, denied private paths/network,
  scrubbed environment, close of a detached process group, and link-loss cleanup.
  Installed Core keys/grants/data, owner Hub WSL and physical devices are untouched.
- 83 builder/target-contract cases and four minimal-Node/deployment cases pass.
  Current Terminal passes 28 frontend tests/typecheck; its rebuilt disposable
  wheel/source ZIP passes validation and the actual Core UI compiler with xterm.
  Core frontend typecheck and production build pass. Browser review covers the
  synthetic disconnected desktop state in light/dark, not installed acceptance.

Counts overlap and must not be added as release coverage. Evidence:
`.runtime/m21-local-{protocol,runtime-final,admission-deploy,key-root}.xml`,
`.runtime/m21-session-sandbox-live.xml`, and `.runtime/m21-browser-tcp.xml`.
Existing dependency/deprecation/test-key warnings remain visible. No version,
Git branch/history/commit/push, installed permission or release was changed.
Only disposable test units/code directories were created and removed. The actual
installed-VM trial and consolidated release checks remain required before a
release-readiness claim; this does not close the whole M21/WP4.
