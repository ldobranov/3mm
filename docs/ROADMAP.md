# 3mm Roadmap

Status: active; Milestones 0–5 completed on 2026-08-09
Planning style: sequential milestones with a runnable result after every milestone

Dates are intentionally not assigned until the current baseline is reproducible. Progress is measured by acceptance criteria, not optimistic calendar estimates.

## Milestone 0 — Reproducible baseline

Status: completed on 2026-08-09. See [MILESTONE_0_REPORT.md](MILESTONE_0_REPORT.md).

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

Status: in progress; first Raspberry Pi 3B+ baseline captured on 2026-08-09. See [RASPBERRY_PI_BASELINE.md](RASPBERRY_PI_BASELINE.md).

Goal: introduce a real Agent, shared contracts and the universal device-role foundation.

Deliverables:

- `core`, `agent` and shared protocol package boundaries;
- versioned protocol schemas;
- stable Agent identity and isolated local data directory;
- mock hardware driver interface;
- Agent CLI and health endpoint;
- laptop launcher for two or more mock Agents;
- lifecycle-managed Core background services;
- common service layout for Core, Agent and setup;
- Standalone, Hub and Node role model without separate images;
- provisioning state machine with a mock network adapter;
- first headless captive-portal prototype;
- Raspberry Pi inventory report and resource baseline.

Acceptance criteria:

- two Agents run concurrently on one laptop;
- they have stable, different identities;
- restarting either Agent preserves its identity;
- Core and Agent contract tests use the same schemas;
- no Raspberry-specific import is required on the laptop;
- a Hub runs its own Agent and exposes local capabilities;
- Standalone can later accept Nodes without reinstallation;
- failed first-boot network configuration returns to setup mode.

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

Status: completed and accepted on the physical `rasp-3mm` baseline on 2026-08-09.

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

Status: completed and accepted on the physical `rasp-3mm` baseline on 2026-08-09.

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

Status: completed and accepted on the physical `rasp-3mm` baseline on 2026-08-09. See [MILESTONE_5_REPORT.md](MILESTONE_5_REPORT.md).

Deliverables:

- digital input/output capability interfaces;
- deterministic mock GPIO driver;
- Agent GPIO module;
- Core output controls derived from capability registrations;
- input events and output commands;
- local offline automation example;
- protocol and integration tests.

Acceptance criteria:

- browser configuration changes a mock output on one selected Agent;
- simulated input produces a timestamped Core event;
- a local input-to-output rule continues while Core is stopped;
- reconnect does not duplicate already acknowledged events.

## Milestone 6 — AI configuration, usage and automation

Goal: let users describe behavior in natural language using existing trusted capabilities.

Deliverables:

- capability-aware AI context builder;
- declarative automation schema;
- plan, validation and diff workflow;
- explicit approval before apply;
- simulator/dry run;
- audit record linking intent, proposal and applied revision;
- provider-independent AI gateway contract;
- AI job estimate, budget reservation and usage ledger;
- prepaid credit and bring-your-own-key integration boundaries;
- guarantee that billing state cannot disable deployed local behavior.

Acceptance criteria:

- AI can compose the mock GPIO scenario without generating Python;
- impossible hardware requests are rejected or clarified;
- invalid AI output cannot be applied;
- user can inspect exactly which devices and settings will change;
- rollback restores the previous configuration revision;
- every paid job has an approved maximum and recorded actual usage;
- an exhausted AI balance blocks only new paid AI work;
- reusing an unchanged artifact does not generate it again.

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

