# WP4 — boot preservation before database lifecycle work, 2026-10-14

Status: bounded source-level safety fence, not prepared-database upgrade,
portable restore/rekey acceptance, a release or WP4 closure.

## Why this precedes upgrade/restore

A prepared database has protected lineage metadata as well as application data.
An enabled prepared application also has `boot-required.json` and
`boot-authority.json`, bound to its exact start, lifecycle, transport key,
principal and reviewed authority. Changing lineage while leaving those records
behind would split database and boot state. A grant/epoch refusal on a later
startup does not make that earlier partial lifecycle change coherent.

The initial preparation and published-candidate recovery helpers did not
previously check for this boot evidence. The latter can create a fresh database
lineage, but it has no authority to silently discard or rewrite boot consent.

## Implemented boundary

Both metadata-only/business-migration initial preparation and published-candidate
recovery now call the common metadata-only `require_no_boot_gate` fence while
holding their existing Root release/runtime mutation locks, after validating
protected parent paths and before Core checkpoints, SQL, snapshots or stopping
the service.

Either fixed boot filename is sufficient to refuse the operation. Partial,
malformed, directory and dangling-link evidence are not treated as absence.
The check does not follow a dangling link, parse an arbitrary package field or
invent an extension-specific rule. The database, key, active/lifecycle records
and original boot evidence are retained. No new rollback marker is manufactured
for this preflight refusal.

The existing separately authorized exact-source stop/reconciliation path owns
verified stop + disable and recoverable boot-evidence archiving. This new check
does not grant that authority, call `systemctl`, perform an archive/delete, renew
a used ticket or automatically reapply permissions. An issued Core recovery
ticket may already have fenced its old epoch; a Root refusal does not roll back
that security fence or mark the recovery completed. Inspect evidence before a
separately authorized next action.

There is no new route, SDK version, database model/Alembic change or generic
relational activation bypass. Reviewed-native code remains cooperative, not a
security sandbox.

## Verification

The new regression cases cover preparation with both ticket classes and both
boot filenames, including dangling links, and candidate recovery with required,
policy-only, paired, dangling-link and directory evidence, plus structurally valid
signed pending/confirmed Root boot publications. They assert refusal
before any helper Core checkpoint/service action, unchanged data/key/metadata,
retained original evidence and a still-recorded recovery/preparation action.
Normal no-boot preparation/migration/recovery remains covered by the surrounding
positive tests, including lost acknowledgements and retained preimages.

Linux tests run in a private mount namespace with a private `/tmp`; they do not
use the installed fixture, production database, transport key or M21 checkout.
The controlled live beta.49 instance and its accepted boot state are unchanged.

Final targeted Linux verification:

- **171 passed**: complete preparation, migration, candidate recovery,
  interrupted-recovery confirmation and SQLite snapshot suites. This includes
  the initial 13 new refusal cases; that separate 13-case run is not added again.
- **38 passed**: normal relational denial gates and SDK wire, two additional
  valid pending/confirmed boot refusal cases, and actual healthy-process initial
  and repeated boot-enable regressions. These do not overlap the 171-case run.
- Total: **209 distinct cases passed**, including **15 new boot-fence cases**.
  This is targeted verification, not full release or live upgrade acceptance.

The standalone Windows SDK wire suite passed **23 cases with 1 expected shared
Linux-clock skip**. An earlier mixed Windows run had 25 passed, 1 skip and 8
failures during unsupported POSIX private-file setup, before these new helpers.
Those same normal-runtime gate scenarios passed on Linux in the 38-case run;
no Windows skip/bypass or production fallback was added to hide those failures.
Existing dependency/datetime/test-key warnings were not suppressed or addressed
as unrelated work. Black, isort, whitespace/link checks and frontend build passed.

## Next database lifecycle contract

Prepared-database upgrade remains a separate operation, never a second invocation
of initial preparation or accept-candidate recovery. Its coordinator must pin
the old lifecycle/schema/artifact and exact reviewed candidate, verify quiescence
and separately reconciled boot state, retain a coherent database/files/metadata
preimage, and run only bounded non-root forward migrations. Publication must
coordinate new lineage/current authority with preserved historical evidence;
uncertain worker stop or finish acknowledgement must retain evidence without
replaying migrations or automatically restarting/regranting the application.

The subsequent [private forward-upgrade foundation](EXTENSION_PLATFORM_V2_RELATIONAL_UPGRADE.md)
now implements the internal consent/worker/preimage/publication boundary with
isolated tests. It is not a public upgrade command or live acceptance. Upgrade
checkpoint recovery/dispatch, portable restore, key rotation/nonempty recovery
and broader Standalone/Hub acceptance remain separate gates.

See [accepted controlled VM restart/boot trial](EXTENSION_PLATFORM_V2_RELATIONAL_VM_TRIAL.md),
[fixture procedure](../modules/wp4-relational-test/README.md) and
[relational storage contract](EXTENSION_PLATFORM_V2_RELATIONAL_STORAGE_CONTRACT.md).
