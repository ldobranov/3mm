# M20 — trusted context sources and invalidation design

Date: 2026-10-08. Status: **source audit and bounded design decision, local**.
This records the source/revision decision following the
[pure context validator](EXTENSION_PLATFORM_V2_CONTEXT_VALIDATOR.md). The design
itself does not implement a live resolver, grant store, approval endpoint or
enforcement. The subsequent local
[authority metadata slice](EXTENSION_PLATFORM_V2_AUTHORITY_METADATA.md) implements
the first migration and transaction helpers. The subsequent
[connector/credential writer slice](EXTENSION_PLATFORM_V2_AUTHORITY_WRITERS.md)
and [lifecycle writer slice](EXTENSION_PLATFORM_V2_LIFECYCLE_AUTHORITY.md) integrate
the identified management/lifecycle paths. [Explicit stopped/disabled recovery](EXTENSION_PLATFORM_V2_LIFECYCLE_RECOVERY.md)
and private helper fencing are now local. [Device pairing/credential/lifecycle, provider/runtime and Agent-module writers](EXTENSION_PLATFORM_V2_DEVICE_AUTHORITY_WRITERS.md)
also participate locally. [Offline restore/rollback/reset fences](EXTENSION_PLATFORM_V2_RECOVERY_FENCES.md)
and helper/recovery serialization are now local. The first
[read-only installed-source resolver](EXTENSION_PLATFORM_V2_SOURCE_RESOLVER.md)
now resolves persisted command/connector evidence with an explicit consistent
snapshot. A subsequent [private review-key store](EXTENSION_PLATFORM_V2_REVIEW_KEYS.md)
now implements explicit POSIX key lifecycle/HMAC primitives locally; production
key coordination/resolver composition, staged proposals, policy/evidence adapters
and live acceptance remain open. Neither can produce executable authority.

Scope: the common Core platform in Standalone and Hub, including local Agent and
provider-neutral devices. Fleet and application extensions are consumers, not
alternative authority stores. SDK 1.3 and normal workload contracts are retained;
the lifecycle slice documents its stricter unconfirmed-helper failure behavior.

## 1. Authoritative sources, not client snapshots

The future resolver accepts a Core-validated, digest-pinned application candidate
and a Core-owned staged configuration reference. A client may select whole scope
IDs; it cannot supply authoritative ownership, revisions, proof or allow sets.

| Context | Actual source | Gap / rule |
| --- | --- | --- |
| Core identity | `CoreInstallationIdentity` singleton in [identity model](../backend/db/installation_identity.py) | Read existing public identity columns only; absence blocks resolution |
| Logical application | `ApplicationExtensionInstallation` in [application models](../backend/db/module.py) | Existing row ID remains; incarnation/epoch, API lifecycle fences and explicit stopped/disabled recovery integrated locally; live recovery acceptance remains open |
| Installed artifact | Installation's `module_package_id` joined to `ModulePackage` | Cross-check module, version, active version and validated digest; never select catalog “latest” |
| Candidate artifact | [existing package validator](../backend/services/module_packages.py), exact bounded bytes | Descriptor/schema validity is not publisher trust, build identity or isolation proof |
| Effective configuration | Saved installation configuration and separately staged candidate configuration; [configuration validator](../backend/services/application_configuration.py) | No client-authored fingerprint; no silent replacement of saved/live values by candidate defaults |
| Device scope | Configuration-bound `Device`, credentials, `DevicePlatformState`, runtime features and [one capability registry](../backend/services/device_capability_registry.py) | Control generation persisted; pairing/credential/local bootstrap, lifecycle/release/preparation, provider/runtime, Agent-module writers and offline recovery fences integrated locally; live recovery acceptance remains pending |
| Connector scope | Actual owned `ApplicationConnectorBinding` | Canonical stored origin, enabled state and credential FK; revision persisted and admin binding writer integrated locally; effect admission still pending |
| Connector credential | Owned `ApplicationSecretReference`: reference, kind, version, revocation | Existing rotation version is reusable; never read/decrypt `encrypted_value` for review |
| Existing command fence | [ApplicationCommandEpoch](../backend/db/application_command.py) | Physical-command generation, not a general grant epoch or application incarnation |
| Policy / trust / isolation / UI proof | Future Core-owned policy and verified evidence adapters | No complete persistent source yet; missing/unsupported evidence remains a blocker |

