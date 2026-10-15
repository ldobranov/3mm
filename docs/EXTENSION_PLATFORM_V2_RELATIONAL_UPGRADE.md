# WP4 — private prepared-database forward upgrade, 2026-10-15

Status: implemented private Core/Root foundation, published-upgrade confirmation
and witnessed completed-rollback confirmation, explicit partial-restore completion
and local administrator/helper wiring, delivered in beta.50. This is not live
upgrade acceptance, a general package installer or WP4 closure. SDK stays 1.3.
Bounded LOCAL inert adoption of a newer uploaded version is now implemented;
the browser/general installer adoption path remains closed.

## Exact boundary

The target must already be the exact reviewed installed binding, disabled, with
fresh native review and normal review/approve/apply for its declared resources.
The migration coordinator does not stage/switch a package, create executable
trust, grant resources implicitly or expose a new HTTP endpoint. A separate
local metadata-only adoption command supplies the target binding described below;
public/general installer adoption remains a separate gate. Do not
edit installation/grant rows or call internal helpers to bypass those gates.

Older worker-foundation tests seed only the installed candidate binding on
disposable paths. The new adoption integration instead uploads a separate catalog
version and uses the actual local adoption writer, fresh native review/approval
and non-root forward migration, without a test-only installation/grant rebind.
The older worker test seam is not an operator installation procedure.
The accepted live beta.49 fixture, immutable release and M21 checkout are untouched.

## Bounded local version adoption — beta.50

`adopt-relational-version` is an inert Core metadata operation, not installation
or execution. Upload the candidate through the existing catalog-only upload path.
Then explicitly stop/reconcile the old exact prepared start with the existing
`recover-relational-start` flow (including stopped-boot reconciliation when needed).
Read its sealed revision with `inspect-relational-recovery`. An unconfirmed stop,
ordinary disable toggle or old stop reserved by a newer start is insufficient.

Using the existing Core service-account environment and hidden administrator
token prompt:

```sh
python -m backend.services.application_authority_admin adopt-relational-version \
  --installation-id <id> --package-id <uploaded-catalog-id> \
  --artifact-sha256 <candidate-sha256> \
  --expected-current-artifact-sha256 <old-package-sha256> \
  --source-recovery-id <confirmed-stop-id> \
  --expected-recovery-revision <exact-stop-revision> \
  --request-id <new-32-lowercase-hex-id> --confirm-adopt-without-execution
```

Current administrator authentication precedes uploaded ZIP I/O and is repeated
inside the authoritative transaction. Both packages are validated outside Core
leases; catalog/installation pins, exact accepted stop receipt and source pointer,
owner/configuration/profile, recovery generation and stopped authority epoch
are checked under the current review key/guard. Version must advance (build-only
changes do not count), schema must differ and the saved configuration must remain
valid unchanged. Configuration migration and compatibility-mode adoption are not
part of this bounded path. General scope/dependency/frontend blockers still refuse.

One short guarded transaction fences the previous authority epoch and commands,
retains the previous catalog package ID, and binds the candidate with
`active_version: null`, disabled/review-required state and a pending socket.
Instance, installation/incarnation, configuration, old grant/native reviews and
original tickets/outcomes/receipts are retained. Old stop/start records get only
an audited adoption reservation and new metadata revisions; no outcome is repaired.
Per-artifact sealed provenance is separate from first-registration history. An
unsigned pointer, altered provenance or missing current review key cannot make
the candidate reviewable. No new table/schema migration is needed.

Success is **`candidate_not_started`**, `permission_approval: not_evaluated`.
The result includes the original prepared source ID for the later upgrade.
No helper, Root transport-key read, app namespace/data write, package import,
migration, start/boot enable, trust or grant occurs. Historical accepted stop
metadata is not claimed as current kernel quiescence: the separate upgrade helper
still verifies current unit/boot/key/publication/preimages under Root locks.

