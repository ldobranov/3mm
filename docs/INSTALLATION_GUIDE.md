# 3mm installation

The supported Raspberry Pi installation uses an official immutable release.
It does not clone the repository or build the frontend on the device. Limited
ARMv6 dependency compilation may be necessary; passwords are not written to
command arguments.

## Standalone pilot: Core 0.3.19 to a Monitor quote

For the pilot use Debian 13 (Trixie) with systemd, a working Internet connection and a trusted LAN.
Use a local account that can run `sudo`. You need two items: the
[public Core 0.3.19 release](https://github.com/ldobranov/3mm/releases/tag/v0.3.19)
and, separately, the Monitor ZIP from the pilot organizer. No checkout or build is needed.
Do not use the Node profile for this walkthrough: it has no admin panel.

The Full profile needs Node.js 20 or newer. Stock Ubuntu 24.04 supplies Node.js 18:
the 0.3.19 installer stops at `runtime.node` before Setup there. Do not skip this check.
On a minimal Debian 13 image, first run the following **in a root shell** to install the
tools used by the public installer from the distribution repositories:

<!-- pilot-os-tools -->
```bash
apt-get update && apt-get install -y ca-certificates wget sudo python3 dbus
```

On the device, download the installer from the exact tag and run it only if the download succeeds:

<!-- pilot-bootstrap -->
```bash
wget -O install-3mm-0.3.19.sh https://raw.githubusercontent.com/ldobranov/3mm/v0.3.19/install.sh &&
  sudo bash install-3mm-0.3.19.sh --tag v0.3.19
```

The bootstrap checks and downloads the architecture-specific package. It then prints a
systemd job name: **starting the job is not installation success**. Follow the log command
it prints and wait for `Deployment succeeded`. If you reconnect later, the service can
already be gone and the last few log lines can omit the result. Use the exact job name
printed by your installer in place of `<job.service>`. This reads the entire job's journal:

```bash
sudo journalctl -u '<job.service>' --no-pager -o cat -g 'Deployment succeeded|Preflight failed|Deployment failed;|Failed with result'
```

No matching line is **not** a confirmed failure. Read the same job without `-g` and
its pattern to see progress or the first error; do not start a second install. Once
installation succeeds, use the device's Ethernet or Wi-Fi
address (shown by `hostname -I`) in place of `<device-IP>`. From a browser on that LAN,
open `http://<device-IP>:8895/setup`, choose **Standalone** and **Keep the operating
system’s connection**, set the device name and administrator credentials, and **Save setup**.
Finish Setup if prompted. Open `http://<device-IP>/user/login` and sign in with the
administrator **email** and password you just set. If this address briefly shows **404**
immediately after saving Setup, wait a few seconds and reload the same login URL.
Do not repeat Setup. If the page loads but sign-in cannot connect, check
`systemctl status 3mm-core.service 3mm-web.service`. On public 0.3.19, the web
page and the login service can become available at different times.
Do not forward these HTTP ports to the Internet.

### Install Monitor and check the first quote

1. On the computer with the browser, obtain `3mm-crypto-monitor-0.8.4.zip` **from the pilot
   organizer**. This native application is a separate handoff, not a Core release asset.
   Verify its SHA-256 with `sha256sum 3mm-crypto-monitor-0.8.4.zip` on Linux or
   `Get-FileHash -Algorithm SHA256 .\3mm-crypto-monitor-0.8.4.zip` in PowerShell.
   Expected: `02ba896c934ae0629b0609ab28e146e33e882cb3996afce812e87a5451252a1e`.
   If the ZIP is missing or does not match, stop and ask the organizer for the correct file.
2. Open **Extensions**. A clean database intentionally has no initial menu.
   If a link is offered in the **Devices** page itself, choose it. On public 0.3.19
   open `http://<device-IP>/extensions` in the same signed-in browser if no link is shown.
   Choose the ZIP and **Upload Extension**. On the **3mm Crypto Monitor**
   card, select version **0.8.4** and **Install and activate**. If asked for **Display Device Id**,
   select your local Standalone device by name, even for this browser-only pilot.
   Leave the optional button device unset. This selects a device; it does not give hardware access.
3. Continue in the access review if it opens automatically. Otherwise open the card’s
   **Application access → Review or change access**. If a named connection
   needs setup, use **Set up connection**, verify the suggested service address, **Save connection**
   and **Back to access review**. Version 0.8.4 declares both `coinbase`
   (`https://api.coinbase.com`) and `coingecko` (`https://api.coingecko.com`).
   Both addresses must be configured. Saving the CoinGecko address does **not** grant its use.
4. Expand **Permissions and details**. Under application permissions select **only Coinbase**
   (`connector:coinbase`); uncheck CoinGecko and leave display/button and other permissions off.
   Under your account select **only** `monitor_configure`. Verify these two selections before
   **Allow access**. Close the dialog; if the reviewed version is inactive, activate it on the card.
5. On the active card choose **Open**. Leave Monitor open until a fresh **BTC / USD** price
   appears; on the clean Debian pilot the first sample arrived about 48 seconds after approval.
   A blank or stale value, or just an **Active** badge, is not a successful quote.
   If there is no fresh result, check that Coinbase is reachable and inspect **Settings →
   Diagnostics**. Do not enable CoinGecko or hardware permissions to troubleshoot this browser pilot.

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

On a clean Full installation, Setup creates the administrator from the username,
email and password you enter. There is no preinstalled login. If an administrator
already exists, Setup requires their current credentials; it does not replace
their password. In 0.3.16 Factory reset also returns to Setup with no users.
For reset devices on 0.3.12–0.3.13 see the [precautions](DEVICE_ADMINISTRATION.md).

## Preserve the current network, or explicitly choose setup AP

By default a fresh installation retains the host's existing Ethernet or Wi-Fi
configuration. It does not take over networking or require an AP-capable adapter.
Finish initial setup from another device on the same LAN:

```text
http://<device-LAN-IP>:8895/setup
```

For the accepted Raspberry Pi aarch64 profile, choose **Standalone** and
**Keep the operating system’s connection**. Set the administrator credentials
and choose **Save setup**. When setup completes, open
`http://<device-LAN-IP>/user/login` and use the email and password you entered.
Both pages use HTTP; complete setup on a trusted LAN, not via Internet port forwarding.

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

For the exact 0.3.19 pilot command, see the
[Standalone walkthrough](#standalone-pilot-core-0319-to-a-monitor-quote) above.

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

For a Standalone Full installation, first save a
[portable recovery file](BACKUP_AND_RESTORE.md#administrator-workflow) off the Pi.
Only for a device still on 0.3.11, run the following on the device instead of
using its old web updater. For a minimal Node append `--profile node`; keep
the existing installation profile. Do not downgrade a newer installation.

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/v0.3.12/install.sh | \
  sudo bash -s -- --tag v0.3.12
```

Follow the journal command printed by the
bootstrap until installation finishes; returning to the shell is not success.
The target installer coordinates the existing Agent, Runtime/connector worker and
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

After a successful Standalone update, sign in again and check that your
applications and their data are present. If the installer reports rollback,
inspect the journal and the restored version before considering a retry.

On a Full update the installer proves the existing installation identity
before it stops services. A busy live SQLite database gets a bounded read-only
wait (up to 15 seconds). A busy database, unreadable database, and unusable
recovery key are different failures. None authorizes creating a replacement
key or switching releases. A preflight refusal is not a completed rollback:
check the active release and its services; do not repeatedly submit the same job.

## If a browser tab still shows the old panel

After the installer confirms an update or rollback, reload the admin page
normally (F5). Firefox can keep a page it previously cached from **0.3.17**
without contacting the device, even on F5. For that tab, keep the device
address and open the same page with a fresh query in the address bar, e.g.
`/monitor?check-update` instead of `/monitor`. Do not run the update again
or change application permissions to refresh the panel. Once a page is served
by the corrected web server it is not cached; versioned scripts still are.

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
