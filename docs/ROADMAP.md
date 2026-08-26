# 3mm Roadmap

Status: active; Milestones 0–9 completed, Milestone 10 in progress
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

Status: completed and Raspberry-validated on 2026-08-14. See [MILESTONE_6_REPORT.md](MILESTONE_6_REPORT.md).

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
- free-provider routing with OpenRouter-to-Groq fallback;
- device-reported deployment status and revision-based enable/disable controls;
- guarantee that billing state cannot disable deployed local behavior.

Acceptance criteria:

- AI can compose the mock GPIO scenario without generating Python;
- impossible hardware requests are rejected or clarified;
- invalid AI output cannot be applied;
- user can inspect exactly which devices and settings will change;
- rollback restores the previous configuration revision;
- enable/disable survives Agent restart and changes local trigger behavior;
- failed Agent commands are shown as failed rather than merely applied;
- every paid job has an approved maximum and recorded actual usage;
- an exhausted AI balance blocks only new paid AI work;
- reusing an unchanged artifact does not generate it again.

## Milestone 7 — AI-generated runtime extensions

Goal: make the AI Extension Builder publish useful extensions that become available immediately, without rebuilding the Core frontend or executing arbitrary generated code.

Status: completed on 2026-08-17; compiled source execution remains explicitly separated into Milestone 8. See [MILESTONE_7_REPORT.md](MILESTONE_7_REPORT.md).

Deliverables:

- versioned `runtime-extension v1` declarative contract;
- strict validation with deny-by-default fields and actions;
- generic Core storage and CRUD boundary for runtime entities;
- precompiled Vue renderer for runtime pages, tables, forms and navigation;
- one hand-written reference CRUD extension proving install-to-use behavior;
- AI generation constrained to the runtime contract;
- draft persistence, validation report and preview in Extension Builder;
- transactional publish, activation and rollback;
- explicit separation between immediately runnable `runtime` extensions and externally built `compiled` extensions.

Acceptance criteria:

- a new runtime extension is installed and opened without rebuilding or restarting the frontend;
- routes and navigation are derived from the validated package rather than a concrete extension name;
- invalid fields, undeclared actions and executable frontend/backend content are rejected;
- a hand-written CRUD reference extension can create, list, edit and delete records;
- AI can generate the same valid reference capability from a natural-language request;
- the user previews the manifest, pages, permissions and validation report before publish;
- failed activation restores the prior version and leaves no partially enabled extension;
- installed runtime behavior continues without AI availability or provider credit.

## Milestone 8 — Compiled Extension Runtime

Goal: install reviewed Vue extension source as immutable browser-ready artifacts without rebuilding the complete Core frontend or running a Vite development server.

Status: completed for reviewed, trusted Vue packages on 2026-08-21. See [MILESTONE_8_REPORT.md](MILESTONE_8_REPORT.md).

Deliverables:

- versioned `compiled-ui v1` contract shared by Core, builder and frontend;
- generic UI entrypoints for widgets, routes, editors and reusable components;
- strict source-package validation and immutable package hashes;
- isolated, offline install-time Vue compiler with CPU, memory and time limits;
- stable Extension Host SDK instead of imports from arbitrary Core internals;
- hashed JavaScript and CSS artifacts stored outside immutable application releases;
- generic runtime asset loader and dynamic route/widget/editor registration;
- transactional activation, version rollback and artifact cleanup;
- explicit administrative review for executable UI packages;
- reference Digital Clock widget and page-extension acceptance packages.

Acceptance criteria:

- the reference Clock `.vue` source compiles during installation on Raspberry Pi;
- the installed Clock appears in Display Editor and updates once per second;
- a compiled route extension opens without rebuilding or restarting the main frontend;
- widget editors use the same compiled artifact pipeline;
- invalid imports, missing entrypoints and compiler failures prevent activation;
- the browser loads only the reviewed immutable artifact hash;
- disabling and rollback do not delete extension data;
- compilation cannot write into `/opt/3mm/current` or access the network;
- Core contains no concrete extension or widget names.

Stages:

1. shared contract, validator and Clock source fixture;
2. isolated install-time compiler and immutable artifact store;
3. generic browser loader for widget, route, editor and component entrypoints;
4. Raspberry acceptance, security limits, rollback and Builder integration.

## Milestone 9 — Capability-based AI Extension Builder

Goal: make AI-generated widgets and extensions reliable by combining structured AI planning with tested platform capabilities and deterministic code generation.

Status: completed and accepted on physical `rasp-3mm` hardware on 2026-08-23. See [MILESTONE_9_REPORT.md](MILESTONE_9_REPORT.md).

Deliverables:

- plain-language intent translated into a versioned, reviewable capability plan;
- reusable builder capabilities for live timers, configurable forms, HTTP/API data, persistent key-value settings, CRUD records, lists/tables and charts/metrics;
- deterministic generation of lifecycle, configuration schema, editor, permissions, packaging and runtime integration;
- AI customization limited to capability selection, presentation and genuinely extension-specific behavior;
- incremental repair of existing projects and files instead of regeneration from zero;
- automatic source validation, compilation and bounded runtime smoke tests before Install is enabled;
- clear separation between provider failure, generation failure, compilation failure and installation failure;
- capability-aware version increments and reuse of already validated artifacts;
- GPIO Input capability spanning Agent, Core and compiled widget runtime;
- generated GPIO status widget with editor fields for device, input pin, active-high/active-low behavior, labels, colors and refresh/event mode;
- permission and ownership checks that prevent a widget from reading undeclared devices or pins.

GPIO acceptance flow:

`Digital input driver → Agent GPIO capability → authenticated Core state/event API → compiled dashboard widget`