Now perform a NEW local code review of the candidate and normal resource
review/approve/apply. Old-version native trust cannot approve it. Only afterward
use `inspect-relational-upgrade` and the separately consented `upgrade-relational`.
Upgrade still leaves the app stopped and requires fresh rights/start consent.
A repeated identical adoption request can return only the authenticated historical
metadata receipt; it cannot rebind again or select another package. Any failed
transaction rolls back provenance, pointers, fencing and reservation together.

This command is not yet deployed to the immutable beta.49 VM. No production/live
upgrade or interrupted-restore acceptance is inferred from isolated process tests.

### Separate neutral upgrade candidate

The existing fixture builder now has an explicit opt-in variant:

```sh
PYTHONPATH=. python3 modules/wp4-relational-test/build_test_package.py \
  --upgrade-candidate --output dist/wp4-relational-test-1.1.0.zip
```

This builds **1.1.0 / schema 0002 / SDK 1.3**, not a Core release. Its second
migration only creates/inserts the synthetic `upgrade_probe` marker; the existing
`probe_writes` records, outbox and SDK metadata are untouched. Its `0001` callback
deliberately refuses execution: this is an upgrade over the prepared 1.0.0/0001
fixture, **not a fresh-install package**. Factory/service operations and bounds
are unchanged. Nothing is uploaded, trusted, approved or started by building it.

Candidate ZIP SHA-256:
`8358fdccc644d299aacef7af1cc80cef3d34df86ff1fa8de5bea6d0d21ed727c`.
The default builder still produces the exact existing 1.0.0 ZIP:
`e3afeeba492b1eb30351ebbf8229c27fa1337ccd940f575bba9b96f2f09157d0`.
The candidate source is outside the original service-file glob, so adding it
does not silently republish an immutable 1.0.0 artifact. Both wheel RECORDs and
deterministic ZIP identities are covered by build-only regression tests.

## Separate human consent and one-use journal

`issue_prepared_database_upgrade` requires a current local Core administrator,
explicit forward-upgrade consent, exact source action/revision and the current
target grant-record revision. Sources must have a signed completed preparation,
candidate recovery or previous upgrade, with the same owner/instance/recovery
generation. Namespace creation or uncertain preparation is not an eligible source.

The closed, purpose-separated `database_upgrade` ticket pins both old and new
package/service/configuration/profile/schema identities, old protected lifecycle
digest, original transport-key digest, source ticket/revision, current reviewed
target authority and a fresh lineage/clock/worker-profile budget. Initial
preparation tickets cannot authorize this worker profile, and upgrade tickets
cannot pass as initial preparation.

Issuing consent reserves the source once and fences the old authority epoch and
old-lineage sealed SQL actions without replacing their permit/outcome/receipts.
Commands are invalidated; the application remains disabled/review-required.
An unavailable helper or refused Root preflight does not undo that security fence
or silently renew the request. Core leases are closed before runtime/files/SQL work.
Every checkpoint rechecks the current administrator, exact reviewed target,
grant/native policy, source reservation, key binding, recovery generation and
boot/deadline. No runtime permissions are manufactured from this migration consent.
Completed historical lifecycle decoding does not require yesterday's worker
profile to equal today's executor policy; current execution checks enforce the
current profile separately. A policy update cannot renew an old execution ticket.

## Protected Root transition

The Root caller supplies fixed own roots, non-root application credentials and
trusted Core checkpoints, not package-selected paths. Existing release/runtime
mutation locks serialize the operation. Exact source/target ZIPs, old protected
publication and wheel, key and database ownership must match. Existing rollback
markers or any boot evidence refuse before service/data effects; boot must first
have its separate exact-source stopped-state reconciliation.

After Core authorization, the normal supervisor confirms stop/disable. The helper
retains verified SQLite/private-file preimages and original active/lifecycle
metadata. Source signed SDK metadata/history is checked before durable Core begin.
Only the existing isolated non-root worker imports the exact target migrations;
the old code and application service factory are not executed by Root.

