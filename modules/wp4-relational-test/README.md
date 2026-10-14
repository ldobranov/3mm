# WP4 Relational Test — explicit disposable-VM acceptance

Separate, headless Manifest v2 package `org.3mm.wp4-relational-test` / `1.0.0`.
Application SDK stays **1.3**. This is not a replacement/update of `wp4-test`,
not a bundled Core extension and not a claim that WP4/M20 is finished.

The factory and health check do not open SQLite, import migrations or request
permissions. Only an explicit protected migration creates `probe_writes` in
the host-owned database. Explicit administrator operations use the scoped SDK;
legacy/direct SQLite and files are refused. No frontend, menu, devices, secrets,
connectors, publications, subscriptions, jobs or external actions are declared.
Reviewed-native code is **not a sandbox**; bounds are cooperative, not disk quotas.

## Exact requested limits

| Parameter | Value |
| --- | --- |
| Own database | 1 MiB |
| Auxiliary pause threshold | 256 KiB |
| SQL statement / value / result | 2 KiB / 1 KiB / 4 KiB |
| Result rows / transaction / busy wait | 16 / 5 s / 500 ms |
| Synthetic business records | At most 16, text at most 256 characters |

The 16-record bound is fixture logic, not a new Core option. There is no destructive
reset/delete operation. Use synthetic text only; no customer or personal data.

## 0. Build and read-only preflight

Use only the disposable Ubuntu/WSL VM, with a verified recoverable pre-test backup
and an independent VM snapshot. A snapshot is particularly important because
general relational portable restore/rollback/rekey remains unfinished. Do not run
two active clones with one device identity. Do not alter `/opt/3mm/releases` permissions.

From the development checkout (with development dependencies available):

```bash
cd /mnt/c/Users/LAZ-DELL/Desktop/3mm
PYTHONPATH=. python3 modules/wp4-relational-test/build_test_package.py \
  --output dist/wp4-relational-test-1.0.0.zip

python3 modules/wp4-relational-test/probe.py preflight
```

The builder validates the final ZIP with Core's existing validator and prints
its **ZIP SHA-256**. The wheel has a separate digest, included in the definition.
The delivered ZIP normalizes line endings, timestamps and wheel RECORD hashes.

Preflight reads version, service state, existing `3mm` / `3mm-app` UID/GID and
the test instance's systemd template principal/state. It creates no account,
namespace, key, grant or service. `ready_for_catalog_only` is **not** authority,
path-access, executable-review, prepared-database or startup approval.
It expects a fresh stopped/disabled test unit; after starting/enabling this fixture,
this first-install preflight deliberately reports blocked.

**Stop** if accounts are missing/root/shared, the unit is unavailable or already
running/enabled, or any service is unhealthy. Account provisioning remains a
separate Core gate. Do not use `useradd`, root execution, numeric UID overrides,
`chmod`, grant SQL edits or manual database bootstrap to make the check pass.

Beta.48 is the first release containing the explicit CLI controls used below.
Record actual version, Agent device ID, ZIP digest and each returned ID/revision.

## 1. Upload to the catalog only, then explicit inert registration

Do **not** use ordinary application Install/Activate/Enable for this package;
generic relational activation is intentionally closed. Inspect the ZIP in
Extensions first if desired. Inspection grants nothing.

The explicit helper below calls **only** the existing module-package upload
endpoint. It verifies the exact local ZIP digest before prompting for credentials.
Replace `EXACT_ZIP_SHA256` with the builder's actual digest:

```bash
python3 modules/wp4-relational-test/probe.py upload \
  --package dist/wp4-relational-test-1.0.0.zip \
  --expected-sha EXACT_ZIP_SHA256 \
  --confirm-catalog-upload-only

python3 modules/wp4-relational-test/probe.py catalog
```

Use the **Core administrator** credentials, not the Linux login. The helper uses
only `http://127.0.0.1:8887`, disables proxy/redirect forwarding, never prints or
stores passwords/tokens, bounds replies and never retries. Upload changes the
catalog/persistent uploads only; it does not register/start/import an application.
After an unavailable upload reply, inspect catalog first; do not upload blindly.

