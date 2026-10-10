# M20 WP4 — bounded private-file SDK adapter

Date: 2026-10-09. Status: local implementation and focused tests; not WP4 closure.
Scope: common application SDK in Standalone and Hub, not Fleet-specific.

## Reuse and boundary

The existing host supplies `ApplicationContext.data_dir` for the logical
installation under its persistent `data` directory. The SDK already exposes an
application-owned SQLite database with migrations and a transactional outbox.
Those APIs and SDK version **1.3** are unchanged.

The additive `context.files` helper uses **only `data/sdk-files`**, with flat
logical file IDs rather than caller paths. It does not access Core tables, global
uploads, a different application, release directories or transport credentials.
Constructing a context or obtaining the helper performs no filesystem write.
Existing applications acquire no files, declarations, grants or migration changes
automatically. A new full-release payload must include `files.py`; the existing
target-owned deployment contract and release-builder tests enforce this dependency.

The direct helper remains an SDK safety adapter for reviewed native code, **not
a grant or isolation against malicious code**. Its constructor's
directory, mode and bounds are trusted host/operator inputs, not a signed grant.
Native code can bypass a Python helper and still has its existing private SQLite
and filesystem access. Declared files instead use the host-selected scoped adapter
and the bounded Core/target-owned execution path below. No package-authored host
path, new Core writable mount or sandbox label is introduced. Unsupported
storage/platform/frontend authority still denies without fallback.

## Current bounded execution and exact administrative review

Installed headless reviewed-native packages can now receive explicit file grants
through the existing `ApplicationAuthorityManager` and admin HTTP review API. It reconstructs
internal version-4 inputs from the actual installed ZIP, full configuration HMAC,
Core/application/incarnation and exact file declaration. Current authenticated
administrator review, separate approval/apply, disabled first adoption, exact
native attestation, expiry and fresh epoch remain mandatory. The current native
policy requires all requested scopes; synthetic policy-subset tests do not make
an installed declaration optional. No installation is adopted implicitly.

The first executor accepts **at most 1 MiB/file**, with the declaration's exact
total/count bounds (up to 64 MiB/1024 files). Larger per-file requests retain the
unsupported-family blocker; they are not silently clamped. Schema/helper ceilings
remain 16 MiB/file for native recovery and compatibility. The catalog marks this
narrower runtime `reviewed_native_scoped_local`, with `core_admin_review_api`,
local-only native trust attestation and its per-file bound.

`files.execute` and `files.status` reuse the signed installation platform gateway;
they add no public HTTP file or native-trust endpoint. The supervised host selects
`ApplicationScopedFileStorage` for a supported declaration, never the direct
native helper. `get/list_entries` require current read authority; `put/delete`
require current write authority. Missing platform, revoked/stale key, grant,
configuration, incarnation, artifact or recovery generation refuses access.
Core continues to have no write access to application-owned files.

The same application host owns one bounded `run/files.sock` worker, separate from
serial `service.sock`, so an SDK call does not call back into its occupied handler.
It uses the existing private `data/sdk-files`, POSIX checks, CAS and bounds. The
worker has one thread, backlog four, bounded frame/read timeout and at most 128
unexpired consumed IDs. No new service, runtime or data root is created. Its fresh
nonce, instance, exact package/declaration and five-second boot-clock deadline
bind each admitted operation; restart/rollback rejects old permits.

Core commits admission under key -> DB guard -> current grant before IPC, then
releases both leases. **Already admitted work may finish after revocation**; new
admissions fail. Every mutation first creates an authenticated durable record in
the existing sealed authority action journal. It records machine principal,
request hash, file ID, operation, grant/epoch, plan/native-review attribution and
metadata-only outcome. No content, private path or transport secret is stored;
no fake human user is written to `AuditLog`. Existing approval audits retain real
administrator attribution. No database model/migration is needed.