Prepared-mode business DDL uses the existing statement/value/row/deadline bounds,
SQL authorizer and sticky failure behavior. It additionally pins a bounded,
key-free fingerprint of SDK lineage/commit metadata before and after callbacks.
Application migrations cannot update/drop those SDK tables, attach another
database, rename business tables into reserved names or convert a caught denied
statement into a successful commit. Raw native tampering is detected against
the preimage/fingerprint, but this is still cooperative reviewed-native execution,
not hostile-code/process/network isolation (WP5).

After the worker exits and its group is confirmed stopped, Root rechecks Core
authority and unchanged transport key. A fixed SDK-only transaction advances
the lineage/schema. It retains original historical receipt bytes/signatures and
validates their schema identities against bounded applied forward history. Those
old receipts cannot acknowledge admissions against the new lineage/schema.
New active/lifecycle publication is verified and signed; no Core lease overlaps
an application SQL write lock.

Success is exactly `upgraded_not_started`. The original key, business rows,
private files, outbox and historical receipts remain. Preimages are archived as
`.upgrade-evidence-<id>`, not erased or overwritten. The application is not
started, boot-enabled or automatically regranted. After a separate fresh review/
approve/apply, the existing explicit activation coordinator accepts the completed
upgrade as its exact prepared source; creating that start consent alone starts
nothing. Public activation/adoption guards remain closed.

## Failure and uncertainty

Ordinary failure after mutation, before attempting finish, restores the verified
database/files/metadata preimage only after confirmed stop with the original key.
The stopped service, blocking rollback marker and Core `execution_unconfirmed`
outcome remain for explicit reconciliation; restoring bytes is not a successful
Core completion or restoration of old permissions.

An uncertain worker/group stop, transport-key drift or attempted/lost finish ACK
never restores over possible writes or a potentially recorded new lineage.
Candidate/preimage/marker and original outcomes are retained, with no migration
replay, automatic retry or restart. A collision while archiving after Core finish
retains both evidence sets rather than overwriting the destination.

### Lost finish response: explicit readonly confirmation

`issue_published_upgrade_confirmation` and the protected Root confirmer handle
only a **fully published** upgrade with a lost finish request/response or an
interrupted evidence archive. This is a separate local-administrator action,
not renewal/re-delivery of the upgrade ticket. It pins the current source action
revision, exact original ticket/key, reviewed target grant/native binding and
recovery generation, fences the previous epoch and blocks old upgrade checkpoints.
The new ticket has its own purpose and fresh boot/deadline; it cannot run a worker.

Root first refuses any boot evidence and unknown/foreign rollback markers. It
requires the original protected `upgrade.json` to say `completion_unconfirmed`
or `upgraded_not_started`, exact source/target ZIPs and staged wheels, verified
old SQLite/private-file/active/lifecycle preimages, and the complete current target
publication. Both database histories and signed receipt metadata are checked
readonly. The old applied schema history must be a strict prefix of the new one;
historical receipt bytes must still match the preimage, including older-schema
receipts. A deleted but otherwise valid receipt set is not accepted.

Confirmation never imports migrations/service code or writes business SQL,
receipt lineage, keys, active metadata or lifecycle metadata. No Core checkpoint
overlaps its readonly SQLite transaction. The supervisor confirms stop/disable;
no service is started or boot-enabled. Root archives matching evidence only after
durable separate Core confirmation, never overwriting an existing archive.

Core records the separate confirmation receipt and preserves an original
`execution_unconfirmed` lifecycle state as `confirmation_previous_state` when
reconciling the source to `upgraded`. Other SQL/command/outbox outcomes and old
receipts remain unchanged. A reserved upgrade source is ineligible for activation
or another upgrade until its latest confirmation is durably confirmed. Even then,
activation still requires its separate fresh review/approve/apply and start consent.

