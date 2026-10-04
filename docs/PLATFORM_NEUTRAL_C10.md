# C10 — Device transport boundary

Local implementation: 2026-10-03. Device protocol remains `1.0`, inventory
schema remains `1`/`2`, Application SDK remains `1.3`. No database migration,
HTTP endpoint rename, hardware support or new network transport.

## Boundaries

- `three_mm_protocol/transport.py`: typed logical `DeviceTransport` port,
  protocol rejection and unconfirmed-delivery errors. No HTTP dependencies.
- `backend/services/device_protocol.py`: common authentication, enrollment,
  heartbeat/inventory, feature/provider reports, command delivery/results/permits,
  events, capability state and desired/reported state. Existing registry, queue,
  application permissions and persistence remain authoritative.
- `backend/routes/device_*.py`, `backend/utils/device_protocol_http.py` and
  `device_auth.py`: reference HTTP boundary. Paths, header parsing, status/error
  translation, bounded long-poll notification and background event dispatch stay
  here. Event dispatch still uses the existing application processor.
- `agent/device_transport.py`: HTTP client adapter and legacy disk-message codec.
  Agent publisher/feature negotiation accept an injected logical transport.
  Redirects are not acknowledgements; enrollment responses bind both identities.

Logical flow: protocol object -> adapter -> common authenticated Core operation.
Core does not branch on a transport or hardware family. A new adapter authenticates
each operation using the common credential validator, translates errors and owns
connection/notification scheduling. It must schedule accepted events through the
existing application processor; persistence alone is not application delivery.

## Compatibility and safety

Existing HTTP URLs, payloads, statuses, unique credentials, administrator approval,
revocation checks, desired state, module command results and provider rules remain.
Optional Linux update transport/provisioning discovery are still adapter concerns,
not mandatory firmware behavior. No MQTT broker or WebSocket server is introduced.

The old suffix/payload outbox format is retained for rollback releases. A codec
validates persisted records into protocol objects before sending through any
adapter; malformed evidence is retained, not dropped. Command journals and event
IDs preserve duplicate handling. A lost delivery response after Core commit is
not evidence of failed execution and must not cause physical replay.

## Evidence and limits

`backend/tests/test_device_transport.py` uses protocol objects, normal enrollment
approval, real SQLite models and the SAME Core services while HTTP calls are
forbidden. It covers inventory, heartbeat, firmware capability registration,
state/events, desired/reported state, capability invocation/results, lost reply,
duplicate delivery, reconnect, identity mismatch and credential revocation. A Linux
publisher uses this adapter with negotiation and its persistent outbox/journal.
An architectural guard excludes HTTP imports/paths from the port/common operations.

Existing HTTP route, Linux Agent and independent mock-embedded tests provide
reference-transport regression coverage; Node update/GPIO tests retain the optional
runtime boundary. Installer tests use fake services/interfaces, never host mutations.

Final focused run: **169 passed, 1 skipped** (Windows cannot prove POSIX file
access modes). This covers the affected device/Agent/installer paths, not the full
project suite. `git diff --check` passes. No frontend files changed or rebuild needed.

This is local architectural proof, not production non-HTTP delivery, live process
rollback or deployed Hub/Zero/Fleet acceptance. The C9 deployment gate remains
open. C11 contract versions, C12 reassignment, C13 lifecycle and C14 three-level
availability are planned separately and are not claimed complete by C10.