A lost dispatch/ACK, malformed reply or failed completion seal leaves
`execution_unconfirmed`; Core never redispatches that request ID, including after
worker restart, revocation or disable. Completion is acknowledged only after its
sealed receipt commits. Historical lookup/retry returns metadata, never bytes or
renewed permission. Altered content/owner or stale recovery/key seals fail.
Unresolved journal entries are retained; capacity is bounded to 4096 total sealed
action rows per installation (including administrative rows). No automatic eviction
or cleanup is provided; reaching capacity requires operator review.

Scoped mutations accept an optional explicit 32-hex `request_id`. Save it before
calling; `ApplicationFileExecutionUnconfirmed.request_id` identifies uncertain
work. `files.operation_status(request_id)` reads only its receipt. Reconcile
receipt/current data before authorizing a new request; do not auto-retry with a
new ID. CAS/quota/runtime refusals are conservatively unconfirmed once admitted,
rather than being relabelled as safe replay.

The existing admin HTTP review schema now accepts only the two exact private-file
scope IDs. The management dialog displays separate read/write cards with the
Core-derived owner, mode, exact per-file/total/count limits and expandable
installation/incarnation/package binding. This is a review, not a file browser,
quota editor or native-trust authoring endpoint. No caller-supplied resource,
owner, path or approval flag is accepted.

The dialog checks closed resource shapes, complete operation selection, consistent
owners/declarations and the current installed package/module before showing its
acknowledgement and separate approve/apply actions. Missing, oversized, foreign,
mixed or unsupported resources fail closed. Existing auth, local code-attestation,
disabled first-adoption, expiry, current-source and revocation gates remain. Lost
or stale decisions clear the review rather than retrying or inferring success.
Startup code must tolerate unavailable file grants until an active-install review
applies; health/staged startup is not a rights bypass. General staged recovery,
relational policy, remaining platform/frontend contracts and neutral Standalone/
Hub live acceptance keep WP4 open.

The worker uses the current reviewed-native shared HMAC transport. Native code can
still bypass Python or forge its own transport traffic: this is **not Core-only
cryptographic isolation against hostile application code**, a POSIX identity
boundary or OS disk quota. Those proofs remain WP5, not inferred from this SDK
path. No live device, deployment or release is included.

## Public API

```python
# The host-created context selects this installation, not a package path.
files = context.files
first = files.put("logo", persisted_image_bytes, expected_sha256=None)
current = files.get("logo")
files.put("logo", replacement_bytes, expected_sha256=current.sha256)
entries = files.list_entries()  # sorted (logical file ID, size in bytes)
files.delete("logo", expected_sha256=first.sha256)  # conflicts after replacement
```

`ApplicationFileStorage`, `ApplicationFileLimits`, `ApplicationFile` and
`ApplicationFileStorageError` are public additive SDK exports. A trusted native
caller may explicitly construct a read-only helper over its host-provided
directory with `mode="read"`; this is a cooperative safety mode, not permission
revocation. IDs are lowercase ASCII, begin with a letter, contain only letters,
digits/underscore and have at most 64 characters. No extensions, separators,
traversal, URLs, absolute paths, NULs or internal names are accepted.

- Default limits: 1 MiB/file, 16 MiB committed content and 256 files. Explicit
  limits are strict integers, with bounded ceilings and coherent sizes. They cover
  this helper's namespace, **not** the SQLite database or arbitrary native writes.
- Content is bytes. The SHA-256 is a content version, not publisher trust or a
  durable request receipt. `expected_sha256=None` means create-only; replacement
  and deletion require the exact current content digest. No wildcard overwrite.
  Equal content versions use the same digest: this is not an ABA-proof revision
  journal and must not represent physical/fiscal work.
- Relative directory descriptors and `O_NOFOLLOW` prevent checked-path symlink
  traversal, including ancestors. Non-regular files and multiply-linked files are
  rejected. Nonblocking opens avoid a FIFO wait. Real POSIX support is required;
  unsupported hosts refuse instead of using an unsafe path-based fallback.
- A nonblocking advisory lock serializes cooperating processes for reads/CAS,
  quota checks and mutations. Contention returns `busy`, not an indefinite wait.
  This does not stop hostile code replacing lock files or bypassing the helper.
