# 3mm

[![Current release](https://img.shields.io/github/v/release/ldobranov/3mm?include_prereleases&label=release)](https://github.com/ldobranov/3mm/releases)
[![CI](https://github.com/ldobranov/3mm/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ldobranov/3mm/actions/workflows/ci.yml)

3mm is a modular edge-control platform for Raspberry Pi and Linux devices. It
combines a central Core, a persistent device Agent, dashboards, provisioning,
runtime extensions and a reviewed AI-assisted extension workflow in one
system.

> **Project status:** Beta. The current physically validated release is
> [v0.3.0-beta.5](https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.5).
> It completed a real Beta-channel OTA update from `v0.3.0-beta.4` on a
> Raspberry Pi 3B+. The project is not yet presented as production-hardened.

## What works

- **Core and web application** — authentication, roles, settings, dynamic
  navigation, dashboards and device management.
- **Persistent Agent** — stable device identity, health and inventory,
  pairing, heartbeat, command processing, reconciliation and offline outbox.
- **Hardware capabilities** — deterministic mock profiles and opt-in native
  Raspberry GPIO input through the official `gpiod` bindings.
- **Provisioning** — browser-based first setup, an open setup-only access
  point, Wi-Fi configuration with rollback and Standalone/Hub/Node roles.
- **Extensions** — declarative runtime extensions and reviewed compiled Vue
  widgets, editors, routes and reusable components.
- **AI Extension Builder** — guided intent planning, editable projects,
  automatic versions, reviewable source changes, deterministic capability
  foundations, compilation and installation.
- **Immutable deployment** — versioned releases, persistent state outside the
  application tree, health checks, rollback and bounded release/backup
  retention.
- **OTA updates** — architecture-specific reproducible artifacts, validated
  manifests, Stable/Beta/Test channels, cached read-only background checks,
  maintenance-window enforcement and explicit administrator approval.

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

Do not treat the development HTTP deployment or open setup-only access point
as the final production security boundary. TLS, marketplace trust and stronger
isolation for third-party executable extensions remain future production work.

## Releases and updates

The source version is stored in [VERSION](VERSION). Releases use immutable
annotated semantic-version tags and publish:

- `aarch64`, `armv7l` and `x86_64` archives;
- `3mm-update-manifest.json`;
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
| [Architecture plan](docs/ARCHITECTURE_PLAN.md) | System boundaries and target architecture |
| [Project rules](docs/PROJECT_RULES.md) | Compatibility, safety and development rules |
| [Roadmap](docs/ROADMAP.md) | Milestones and remaining work |
| [Raspberry baseline](docs/RASPBERRY_PI_BASELINE.md) | Physical device baseline and measurements |
| [First boot](docs/RASPBERRY_PI_FIRST_BOOT.md) | Repeatable Raspberry installation and provisioning |
| [Extension lifecycle](docs/EXTENSION_LIFECYCLE.md) | Package, version and data lifecycle |
| [Runtime extension v1](docs/RUNTIME_EXTENSION_V1.md) | Declarative extension contract |
| [Compiled extension v1](docs/COMPILED_EXTENSION_V1.md) | Reviewed Vue compilation boundary |
| [Module Manifest v2](docs/MODULE_MANIFEST_V2.md) | Package envelope and identities |
| [OTA update plan](docs/OTA_UPDATE_PLAN.md) | Update architecture and acceptance stages |
| [Release guide](docs/RELEASING.md) | Versioning, publication and verification |

Milestone reports in `docs/MILESTONE_*_REPORT.md` retain the detailed
acceptance evidence behind the current implementation.
