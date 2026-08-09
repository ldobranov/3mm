# 3mm Roadmap

Status: draft for review  
Planning style: sequential milestones with a runnable result after every milestone

Dates are intentionally not assigned until the current baseline is reproducible. Progress is measured by acceptance criteria, not optimistic calendar estimates.

## Milestone 0 — Reproducible baseline

Goal: make the existing project safe to start and evaluate on a new laptop without machine-specific services.

Deliverables:

- inventory of current working, mocked and broken features;
- clean development configuration using SQLite;
- `.env.example` or typed settings defaults with no secrets;
- removal of committed live credentials and local generated artifacts from active configuration;
- one documented development start command;
- backend health endpoint and frontend startup verification;
- backend test command and frontend type-check/build command;
- baseline issue list without unrelated rewrites.

Acceptance criteria:

- a clean clone starts on a laptop without PostgreSQL;
- no secret or local-machine credential is required;
- backend health check succeeds;
- frontend loads and reaches the backend;
- test/build results are recorded.

## Milestone 1 — Core and Agent foundations

Goal: introduce a real Agent as a separate application and establish shared contracts.

Deliverables:

- `core`, `agent` and shared protocol package boundaries;
- versioned protocol schemas;
- stable Agent identity and isolated local data directory;
- mock hardware driver interface;
- Agent CLI and health endpoint;
- laptop launcher for two or more mock Agents;
- lifecycle-managed Core background services.

Acceptance criteria:

- two Agents run concurrently on one laptop;
- they have stable, different identities;
- restarting either Agent preserves its identity;
- Core and Agent contract tests use the same schemas;
- no Raspberry-specific import is required on the laptop.

## Milestone 2 — Secure pairing and device registry

Goal: replace the hardcoded Raspberry list with real devices.

Deliverables:

- Device, credential, pairing and heartbeat database models;
- single-use, expiring pairing codes;
- pending-device approval UI;
- device-specific credentials and revocation;
- inventory and heartbeat submission;
- online/offline calculation;
- removal of mock devices from Main Server UI.

Acceptance criteria:

- an unknown Agent cannot register silently;
- approved Agents appear with real inventory;
- revoked Agents cannot reconnect;
- status changes to offline after the configured heartbeat window;
- pairing and revocation are present in the audit log.

## Milestone 3 — Desired state and reliable commands

Goal: make Core-to-Agent operations explicit, observable and resilient.

Deliverables:

- desired and reported state revisions;
- bidirectional live transport plus reconnect fallback;
- command queue and structured results;
- message acknowledgements, expiry and idempotency;
- offline event/log buffer on Agent;
- UI for command lifecycle and device history.

Acceptance criteria:

- Core distinguishes queued, delivered and successfully executed commands;
- duplicate delivery does not duplicate an idempotent action;
- expired commands are rejected;
- Agent reconnects after simulated network loss;
- desired/reported differences are visible and reconciled.

## Milestone 4 — Module manifest v2 and runtime lifecycle

Goal: provide one consistent module model across Core, Agent and UI.

Deliverables:

- manifest v2 JSON schema;
- module package validator;
- Core catalog and per-device installation records;
- Agent staging, activation, health check and rollback;
- capability registry;
- permission declarations and runtime enforcement foundation;
- compatibility checks for architecture and protocol version.

Acceptance criteria:

- incompatible packages are rejected before transfer;
- a valid module installs transactionally;
- failed health check restores the prior version;
- disabling does not delete user data;
- Core navigation and services are derived from registrations, not module names.

## Milestone 5 — Mock GPIO vertical slice

Goal: prove a complete useful module without Raspberry hardware.

Deliverables:

- digital input/output capability interfaces;
- deterministic mock GPIO driver;
- Agent GPIO module;
- Core configuration UI generated from schema;
- input events and output commands;
- local offline automation example;
- protocol and integration tests.

Acceptance criteria:

- browser configuration changes a mock output on one selected Agent;
- simulated input produces a timestamped Core event;
- a local input-to-output rule continues while Core is stopped;
- reconnect does not duplicate already acknowledged events.