- Write a unique private staging file, sync it, rename atomically and sync the
  directory before returning. New files are `0600`, namespace `0700`; an existing
  namespace is not recursively chmod/chowned. Staging can temporarily consume up
  to one additional bounded file beyond the committed-content quota.
- A rename/sync failure has no automatic retry. Read/compare the same logical ID
  to reconcile an uncertain result before deciding what to do. Deletion likewise
  reports a sync failure as uncertain; missing data is not a historical receipt.
- Crash-left staging or unknown namespace entries block new mutations/listing for
  explicit recovery review, rather than automatic deletion or replay. Existing
  regular committed files remain individually readable for recovery.

Errors exposed by this API do not include host paths. Underlying chained OS
diagnostics remain private to a trusted operator, not an HTTP response contract.

## Compatibility and earlier delivery history

The sections below record the earlier declaration, pure-policy, denial and
recovery slices. Their unsupported-runtime statements describe those preceding
slices; the bounded local runtime above is the current status.

No Core schema, Alembic migration, manifest or Device Protocol change is needed.
The existing application data directory and database names do not change.
Private file data is not code in an immutable release. No actual application is
modified to consume the helper in this delivery.

### Inspectable file requests, not storage grants

The optional `storage.private_files` field in `application-extension.json` now
describes an author's request. It reuses application descriptor v1 and SDK **1.3**;
`file_contract_version: 1` versions only this nested declaration. Example (inside
the existing storage descriptor, not a complete application descriptor):

```json
{
  "private_files": {
    "file_contract_version": 1,
    "namespace": "private_files",
    "mode": "read_write",
    "max_file_bytes": 1048576,
    "max_total_bytes": 16777216,
    "max_files": 256
  }
}
```

`mode` is explicitly `read` or `read_write`. All three limits and the integer
contract version are required; booleans, coerced strings/floats, zero, negative
and unsupported values are rejected. Ceilings match the SDK: 16 MiB/file,
64 MiB total and 1024 files, with per-file size no greater than total size. The
sole namespace defaults to `private_files` and belongs to the Core-resolved
installation. A package cannot select a host path, foreign owner, grant or
database policy. Classification, personal-data lifecycle operations and backup
requirements remain in the enclosing storage declaration and apply to its data.
A file `read` request does not make the existing private SQLite database read-only.

Package Inspection projects the mode and limits as a separate
`storage:private_files` request. Addition, change and removal use the existing
declaration diff. Unchanged requests also remain unresolved: declaration validity
is not permission approval. The public schema catalog advertises this field with
`runtime_authority: not_implemented`, not as a supported runtime grant.

The real source resolver reports `unsupported_scope_family`; the existing
authority manager refuses grant planning/native-review adoption for such a
package, even when the selected scopes contain only existing commands/connectors.
An old exact-artifact native review cannot authorize this new declaration. Refusal
does not modify the compatibility installation, authority epoch, grant/plan/native
review rows or audit state. It also does not silently enforce/revoke native file
access: reviewed-native compatibility access still has its documented limitations.
Descriptor limits are **not yet wired into a guarded storage runtime**, nor are
they an OS quota. No positive storage permission or file broker action is added.

Old descriptors without this optional request remain supported with SDK 1.0–1.3.
There is no automatic declaration, migration or permission adoption. New requests
require SDK 1.3 and this updated Core validator; older strict Core validators are
not expected to accept an unknown field. Update compatibility is not a promise
that new descriptors can run on old Core releases.

Next gate: bind exact approved mode/bounds to authenticated runtime admission and
every file operation, with expiry, revocation/race and recovery denial tests,
before removing the unsupported-family blocker or issuing storage grants. Private
relational policy and hostile native isolation remain separate unfinished gates.

### Exact file-policy review inputs — internal version 4

The existing pure policy/context evaluator now understands private files alongside
commands, connectors, subscriptions and publications. It uses internal subject,
evidence, context and selection **version 4**, not a new public descriptor, SDK,
Device Protocol, permission endpoint or competing grant store. Existing version
1–3 inputs retain their schema, canonical shape and fingerprint behavior. A caller
must explicitly enable version 4 parsing; the installed authority coordinator still
accepts only the previously supported versions and rejects storage adoption.

