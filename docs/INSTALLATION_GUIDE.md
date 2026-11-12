# 3mm installation

The supported Raspberry Pi installation uses an official immutable release.
It does not clone the repository or build the frontend on the device. Limited
ARMv6 dependency compilation may be necessary; passwords are not written to
command arguments.

## One-command Raspberry Pi installation

On a supported Raspberry Pi OS or Debian installation with systemd and a working
LAN connection, run:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | sudo bash
```

The bootstrap defaults to the latest published Stable release. It:

1. selects the official artifact for the current CPU architecture;
2. validates the release identity and reviewed dependency list;
3. installs only those APT dependencies;
4. verifies the artifact size and SHA-256 digest;
5. runs the read-only first-boot preflight;
6. starts the rollback-capable immutable installer as a detached systemd job.

Git is not required on the Raspberry Pi.

The default `full` profile installs Core, the prebuilt Web interface and the local
Agent. It supports `aarch64`, `armv7l`, `x86_64` and the ARMv6 profile below.

For the current Beta/test installation, a brand-new empty database receives
the initial login `admin@example.com` with password `admin`. Change it from
**Profile** after signing in. An update never recreates the account or resets
an existing password.

## Preserve the current network, or explicitly choose setup AP

By default a fresh installation retains the host's existing Ethernet or Wi-Fi
configuration. It does not take over networking or require an AP-capable adapter.
Finish initial setup from another device on the same LAN:

```text
http://<device-LAN-IP>:8895/setup
```

To explicitly choose NetworkManager-managed Wi-Fi/AP setup on fresh media:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | \
  sudo bash -s -- -ap
```

This optional path requires NetworkManager and a usable AP-capable Wi-Fi adapter.
On an unprovisioned supported device, Wi-Fi SSH may close when the open
`3mm Setup XXXX` access point starts. Join that network from a phone; the
captive portal should open automatically. Its fallback address is:

```text
http://10.42.0.1:8895/setup
```

The detached job continues even after SSH disconnects. The command prints its
transient service name; follow the log with the printed `journalctl` command.
Updates preserve the saved network backend, role and data unless explicitly
overridden. `-ap` does not reset an already configured device or force it back
into setup mode. `--network-backend host|network-manager` is the advanced form
of the network choice, separate from the `full|node` installation profile.

## Raspberry Pi Zero W / ARMv6

For a full Standalone/Hub installation on the original Zero W, use **32-bit
Raspberry Pi OS Trixie (Raspbian 13), ARMv6, with Python 3.13** and the
distribution's Node.js/npm. Use the same standard command above. The bootstrap
selects the ARMv6 Full artifact and installs the reviewed host build prerequisites
needed by its constrained dependency profile. Do not substitute ARMv7/aarch64
wheels or download a generic Node ARM binary for the original Zero W.

For an Agent-only Zero W controlled by a separate Hub, use the minimal Node
profile instead:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | \
  sudo bash -s -- --profile node
```

This Node profile currently supports `armv6l` with Python 3.13. It installs Agent
and shared setup/recovery, not Core, application hosts or a frontend, and does
not require Node.js/npm. Network behavior is still host-managed by default;
add `-ap` only when managed setup Wi-Fi is intended. The Node's Hub pairing is
a separate step. Full ARMv6 installs remain resource-constrained and may take
longer than installations on a Pi 3 or newer.

## Installer options

Pin an exact published release:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | \
  sudo bash -s -- --tag v0.3.11
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

## One-time upgrade to the neutral source layout

The source-layout reorganization changes internal Python paths to `backend/`,
`components/` and `packages/`. The web updater published in **0.3.11** requires
two old source paths in every target archive, so it safely refuses the reorganized
release before installation. Refreshing the page or repeating its approval cannot
change that installed validator. Do not add old import shims or remove archive
verification to get past the refusal.

Older Node OTA validators/installers have the same source-layout boundary. Use
the verified console bootstrap for this one transition on either profile; do
not try to force the neutral archive through an old Node OTA operation. This
does not disable normal signed Node updates after the transition.

After the neutral-layout release is published, cross this boundary through the
verified bootstrap/console installer, not the old web updater. The target
installer coordinates the existing Agent, Runtime/connector worker and
application-host artifacts under the same installation lock. It proves old
artifacts through the previous immutable release, stages verified replacements,
and preserves already-compatible pins. The Node profile transitions only Agent.
Disabled application hosts remain disabled; application packages, data and
rights are not rewritten or approved by this operation.

Original current/previous component pairs are retained in a protected journal
under `/var/lib/3mm-component-transitions/`. An installation failure restores
these pairs before restarting the previous release. Incompatible old builds
are not left as independently selectable rollback pointers under the new
validators; they remain available for this coordinated rollback. Optional host
dependencies must match the target's exact locks or preparation refuses before
stopping services. There is no automatic dependency download or import shim.

An older application wheel may itself import a removed SDK path. The installer
does not adapt application code: prepare an updated application separately.
If a previously active application cannot pass health checks, the installation
rolls back rather than reporting success with that application broken.

A retained completed rollback requires an explicit retry. Only after the
installer reports `completed_rollback_retry_required`, review the restored
state and repeat the same verified bootstrap installation with the explicit
`--retry-rolled-back` option. It forwards `THREE_MM_RETRY_ROLLED_BACK_TRANSITION=1`
to the detached target installer; a direct target-installer invocation can set
that environment variable instead. Original proofs and exact pointers are
checked again and the previous attempt is retained. This option does not clear
an interrupted or unconfirmed transition; inspect its journal before recovery.
It is not an instruction to erase the SD card, reset setup, alter rights or
modify immutable releases. Do not bypass component verification to force an
upgrade.

Before publication, the public bootstrap cannot install this working tree. Use
the development deployment procedure below only when a device deployment has
been explicitly agreed.

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
[Core asset storage](CORE_ASSET_STORAGE.md) for the shared backend helper
and the boundary between public assets and private application data.

After setup, the application is available at `http://<device-ip>/` and
`http://<hostname>.local/`. Port `8080` remains as a compatibility listener.

## Wired-only Linux and Ubuntu under Windows (WSL)

Use the full profile with systemd enabled and retain the default host-managed
network backend. Initial setup remains available over the existing LAN without
attempting Setup AP; select the device role independently from the network.
Windows can access a WSL-forwarded installation at `http://localhost/`; port
`8080` is also supported when Windows port 80 is occupied by another service.

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
See [VM recovery and validation](INSTALLER_VM_RECOVERY.md) for the dated
recovery evidence; it is not a new acceptance claim for the current defaults.

Continue with the complete
[Raspberry Pi first-boot procedure](RASPBERRY_PI_FIRST_BOOT.md) for phone
setup, initial login, local Agent pairing and acceptance checks.

## Development deployment

For an unpublished development commit, use the laptop-driven [`deploy.ps1`](../deploy.ps1)
workflow documented in the first-boot procedure. The public one-line installer
intentionally accepts only published release artifacts.
