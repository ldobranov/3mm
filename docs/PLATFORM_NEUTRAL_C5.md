# C5 — Runtime feature advertisement and negotiation

Implemented locally on 2026-10-03. This is the common Device/Node Platform:
Standalone, Hub/Fleet, local Agent and application extensions share the same
device records, trust, command queue and support query. No Fleet dependency or
concrete hardware/extension branching. Transport remains `1.0`, HTTP `/api/v1`,
Application SDK `1.3`; no re-pairing, deployment or release.

## Separate contracts

Runtime features describe which protocol workflows a node implements.
Application capabilities describe what it does. Neither is an authorization
grant, and advertising a runtime feature does **not** register a capability.

Examples: `module_lifecycle` is a runtime feature; `gpio.digital.control` is an
application capability. A firmware provider needs no module installation.
Generic firmware `ota` does not imply Linux `agent.update.apply` support.
Unknown bounded feature/command identifiers are allowed for future generic
contracts; actual hardware actions should continue through `capability.invoke`.

Shared schemas live in `three_mm_protocol/node_features.py`. The mandatory
feature set is `inventory`, `heartbeat`, `commands`, `events`,
`capability_invocation`, `capability_state`, `desired_reported_state`.
Capabilities may still be empty; nodes must not invent observations or events.
`capability.invoke` is the mandatory dispatch envelope, not a GPIO grant.

Optional contracts already implemented by the Linux runtime:

| Feature | Supported command types |
| --- | --- |
| `module_lifecycle` | `module.install`, `module.disable` |
| `local_automations` | `automation.apply`, `automation.remove` |
| `gpio_configuration` | `agent.gpio.configure` |
| `inventory_refresh` | `agent.refresh_inventory` |
| `release_update_prepare` | `agent.update.prepare` |
| `release_update_apply` | `agent.update.apply` |
| `application_execution_permits` | `application.capability.invoke` |

Known features and their command sets must agree. Duplicate declarations,
unsupported schema/protocol versions, oversized identifiers/lists/reports and
invalid revisions are rejected: <=64 features, <=64 commands, identifiers
<=100 characters, validated report <=16 KiB, bounded non-boolean integer revision.
No credential belongs in these reports.

## Common Core API

Here `D` means `/api/v1/devices/{device_id}`.

- Device-authenticated `GET D/protocol` returns supported inventory schemas
  `[1,2]`, feature schema `[1]`, capability registry views `[1,2]`, provider
  report schema `[1]`, and current feature revision. Path identity is bound to
  the authenticated device. This is schema negotiation, not a new transport.
- Device-authenticated `PUT D/runtime-features` replaces the device's declaration
  with runtime name/version, features, command types and `expected_revision`.
  Path and body must both belong to the credential. Initial revision is zero;
  changes increment it. Identical current/exact lost-response retries are
  idempotent; changed stale reports return `409`, requiring a fresh read.
- Administrator `GET D/runtime-features` exposes source, revision, declaration
  and receipt time. Missing/human/cross-device/revoked credentials cannot write;
  ordinary users cannot read the administrative diagnostic.

There is one `device_runtime_features` row per device. Migration
`748cd3e4f5a6` follows `637bc2d3e4f5`, adds only this table/index, and is reversible.
The legacy metadata baseline excludes it so clean migration does not create it
twice. No device identity, credential, module/provider, desired state or SDK
data is rewritten. Changed declarations produce `runtime.features.updated`
device audit events; unchanged retries do not duplicate the audit.

The diagnostic source is either `advertised` or `legacy_unadvertised`. Missing
legacy support is **unknown**, not a fabricated list of all supported features.
There is no route to delete an advertisement back to unknown.

## Queue, execution and compatibility

For advertised nodes, the shared queue rejects unsupported new command types
with `409`. All existing actor, capability, binding, expiry and OTA checks still
apply. An identical existing request can still return its original command;
this is a receipt lookup, not permission for a new action.

Support is rechecked under the same device writer lock before first dispatch.
Withdrawn queued work with no delivery/attempts becomes Core-side failed
`execution_state=not_dispatched`; module lifecycle status is updated as failed.
Already delivered commands retain their lease/result/uncertainty contract.
Withdrawal is not proof that a previously delivered external effect failed.
Signed application execution rechecks optional permit support before consuming
the existing one-time permit. A registered GPIO capability alone is insufficient.

A Node Update rejected before any dispatch cannot have started and need not
hold the mutation gate. A failed/expired/lost acknowledgement **after delivery**
still cannot release that gate without the independently validated terminal
operation report. No automatic replay or new physical authorization is introduced.

