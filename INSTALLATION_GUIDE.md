# 3mm installation

The supported Raspberry Pi installation uses an official immutable release.
It does not clone the repository, build the application on the device or write
passwords to command arguments.

## One-command Raspberry Pi installation

On a current 64-bit Raspberry Pi OS or Debian installation, run:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | sudo bash
```

The bootstrap defaults to the latest published Beta release while 3mm remains
in Beta. It:

1. selects the official artifact for the current CPU architecture;
2. validates the release identity and reviewed dependency list;
3. installs only those APT dependencies;
4. verifies the artifact size and SHA-256 digest;
5. runs the read-only first-boot preflight;
6. starts the rollback-capable immutable installer as a detached systemd job.

Git is not required on the Raspberry Pi.

For the current Beta/test installation, a brand-new empty database receives
the initial login `admin@example.com` with password `admin`. Change it from
**Profile** after signing in. An update never recreates the account or resets
an existing password.

## Wi-Fi-only installation

The detached job continues after SSH disconnects. On an unprovisioned device,
the connection is expected to close when `wlan0` becomes the open `3mm Setup
XXXX` access point. Join that network from a phone. The captive portal should
open automatically; its fallback address is:

```text
http://10.42.0.1:8895/setup
```

The command prints the transient service name. While LAN access remains, follow
its log with the printed `journalctl` command.

## Installer options

Pin an exact published release:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | \
  sudo bash -s -- --tag v0.3.0-beta.8
```

Select a channel explicitly:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | \
  sudo bash -s -- --channel beta
```

On a first installation the application origin defaults to the detected device
IP. On a full-profile update the bootstrap preserves the existing `FRONTEND_URL`
from `/etc/3mm/3mm.env`, unless an explicit option/environment override is supplied.
It reads this file as data, never executes it as a shell script.

Override the application origin only when necessary:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | \
  sudo bash -s -- --frontend-origin http://192.168.1.88
```

Available options are shown without changing the system:

```bash
bash install.sh --help
```

## Installed layout

```text
/opt/3mm/current  -> active immutable release
/opt/3mm/previous -> rollback release
/opt/3mm/releases -> installed release directories
/var/lib/3mm      -> persistent application and device state
/etc/3mm          -> protected service configuration
```

Uploaded logos and public assets use `UPLOADS_DIR`, configured by the installer
as `/var/lib/3mm/core/uploads`. Settings images live in its `settings/`
subdirectory and retain their `/uploads/settings/...` URLs. They are included
in backup/portable recovery and are not replaced by a release update. Do not
make `/opt/3mm/releases` writable to fix an upload error. See
[Core asset storage](docs/CORE_ASSET_STORAGE.md) for the shared backend helper
and the boundary between public assets and private application data.

After setup, the application is available at `http://<device-ip>/` and
`http://<hostname>.local/`. Port `8080` remains as a compatibility listener.

## Wired-only Linux and Ubuntu under Windows (WSL)

Use the full profile with systemd enabled. Without a supported Wi-Fi interface,
the installer initializes Standalone rather than attempting Setup AP. Windows
can access a WSL-forwarded installation at `http://localhost/`; port `8080` is
also supported when Windows port 80 is occupied by another service.

The full-profile installer merges existing explicit `CORS_ORIGINS` with its
configured IP/hostname and these local browser origins:

```text
http://localhost
http://localhost:8080
http://127.0.0.1
http://127.0.0.1:8080
```

Custom HTTP(S) origins are preserved, duplicates removed, and invalid/wildcard
origins rejected before stopping services. The list is bounded to 128 origins.
The approved UI updater runs the same verified target installer and preserves
the configured frontend URL. When Core is selected, update success also requires
local browser CORS preflight checks, not just a successful `/ready` GET.

This policy is included only in releases containing `deployment/frontend_access.py`;
installing an older tag uses that tag's installer. A configuration repair on an
existing host is not a replacement for publishing the next release.

An HTTP 400 `Disallowed CORS origin` means the browser origin is not allowed;
it does not by itself mean installation failed. Check the detached installer or
`3mm-update-apply.service` journal before reinstalling. Preserve protected
configuration backups and do not modify immutable release files or reset data.
See [VM recovery and validation](docs/INSTALLER_VM_RECOVERY.md).

Continue with the complete
[Raspberry Pi first-boot procedure](docs/RASPBERRY_PI_FIRST_BOOT.md) for phone
setup, initial login, local Agent pairing and acceptance checks.

## Development deployment

For an unpublished development commit, use the laptop-driven `deploy.ps1`
workflow documented in the first-boot procedure. The public one-line installer
intentionally accepts only published release artifacts.