Each resolved file scope contains the validated declaration, the full Core-owned
application principal (Core installation, application installation, incarnation,
module ID), the exact installed **package** digest and one operation. That digest
pins the declaration and service payload together. There are only two scope IDs:

- `storage:private_files_read`: the planned get/list authority.
- `storage:private_files_write`: the planned put/delete authority.

These are review-input identities, **not implemented broker actions**. A complete
resolved subject/context includes every operation requested by its mode. Read-only
requests cannot contain write; read/write requests cannot hide their write request
by omitting it. Both scopes refer to one identical own namespace, declaration and
package. There is no path, foreign namespace, wildcard, caller approval flag or
database-policy input.

Trusted policy inputs may allow a strict operation subset or explicitly allow
neither file operation. Read does not imply write, and write does not imply read.
Every policy rule pins exact declared limits; there is no inferred quota containment
or silent bounds expansion. Mode/count/size changes require new exact evidence
and produce a different policy identity/review fingerprint. Required scopes must
be selected; omitted or unauthorized operations, duplicate/mixed resources,
foreign owners/artifacts and unsupported versions fail closed.

Policy comparison and context review perform **no filesystem, database, network
or process I/O**. They neither authenticate synthetic evidence nor issue a grant
or file permit. Existing native-review, frontend/isolation, source and expiry gates
remain intact. The production resolver's unsupported-storage blocker, host denial
adapter and catalog's `runtime_authority: not_implemented` deliberately remain.
The next implementation must reconstruct these inputs from protected current
sources and wire actual sealed approval/admission to the target-owned executor,
with revocation/lifecycle and uncertain-result tests before enabling file authority.

### Host propagation and no ungranted SDK fallback

Activation now copies a **validated file request**, when present, into the existing
protected `active.json` storage metadata. It copies no path, approval flag, grant
or authority epoch. No extra field is written for old undeclared packages. The
normal metadata snapshot/rollback retains the exact previous request or absence;
portable reconstruction uses the installed package's validated request again.

The supervised host revalidates that nested contract before importing package
migrations, opening SQLite or constructing the service. It supplies a same-data-root
file adapter to the existing SDK context. Mode and bounds reflect the request,
not granted authority. A declared request currently denies every get/list/put/delete
before opening/creating the SDK namespace: it cannot fall back to the default
native helper when a platform client, positive grant or supported runtime adapter
is missing. The existing source/authority blocker remains in place.

SDK 1.3 gains only an optional **keyword-only trusted-host adapter** on
`ApplicationContext`; existing positional arguments, including the clock, stay
unchanged. Context construction rejects foreign-root/non-file adapters and does
not open/create files. Old descriptors retain the reviewed-native helper and
private SQLite behavior. Operators' backup/rollback helpers are separate from
runtime permission and remain able to preserve private data.

This closes a declaration-to-default-helper gap, not positive storage authority
or hostile native isolation. Reviewed code can still bypass Python adapters and
use its existing native filesystem access; it has not become a sandbox. The Core
service still has no new write access to application data: its immutable/systemd
protection and existing application-owned `0700` file namespace are unchanged.
Do not implement a Core-side file writer by widening those protections or create
a second storage root. The next guarded executor must operate through a proven
target-owned runtime boundary, bind exact current grants and serialize revocation/
lifecycle against mutations. A preflight permission boolean followed by an
unguarded local write is not sufficient.

The existing host serves application requests serially. A future platform broker
must not call back into that same occupied service socket while application code
is waiting for an SDK response: that would deadlock. A bounded host-owned executor
and authenticated admission/completion boundary need explicit implementation and
tests, including uncertain IPC results; neither a new permission boolean nor a
broader Core writable mount solves this. They are not delivered by this denial slice.

### Local activation rollback integration