Old nodes without advertisements keep legacy queue behavior and all previous
authorization checks. This explicit compatibility adapter is not certification
of old-node support. Updated independent runtimes must negotiate before their
normal publication/poll flow; they cannot substitute fake Linux values for an
unsupported inventory schema.

## Runtime adoption

The production Linux Agent enables negotiation when constructing its publisher.
It advertises optional features from actual runtime components. Signed release
apply is advertised only with positive, identity-bound update-helper support;
prepare and apply are distinct. A direct library `CorePublisher` constructor
retains its opt-in compatibility switch for legacy embeddings/test adapters.

The Agent negotiates before inventory/command polling. It preserves configured
inventory schema 1 by default; configured schema 2 is sent only when supported.
Only a missing legacy negotiation endpoint (`404`/`405`) permits fallback to
schema 1. Authentication, transport, malformed response, identity mismatch or
server failures are not silently downgraded. Requests do not follow redirects.
Component support is reconsidered at most every 30 seconds, with a periodic
Core exchange every five minutes or upon a changed declaration, avoiding extra
requests for every heartbeat/command. Restart negotiates again without rekeying.

The independent `examples.mock_embedded` client negotiates the common schemas
and advertises mandatory features plus `capability.invoke` before its normal
tick. It uses only shared contracts, not Agent runtime code. Unsupported Linux
workflows are now rejected by Core before reaching it. Its direct dispatcher
still rejects malformed/unsupported commands without effects as a second boundary.
At C5 it did not implement signed application execution. [C9](PLATFORM_NEUTRAL_C9.md)
adds optional `application_execution_permits` / `application.capability.invoke`
with the existing authorization contract. Actual firmware OTA remains outside scope.

## Evidence and remaining scope

Focused checks cover the new schemas, revision/retry/audit semantics, own-device
authentication/revocation, ordinary-user denial, no capability grants, support
withdrawal before/after dispatch, OTA uncertainty, signed execution permits,
Agent compatibility/errors/cache/component advertisement, Linux role/schema
baseline, mock coexistence/real loopback HTTP, additive/clean migrations and
SQLite backup preservation. Windows/Python 3.13 focused evidence:

- New feature schemas/Core plus mock/conformance: **26 passed in 10.28s**.
- Agent negotiation, Linux baseline, migration/backup, provider broker and
  existing Node Update/queue rules: **62 passed in 39.14s**.
- Existing Agent publisher, command routes, Node Update delivery, application
  commands and direct mock dispatch: **41 passed in 9.87s**.
- **129 passed** across the three targeted gates, with existing dependency
  deprecation/test-key warnings only. New files pass Black; task whitespace
  checks pass. No frontend build was needed because C5 changes no frontend.

Reproduce from the repository root with `.venv\Scripts\python.exe -m pytest -q`
and these file groups:

1. `three_mm_protocol/tests/test_node_features.py`,
   `backend/tests/test_device_runtime_features.py`,
   `backend/tests/test_mock_embedded_protocol.py`,
   `backend/tests/test_node_contract_conformance.py`.
2. `agent/tests/test_runtime_features.py`,
   `backend/tests/test_node_protocol_baseline.py`,
   `backend/tests/test_device_runtime_feature_migration.py`,
   `backend/tests/test_device_capability_provider_migration.py`,
   `backend/tests/test_migration_history.py::test_clean_database_migrates_to_head_and_back_to_base`,
   `backend/tests/test_application_command_providers.py`,
   `backend/tests/test_node_update_approval.py`,
   `backend/tests/test_device_commands.py`.
3. `agent/tests/test_core_client.py`, `backend/tests/test_device_command_routes.py`,
   `backend/tests/test_node_update_delivery_route.py`,
   `backend/tests/test_application_commands.py`, `examples/mock_embedded/test_client.py`.

No frontend, ESP firmware, board profiles, separate Fleet package, deploy or
release was changed for C5. Separate consumers can adopt the administrator
diagnostic/query, but missing consumer adoption does not create another registry.
[C6](PLATFORM_NEUTRAL_C6.md) now defines the firmware/extension boundary and
[C7](PLATFORM_NEUTRAL_C7.md) implements common security hardening.
[C8](PLATFORM_NEUTRAL_C8.md) now verifies migrations and mixed-version recovery;
C9 now verifies local runtime/application acceptance; deployed Hub/Zero/Fleet
acceptance remains pending.
