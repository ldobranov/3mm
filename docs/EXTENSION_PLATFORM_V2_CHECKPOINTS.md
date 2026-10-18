# M20 WP4 — scoped own-installation checkpoints

Status: bounded reviewed-native implementation, **local, 2026-10-15**. This adds
exact checkpoint declarations, review/grants, signed runtime admission, SQL CAS
and administrator resource cards to the existing SDK/authority path. It does
not close WP4, change the VM or authorize a release. SDK remains **1.3**; Module
Manifest v2 and application descriptor v1 retain their existing versions.

## Purpose and exact declaration

Checkpoints are small application-owned JSON progress/state objects in the
existing Core `ApplicationSyncCheckpoint` table, not application SQL database
backups, private files or a general Core database API. Optional application
descriptor `checkpoints` contains at most **32** declarations with unique IDs:

```json
{
  "checkpoints": [
    {
      "contract_version": 1,
      "checkpoint_id": "progress",
      "mode": "read_write",
      "max_value_bytes": 4096
    }
  ]
}
```

Each declaration has exactly these four required fields. `contract_version` is
the integer **1**, not boolean/string/float. IDs match
`[a-z][a-z0-9_]{0,95}` (at most 96 characters), with no path, wildcard or foreign
owner. Mode is `read` or `read_write`; `max_value_bytes` is a strict integer
**1..262144**, explicit and never silently clamped. Declarations require SDK
1.3; absent declarations preserve supported older packages. Existing strict raw
parsing refuses duplicate keys, including a hidden `checkpoints` declaration.

Value limits count compact, sorted-key **UTF-8 JSON bytes**, not character
count, Python object size or the size of a complete signed transport frame.
Values must be JSON objects; nested arrays/objects, strings, booleans, null and
finite numbers are supported within depth **16** and **16384** visited nodes
(including object keys). Number magnitude is at most `2**53 - 1`; unpaired
surrogates, NaN/infinity and non-JSON values are refused. These are cooperative
operation bounds, not OS memory/disk quotas or hostile-code isolation.

An absent checkpoint returns the unchanged SDK sentinel
`{"checkpoint_id":"progress","revision":0,"value":{}}`. This sentinel is not
stored content and is exempt from the declared value-size test, so an absent
checkpoint can be read even with a one-byte declaration. An actual stored `{}`
is two UTF-8 bytes and cannot be written under that one-byte limit. Existing
oversized/incompatible stored values are preserved but not exposed by a scoped
read; the adapter does not truncate, migrate or erase them automatically.

## Exact resources and current authority

Separate resource scopes are `checkpoint:<id>:read` and
`checkpoint:<id>:write`. Read-only declarations request read; read/write
declarations produce both exact operation resources. Read access never implies
write access. Internal subject/context/policy/selection **version 6** adds up to
64 checkpoint operation resources and a 196-entry overall scope ceiling; existing
internal versions 1–5 retain their previous shape.

Every resource binds the whole declaration to the Core-resolved
Core installation/application installation/incarnation/module principal and
exact package SHA-256. The complete resolved request rejects duplicate operations,
incomplete read/write pairs, altered declarations and mixed owners. Mixed
checkpoint/private-file/relational requests retain the same current owner and
package; one family's grants never stand in for another's.

Installed-source reconstruction and the existing protected local native-review
→ administrator review → separate approve → apply → revoke cycle are reused.
Declarations, schema/catalog entries, native trust and human roles are not grants.
The package cannot submit an owner, Core token, approved revision or human admin
identity. Current key/configuration/artifact/incarnation/recovery generation,
native trust, active installation and exact applied grant are checked at runtime;
opted-in denials never fall back to compatibility execution.

The administrator dialog presents checkpoint IDs, modes, exact value bounds,
owners and Core/incarnation/package bindings in EN/BG. It exposes no checkpoint
contents, payload editor, browser storage or direct SDK/key operation. Explicit
resource acknowledgment, approve, apply and revoke remain separate; opening and
refreshing are read-only. Existing conservative SQL runtime warnings stay separate
when a review also contains relational storage.

## Runtime, SQL compare-and-swap and uncertain replies

Existing public SDK signatures and result shape are unchanged:

```python
platform.get_checkpoint("progress")
platform.put_checkpoint("progress", {"page": 2}, expected_revision=0)
```

