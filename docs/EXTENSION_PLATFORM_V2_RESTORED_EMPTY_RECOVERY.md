# WP4 — restored-empty initial preparation recovery

Status: delivered in **beta.50**, not included in beta.49 and not live WP4 closure.
SDK 1.3 / Device Protocol 1.0 / Core schema unchanged. A separate
owner-approved development trial below now accepts recovery/preparation on the VM;
it does not turn these commands into an installed beta.49 feature.

## Disposable VM development trial — no second release

On 2026-10-14 the owner approved testing with a separate protected, root-owned
code snapshot outside `/opt/3mm/current` and `/opt/3mm/releases`. The snapshot pins
the beta.49 commit, only the reviewed recovery deltas and shared protocol resources;
its file hashes/protection are checked before use. It uses the existing installed
interpreter/dependencies. No permanent helper replacement, drop-in, listener,
Core/Agent/Web restart, source branch or new release is involved.

A temporary local launcher authenticates to the existing loopback Core before
starting each restricted one-shot root unit. Tokens travel only through private
stdin pipes, never argv, environment, logs or saved files. The root worker uses
the actual Core service UID metadata worker and the same mutation locks and
filesystem/kernel/UID-switch protections. Each effect is a separate explicit
command; there is no SQL/start/grant chain or automatic retry.

Actual results for the neutral relational fixture:

- Recovery `b5560287efa54697972437834b042f70` is confirmed with
  `restored_empty_not_started`; the old failed source remains uncertain and all
  old checkpoint bytes/key/wheel are retained.
- Separately approved preparation `718b87f2a29f45b7afd276ce608947a9` is durably
  `prepared_not_started`, schema `0001`, zero business probe rows.
- The **installed beta.49** prepared-lifecycle reader accepts the new state and
  verifies the unchanged original key. No pending rollback remains.
- Beta.49 symlink/code, four installed service states and Agent identity are
  unchanged. The fixture is still disabled/inactive with MainPID 0.

This accepts the bounded recovery/preparation development trial, not a new-artifact
installation path, official deployed fix or complete WP4 acceptance. Continue with
beta.49's existing explicit activation, fresh rights decisions and signed SDK
execution tests; consolidate the actual Core changes into one later release.
Temporary trial source/launchers and redacted evidence stay outside release assets.

## Exact boundary

This covers an initial `prepare_migrated_schema` attempt with a sealed Core action
still `execution_unconfirmed`, a completed matching namespace action, and a root
rollback checkpoint whose phase is exactly `restored_not_started`. Both database
and private-file preimages must prove absence; live `data` and `run` must be empty.
There must be no database, sidecars, candidate files, active/relational metadata,
foreign checkpoint, changed wheel/key, links or unknown lifecycle content.

It is generic across relational application packages. There is no concrete test
module name in Core, public API, permission fallback or normal activation bypass.
It is reviewed-native lifecycle management, **not a hostile-code sandbox**.

Recovery checks current local administrator/session, native review, grants,
installation/incarnation/package/configuration/profile, source revision and
recovery generation. The outer ticket has a fresh five-minute boot-bound budget;
expired historical source tickets are never renewed or used to authorize SQL.
Release/runtime mutation locks serialize the root helper. The actual systemd
adapter stops/disables the unit and verifies quiescence before file work.

Only the exact rollback is renamed to protected `.preparation-evidence-*`
storage. All its bytes, the staged wheel, namespace witness and existing transport
key are retained. The original Core action stays uncertain, with no invented
completion receipt; its old helper is superseded. Recovery itself never opens
SQLite, imports package code, creates a key, grants rights or starts/enables a unit.

A separate pending recovery marker fences preparation/start and encrypted
backup/restore until the new Core confirmation is acknowledged and local confirmed
evidence is published. A lost finish response or interruption after the source
rename remains blocked. A **new explicit** recovery ticket can reconcile validated
old recovery markers; their uncertain records are archived unchanged, not relabeled
successful. An empty/unrecognized marker, unknown/candidate data or changed source
requires investigation; this is not arbitrary partial-file repair or deletion.

## Installed procedure — beta.50 or newer

Use the existing hidden-token `core_authority` wrapper as the Core service account.
Keep an independent pre-test VM snapshot and all failed-operation evidence. These
are templates; persist fresh request IDs and use actual returned opaque revisions.
`grant_revision` (integer) is not `grant_record_revision` (32-hex string).