The public catalog/upload DTO exposes `module_id`, `version` and `sha256`, **not**
the numeric internal package ID required by `register-relational`. The helper does
not invent an ID or infer it from list position. Obtain the exact ID through a
read-only local Core-account lookup, matching both the module ID and ZIP digest:

```bash
sudo -u 3mm /opt/3mm/current/.venv/bin/python - <<'PY'
import sqlite3
from contextlib import closing

with closing(sqlite3.connect(
    "file:/var/lib/3mm/core/3mm.db?mode=ro", uri=True, timeout=3
)) as db:
    db.execute("PRAGMA query_only=ON")
    rows = db.execute(
        "SELECT id, version, sha256 FROM module_packages "
        "WHERE module_id=? AND sha256=? LIMIT 2",
        (
            "org.3mm.wp4-relational-test",
            "e3afeeba492b1eb30351ebbf8229c27fa1337ccd940f575bba9b96f2f09157d0",
        ),
    ).fetchall()
    if len(rows) != 1 or rows[0][1] != "1.0.0":
        raise SystemExit("STOP: exact catalog package is unavailable or ambiguous")
    print({"package_id": rows[0][0], "version": rows[0][1], "sha256": rows[0][2]})
PY
```

The example digest is for this delivered ZIP; compare it with your actual build.
This lookup writes nothing and does not execute application code. Do not edit
catalog/installation/grant rows to bypass registration or authorization.

Define the same local Core administration wrapper used by the private-file test:

```bash
core_authority() {
  sudo systemd-run --quiet --pty --wait --collect \
    --property=User=3mm --property=Group=3mm \
    --property=NoNewPrivileges=yes \
    --property=EnvironmentFile=/etc/3mm/3mm.env \
    --working-directory=/opt/3mm/current \
    --setenv=PYTHONPATH=/opt/3mm/current \
    /opt/3mm/current/.venv/bin/python \
    -m backend.services.application_authority_admin "$@"
}
```

The CLI prompts for a current Core administrator token **hidden**. Never pass it
in command arguments, shell history, environment variables, files or chat.
Keep the existing valid review key; this test does not rotate/recover it or
automatically create another one. A missing/unavailable key is a stop condition.

The following are **templates**, not paste-ready commands. Substitute only actual
returned values; `PACKAGE_ID` is not an installation ID. Persist a fresh 32-hex
registration request ID before running:

```text
core_authority register-relational \
  --package-id PACKAGE_ID --artifact-sha256 EXACT_ZIP_SHA256 \
  --request-id REGISTRATION_REQUEST_ID --confirm-register-without-start
```

Require `registered_not_started`, `active_version: null`, a newly registered
installation and no app process/database. Preserve the result. Numeric installation
IDs can be reused after uninstall; verify module ID, exact artifact, registration
ID and incarnation, not the integer alone. Old native reviews/grants do not authorize
the new subject, even if historical grant metadata remains visible.

## 2. Actual code review and explicit preparation

A trusted reviewer must review the exact service/migrations/wheel and retain a
local document. This README is instructions, **not a completed-review attestation**.
Only after the review and explicit acceptance of native host risk:

```text
core_authority native-review \
  --installation-id INSTALLATION_ID --artifact-sha256 EXACT_ZIP_SHA256 \
  --review-document ACTUAL_COMPLETED_REVIEW_DOCUMENT \
  --code-review-completed --accept-native-host-risk
```

**beta.48 UI limitation:** the management dialog does not yet accept relational
scope/resource DTOs. Do not use its private-file controls for this package or
modify browser validators. The separate `authority_probe.py` uses Core's **existing**
administrator API for this exact fixture. It never records native trust, starts
a service, creates a key, retries or chains permission decisions.

Persist different request IDs for these three separate actions. These are templates:

```text
python3 modules/wp4-relational-test/authority_probe.py review \
  --request-id REVIEW_REQUEST_ID --native-review-id ACTUAL_NATIVE_REVIEW_ID \
  --expected-sha EXACT_ZIP_SHA256

python3 modules/wp4-relational-test/authority_probe.py approve \
  --request-id APPROVE_REQUEST_ID --plan-id ACTUAL_PLAN_ID \
  --expected-revision REVIEW_RESULT_REVISION --fingerprint REVIEW_RESULT_FINGERPRINT \
  --confirm-reviewed-rights

python3 modules/wp4-relational-test/authority_probe.py apply \
  --request-id APPLY_REQUEST_ID --plan-id ACTUAL_PLAN_ID \
  --expected-revision APPROVE_RESULT_REVISION --fingerprint REVIEW_RESULT_FINGERPRINT \
  --confirm-reviewed-rights
```

