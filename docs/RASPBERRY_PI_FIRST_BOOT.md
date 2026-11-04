# Raspberry Pi installation and first boot

Status: the standard bootstrap selects Stable and retains the existing LAN.
The earlier explicit setup-AP flow was physically validated on the Raspberry Pi
3B+ baseline; that evidence is not a new clean-media acceptance of these defaults.

This guide installs one Raspberry Pi as a 3mm Standalone device. It deliberately
keeps Raspberry, Wi-Fi and user-selected passwords out of commands, files and
Git. Password prompts must be answered interactively. The public `admin` Beta
login described below is a disposable test default, not a secret.

## Validated baseline

The current physical baseline is a Raspberry Pi 3B+ running Debian GNU/Linux 13
on `aarch64`. The accepted host has Python 3.13.5, Node.js 20.19.2, npm 9.2.0,
NetworkManager and a Wi-Fi interface named `wlan0`.

The public bootstrap installs the reviewed clean-host and release prerequisites.
By default it retains host-managed networking; managed Wi-Fi/AP setup is opt-in.
It does not alter the firewall. The immutable installer creates the `3mm` system
account, release-specific Python environment, persistent directories and
systemd units. Internet access is required while the release and dependencies
are downloaded.

Ethernet is preferred but no longer required for the first installation. The
public bootstrap starts the immutable installer as a detached systemd job. When
the optional `-ap` path is selected on an unprovisioned device, installation can
finish even if changing `wlan0` to the setup access point closes Wi-Fi SSH.

## 1. Prepare the Raspberry Pi

Install a current 64-bit Raspberry Pi OS or Debian image. In the imaging tool:

- enable SSH;
- configure the device hostname;
- add the dedicated device SSH public key;
- do not embed an SSH password in the image or repository;
- connect Ethernet when convenient, or preconfigure temporary Wi-Fi.

The host must provide:

- Python 3.10 or newer with the `venv` module;
- Node.js 20 or newer and npm;
- `bash`, `tar`, `flock` and `systemctl`.

The optional `-ap` path additionally requires active NetworkManager and a usable
AP-capable Wi-Fi adapter; the host-managed LAN path does not require Wi-Fi/AP.

## 2. Install with one command

On the Raspberry Pi, run:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | sudo bash
```

Git is not required on the device. The bootstrap selects the latest published
Stable release for the current architecture, validates the release manifest,
installs its reviewed dependencies, verifies the artifact size and SHA-256,
and runs the read-only preflight automatically. It then delegates activation to
the existing rollback-capable immutable installer.

The background job survives loss of the SSH connection. Its unit name is
printed before the command returns and its log can be followed with the printed
`journalctl` command. The standard command retains the current Ethernet or Wi-Fi
connection. Complete setup from another device on that LAN at:

```text
http://<LAN-IP>:8895/setup
```

To explicitly enable managed setup Wi-Fi on a fresh installation instead:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | sudo bash -s -- -ap
```

This selects the managed networking backend. On an unprovisioned AP-capable
device, Wi-Fi SSH may close when `3mm Setup XXXX` starts. On a provisioned device
`-ap` does not reset the saved role or force a setup access point. Updates without
an override retain the saved backend, role and data. The advanced
`--network-backend host|network-manager` option remains available; `-ap` is the
short form for choosing `network-manager`, not a reset command.

To pin an exact published release:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | \
  sudo bash -s -- --tag v0.3.7
