# C4 — Minimum Node protocol conformance

Defined and tested locally 2026-10-03 on C0–C3. Applies to the common Core
Device/Node Platform in Standalone, Hub/Fleet, local Agent and applications.
Fleet, cloud, inbound Node HTTP servers and Linux are not prerequisites.
Device transport remains `1.0`, HTTP APIs remain `/api/v1`, Application SDK
remains `1.3`. No deployment, release, database migration or re-pairing.

This document separates **mandatory protocol behavior** from **optional runtime
operations**. It is a conformance specification, not a new wire announcement,
certificate of production readiness or claim that every old endpoint strictly
enforces every requirement. C5 implements feature advertisement/negotiation;
C7/C8/C9 complete security, migration and mixed-runtime acceptance.

## 1. Mandatory common behavior

Every new Node must implement these boundaries, even if no application
capabilities are currently enabled. Historical Python DTO names containing
`Agent` are compatibility names; a Node does not need Python or this SDK.
In the table, `D` means `/api/v1/devices/{device_id}`.

| Contract | Existing transport / shared schema | Required semantics |
| --- | --- | --- |
| Identity | `dev_` + 32 lowercase hex characters | Persist across restart, IP/hostname change and ordinary update. Not a MAC, IP or user-selected name. |
| Enrollment | `POST /api/v1/pairing/enroll`; `NodeEnrollmentRequest/Response` | Stable request token and credential hash; explicit administrator approval. Same retry must not create a new identity/credential. |
| Authentication | `Authorization: Device <credential_id>:<secret>` | Unique per-device credential, own-device scope, selected Core authority, revocation. Human/application credentials do not substitute. |
| Inventory | `POST D/inventory`; `DeviceInventoryV2`, `202` | Truthful platform/runtime/resources; optional measurements omitted, not invented. Inventory capability names do not register authority. |
| Heartbeat | `POST D/heartbeat`; `AgentHeartbeat`, `202` | Report uptime and ready/degraded status. Core online status derives from heartbeat receipt policy, not a Node's boolean. |
| Commands | `GET D/commands/next`; `AgentCommand`, `200` or `204` | Validate device/version/type/arguments/deadline; persist replay identity before irreversible work. Empty response is normal. |
| Command results | `POST D/commands/{command_id}/result`; `AgentCommandResult`, `200` | Delivery is not execution. Return succeeded/failed honestly; retry the original terminal result without repeating the effect. |
| Capability registry | Common registry; `CapabilityProviderReportV1/SnapshotV1` for runtime-owned providers | Advertise actual capabilities, preserve provider ownership/revision, respect Core-owned disable. No fake module installations. |
| Capability invocation/state | Existing `capability.invoke` envelope; `POST D/capabilities/{capability_id}/state`, `CapabilityStateReportV1/SnapshotV1`, `200` | Execute only supported actions and publish real observations for registered capabilities. No fabricated success/state. |
| Events | `POST D/events`; `DeviceEventV1`, `202` | Unique persistent event ID, identity/time/type/payload; retry identical content, do not regenerate IDs on replay. |
| Desired/reported state | `GET D/desired-state`; `DeviceDesiredState`, `200`; `POST D/reported-state`, `AgentReportedState`, `200` | Persist desired revision; report what was applied. Reject/describe unsupported state instead of acknowledging work not performed. |

Legacy pairing-code claim/approve/complete remains a supported enrollment
adapter. Existing Linux nodes need not adopt code-free enrollment or re-pair.
Existing inventory schema 1 remains accepted; new independent runtimes use
schema 2. Schema compatibility and provider representation are separate from
transport protocol and deployment role.

Capability registration has one Core query boundary, with two compatible
representations: installed Agent module registrations, or authenticated
runtime provider reports. A Linux module provider does not need to fabricate
a firmware report; a firmware provider does not need module lifecycle support.
Runtime-owned providers use device-authenticated GET/PUT at
`D/capability-providers/{provider_type}/{provider_id}`. Registration revision
and ownership rules are specified in [C2](PLATFORM_NEUTRAL_C2.md).

