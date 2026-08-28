# Milestone 11 report — Recoverable Standalone appliance

Status: in progress; backup, local restore, portable disaster recovery,
administrator UI, diagnostics and bounded retention implemented and deployed
on physical `rasp-3mm` on 2026-08-28. Final clean-media restore acceptance is
still pending.

## Goal

Make one Standalone device safely ownable, diagnosable and recoverable before
Hub/Node orchestration expands the failure surface.

## Stage 1 result

- Added the strict, versioned `BackupManifestV1` shared contract.
- Recorded application, protocol, database revision and architecture
  compatibility metadata.
- Bound a full backup to one stable Agent device identity and Standalone role.
- Required per-file SHA-256, byte size, sensitivity and logical state area.
- Rejected unsafe paths, duplicate entries, incorrect totals and unknown
  fields.
- Required every secret-bearing backup to be device-bound and local-only.
- Completed the production persistent-state inventory and explicit exclusion
  list in [BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md).

## Read-only preview result

- Added an administrator-only backup preview API.
- Scans only allowlisted Core, Agent, provisioning and host-config sources.
- Calculates stable SHA-256 values and rejects symbolic links or files that
  change while being read.
- Reads the installed application version, Alembic database revision, machine
  architecture, Standalone role and stable Agent identity.
- Reports estimated size, available space, required reserve and structured
  readiness issues without creating files or directories.

## Encrypted local backup result

- Added an explicitly confirmed, administrator-only create request and audit
  event.
- Schedules only a fixed root worker through the existing Unix-socket helper.
- Uses the shared release mutation lock and quiesces Core/Agent for a stable
  snapshot.
- Revalidates file checksums after quiescence and restarts services on success
  or failure.
- Streams directly into a root-only AES-256-GCM `.3mmbak` archive; no plaintext
  archive is created.
- Keeps only non-secret operation metadata readable by the Core service.

## Administrator recovery UI and retention result

- Added an administrator-only catalog backed by non-secret metadata sidecars;
  Core never reads the root-only encrypted archives.
- Added a responsive Settings section for readiness, size/free-space preview,
  explicit backup creation, operation state and restore confirmation.
- Keeps the five newest valid backups and prunes only archive/metadata pairs
  inside the fixed backup directory.
- Added English and Bulgarian interface text and component/API coverage.

## Redacted diagnostics result

- Added administrator-only preview and in-memory JSON download endpoints.
- Reports release, platform, storage, SQLite, Agent and backup-operation health
  without reading database rows, environment values, logs or network profiles.
- Replaces common secret fields and inline credential forms before stable,
  sorted JSON serialization.
- Uses a one-way Agent device fingerprint instead of exposing stable identity.
- Added a responsive Settings diagnostics section and English/Bulgarian text.
- Documented the exact inclusion and exclusion boundary in
  [DIAGNOSTICS.md](DIAGNOSTICS.md).

## Portable disaster recovery result

- Added one password-protected `.3mmrecovery` download per local backup.
- Kept the root-only local `.3mmbak` and device key inaccessible to Core.
- Added bounded administrator upload and restore from a portable file after a
  clean installation or failed SD card.
- Authenticates and validates the portable envelope and full inner backup
  before importing it under the new installation's device key.
- Reuses the existing transactional restore, migration, health verification
  and automatic rollback boundary.

## Raspberry review result

- Restored the real local backup `bkp_20260828T114103Z_b47dfc1d` through the
  privileged recovery path and returned all services to a healthy state.
- Deployed immutable review release
  `worktree-50f841dce023-20260828175806`.
- Completed a real password-protected portable export/import round trip on the
  Raspberry using a fresh temporary device key.
- Verified envelope authentication, complete inner-backup validation, private
  export-directory permissions and one-time export cleanup.
- Kept the destructive final acceptance separate: no portable restore was
  applied over the currently running installation during the smoke test.

## Next stage

Download the recovery file through the browser, perform a clean installation,
upload and apply the file, then verify users, settings, dashboards, extensions,
Builder history and stable Agent identity before closing Milestone 11.
