# M20 — read-only installed authority sources

Date: 2026-10-08. Status: **implemented locally, bounded internal foundation**.
This follows the [source/revision design](EXTENSION_PLATFORM_V2_RESOLVER_DESIGN.md)
and [recovery fences](EXTENSION_PLATFORM_V2_RECOVERY_FENCES.md). It is common Core
infrastructure for Standalone/local Agent and Hub/provider-neutral devices, not
Fleet-only. No public route, UI, SDK change, activation hook or enforcement.

## What is resolved

[resolve_installed_authority_sources](../backend/services/application_authority_sources.py)
accepts a trusted Core Engine, an existing installation ID and Core-owned package
storage/version settings. It accepts **no caller configuration, policy, ownership,
revision, credential value, candidate model or authoritative client snapshot**.

1. Select the actual installation/package pointer, not catalog latest. Only a
   coherent active/enabled or disabled/not-enabled installation is supported.
   Missing, transitional or inconsistent state is unavailable, never a new install.
2. Close the preflight transaction. Read the digest-named ZIP through the existing
   bounded/no-follow inspection reader and validate its exact bytes, module,
   version and descriptor. Ignore the catalog's arbitrary `file_path`. No build,
   extraction, service/migration execution, network call or filesystem write.
3. Open the final consistent read snapshot and recheck the exact package pin.
   Read the existing guard, incarnation/epoch/mode, public Core identity and
   **saved** configuration. Validate it without merging manifest defaults into
   missing live values. Never initialize missing metadata or identity.
4. For command bindings, resolve exact configured target/sensor IDs, approved
   device/control metadata, active credential IDs and advertised runtime support.
   Use the existing **single effective capability registry** and its module
   adapter: unselected offers/conflicts/disabled providers are not capabilities.
   Pin the selected provider/version, declaration revision or immutable module
   package digest, and exact action/contract version/digest. Require explicit
   contract/permit support here; existing legacy runtime dispatch is unchanged.
5. For connectors, follow the owned installation/connector binding and its real
   credential FK. Compare canonical configured/stored origin, enabled state,
   binding generation, credential owner/reference/kind/version/revocation.
   Authentication `none` cannot inherit an attached credential. Unsupported path
   syntax fails before returning any resources.

The final result contains immutable/redacted source evidence and closed reason
codes, not configuration or arbitrary resource payloads. Explicit secret/identity/
device-credential column selections exclude `encrypted_value`,
`encrypted_private_key` and `secret_hash`. Nothing is decrypted. The existing
bounded JSON checker also caps the returned evidence. Any failed source lookup
returns no partial resource set and no raw database/archive/validation error.

## Snapshot boundary

The resolver owns dedicated connections/Sessions, never a caller's Session or
cached ORM state. It cannot flush, commit or discard that caller's pending work.

- SQLite: ordinary existing file-backed Engine only; reject in-memory/shared
  pools, custom URI and `read_uncommitted` configurations. Explicit database
  `BEGIN` precedes SELECT, rather than relying on legacy driver's implicit
  transaction behavior. `query_only=ON` rejects writes within the snapshot.
  Roll back/close and restore the connection's prior setting before pool reuse;
  invalidate the connection if cleanup fails. An absent database path is rejected
  before connecting. Deployment must keep the managed DB file stable/quiesced
  during restore; this adapter is not a filesystem-replacement lock.
- PostgreSQL: request `REPEATABLE READ` plus dialect `postgresql_readonly=True`
  before beginning. Only the dialect API wiring is tested locally, **not live
  PostgreSQL isolation/concurrency acceptance**.

No mutation guard is taken for these reads. Artifact I/O is outside both
transactions. With SQLite WAL, an independent authority writer can commit while
the reader retains one coherent old guard/resource snapshot. The next resolution
sees its new guard, application/device/binding generations and credential version.
This is snapshot consistency, **not stale-plan rejection or effect admission**.
No guarantee is made that evidence remains current after the snapshot closes.