Capabilities may be empty. A node supports command/event/state transport even
when idle; it need not invent events or measurements. An application capability
is not mandatory merely because the reference client demonstrates it.
Stateless capabilities must not claim observations they cannot provide.

## 2. Optional runtime operations

These operations are not implied by pairing, a deployment role, a platform
string, inventory schema 2 or a capability registration:

| Optional operation family | Existing examples / requirements |
| --- | --- |
| Agent module lifecycle | `module.install`, `module.disable`, package files, module manifests/runtime. Not required for firmware capabilities. |
| Runtime update | Linux `agent.update.prepare` / `agent.update.apply` and privileged installer/recovery helper. Firmware OTA is a different optional implementation, not this Linux workflow. |
| Local automations | `automation.apply` / `automation.remove` and an autonomous rule runtime. |
| Local GPIO configuration | `agent.gpio.configure` and the applicable driver/configuration contract. Capability invocation alone does not imply this feature. |
| Signed application execution | `application.capability.invoke` with Core one-time authorization, expiry and signed binding checks. Never execute it as an ordinary unsigned capability command. |
| Local diagnostics/provisioning | Agent hello/health/inventory HTTP, browser setup, Wi-Fi/AP, NetworkManager, OS/Python/systemd diagnostics. No inbound Node web service is required. |

Concrete application capabilities such as `gpio.digital.control` or
`identifier.scan.v1` are separate from these protocol/runtime operations.
Neither a capability nor `provider_type=embedded_firmware` grants module
lifecycle, OTA or execution-permit support. Python and a filesystem package
layout are implementation choices, not mandatory Node contracts.

In C4 an unsupported delivered operation must fail without effects and return
an honest result. C5 must allow consumers/Core to avoid queueing unsupported
optional workflows before dispatch, with explicit legacy compatibility.
There is **no new `features` wire field in C4** and no SDK/protocol version bump.

## 3. Versions, time, persistence and failures

- Unknown transport versions/extra fields are not silently interpreted as a
  compatible protocol. Retain each existing envelope: events and desired/state
  DTOs do not gain a `protocol_version` field merely because other DTOs have it.
  `DeviceEventV1` is the existing untagged event envelope; event-specific payload
  schemas keep their own versioning and validation.
- New clients send timezone-aware UTC timestamps. Use monotonic clocks for
  local uptime/intervals, not wall time. A command must not start after expiry;
  retrying its stored result does not authorize a second action or extend TTL.
  Clock recovery/synchronization is a runtime responsibility.
- `command_id` and idempotency key are durable, device-scoped receipt identity.
  Changed content must never be treated as the same action. Real physical
  dispatch uncertainty is quarantined, not replayed blindly. The C3 SQLite
  simulation transaction is not a physical execution guarantee.
- Persist credential/authority, desired revision, receipts and pending
  event/results before relying on them. A lost reply can follow a committed
  action. Retry identical envelopes; stop/back off on connectivity failures.
  Do not reset identity, replace secrets or move authority to bypass rejection.
- Keep bounded buffers/receipts and payloads. Overflow must be visible and safe,
  not silent dropping of uncertain actions or deletion of replay protection.
  Inventory and provider reports enforce 64 KiB validated limits; capability
  state has <=256 channel entries, channel names <=160 characters. See C1/C2
  for detailed bounds. At the C4 checkpoint, generic command/event/result/state
  body byte limits were not uniformly enforced. [C7](PLATFORM_NEUTRAL_C7.md)
  now adds common finite JSON/body limits and the bounded module archive
  compatibility exception. Optional signed commands retain their tighter
  declared argument/TTL limits; this is not production certification.
- JSON/identity patterns and existing field maxima remain: command type <=100,
  idempotency key <=128, event type <=120, result error <=2000 characters.
  Credential and business secrets must not appear in inventory, metadata,
  events, results or diagnostic output. Secure at-rest storage and TLS are
  deployment requirements, not waived for embedded devices.

HTTP handling is endpoint-specific, not one generic retry policy:

- `204` command poll: no work. `202` event/inventory/heartbeat: accepted,
  not proof of an external effect. `200` command queue: queued, not executed.
