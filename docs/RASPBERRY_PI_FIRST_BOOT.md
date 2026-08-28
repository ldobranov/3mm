# Raspberry Pi installation and first boot

Status: one-command clean-media bootstrap, setup AP and return to the normal
Standalone runtime are physically validated on the Raspberry Pi 3B+ baseline.

This guide installs one Raspberry Pi as a 3mm Standalone device. It deliberately
keeps Raspberry, Wi-Fi and user-selected passwords out of commands, files and
Git. Password prompts must be answered interactively. The public `admin` Beta
login described below is a disposable test default, not a secret.

## Validated baseline

The current physical baseline is a Raspberry Pi 3B+ running Debian GNU/Linux 13
on `aarch64`. The accepted host has Python 3.13.5, Node.js 20.19.2, npm 9.2.0,
NetworkManager and a Wi-Fi interface named `wlan0`.

The public bootstrap installs only the reviewed APT dependencies recorded in
the release manifest. It does not alter the firewall or replace the
host's network manager. The immutable installer creates the `3mm` system
account, release-specific Python environment, persistent directories and
systemd units. Internet access is required while the release and dependencies
are downloaded.

Ethernet is preferred but no longer required for the first installation. The
public bootstrap starts the immutable installer as a detached systemd job. An
unprovisioned release can therefore change `wlan0` into the setup access point
without terminating the installation when the Wi-Fi SSH session closes.

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
- `bash`, `tar`, `flock`, `systemctl` and `nmcli`;
- active NetworkManager managing an interface named `wlan0`.

## 2. Install with one command

On the Raspberry Pi, run:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | sudo bash
```

Git is not required on the device. The bootstrap selects the latest published
Beta release for the current architecture, validates the release manifest,
installs its reviewed dependencies, verifies the artifact size and SHA-256,
and runs the read-only preflight automatically. It then delegates activation to
the existing rollback-capable immutable installer.

The background job survives loss of the SSH connection. Its unit name is
printed before the command returns and its log can be followed while LAN access
remains with the printed `journalctl` command. On a Wi-Fi-only first boot, loss
of SSH after that point is expected; continue from the phone on `3mm Setup
XXXX`.

To pin an exact published release:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | \
  sudo bash -s -- --tag v0.3.0-beta.8
```

## 3. Manual development deployment

The laptop-driven path remains available when testing an exact development
commit that has not yet been published as a release.

### Run the read-only preflight

From the development laptop, copy only the dependency-free checker and run it
before deploying:

```powershell
scp .\deployment\first_boot_preflight.py raspberry@<device-ip>:/tmp/3mm-first-boot-preflight.py
ssh raspberry@<device-ip> "python3 /tmp/3mm-first-boot-preflight.py"
```

Continue only when the last line is `result=ready failed=0`. The checker does
not install packages, start or stop services, or change NetworkManager.

### Build and install an immutable release

Use a clean commit that is already pushed to the selected remote. From Windows
PowerShell in the repository root:

```powershell
.\deploy.ps1 `
  -SshHost raspberry@<device-ip> `
  -FrontendOrigin http://<final-lan-address> `
  -InteractiveSudo `
  -SkipPush
```

Omit `-SkipPush` when the wrapper should push and verify the clean commit. Do not
use `-IncludeWorkingTree` for clean-install acceptance.

The sudo password, if one exists, is entered only at the interactive prompt.
The laptop builds and verifies `frontend/dist`; the Raspberry creates the
release-specific virtual environment and compiler dependencies. A failed
activation restores the prior release automatically.

On an empty provisioning state the expected successful result is the setup
runtime, not the normal login page. The deployment wrapper recognizes both
valid outcomes:

- first boot: setup portal healthy on port 8895 with a captive HTTP entry point
  on port 80;
- provisioned device: Core, Web and Agent healthy on ports 8887, 80/8080 and
  8890.

After installation, the release itself can be checked without mutation:

```bash
python3 /opt/3mm/current/deployment/first_boot_preflight.py \
  --release-root /opt/3mm/current
```

## 4. Complete setup from a phone

The unprovisioned device enables only:

- `3mm-network-helper.service`;
- `3mm-setup-ap.service`;
- `3mm-setup.service`.

Join the open Wi-Fi network named `3mm Setup XXXX`. It intentionally has no
password and exists only during setup or an explicit network reset. The phone
should detect the captive portal and open the setup page automatically. Some
operating systems show a **Sign in to network** notification instead. If the
page does not open, use the fallback address:

```text
http://10.42.0.1:8895/setup
```

Select a nearby network from the scan results, or enter its name manually.
Enter its password, device name and locale, then select **Standalone**. The
portal follows the saved application theme. The Wi-Fi password is passed to
NetworkManager and is not stored in the provisioning journal, application
database or logs.

On success the setup access point is removed, the saved Wi-Fi profile becomes
active, and Core, Web and Agent replace the setup services. On failure the
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

## 6. Pair the co-located Agent

The Standalone Agent has a persistent identity but needs its own Core credential.
Copy the public half of the dedicated device key to a temporary readable path:

```powershell
scp <device-key>.pub raspberry@<device-ip>:/tmp/3mm-device.pub
```

Then pair it locally through the audited Core pairing services:

```bash
sudo -u 3mm env \
  PYTHONPATH=/opt/3mm/current \
  DATABASE_URL=sqlite:////var/lib/3mm/core/3mm.db \
  /opt/3mm/current/.venv/bin/python \
  /opt/3mm/current/deployment/bootstrap-local-agent.py \
  --admin-email <administrator-email> \
  --identity-file /var/lib/3mm/agent/identity.json \
  --credential-dir /var/lib/3mm/agent \
  --public-key-file /tmp/3mm-device.pub \
  --display-name <device-name> \
  --role standalone

sudo systemctl restart 3mm-agent.service
rm -f /tmp/3mm-device.pub
```

Only the public key is copied. The generated Agent credential remains private
under `/var/lib/3mm/agent`.

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
- an explicit network reset returns to the open setup AP and preserves the
  application database and Agent identity.

## 8. Recover or move the device to another Wi-Fi network

Sign in as an administrator and open **Settings → Network Configuration**.
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
  immutable release and Raspberry Pi OS remain installed, and setup Wi-Fi is
  started again.

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
automatically tested. The destructive factory-reset path is intentionally still
pending one explicit physical acceptance run. Local Agent pairing and the full
post-install checklist remain separate acceptance steps.

Node setup is also not yet claimed as complete. The portal persists the selected
Hub address, but external-Hub credential bootstrap is not yet a single first-boot
flow. Use the Standalone path for the current Milestone 10 physical acceptance.
