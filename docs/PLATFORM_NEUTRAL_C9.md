# C9 — Common runtime and application acceptance

Verified locally 2026-10-03 on C0–C8. Shared Device/Node Platform, **not
Fleet-only**. Protocol `1.0`, HTTP `/api/v1`, Application SDK `1.3` unchanged.
No production Core behavior, endpoint, migration, deployment, commit, push or
release changed for this stage. Child Center work remains untouched.

## Implemented

The independent `examples.mock_embedded` reference runtime is now `0.2.0`.
It advertises `application_execution_permits` with
`application.capability.invoke`, in addition to its mandatory contracts.
This is runtime support, not a capability registration or permission grant.

Before requesting Core's existing single-use execution permit, the client
commits a content-bound uncertain receipt. It requires a matching command ID,
`authorized=true`, an acknowledgement within two seconds, and an unexpired
deadline immediately before the simulated effect. Application commands have
at most ten seconds of lifetime, matching the current application contract.
No signed command is downgraded into an unsigned invocation.

A denied, lost, malformed, wrong-identity or late permit causes no simulated
effect. A restart after an unfinished attempt returns `unknown` without another
permit/action. Once completed, redelivery returns the durable original receipt.
Simulation effect, final receipt, state/event and result outbox commit together;
overflow rolls back these changes, retaining the earlier uncertain intent.
Pending work is not silently evicted. This is SQLite simulation, **not** an
exactly-once guarantee for physical GPIO.

## Joined evidence

The existing common-Core test now runs both implementations simultaneously:

| Scenario | Locally verified path |
| --- | --- |
| Standalone/local Linux Agent + embedded node | Real Core routers/auth/SQLite; Linux publisher/module runtime and independent firmware-provider client, no Fleet extension |
| Hub-role Linux Agent + embedded node | Same registry, device credentials, negotiation, queue/results and capability state; no second device subsystem |
| Application binding -> either provider | Same validated SDK 1.3 application package, declarative binding/action/arguments and signed platform request; only the bound device ID differs |

The application path exercises the real platform server's signed framing,
signature verification, dispatch and broker, followed by existing
device-authenticated HTTP delivery/permit/result/state APIs. Invalid installation
signatures queue nothing. Both providers execute the same command and report
the same state. Duplicate application requests return the existing command;
duplicate device execution does not repeat the effect/consume another permit.
Disabling the application after dispatch denies execution. Losing the permit
acknowledgement after Core consumes it performs no action or automatic retry.

Core/app bindings contain no provider selection or hardware conditional.
Only Linux needs a real module installation; the firmware provider does not.
Existing provider tests also cover a native provider using the same broker.
Existing ordinary transport tests retain identity/credentials/provider on
reconnect, acknowledged outbox retries, events and desired/reported state.

Focused final gate: **55 passed in 26.76s** on Windows/Python 3.13. Includes the
12-case C0 Linux role/schema baseline, C4 conformance, provider-neutral application
broker, C5 queue/permit support, C8 legacy adapter/recovery-conflict regression,
physical-journal safety, and operator permission grant/revocation regression.
An expired-command fixture was corrected to have a valid historical lifetime
under C7's stricter envelope validation; expiry protection was not weakened.
Black passes. Existing dependency/test-key warnings remain. No frontend changes,
so no frontend rebuild is needed for C9.

Reproduce from the repository root, PowerShell:

```powershell
$tests = @(
  "examples/mock_embedded/test_client.py"
  "backend/tests/test_mock_embedded_protocol.py"
  "backend/tests/test_node_protocol_baseline.py"
  "backend/tests/test_node_contract_conformance.py"
  "backend/tests/test_application_command_providers.py"
  "backend/tests/test_device_runtime_features.py"
  "backend/tests/test_node_compatibility.py"
  "agent/tests/test_physical_command_journal.py"
  "backend/tests/test_application_access.py::test_operator_permission_is_server_enforced_and_revocable"
)
.venv\Scripts\python.exe -m pytest -q @tests
```

## Remaining acceptance gate — do not call this firmware readiness

Tests simulate hardware and installation transport connections. The platform
handler receives signed framed messages through a test connection, not a live
Unix socket/application service process. A separate existing test does use real
loopback HTTP sockets for the independent device protocol. Role tests are not
separate deployed Standalone/Hub systemd installations.

After explicit deployment approval, verify the updated Core/Agent on Hub and
Zero without re-pairing or changing identity/credentials/module installations;
connect a separate mock client and inspect/invoke both providers through the
actual Fleet/application consumers. Check firmware-provider inventory/state
presentation without fake module IDs. Any separately maintained Fleet UI adoption
belongs to that extension, not a parallel Core registry.

Real Linux private storage modes, deployed transport/HTTPS and physical
power-loss/timing tests remain deployment responsibilities. No real ESP firmware,
provisioning, GPIO, OTA, board profiles or embedded extension has been built.
Local architecture acceptance is complete; the full deployed C9 gate is pending.
Only after that gate should the separate Embedded Runtime / ESP32 MVP start.