Acceptance criteria:

- a non-technical user can describe a widget without entering routes, versions, schemas or source filenames;
- a weak/free AI provider can select and configure existing capabilities without generating the trusted runtime foundation;
- generated code cannot replace or weaken capability security and lifecycle boundaries;
- invalid or incomplete AI output cannot be presented as an installable build;
- a failed build can be repaired from the existing project without re-entering its complete description;
- Install is enabled only for the exact artifact that passed validation and compilation;
- on the mock driver, changing a selected input pin changes the dashboard lamp between red and green;
- on `rasp-3mm`, the same widget reads a declared physical input pin through the Agent without browser, Core or generated code accessing GPIO directly;
- changing pin or active-high/active-low in the widget editor persists and takes effect without regenerating the extension;
- disconnecting Core shows a stale/offline state rather than a false red or green value;
- Core and the generic frontend contain no concrete GPIO widget or generated extension name.

Stages (completed on 2026-08-23):

1. capability-plan contract, project migration and deterministic generator foundation;
2. common UI/data building blocks and incremental repair workflow;
3. GPIO Input capability across Agent, Core and widget editor/runtime;
4. compile/runtime validation, physical Raspberry acceptance and Builder UX cleanup.

## Milestone 10 — Real Raspberry Pi validation

Goal: replace mock hardware with real Raspberry adapters while preserving contracts.

Status: in progress on the physical `rasp-3mm` Raspberry Pi 3B+ baseline. The
native `libgpiod` input path, systemd deployment, reboot and reconnect behavior
bounded release retention and automatic failed-deployment rollback are
accepted; deployment-backup retention and the read-only first-boot preflight are
also accepted, while clean-media installation acceptance remains. See
[MILESTONE_10_REPORT.md](MILESTONE_10_REPORT.md).

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

## Milestone 11 — Safe compiled AI module builder

Goal: evolve the existing AI Extension Builder into a controlled module development pipeline.

Boundary: Milestone 9 covers trusted capability composition and deterministic
generation. This milestone covers genuinely new executable frontend/backend
code that cannot be expressed through registered capabilities.

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

## Milestone 12 — Production operations

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

OTA update stages (see [OTA_UPDATE_PLAN.md](OTA_UPDATE_PLAN.md)):

1. administrator-only, read-only release catalog and dependency preview — completed locally on 2026-08-26;
2. reproducible, architecture-specific GitHub Release artifacts and strict manifest generation — `v0.1.0` published;
3. verified staging, allowlisted dependency installation, explicit approval and automatic rollback — `v0.2.1` rollback verified; corrected `v0.2.2` manually deployed as the trusted base; `v0.2.3` OTA acceptance pending;
4. update channels, maintenance windows and fleet rollout controls.

## Milestone 13 — Ecosystem expansion

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
- [x] Define and test the strict `runtime-extension v1` declarative contract.
- [x] Add generic Core storage and a versioned, contract-validated runtime CRUD API.
- [x] Implement the generic runtime page renderer and route registration.
- [x] Add a hand-written Contacts CRUD runtime package and transactional catalog activation.
- [x] Define the shared `compiled-ui v1` source and entrypoint contract.
- [x] Add strict compiled-source package validation and a reference Clock fixture.
- [x] Build the install-time Vue compiler and immutable artifact store; production sandbox enforcement remains in Milestone 8 Stage 4.
- [x] Add the generic browser loader and connect compiled widgets, routes, editors and components without rebuilding Core frontend.
- [x] Prove the compiled Clock artifact in Display Editor on Raspberry Pi.
- [x] Prove Contacts install-to-use behavior in the browser on Raspberry Pi.
- [x] Constrain AI Extension Builder generation to reviewed runtime and compiled capability contracts.
- [x] Validate the native `libgpiod` input capability and generated GPIO widget on physical `rasp-3mm`.
- [x] Stabilize incremental AI file responses, one-click build/install and version-aware widget rollback.
- [x] Verify Agent/Core/Web recovery and persistent identity across a controlled Raspberry Pi reboot.
- [x] Verify Agent buffering and automatic reconciliation across a controlled Core outage.
- [x] Record storage bounds and apply protected release retention on `rasp-3mm`.
- [x] Verify interrupted-deployment recovery and automatic rollback.
- [x] Bound deployment backup history while preserving matching recovery points.
- [x] Add and physically run the read-only first-boot host/release preflight.
- [x] Document the current clean Standalone install, admin bootstrap and local pairing flow.
- [x] Add an admin-only, read-only GitHub Release catalog with strict manifest validation and dependency preview.
- [x] Add deterministic multi-architecture release packaging, manifest generation and a draft-first tag workflow.
- [x] Publish the first reproducible architecture-specific release and generated update manifest (`v0.1.0`).
- [x] Add verified staging and an explicitly approved, allowlisted dependency plan without giving the Web service unrestricted root access.
- [x] Add a narrow root helper that independently revalidates the official manifest before package or installer mutation.
- [ ] Reuse immutable activation, health checks and rollback for the first manually applied OTA update.
- [ ] Repeat the documented Standalone flow on clean media and close the Milestone 10 report.
- [ ] Validate the open setup-only access point and persistent NetworkManager profile across a Raspberry Pi reboot.
- [ ] Validate automatic transition from setup services to the selected runtime role on physical `rasp-3mm`.

## Explicitly deferred

The following work does not begin before the relevant foundations are accepted:

- real GPIO access before the mock vertical slice;
- public marketplace downloads;
- arbitrary AI-generated Python execution;
- automatic root/system-package operations;
- Docker/Kubernetes fleet architecture;
- large-scale telemetry storage;
- visual redesign unrelated to the first device workflow.