## Milestone 6 — AI configuration and automation

Goal: let users describe behavior in natural language using existing trusted capabilities.

Deliverables:

- capability-aware AI context builder;
- declarative automation schema;
- plan, validation and diff workflow;
- explicit approval before apply;
- simulator/dry run;
- audit record linking intent, proposal and applied revision.

Acceptance criteria:

- AI can compose the mock GPIO scenario without generating Python;
- impossible hardware requests are rejected or clarified;
- invalid AI output cannot be applied;
- user can inspect exactly which devices and settings will change;
- rollback restores the previous configuration revision.

## Milestone 7 — Real Raspberry Pi validation

Goal: replace mock hardware with real Raspberry adapters while preserving contracts.

Deliverables:

- Raspberry Pi OS installation path;
- systemd Agent service;
- gpiozero/libgpiod driver decision and implementation;
- Pi Zero 2 W and Pi 3B resource measurements where available;
- reconnect, reboot, storage-limit and power-loss tests;
- first-boot/pairing documentation.

Acceptance criteria:

- the same GPIO module passes against mock and real drivers;
- Agent automatically reconnects after reboot;
- local automation operates while Core is unavailable;
- CPU, memory and storage remain within documented limits;
- clean device installation can be repeated from the guide.

## Milestone 8 — Safe AI module builder

Goal: evolve the existing AI Extension Builder into a controlled module development pipeline.

Deliverables:

- isolated build workspace;
- manifest-first generation;
- generated tests and validation gates;
- dependency allowlist and license metadata;
- artifact signing and immutable versions;
- human review diff;
- isolated runtime for generated backend code.

Acceptance criteria:

- generated code never executes inside the Core API process before approval;
- failed checks prevent packaging and installation;
- requested permissions are visible and explainable;
- installed artifact corresponds exactly to the reviewed hash;
- removal and rollback are verified.

## Milestone 9 — Production operations

Goal: make small real installations supportable.

Deliverables:

- backup and verified restore;
- Core migration from Raspberry Pi to PC;
- TLS and secure remote access guidance;
- fleet update rings and maintenance windows;
- retention and storage management;
- diagnostics bundle with secret redaction;
- release compatibility matrix.

Acceptance criteria:

- Core can be restored onto a different host without re-pairing all Agents, subject to preserved keys;
- failed staged update does not affect the whole fleet;
- diagnostics are useful and contain no secrets;
- storage cannot grow without configured bounds;
- release and rollback procedures are repeatable.

## Milestone 10 — Ecosystem expansion

Goal: expand capabilities without weakening Core architecture.

Candidate modules:

- media player and kiosk;
- UDP, MQTT and Modbus;
- RFID/NFC;
- cameras and streaming;
- audio and lighting;
- Home Assistant bridge;
- museum installation bundle based on ShowController lessons;
- child-center device integrations where appropriate;
- signed private module repositories.

Candidate selection criteria:

- real user need;
- reusable capability rather than one-off special case;
- clear permissions and failure behavior;
- laptop-testable logic;
- hardware availability for final acceptance.

## Immediate work queue

These are the first concrete tasks after approval of this plan:

1. Record the current backend and frontend startup failures from a clean environment.
2. Replace committed active PostgreSQL credentials with portable development defaults.
3. Add typed configuration and `.env.example`.
4. Make SQLite the verified default development database.
5. Add one development launcher for backend and frontend.
6. Establish backend and frontend quality gates.
7. Document which existing tests are trustworthy.
8. Design the shared protocol package and first `agent.hello` schema.
9. Create a minimal Agent with persistent local identity.
10. Start two mock Agents on the laptop.

## Explicitly deferred

The following work does not begin before the relevant foundations are accepted:

- real GPIO access before the mock vertical slice;
- public marketplace downloads;
- arbitrary AI-generated Python execution;
- automatic root/system-package operations;
- Docker/Kubernetes fleet architecture;
- large-scale telemetry storage;
- visual redesign unrelated to the first device workflow.