- `401`: no valid device trust; stop protected work. `403`: wrong authority or
  identity/actor scope; never retry with a newly generated identity.
- `404`: missing resource (e.g. first provider GET); not implicit enrollment.
  `422`: invalid version/schema/payload, not a transient network failure.
- `409`: inspect the relevant conflict: provider revision/ownership, desired
  revision, different event identity content, unavailable capability or invalid
  command lifecycle. Do not blindly resubmit mutations under new keys.
- Enrollment may return `429` when its bounded request capacity is exhausted.
  Local timeout/lost replies require durable exact retry, not presumed failure.

Current command delivery lease is 30 seconds; it may redeliver the same command.
Polling long-wait is optional (`wait_seconds` 0–20); correctness cannot depend
on it. Core accepts a result only for its device/delivered command and preserves
the first terminal result. The completed time must precede the command expiry;
permanently rejected late results remain a recovery concern, not replay consent.

## 4. Changes and focused evidence

The generic event envelope was extracted from Core to
`three_mm_protocol.DeviceEventV1` and used by the independent client. Core's
`DeviceEventPayload` retains its existing component name, shape, mutable local
model behavior and specific identifier/passage payload validation. Authentication,
routes, status codes, event identity/deduplication and database schema are unchanged.
Legacy naive timestamps remain accepted where previously accepted; the stricter
new-client requirement is not falsely presented as legacy server enforcement.

`backend/tests/test_node_contract_conformance.py` checks all ten protected Node
boundary operations against missing/human credentials, another device's path
and revoked credentials. It also checks honest unsupported-operation results,
continued mandatory flows without modules, shared event shape, replay conflict
and retained known-event validation. Shared DTO tests cover round-trip, identity,
extra-field rejection and compatibility; C3 still exercises real loopback HTTP.

Focused Windows/Python 3.13 evidence:

- C4 + shared event + event/command/state + C3/reference checks: **31 passed
  in 9.40s**; dependency deprecation warnings only.
- Joined Linux role/schema baseline and existing shared model checks:
  **18 passed in 10.34s**. **49 passed overall** across the two focused gates.
- New/shared/reference files pass Black; task files pass whitespace checks.
  No frontend edits, live Pi operation, migration or optional-package changes.

Reproduce (repository root, PowerShell):

```powershell
$c4Tests = @(
  "backend/tests/test_node_contract_conformance.py"
  "three_mm_protocol/tests/test_device_event.py"
  "backend/tests/test_device_event_routes.py"
  "backend/tests/test_device_command_routes.py"
  "backend/tests/test_device_state_routes.py"
  "backend/tests/test_mock_embedded_protocol.py"
  "examples/mock_embedded/test_client.py"
  "backend/tests/test_node_protocol_baseline.py"
  "three_mm_protocol/tests/test_models.py"
)
.venv\Scripts\python.exe -m pytest -q @c4Tests
```

## 5. Explicit next-stage limitations

The following describes the C4 checkpoint. [C5](PLATFORM_NEUTRAL_C5.md) now
implements advertisement, negotiation and pre-dispatch checks for advertised
nodes; raw queue acceptance remains only the explicit legacy adapter. Its
updated conformance tests require unsupported optional work to be rejected
before queueing. The historical C4 test counts above are retained as evidence.

C5 must advertise actual optional support and preserve old Linux behavior,
without interpreting missing advertisements as full support for new runtimes.
Today the raw administrative command queue still accepts unsupported types.
In particular, do not send Linux `agent.update.apply` to a runtime lacking its
durable update operation contract: Core's existing Node Update safety gate
requires an independently validated terminal operation, not just a failure
acknowledgement. This workflow must be gated/negotiated, not bypassed.

C7 implements common bounds, command time/security checks and uncertainty handling;
C8 covers the complete mixed-version restore/rollback matrix. C9 still requires
deployed Standalone/Hub/Fleet and application -> independent node execution.
The C3 client currently rejects signed application execution; its availability
must not be presented as that optional feature being implemented. No ESP code
or hardware-specific Core contract was added.
