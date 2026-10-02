# 3mm

[![Current release](https://img.shields.io/github/v/release/ldobranov/3mm?include_prereleases&label=release)](https://github.com/ldobranov/3mm/releases)
[![CI](https://github.com/ldobranov/3mm/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ldobranov/3mm/actions/workflows/ci.yml)

3mm is a modular edge-control platform for Raspberry Pi and Linux devices. It
combines a central Core, a persistent device Agent, dashboards, provisioning,
runtime extensions and a reviewed AI-assisted extension workflow in one
system.

> **Project status:** Beta. The current release is
> [v0.3.0-beta.31](https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.31),
> introducing installation identity, consent-scoped HTTPS peers and Application
> SDK 1.2, plus read-only Node Update checks. Isolated Raspberry peer acceptance
> passed; Cloud Manager business integration and public ingress are still separate
> work. This release does not automatically connect to a cloud or update devices.

## What works

- **Core and web application** — authentication, roles, settings, dynamic
  navigation, dashboards and device management.
- **Persistent Agent** — stable device identity, health and inventory,
  pairing, heartbeat, command processing, reconciliation and offline outbox.
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
- **AI Extension Builder** — guided intent planning, editable projects,
  automatic versions, reviewable source changes, deterministic capability
  foundations, compilation and installation.
- **Immutable deployment** — versioned releases, persistent state outside the
  application tree, health checks, rollback and bounded release/backup
  retention.
- **OTA updates** — architecture-specific reproducible artifacts, validated
  manifests, Stable/Beta/Test channels, cached read-only background checks,
  maintenance-window enforcement and explicit administrator approval.
- **Optional installation peers** — encrypted installation identity, verified
  HTTPS enrollment with separate local consent and receiver approval, limited
  status sharing, revocation and durable retries. No cloud command authority.

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

After the new GitHub Release is fully published, update the Hub through
`/system/updates` using the Beta channel. Update the Zero over SSH with the same
Node bootstrap command above; add `--tag v0.3.0-beta.31` to select the published
release. Provisioned upgrades preserve identity and pairing, not Master reset.
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

See the [changelog](CHANGELOG.md) for user-visible changes and the
[release guide](docs/RELEASING.md) for the maintainer workflow.

## Documentation

| Document | Purpose |
| --- | --- |
| [Product master plan](docs/MASTER_PLAN.md) | Local-first product sequence and optional central extensions |
| [Architecture plan](docs/ARCHITECTURE_PLAN.md) | System boundaries and target architecture |
| [Project rules](docs/PROJECT_RULES.md) | Compatibility, safety and development rules |
| [Users and access](docs/ACCESS_CONTROL.md) | Roles, groups, scoped permissions and extension delegation handoff |
| [Roadmap](docs/ROADMAP.md) | Milestones and remaining work |
| [Raspberry baseline](docs/RASPBERRY_PI_BASELINE.md) | Physical device baseline and measurements |
| [First boot](docs/RASPBERRY_PI_FIRST_BOOT.md) | Repeatable Raspberry installation and provisioning |
| [Network recovery](docs/NETWORK_RECOVERY.md) | Port 80, hostname access, setup AP and Wi-Fi recovery |
| [Device administration](docs/DEVICE_ADMINISTRATION.md) | Menu audiences, restart and factory reset |
| [Backup and restore](docs/BACKUP_AND_RESTORE.md) | Local snapshots, portable recovery and restore safety |
| [Redacted diagnostics](docs/DIAGNOSTICS.md) | Support bundle contents and secret exclusions |
| [Extension lifecycle](docs/EXTENSION_LIFECYCLE.md) | Package, version and data lifecycle |
| [Runtime extension v1](docs/RUNTIME_EXTENSION_V1.md) | Declarative extension contract |
| [Compiled extension v1](docs/COMPILED_EXTENSION_V1.md) | Reviewed Vue compilation boundary |
| [Application extension v1 plan](docs/APPLICATION_EXTENSION_V1_PLAN.md) | Planned trusted business-service and integration boundary |
| [Application commands and passage](docs/APPLICATION_COMMANDS.md) | Scoped SDK commands, crash/restore safety and correlated sensor evidence |
| [Application job scheduler](docs/APPLICATION_JOB_SCHEDULER.md) | Interval scheduling, bounded concurrency and unknown-outcome recovery |
| [Installation identity v1](docs/INSTALLATION_IDENTITY_V1.md) | Stable identity, bounded proofs, backup and clone boundaries |
| [Installation peers v1](docs/INSTALLATION_PEER_V1.md) | SDK 1.2 consent, enrollment, status projection and HTTPS acceptance |
| [Module Manifest v2](docs/MODULE_MANIFEST_V2.md) | Package envelope and identities |
| [OTA update plan](docs/OTA_UPDATE_PLAN.md) | Update architecture and acceptance stages |
| [Release guide](docs/RELEASING.md) | Versioning, publication and verification |
| [Fleet GPIO configuration](docs/FLEET_GPIO_CONFIGURATION.md) | Compatible updates and one safe output without SSH |
| [Fleet Node OTA](docs/FLEET_NODE_OTA.md) | Signed Hub approval, Node trust and independent installation outcomes |
| [Fleet business plan](docs/FLEET_BUSINESS_PLAN.md) | Local-first delivery before optional cloud and paid functions |

Milestone reports in `docs/MILESTONE_*_REPORT.md` retain the detailed
acceptance evidence behind the current implementation.