Review must show the exact ZIP and only the two own-database read/write resources
and declared limits above. Read those resources before Approve, and explicitly
decide Apply afterward. The approve response supplies a **new** revision for apply.
Approval alone must not create effective access. Each command prompts for current
Core credentials; permissions/native/session/expiry/fingerprint checks remain in
the real Core API. Do not use this fixture helper for business extensions.
There is no implicit trust/apply just from uploading or inspection.

Read current state:

```bash
python3 modules/wp4-relational-test/probe.py status
```

Expect disabled/stopped, reviewed `enforced` mode with an active preparation grant,
but `grant_effective: false` while disabled. Save `grant_record_revision` and use
it exactly, not `grant_revision` (integer), in preparation:

```text
core_authority prepare-relational \
  --installation-id INSTALLATION_ID \
  --expected-grant-record-revision CURRENT_GRANT_RECORD_REVISION \
  --confirm-fresh-owned-namespace --confirm-owned-business-migrations
```

Require `prepared_not_started`. Save the **database** preparation ID from
`preparation.database.preparation_id`, not the namespace preparation ID.
No boot enabling, application start or post-start permissions should occur here.
Package migrations run as the existing non-root application principal, not root.

On any refused/unconfirmed preparation: stop, retain the whole redacted result
and all helper recovery evidence. Do not repeat preparation, delete markers or
fabricate an empty namespace. Partial/nonempty recovery needs its own review.

### beta.48 live prerequisite failure and unreconciled checkpoint

On the owner's VM, catalog upload, inert registration, native review and a fresh
relational review/approve/apply succeeded. First preparation created the namespace
and key, then failed to change to the non-root migration UID inside the deployed
helper's `NoNewPrivileges`/`ProtectKernelTunables` hardening. The helper rolled back
to no database/active metadata and retained the migration rollback checkpoint;
Core still correctly records `execution_unconfirmed`, not a completed preparation.

The local fix explicitly retains **only `CAP_SETUID`** across helper exec and
checks effective `CAP_SETUID`/`CAP_SETGID` before namespace/key/ticket or migration
effects. Existing hardening stays on. A separate real systemd regression proves
the dropped-UID migration child has no effective/ambient capabilities, no extra
groups and `NoNewPrivileges=1`; without the capability it refuses before effects.
This is a process/deployment prerequisite, not a new SDK permission or app capability.
The exact fixture ZIP/SDK 1.3/protocol remain unchanged. The fix is not yet a
published release and does not alter the VM's immutable beta.48 files.

The interrupted fixture remains stopped with its existing key/evidence. Do not
repeat fresh preparation or delete its rollback marker. beta.48's empty-bootstrap
recovery refuses staged wheels/migration evidence, while its prepared-candidate
recovery requires an already prepared database. Neither is a recipe for this
`restored_not_started` migration checkpoint. Its explicit reconciliation is a
separate remaining WP4 gate; successful isolated launcher tests do not close it.

Verification of this local fix on 2026-10-14: **38 cases passed** under isolated
Linux root, including both real systemd launcher cases (missing prerequisite and
successful non-root SQL with zero child capabilities). The broader migration,
first-installation and two fixture suites passed **95 cases** in a fresh isolated
root run. An earlier run had one signed-SDK gateway refusal; that case passed
alone and the complete 95-case rerun passed without a production-behavior change.
The fixture harness now retains only allowlisted gateway diagnostics and never
retries an operation to make a test pass. Black/isort checks passed. These are
targeted regressions, not full release checks, deployed-fix or recovery acceptance.

## 3. One-shot start and explicit post-start rights

Persist a new activation request ID. With the still-current preparation grant:

```text
core_authority activate-relational \
  --installation-id INSTALLATION_ID --source-preparation-id DATABASE_PREPARATION_ID \
  --request-id ACTIVATION_REQUEST_ID \
  --expected-grant-record-revision CURRENT_GRANT_RECORD_REVISION \
  --confirm-start-prepared-service
```