Important source details:

- [application_instance_id](../three_mm_runtime/application_activation.py) is a
  deterministic hash of the module ID. It is a runtime locator, **not** proof of
  a new installation: uninstall/reinstall can produce the same value. An integer
  row ID is not an incarnation either.
- [installation_identity](../backend/services/installation_identity.py) calls
  `_load_or_create`, which can create/commit identity and decrypt its private key.
  [platform_snapshot](../backend/services/device_platform.py) can initialize
  device state as well. Neither is a read-only resolver dependency.
- Provider `revision` advances for both device declaration replacement and Core
  configuration/enable changes. Reuse it for that provider; it does not cover
  device credential changes, all Agent module transitions or installation restore.
- Connector `updated_at` changes with operational telemetry. Application timestamps,
  heartbeat times and desired/reported revisions are not authority revisions.

## 2. Resolver sequence and fail-closed behavior

1. Validate and pin bounded candidate bytes without executing code, building UI,
   calling helpers, reading extension data or accessing a network. Reuse the safe
   baseline reading rules in [inspection](../backend/services/application_authority_inspection.py).
2. Open a dedicated, explicitly consistent read transaction. Select needed columns
   with no autoflush; do not reuse stale ORM identity-map objects or a caller's
   pending writes. Reading must not lazily initialize any state.
3. Read existing Core identity, application incarnation/epoch/mode and actual
   package pointer. An inconsistent/unavailable baseline is not “new install”.
   A new install without a durable staged identity is unresolved: a future
   explicit prepare step must reserve it without starting the application.
4. Validate the Core-owned proposed configuration against the candidate schema.
   Activation currently merges candidate defaults, saved values and explicit
   device overrides. Preserve that behavior through an explicit staged proposal;
   defaults alone cannot establish a live device, connector or credential binding.
   Fingerprint the full resolved proposal privately, not only its visible fields.
5. Enumerate all authority-bearing declarations through the descriptor adapter.
   Resolve command target/sensor configuration keys to exact approved devices;
   require control authority and the configured, unambiguous capability/contract.
   Inventory-only offers never grant control. Include provider/runtime identity
   and contract changes in the target's control identity.
6. Resolve each connector by installation owner plus connector ID. Compare the
   configured canonical origin with the actual stored binding; follow its real
   credential FK and check owner/reference/kind/version/revocation. Missing,
   foreign, disabled or mismatched records block; do not auto-bind or rotate.
7. Resolve Core policy, publisher trust, runtime profile and isolation/UI evidence.
   Compute allowed whole scopes against the resolved resources, not manifest IDs
   alone. Unsupported authority families, peers, dependencies or executable UI
   without an accepted adapter remain explicit blockers, never silently omitted.
8. Construct the internal context and call the pure validator with explicit time.
   No partial context gets a reviewable fingerprint. Return bounded/redacted
   reasons, not configuration values, plaintext/ciphertext or private keys.
9. End the read transaction. This result is review evidence only. Approval/apply
   and effect admission must independently resolve and compare current state.

A read transaction must really be a consistent snapshot on the supported database;
plain sequential SELECTs under an ORM session are not sufficient proof. Artifact
validation may occur before it, but exact immutable identities are rechecked in
the snapshot and again at apply. No filesystem/network work while holding mutation
or effect-admission locks.

## 3. Durable ownership decisions

These are internal state decisions, not new public SDK/manifest fields:

- **Application incarnation:** attach an opaque, random, non-reused incarnation
  to the existing logical installation. Preserve it across ordinary restart,
  update, disable/enable and data-retaining lifecycle operations while the install
  exists. A completed uninstall followed by reinstall gets a new incarnation even
  when runtime locator, module ID, retained data or integer PK match.
- **Application authority epoch:** a separate random generation covering general
  service authority. Advance before lifecycle/configuration/grant transitions can
  admit new effects; returning A → B → A never restores the old epoch. Integrate
  with, do not replace, existing command-generation invalidation. Do not synthesize
  this epoch from package digest, status, a timestamp or job lease.
- **Connector authority revision:** add a dedicated non-reused generation to the
  binding, advanced for effective origin/credential/enable changes, deletion and
  recreation. An exact idempotent retry need not advance it. Operational results
  never change it. Resolve owner/incarnation as well as connector ID.
