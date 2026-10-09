# M20 — offline restore, rollback and reset authority fences

Date: 2026-10-08. Status: implemented locally, bounded metadata/recovery slice.
Common Standalone/Hub Core; SDK 1.3 and public protocols are unchanged. This is
not a grant store, approval API, private review key or effect-enforcement release.

## Recovery boundary

[Offline fencing](../deployment/authority_recovery.py) opens an existing SQLite
database in `mode=rw`, never creates one, and owns one short `BEGIN IMMEDIATE`
transaction. Its first row write locks the existing singleton, matching online
writers. It validates all existing authority metadata and device platform rows;
missing, partial, invalid or unknown-mode current metadata fails without repair.

Before any restored service starts, the transaction assigns:

- A fresh random Core guard generation, revision 2 (used, not silently downgradable).
- Fresh application epochs, connector revisions and device control generations.
- The existing physical-command epoch fence and occupied-job quarantine.

Logical device/Core/application identities, application incarnations and modes,
credentials, configuration, provider/module selection, public lifecycle revisions,
desired/reported state and stored receipts remain. Same-ID restore is not new
pairing/reinstall. Restoring the exact same backup again gets new fences; neither
the archive's identity nor an earlier successful restore's review context returns.

Never-dispatched queued physical commands are invalidated. Delivered commands,
including queued rows with a recorded attempt/delivery timestamp, become
`unknown / restore_unconfirmed`, not certainly failed; their results, delivery
attempts and timestamps remain. Existing unknown commands remain unchanged.
An occupied/running scheduler claim receives a replacement **nonempty** token,
no lease deadline, and unknown outcome. It is not released or replayed. Cursors
are not rewound by fencing. Other command types are not silently replayed/reset.
No filesystem, service, helper or network operation runs under the DB transaction.

An explicit rollback to a wholly pre-M20 schema may retain its legacy behavior
without inventing metadata. This exception cannot accept partial M20 columns,
a missing singleton in a current-schema database, or a normal restore/reset that
has not migrated. The current schema revision is explicitly recognized as M20;
future authority schema revisions must extend this recovery contract/test gate.

## Coordinators and serialization

| Path | Ordering / failure behavior |
| --- | --- |
| [Backup/portable restore](../deployment/restore_backup.py) | Validate first; stop runtime, switch state, migrate, fence, then activate/verify |
| Failed restore / partial switch | Stop runtime, restore old state, allocate fresh fences, then restart; fence failure leaves services stopped and recovery state retained |
| [Application reconstruction helper](../deployment/restore_application_extensions.py) | Independently fence before any external activation; commit per-package bookkeeping before the next activation, with no DB write transaction across helpers |
| [Immutable installer rollback](../deployment/install-systemd.sh) | Stop runtime/app services, restore DB, run candidate's stdlib-only fence, then restore old runtime; stop/DB/environment/fence failure prevents restart/cleanup |
| [Factory reset](../deployment/factory_reset.py) | Existing fixed-target removal and key deletion, fresh migration, fence, bootstrap, then activation; retained encrypted backups remain available |

The production coordinators already hold `/run/lock/3mm-release-mutation.lock`.
The [private lifecycle helper](../three_mm_runtime/application_lifecycle.py) now
acquires that same nonblocking root-owned lock **before** its instance-runtime
lock and current-ticket validation/receipt. A delayed activation cannot overlap
recovery, and a previously queued ticket fails after the fresh guard/epoch.
The global lock lives outside swapped/deleted state directories. Its lifetime is
an OS/runtime coordination boundary, not a DB write transaction across I/O.
The hardened helper unit gains writable access to `/run/lock`, not release code.

Normal startup and successful update do not call offline fencing. Existing
identity/credentials and authority metadata are not rotated on ordinary restart.
Full releases explicitly require the recovery implementation in the target-owned
deployment contract, builder and installer. Node-only packaging needs no Core DB.

The full restore coordinator and application reconstruction helper deliberately
fence at their own entry boundaries; a production reconstruction may rotate again
before startup. No services run between those fences. Do not bypass them with a
client-authored “already approved/fenced” flag. Trusted root library callers must
provide the same quiescence and release-lock boundary as the production CLI.

## Evidence and remaining gates

Focused disposable-file tests cover all four reasons, generation non-reuse,
mode/incarnation/identity/credential preservation, uncertain command/job evidence,
missing/corrupt metadata, injected late failure with atomic rollback, strict versus
legacy recovery, and absent-file refusal. Actual encrypted portable tests migrate
old and current schemas, check fresh fences **inside activation**, exercise failed
health rollback and repeat the exact current-schema backup. Corrupt restored
metadata is never activated; corrupt rollback metadata preserves manual recovery.

Factory reset ordering/failure and installer shell rollback are tested with
command doubles, not real services. Application reconstruction checks independent
DB write visibility during multiple external activations. Existing recovery,
identity/signing-key, asset/theme storage and release packaging checks also pass.

Native Linux evidence additionally uses two real processes and temporary state:
recovery's flock blocks helper admission before receipts, admitted helper work
blocks recovery's flock, and an old ticket fails after guard replacement. Windows
pytest skips its two native flock cases; its other checks use explicit test doubles.
This is not a live systemd/mount/ownership/clean-install acceptance run.

Recorded targeted runs (overlapping suites, not a release-suite total):

- Recovery/portable migration/reset/lifecycle helper/installer/packaging:
  110 passed, 2 native-lock cases skipped, 5 warnings, 66.14s.
- Historical recovery compatibility, recovery storage, assets/themes and installer:
  98 passed, 18 warnings, 68.49s.
- Final additional installer failure propagation + existing privileged-helper
  regression checks: 39 passed, 3 warnings, 8.78s.
- Compilation, local Markdown links and tracked/new-file whitespace checks passed.

The final physical-evidence follow-up additionally covers attempted-but-queued
commands: 27 focused recovery/reconstruction/portable-migration cases passed,
5 warnings, 54.47s.

Operational attribution remains in existing root recovery status/deployment
journals. A redacted fence summary is emitted only after commit. No administrator
is falsely attributed by reusing a user integer from a foreign/restored DB, and
no new durable approval-decision audit store is claimed.

Fences cannot reverse or reconstruct external actions absent from a snapshot.
Post-backup effects and uncertain external outcomes still require the existing
review/reconciliation workflow; this slice does not prove general crash-safe
effect admission or cross-snapshot history merging. Fresh metadata alone is not
fresh permission. Peer consent quarantine remains the existing restore policy.

The consistent read-only resolver, private review-key provisioning/rotation
(including its recovery policy), approval/apply/decision audit, effect admission,
cross-instance isolation and live Linux/PostgreSQL acceptance remain separate
gates. No new approved grants, silent compatibility-to-enforced conversion,
frontend changes/build, live reset/restore/deploy, commit/push or release here.