```

## 3. Local development updates

After the one-command installation and setup, the laptop-driven path can update
an existing full installation from the current checkout without publication.

### Run the read-only preflight

From the development laptop, copy only the dependency-free checker and run it
before deploying:

```powershell
scp .\deployment\first_boot_preflight.py raspberry@<device-ip>:/tmp/3mm-first-boot-preflight.py
ssh raspberry@<device-ip> "python3 /tmp/3mm-first-boot-preflight.py"
```

Continue only when the last line is `result=ready failed=0`. The checker does
not install packages, start or stop services, or change NetworkManager.

### Prepare and install an immutable local update

From Windows PowerShell in the repository root, with WSL `Ubuntu-26.04` and the
development Python/Node/npm/Git toolchain available:

```powershell
.\deploy.ps1 -Action Prepare
.\deploy.ps1 -SshHost raspberry@rasp-3mm.local
.\deploy.ps1 -Action Status
.\deploy.ps1 -Action Logs
```

Preparation is local only. The wrapper snapshots current source, records checks,
and reuses exact checked builds/dependencies on repeats; it never pushes Git or
changes versions. The default target is already `raspberry@rasp-3mm.local`.
Use `-Bundle <ready-directory>` to deploy an exact prepared kit. See the root
README for bounded developer check selections and target options.

SSH and sudo passwords are entered at the interactive prompts. The installed
frontend URL and network backend are preserved. The Raspberry creates the
release-specific environment; unchanged native hosts are reused. The existing
installer restores the prior Core release on activation failure.

The install runs independently of SSH. Wait for `3mm update succeeded`; closing
the observer does not stop it. Status/Logs never upload or repeat an install.
An uncertain/failed job requires inspection before further action. This local
update path expects a provisioned device with Core ready. The clean-OS installer
above exposes setup on port 8895 over the existing LAN. The optional managed AP
path also provides a captive HTTP entry on port 80.

After installation, the release itself can be checked without mutation:

```bash
python3 /opt/3mm/current/deployment/first_boot_preflight.py \
  --release-root /opt/3mm/current
```

## 4. Complete setup from a phone

With the standard host-managed installation, open
`http://<LAN-IP>:8895/setup` from a phone on the same network. Complete the device
name, locale and Standalone role without replacing the host's network settings.
On success, Core, Web and Agent start; the existing LAN connection is retained.

With explicit `-ap` managed setup, the unprovisioned device uses:

- `3mm-network-helper.service`;
- `3mm-setup-ap.service`;
- `3mm-setup.service`.

For that optional AP path, join the open Wi-Fi network named `3mm Setup XXXX`.
It intentionally has no password and exists only during setup or an explicit
network reset. The phone
should detect the captive portal and open the setup page automatically. Some
operating systems show a **Sign in to network** notification instead. If the
page does not open, use the fallback address:

```text
http://10.42.0.1:8895/setup
```

In managed setup, select a nearby network from the scan results, or enter its
name manually. Enter its password, device name and locale, then select **Standalone**. The
portal follows the saved application theme. The Wi-Fi password is passed to
NetworkManager and is not stored in the provisioning journal, application
database or logs.

On managed setup success the access point is removed, the saved Wi-Fi profile
becomes active, and Core, Web and Agent replace the setup services. On failure the
network change is rolled back and setup mode remains available.

The current **Administrator name** field remains provisioning metadata and does
not select the application login. During Beta, the immutable installer creates
the documented test administrator only when the user table is initially empty.

## 5. Sign in with the Beta/test administrator

Open `http://<hostname>.local/` or `http://<device-ip>/` and use:

- email: `admin@example.com`
- password: `admin`

Change the password from **Profile** after signing in. This short default is for
the current Beta/test flow, not the production security model. It is created
only for a brand-new empty database; upgrades do not recreate it, replace an
existing administrator or reset a password.

If an older installation has no administrator, create one interactively:

Reconnect over SSH on the final LAN and run:

```bash
sudo -u 3mm env \
  PYTHONPATH=/opt/3mm/current \
  DATABASE_URL=sqlite:////var/lib/3mm/core/3mm.db \
  /opt/3mm/current/.venv/bin/python -m backend.scripts.bootstrap_admin
```

Enter the username, email and password only at the prompts. The normal minimum
password length is 12 characters. The bootstrap refuses to replace an existing
administrator.

## 6. Verify automatic local Agent pairing

Completing a Standalone or Hub setup now pairs the co-located Agent before its
service starts. The bootstrap creates a persistent Ed25519 device key, runs the
normal audited Core pairing flow and stores the issued credential under
`/var/lib/3mm/agent`. Repeated runtime activation is idempotent and does not
create another device. Node mode intentionally remains dependent on its
external Hub pairing flow.

