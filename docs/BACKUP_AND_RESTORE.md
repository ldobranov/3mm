# Backup and restore contract

Status: Milestone 11 contract and implemented Standalone recovery boundary.

## Boundary

A Standalone backup represents application state, not an operating-system
image. Software releases remain immutable and reproducible from the official
release channel. NetworkManager profiles and host identity remain owned by the
operating system.

The shared `BackupManifestV1` contract records the exact files, sizes and
SHA-256 digests in a backup together with:

- application, protocol, database and architecture compatibility metadata;
- the originating device identity and Standalone role;
- whether secret material is present;
- whether the backup may leave the device.

All archive paths are relative to one declared area. Absolute paths,
traversal, duplicate entries, incorrect totals and unknown manifest fields are
rejected.

## Persistent-state inventory

| Area | Production source | Contents | Sensitivity | Backup policy |
| --- | --- | --- | --- | --- |
| Core | `/var/lib/3mm/core/3mm.db` | users, settings, menus, dashboards, extension catalog/data, Builder projects, device registry, audit and update policy data | secret | include in device-bound backup |
| Core | `/var/lib/3mm/core/uploads` | user-uploaded assets and module packages | private | include |
| Core | `/var/lib/3mm/core/extensions/backend` | installed backend extension files | private | include |
| Core | `/var/lib/3mm/core/extensions/frontend` | installed frontend extension files | private | include |
| Core | `/var/lib/3mm/core/extensions/compiled` | immutable compiled UI artifacts | private | include so the restored active hash is immediately available |
| Applications | `/var/lib/3mm/application-extensions/<instance>/data` | extension-owned SQLite state, files and transactional outbox | secret | include only the mutable `data` subtree; exclude reviewed code and runtime material |
| Agent | `/var/lib/3mm/agent` | stable identity, Core credential, command journal, outbox, automations and module data | secret | include in device-bound backup |
| Provisioning | `/var/lib/3mm/provisioning` | role, locale, device name and recovery state | private | include, excluding transient scan cache |
| Host config | `/etc/3mm/3mm.env` | deployment overrides and possible provider or service secrets | secret | include only in device-bound backup |

The database is a consistency boundary: it must be captured through SQLite's
online backup mechanism or while the Core service is quiescent. A plain copy
of a live database is not an accepted snapshot.

## Explicit exclusions

- `/opt/3mm/releases`, `/opt/3mm/current` and the virtual environment: restored
  from an official release, not user state;
- `/var/lib/3mm/core/update-staging`, `/var/lib/3mm/update-helper`,
  `/var/lib/3mm/deploy-backups`: transient or independently bounded recovery
  data;
- Wi-Fi scan cache, logs, runtime sockets and temporary files;
- `/etc/NetworkManager`: network credentials and host networking remain outside
  application restore;
- `/etc/machine-id`, SSH host/user keys and general Raspberry Pi OS settings.

## Checking readiness

**Settings → Backup and recovery** initially reads only the local catalog and
operation status, not file contents. **Check readiness** is an explicit
administrator read (`GET /api/v1/backups/readiness`). The browser receives
totals and grouped issues, not private filenames, file hashes or raw errors.
It lists at most 32 application data namespaces, with file counts, sizes and
current catalog matches; extra files are counted separately. Without a valid
manifest the inventory is unavailable, not empty. Installed/retained labels
and the selected package version describe the current catalog, not an inferred
database schema or successful restore. No application is started by this check.

After **Check readiness**, **Save check summary** saves the last result locally;
it does not scan the Pi again. For support, share that small JSON rather than a
recovery file. The summary contains only issue codes/counts, inventory totals
and whether capture was ready. It contains no filenames, application names,
account IDs, free-space readings or keys. Refresh clears that observation.
Read it offline with `python -m tools.diagnostics explain backup-readiness.json`.

