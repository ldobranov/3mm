# C3 — Independent mock embedded node

Implemented locally 2026-10-03 on C0/C1/C2. Device protocol is `1.0`, inventory
schema `2`, provider report schema `1`; Application SDK remains `1.3`.
No deployment, release, commit or push. No Child Center changes in this stage.

## Scope and boundary

`examples/mock_embedded` is a separate reference runtime, not a Linux Agent
module. Its implementation imports only standard libraries, requests and
shared protocol contracts. It does not import Core, Agent module runtime,
Fleet or hardware drivers. The legacy-named shared `fleet_pairing` file supplies
enrollment DTOs only; enrollment itself is a common Core API, not a Fleet API.

The client reports an embedded/mock-embedded platform without Linux values.
It registers firmware provider `3mm-embedded-test` and capability
`gpio.digital.control` directly, without a ModulePackage/ModuleInstallation.
The supported action is `set_output`, channel `gpio.output.1`, boolean `value`.
This is the same invocation contract used by the Linux module in the mixed test.
The output is **SQLite simulation, not a physical pin**.

No Core production behavior, endpoint, database model or migration was added
for C3. Standalone and Hub use the same device layer; Fleet is not required.
Mock platform names and the concrete capability belong to the reference client,
not to Core domain conditionals.

## Durable behavior and failure boundaries

- A unique device identity, credential and enrollment token are generated once
  in a private local SQLite file. Only the credential hash is enrolled. The
  node waits for explicit administrator approval and authenticates normal traffic
  with the existing device credential; revocation does not trigger re-enrollment.
- State is bound to an explicit Core origin. Restart cannot silently move the
  identity to another server. Redirects and environment proxy inheritance are
  disabled; normal requests TLS verification remains enabled.
- Simulation effect, receipt, event, state and result are committed together.
  Exact redelivery returns the original result without repeating the action;
  changed content/key/command identity is rejected. Expired, unsupported,
  disabled-provider or invalid-argument commands perform no mock action.
- Events/results are retained until acknowledged. Lost acknowledgements retry
  identical content. Latest state/reported-state entries are coalesced. Outbox
  limit: 128 entries, 64 KiB per entry; receipts: 1024. Overflow fails closed,
  with no automatic receipt eviction or silent loss of pending work.
- Desired state is persisted and reported as a **mock configuration shadow**,
  not claimed as real GPIO/driver configuration. Inventory and heartbeat are
  regenerated on reconnect; they are not accumulated in the outbox.
- Provider revision is read/retried through C2. Core-owned disable remains
  authoritative and cannot be overwritten by a device report.

The SQLite atomic-effect technique is valid only for simulated state. Real
physical effects require a dispatch/uncertainty journal, not this transaction.
Stopped or permanently rejected outbox data is retained for inspection, not
discarded; this reference client does not implement a production recovery UI.

## Run locally against an updated Core

Use a Core checkout with **C1/C2 and the provider migration applied**, not the
currently published beta. From the repository root, using its existing Python
environment:

```powershell
.venv\Scripts\python.exe -m examples.mock_embedded --core-url http://127.0.0.1:8887 --data-dir .runtime/mock-embedded-a
```

Use the actual Core **API origin**, not the frontend origin/proxy path. The
client prints the device ID and waits in `pending_approval`. An administrator
approves its existing pairing request through:

1. `GET /api/v1/pairing/requests` using normal administrator authentication.
2. `POST /api/v1/pairing/requests/{request_id}/approve` for this device.

The mock node needs no administrator password/token. Never add its SQLite
file or credentials to Git; `.runtime/` and `*.sqlite3` are already ignored.
Use a different private directory per node, retain it across restarts, and stop
with Ctrl+C. `--once` runs one cycle; `--interval` accepts 1–60 seconds, default 5.
Plain HTTP here is a local test, not a production transport/security claim.
POSIX file modes are restricted; Windows ACL/secure embedded storage remain
platform deployment responsibilities, not proved by this Windows reference.

An administrator can inspect the same device/detail, registry-v2, commands,
events and capability-state APIs used for Linux. Invoke for this device:

```json
{
  "capability_id": "gpio.digital.control",
  "action": "set_output",
  "arguments": {"channel": "gpio.output.1", "value": true}
}
```

Send to `POST /api/v1/devices/{device_id}/capabilities/invoke` with normal
administrator authentication; this queues a command, not an execution claim.
Wait for the reported command result and capability state.

## Focused evidence

Windows/Python 3.13, 2026-10-03:

- C3 unit/integration tests: **14 cases**. Independent enrollment, approval,
  inventory, heartbeat, firmware registration, command execution/result/state,
  event, lost acknowledgement, disconnect, durable restart and duplicate lease
  delivery all pass. Same identity/credential/provider survive reconnect.
- A default-transport test uses **real loopback HTTP sockets** through requests
  and Uvicorn/Core, without injected transport or Agent imports in the client.
- Mixed Linux Agent publisher/module runtime + independent embedded node pass
  on one Core for both `standalone` and `hub` Linux device roles. Same capability,
  action and arguments; one real Linux module installation, none for embedded.
  The test Core loads common routers only, no Fleet extension.
- C0 now runs 12 role/schema/hardware combinations; C1 ingestion tests run
  Standalone/Hub/Node roles. These are common-contract role tests, not a claim
  that separate systemd deployment topologies were exercised.
- C0/C1/C3 focused gate: **70 passed in 20.35s**. C2 migration/provider/application
  and existing enrollment/Agent journal gate: **57 passed in 14.58s**.
  **127 passed overall**; dependency deprecation warnings, no failures.
- CLI help and Black checks pass. No frontend edits in this stage, so prior
  frontend checks are not rerun. No live Raspberry mutation or network change.

Reproduce the focused gates (repository root, PowerShell):

```powershell
$protocolTests = @(
  "examples/mock_embedded/test_client.py"
  "backend/tests/test_mock_embedded_protocol.py"
  "backend/tests/test_node_protocol_baseline.py"
  "backend/tests/test_platform_inventory.py"
  "agent/tests/test_inventory_versions.py"
  "three_mm_protocol/tests/test_device_inventory.py"
)
.venv\Scripts\python.exe -m pytest -q @protocolTests
$compatibilityTests = @(
  "backend/tests/test_device_capability_providers.py"
  "backend/tests/test_device_capability_provider_migration.py"
  "backend/tests/test_application_command_providers.py"
  "backend/tests/test_node_enrollment.py"
  "agent/tests/test_core_client.py"
  "agent/tests/test_physical_command_journal.py"
  "three_mm_protocol/tests/test_device_capabilities.py"
)
.venv\Scripts\python.exe -m pytest -q @compatibilityTests
```

## Later stages and remaining deployed acceptance

C3 is local architectural proof, not firmware readiness. Mandatory conformance,
optional feature advertisement/negotiation, production TLS/storage/ingress limits,
power-loss tests, deployed Fleet adoption and full migration/restore acceptance
remain separate stages. C4–C8 now provide the shared contracts, negotiation,
hardening and local migration/recovery evidence. [C9](PLATFORM_NEUTRAL_C9.md)
adds the independent client's optional application execution permit contract and
local signed application -> Linux/embedded acceptance. Module installation,
Linux OTA and actual firmware OTA are still unsupported by this client.
No ESP, GPIO driver, provisioning or board profile implementation is started.