- **Secret version:** retain existing reference plus rotation version and revoked
  flag. Rotation/revocation must atomically advance the owner's general authority
  epoch. Creating an unused credential or renaming a label grants nothing and
  need not invalidate unrelated reviews. Never compare decrypted secret values.
- **Device control generation:** add internal Core-owned authority generation
  alongside existing device state, not a second device/capability registry and not
  a change to the published lifecycle revision semantics. Pair/rebind, credential
  replacement/revocation and authority release/recovery advance it. Combine it
  with the selected capability's provider/contract and runtime-feature revisions
  for `control_revision`; Agent-module transitions now participate locally. Same-ID
  resource A → B → A is not equivalent to uninterrupted authority.
- **Private configuration key:** a dedicated purpose-separated installation-local
  key and opaque key ID, owned by Core, not an application transport key, identity
  signing key or encryption master key. Keep protected writable state outside the
  immutable release; no key/configuration values in review or audit responses.
  Provision/rotate explicitly, never during inspection. Missing key blocks review.
  Key rotation invalidates pending reviews. Restore creates a fresh review key
  identity/fence; backed-up authority cannot reactivate itself.
- **Policy/evidence revisions:** Core-owned, immutable evidence references or
  monotonic/non-reused generations; package metadata cannot set them. Core adapter
  semantics changes have an explicit revision even if descriptor bytes do not.
  If no accepted source exists, the corresponding family remains unsupported.

The internal v1 validator provides evidence slots, not all these mechanisms. It
must not be wired with constants or fabricated “revision 1” values to fill gaps.
Final persisted plan identity/versioning, key storage/ACLs and restart-safe review
clock binding need implementation tests before an approval API can be enabled.

## 4. Writer and invalidation ledger

This ledger covers current production entry points affecting the bounded command/
connector context. This is an integration checklist, **not a completed fence**.
Connector/credential management and API lifecycle rows have local implementation evidence.
New writers must join it; direct SQL/helper writes are not exempt.

