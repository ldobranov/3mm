# systemd service templates

Status: validated service templates installed by the immutable release installer.

Application and setup-portal services run as the dedicated unprivileged `3mm`
user from an immutable
release link at `/opt/3mm/current`. Persistent state is under `/var/lib/3mm`,
optional non-secret overrides are read from `/etc/3mm/3mm.env`. Core binds to
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

`deployment/install-systemd.sh` installs a prepared release archive. It must be
run explicitly as root and requires the archive path, an immutable release ID
and the exact frontend origin allowed by Core CORS. It does not install system
packages, change networking or configure a firewall.

## First administrator

After Core is healthy, create the first administrator from an interactive
terminal. The command reads the password without echoing it and runs with the
same unprivileged account that owns the Core database:

```bash
sudo -u 3mm env \
  PYTHONPATH=/opt/3mm/current \
  DATABASE_URL=sqlite:////var/lib/3mm/core/3mm.db \
  /opt/3mm/venv/bin/python -m backend.scripts.bootstrap_admin
```

If the same username and email were already registered through the web UI,
that account is promoted and its password is replaced. The command refuses to
change anything when an administrator already exists or when the username and
email belong to different accounts. Passwords shorter than 12 characters are
rejected unless the explicit development-only override is supplied.
