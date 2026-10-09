# M20 — device pairing, lifecycle, provider/runtime and Agent-module authority writers

Date: 2026-10-08. Status: implemented locally, bounded writer integration.
Common Core for Standalone/local Agent, Hub and provider-neutral nodes; not
Fleet-only. No SDK/protocol version bump, new grant, resolver or effect admission.

## Scope

The existing [pairing service](../backend/services/device_pairing.py) and
[HTTP routes](../backend/routes/device_pairing.py) retain public request/response
contracts and administrator authorization. They now commit the effective resource
change, fresh internal device control generation, guard revision and redacted
audit/event together:

- Approve legacy pairing: create the approved device and its platform state;
  completion separately issues the one-time credential and advances again.
- Approve automatic enrollment: accept the device's persisted credential verifier
  in the approval transaction. Core never receives its plaintext secret.
- Same-ID re-enrollment: require the existing explicit released/prepared state;
  retain the device PK/stable ID and history, with a fresh control generation.
- Credential replacement: issue a new credential and advance authority. Preserve
  the existing API behavior: this endpoint does not revoke all other credentials.
- Revoke the selected owned credential: revoke and advance together. Foreign or
  already-revoked credentials keep their previous not-found behavior and do not
  advance metadata. Consumed/expired pairing cannot complete a second time.
- Trusted co-located bootstrap repair: re-read eligibility under the guard,
  revoke previous credentials and issue/audit a replacement atomically. Revoked
  or released devices cannot silently regain authority; explicit administrator
  preparation is required. This is not a new remote recovery endpoint.

Normal replacement/revocation does not change the published lifecycle revision.
Re-enrollment retains its existing lifecycle revision semantics. Provider/module
registrations, desired/reported state and command history are not reset or replayed.
An uncertain command remains uncertain.

## Transaction and persistence boundary

The internal commit-owning boundary ends only a known read-only AUTOBEGIN auth/
preflight transaction. Pending ORM writes, explicit transactions and savepoints
are rejected without discarding them. It is not an adapter for arbitrary callers
with previously flushed SQL writes. All mutable decisions are loaded again after
the singleton lock, rather than using an earlier ORM cache. Device locks follow
the guard and precede pairing/credential mutation, matching the device-first order
of existing recovery writers. Control generation uses the existing identity-bound
CAS primitive.

Missing guard or existing device metadata fails closed. Audit failure rolls back
the credential, pairing reservation, control generation and guard revision.
Audit/events contain selected IDs/provenance, never pairing tokens, credential
secrets or verifiers. No filesystem/network work occurs under this write guard.

The [local bootstrap](../deployment/local_agent_pairing.py) saves the returned
credential and authority pin after the database commit. Filesystem and database
are not one atomic transaction; a lost file still uses the existing explicit
repair/revocation rules, never rollback to an old control generation. Normal
already-paired startup does not issue a credential or advance the guard.

The still-unreleased [metadata migration](../backend/alembic/versions/b8c017c8d9e0_authority_metadata.py)
now fills missing legacy-default platform rows once at upgrade. Existing rows,
credentials, identities, module installations, desired state and uncertain work
are preserved. Metadata readers and participating writers do not recreate missing
existing authority. The legacy `platform_snapshot` still has its historical lazy
initialization behavior and is not a read-only resolver dependency. An
unused downgrade retains additive default rows; a used guard still refuses
silent downgrade. This is not permission to edit an already-deployed migration.

## Verification

Focused tests cover public pairing and admin-only mutations, local pin/revocation
recovery, real Linux/mock embedded contracts, legacy migration, control CAS,
redaction, foreign credentials, pending transaction rejection and injected audit
failure for all five authority writers. Two real SQLite connections race duplicate
completion: the guard is the first write, the waiter cannot issue another key,
and only the successful completion advances authority. Bootstrap file writes are
checked against an independently visible committed credential/audit/guard.

Targeted runs (some suites overlap):

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_device_pairing.py backend/tests/test_device_pairing_routes.py backend/tests/test_node_enrollment.py backend/tests/test_local_agent_pairing.py backend/tests/test_local_agent_authority.py backend/tests/test_device_transport.py backend/tests/test_device_platform.py -q --disable-warnings --tb=short
# 36 passed, 44 warnings, 11.52s