These use existing signed local `checkpoint.get` / `checkpoint.put` transport.
The dispatcher fixes the installation from the authenticated instance; scoped
requests have a closed field set and cannot select paths or owners. Runtime
grant admission and revocation use the existing Core key → authority guard order.
There is no HTTP checkpoint-content endpoint or new generic broker.

A write conditionally updates one row by **installation + checkpoint ID + expected
revision** in one SQL `UPDATE`, incrementing revision by one. Expected revision
must be a nonnegative integer below `2**53 - 1`. Creating an absent row requires
expected revision zero and the existing owner/ID unique constraint; competing
creates or stale writes fail rather than overwriting current state. An unexpected
SQL row count is refused. Compatibility access is preserved, but its old
read/assign race is also strengthened to the same atomic CAS. Legacy admissions
are linearized against disable/adoption without manufacturing scoped grants.

The SDK does not retry. A stale revision conflicts even if the caller repeats
the same value. Lost acknowledgment may mean the write committed; callers must
read current state and reconcile revision/value before any separately intended
new action. Checkpoint results and the machine audit below are **not Core
idempotency receipts**, do not establish exactly-once delivery and do not provide
a replay endpoint. No external/physical work is replayed by this adapter.

## Atomic, redacted machine audit

Successful scoped writes add a sealed completed **machine Action** in the existing
authority journal. It records application actor/principal, exact scope/package,
checkpoint ID and expected/new revisions, never the value, login token, key or
caller-selected receipt. Reads do not create checkpoint-write audit entries.

An SQL `count` bounds this operation at **4096 total existing Action rows for the
installation**, not 4096 checkpoint rows in addition to other lifecycle/evidence
records. At the cap the write fails closed. It never scans the whole journal into
memory, prunes evidence automatically or reuses an old action as write authority.
Checkpoint change and sealed audit commit together under the admission guard;
audit failure/cap exhaustion rolls back the checkpoint mutation as well. This is
not an unrestricted human-admin audit writer.

## Relational lifecycle compatibility and explicit limits

The prepared relational start-consent reader explicitly selects its historical
subject/policy model for version **5** (SQL-only) or **6** (mixed checkpoints).
It still independently checks current trust, exact grant revision, resource
identity and signed historical start consent. This is a compatibility adapter,
not a new start/boot/SQL/migration permit or bypass of the existing explicit
prepared lifecycle. Generic relational adoption/activation guards remain closed.

The public schema catalog reports checkpoint declaration validation and
`reviewed_native_scoped_local` authority with SDK 1.3 and local-only native-trust
administration. Schema validity is not installation availability or authorization.
No DB model/Alembic migration, dependency, SDK/manifest/Core version or new
installation path is introduced. This slice changes no user VM services, values,
keys or rights, and performs no commit, push or release.

Identity/peers/status operations, jobs/public routes/provides and the public
frontend operation bridge remain separate scoped contracts. The next bounded
platform work is **identity/peers/status**, not another checkpoint implementation.
Public/kiosk/operator/admin and consolidated neutral Standalone/local-Agent/Hub
acceptance, supported broader recovery and WP5 isolation remain separate gates.
The already accepted bounded beta.51 SQL upgrade/recovery scenario is retained;
this checkpoint work neither reopens it nor extends its evidence to a general
installer, portable restore or Hub acceptance.

## Verification — local, not deployment acceptance

- Full frontend suite: **344 passed / 46 files**, one worker, with type-check and
  production build passing. Included focused coverage is **70** cases: 50 dialog,
  11 relational DTO and 9 checkpoint DTO tests; do not add those again to 344.
  Checkpoint DTO tests cover exact IDs/types/limits, complete operation pairs,
  mixed owners, unknown fields/payloads, maximum counts and historical rejection.
  Component cases verify EN/BG resource cards, disabled approval before explicit
  acknowledgment and distinct approve/apply, with no live backend credentials.
- Final broad Windows protocol/SDK/authority-context/policy/advisory regression:
  **998 passed / 22 expected Linux-specific skips / 10 warnings**, exit 0. This
  run includes the final checkpoint catalog runtime-support change. The earlier
  overlapping 494-case run is not added to this total. Windows skips do not
  stand in for the separate native Linux execution below.