A second lost confirmation response or partial archive retains blocking evidence.
A NEW explicit human action supersedes the previous confirmation and rechecks the
same exact publication, without replay. At most 32 pending checkpoints, including
the new one, are accepted; foreign, malformed and over-budget evidence is refused.
Verified SQLite backup preimages are read as closed immutable snapshots, so
confirmation does not create WAL/SHM files beside archived evidence.

### Completed rollback: separate readonly reconciliation

`issue_restored_upgrade_confirmation` and its protected Root verifier accept
only a **completed, witnessed** `restored_not_started` rollback. At the end of
the original restore, Root captures a protected coherent SQLite proof snapshot
and signs `rollback-proof.json`, binding that snapshot, the original preimage,
SDK-file manifest, source lifecycle and exact failed upgrade ticket. The proof
is durable before publishing the restored phase. Older/unwitnessed markers are
not silently grandfathered into this contract.

The fresh administrator consent pins the failed action/revision, original key,
current exact target grant/native binding and recovery generation, and fences
the old epoch. The target grant is historical consent for verification only;
its schema/package fields do not authorize running the restored old version.
The restored lineage/digest are pinned separately. A recorded/completed successful
upgrade cannot be reinterpreted as a confirmed rollback.

After confirmed stop/disable, Root checks both exact ZIPs/wheels, the old live and
saved active/lifecycle publication, signed proof and original preimages. It checks
every restored SDK private file and compares a fresh coherent SQLite backup with
the protected restore-completion snapshot. This catches changed business rows,
not merely changed schema/receipt metadata. Both metadata histories are verified
from closed, checksummed snapshots. Live database capture uses normal readonly
SQLite backup, including committed WAL, never `immutable=1` or ignored sidecars.
Generated proof snapshots are retained under the protected evidence directories.

The shared restore helper now reads its already validated closed preimage with
`immutable=1`; otherwise a readonly WAL-header backup can acquire WAL/SHM files
beside the evidence merely by being copied. This exception applies ONLY after
manifest/hash/sidecar verification, never to a live database. Snapshot corruption,
foreign links and pre-existing sidecars still refuse before candidate detachment.

The new confirmation does not run a migration, restore data again, rewrite
lineage/keys, switch the installed package, start/enable the service or restore
permissions. Core records a separate `restored_not_started` receipt. The original
upgrade remains `execution_unconfirmed`, as do unrelated uncertain SQL/outbox/
command outcomes. Known evidence is archived without deletion or overwrite.

Only a separately reviewed NEW forward-upgrade consent may subsequently replace
the old source reservation, after verifying its latest completed rollback receipt.
It records `previous_upgrade_id` in the sealed new action. Pending confirmation
or a new grant alone cannot bypass that check. The old upgrade/helper tickets
remain fenced. A lost response or partial archive requires another fresh human
confirmation; the same restore/migration is never automatically replayed. An
unused earlier published-upgrade confirmation may be explicitly superseded by
this rollback review, without admitting a successful-upgrade source.
Do not issue the next lifecycle until the Root confirmation has returned full
success: a durable Core receipt alone does not waive a still-pending filesystem
marker. The normal helper preflight continues to refuse such a marker.

### Partially interrupted restore: fresh fixed completion

`finish-relational-restore` is a DIFFERENT human choice from readonly confirmation.
Its strict, purpose-separated `database_upgrade_restore` ticket authorizes only
finishing the original verified rollback whose protected phase is `restoring`.
It cannot run application migrations, accept a successful published upgrade as a
rollback, bypass an uncertain worker stop, or renew a historical execution ticket.
The original failed Core action/revision, current reviewed target/grant, owner,
key, recovery generation and fresh five-minute clock are checked at issue and
throughout execution. The old source clock is evidence only.

Under the shared release/runtime locks and verified stop/disable, Root checks the
original protected SQLite/file preimages, signed source metadata/history, exact
old and target ZIPs/wheels and current split publication. Old/new metadata or
absence is allowed; foreign publication, symlinks, changed keys, missing or corrupt
preimages and unknown markers refuse. No package code is imported.