| Writer / source | Required future fence |
| --- | --- |
| `activate_application_extension` in [application routes](../backend/routes/application_extensions.py) | Implemented locally: guarded epoch/physical-command fence + start audit, helper outside locks, exact candidate/configuration/ticket CAS and terminal audit; unconfirmed outcome stays disabled for explicit recovery |
| `disable_application_extension`, `uninstall_application_extension` in same routes | Implemented locally: guarded pending/completion phases and audit; no old epoch/status restoration on helper failure; reinstall gets fresh incarnation; retain peer tombstones and refuse uninstall with outstanding job claims |
| `recover_application_extension` in same routes and [private helper fencing](../three_mm_runtime/application_lifecycle.py) | Implemented locally: explicit reviewed admin recovery to verified stopped/disabled state; fresh guard/incarnation/epoch ticket, serialized helper effects and durable one-use receipts; no activation/data rollback/job replay inferred |
| Future configuration-only edit or explicit grant apply/revoke | Same owner transaction advances epoch and relevant resource revision; approval of staged code alone does not change active grants |
| `bind_application_connector` in [connector service](../backend/services/application_connectors.py), via [operations route](../backend/routes/application_operations.py) | Implemented locally: package preparation outside lock, owner/package recheck, effective binding revision + owner epoch + guard revision + audit in one transaction; identical retry retains revisions |
| `rotate_secret_reference`, `revoke_application_secret` in [secret service](../backend/services/application_secrets.py) / operations route | Implemented locally: owned secret identity/version check, version/revocation + owner epoch + guard revision + audit in one transaction; repeated revoke retains identity; unused creation does not advance epoch |
| `approve_pairing_request`, pairing completion, `revoke_device_credential`, `issue_replacement_device_credential`, trusted `recover_device_credential` in [pairing service](../backend/services/device_pairing.py) / [local bootstrap](../deployment/local_agent_pairing.py) | Implemented locally: guard-first recheck, resource + fresh device control generation + guard revision + redacted audit in one transaction; same-ID re-enrollment preserves identity/history; local credential files saved after commit; no command replay or provider/desired-state reset |
| `report_lifecycle`, `release_authority`, `prepare_reenrollment` in [device platform](../backend/services/device_platform.py) | Implemented locally: guard-first current device/credential recheck, control generation + resource + existing lifecycle event committed atomically; reason-only diagnostics and exact lifecycle/release retries do not advance control identity; preserve public revision semantics and dispatched/uncertain evidence |
| `replace_provider`, `configure_provider`, `set_provider_enabled` in [registry](../backend/services/device_capability_registry.py) | Implemented locally: guard-first device/actual credential recheck; effective declarations/configuration/enable changes commit existing provider revision + fresh device control generation + guard revision + audit together; exact retries retain authority; withdrawal/re-enable cannot restore an old generation |
| `replace_runtime_features` in [runtime features](../backend/services/device_runtime_features.py) | Implemented locally: guarded effective declaration/support changes commit runtime revision + fresh device control generation + guard revision + existing Core event together; exact retry retains revisions; health/state telemetry remains separate |
| `install_module`, `disable_module` in [module routes](../backend/routes/modules.py), `record_command_result` and pre-dispatch module failures in [command service](../backend/services/device_commands.py) | Implemented locally: guard-first request/receipt/failure transactions with fresh control generation + guard revision + redacted audit; exact retries/superseded receipts cannot revive old installations; ZIP validation and notification outside the guard; no command replay |
| Policy/profile/trust/proof update; compiled executable UI identity change | Advance owning policy/evidence identity; until adapters exist, affected scope stays blocked, not downgraded to trusted native |
| Peer consent/revoke/rotation/reopen in [peer service](../backend/services/installation_peers.py) | Reuse peer generation/consent fences; peer authority remains blocked in this context slice until its adapter exists |
| [Application restore helper](../deployment/restore_application_extensions.py), [portable restore](../deployment/restore_backup.py), [immutable rollback](../deployment/install-systemd.sh), [peer recovery](../deployment/installation_peer_recovery.py) | Implemented locally: fresh guard/application/device/binding generations and physical quarantine before services start, including failed-restore/installer rollback; missing metadata fails closed; retained evidence is not automatically live authority; private review-key primitives reject recovered-generation mismatches, but their coordinator/audit integration remains pending |
| [Factory reset](../deployment/factory_reset.py), explicit Core identity/key replacement | Reset now fences its fresh migrated DB before activation, retaining existing key-removal/backup safety; local private review-key primitives do not yet wire provisioning/rotation into this coordinator |

Non-authority writes must not cause perpetual reapproval: heartbeat/inventory
refresh, capability state, unchanged health evidence, last-seen/last-used times,
connector attempt telemetry, job scheduling/claims and event cursors. Availability
can still block a dispatch without rewriting the permission grant. User/role/kiosk
changes remain independent live actor checks; a service grant never overrides them.

Actual declaration/contract changes in an inventory/provider path are not merely
telemetry. Likewise a lifecycle transition that withdraws control is authority
even if triggered by a device report. Classify the effective change, not the route
name. Preserve the existing registry and health/OTA/control checks at dispatch.

## 5. Concurrency and recovery integration

The existing `/run/lock/3mm-release-mutation.lock` coordinates release installer,
backup/restore/reset. It does **not** serialize ordinary connector, credential or
device API writers. The current command epoch/one-use permit is not that missing
general lock either.

For the first bounded implementation, prefer one internal Core authority mutation
guard over a premature fine-grained lock graph. It is a short database transaction
guard, not a new command queue. All participating authority writers, approval apply
and effect admissions acquire it **before** other mutable rows, then use one fixed
resource order and current-state CAS. Advance a guard revision on effective changes
for snapshot consistency checks. SQL no-op updates/conditional updates must be
tested across connections for SQLite and the supported SQL deployment path; an
in-process lock is insufficient. Existing paths that lock/commit earlier must be
adapted together before enforcement is advertised.

Read-only review does not take that write lock. It uses a genuine consistent
snapshot and records its revisions; mutating decisions re-resolve after acquiring
the guard. Approval must compare the **pre-apply baseline**, then create the new
epoch/grant state. Do not compare a plan with its own changed post-apply epoch.

Commit durable admission/evidence before connector network I/O or a one-use physical
permit leaves Core. Release general authority database locks before external effect I/O; keep immutable
admitted origin/credential-version/target evidence. Revocation winning before
admission denies it. Once admitted, revocation cannot promise to recall an external
POST or issued permit. Lost responses remain uncertain, never automatic replay.