The supervised activation helper now captures `state.sqlite3` **and only the SDK
`data/sdk-files` namespace** before candidate startup. It reuses the existing
release/lifecycle lock and one-use admission receipt; no new authority is minted.
An existing installation is quiesced even when disabled rather than enabled.
Production systemd stop additionally verifies inactive/failed, disabled/masked,
no main process and no pending job before snapshot or data restoration. Alternate
supervisors must honor the same stop contract.

Each attempt has a fresh helper-owned `0700` `.activation-*.rollback` directory,
not a reused artifact-digest path. Its synced record identifies the candidate,
previous metadata/enable state, quiescent database presence and last recorded
phase. Previous `active.json`, SQLite preimage and a bounded file manifest with
IDs/sizes/digests are retained there. Package configuration in the old metadata
is private recovery data, never a public inspection response.

The file preimage validates all entries through the SDK's pinned POSIX access and
cooperative lock. It accepts the SDK's maximum supported limits, not just the
default helper limits. Unknown/pending entries, unsafe links, lock contention or
incomplete preimages prevent candidate startup and require recovery review.
There is no arbitrary recursive copy of native data or global uploads.

For an ordinary failed activation, the helper confirms the candidate stopped,
validates/stages the bounded file preimage, detaches the candidate namespace without
following links, restores the old namespace/database/metadata and then restarts
only a previously enabled installation. An originally absent namespace is made
absent again; an empty namespace stays present and empty. New namespace/files
retain `0700`/`0600` and the existing service UID/GID. Other native data is untouched.
Successful activation retains candidate files. Normal uninstall retains SDK files.

DB and directory replacement are **not one filesystem/database transaction**.
On an unconfirmed stop, invalid/missing snapshot, failed switch or database restore,
the helper does not restart or claim that restoration succeeded. It keeps recovery
evidence, including any detached candidate data. Incomplete/legacy rollback
artifacts block further activation, uninstall and erasure instead of being
overwritten/deleted. Cleanup failure also requires review and attempts to quiesce
the runtime; an unconfirmed stop is reported explicitly.

This is an in-process failure rollback, **not automatic crash recovery**. A helper
crash leaves review-required artifacts; there is no inferred activation/replay or
new public file-restore action. Existing administrative lifecycle reconciliation
can verify disabled state, but cannot by itself restore/approve/delete these files.
The general WP3 recovery coordinator remains an explicit next gate. Local data
rollback never reverses/replays a physical, payment or connector effect, nor
restores old Core grants/authority epochs.

The file copy/stage can temporarily require two additional bounded namespace
copies (up to 128 MiB beyond a 64 MiB source), plus SQLite backup and metadata.
Reads are per-file, not one 64 MiB memory allocation. This is not a production disk
quota or measured low-resource acceptance. Interrupted activation still requires
recovery-coordinator/live fixtures, as do per-instance POSIX identity/mount isolation
and the broader staged-migration contract.

### Local Standalone backup and portable recovery

The existing encrypted full-state backup already includes application-owned
`data` files. SDK files reuse that archive, catalog and password-protected download/
import flow; there is no second backup format or endpoint. This recovery flow is
**Standalone-only**, as before. The SDK remains common to Standalone and Hub, but
this delivery does not introduce Hub/Fleet full-state recovery.

Backup preview now validates each present SDK namespace through the read-only
POSIX helper before generic scanning/hashing. Unsafe links, special files, pending
entries, missing/nonempty locks, contention and limits exceeded make it not ready.
Maximum supported SDK bounds are used, so explicit limits above SDK defaults still
round-trip. Validation does not create a namespace or repair/delete its contents.

Pending or legacy activation rollback evidence prevents backup and restore rather
than being silently omitted from the archive or erased by a successful state switch.
Backup checks this before stopping/restarting services, then performs the ordinary
quiesced preflight. Restore checks the existing target before service stop. Production
helper entry points retain their existing release-mutation lock; direct root callers
must provide the same coordination, not race another lifecycle operation.