.venv/Scripts/python.exe -m pytest backend/tests/test_device_pairing_authority.py backend/tests/test_authority_metadata_migration.py backend/tests/test_authority_metadata.py -q --disable-warnings --tb=short
# 39 passed, 38 warnings, 88.10s (before adding the bootstrap file-boundary test)

.venv/Scripts/python.exe -m pytest backend/tests/test_device_pairing_authority.py backend/tests/test_device_pairing_routes.py backend/tests/test_node_protocol_baseline.py backend/tests/test_mock_embedded_protocol.py backend/tests/test_node_contract_conformance.py -q --disable-warnings --tb=short
# 41 passed, 120 warnings, 57.34s (includes the bootstrap file-boundary test)

.venv/Scripts/python.exe -m pytest backend/tests/test_device_pairing_routes.py -q --disable-warnings --tb=short
# 10 passed, 20 warnings, 4.28s (added replacement/revocation auth and missing-guard HTTP conflicts)

.venv/Scripts/python.exe -m pytest backend/tests/test_device_pairing_authority.py backend/tests/test_device_pairing.py backend/tests/test_device_pairing_routes.py backend/tests/test_local_agent_authority.py backend/tests/test_device_platform.py -q --disable-warnings --tb=short
# 44 passed, 73 warnings, 42.26s (final device-before-pairing mutation order)
```

No full release suite, frontend build, live database/device mutation or deployment
is included. The new writer race uses SQLite, not live PostgreSQL; existing
metadata tests compile both supported SQL dialects without claiming a PostgreSQL
locking proof.

## Device lifecycle writer follow-up

The existing `report_lifecycle`, `release_authority` and `prepare_reenrollment`
now join the same guard-first metadata transaction as pairing/credential writers.
Public routes, payloads and lifecycle revision rules remain unchanged. The internal
report service additionally requires the authenticated credential ID, passed from
the already-validated HTTP header; it is not client-authored authority evidence.

- Re-read the actual device/credential/state after locking the guard, then the
  device. A credential revoked after HTTP authentication cannot report lifecycle,
  even if a different credential on that device is still active.
- Lifecycle state changes receive fresh control generations. Exact same-state/
  reason retries retain both revisions and emit no duplicate event. Reason-only
  diagnostics retain the existing public revision/event behavior without advancing
  the internal control generation or guard revision. A -> B -> A does not restore
  an old control generation.
- Release advances control generation together with credential revocation, the
  existing lifecycle event and failure of provably never-dispatched commands.
  Delivered, unknown and queued-but-attempted actions retain their evidence;
  nothing is replayed. An accepted release retry does not advance again.
- Explicit enrollment preparation advances control identity and retains old
  pairing approvals as history while freeing their automatic enrollment index.
  It grants no credential or control. Its existing public revision/precondition
  behavior is retained, not replaced by a new retry policy.
- Missing guard/platform metadata fails closed without repair. Metadata errors
  retain the signed-management adapter's redacted HTTP 503 behavior; public
  revision conflicts retain their existing HTTP 409 behavior.
- Existing device lifecycle `DeviceEvent` audit, resource writes and internal
  generations commit together. Event insertion failure rolls all of them back.

Identity initialization/decryption and configuration loading remain outside the
short device authority transaction. Pending ORM work, explicit transactions and
savepoints are rejected before that initializer can commit. A known read-only
AUTOBEGIN preflight is ended; this is not a generic adapter for previously flushed
SQL writes. The response DTO is built after flush within the guard, with no key
decryption, configuration/file access, helper call or network I/O under that lock.
As before, initial installation identity creation is a separate preflight commit,
not part of the device mutation. This does not coordinate restore/reset yet.

Focused follow-up evidence covers actual two-connection release-versus-report
serialization, credential revocation between HTTP authentication and the writer,
missing metadata, stale revisions/foreign confirmation, A -> B -> A, exact retry,
reason-only diagnostics, pending caller transaction rejection, history preservation
and injected audit failure for all three writers. The guard is the first write of
each raced device authority transaction. PostgreSQL/live-device acceptance remains
open; no new schema, SDK, resolver, grant or effect-admission API is introduced.

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_device_lifecycle_authority.py backend/tests/test_device_platform.py backend/tests/test_device_pairing_routes.py backend/tests/test_local_agent_authority.py -q --disable-warnings --tb=short
# 33 passed, 65 warnings, 38.05s
```

Python compilation and whitespace checks passed. No full release suite, frontend
build, commit/push/release or live deployment was performed for this follow-up.