## Deliberate remaining blockers

`sources_resolved` refers only to `installed_command_connector_sources`, not all
manifest authority or a completed trusted candidate resolver. Every result has:

- `reviewable: false`, `context_fingerprint: null`,
  `permission_approval: not_evaluated`.
- No invented approved grant revision, policy/trust/profile/isolation proof,
  configuration HMAC/key identity, clock or authorization token.
- Explicit missing configuration-key/policy-evidence/staged-candidate gates.
  No proposed candidate/new-install reservation or durable staged configuration
  exists in this slice. A saved installation is not that proposal.
- Explicit schema-containment and sensor-contract gates when applicable. Checking
  action/version does not prove all proposed arguments fit the provider schema,
  or that a sensor ID is available and suitable for passage evidence.
- Explicit unsupported event/job/public HTTP/platform/provided-capability,
  peer, dependency and executable frontend authority blockers when declared.
  Policy/runtime/storage/actor evidence still needs accepted adapters; no silent
  promotion to reviewed-native or proven-isolated execution.
- Unchecked live health/online/OTA gates, current actor/approved grants,
  restart-safe review clock and effect admission. Those remain independent live
  checks; this read-only source helper does not change them.

The source result is deliberately **not** passed to the pure context validator.
Its missing mandatory evidence cannot be replaced by constants to mint a
reviewable fingerprint. Subsequent [private review-key primitives](EXTENSION_PLATFORM_V2_REVIEW_KEYS.md)
are local but deliberately unwired in this source-only helper. The separate
[installed-subject composer](EXTENSION_PLATFORM_V2_POLICY_SUBJECTS.md), added
2026-10-09, can use the actual existing key and full saved configuration in this
same DB snapshot. It also compares each binding with the selected action's exact
validated argument schema. Only that bounded exact-equality case can clear the
schema placeholder; containment and sensor contracts remain unsupported. The
source-only result stays unchanged and cannot itself authorize anything.
Key coordination and trusted policy/evidence adapters remain prerequisites;
staged proposals, approval/audit/apply and effect enforcement remain separate
deliveries. No key blocker is cleared merely by importing that helper.

## Verification

[Focused tests](../backend/tests/test_application_authority_sources.py) use actual
disposable file-backed SQLite tables and real validated ZIP bytes. They cover:
stable/disabled/missing installations, exact artifact drift, corrupted/symlink
archives, missing/invalid metadata/public identity, saved configuration versus
defaults, credential revocation/foreign ownership/kind/reference, unsafe origins/
paths, unauthenticated connectors, sensor non-inference, unselected/conflicting
capabilities and all three runtime roles across native/firmware/module providers.

SQL tracing verifies read-only operations and exclusion of encrypted/verifier
columns; caller pending/cache state stays untouched. A real two-connection WAL
race commits resource/generation changes between final guard and resource reads:
the reader returns the complete old evidence, then a fresh call returns the new
evidence. A failed write inside the read snapshot cannot change state or leave
the pooled connection unwritable. PostgreSQL is a wiring double only.

Local runs (overlapping, not the full release suite):

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_application_authority_sources.py backend/tests/test_application_authority_context.py backend/tests/test_application_authority_inspection.py backend/tests/test_authority_metadata.py -q --disable-warnings
# 164 passed, 1 skipped (Linux FIFO), 81 warnings, 17.34s
# Before the final additional disabled/default/sensor/connector/missing-DB cases.

.venv/Scripts/python.exe -m pytest backend/tests/test_application_authority_sources.py -q --disable-warnings
# Final: 49 passed, 5 warnings, 15.54s.
```

Python compilation, scoped whitespace and local Markdown target checks passed.

No schema migration, frontend change/build, full release suite, live installation
mutation, commit/push, release or deployment is included. This is not completion
of WP4/WP5 or production-security acceptance.