Each action uses a NEW protected `restore-work` directory inside its own marker.
It stages independently verified backup copies and preserves current metadata,
SDK-file namespace and each current database/sidecar before fixed restoration.
An orphan sidecar from an interrupted main-file detach is preserved individually,
not opened as a complete database, followed as a link, deleted or ignored.
Existing candidate/staging evidence in the original or any earlier attempt is
never reused or overwritten. Database/profile/file budgets and the pending-marker
limit remain enforced. Current consent/key/clock are rechecked before data switches.

Only after restoration of database, SDK files and source metadata does Root write
a fresh coherent signed rollback witness and `restored_not_started`. Any earlier
partial witness is preserved in the new work directory. Normal completed-rollback
verification then runs before the separate durable Core finish and evidence
archive. The original upgrade stays `execution_unconfirmed`; no SQL receipt,
outbox outcome, grant, key, boot policy or process-start permission is manufactured.

Another interruption while `restoring` requires a NEW explicit restore action
with fresh revisions. A lost finish after witnessed completion instead requires
`confirm-relational-rollback`, which is readonly and does not restore again.
The same consumed ticket is never retried automatically. Keep all evidence until
the Root response fully succeeds, including any post-Core archive work.

### Local administrator flow (beta.50 commands)

Use the existing local Core service-account environment and hidden administrator
login-token prompt (`application_authority_admin`), not the Linux password or a
token in argv/environment. No browser permission screen can create native code
trust, perform a restore, or submit these new lifecycle actions.

First read the sealed source revision without effects:

```sh
python -m backend.services.application_authority_admin inspect-relational-upgrade \
  --installation-id <id> --source-action-id <source-id>
```

The inspection returns Core journal state/revision and current grant-record
revision; it does NOT claim the runtime/filesystem operation succeeded. After
reviewing the correct evidence, choose exactly one command:

| Command | Source action | Required explicit consent |
| --- | --- | --- |
| `upgrade-relational` | completed preparation/recovery/upgrade | `--confirm-owned-forward-upgrade` |
| `confirm-relational-upgrade` | fully published original upgrade | `--confirm-published-upgrade-reviewed` |
| `confirm-relational-rollback` | failed upgrade with completed witnessed rollback | `--confirm-restored-state-reviewed` |
| `finish-relational-restore` | failed upgrade with partially interrupted restore | `--confirm-finish-interrupted-restore` |

Each takes `--installation-id`, `--source-action-id`, `--expected-source-revision`,
`--expected-grant-record-revision`, a new `--request-id` (32 lowercase hex) and
its own required consent flag. No caller paths, ZIPs, configuration, SQL, key,
UID, worker command or arbitrary callback are accepted. Inspection of the returned
action ID reads its sealed state; it is not a retry instruction on lost response.

CLI authenticates before calling the existing Unix helper. Linux `SO_PEERCRED`
must match the exact configured Core UID, not Root/app UID or a payload claim.
The helper resolves protected roots, package hashes and current configuration
from trusted local dependencies and a bounded Core metadata snapshot. Fixed
Core-UID workers reauthenticate and recheck seals/CAS for issuance and each
checkpoint. Tokens and transport secrets travel only through private pipes/socket
frames, never process arguments, error logs or output. No request automatically
starts/enables a service, grants access or retries an uncertain operation.

The separate `adopt-relational-version` command supplies only the bounded stopped
candidate-binding step, not the general installer/UI. Migration still requires
the exact target to be freshly reviewed/approved; editing installation/grant rows
remains unsupported. The current VM's
immutable beta.49 does not acquire these commands until the beta.50 update.

### Still outside this slice