1. Check release/Core/Agent/helper health and unchanged identity. Read current
   fixture status and ensure the installation is disabled. Inspect the exact
   migration and namespace sources:

```text
core_authority inspect-relational-preparation \
  --installation-id INSTALLATION_ID \
  --source-preparation-id FAILED_DATABASE_PREPARATION_ID \
  --source-namespace-id COMPLETED_NAMESPACE_PREPARATION_ID \
  --expected-grant-record-revision CURRENT_GRANT_RECORD_REVISION
```

2. After reviewing the restored-empty evidence, explicitly reconcile it:

```text
core_authority recover-relational-preparation \
  --installation-id INSTALLATION_ID \
  --source-preparation-id FAILED_DATABASE_PREPARATION_ID \
  --source-namespace-id COMPLETED_NAMESPACE_PREPARATION_ID \
  --expected-preparation-revision INSPECTED_SOURCE_REVISION \
  --expected-grant-record-revision CURRENT_GRANT_RECORD_REVISION \
  --request-id FRESH_RECOVERY_REQUEST_ID \
  --confirm-restored-empty-checkpoint
```

Require `restored_empty_not_started`, with no database/start and unchanged key.
Save `recovery.preparation_id`. A refused/unconfirmed result is a stop condition,
not authority to retry, delete a marker, invoke generic Install/Activate or SQL.

3. Inspect the new sealed recovery revision:

```text
core_authority inspect-relational-preparation-recovery \
  --installation-id INSTALLATION_ID --source-recovery-id RECOVERY_REQUEST_ID
```

Require `state: confirmed`, `resumption_reserved: false`; this metadata alone does
not prove the local pending marker has been cleared. Keep the existing valid native
review and explicitly review/apply current resources if their bindings changed.

4. Separately authorize one new migration attempt in the retained empty namespace:

```text
core_authority resume-relational-preparation \
  --installation-id INSTALLATION_ID --source-recovery-id RECOVERY_REQUEST_ID \
  --expected-recovery-revision INSPECTED_RECOVERY_REVISION \
  --expected-grant-record-revision CURRENT_GRANT_RECORD_REVISION \
  --request-id FRESH_DATABASE_PREPARATION_REQUEST_ID \
  --confirm-owned-business-migrations
```

This is new consent, **not replay** of the failed worker. Both sealed Core recovery
and matching protected confirmed local evidence are required. It reserves the
source one-use, checks the UID-switch prerequisite before issuance and rechecks
the restored-empty witness under mutation locks. It keeps the same key, creates a
new preparation lineage and executes migrations only through the existing bounded
non-root worker. Require `prepared_not_started`; use
`preparation.preparation_id` as the **new database preparation ID** for the fixture's
separate `activate-relational` step. No boot/start or runtime grant is implied.

After start, perform fresh resource review/approve/apply and the normal fixture
SQL/replay/conflict/boundary/revoke/restart checks. Updating Core or successfully
reconciling this checkpoint does not complete the relational acceptance.

## Out of scope

Nonempty/previous database restoration, candidate SQL outcome recovery, schema
upgrades, key rotation/portable restore, general corrupt-marker repair and public
relational installation remain separate gates. No installed state is changed by
the local test suite or by publication of this implementation.

## Local verification — 2026-10-14

- Isolated Linux/root regression selection: **198 passed**, covering new recovery,
  existing preparation/namespace recovery/first installation, helper transport
  (including actual kernel peer credentials) and relational wire contracts.
- Separate actual Core-UID metadata-worker/CLI and actual non-root migration
  integration: **1 passed**. Both inspect commands and recovery/resumption use the
  installed fixed dialect; no live systemd/account/VM changes. Its first harness
  run waited on an inherited terminal; the CLI subprocess now uses a separate
  session and the complete case passes. Production timeouts/guards were unchanged.
- Windows transport/helper/wire regression: **62 passed, 3 expected POSIX skips**.
- Frontend production build and Black/isort checks for the new Python files pass.

Tests include stale/superseded human/source/grant/native/epoch/generation/clock
authority, closed ticket purposes, unknown/nonempty/candidate/link/key/wheel
refusal, lost finish acknowledgement on both sides of Core commit, interrupted
source rename, retained original bytes and separate one-use non-root resumption.
Early development runs caught the missing private signing-purpose allowlist and
a duplicate-request test using a changed CAS; both were corrected before the
passing regression run. Existing dependency/datetime warnings remain visible.
This is targeted verification, not the complete release suite or live acceptance.