Require `active_review_required`, healthy non-root service and
`boot_autostart_enabled: false`. Start does not restore/reapply rights. Make a
**fresh** resource review → approve → apply with `authority_probe.py` after start.
Require current
`mode: enforced` and `grant_state: active` in `probe.py status`, then prove SQL
admission with the successful `get`/`put` checks below.

**beta.48 status caveat:** the shared status endpoint intentionally reports
`grant_effective: false` and `runtime_blockers: [relational_runtime_unavailable]`
for relational declarations, including an explicitly prepared/running fixture.
It does not probe the prepared host or advertise generic relational activation.
Do not equate this conservative generic status with private-file effectiveness,
claim the UI verifies relational runtime, edit grant rows or keep reapplying to
turn it green. Use exact grant state plus actual signed SDK execution as the
bounded prepared-runtime proof. A failed SDK call is still a stop condition.

For a lost/uncertain start reply, do **not** retry/start/re-enable with a new ID.
Read exact historical Core metadata, preserving the original activation ID:

```text
core_authority inspect-relational-start \
  --installation-id INSTALLATION_ID --source-activation-id ACTIVATION_REQUEST_ID
```

Historical status/revision is not proof of today's running process. Confirm kernel
process/unit state separately. Preserve recovery evidence for the next reviewed step.

## 4. Synthetic SQL, deduplication and negative boundary

```bash
python3 modules/wp4-relational-test/probe.py get
wp4r_request_id="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
printf 'Save this request ID: %s\n' "$wp4r_request_id"
python3 modules/wp4-relational-test/probe.py put \
  --request-id "$wp4r_request_id" --text "WP4 relational VM test"
python3 modules/wp4-relational-test/probe.py record --request-id "$wp4r_request_id"
python3 modules/wp4-relational-test/probe.py get
```

Expect missing/zero → stored → own record found → found/count one. A repeat of
the exact put must return replayed without another business record. Changed text
under that same ID must return conflict without overwriting it. Repeat/count
checks spend new admitted SQL transactions/SDK receipts; only the **business
effect** is deduplicated. This is not an exactly-once transport promise.

```bash
python3 modules/wp4-relational-test/probe.py boundary
```

Expect blocked: this attempts only `ATTACH ':memory:'` through a read session,
never a foreign real file. A blocked result alone might mean missing admission;
pair it with a successful current `get` and unchanged count to prove the SQL fence.
`unexpected_allowed` is a failed test; stop without repairing or deleting data.

`record` is explicitly labeled `application_record_not_core_receipt`. It requires
current read permission and is not the private-file fixture's signed historical
receipt API or a Core completion acknowledgement. An unconfirmed write may have
committed; save any returned SDK transaction ID and inspect evidence before another
mutation. Do not change IDs/retry automatically to make uncertain results disappear.

Revoke only this fixture's rights via the existing admin API helper:

```text
python3 modules/wp4-relational-test/authority_probe.py revoke \
  --request-id REVOKE_REQUEST_ID --expected-revision CURRENT_GRANT_RECORD_REVISION \
  --confirm-reviewed-rights
```

New get/put must fail or be blocked/unconfirmed. After fresh explicit
review/approve/apply, the original business
record/count must remain and a denied new request must not have appeared.

## 5. Stop-only recovery, reactivation, then separate boot consent

Use the original activation ID and `inspect-relational-start` source revision.
Only after a fresh review of exact current state, persist a new recovery request:

```text
core_authority recover-relational-start \
  --installation-id INSTALLATION_ID --source-activation-id ACTIVATION_REQUEST_ID \
  --expected-activation-revision INSPECTED_SOURCE_REVISION \
  --request-id RECOVERY_REQUEST_ID --confirm-stop-preserve-prepared-state

core_authority inspect-relational-recovery \
  --installation-id INSTALLATION_ID --source-recovery-id RECOVERY_REQUEST_ID
```

Require confirmed `stopped_review_required`; preserve the prepared database/key.
No restart, key replacement, rollback or grants should occur. On an uncertain
stop, do not proceed. This normal healthy-start stop/reconciliation test does
**not** prove a genuinely interrupted start. Fault injection is a separate supervised
disposable-VM step; do not kill the shared update helper/Core or remove markers.

