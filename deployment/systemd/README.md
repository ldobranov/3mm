# systemd service templates

Status: validated service templates installed by the immutable release installer.

Application and setup-portal services run as the dedicated unprivileged `3mm`
user from an immutable release link at `/opt/3mm/current`. Every release owns
its Python environment at `/opt/3mm/releases/<release-id>/.venv`; switching the
current link therefore switches code and dependencies together. Persistent
state is under `/var/lib/3mm`, optional overrides are read from
`/etc/3mm/3mm.env`. Core binds to
all interfaces so a Hub can be reached from its trusted local network. Agent
remains loopback-only. The setup portal binds only while setup mode owns the
Wi-Fi interface. Internet exposure still requires
an authenticated reverse proxy and a separate security review.

The shared runtime planner determines which units an installer enables:

| Device state or role | Enabled services |
|---|---|
| Unprovisioned or interrupted setup | `3mm-network-helper.service`, `3mm-setup-ap.service`, `3mm-setup.service` |
| Node | `3mm-agent.service` |
| Hub or Standalone | `3mm-core.service`, `3mm-web.service`, `3mm-agent.service` |

`3mm-update-helper.service` is always enabled after a successful immutable
installation. It exposes only a group-restricted Unix socket and can schedule
one fixed staged-update worker. It does not accept commands, URLs, archive
paths or package names from Core.

Application extensions use `3mm-application-extension@.service` and the
separate unprivileged `3mm-app` identity. The service imports only the reviewed
wheel selected by root-owned active metadata and communicates with Core over a
per-installation signed Unix socket. It has a private network namespace and can
write only its own `data` and `run` directories. Activation is explicit,
applies forward-only extension migrations, is health checked and restores both
the previous active version and its SQLite snapshot if the candidate fails.
Backup quiesces application instances and includes only their mutable `data`;
restore reactivates them from checksum-addressed reviewed packages.

The setup portal remains unprivileged and talks through a root-owned Unix
socket to a narrowly scoped NetworkManager helper. The open `3mm Setup XXXX`
access point exists only in unprovisioned or explicit network-reset mode,
exposes only the captive setup portal and is removed after successful setup.
The submitted Wi-Fi secret travels only in memory and is stored solely by
NetworkManager in its root-only system connection profile. It is never written
to the provisioning journal, application database, environment file or logs.

The templates intentionally use `Restart=on-failure`, not unconditional
restart, and do not couple Core and Agent process lifetimes. A failed Core must
not stop already deployed local Agent workloads.

`deployment/install-systemd.sh` is the single installer for prepared release
archives. It must be run explicitly as root and requires the archive path, an
immutable release ID and the exact frontend origin allowed by Core CORS. The
optional fifth argument verifies the archive SHA-256. It builds dependencies
before stopping services, backs up SQLite and the service environment, switches
the current link atomically, verifies active runtime endpoints and restores the
previous release automatically on failure. It does not install system packages,
change networking or configure a firewall.

The System Updates UI separates catalog check, download/verification and
installation approval. Core stages one bounded archive under
`/var/lib/3mm/core/update-staging`, verifies its size, SHA-256, safe tar layout,
embedded identity, free space, SQLite health and dependency plan, then requires
a second administrator action. Immediately before mutation, the root worker
independently checks the staged identity and checksum against the official
GitHub manifest again. Only packages present in both the release declaration
and the installed root-owned allowlist can reach `apt-get`; no shell fragment
or generated installer is accepted. The existing installer remains the owner
of database backup, migration, activation, health checks and rollback. Root
results are persisted under `/var/lib/3mm/update-helper` without credentials or
provider keys so the restarted Core can report the outcome.

Every successful replacement also records the verified prior release at
`/opt/3mm/previous`. Release cleanup is a separate, explicit operation. Its
default mode is read-only and reports protected releases, deletion candidates
and reclaimable storage:

```bash
sudo python3 /opt/3mm/current/deployment/release_retention.py --keep-history 3
```

The active release, the explicit rollback target and the selected number of
additional recent releases are always protected. Actual deletion requires the
additional `--apply` flag and is refused when the rollback link is unavailable
or unsafe. Deployment and cleanup share an exclusive mutation lock so that the
active target cannot change during deletion. Persistent data below
`/var/lib/3mm` is outside the cleanup scope.

Deployment state backups have their own root-only retention tool. It always
protects the backups corresponding to both `/opt/3mm/current` and
`/opt/3mm/previous`, plus the configured number of recent recovery points:

```bash
sudo python3 /opt/3mm/current/deployment/deployment_backup_retention.py \
  --keep-history 3
```

This command is also a dry run unless `--apply` is supplied. Apply is blocked
if either protected release has no matching deployment backup, if a release
link changes while planning, or if an unexpected symlink is found. Release and
backup retention share the installer mutation lock.

`deploy.ps1` builds and verifies the frontend on the development machine,
creates the archive and delegates installation to that same script. Normal
deployments require a clean, pushed commit. The explicit `-IncludeWorkingTree`
switch is reserved for test deployments of reviewed uncommitted changes.

The wrapper accepts either runtime selected by the shared planner: the normal
Core/Web/Agent application runtime or the setup-only runtime expected on a clean
device. The complete host preflight, open-AP setup, administrator bootstrap and
co-located Agent pairing procedure is documented in
[`docs/RASPBERRY_PI_FIRST_BOOT.md`](../../docs/RASPBERRY_PI_FIRST_BOOT.md).

The rollback path has an explicit acceptance mode for a reviewed test snapshot:

```powershell
.\deploy.ps1 -IncludeWorkingTree -InteractiveSudo -RollbackTestAfterHealth
```

This mode creates only a `rollback-test-*` candidate, verifies that the new
runtime becomes healthy, injects a controlled installer error and expects the
installer to restore the exact release that was active before the test. The
wrapper then checks external health, confirms that the failed release directory
was removed and removes its test-only deployment backup. The failure injection
is rejected for every release ID outside the reserved test prefix.

After deployment, the dependency-free release smoke test checks the Web shell,
the required Core API surface, Agent readiness, hello and inventory, and verifies
that all Agent responses expose the same persistent device identity:

```bash
python3 /opt/3mm/current/deployment/release_smoke.py
```

## First administrator

On the first deployment of a brand-new empty database, the Beta/test installer
creates `admin@example.com` with password `admin`. It does this only when the
database did not exist before deployment and the user table is empty. Updates
therefore do not recreate the account, replace an administrator or reset a
password. Change the default immediately from **Profile**.

For an older installation without an administrator, create one interactively.
The command reads the password without echoing it and runs with the same
unprivileged account that owns the Core database:

```bash
sudo -u 3mm env \
  PYTHONPATH=/opt/3mm/current \
  DATABASE_URL=sqlite:////var/lib/3mm/core/3mm.db \
  /opt/3mm/current/.venv/bin/python -m backend.scripts.bootstrap_admin
```

If the same username and email were already registered through the web UI,
that account is promoted and its password is replaced. The command refuses to
change anything when an administrator already exists or when the username and
email belong to different accounts. Passwords shorter than 12 characters are
rejected unless the explicit development-only override is supplied.