Partial forward publication without a verified `restoring` checkpoint, an uncertain
migration-worker stop, key drift, an unwitnessed completed rollback or an archive
collision with unknown evidence
are **not** repaired by readonly confirmation. Their data/evidence remain blocking
for separate explicit recovery contracts. Public candidate staging/adoption and
the general upgrade/adoption installer UI remain separate gates. Existing
empty-bootstrap, initial-preparation and candidate-recovery commands are not
substitutes and must refuse unknown upgrade markers. General portable restore/
rekey/account provisioning and broader neutral Standalone/Hub acceptance remain open.

## Verification

### Local candidate adoption — 2026-10-15

- Fresh isolated Linux regression: **322 passed, 1 expected non-POSIX case
  skipped** across candidate admission, original registration, persisted sources,
  policy subjects/management, forward upgrades, partial restore and closed helper
  transport. This includes **54 new candidate cases**, not a full release suite.
- Separate deterministic-package/fixture regression: **44 passed**, including
  **6 new builder cases** and the original exact-delivered-ZIP/Core-UID signed SDK
  cases. This is disjoint from the 322-case run: **366 passing checks total**,
  not a full release run. Original ZIP SHA-256 remains unchanged; the separate
  1.1.0 ZIP was built/validated locally only, not uploaded or installed.
- Three of those candidate cases perform an actual non-root service start/stop,
  catalog-only version upload, the real adoption writer, NEW native review and
  normal approve/apply, then actual non-root forward migration. Two inject an
  interrupted database-detach or metadata-publication restore and complete it
  under a fresh restore consent without migration replay. Unit supervision uses
  disposable process adapters, **not live systemd**. No installed-candidate row
  or grant is seeded to bypass the new adoption path.
- Coverage includes failed metadata-commit rollback, actor/catalog/configuration/
  epoch/key races after ZIP validation, old native-trust rejection, altered stop
  seals/reservations/generation, strict ID/budget/version gates, exact keyed
  candidate provenance, historical-only duplicate receipts and token-free CLI/audit.
- Early process-test runs exposed test-harness-only namespace/stop-interface
  mismatches. The fixture now builds wheel paths from its declared entrypoints
  and supplies a stop adapter that verifies its actual process is gone. The final
  three process cases and the complete regression passed without relaxing a
  production ownership/stop/authority check or adding execution retries.
- Frontend `npm run build-only` passed (340 modules); scoped Black/isort, local
  CLI help and documentation-link/whitespace checks passed. Existing dependency,
  datetime and test-key warnings remain outside this slice.

Live read-only preflight afterward still reports immutable **beta.49**, all four
Core/Agent/Web/helper services and the original fixture unit active, both readiness
endpoints ready and the original Agent identity. No live installation, grant,
key, stop/start/boot setting or M21 checkout was changed. No commit/push/release.

### Partial restore and local-admin flow — 2026-10-15

- **392 isolated Linux regression cases passed** across forward upgrades,
  published/completed-rollback confirmations, the new partial restore, helper
  dispatch/client protocols, SQLite/private-file snapshots and SDK wire/receipts.
  This includes **21 new Core/Root restore/admin-inspection cases**, **72 closed
  upgrade transport/CLI cases** and **8 new fixed-restore wire cases**.
- **4 separate end-to-end Linux process cases passed**: actual local admin CLI
  and Unix kernel peer identity, Root helper, separate Core-UID metadata workers,
  and actual non-root migration where appropriate. Upgrade, published confirmation,
  completed rollback confirmation and partial restore completion all succeed.
  Only disposable unit supervision is doubled; no live systemd unit is changed.
  These files are disjoint from the 392-case run: **396 distinct passing Linux
  checks**, not the full release suite or live upgrade acceptance.
- New recovery tests interrupt SDK-file staging/detachment, SQLite staging/main
  detachment and split old/new publication. They cover another interruption of
  the recovery itself, lost finish before/after Core, refused migration/restore
  replay, corrupt/foreign evidence, key/grant/actor drift, an expired historical
  source clock and a separately reviewed new actual forward upgrade afterward.
  Original preimages, SDK files/outbox/receipts and failed Core outcomes remain.