Review/apply current resources while stopped, inspect exact recovery revision,
then explicitly request one new start:

```text
core_authority reactivate-relational \
  --installation-id INSTALLATION_ID --source-recovery-id RECOVERY_REQUEST_ID \
  --expected-recovery-revision INSPECTED_RECOVERY_REVISION \
  --expected-grant-record-revision CURRENT_GRANT_RECORD_REVISION \
  --request-id REACTIVATION_REQUEST_ID --confirm-restart-stopped-prepared-service
```

Require healthy `active_review_required`, no boot enable. Review/apply again
after start; recheck original records/count. For boot use this **new** start ID,
its current `inspect-relational-start` source revision and post-start grant:

```text
core_authority enable-relational-boot \
  --installation-id INSTALLATION_ID --source-activation-id REACTIVATION_REQUEST_ID \
  --expected-activation-revision INSPECTED_CURRENT_START_REVISION \
  --expected-grant-record-revision CURRENT_GRANT_RECORD_REVISION \
  --request-id BOOT_REQUEST_ID --confirm-enable-prepared-boot
```

Require confirmed `boot_enabled_not_started`: enable only, no new process/start,
database mutation or grants. An uncertain enable never means safe-to-retry.
Do not use direct `systemctl enable/start`, symlink changes or manual boot metadata.

Only after separate explicit agreement, restart the disposable VM/WSL (stop other
development work first). Verify real unit PID/UID/GID, Core/Agent readiness and
identity, current grant state, admitted SDK reads and unchanged records/count. Reboot
does not itself permit repairs/regrants. Missing/expired/changed trust must fail
closed before package import. Live restart/refusal and genuine interrupted-start
acceptance remain unclaimed until their actual outputs are reviewed.

## Verification and remaining scope

```bash
python3 -m pytest backend/tests/test_wp4_relational_test_extension.py -q
```

The unit cases check deterministic ZIP/RECORD, metadata-only health, missing
admission/direct fallback refusal, request validation, counts, conflicts, bounds,
ATTACH denial and no write retry after uncertain completion. Unit admission is
explicit test-only, not a production bypass. Disposable Linux root cases use the
exact ZIP, real inert registration/native review/approve/apply, Core-UID metadata
worker, non-root migration/host and post-start review. A separate actual Core-UID
platform server/dispatch proves signed SDK SQL, three protected transaction
receipts with one business record, conflict/ATTACH refusal and revoked admission.
Systemd I/O remains a test adapter, not deployed boot proof. No live
accounts/services/rights are changed.

Targeted validation on 2026-10-14: this fixture plus the unchanged private-file
fixture passed **43 cases under isolated Linux root**, including the actual
non-root processes, and **40 cases on Windows with 3 expected POSIX/root skips**.
The authority-helper cases cover separate decisions, missing consent, changed
artifact/resources/native review/key and unavailable apply without retry.
Black/isort checks pass; legacy dependency/datetime warnings were not suppressed.
These are targeted tests, not another full release suite or live boot acceptance.
The later catalog-helper correction was checked against the actual public
`PackageResponse` DTO (which has no internal `id`): **41 cases passed on Windows,
with the same 3 expected POSIX/root skips**. Black/isort checks passed again.
The previous isolated native Linux run was not repeated for this helper-only change.
The ZIP built on Windows and Linux has the same SHA-256:

```text
e3afeeba492b1eb30351ebbf8229c27fa1337ccd940f575bba9b96f2f09157d0
```

Read-only preflight of the owner's beta.48 WSL VM also passed with distinct
non-root Core/application accounts and an inactive/disabled test unit. No package
was uploaded/registered/prepared/started and no native trust/rights were recorded
by that check. Manual live acceptance must still follow the steps above.

General account provisioning, database upgrade/portable restore/rekey/nonempty
recovery, full Standalone/Hub acceptance and WP5 isolation are still separate.
Neither this package nor its instructions open Core's generic relational gates.

See [authority apply](../../docs/EXTENSION_PLATFORM_V2_AUTHORITY_APPLY.md),
[relational contract](../../docs/EXTENSION_PLATFORM_V2_RELATIONAL_STORAGE_CONTRACT.md),
[closure audit](../../docs/EXTENSION_PLATFORM_V2_WP4_CLOSURE_AUDIT.md).