Archive validation requires application entries under the existing instance's
`data` namespace. SDK entries must be flat logical blobs plus an empty lock, within
16 MiB/file, 64 MiB/namespace and 1024 blobs. This check runs before payload extraction,
even for an authenticated archive. The extracted namespace is validated again before
state replacement. Other legacy/native data paths remain unchanged. Empty SDK
namespaces retain their lock; an absent namespace is not created by recovery.

Payload preparation restores SDK directories as `0700` and files/locks as `0600`,
using the existing application service UID/GID instead of widening private-directory
access to the legacy `0750` mode. No immutable release permissions are changed.
Existing successful/failed-health state-switch recovery and authority fencing are
reused. A backup restores data, not historical storage grants or authority epochs.

The portable fixture exports a real encrypted backup, keeps only its downloaded
file, removes the disposable original state/key and imports into a fresh fixture
with a different device backup key. It then runs actual application reconstruction,
package validation and activation against the recovered SQLite and SDK files.
Service control, health transport and migration are doubles; this proves the local
file/crypto/reconstruction boundaries, not live systemd, grant or migration acceptance.

WP4 remains open for the file-management UI and broader storage/database policy,
remaining platform/frontend host contracts and neutral
human/kiosk/Standalone/Hub SDK acceptance. WP5 separately proves hostile
cross-application isolation and measured resource exhaustion. No live deployment,
rights change, commit, push or release is performed in this step.

## Local evidence

Initial adapter verification: **69 focused Linux tests passed**: all public SDK tests, actual host/wheel loading,
full release-builder checks and Node-release regression. New private-file fixtures
cover independent contexts, SDK 1.3, strict IDs/limits/modes, stale CAS, quotas,
restart, ancestor/data/namespace/blob/lock symlinks, hardlinks, FIFO refusal, crash
staging, pre-replace failure, post-replace sync uncertainty, prompt lock refusal
and two actual processes competing for the same version. All paths/data are
temporary; production services/credentials/devices are not used.

Frontend production build passed (340 modules); no frontend source or visual
screen changed. This is not a full release suite or live OS/backup acceptance.

The rollback follow-up adds real POSIX fixtures for combined SQLite plus file
add/change/delete, healthy-candidate retention, failed first install, absent/empty
namespaces, disabled-install quiescence, metadata write failure, unconfirmed stops,
missing/corrupt preimages, partial namespace switch, busy writers, symlink/hardlink/
crash-staging refusal, manifest validation, explicit larger SDK limits, uninstall
retention and recovery-evidence protection. Systemd effects remain command doubles;
no live service, device, credentials or external operation is used.

Final follow-up verification: **178 focused Linux tests passed** (45.54s), covering
the new file rollback plus SDK, activation, host loading, lifecycle/ticket authority,
application reconstruction and full/Node release packaging regressions. The
frontend production build also passed (340 modules). These are scoped checks,
not the complete release suite or live/portable recovery acceptance.

The next recovery follow-up adds SDK-file fixtures for encrypted local restore,
failed health with previous-state rollback, password-protected downloaded recovery
after source/key loss, application reconstruction, namespace presence/modes/service
identity selection, source/import quotas, authenticated malformed archive refusal
before extraction, and retained pending rollback evidence without runtime restart.
Only test-owned temporary directories are erased in the source-loss simulation.

Recovery follow-up verification: **147 focused Linux tests passed** (164.18s),
including SDK-file recovery, existing backup routes/preview/compatibility, storage,
installation identity, Node recovery, authority fences, application reconstruction
and activation/snapshot regressions. Frontend production build passed (340 modules).
This is not the complete release suite or live device acceptance. No commit, push,
deployment or release was requested/performed for this follow-up.

Declaration follow-up verification: **317 focused Linux tests passed**, one
non-POSIX-specific case skipped (62.14s). This includes 78 new declaration/negative
adoption cases plus existing descriptors, schema catalog/CLI, ZIP validation,
authority inspection/sources/subjects/management and the public SDK suite. The
source/adoption refusal uses a real headless package, Core keys, SQLite and existing
authority manager; malformed ZIPs are refused without executing package code.
Frontend production build passed (340 modules); no frontend source changed.
This is not a complete release suite, positive file-grant acceptance or WP5
isolation proof. No live data/device, commit, push, deployment or release was used.