- Windows wire/transport checks: **76 passed, 4 expected Linux-kernel skips**.
  These overlap Linux coverage and are not added to its count.
- Frontend `npm run build-only`, Black/isort on the 13 scoped formatted Python
  files, CLI parser/help and local documentation-link/whitespace checks passed.
  Existing dependency/datetime/test-key warnings remain outside this task.
- Initial integration tests caught the wrong package-vs-installation instance-ID
  lookup and test-only ancestor traversal/rename-wrapper setup. They were fixed;
  the four actual process paths and final regression passed without production
  retries, relaxed ownership checks, code-trust fabrication or permission fallback.

No VM services/data/keys/grants, immutable release or M21 checkout were changed.
No version bump, commit, push or release was made. General candidate staging/adoption,
broader recovery contracts and explicit live acceptance remain separate gates.

### Earlier isolated verification (overlapping history)

The new root/non-root cases exercise actual forward schema changes and preserved
business/outbox/private-file data, untouched old receipts, changed-content/code/
key/boot/rollback refusals, old SQL fencing, administrator/grant/native/deadline
drift, observed committed intermediate migration plus coherent rollback, raw
native metadata tampering, lost ACK before/after Core and unconfirmed worker stop.
Pure wire/metadata cases cover closed distinct contracts, repeated forward
schemas with old receipt preservation and invalid history/signatures/triggers.

All Linux checks use a private mount namespace/private `/tmp`, not production
Core data. Completed-rollback confirmation checks, 2026-10-15:

- **28 Core/Root cases passed**: actual committed forward migration followed by
  verified rollback and readonly reconciliation, fresh reviewed forward retry,
  unknown outcome preservation, business/file/proof/preimage tampering refusals,
  lost ACK before/after Core, partial archive and current authority drift. A
  mistakenly requested published-upgrade confirmation can be safely superseded.
- Pure Windows SDK rollback/upgrade/confirmation wire checks: **35 passed**.
  This includes the **9 new rollback wire cases** and overlaps the earlier SDK
  counts below; do not sum them as distinct checks.
- Separate Linux upgrade/published-confirmation, database/file snapshot and SDK
  regression: **222 passed**, including the new closed-preimage WAL restore test
  and rollback wire cases. Together with the disjoint 28-case rollback file this
  is **250 distinct passing Linux cases** for this step, not the full release suite.
- The first integration run exposed WAL/SHM creation when copying a verified
  closed preimage. The fixed reader and a focused WAL restore regression protect
  the evidence without treating the live source as immutable.

Earlier published-upgrade confirmation checks, 2026-10-15:

- **59 passed**: 49 Core/Root confirmation scenarios, one explicit WAL-snapshot
  test and 9 pure closed-wire tests. They include two consecutive actual forward
  upgrades with readonly confirmation, lost finish on both sides of Core,
  repeated confirmation interruption, partial archive, old receipt deletion,
  strict marker decoding, live authority/key/generation drift and refusal of a
  real failed-and-restored upgrade. A new grant cannot bypass pending confirmation.
- Separate existing upgrade/activation/recovery-confirmation and SDK wire/receipt
  regression: **193 passed**. These two current Linux runs cover disjoint test
  files (**252 distinct passing cases**); earlier run totals below overlap and
  must not be added. Initial test-harness failures (stale-generation decoding
  and main-file-only WAL comparison) were corrected and the affected suite rerun.
- Live database assertions compare coherent readonly SQLite serialization,
  including committed WAL pages, rather than GC-dependent main-file bytes alone.
  Protected archived preimages and lifecycle publication still have byte checks.
- Windows SDK wire/receipt/upgrade/confirmation regression: **69 passed**, with
  **2 expected Linux-clock skips**.

Earlier forward-upgrade foundation checks, 2026-10-14 (overlapping runs):

