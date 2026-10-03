# C8 — Migration, recovery and mixed-version compatibility

Implemented and checked locally 2026-10-03. This is the common Device/Node
Platform, not a Fleet migration. Transport `1.0`, HTTP `/api/v1` and Application
SDK `1.3` are unchanged. No deployment, re-pairing, release or Git operation.

## Additive persistence

The existing C2/C5 migrations form one linear chain:

`526ab1c2d3e4 -> 637bc2d3e4f5 -> 748cd3e4f5a6`.

They add `device_capability_providers` and `device_runtime_features`; they do
not rewrite identities, credentials/hashes, desired revisions or installed
modules. Existing module capabilities continue through the same compatible
provider adapter, without backfilling fake installations or firmware providers.
Missing feature declarations remain `legacy_unadvertised`, not fabricated
support. No additional migration or data deletion was needed for C8.

The existing clean migration and populated-upgrade tests check the Alembic
schema against ORM metadata. Scratch-database downgrade tests verify removal
of the new tables without altering old device rows. They are **not** a
production rollback procedure: dropping these tables loses their new data.

## Supported compatibility matrix

| Scenario | Policy and local evidence |
| --- | --- |
| Updated Core + legacy Linux wire client | Inventory 1, existing credentials/modules/state and module capability adapter remain usable; no runtime declaration is invented. The HTTP/module coexistence test also includes an independent firmware provider. |
| Updated Agent + older Core without negotiation | Only `404`/`405` permits inventory 1 fallback. No feature PUT, credential replacement, re-pairing or binding rewrite. Other failures remain fail-closed as specified in C5. |
| Updated Core + updated Linux / independent runtime | Existing shared device contracts and provider registry; C3/C5 coexistence remains the baseline. |
| Older encrypted/portable backup -> updated Core | Known ancestor revision migrates to head after staging/switch. Device credentials, desired state, modules and Agent files survive. |
| Current mixed-runtime backup -> updated Core | Device registry, credentials, firmware provider revision/Core-owned disable and runtime declarations survive encrypted export/import/restore. |
| Current-schema backup -> older release | Preflight rejects an unknown migration revision even if the application version strings match. No forced stamp, downgrade or state replacement. |
| Restore activation/health failure | Existing transactional recovery returns the previous database and Agent files; status is `rolled_back`. No partial provider/credential state is accepted. |

Legacy-client tests exercise the old wire/feature adapter using the current
publisher and simulated endpoint absence. They do not claim that archived
release binaries were booted. Portable recovery uses real AES-GCM/password
export/import, actual Alembic migrations and filesystem switching; service
stop/start and health outcomes are injected locally, not live systemd tests.

## Historical rows outside C7 bounds

Migration preserves historical data even when new Node message validation
cannot safely transmit it. It must not silently truncate payloads, reset
revisions or replay old work.

- Invalid/oversized stored desired state now returns `409` with
  `code=stored_desired_state_invalid` and its preserved revision, instead of
  `500`. The same diagnostic is available on the administrative state read.
  Back up the original data first; an administrator can deliberately replace
  it with a supported bounded state using the existing PUT and exact
  `expected_revision`. That explicit update increments the revision normally.
- A stored command is validated before acquiring a new delivery attempt. If
  invalid and proven never delivered, it becomes failed with
  `execution_state=not_dispatched` and `recovery_code=stored_command_invalid`;
  its original payload remains in the database. Related module lifecycle
  status is updated consistently. Poll returns an explicit `409`, not `500`.
- Previously dispatched invalid work keeps its existing delivery/result
  evidence and returns a recovery conflict. It is not relabeled unexecuted,
  automatically replayed or used to release an uncertain Node Update gate.
  Existing operator recovery/independent outcome validation still applies.
- Invalid/oversized historical Agent receipts are retained individually rather
  than stopping the whole publisher or being mistaken for cache misses. Their
  commands return `unknown / legacy_receipt_invalid` without executing. Saving
  unrelated new receipts preserves the original raw record; overwriting the
  unverified key is refused. A structurally unreadable journal still fails
  closed and needs recovery, not automatic deletion.
- A rollback-era write to the original receipt map can invalidate a retained
  proof. The updated publisher detects that conflict instead of trusting stale
  success or repeating the action. Original credential/result file schemas
  remain readable; the new binding/proof files are sidecars.

Administrative history and encrypted backups retain the original evidence.
This is bounded transmission plus explicit recovery, not permissive exceptions
that weaken C7 for new messages. Oversized old outbox entries likewise remain
pending when Core rejects them; C8 does not silently discard their evidence or
provide a new general-purpose quarantine editor.

## Release rollback versus restore

For a failed immutable installation, retain the installer’s existing release
link, environment and pre-upgrade SQLite snapshot rollback. Do not replace it
with an in-place Alembic downgrade. The old release cannot implement new
firmware/provider contracts merely because its database has extra tables.

Returning to a pre-upgrade snapshot returns **that snapshot's state**, not
changes made afterward. Save a current compatible encrypted backup before any
intentional rollback. Restore a newer backup only with a release whose catalog
knows its revision; then upgrade normally. Preserve Agent identity/credentials,
module state, receipts, bindings and outbox together. Never copy a device secret
to a second simultaneously active device to simulate recovery.

The existing Standalone archive includes the entire persistent Agent area,
including `core-binding.json`, receipt proofs and outbox, without a new archive
format or allowlist. The portable tests compare the restored files and relevant
device/module/provider tables with the original snapshot, including hashes and
revision/disable semantics.

This stage does not add Node-only or Hub-profile backup support. The existing
Standalone recovery can contain records for its remote Linux/embedded nodes;
it does not archive those nodes' own files, firmware credential storage or
flash. Device protocol compatibility is common across roles; installation
backup product scope remains the existing separate policy.

## Focused evidence

Windows/Python 3.13 final gate: **61 passed, 1 skipped in 72.70s**, with 45
existing dependency/deprecation warnings. The skipped POSIX storage check is
not executable on Windows; live Pi file permissions are not claimed. New C8
test files pass Black; changed tracked files pass whitespace checks.

Reproduce from the repository root, PowerShell:

```powershell
$c8Tests = @(
  "agent/tests/test_node_compatibility.py"
  "backend/tests/test_node_compatibility.py"
  "backend/tests/test_node_recovery_compatibility.py"
  "backend/tests/test_device_capability_provider_migration.py"
  "backend/tests/test_device_runtime_feature_migration.py"
  "backend/tests/test_migration_history.py::test_clean_database_migrates_to_head_and_back_to_base"
  "agent/tests/test_core_client.py"
  "agent/tests/test_node_security.py"
  "backend/tests/test_device_command_routes.py"
  "backend/tests/test_device_state_routes.py"
  "backend/tests/test_node_update_delivery_route.py"
  "backend/tests/test_node_update_approval.py"
)
.venv\Scripts\python.exe -m pytest -q @c8Tests --tb=short
```

[C9](PLATFORM_NEUTRAL_C9.md) now verifies simultaneous Linux/independent runtime
and application execution locally, including the optional signed-permit contract;
deployed consumer checks remain pending. C8 adds no ESP code, separate device subsystem, firmware OTA or physical
hardware claim. No frontend files or unrelated application extension changed.
