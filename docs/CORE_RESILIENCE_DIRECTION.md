# Core resilience and independent component development

Updated: 2026-10-23. Owner-confirmed prototype assumptions and architecture
reference. The single execution sequence, including unified debugging, is the
[consolidated action plan](CORE_STABILIZATION_ACTION_PLAN.md). No runtime redesign,
deployment or M21 takeover is performed by writing these documents.

## Operating assumptions

- 3mm is an unreleased prototype without production users. Target manifest v2;
  legacy installed extensions, manifests and SDK/API compatibility need not be
  preserved. Update current consumers together and remove replaced paths.
- Manifest, SDK, device transport and descriptor versions are independent. A
  descriptor named v1 is not obsolete merely because manifests use v2.
- Preserve the owner's source work. Reset/reinstall can be part of an explicit
  implementation package; prototype status is not an immediate wipe request.
- Develop from the laptop repository. Run Linux integration against isolated
  code/data in WSL Ubuntu; preserve the dirty M21 tree at `/opt/3mm-dev`.
  Raspberry devices cover real ARM/ARMv6, hardware and resource acceptance.

## Observed coupling in the current code

- P3b removes the legacy in-Core Python extension loader, manager, lifecycle
  endpoints and direct frontend consumers. Current compiled/declarative/application
  contracts remain. Languages use generic data-only manifest-v2 packages; Bulgarian
  is an extension too, with English as the built-in recovery base.
- P3c gives Core/SDK one current signed discovery/framing contract with bounded
  connections, absolute transport deadlines, reason codes and generation metadata.
  Discovery is not a grant; current Core admission/revocation remains mandatory.
  Compatibility-only scheduled jobs are retired, not moved into Runtime. See the
  [current transport contract](EXTENSION_PLATFORM_V2_PUBLIC_CONTRACTS.md).
- P3a introduced one lifecycle for optional listeners/services. Current Core
  manages the private authority and optional services through it. Startup failures degrade those features while administration
  stays available; the Core database remains required. Admin diagnostics expose
  component state. P4a/P4b now extract all 25 signed SDK transports to a separate
  Runtime process/artifact/environment and private UID-authenticated Core gate.
  The old public SDK listener is removed. Boot passes the original socket FD with
  SCM_RIGHTS, preserving kernel SO_PEERCRED. Current authority/domain adapters
  remain in Core. P4d1 moves public response waiting and the
  public socket to Runtime: Core admits/sends once and checks the signed result
  after a connected-FD handoff, without waiting for the extension handler. P4d2
  similarly moves durable event response I/O to Runtime: Core keeps matching,
  current grants, journaled attempt ownership and signed completion accounting.
  Core has no event executor loop. The boot-clock lease survives component loss;
  fresh retries recheck current authority and keep the original event ID.
- P4c gives application hosts native immutable code/vendor/venv releases outside
  Core, with separate per-instance current/previous pins. Compatible host updates
  restart only that application and preserve Core/Runtime/other-host processes.
  Existing provider wheels remain independent. Host units have no Core PartOf
  dependency; shared application UID remains reviewed-native, not hostile isolation.
- P4 completion gives Agent, public HTTP and session workers their own native
  code/vendor/venv artifacts, pins and update/recovery journals. Compatible updates
  leave Core and its release pointer untouched. Agent keeps trusted account `3mm`
  and receives a filtered own environment; hostile-code Agent isolation is not claimed.
- P4d3 removes connector HTTP execution from Core into a distinct outbound-network
  worker. Core sends one admitted plan after durable attempt commit, then hands
  Runtime the connected FD. Result HMAC/CAS bookkeeping is separate and cannot
  resend an effect. Four disposable children bound DNS/TLS/read/trickle work;
  Runtime remains network-isolated. The shared small executable has independently
  pinned process roles, services, environments and update journals. Agent/public/
  session delivery boundaries are completed locally; installed hardware gates remain.
- P4d4 moves admin operational-status response reading to an eight-slot,
  response-only FD relay in Runtime. Core HTTP waits asynchronously with no held
  Core thread/DB transaction. It reserves before sending, verifies the original
  signed reply and current application snapshot locally, and returns explicit
  unknown telemetry when Runtime is absent or the result is stale. The channel
  has no keys, dispatch data or authority.
- P4d5 uses the same relay for declared admin health, keeping Core package/native
  UI trust, original HMAC/schema validation and current lifecycle admission. An
  atomic completion fence prevents stale `health_checked_at` writes. Health gets
  no relational SQL ticket or host-metadata IPC; the prepared host can answer
  readiness after resource revoke without acquiring SQL rights. P4d6/P4d7 reuse
  the relay for human/kiosk operations and peer callbacks, with current policy
  before send and disclosure. Late refusal is unconfirmed without replay. Relational
  metadata remains Core admission, under one absolute two-second IPC deadline.