For every enabled, active application, preflight checks the catalog's package
owner, active version, instance, checksum-addressed ZIP and nonempty application
database. During restore (also during portable import) the staged ZIP is validated
without running its code. Its declared schema revision must match the SDK ledger
in an intact staged database. A committed SQLite WAL is included when checking
the revision; a temporary copy protects the archived bytes. Missing packages
and mismatched/corrupt active databases are reported before any service is stopped.
Disabled and retained data are not an instruction to start an application.
The separately prepared relational profile is not reconstructed by ordinary
Standalone activation. A full archive can preserve its data, but if it requests
automatic reactivation of such an application, portable import/restore refuses
before stopping services. It never substitutes a different storage mode or
recreates a grant. **Check readiness** now warns about that limitation before
creating an archive. It examines only declarations for current active packages,
using the original content hashes, after closing the catalog connection. The
advisory covers at most 32 packages / 24 MiB of package input and up to 256 KiB
per declaration; anything not verified is reported as such. Disabled packages
and retained data are not inspected as startup requests. Advisory work does
not run while services are stopped for capture. A positive inventory check is
not an activation rehearsal; private staging still performs the full restore checks.

The full manifest remains an explicit, separate administrator interface.
Creation rechecks the files after services are quiesced. The encrypted writer
verifies the bytes as they enter the archive; a changing file aborts publication.
On the supported local Linux filesystem an existing archive or catalog entry
is never replaced on an ID collision. Local retention or erasure does not
delete portable recovery files previously downloaded elsewhere.

## Secret boundary

The first full-device backup necessarily contains password hashes, provider
settings and the Agent credential. Therefore the local `.3mmbak` remains
`device-bound` and `local-only`: the API shows metadata and progress, but never
offers that archive or its key directly. The encryption key is
device-local and is not stored inside the backup or `/var/lib/3mm`, allowing a
factory reset of 3mm state followed by restore on the same appliance.

For failed-media recovery, an administrator can explicitly create a separate
`.3mmrecovery` file. It contains the local encrypted archive and its recovery
key inside a second AES-256-GCM envelope derived from an administrator-chosen
password with scrypt. The password is never stored. The portable file must be
kept away from the device together with its password; losing either makes it
unrecoverable, while disclosure of both exposes all backed-up secrets.

### Checking an exported file without importing it

On a trusted Linux workstation, use a checkout of the **Core release you intend
to restore to** and its normal Python dependencies. No running 3mm services,
administrator login, original SD card, device key or network access are needed.
For example, for a 64-bit Raspberry Pi target:

```sh
python -m tools.recovery_check saved.3mmrecovery --target-architecture aarch64
```

Enter the export password at the hidden terminal prompt, **not** in a command,
environment variable or diagnostic attachment. Use the architecture of the
intended installation (e.g. `armv6l` on a 32-bit Zero W); otherwise the check
uses the workstation architecture. `--json` returns a short result with a
fixed reason and next check on failure. No filenames, keys, application
contents or identifiers appear in it. The same offline diagnostics reader can
explain this JSON; it distinguishes checking an actual recovery file from a
capture-readiness snapshot. Neither is a signed attestation or boot test.

Once both envelopes authenticate, the checker distinguishes a file checksum
mismatch, an unreadable Core database, a missing/ambiguous or inconsistent
database revision, and a device identity or role mismatch. A wrong password and
an unauthenticated envelope intentionally share one reason. Keep the original
file; try another export rather than rewriting the archive or its database.

This authenticates both encryption layers, compares the archive's inventory
and every file checksum, and runs the restore validator for the specified
release/architecture, including database, identity and active package/schema
checks. It never imports into a catalog, creates a device key, stops services,
executes an application, replaces data or changes rights. A valid result
means **the file passed staging**, not that a different machine has enough
space, its services will start, or a physical restore has passed.