Host propagation follow-up: **238 focused Linux tests passed** (38.54s), including
23 new actual wheel/host/context cases, SDK regressions, activation/data rollback,
file snapshots, encrypted/portable recovery, reconstruction, release packaging,
public declarations and negative authority adoption. Malformed file metadata
fails before package import/SQLite; declared reads/writes deny before opening the
namespace, even with retained existing files. Old SDK 1.0–1.3 packages still load
and use the legacy helper; failed updates restore the exact old request/absence.
Service/health effects are doubles; no production system or external work is used.
Frontend production build passed (340 modules). No complete release-suite, positive
storage grant, hostile-code isolation, commit, deployment or release is claimed.

File-policy context follow-up: **390 focused Linux tests passed**, one
non-POSIX-only case skipped (122.58s). New pure version-4 vectors cover exact
owned artifact requests, independent read/write policy subsets, complete-request
validation, mode/limit drift, fixed canonical identities, expiry, malformed or
constructed inputs and no live I/O. Regression checks cover existing version 1–3
policy/context behavior, actual keys/SQLite/native-review management, installed
sources/subjects/status, scoped event consumption/publication and declared-file
adoption/host denial. Those real installed paths still refuse storage authority;
synthetic positive context comparison is not positive runtime-grant acceptance.
Frontend production build passed (340 modules). No database migration, live data,
device effect, commit, push, deployment or release was used for this slice.

Scoped execution follow-up: **664 focused Linux tests passed**, one real
non-POSIX-only case skipped (241.46s). These cover installed version-4 native
review/approve/apply and current file grants, real signed SDK -> Core gateway ->
target-owned worker CRUD, the full 1 MiB boundary, exact receipts, CAS refusals,
revocation before/after admission, uncertain dispatch/completion, runtime restart,
configuration/identity/key/recovery drift and read-only denial. Existing version
1-3 authority, event consumption/publication, descriptor/catalog, SDK, activation,
snapshot and full-release/Node-catalog checks remain green. The required release
file list retains its strict sorted/unique validation and includes the new
execution dependencies.

A supplemental **68 Linux tests passed** (65.91s) for host startup/shutdown,
signed platform compatibility, SDK denial/uncertainty, Node packaging and encrypted/
portable file recovery. These overlap the broad run and are not an additional
unique-test total. Frontend production build passed (340 modules); no frontend
source changed. Administration remains local Core API only: the exact file-rights
HTTP/dialog slice is next. SDK remains 1.3; WP4/WP5, the full release suite and live
OS/device acceptance are not claimed complete. No commit, push, deployment or
release was performed.

Exact HTTP/dialog follow-up (2026-10-09): **26 Linux tests passed** (54.07s)
for the actual file declarations, current admin sessions, native review,
separate approve/apply/revoke and existing signed file execution. Anonymous,
non-admin, revoked-session, absent native proof, active first-adoption,
configuration drift, wildcard/extra-resource and incomplete-selection requests
refuse without granting rights or creating file data. **112 further Linux tests
passed** (30.32s) for existing authority management, private-file declarations and
the authoritative schema catalog. These two runs total 138 distinct tests, not
a full release-suite run; formatter/import-order checks and scoped diff checks
also passed.

**49 frontend tests passed**, including the exact read/read-write view, malformed,
foreign, mixed, unsupported and changed file bindings alongside existing
authorization/expiry/stale/lost-decision behavior. Type checking and production
build passed (340 modules). The actual component was visually checked through
the browser in desktop EN light, BG dark and 390 x 844 mobile BG dark, including
long binding IDs, keyboard access and reachable footer controls. The isolated
fixture has no backend or real data and refuses decision mutations; no real
permissions were granted. Owner visual acceptance remains separate.

This delivery updates the public catalog to distinguish admin resource review
from local-only native code attestation. SDK 1.3 and the current Core version
remain unchanged. WP4/WP5 and live Standalone/Hub recovery/security acceptance
remain open; no commit, push, deployment or release was performed.