- `deployment/install-systemd.sh` stops the runtime service group and replaces
  the common release pointer. `release.yml` runs full Python/frontend/deployment
  checks and builds full/Node artifacts before publishing. P4a adds a separate
  Runtime update helper and immutable current/previous pointers outside that
  shared release. A compatible Runtime update stops only its own service and
  verifies Core process/release continuity. P4c adds a separate host helper/pins;
  the full coordinated platform installer still stops its runtime service group.

P4's agreed extraction and independent-delivery scope is complete locally. Shared
transactions, native targets/contracts, active-component checks and the release
lock preserve operator stop and Core process/source continuity. Recovery clears
only the selected role's failure counters. Core is favored under global OOM (-500
versus +300 for optional workers), with finite per-service resource/restart budgets.
Actual session DynamicUser/network/filesystem restrictions passed with uniquely
owned systemd units. Installed/device/resource/reboot/power acceptance remains P6.

Core still owns authority/domain/control-plane adapters and outbound peer HTTPS.
Existing M21 broker/stream ownership is unchanged. Independent worker packaging
is not a claim that all streaming traffic has moved out of Core.

## Setup, device role and optional networking

Setup/recovery is a platform bootstrap boundary, independent of optional Runtime
and providers. Define it before extracting services so a clean installation and
recovery do not acquire a dependency on the component being repaired.

Historical setup coupling observed before P2:

- `setup_service/static/setup.html` and `SetupConfiguration` already offer the
  three roles. The minimal Node package intentionally removes Hub/Standalone
  choices; API validation also refuses roles whose components are not installed.
- Both HTTP configuration and `ProvisioningRequest` require Wi-Fi credentials;
  `ProvisioningStateMachine` always stages and verifies a network change.
- `3mm-setup.service` requires AP/network-helper units; the AP and activation
  adapter assume `wlan0`. Setup units conflict with Core/Web/Agent. A recovery
  marker currently selects only setup services and activation stops the others.
- `install_bootstrap.prepare` has a special full-install path without Wi-Fi:
  it initializes an absent journal as Standalone after finding a Core admin and
  disables automatic AP recovery by default. This is not a role-selecting wired
  setup flow; a fresh minimal Node without Wi-Fi is refused by this path.
- Existing recovery monitoring already uses local Ethernet/Wi-Fi link state,
  without Internet probes. Preserve this distinction when extending setup.

P2a/P2b now implement explicit roles, host-managed or selected Wi-Fi, protected
LAN setup and journaled recovery locally; the bullets above explain the original
coupling, not the current implementation. The real Raspberry Wi-Fi/AP acceptance
is explicitly deferred by the owner. See the action plan for current evidence.

The target has independent inputs:

| Input | Meaning |
| --- | --- |
| Device role | Standalone, Hub or Node: the intended behavior and required components |
| Installed components | Full/minimal installation and actual supported capabilities; a missing Core cannot be enabled by a role label |
| Network choice/ownership | Keep OS configuration, configure a selected supported adapter, or local-only operation where applicable |
| Bootstrap/recovery state | First boot, normal use or an explicitly enabled recovery session; not another device role |

Roles must be explicit regardless of Wi-Fi availability:

| Role | Intended operation | Setup requirements |
| --- | --- | --- |
| Standalone | Local management and local Agent/workloads | Device identity, local administrator; can operate locally without external connectivity |
| Hub | Manage devices and its own local Agent | Local administrator and intended management address; no dependency on Internet for local operation |
| Node | Device Agent/providers managed by a Hub | Device identity, Hub address/discovery and explicit enrollment; show pending pairing until actually accepted |

Hardware type must not choose the network policy. A Raspberry can use Ethernet;
a Linux PC can use Wi-Fi. Detect real interfaces and AP support, including a
disabled radio and several adapters; never infer `wlan0` or AP support from a
board name. Expose only available actions, with a clear reason for unavailable
ones. Keep role selection separate from the installation profile restriction.

Proposed setup flow:

1. Discover available components, network adapters and existing connectivity.
   Reach setup through an existing LAN address, localhost/console, or an explicitly
   needed supported setup AP. LAN bootstrap endpoints need a bounded bootstrap or
   recovery authorization context; discovery is not permission to reconfigure.
2. Choose role, with a short explanation and any missing-component requirement.
3. Choose **keep existing network**, **configure Wi-Fi**, or **local-only** where
   the role permits it. Existing Ethernet/preconfigured Wi-Fi needs no SSID or
   password submission. OS-managed networking needs no NetworkManager dependency;
   do not replace or take over the host's network manager.
4. Set device name, locale/timezone and the actual administrator for Core-bearing
   roles, or Hub/enrollment details for Node. A display-name field must not imply
   that an administrator account was created. Save incomplete enrollment honestly
   as pending; do not report a connected Node before successful acceptance.
