# Milestone 0 Completion Report

Completion date: 2026-08-09
Branch: `planning/core-agent-roadmap`
Goal: a reproducible laptop baseline before introducing the real Agent

## Outcome

The current Core and frontend now install, test, build and start on a laptop without PostgreSQL or Raspberry Pi hardware. The default development database is SQLite, runtime workers follow the FastAPI application lifecycle, and both applications can be launched with one command:

```bash
./dev.sh
```

This milestone stabilizes the inherited application. It does not yet implement the standalone Agent, device pairing or real GPIO.

## Completed work

| Area | Result |
|---|---|
| Architecture | Core/Agent boundaries, project rules and the milestone roadmap are documented |
| Configuration | Typed environment-driven settings and a safe SQLite development default |
| Secrets | The active tracked PostgreSQL credential file was removed and `.env.example` was added |
| Backend lifecycle | Background workers start and stop through FastAPI lifespan instead of module import |
| Observability | `/health` and `/ready` endpoints are available |
| Frontend bootstrap | Router initialization no longer relies on top-level `await` |
| Dependencies | Reproducible base and development Python requirements are pinned |
| Tests | A trusted backend baseline suite covers configuration, models, lifecycle and public routes |
| Local launcher | `dev.sh` provisions dependencies and starts Core plus the Vue development server |
| Repository hygiene | Tracked logs, bytecode and the obsolete checked-in Python environment artifacts were removed |

## Verification

Final checks were run from the project root after all implementation and repository cleanup.

| Check | Result |
|---|---|
| Fresh Python 3.12 development dependency installation | Pass |
| Backend test suite | Pass: 10 tests |
| Frontend TypeScript check and production build | Pass |
| Core startup through Uvicorn | Pass |
| `GET /health` | HTTP 200 |
| `GET /ready` | HTTP 200 |
| OpenAPI document | HTTP 200 |
| Combined `./dev.sh` launcher | Pass: Core on port 8887 and frontend on 127.0.0.1:5173 |

## Reviewable commit sequence

1. `36203a3` — architecture, rules and roadmap
2. `1eba0e3` — portable development configuration
3. `89e9334` — managed backend worker lifecycle
4. `0b17a2d` — production-safe frontend bootstrap
5. `124fc91` — reproducible backend test baseline
6. `96b4b3f` — one-command local launcher
7. `e24e89d` — removal of generated Python artifacts from Git

## Known follow-up work

The following findings are recorded rather than hidden by the green baseline:

- the standalone Agent and shared protocol package start in Milestone 1;
- the Main Server extension still shows mock devices until the registry arrives in Milestone 2;
- existing Pydantic, SQLAlchemy and UTC datetime deprecation warnings need incremental cleanup;
- the language routes currently produce a duplicate OpenAPI operation ID warning;
- the main frontend JavaScript chunk is slightly above Vite's 500 kB warning threshold;
- the legacy installer needs redesign around the new Core/Agent packaging model;
- arbitrary extension code still runs inside Core and is not considered a security boundary;
- the removed database credential remains in public Git history and must be rotated if it was ever used outside disposable local development.

## Milestone 1 entry criteria

Milestone 1 can now begin without Raspberry hardware. Its first vertical slice is:

1. define versioned shared schemas for `agent.hello`, health and inventory;
2. create a standalone Agent process with stable identity and isolated data directory;
3. add a mock hardware driver that has no Raspberry-specific imports;
4. launch two independent mock Agents on the laptop;
5. add contract and restart-persistence tests;
6. keep Core registry-driven, with no concrete module names in Core logic.