- Wider preparation/migrations/recovery/confirmation/activation/upgrade and SDK
  regression: **304 passed**. This preceded the final bounded-history and
  historical-worker-profile refinements.
- Fresh final upgrade + SDK wire/receipt regression: **97 passed**, including all
  **35 Core/Root upgrade cases** and **17 new pure upgrade cases**. It covers the
  final profile checks, bounded revision decoding and two actual consecutive
  upgrades (`0001` → `0002` → `0003`) without replaying the applied prefix.
- These earlier counts must not be added to the current checks. That step's
  Windows pure SDK suite passed **60 cases, with 2 expected Linux-clock skips**.
- Black/isort, whitespace/link checks and `npm run build-only` passed. Existing
  dependency/datetime/test-key warnings were not suppressed or repaired as
  unrelated work.

These are targeted checks, not a full release suite or actual systemd upgrade
acceptance. No VM services, production data, keys or grants were changed. There
was no commit, push, release or public activation/authorization bypass.

## Implementation references

- [Core consent and checkpoints](../backend/services/application_relational_upgrade.py)
- [Inert local candidate adoption](../backend/services/application_relational_candidate.py)
- [Candidate admission/security and process tests](../backend/tests/test_application_relational_candidate.py)
- [Deterministic original/candidate fixture tests](../backend/tests/test_wp4_relational_candidate_package.py)
- [Protected Root upgrade](../three_mm_runtime/application_relational_upgrade.py)
- [Core published-upgrade confirmation](../backend/services/application_relational_upgrade_confirmation.py)
- [Readonly Root confirmation](../three_mm_runtime/application_relational_upgrade_confirmation.py)
- [Core completed-rollback confirmation](../backend/services/application_relational_upgrade_rollback.py)
- [Protected rollback verifier and proof writer](../three_mm_runtime/application_relational_upgrade_rollback.py)
- [Fixed partial-restore completion](../three_mm_runtime/application_relational_upgrade_restore.py)
- [Closed local helper/Core wiring](../three_mm_runtime/application_relational_upgrade_control.py)
- [Local administrator commands](../backend/services/application_relational_upgrade_cli.py)
- [Partial restore fault-injection tests](../backend/tests/test_application_relational_upgrade_restore.py)
- [Actual CLI/socket/Core-UID process tests](../backend/tests/test_relational_upgrade_admin_flow.py)
- [Peer/frame/client security tests](../three_mm_runtime/tests/test_relational_upgrade_transport.py)
- [Existing non-root migration worker](../three_mm_runtime/application_relational_migrations.py)
- [Private upgrade wire](../three_mm_application_sdk/relational_upgrade_wire.py)
- [Fixed receipt metadata steps](../three_mm_application_sdk/relational_upgrade_receipts.py)
- [Root/Core integration tests](../backend/tests/test_application_relational_upgrade.py)
- [Confirmation integration tests](../backend/tests/test_application_relational_upgrade_confirmation.py)
- [Rollback confirmation integration tests](../backend/tests/test_application_relational_upgrade_rollback.py)
- [Wire/metadata tests](../three_mm_application_sdk/tests/test_relational_upgrade.py)
- [Closed confirmation wire tests](../three_mm_application_sdk/tests/test_relational_upgrade_confirmation.py)
- [Closed rollback wire tests](../three_mm_application_sdk/tests/test_relational_upgrade_rollback.py)
- [Closed fixed-restore wire tests](../three_mm_application_sdk/tests/test_relational_upgrade_restore.py)
- [SQLite snapshot/restore regression](../three_mm_runtime/tests/test_application_database_snapshot.py)
- [Boot preservation fence](EXTENSION_PLATFORM_V2_RELATIONAL_BOOT_FENCE.md)
- [Accepted live preparation/restart/boot trial](EXTENSION_PLATFORM_V2_RELATIONAL_VM_TRIAL.md)