5. Preview the selected role, connection, management address and affected services,
   then apply through the narrow privileged helper. Preserve identity and role
   when only changing a network. Apply role changes through a separate component
   activation plan with explicit validation and rollback.

Network recovery must not reinterpret a lost link or unreachable Hub as loss of
the device role. Keep healthy local Core/Agent workloads running and expose a
separate recovery status. A setup AP is optional and policy-controlled. Switching
a single radio from client to AP may interrupt that radio's link; handle this
explicitly without requiring the local services themselves to stop.

Use staged network changes, a bounded confirmation window and automatic rollback
where the network backend supports it; NetworkManager has checkpoint/timeout
rollback primitives. Validate local addressing and intended management/Hub
reachability separately from Internet access. Preserve a known recovery route
and report progress after the browser's connection changes. Credential storage
remains owned by the selected OS network backend.

Acceptance must cover Ethernet-only/WSL hosts without Wi-Fi or NetworkManager,
Wi-Fi present but unused, the current Raspberry AP path, non-`wlan0`/multiple
adapters, LAN without Internet, role selection on each supported install profile,
pending Node enrollment, failed network apply with recovery, and interrupted
setup/reboot. Prove that link loss/recovery does not unnecessarily stop Core or
Agent and that Runtime being absent does not prevent setup. These are planned
checks for implementation, not claimed passing results from this design review.

## Proposed component boundaries

| Component | Responsibility | Failure/update boundary |
| --- | --- | --- |
| Core | Identity, current authority, device/provider registry, configuration/desired state, bounded management API, audit metadata | Boots and serves administration with optional runtimes absent |
| Platform Runtime | SDK transport, supported adapters/event execution and session/stream routing; retired compatibility jobs stay removed | Separate process, dependencies, mutable state and update artifact; all signed SDK transport implemented in P4a/P4b |
| Application/provider workers | Extension code, business logic and provider implementations | Separate worker identities/resources; one failure cannot take down Core or another worker |
| Agent | Device identity/connection, local workload execution and hardware capability providers | Continues its defined safe local behavior during Core/Runtime outage |
| Setup/recovery | First boot, role/component selection, optional network configuration and recovery access | Starts without Core/Runtime or a Wi-Fi adapter; AP is a conditional adapter |
| Recovery/update helper | Narrow privileged update/recovery operations | Reachable locally even when Core cannot start; reuses existing recovery mechanisms |
| Shared diagnostics | Bounded structured events, correlation and optional diagnostic sessions/export | Local evidence survives one unavailable component; collection never gates Core work |

Keep the monorepo. Use one generic Runtime service initially, with isolated
workers and a separate session/stream listener. Add another service only for a
demonstrated failure/resource boundary; no distributed message-bus project is
needed for the first result. A lightweight Node does not need the full Runtime.

Core remains the authority owner; Runtime/providers do not get its database or
private signing keys. Use bounded, versioned IPC locally and the authenticated
device transport remotely. Providers declare capabilities/contracts, so adding
terminal, serial, log or echo implementations does not add special Core branches.
Moving broker/stream transport requires its own current-authority and lifecycle
design; P4 preserves the existing M21 broker while separating the worker artifact.

Authorization is a real contract, not a token passed unchecked across the new
boundary. New privileged effects require current admission. Core unavailability
must not silently grant new rights. Specify revocation, bounded session leases,
disconnect cleanup and recovery generations explicitly before moving a broker;
do not claim instantaneous revocation from an unbounded cache. Existing local
workloads follow a declared offline/safe-state policy without blindly replaying
commands on reconnect.

## Survive failures and recover predictably

- No extension/provider Python imports in the Core process on the target path.
  P3b retires the legacy loader and replaced endpoints together. P3c implements
  the current Core-Runtime transport contract. P4a proves the independent
  process, principal and update boundary locally; P4b completes signed SDK
  routing with original boot peers. Adapter execution and independent provider/
  application-host artifacts have P4c independence. P4d completes the selected
  handler-response/connector execution and Agent/public/session delivery boundaries.
- Core readiness tests its own essential state; Runtime/provider unavailability
  is a visible degraded feature state, not a reason to fail Core readiness.
- Bound IPC size, work queues, concurrency, logs and operation deadlines. Reject
  overload; do not allow a slow worker to monopolize Core threads/DB transactions.
- Give workers independent memory/CPU/task/file-descriptor budgets and restart
  backoff; quarantine a repeatedly failing provider. Check installed systemd and
  cgroup support on each target before selecting exact limits.
- Add liveness-aware watchdog/restart supervision where appropriate. A watchdog
  must observe actual service progress, not a thread that pings while work is hung.
  Keep restart loops bounded and preserve operator stop/recovery semantics.
- Keep Core's durable state private and transactional. Separate application data
  and execution journals; supervise disk/log use and expose a usable recovery path
  when essential storage is unavailable. A restart is not a database repair.
