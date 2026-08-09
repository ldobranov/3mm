# systemd service templates

Status: validated templates; not an installer and not installed on the test
Raspberry Pi.

All services run as the dedicated unprivileged `3mm` user from an immutable
release link at `/opt/3mm/current`. Persistent state is under `/var/lib/3mm`,
optional non-secret overrides are read from `/etc/3mm/3mm.env`. Core binds to
all interfaces so a Hub can be reached from its trusted local network. Agent
and the setup prototype remain loopback-only. Internet exposure still requires
an authenticated reverse proxy and a separate security review.

The shared runtime planner determines which units an installer enables:

| Device state or role | Enabled services |
|---|---|
| Unprovisioned or interrupted setup | `3mm-setup.service` |
| Node | `3mm-agent.service` |
| Hub or Standalone | `3mm-core.service`, `3mm-web.service`, `3mm-agent.service` |

The setup service still uses the deterministic mock network adapter. Its unit
has no root user, Linux capabilities or NetworkManager write access. A future
network mutation adapter requires a separately reviewed privileged boundary;
these templates must not be expanded silently to grant it.

The templates intentionally use `Restart=on-failure`, not unconditional
restart, and do not couple Core and Agent process lifetimes. A failed Core must
not stop already deployed local Agent workloads.

`deployment/install-systemd.sh` installs a prepared release archive. It must be
run explicitly as root and requires the archive path, an immutable release ID
and the exact frontend origin allowed by Core CORS. It does not install system
packages, change networking or configure a firewall.