## Provider/runtime writer follow-up

The existing `replace_provider`, `configure_provider`, `set_provider_enabled` and
`replace_runtime_features` now use the short DB-only
[device authority boundary](../backend/services/device_authority.py). It locks the
singleton before the device, reloads current ownership/lifecycle/control metadata
and serializes the resource decision. These services now own the commit; internal
callers must finish fixture/setup mutations before entry. A known read-only
AUTOBEGIN preflight can be ended, not arbitrary previously flushed SQL writes.
Pending ORM work, explicit transactions and savepoints are rejected, not discarded.
Private implementations require the owning live metadata transaction as well.

- Effective provider declarations/version/withdrawal, Core-selected offers,
  enabled state and runtime declarations advance a fresh device control
  generation and guard revision. A -> B -> A never restores prior authority.
  Existing provider/runtime revisions and public lifecycle revision semantics
  remain unchanged; this does not create a second capability registry.
- Device adapters pass the exact credential ID from the already-authenticated
  request, and the writer checks it again under the guard. A different active
  key on the same device cannot authorize a request authenticated with a revoked
  key. `DeviceOperations` rejects missing principal information for these reports.
  Authentication rejections retain HTTP 401, not revision-conflict HTTP 409.
- Exact no-op/lost-response retries keep their existing semantics and do not
  advance metadata or duplicate events. Core-owned selected offers/disable state
  cannot be overwritten by a new device report. Existing conflict/quota checks,
  dispatch health/OTA checks and module compatibility adapter remain intact.
- Missing guard or platform/control metadata fails closed without initialization
  or repair. Resource revision, relevant stale-state deletion, control generation,
  guard revision and existing redacted audit/event commit or roll back together.
  No file/key/helper/network I/O occurs inside this guard.
- Health reports remain separate evidence: they may block dispatch but cannot
  register an unselected offer, change a grant or advance control authority.
  Heartbeat, inventory, desired/reported state and uncertain command evidence are
  not reset or replayed by these writers.

The focused [provider authority tests](../backend/tests/test_device_provider_authority.py)
cover all four writers' audit-failure rollback, missing metadata and caller
transaction rejection, declaration/configuration/enable/runtime A -> B -> A,
withdrawal/retry, telemetry separation and exact-key revocation after real HTTP
authentication. Two real SQLite connections race a report with stale administrator
control: the guard is each transaction's first write, the waiter rechecks the
committed provider revision, and only the successful change advances authority.
This is not live PostgreSQL or effect-admission proof.

Existing test fixtures explicitly seed control metadata where they manually create
approved devices instead of using pairing. Historical backup fixtures insert their
actual historical table shape, rather than invoking today's guarded service on
an old schema. No production fallback or new schema migration is added here.

Final targeted runs:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_device_provider_authority.py backend/tests/test_capability_availability.py backend/tests/test_device_runtime_features.py backend/tests/test_device_transport.py -q --disable-warnings --tb=short
# 40 passed, 30 warnings, 79.14s

.venv/Scripts/python.exe -m pytest backend/tests/test_capability_contracts.py backend/tests/test_node_security.py -q --disable-warnings --tb=short
# 30 passed, 27 warnings, 16.21s