- [x] Record the current backend and frontend startup failures from a clean environment.
- [x] Replace committed active PostgreSQL credentials with portable development defaults.
- [x] Add typed configuration and `.env.example`.
- [x] Make SQLite the verified default development database.
- [x] Add one development launcher for backend and frontend.
- [x] Establish backend and frontend quality gates.
- [x] Document which existing tests are trustworthy.
- [x] Design the shared protocol package and first `agent.hello` schema.
- [x] Add the minimal standalone Agent and a two-Agent laptop simulation.
- [x] Add the hardware inventory driver contract and deterministic mock profiles.
- [x] Validate the minimal Agent on Raspberry Pi 3B+ without network changes or a systemd unit.
- [x] Add the provisioning state machine and mock network adapter.
- [x] Add the first headless captive-portal prototype.
- [x] Persist secret-free provisioning state and recover interrupted setup after restart.
- [x] Validate a privacy-safe read-only NetworkManager adapter on Raspberry Pi.
- [x] Hand off the provisioned device role to Agent startup without changing identity.
- [x] Measure the Standalone Core plus local Agent footprint on Raspberry Pi 3B+.
- [x] Add a shared device-role service planner for Setup, Core and Agent.
- [x] Add hardened systemd templates with structural listener tests.
- [x] Validate trusted-LAN Core access while keeping Agent loopback-only.
- [x] Build the frontend off-device and validate the static artifact over LAN.
- [x] Install and validate the Standalone Core, Web and Agent systemd services.
- [x] Add a secret-free interactive bootstrap for the first Core administrator.
- [x] Add the Device registry, credential, pairing, inventory and heartbeat schema.
- [x] Add atomic single-use and expiring pairing-code domain services.
- [x] Add versioned pairing-code, claim and explicit approval APIs.
- [x] Issue a unique device credential once after explicit pairing approval.
- [x] Authenticate Agent requests with unique revocable device credentials.
- [x] Accept authenticated heartbeats with strict device identity matching.
- [x] Accept authenticated inventory and expose a real admin device registry API.
- [x] Derive online and offline status from the configured heartbeat window.
- [x] Replace the Main Server mock device list with the real Core registry API.
- [x] Persist the Agent credential locally and publish inventory plus periodic heartbeats to Core.
- [x] Pair and validate the co-located Agent on the physical Standalone Raspberry Pi baseline.
- [x] Add an expiring, idempotent Core command queue with structured results.
- [x] Execute the first allowlisted Agent command and persist its idempotency journal.
- [x] Redeliver unacknowledged commands after reconnect without repeating completed actions.
- [x] Expose command submission, status, results and delivery attempts in the device registry UI.
- [x] Reconcile the first allowlisted desired state revision on the physical Agent.
- [x] Show desired/reported revisions and synchronization status in the device registry UI.
- [x] Persist Agent events during Core downtime and replay them after reconnect.
- [x] Add device diagnostics with inventory, state revisions and command history.
- [x] Validate credential revocation, rejection and controlled replacement without changing device identity.
- [x] Complete the Milestone 3 physical acceptance suite and report.
- [x] Define the strict shared module manifest v2 contract and safe immutable ZIP validator.
- [x] Add the Core module catalog, registration API and per-device installation records.
- [x] Add transactional Agent staging, activation, health checking, rollback and disable.
- [x] Enforce protocol, runtime, architecture, integrity and declared-permission compatibility.
- [x] Derive frontend navigation from generic module registrations rather than module names.
- [x] Complete the Milestone 4 automated and physical acceptance suite and report.
- [x] Add portable digital GPIO interfaces and a deterministic in-memory driver.
- [x] Activate the trusted mock GPIO module from manifest v2 registrations.
- [x] Add capability-driven Core output controls and Agent state persistence.
- [x] Run local GPIO rules while Core is offline and replay timestamped events.
- [x] Verify duplicate event replay remains idempotent on physical `rasp-3mm`.
- [x] Complete the Milestone 5 automated and physical acceptance suite and report.

## Explicitly deferred

The following work does not begin before the relevant foundations are accepted:

- real GPIO access before the mock vertical slice;
- public marketplace downloads;
- arbitrary AI-generated Python execution;
- automatic root/system-package operations;
- Docker/Kubernetes fleet architecture;
- large-scale telemetry storage;
- visual redesign unrelated to the first device workflow.