The private lifecycle helper uses a separate file lock across runtime/systemd
mutation so recovery cannot overlap an admitted activation. Its short read-only
database snapshot closes before that runtime work. This is not a database write
guard held across an application POST. It now takes the shared release mutation
lock first, excluding restore/reset/installer rollback while helper work is admitted.

Restore continues under the existing release mutation lock with runtime services
quiesced. Its raw-SQL fences now rotate authority before restart, including rollback recovery;
normal restart preserves logical identity, credentials and active authority but
must invalidate or revalidate pending clock-bound reviews. Do not release unknown
job claims, rewind cursors or replay device/connector actions to “repair” a grant.

## 6. Bounded implementation and remaining gates

The [metadata delivery](EXTENSION_PLATFORM_V2_AUTHORITY_METADATA.md) now adds durable
incarnation/epoch/resource generations, the transaction guard and Alembic/migration
tests. Existing installations are backfilled into compatibility state, not
fabricated approved grants or proven isolation. It preserves existing data and
uncertain work; no enforced mode or new runtime authorization is enabled.

The [first writer slice](EXTENSION_PLATFORM_V2_AUTHORITY_WRITERS.md) now integrates
connector binding and credential management. The subsequent
[lifecycle slice](EXTENSION_PLATFORM_V2_LIFECYCLE_AUTHORITY.md) adds API lifecycle
fences, existing command invalidation and audit. [Explicit helper-outcome recovery](EXTENSION_PLATFORM_V2_LIFECYCLE_RECOVERY.md)
now reconciles to verified stopped/disabled state locally. The
[device writer slice](EXTENSION_PLATFORM_V2_DEVICE_AUTHORITY_WRITERS.md) adds
credential authority, trusted local bootstrap repair, lifecycle/release/preparation
and provider/runtime declaration/configuration/enable changes, plus Agent-module
requests, matching receipts and proven pre-dispatch failures.
Raw-SQL recovery integration is now local. Live Linux recovery and recovery UX
remain gates, alongside the explicit limitations in the recovery fence report.
The other ledger rows remain pending, not installed hooks. The first
[installed-source resolver](EXTENSION_PLATFORM_V2_SOURCE_RESOLVER.md) now verifies
command/connector sources in a dedicated read-only snapshot, including an actual
SQLite writer race. This is not the staged-candidate/full-context resolver.
The [private key store](EXTENSION_PLATFORM_V2_REVIEW_KEYS.md) now supplies unwired
local lifecycle/HMAC primitives, not a provisioning/audit or grant-management API.
Key coordination/composition, trusted policy/evidence adapters, live PostgreSQL
acceptance and issuer integration remain separate prerequisites.

A subsequent [pure policy evaluator](EXTENSION_PLATFORM_V2_POLICY_EVALUATOR.md)
now fixes exact trusted-input binding/rule comparison and preserves unsupported
proof gates locally. It does not authenticate its supplied evidence, create a
policy store or clear the installed resolver's `policy_evidence_unavailable`
blocker. Protected policy/native-provenance sources and guarded decision/audit/
invalidation remain the next implementation gate, not synthetic default inputs.

Required integration tests before wiring the resolver/issuer (the metadata report
distinguishes the passing primitive/migration subset from these remaining gates):

- Existing-data migration and repeat startup preserve identity, data and command/
  job/event evidence; uninstall/reinstall cannot reuse incarnation.
- A → B → A, same-ID rebind, credential rotate/revoke, provider withdrawal and
  restore/rollback cannot resurrect old review identity; exact retries stay safe.
- Actual metadata resolution is read-only, secret-safe and independent of ORM
  cache/pending writes; missing identity/key/evidence/configuration blocks.
- Two connections/processes race writer versus review/apply/admission; stale plans
  fail, no lock is held across I/O and already-admitted effects are not replayed.
- Normal restart, backward clock movement, expired plans and recovered/foreign
  decisions cannot bypass fresh apply validation; active workloads retain the
  explicitly accepted compatibility behavior.

The original design delivery used source inspection, Markdown target and whitespace
checks only. Subsequent metadata code/schema changes and their local test evidence
are recorded separately; neither delivery claims live security or recovery acceptance.