.venv/Scripts/python.exe -m pytest backend/tests/test_device_capability_provider_migration.py backend/tests/test_node_recovery_compatibility.py 'backend/tests/test_node_update_approval.py::test_pending_physical_or_configuration_work_blocks_ota[application.capability.invoke]' backend/tests/test_node_update_approval.py::test_ota_gate_blocks_new_device_mutations_but_not_replay_and_releases_after_terminal -q --disable-warnings --tb=short
# 10 passed, 9 warnings, 66.69s
```

The HTTP revocation test caught and corrected a broad `ValueError` translation
which converted runtime authentication rejection to conflict; the final runs above
include the corrected HTTP 401 behavior. Python compilation, local documentation
links and whitespace checks also passed.
No frontend changes/build, full release suite, live mutation, commit/push/release
or deployment is included.

## Agent-module writer follow-up

The existing install/disable endpoints, matching Agent command results and Core's
proven pre-dispatch module rejection now participate in the same device authority
transaction. No new wire fields, schema migration, SDK, module runtime or registry
is introduced. The module compatibility adapter remains the one source for Agent
capabilities in the common Standalone/Hub device layer.

- Validate and encode immutable ZIP bytes outside the guard, pin their digest/
  module/version and device architecture/protocol, then re-read those identities
  inside the transaction. Changed/unreadable bytes fail before queueing. Pending
  caller ORM work is rejected before preflight queries can autoflush it.
- Effective install/disable requests commit command + current installation +
  fresh control generation + guard revision + redacted admin/device audit together.
  Agent notification follows commit, never a rejected/rolled-back request. Exact
  client/legacy retries return the current installation without rewinding its
  episode, generating another command or advancing authority. An orphaned replay
  fails for explicit recovery rather than recreating old authority.
- Command results and installation confirmation are no longer two separate
  commits. Match both device and the installation's current command ID; an old
  receipt may finish its own command but cannot overwrite a newer episode. A
  terminal retry uses the stored original receipt, not conflicting retry output.
  The former two-commit gap can be reconciled once from that receipt under the
  guard. Returning to the same module/version never restores an old generation.
- `DeviceOperations.command_result` requires the actual authenticated credential
  ID. The HTTP adapter passes it from the already-validated header; the writer
  rechecks that exact key under the guard, even when another key is active. Other
  trusted internal service calls may omit it. Authentication rejection stays 401.
- Core refusal of never-dispatched module work commits failure evidence and the
  installation/control/audit change atomically. Invalid stored commands retain
  their existing conflict response after evidence commits. Already-delivered work
  keeps its lease, uncertainty and original evidence; no new replay is introduced.
- Poll delivery and result recording acquire the guard before device/command
  locks, including polls with no work, because they may reject a module command.
  Normal dispatch, ordinary receipts, expiry and no-work polls do not advance
  authority by themselves. Existing expiry semantics are retained. Long-poll
  waiting is outside the DB transaction. This is writer integration, not a claim
  that the future general effect-admission/physical-permit boundary is complete.
- Missing guard/control metadata fails without repair. Audit insertion failure
  rolls back the command, installation and generations together. The reserved
  `device.module.lifecycle.updated` event contains IDs, state and provenance, not
  package bytes, result output or error text; devices cannot forge it.

Focused tests exercise request/result retries, the existing capability adapter,
late/superseded receipts, the historical two-commit gap, missing metadata, pending/
explicit/nested caller transactions, exact-key revocation after HTTP authentication,
ZIP preflight drift, audit rollback and a real two-connection duplicate install.
The guard is both racers' first write and only one command/authority change wins.
Independent-connection visibility verifies notification occurs after commit.
Linux Agent baseline, mock embedded protocol and existing command/OTA checks also
run locally. This is not live Linux/PostgreSQL locking or recovery acceptance.

Final targeted runs for this follow-up (154 passing cases, not the release suite):

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_device_module_authority.py backend/tests/test_module_lifecycle_idempotency.py backend/tests/test_device_commands.py -q --disable-warnings --tb=short
# 52 passed, 51 warnings, 105.76s (before the additional reserved-event test below)

.venv/Scripts/python.exe -m pytest backend/tests/test_application_commands.py backend/tests/test_device_platform.py backend/tests/test_capability_contracts.py backend/tests/test_node_update_approval.py -q --disable-warnings --tb=short
# 61 passed, 77 warnings, 34.88s

.venv/Scripts/python.exe -m pytest backend/tests/test_node_protocol_baseline.py backend/tests/test_mock_embedded_protocol.py backend/tests/test_node_security.py backend/tests/test_device_runtime_features.py backend/tests/test_device_transport.py backend/tests/test_device_module_authority.py::test_device_cannot_forge_module_authority_audit -q --disable-warnings --tb=short
# 41 passed, 80 warnings, 28.11s
```

Python compilation, local documentation links and whitespace checks passed.
No frontend changes/build, full release suite, live mutation, commit/push/release
or deployment is included.

## Remaining gates

[Fresh offline recovery fences](EXTENSION_PLATFORM_V2_RECOVERY_FENCES.md) now cover
portable restore, failed-restore/installer rollback and reset before restart,
with shared helper/recovery serialization. Existing nonparticipating
writers are not claimed to share a completed authority lock model. The consistent
read-only resolver, private review key, approval/apply, effect admission, isolation
and live Linux/PostgreSQL acceptance remain separate work. The current slice alone
does not make old backed-up approvals trustworthy or recall dispatched effects.
