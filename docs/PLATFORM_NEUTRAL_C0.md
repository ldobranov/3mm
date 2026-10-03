# C0 — Existing Linux Agent / Core baseline

Date: 2026-10-02. Base: `5cc0edf`, source version `0.3.0-beta.32`.
Peer v2 and Application SDK 1.3 are retained byte-for-byte from that commit.
The temporary local reversal was cancelled; no Git history/tag was rewritten.

Scope: behavior before C1/C2, not embedded support. Production device contracts,
authentication, database schemas, Agent runtime and deployment are unchanged.
No Child Center files, live installation or electrical operations are modified.

This is the shared Core Device/Node Platform baseline, not Fleet-only work.
Standalone/local Agent and Hub/remote Nodes use the same contracts. Fleet is
an optional consumer; it is not loaded by the joined test application.

## Joined architectural regression

`backend/tests/test_node_protocol_baseline.py` runs the existing Python Agent
publisher/module runtime against real in-process Core HTTP routers and SQLite.
It uses two deterministic hardware profiles: Raspberry-like ARM64 and generic
Linux x86_64. The 2026-10-03 scope extension runs both inventory schemas for
all three device roles (`standalone`, `hub`, `node`), not only Nodes. It tests:

1. Stable identity -> pairing claim -> explicit approval -> private credential storage.
2. Actual Agent inventory publication and authenticated heartbeat -> online registry.
3. A module.install command -> actual package activation -> result -> registered capability.
4. capability.invoke -> driver action -> command result -> capability state read.
5. Desired revision -> Agent reconciliation -> synchronized reported state.
6. Device event and capability state buffered during simulated disconnection.
7. Reload identity/credential/journals, restore active module and drain outbox.
8. Replayed event remains a single record; no duplicate device or re-pairing.
9. Credential revocation blocks subsequent authenticated device traffic.

This freezes externally observable behavior, not the current Linux inventory
field layout or module-specific registry implementation. Tests may use a
compatibility publishing mode during C1, but their authenticated behavior and
identity/state guarantees must stay true.

## Existing negative and lower-level coverage

| Contract | Existing tests |
| --- | --- |
| Pairing, expiry, replay, approval, durable enrollment | test_device_pairing, test_device_pairing_routes, test_node_enrollment |
| Authenticated inventory/heartbeat and identity mismatch | test_device_ingest_routes |
| Latest inventory, online/offline, administrator visibility | test_device_registry_routes |
| Enabled capabilities, unknown capability rejection | test_device_capability_routes, test_device_capability_state_routes |
| State snapshots and monotonic observation | test_device_capability_state_routes, protocol test_capability_state |
| Event replay and validation | test_device_event_routes |
| Queued/delivered/result, expiry, idempotency and long poll | test_device_commands, test_device_command_routes |
| Desired revision conflicts, UTC and reported state | test_device_state_routes, joined baseline |
| Durable identity/credentials, journals/outbox and independent command loop | Agent test_identity, test_core_client |
| Module registration, disable, rollback and restart | Agent test_module_runtime |
| Physical at-most-one attempt, crash/unknown and expiry | Agent test_physical_command_journal |
| Shared protocol shapes and validation | protocol test_models |

## Reproduce the focused C0 gate

Run from the repository root in PowerShell; choose the existing development
virtualenv rather than installing another environment:

```powershell
$c0Tests = @(
    "backend/tests/test_node_protocol_baseline.py"
    "backend/tests/test_device_pairing.py"
    "backend/tests/test_device_pairing_routes.py"
    "backend/tests/test_node_enrollment.py"
    "backend/tests/test_device_ingest_routes.py"
    "backend/tests/test_device_registry_routes.py"
    "backend/tests/test_device_capability_routes.py"
    "backend/tests/test_device_capability_state_routes.py"
    "backend/tests/test_device_event_routes.py"
    "backend/tests/test_device_commands.py"
    "backend/tests/test_device_command_routes.py"
    "backend/tests/test_device_state_routes.py"
    "agent/tests/test_identity.py"
    "agent/tests/test_inventory.py"
    "agent/tests/test_core_client.py"
    "agent/tests/test_module_runtime.py"
    "agent/tests/test_physical_command_journal.py"
    "three_mm_protocol/tests/test_models.py"
    "three_mm_protocol/tests/test_capability_state.py"
)
.venv\Scripts\python.exe -m pytest -q @c0Tests
```

On Linux use the equivalent Python interpreter and the same paths. These tests
do not require a live Pi, cloud, GPIO driver installation or network mutation.

## Evidence and limitations

The combined focused gate passed on Windows/Python 3.13: **87 tests in 12.50s**,
including both original joined scenarios. This is historical C0 evidence,
not the count of the subsequently expanded role/schema matrix. C0 is complete
as the local regression baseline before C1. Existing dependency warnings are unchanged. Black passed
for the new test and `git diff --check` passed for this task's files.

Hardware and HTTP sockets are simulated; this is not independent real-Linux,
systemd, power-loss, TLS, Unix permission or electrical timing acceptance. C1/C2
must keep this gate green, and C7/C8/C9 need their own security, migration,
mixed-version and Linux + independent embedded client evidence.

The role matrix verifies common protocol behavior, not a deployed installation
topology. C3 additionally joins a real Linux Agent publisher/module runtime and
an independent mock embedded client on one Core without Fleet; C9 still owns
the full Standalone/Hub/application acceptance matrix and live-system proof.
The expanded matrix passes with C1/C2/C3; current focused results and commands
are recorded in [C3 evidence](PLATFORM_NEUTRAL_C3.md).