No SSH key copy, device-ID entry or manual pairing command is required. For an
older installation, or to repair an interrupted local bootstrap, run the same
automatic operation explicitly:

```bash
sudo -u 3mm env \
  PYTHONPATH=/opt/3mm/current \
  DATABASE_URL=sqlite:////var/lib/3mm/core/3mm.db \
  /opt/3mm/current/.venv/bin/python \
  /opt/3mm/current/deployment/bootstrap-local-agent.py \
  --automatic

sudo systemctl restart 3mm-agent.service
```

The private device key and generated Core credential remain readable only by
the `3mm` service account and are included as secret material in encrypted
Standalone backups.

## 7. Acceptance checks

Run the release smoke test:

```bash
python3 /opt/3mm/current/deployment/release_smoke.py
```

Then verify:

- `http://<final-lan-address>/user/login` loads;
- `http://<hostname>.local/user/login` loads on a client with mDNS support;
- port 8080 remains available as a compatibility listener;
- the new administrator can sign in;
- the local Agent is present and online in Devices;
- health, hello and inventory expose one stable device identity;
- a reboot returns to Core, Web and Agent without recreating the setup AP;
- on the optional managed networking path, explicit setup Wi-Fi recovery
  preserves the application database and Agent identity.

## 8. Recover or move the device to another Wi-Fi network

For the optional managed networking path, sign in as an administrator and open
**Settings → Network Configuration**. Host-managed networking remains managed by
the operating system; this installation does not silently enable AP recovery.
This panel provides two independent controls:

- **Start setup Wi-Fi** immediately switches the device to its open
  `3mm Setup XXXX` access point;
- **Automatically start setup Wi-Fi after 5 minutes offline** is enabled by
  default and can be disabled. It measures only whether both Wi-Fi and Ethernet
  links are disconnected; it does not test Internet access.

The checkbox is useful for devices that must recover unattended. Disable it
when the Raspberry Pi may remain powered by a UPS while its router is expected
to be temporarily offline and must retain its saved network profile.

Starting setup on a Wi-Fi-only device intentionally drops its normal IP,
hostname page and SSH connection. Join the open AP from a phone and complete
the same setup flow described above. Successful setup restores the normal
runtime without changing the Core database or Agent identity.

See [NETWORK_RECOVERY.md](NETWORK_RECOVERY.md) for the runtime boundary,
fallback addresses and operational details.

## 9. Restart or reset the installed device

Administrators can open **Settings → Device Control** after provisioning.

- **Restart device** schedules a normal Raspberry Pi restart. Core acknowledges
  the audited request before the helper restarts the host, so the browser and
  SSH connection are expected to disappear briefly.
- **Factory reset** requires the exact phrase `FACTORY RESET`. It deletes
  persistent 3mm users, settings, dashboards, extensions, Agent identity,
  provisioning data, deployment backups and update-helper state. The current
  immutable release and Raspberry Pi OS remain installed. Setup returns through
  the configured network backend: LAN for host-managed networking or setup Wi-Fi
  for the supported managed AP path.

Factory reset is not an SD-card erase. The last verified NetworkManager Wi-Fi
profile remains available as a connection rollback until setup successfully
applies a replacement. During the current Beta, the empty application database
receives the documented test administrator again.

See [DEVICE_ADMINISTRATION.md](DEVICE_ADMINISTRATION.md) for confirmations,
authorization and the complete reset boundary.

## Current acceptance boundary

The host/release preflight, one-command installation, Wi-Fi-only handoff to the
open setup AP, captive setup and return to the Standalone runtime have been
verified on a clean SD card on the physical Pi 3B+. Restart is implemented and
physically tested. Factory reset, setup-AP return across reboot, phone setup and
the fresh Standalone login are also physically accepted. Local Agent pairing on
an external Core remains part of the future Hub/Node milestone.

Node setup is also not yet claimed as complete. The portal persists the selected
Hub address, but external-Hub credential bootstrap is not yet a single first-boot
flow. Use the Standalone path for the current Milestone 10 physical acceptance.
