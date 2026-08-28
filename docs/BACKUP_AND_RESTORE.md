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
Core, Agent, provisioning and host-config state, runs current migrations and
requires Core, Agent and Web health checks to pass. A failure restores the
previous directories. If rollback itself cannot complete, its recovery files
are retained instead of being deleted.

`GET /api/v1/backups` returns only validated catalog sidecars. Each sidecar
contains timestamps, compatibility, size and archive checksum metadata, but no
payload or encryption key. The Settings UI uses this catalog for explicit
restore selection. Creation automatically retains the five newest valid
archive/metadata pairs; unknown or malformed files are reported and never
deleted by retention.

The current Beta restore window is intentionally conservative: backup and
installed application versions must match exactly.

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

1. Open **Settings → Backup and recovery** and create a local backup.
2. Select **Download**, enter a separate recovery password twice and save the
   resulting `.3mmrecovery` file away from the Raspberry Pi.
3. After a clean installation of the compatible 3mm version, open the same
   Settings section and select **Restore from file**.
4. Choose the saved file, enter its recovery password and approve the exact
   restore confirmation. The imported backup is re-encrypted with the new
   installation's device key before the normal transactional restore begins.

The recovery password is not the login password and is never stored by 3mm.
The file is unrecoverable if that password is lost. A factory reset or failed
SD card removes device-local backups, but cannot remove a recovery file that
was already saved on another computer or phone.