- Each independently delivered component needs its own immutable artifact,
  dependency environment, active pointer, health check and rollback boundary.
  Pin a tested component set and reject an unsupported protocol combination.

The goal is fault containment and measured recovery, not literal immortality.
Power, kernel or storage failure can stop one machine; uninterrupted operation
across those faults would require an additional hardware/availability design.

## Shorter development loop

1. Develop and test a provider against a fixed Core/Runtime contract in the Linux
   development environment. No version bump or published release per experiment.
2. Install a local development artifact into the isolated test deployment. Existing
   `deploy.ps1 -IncludeWorkingTree` shows a reviewed local-snapshot path already
   exists; it still deploys the common release and is not component independence.
3. Run affected provider/SDK checks, boundary denial/revocation checks and a small
   Core-survival smoke test. Run ARM/ARMv6 trials only where platform behavior is
   relevant; preserve previous evidence for unchanged artifacts/environments.
4. Publish only when a coherent result is ready. A provider-only update within a
   fixed contract should replace only that provider. A Runtime update should
   leave the exact Core artifact and process untouched.
5. Full platform checks remain for shared-contract changes and coherent platform
   releases. Component releases select their affected contracts and failure
   boundaries; independent packaging must come before claiming cheaper releases.

This requires changes to packaging/deployment and CI ownership as well as code.
Do not promise a fixed time or credit saving before measuring the new loop.

## Local diagnostic/dev workflow (P5)

P5 is implemented locally: the existing Settings diagnostics surface now includes
bounded component observations, scoped TTL sessions and a shared Core/producer
snapshot timeline. Recording is inactive at startup and does not grant execution.
Core/SDK operation records remain fixed metadata; imports identify missing/dropped/
truncated evidence and clock limits. Collection is explicit pull/import with bounded,
non-queued work, not an automatic fleet recorder. An offline protocol command works
without Core/SQLAlchemy. The developer CLI uses current protected APIs and exact
archive hashes; no Core release is needed for compatible package iterations.

Two existing neutral packages passed local independent host install/update/rollback
and failure checks with fixed Core/Runtime processes. Reference compatibility fixtures
and scoped SDK revoke checks have distinct stated scopes. [Commands and limits](DIAGNOSTICS.md)
and exact evidence in WORKING_STATE.md do not replace P6 installed/hardware acceptance.

## Execution and architecture acceptance

Use packages P0–P6 in the [action plan](CORE_STABILIZATION_ACTION_PLAN.md): bounded
audit/dev environment, diagnostic foundation, boot/setup, Core/SDK cleanup,
Runtime/component packaging, complete debug/development workflow, then acceptance.
The thin diagnostic foundation precedes service extraction so the changes can be
observed. Setup still precedes changing ownership of the runtime services.
Do not maintain a second implementation queue in this reference document.

Acceptance for the resulting boundaries:

- Core starts and remains administrable with Runtime absent, killed or hung.
- Setup works without Core/Runtime, role selection does not require Wi-Fi, and
  recovery preserves the role/identity and healthy local workloads.
- A crashing/flooding/over-budget provider affects only its bounded feature.
- Worker and Runtime updates/restarts leave the unchanged Core process/artifact
  intact; a second provider needs no Core change.
- Authority denial/revocation, disconnect cleanup and no-replay behavior pass at
  the new process boundary. An outage does not restore expired/revoked rights.
- Shared traces and bounded diagnostics work across the process boundaries;
  collector failure, buffer exhaustion and debug expiry cannot stop Core work.
- Agent offline/safe-state behavior, component health/rollback and actual ARMv6
  resource limits are measured in the appropriate isolated and hardware tests.

## References

- Existing source: `backend/main.py`, `backend/utils/extension_manager.py`,
  `backend/services/application_platform.py`, `deployment/systemd/`,
  `deployment/install-systemd.sh`, `.github/workflows/release.yml`,
  `setup_service/{main,schemas}.py`, `setup_service/static/setup.html`,
  `three_mm_provisioning/{models,state_machine}.py`,
  `three_mm_runtime/{services,activate,install_bootstrap,network_recovery}.py`.
- Existing diagnostics: [scope](DIAGNOSTICS.md), `backend/services/diagnostics.py`,
  `backend/routes/diagnostics.py`, `frontend/src/components/settings/DiagnosticsSection.vue`.
- [NetworkManager checkpoint rollback](https://networkmanager.dev/docs/api/latest/gdbus-org.freedesktop.NetworkManager.html#gdbus-org.freedesktop.NetworkManager.CheckpointCreate).
- [systemd watchdog and restart semantics](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html).
- [systemd resource controls](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html).
- [OpenAI: work stays on the selected development host](https://developers.openai.com/blog/mastering-codex-remote-for-engineering).
