# 3mm Baseline Audit

Audit date: 2026-08-09  
Revision inspected: `24c9eb2` (`main`)  
Planning branch: `planning/core-agent-roadmap`

## Environment

- Python 3.12.13
- Node.js 24.14.0
- npm 11.9.0
- temporary clean Python virtual environment
- temporary SQLite database supplied through `DATABASE_URL`
- frontend dependencies installed with `npm ci`

No committed application behavior was changed during this audit.

## Current result

The repository does not currently start cleanly on a new laptop. The blockers are reproducible and belong to the application baseline, not to Raspberry Pi hardware.

| Check | Result | Finding |
|---|---|---|
| Backend dependency installation | Pass | Unpinned current packages install successfully |
| Backend startup with SQLite | Fail | Background tasks are created during module import without a running event loop |
| Database table creation with SQLite | Partial pass | Tables are created before backend startup fails |
| Frontend dependency installation | Pass | `npm ci` succeeds with a writable npm cache |
| Frontend TypeScript check | Pass | `vue-tsc --build` exits successfully |
| Frontend production build | Fail | Top-level `await` is incompatible with configured Vite browser targets |
| Backend test collection | Fail | Duplicate `menus` table model and missing compatible TestClient dependency |

## Blocker 1 — Backend startup lifecycle

Reproduction:

```bash
DATABASE_URL=sqlite:////tmp/3mm-baseline.db \
  uvicorn backend.main:app --host 127.0.0.1 --port 8887
```

Observed failure:

```text
RuntimeError: no running event loop
```

Cause:

`backend/main.py` calls `asyncio.create_task()` at module import time for the update worker, performance monitor and enabled-extension loader. Application background work must be started from FastAPI's lifespan/startup lifecycle and stopped during shutdown.

Required correction:

- add an application lifespan context;
- start managed tasks only after the event loop is running;
- retain task references;
- cancel and await tasks during shutdown;
- add a startup smoke test.

## Blocker 2 — Machine-specific database configuration

`backend/database_config.json` contains a concrete PostgreSQL username, password and database. Because this file has priority over root `config.json`, a clean checkout attempts to use that local PostgreSQL instance.

Required correction:

- remove active credentials from tracked configuration;
- rotate the exposed password if it has been used anywhere beyond local development;
- make SQLite the development default;
- use environment variables and a checked-in non-secret example;
- add a configuration validation test.

## Blocker 3 — Frontend production build

TypeScript validation passes, but `vite build` fails because `frontend/src/router/index.ts` uses top-level `await` while the configured build target includes browsers that do not support it.

Required correction:

- move asynchronous router creation into an explicit application bootstrap function; or
- intentionally raise the supported browser target and document that decision.

The preferred fix is an explicit bootstrap function because application initialization remains clear and does not depend on top-level module evaluation.

## Blocker 4 — Backend tests

Test collection fails before meaningful tests execute:

1. `backend.db.menu.Menu` and another imported model both define the `menus` table in the same SQLAlchemy metadata.
2. Current unpinned FastAPI/Starlette dependencies require a TestClient package not declared by the project.
3. Custom pytest markers are not registered.

Required correction:

- choose one canonical Menu model and migrate imports;
- pin a compatible dependency set;
- include test-only dependencies in a reproducible development installation;
- register project markers;
- separate legacy tests from the trusted baseline suite.

## Other high-priority observations

- `MainServerExtension` returns a hardcoded mock device list.
- Documented registration and heartbeat endpoints are not implemented.
- Update deployment creates a package but does not transfer or apply it.
- arbitrary extension Python is imported directly into the Core process;
- the existing Python sandbox is not used as a security boundary by the extension loader;
- CORS currently permits every origin while credentials are enabled;
- application startup creates database tables directly instead of treating Alembic as the production migration path;
- dependencies are not version-pinned, so installing at different dates can produce incompatible environments;
- temporary generated extensions, uploaded images and debug behavior remain in the repository.

## Recommended next commit sequence

1. `docs: define core-agent architecture and roadmap`
2. `fix: make development configuration portable and secret-free`
3. `fix: manage backend workers through FastAPI lifespan`
4. `fix: make frontend bootstrap compatible with production build`
5. `test: establish a reproducible baseline quality gate`
6. `refactor: introduce shared protocol package and minimal agent`

Each commit must leave the project in a demonstrably better and independently reviewable state.

