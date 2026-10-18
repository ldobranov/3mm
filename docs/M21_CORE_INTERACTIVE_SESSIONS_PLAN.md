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