For the source-level end-to-end rehearsal,
`backend/tests/test_recovery_native_note.py` runs the official Note package,
saves a revision, exports it, detaches the source installation, then imports and
restores into a separate Linux directory with a new key. A newly started native
host reads both the original note and its save receipt. Core also resolves the
active package from the **destination** upload directory. A fresh normal login
in the rehearsal checks the operator's stored read permission and rejects a
write; no new application approval is issued. This is not a physical Raspberry
Pi boot or a browser test with anyone's real account.
A second rehearsal starts with different data on the destination, refuses the
final health check after the candidate serves the imported note, and checks
that the restarted previous instance serves only its pre-restore note and
receipt. The recorded result must be `rolled_back`, never `completed`.
The opt-in [user-systemd rehearsal](DEVELOPMENT_CHECKS.md#small-handoff) starts
the app through the actual local user manager. Installed system services and
their production permissions are outside that test.

Recovery rebuilds catalog locations from the destination upload directory
and the stored SHA-256, including disabled and staged versions. A location
is not proof of a valid file: normal package verification still applies.
Missing or damaged inactive packages are not enabled, downloaded or granted
access. Restore does not read a package through a path from the old machine.

Use a private, trusted Linux filesystem for temporary plaintext
(`--scratch /path/to/trusted-directory`); not a network share or a Windows
mount passing through Linux. Normal completion or failure removes the private
temporary directory, without touching the selected file. This is not secure
wiping; after power loss there may be a leftover `recovery-check-*` directory.
This operator profile accepts an inner archive up to 512 MiB and 32,768 payload
entries. It requires temporary free space of at least five times the input size
plus 64 MiB. A size limit or “not verified” is not proof that a file was erased.

## Local recovery boundary

The admin-only `GET /api/v1/backups/preview` endpoint now performs a read-only
preflight. It reports the candidate manifest, per-file SHA-256 values, total
size, available storage, required reserve and structured warnings/errors. It
does not create the backup directory, archive files or stop services.

An administrator can explicitly queue creation with `POST /api/v1/backups`
and the confirmation `CREATE BACKUP`. Core sends only the fixed action and user
ID to the privileged helper. The worker acquires the shared mutation lock,
briefly quiesces Core and Agent, repeats the preflight, verifies every checksum
again and streams the archive directly through AES-256-GCM encryption. No
plaintext tar archive is written. The device-bound key and `.3mmbak` archive
are root-only; `/api/v1/backups/operation` exposes only non-secret status.

Restore is queued only after the administrator types `RESTORE <backup-id>`.
The root worker authenticates and decrypts into a root-only temporary staging
area, validates the complete manifest, exact archive inventory, every checksum,
application/protocol/architecture compatibility, SQLite integrity and stable
device identity before stopping services. It then swaps only the allowlisted
Core, Agent, provisioning, application and host-config state. Restored enabled
applications are rebuilt from their checksum-addressed packages and migrate
their own database before Core, Agent and Web health checks must pass. Reviewed
service wheels, active pointers, sockets and transport keys are not accepted
from the archive. A failure restores the previous directories. If rollback
itself cannot complete, its recovery files are retained instead of being
deleted.

`GET /api/v1/backups` returns only validated catalog sidecars. Each sidecar
contains timestamps, compatibility, size and archive checksum metadata, but no
payload or encryption key. The Settings UI uses this catalog for explicit
restore selection. Creation automatically retains the five newest valid
archive/metadata pairs; unknown or malformed files are reported and never
deleted by retention.

The Beta restore window accepts the same version and older versions within
the same major/minor series, provided the database revision has a known path
to the installed Alembic head. Newer backups require updating the device first.
Protocol and architecture must still match. Migration or health-check failure
rolls back the previous state.

## Portable disaster recovery

Each catalog row can prepare a one-time password-protected download. The root
helper reads the root-only local archive and device key, streams them into the
portable envelope and exposes only a random, administrator-authorized download
handle. The generated server-side export is deleted after download.

`POST /api/v1/backups/restore-file` accepts only a bounded `.3mmrecovery`
upload from an administrator. The upload is placed in a fixed non-traversable
staging directory. The root helper authenticates the password envelope,
validates its exact inventory and checksums, validates the complete inner
backup, then re-encrypts it with the new installation's device key. Only after
that import succeeds does it queue the existing transactional restore worker.
Wrong passwords, corrupt files, unsafe paths, incompatible versions and
oversized uploads fail before persistent state is changed.

## Administrator workflow

1. Open **Settings → Backup and recovery**, select **Check readiness**, then
   **Create backup** and approve its exact confirmation.
2. Select **Download**, enter a separate recovery password twice and save the
   resulting `.3mmrecovery` file away from the Raspberry Pi.
3. After a clean installation of the compatible 3mm version, open the same
   Settings section and select **Restore from file**.
4. Choose the saved file, enter its recovery password and approve the exact
   restore confirmation. The imported backup is re-encrypted with the new
   installation's device key before the normal transactional restore begins.

The recovery password is not the login password and is never stored by 3mm.
The file is unrecoverable if that password is lost. Master reset preserves local
backups and their key; formatting or losing the SD card does not. Keep a recovery
file on another computer or phone. Installation and reset prepare recovery
storage before starting services; see [clean-install recovery](RECOVERY_CLEAN_INSTALL_FIX.md).
