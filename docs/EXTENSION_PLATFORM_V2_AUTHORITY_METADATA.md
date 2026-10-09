# M20 — inactive authority metadata foundation

Date: 2026-10-08. Status: **implemented and tested locally, not runtime enforcement**.
This is the first persistence/transaction slice of the
[trusted resolver design](EXTENSION_PLATFORM_V2_RESOLVER_DESIGN.md), within
[WP4](../EXTENSION_PLATFORM_V2_CORE_PLAN.md#wp4--public-platform-api-sdk-and-authorization).
It is common Core infrastructure, not Fleet-specific. SDK 1.3, public contracts
and current application/device authorization behavior remain unchanged.
Subsequent [connector/credential writer integration](EXTENSION_PLATFORM_V2_AUTHORITY_WRITERS.md)
uses these primitives locally. Later [lifecycle recovery](EXTENSION_PLATFORM_V2_LIFECYCLE_RECOVERY.md)
and [device pairing writers](EXTENSION_PLATFORM_V2_DEVICE_AUTHORITY_WRITERS.md)
also participate; the remaining writer ledger is still incomplete.
The evidence below records the initial metadata delivery.

## Persisted metadata

| Owner | New internal metadata | Purpose |
| --- | --- | --- |
| Core singleton | `core_authority_guard.generation`, `revision` | Database transaction guard and change counter, not a grant or command queue |
| Application installation | `authority_incarnation`, `authority_epoch`, `authority_mode` | Distinguish reinstall from restart/update; identify later authority changes |
| Connector binding | `authority_revision` | Non-reused binding generation, separate from attempt timestamps |
| Existing device platform state | `control_generation` | Internal control identity without changing public lifecycle revision semantics |

Generations are independent random 128-bit lowercase hexadecimal values.
The guard revision is bounded to `1..2**53-1`. Application mode starts as
`compatibility`; the schema also reserves `review_required`. There is no
`enforced` mode, approved grant store or mode-changing endpoint in this slice.
The new fields alone do not establish permission, publisher trust or isolation.

ORM creation gives a recreated application a fresh incarnation even if its
integer primary key, module ID and deterministic runtime locator are reused.
Existing installations retain their backfilled incarnation across normal writes.
Subsequent lifecycle writers now advance the general epoch; see their delivery reports.

## Migration and compatibility

[Migration `b8c017c8d9e0`](../backend/alembic/versions/b8c017c8d9e0_authority_metadata.py)
follows `a7bf06b7c8d9`. It backfills existing rows in bounded batches and seeds
the singleton without creating approved grants. Existing applications stay in
compatibility mode. The device-pairing slice extends this still-unreleased migration
to materialize missing legacy-default device platform rows (`bound`, `active`,
revision 0) once, before assigning control generations. This matches the previous
lazy default; existing released/revoked/recovery rows and credential revocation
semantics are not overwritten. Runtime authority readers/writers never repair a
missing existing row. Newly approved devices create their row explicitly.

The populated-database test compares every pre-existing column before and after
upgrade/downgrade, including installation/configuration, connector credentials,
device credentials, desired state, unknown commands/jobs, leases and event cursor
evidence. Identity, module installations and public lifecycle revisions are not
reassigned. Additive legacy-default rows remain on unused downgrade rather than
being destructively removed. Repeating an already-applied upgrade preserves the
new generations. This migration has not been released; a deployed migration
would require a new successor revision rather than editing its backfill.

The historical baseline's post-baseline table exclusion list now includes the
guard table. This prevents today's model registration from creating it too early
during a clean migration. The new migration also tolerates a guard table already
created by legacy `create_all`, initializing only an absent singleton and
preserving an existing generation/revision. Other migration history is unchanged.

Downgrade removes unused metadata only while guard revision is still 1 and all
application modes remain compatibility. Once participating writes have advanced
the guard, or review-required state exists, downgrade refuses before schema
changes and requires a verified pre-upgrade recovery path. This is not permission
to erase used authority history manually.

## Internal read and mutation contracts

[Metadata helpers](../backend/services/authority_metadata.py) expose immutable
snapshots of existing rows through explicit-column SELECTs with no autoflush.
They do not read configuration, encrypted secret values or private keys, initialize
missing rows, decrypt, perform I/O or rely on cached ORM object values. Connector
lookup joins the actual owner; missing/foreign/stale state fails with one redacted
error. Missing device platform state is unavailable, not invented authority.

`authority_transaction` owns begin/commit/rollback on a clean dedicated Session.
Its first write locks the singleton before mutable resources, optionally comparing
the expected guard identity/revision. Inside that short scope, helpers can:

- Advance an application's epoch with owner/incarnation/epoch/mode comparison.
- Advance a connector revision and its owner's epoch atomically.
- Advance device control generation with device identity comparison.
- Advance the guard revision in the same transaction for each metadata mutation.

Failed compare-and-swap poisons the scope: catching the error inside it does not
permit partial commit. Resource writes made in the same Session roll back too.
The mutation object is invalid after scope exit. Callers must not manually commit,
roll back, open savepoints or perform filesystem/network I/O inside the scope.
The helper is an internal trusted transaction primitive, not an authorization API.

At initial delivery, production writers still used their previous transaction
boundaries. The subsequent writer slice owns connector/credential changes and
audit together. The metadata primitives themselves do not write configuration, rotate credentials,
record audit, invalidate `ApplicationCommandEpoch`, admit effects or issue permits.
Read helpers alone do not implement the complete consistent-snapshot resolver.

## Evidence and limits

Initial targeted verification: **130 passed**, 23 warnings. This includes 25 new metadata/
migration cases, clean migration to head/back to base, existing Device Platform
migration checks, application commands/connectors and pure authority-context tests.

New checks cover populated migration, guarded downgrade, precreated singleton,
reinstall identity, stale/foreign snapshots, caught-error rollback, real connector
write rollback, missing state, revision overflow and SELECT-only secret-safe reads.
Two real SQLite connections prove guard serialization for commit and rollback.
SQLite/PostgreSQL guard SQL compiles; no live PostgreSQL concurrency test was run.
All migration databases are disposable test files, not development/live databases.

No complete writer ledger, live resolver, approval API/UI, grant issuer, private
configuration HMAC key, publisher/isolation proof or effect enforcement is enabled.
Raw backup/restore of these rows is not a fresh authority proof. Restore/rollback
now receive [fresh metadata fences before restart](EXTENSION_PLATFORM_V2_RECOVERY_FENCES.md),
including failed recovery and installer rollback. Private review-key lifecycle
remains a separate prerequisite before a future issuer is enabled.
No live deployment acceptance is claimed.

## Next bounded step

Connector binding/credential writers, application lifecycle/recovery and device
pairing/credential writers are covered by subsequent slices.
Device lifecycle/provider/runtime, Agent-module writers and raw-SQL recovery
fences are covered by subsequent local slices. Next: consistent read-only resolver
and explicit private-key provisioning, without fabricated policy/isolation
evidence. Approval/apply and effect admission remain gated independently.
