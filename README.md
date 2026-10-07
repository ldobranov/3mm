# 3mm

[![Current release](https://img.shields.io/github/v/release/ldobranov/3mm?include_prereleases&label=release)](https://github.com/ldobranov/3mm/releases)
[![CI](https://github.com/ldobranov/3mm/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ldobranov/3mm/actions/workflows/ci.yml)

3mm is a modular edge-control platform for Raspberry Pi and Linux devices. It
combines a central Core, a persistent device Agent, dashboards, provisioning,
runtime extensions and a reviewed AI-assisted extension workflow in one
system.

> **Project status:** Beta. This source prepares **v0.3.0-beta.42**, adding
> target-owned Update Contract v2 and shared Frontend Bootstrap/Data Access v1
> to the accepted Theme Platform V5 and merged Milestone 19 foundation.
> It includes the generic Public Web Runtime and Application
> Extension HTTP contract while keeping the administrative SPA isolated on its
> existing surface. The release contains no Shop or SEO-specific Core logic.
> Existing device transport, capability authority and lifecycle remain unchanged.
> Device protocol 1.0, Application SDK 1.3, installation peers and Node Update remain.
> Release assets become available only after the tag-driven workflow succeeds;
> the release badge above reflects published versions. Linux + independent mock
> embedded/application acceptance passed locally; deployed Hub/Zero/Fleet checks
> remain pending. No real ESP firmware, automatic cloud connection or device update.
> Real peer v2 HTTPS/Linux acceptance, Cloud Manager integration and public ingress
> remain separate work.
>
> Beta.36 published the compatible v1 theme platform. Theme lifecycle, v2 asset
> loading and portable recovery are locally checked; desktop/mobile light/dark
> review used an isolated fixture, not a live device. Installed-package preview,
> licensed font/Cyrillic proof and the integrated theme editor passed local V5
> review; V6–V8 screen migration, extension UI adoption and live recovery remain.
> Updates keep the existing appearance until an administrator selects a v2 theme.
> No concrete theme (including Graphite Mint) or business extension is bundled.

## What works

- **Core and web application** — authentication, roles, settings, dynamic
  navigation, dashboards and device management.
- **Persistent Agent** — stable device identity, health and inventory,
  pairing, heartbeat, command processing, reconciliation and offline outbox.
- **Shared Device/Node Platform** — versioned neutral inventory and one capability
  registry for module, native and firmware providers, with advertised runtime
  features, strict optional capability contracts, authority/lifecycle and an
  independent mock client. Discovery does not grant execution authority; fresh
  health is distinct from persistent selection. Fleet is optional, not a prerequisite.
- **Hardware capabilities** — deterministic mock profiles and opt-in native
  Raspberry digital input/output through the official `gpiod` bindings,
  edge-driven inputs and safe bounded output pulses.
- **Provisioning and recovery** — browser-based first setup, Wi-Fi scan and
  rollback, an open setup-only access point, secret-free recovery prefill,
  administrator-controlled network recovery and Standalone/Hub/Node roles.
- **Device administration** — audience-aware dynamic menus, audited Raspberry
  restart and an explicit 3mm factory reset that returns an installed device
  to first-boot setup.
- **Backup and diagnostics** — encrypted local snapshots, transactional
  restore with rollback, password-protected disaster-recovery downloads and
  secret-redacted diagnostic bundles.
- **Extensions** — declarative runtime extensions and reviewed compiled Vue
  widgets, editors, routes and reusable components, plus the locally completed
  supervised application-service foundation for transactional extensions.
- **Installable themes** — compatible v1 palettes and v2 design packages with
  Core-owned layout/component variants and bounded local fonts/logos, without
  arbitrary CSS or executable code. Upload, enable, disable and delete versions in
  Extensions; select an enabled version or built-in appearance in Settings.
  Invalid or disabled packages fall back safely; temporary network failures retain
  the last verified theme. Existing custom settings remain.
- **AI Extension Builder** — guided intent planning, editable projects,
  automatic versions, reviewable source changes, deterministic capability
  foundations, compilation and installation.
- **Immutable deployment** — versioned releases, persistent state outside the
  application tree, health checks, rollback and bounded release/backup
  retention.
- **OTA updates** — architecture-specific reproducible artifacts, validated
  manifests, Stable/Beta/Test channels, cached read-only background checks,
  maintenance-window enforcement and explicit administrator approval. Full-profile
  updates execute the verified target artifact's installer from a root-private
  snapshot, with versioned preflight and persistent failure diagnostics.
- **Shared frontend bootstrap** — cached runtime configuration and public
  extension discovery shared by routing, translations and extension consumers,
  with single-flight requests, bounded timeouts and failure cooldowns. HTTP
  interceptors do not perform discovery or replay uncertain mutations.
- **Optional installation peers** — encrypted installation identity, verified
  HTTPS enrollment with separate local consent and receiver approval, limited
  status sharing, revocation and durable retries. Peer v2 binds an opaque
  application intent and exact consent revision/hash to proofs and approval;
  changing the selection stops export until reapproval. No cloud command authority.

## Architecture

```text
Browser
   |
   v
Core API + SQLite  <---->  Runtime and compiled extension artifacts
   |
   | authenticated device protocol
   v
Agent  <---->  hardware drivers and local capabilities

Provisioning selects the device role.
The immutable updater activates releases and preserves rollback state.
```

The Core does not hardcode concrete extensions. Routes, navigation, widgets
and data contracts are discovered from validated package metadata. The Agent
is the hardware boundary; browser code and generated extensions do not access
devices directly.

## Technology

- Python 3.10+ and FastAPI
- SQLAlchemy, Alembic and SQLite
- Vue 3, TypeScript, Vite, Pinia and Vue Router
- Bootstrap plus project CSS tokens and native Vue components
- systemd and NetworkManager on the Raspberry deployment
- pnpm for locked frontend release builds

## Local development

Recommended host tools:

- Python 3.13;
- Node.js 22;
- pnpm 10.13.1.

On Linux, macOS or WSL, start Core and the development frontend from the
repository root:

```bash
./dev.sh
```

The launcher creates `backend/.venv`, starts Core on
`http://localhost:8887`, waits for health and starts Vite on
`http://localhost:5173`.

On Windows, prepare the backend once:

```powershell
py -3 -m venv backend\.venv
backend\.venv\Scripts\python -m pip install -r backend\requirements-dev.txt
```

Then run Core:

```powershell
backend\.venv\Scripts\python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8887
```

In a second terminal, run the frontend:

```powershell
cd frontend
corepack enable
corepack prepare pnpm@10.13.1 --activate
pnpm install --frozen-lockfile
pnpm run dev
```

### Quality checks

From the repository root:

```bash
backend/.venv/bin/python -m pytest -q
pnpm --dir frontend run test:unit -- --run
pnpm --dir frontend run type-check
pnpm --dir frontend run build-only
```

On Windows, use `backend\.venv\Scripts\python` for the Python command.
Four Agent tests that assert Unix `0600` mode bits are expected to fail on
NTFS; the same paths are enforced and tested on Linux.

### Standalone Agent

Run an isolated development Agent with a persistent identity:

```bash
backend/.venv/bin/python -m agent \
  --data-dir .runtime/agent \
  --name local-agent \
  --role standalone
```

The Agent listens on `127.0.0.1:8890` by default:

- `/health`
- `/ready`
- `/api/v1/agent/hello`
- `/api/v1/agent/inventory`

Use `./dev-agents.sh` to start two independent mock devices.

## Raspberry Pi

For a clean Raspberry Pi OS/Debian installation, the normal Beta bootstrap is
one command:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | sudo bash
```

Git is not required on the Raspberry Pi. The bootstrap selects the latest
published Beta artifact for the device architecture, installs its reviewed APT
dependencies, verifies its size and SHA-256 digest, runs the read-only host
preflight and starts the immutable installer as a detached systemd job. This
allows installation over Wi-Fi: the SSH session is expected to close only when
the device switches to its open `3mm Setup XXXX` access point.

### Minimal Node / Raspberry Pi Zero W

Fleet beta.21 adds a minimal Node profile for **Zero W ARMv6 with
Raspbian 13 / Python 3.13**. It installs Agent and shared Setup/recovery, not Core,
the application database or npm. After a release containing Node assets is published:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | sudo bash -s -- --profile node
```

This command is **not available in beta.19 or earlier**; beta.20 published no assets. It requires
the new bootstrap and `3mm-node-manifest.json` release asset. Other Node
architectures/Python versions are rejected rather than compiling on-device.
The fresh-install Setup AP changes Wi-Fi and may disconnect SSH. Setup only
offers the Node role. Local enrollment and administrator approval are available
through the optional Fleet extension; installing Node is not completed pairing.
There is no permanent Node administration page. The optional Fleet extension
provides a Hub-side Node runtime OTA interface; trust bootstrap is described below.
See [Node installation](docs/NODE_INSTALLATION.md) for scope and verification.

### Updating a paired Hub and Zero

After beta.42 is fully published, manually install this first corrected
full-profile release on the two existing development hosts (Raspberry/WSL):

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | sudo bash -s -- --tag v0.3.0-beta.42
```

An older installed updater cannot acquire the target-installer fix before it
runs. Test a subsequent official release through `/system/updates` using the
Beta channel; no bridge release or reset is required. Update the Zero over SSH
with the Node bootstrap command above and add `--tag v0.3.0-beta.42` to select
this exact release. Provisioned upgrades preserve identity and pairing, not
Master reset. Real update/rollback and browser request/CPU checks remain pending;
see [platform stability acceptance](docs/PLATFORM_STABILITY_ACCEPTANCE.md).
Then upload Fleet `0.1.7` on the Hub through Extensions. Updating the Fleet ZIP
alone does not update Core or the Zero Agent. Follow the
[GPIO configuration guide](docs/FLEET_GPIO_CONFIGURATION.md) before enabling outputs.
The signed Node OTA path requires an explicit one-time Hub key trust bootstrap;
see [Node update scope and acceptance](docs/FLEET_NODE_OTA.md). Fleet 0.1.7
exposes prepare and explicit install controls, while Core remains the source of truth.
Already paired, signed-update-capable Nodes with a verified Hub key pin can be
updated from Fleet instead of SSH. Unknown outcomes must be reviewed, not replayed.
The new Node check reports the latest release and confirmed Hub OTA history;
manual upgrades without that history remain unknown, not automatically up to date.

Use `--tag` for a reproducible exact release, for example by appending
`-s -- --tag v0.3.0-beta.11` after `sudo bash`. The Raspberry host password is
requested only by `sudo` and is never a command argument or repository value.

During Beta, a brand-new empty database receives one test administrator:

- email: `admin@example.com`
- password: `admin`

Sign in and replace this password from **Profile**. Updates never recreate this
account, reset its password or change existing users. The interactive secure
administrator bootstrap remains available for installations that do not use
the Beta default.

The tested deployment uses an immutable layout:

```text
/opt/3mm/current  -> /opt/3mm/releases/<release-id>
/opt/3mm/previous -> last rollback release
/var/lib/3mm      -> persistent application and device state
```

Start with the
[Raspberry Pi first-boot procedure](docs/RASPBERRY_PI_FIRST_BOOT.md). It covers
preflight, installation, setup Wi-Fi, administrator bootstrap, Agent pairing
and smoke checks. The normal installer performs backup, migration, atomic
activation, health verification and rollback.

Wired-only Linux/VM installer corrections are included since beta.35: absent first-boot
state initializes Standalone without a Wi-Fi AP, required service groups are
created, and upgrade rollback restores the previously active services. They take
effect through the published release assets; see
[VM installer behavior and remaining live checks](docs/INSTALLER_VM_RECOVERY.md).

On a provisioned device, open the application at `http://<device-ip>/` or
`http://<hostname>.local/`. Port `8080` remains available for compatibility.
The [network recovery guide](docs/NETWORK_RECOVERY.md) covers manual setup
Wi-Fi, the optional five-minute offline trigger and the phone captive portal.
The [device administration guide](docs/DEVICE_ADMINISTRATION.md) documents
public navigation, restart and the exact factory-reset boundary.
The [backup and restore guide](docs/BACKUP_AND_RESTORE.md) explains local
recovery and how to keep a password-protected `.3mmrecovery` file away from
the device for failed-SD-card recovery. The
[diagnostics guide](docs/DIAGNOSTICS.md) records the redaction boundary.

Do not treat the development HTTP deployment or open setup-only access point
as the final production security boundary. TLS, marketplace trust and stronger
isolation for third-party executable extensions remain future production work.

## Releases and updates

The source version is stored in [VERSION](VERSION). Releases use immutable
annotated semantic-version tags and publish:

- `aarch64`, `armv7l` and `x86_64` archives;
- `3mm-update-manifest.json`;
- a separate ARMv6 Node archive and `3mm-node-manifest.json`;
- `SHA256SUMS`.

Stable releases use the Stable channel, `-test...` prereleases use Test and
other prereleases use Beta. The updater verifies release identity, checksum,
architecture, dependencies and preflight conditions before it can ask for
explicit administrator approval. Administrators can opt into cached background
catalog checks with persisted retry backoff. A daily maintenance window can
gate installation; applying outside it requires a separate explicit override.
Background checks never download or install a release.

Since beta.42, full-profile artifacts include their own versioned deployment
contract and required-file declaration. The privileged updater revalidates the
approved official bytes, freezes a private archive/installer snapshot and checks
installer syntax before dependency changes. Unknown contracts fail closed;
legacy artifacts retain a compatible minimum. Release metadata and Manifest v1,
the dependency allowlist, explicit approval, immutable layout and rollback owner
remain unchanged. Node updates use their existing separate workflow.

The final approval dialog shows the installed version and the exact verified
version to install separately. Fresh installed-release metadata takes precedence
over an older cached catalog check; unknown metadata is not replaced by the target.

See the [changelog](CHANGELOG.md) for user-visible changes and the
[release guide](docs/RELEASING.md) for the maintainer workflow.

### Installing a visual theme

After updating Core to beta.37, upload your separate v1/v2 theme ZIP through
**Extensions**, enable it, then select it in **Settings → Theme Customization**
and apply. Enabling a package or updating Core does not select a new theme.
Concrete themes are not included in the Core release archives or release assets.

Since beta.38, refresh waits for appearance initialization before showing the
application shell and pages. A brief neutral loading screen prevents the default
layout from appearing first. Waiting is limited to eight seconds; unavailable
resources fall back safely, retaining the browser's saved mode and language.

Since beta.39, **Theme Customization** owns layout, density, button/card variants
and header colors, with Save, Discard and Reset controls. Changes are scoped to
the exact theme version or built-in appearance; theme ZIPs remain immutable.
**Header Customization** owns translated text and the logo. Personal light/dark
mode remains separate. Uploaded settings images use persistent
`/var/lib/3mm/core/uploads/settings`, retaining their public URLs across updates
and participating in portable backup/restore.

Since beta.40, installed themes also expose their supported color parameters in
Theme Customization: 11 legacy colors for v1, 17 semantic colors for v2. Edit
light/dark palettes independently, preview before Save, discard or restore a
palette. V2 changes must retain readable contrast. Overrides are version-scoped;
the original ZIP and built-in colors are preserved. Public uploaded logos are
served on the same web origin on ports 80/8080, including when reopened for editing.

The v2 shell preserves data-driven navigation, translations and access rules;
legacy screens and extensions are not automatically redesigned. If installed
styling becomes unusable, sign in as an administrator and open
`/settings/ui-preview?recovery=1`, then choose **Use built-in permanently**.
This clears only the theme selection, not saved settings or application data.
Since beta.41, Theme Customization combines layout/color controls with live
component samples using the selected package's actual design and local font.
Optional `customization_options` in a v2 package declares which bounded variants
and colors are editable; omitted declarations preserve older packages' controls.
Packages using that new field require beta.41 or newer Core. Changes remain
version-scoped and are persisted only by **Save appearance**.

**Preview theme** can temporarily load another enabled package without changing
the installation selection; Cancel restores the selected appearance. Apply that
package before editing its saved controls. Preview assets require administrator
access; public serving remains selected-only. Theme ZIPs remain separate uploads,
not Core release assets. Ordinary `/settings/ui-preview` bookmarks redirect to
the integrated editor; the explicit recovery URL above remains independent.

An idle tab retains its last verified theme, preferences and loaded resources if
appearance refresh fails. A verified deselection or disabled/corrupt package still
uses built-in fallback. This does not repair DNS/network outages or make a fresh
offline browser capable of fetching missing resources.

## Documentation

| Document | Purpose |
| --- | --- |
| [Product master plan](docs/MASTER_PLAN.md) | Local-first product sequence and optional central extensions |
| [Architecture plan](docs/ARCHITECTURE_PLAN.md) | System boundaries and target architecture |
| [Platform-neutral Nodes plan](docs/PLATFORM_NEUTRAL_NODES_PLAN.md) | C0–C14 shared device, transport, authority and capability contracts |
| [Device transport boundary](docs/PLATFORM_NEUTRAL_C10.md) | C10 logical operations, HTTP adapter and non-HTTP proof |
| [Versioned capability contracts](docs/PLATFORM_NEUTRAL_C11.md) | C11 exact versions, bounded schemas and pre-dispatch compatibility checks |
| [Device authority and lifecycle](docs/PLATFORM_NEUTRAL_C12_C13.md) | C12/C13 installation pins, release/recovery and separate reset policies |
| [Capability configuration and health](docs/PLATFORM_NEUTRAL_C14.md) | C14 supported offers, Core-owned selection, fresh availability and compatible dispatch |
| [Wired-only VM installer](docs/INSTALLER_VM_RECOVERY.md) | Standalone first boot, service groups, safe activation and rollback |
| [Node regression baseline](docs/PLATFORM_NEUTRAL_C0.md) | Existing Linux Agent behavior, focused test gate and limitations |
| [Platform-neutral inventory](docs/PLATFORM_NEUTRAL_C1.md) | Schema 2, legacy compatibility, Agent configuration and Fleet adoption |
| [Project rules](docs/PROJECT_RULES.md) | Compatibility, safety and development rules |
| [Users and access](docs/ACCESS_CONTROL.md) | Roles, groups, scoped permissions and extension delegation handoff |
| [Roadmap](docs/ROADMAP.md) | Milestones and remaining work |
| [Raspberry baseline](docs/RASPBERRY_PI_BASELINE.md) | Physical device baseline and measurements |
| [First boot](docs/RASPBERRY_PI_FIRST_BOOT.md) | Repeatable Raspberry installation and provisioning |
| [Network recovery](docs/NETWORK_RECOVERY.md) | Port 80, hostname access, setup AP and Wi-Fi recovery |
| [Device administration](docs/DEVICE_ADMINISTRATION.md) | Menu audiences, restart and factory reset |
| [Backup and restore](docs/BACKUP_AND_RESTORE.md) | Local snapshots, portable recovery and restore safety |
| [Core asset storage](docs/CORE_ASSET_STORAGE.md) | Persistent public assets outside immutable releases |
| [Redacted diagnostics](docs/DIAGNOSTICS.md) | Support bundle contents and secret exclusions |
| [Extension lifecycle](docs/EXTENSION_LIFECYCLE.md) | Package, version and data lifecycle |
| [Theme Platform plan](docs/THEME_EXTENSION_PLAN.md) | Theme lifecycle, browser activation and remaining acceptance stages |
| [Theme extension v1](docs/THEME_EXTENSION_V1.md) | Closed light/dark token contract and shared Extensions upload |
| [Theme Platform v2 plan](docs/THEME_PLATFORM_V2_PLAN.md) | V0–V5 delivery and remaining screen/recovery acceptance |
| [Theme Design API 2](docs/THEME_DESIGN_API_V2.md) | Shared tokens, component variants, shell modes and compatibility |
| [Theme extension v2](docs/THEME_EXTENSION_V2.md) | Package/asset validation, lifecycle, loader and recovery |
| [Embedded Nodes extension plan](docs/EMBEDDED_NODES_EXTENSION_PLAN.md) | Deferred firmware/extension work outside Core |
| [Runtime extension v1](docs/RUNTIME_EXTENSION_V1.md) | Declarative extension contract |
| [Compiled extension v1](docs/COMPILED_EXTENSION_V1.md) | Reviewed Vue compilation boundary |
| [Application extension v1 plan](docs/APPLICATION_EXTENSION_V1_PLAN.md) | Planned trusted business-service and integration boundary |
| [Application commands and passage](docs/APPLICATION_COMMANDS.md) | Scoped SDK commands, crash/restore safety and correlated sensor evidence |
| [Application job scheduler](docs/APPLICATION_JOB_SCHEDULER.md) | Interval scheduling, bounded concurrency and unknown-outcome recovery |
| [Installation identity v1](docs/INSTALLATION_IDENTITY_V1.md) | Stable identity, bounded proofs, backup and clone boundaries |
| [Installation peers v1](docs/INSTALLATION_PEER_V1.md) | SDK 1.2 consent, enrollment, status projection and HTTPS acceptance |
| [Installation peers v2](docs/INSTALLATION_PEER_V2.md) | SDK 1.3 verified intent, exact consent review and reapproval boundaries |
| [Module Manifest v2](docs/MODULE_MANIFEST_V2.md) | Package envelope and identities |
| [OTA update plan](docs/OTA_UPDATE_PLAN.md) | Update architecture and acceptance stages |
| [Platform stability acceptance](docs/PLATFORM_STABILITY_ACCEPTANCE.md) | Target-owned updater, shared bootstrap and pending real-device checks |
| [Release guide](docs/RELEASING.md) | Versioning, publication and verification |
| [Fleet GPIO configuration](docs/FLEET_GPIO_CONFIGURATION.md) | Compatible updates and one safe output without SSH |
| [Fleet Node OTA](docs/FLEET_NODE_OTA.md) | Signed Hub approval, Node trust and independent installation outcomes |
| [Fleet business plan](docs/FLEET_BUSINESS_PLAN.md) | Local-first delivery before optional cloud and paid functions |

Milestone reports in `docs/MILESTONE_*_REPORT.md` retain the detailed
acceptance evidence behind the current implementation.