- Final native Linux verification: **310 distinct passing cases** across three
  runs on the same final source. Primary runtime/authority/CAS/signed-SDK and SQL
  activation regression has **204 passed / 15 root-only skips**; all 15 were then
  executed as actual Root, **15 passed / 55 already-covered cases deselected**.
  The disjoint event publication/consumption, file execution/review API/status
  compatibility run has **91 passed**. Thus `204 + 15 + 91 = 310`; no native skip
  remains in this selected coverage. All six new mixed SQL/version-6 historical
  start-consent cases are included. The Linux total includes 27 pure context
  cases also present in Windows; cross-platform counts are not a unique global
  sum, and the focused frontend cases are not added again.
- Native execution used Python **3.14.4**, private unshared mount namespaces and
  private `/tmp`, disposable native `/var/tmp` source snapshots, non-root UID
  **1000** and actual Root helper runs with non-root application UID **1200**.
  It covers current-grant refusals, actual concurrent SQL CAS, machine-audit cap
  rollback, signed socket/lost reply and legacy compatibility. An earlier
  diagnostic run found three fixture/assertion errors: a key-identity attribute,
  expected 403 instead of the actual 401 denial, and an outdated assertion that
  checkpoints were unsupported. Those were corrected before the full 219-case
  primary rerun and separate Root/compatibility runs; production denials and
  assertions were not weakened to obtain green results. Existing warnings were
  not suppressed. Logs/JUnit are ignored under
  `.runtime/m20-checkpoints-{linux,root,compat}.{log,xml}`. VM services, system
  users and production data/keys/grants were untouched.
- Browser fixture inspection: light/EN, Graphite Mint dark/BG and 390px mobile;
  exact cards/bindings, wrapping and unchecked/disabled approval were inspected.
  Mobile dialog content width and scroll width are both **325px**, without
  horizontal overflow. Screenshots are ignored under
  `.runtime/m20-relational-ui/checkpoints-*.jpg`; the tab remains available for
  separate owner visual review. No fixture result is live VM/Standalone/Hub
  acceptance.

The full release workflow and explicit owner VM acceptance were not requested
or performed by this slice. These are selected regression runs, not the full
Python release suite or live Standalone/Hub acceptance. **WP4 and Milestone 20
remain open** for the stated contracts/acceptance, not because these bounded
checkpoints require a new WP.

## Authoritative source and regression references

- [Application descriptor](../three_mm_protocol/application_extension.py),
  [schema catalog](../three_mm_protocol/extension_schemas.py),
  [protocol/strict-JSON tests](../three_mm_protocol/tests/test_application_checkpoints.py).
- [Resolved context](../backend/services/application_authority_context.py),
  [policy subjects](../backend/services/application_authority_subjects.py),
  [source resolver](../backend/services/application_authority_sources.py),
  [policy evaluator](../backend/services/application_authority_policy.py).
- [Review/apply and machine audit](../backend/services/application_authority_management.py),
  [existing administrator route](../backend/routes/application_authority.py),
  [checkpoint context tests](../backend/tests/test_application_checkpoint_authority_context.py),
  [installed authority/API tests](../backend/tests/test_application_checkpoint_authority.py).
- [Checkpoint engine](../backend/services/application_checkpoints.py),
  [signed dispatcher](../backend/services/application_platform.py),
  [existing SDK](../three_mm_application_sdk/__init__.py),
  [runtime/CAS/socket tests](../backend/tests/test_application_checkpoints.py).
- [Prepared start-consent compatibility](../backend/services/application_relational_activation.py),
  [activation regression](../backend/tests/test_application_relational_activation.py).
- [Administrator dialog](../frontend/src/components/extensions/ApplicationAuthorityDialog.vue),
  [checkpoint DTO tests](../frontend/src/components/extensions/authority-checkpoints.test.ts),
  [component tests](../frontend/src/components/extensions/ApplicationAuthorityDialog.test.ts).
- [Accepted bounded beta.51 SQL evidence](EXTENSION_PLATFORM_V2_RELATIONAL_UPGRADE.md#owner-vm-beta51--accepted-bounded-upgraderecovery-2026-10-15),
  [WP4 closure audit](EXTENSION_PLATFORM_V2_WP4_CLOSURE_AUDIT.md).
