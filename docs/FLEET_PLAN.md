# 3mm Fleet — Milestone 13 delivery plan

Updated: 2026-09-30. Status: Node installation and real rollback accepted on Zero;
beta.20 adds release packaging; clean-media AP onboarding remains pending.
Parent milestone: [Hub and Node orchestration](ROADMAP.md#milestone-13--hub-and-node-orchestration).

## Scope

One existing Standalone/Hub manages multiple generic Nodes. A Node runs the
Agent, shared provisioning/network recovery and a lightweight local web UI.
It does not need Core, the business application database, AI Builder or an
application-extension host. No concrete extension names or business rules belong
in Fleet. Promote an existing Standalone without reinstalling or losing data.

Keep one codebase and one bootstrap entry point. A minimal Node installation
profile is packaging/dependency selection, not a separate product or fork.
Do not advertise an installer flag until it is implemented and tested.

## Local-first and optional central management

The vendor's central server is another installation of the same 3mm app, not
a separate Core fork. Client installations retain independent local users,
data, extensions and Hub/Node topology. Local-only mode needs no cloud account,
activation call, telemetry or external request for normal local operation.
Services inherently using external APIs remain dependent on those APIs.

Keep two independent configuration decisions:

1. Which Hub controls this Node?
2. Does this client installation opt into a central 3mm management service?

Cloud enrollment is never a prerequisite for local pairing. The example central
address is `https://3mm.config.bg`; no product hostname is hardcoded. Cloudflare
may publish a running 3mm installation, but is not the device-management protocol.
Discovery, ownership and remote administration require explicit trust/approval.
Registration does not grant unrestricted access to client data or physical actions.
Internet loss does not stop supported local operation. Reconnection must never
replay expired access commands or uncertain payments/physical actions.

### Follow-on milestone — optional central 3mm management

After Milestone 13 local acceptance:

1. Generic installation identity (separate from device and user IDs), outbound
   authenticated enrollment, scoped/revocable delegation and tenant isolation in Core.
2. A separately versioned Fleet Management extension in the central 3mm: customer
   organizations, owned installations, invitations and explicit sharing. Start
   read-only, then add opt-in updates/support. Common ownership grants no implicit
   cross-installation command or data access.
3. A separate subscriptions/entitlements extension: plans and signed grants;
   Core verifies grants locally without knowing concrete paid features by name.
   Define offline validity, expiry, clock handling and revocation limits explicitly.
   Essential local/safety behavior must not depend on an online billing check.

Core/Agent/Setup changes stay in the `3mm` repository. The central management and
commercial extensions should have separate repositories, versions and packages.
Neither extension is part of the Stage 1 installation task.

## Existing foundations verified in the checkout

- `agent/cli.py`, `agent/role.py`: Node role and explicit Core URL.
- `agent/identity.py`, `agent/core_client.py`: persistent identity, credential
  storage, authenticated heartbeat/events and a separate command long-poll loop.
- `backend/routes/device_pairing.py`: issue code, claim, administrator approval,
  completion and credential revocation. Reuse this contract rather than adding
  another enrollment protocol.
- Shared provisioning and network recovery already exist. Local automatic Agent
  pairing is documented for Standalone/Hub; external Node onboarding is unfinished.
- GPIO input/output capability support exists. Identifier configuration currently
  supports only disabled/mock, so a real reader still requires a hardware adapter.
- Release architectures currently are aarch64, armv7l and x86_64. An armv6l device
  must be rejected clearly until its runtime dependencies and artifacts are tested.

## Stage 1 — Minimal installation and service boundary

- Inventory provisioning/runtime/helper dependencies before selecting Node files.
- Add a reviewed Node install profile to the existing immutable deployment path.
  Preserve artifact validation, health checks, rollback and persistent directories.
- Install only the runtime dependencies required by Agent, shared Setup/recovery
  and Node administration; no on-device frontend compilation or Core migrations.
- Keep Agent RPC on loopback. Expose only explicitly supported web endpoints
  through the existing HTTP entry-point design, not the unrestricted Agent API.
- Define role-transition prerequisites: a minimal Node cannot become Hub until
  the full runtime is safely installed. Changing a role flag alone is insufficient.
- Acceptance: isolated clean-root service/dependency tests, failed activation
  rollback and unchanged Standalone/Hub behavior. No live networking changes.

## Stage 2 — Shared Setup and durable pairing

- Reuse the existing setup portal, Wi-Fi scan, captive AP and network rollback.
  Node setup collects name, Wi-Fi and Hub address; discovery is optional assistance,
  with manual address entry always available.
- Wi-Fi provisioning and Hub enrollment are separate durable states. Unreachable
  Hub must not undo working Wi-Fi or silently mark the Node as paired.
- Hub creates a short-lived pairing code; Node claims it; administrator confirms
  the device identity; Node completes enrollment and stores its own credential.
- Bind enrollment to the selected Hub identity. Discovery is not trust; define
  authenticated transport/trust establishment before exposing enrollment secrets.
- Handle expiry, rejection, interruption after approval/completion and reboot
  without duplicate devices or silently consuming/replacing credentials.
- Preserve identity and pairing during network recovery. Explicit device reset,
  Hub revocation and reassignment have separate, documented effects.
- Acceptance: two simulated Nodes, expired/reused codes, wrong Hub, approval
  checks, interrupted completion, revocation and reconnect.

## Stage 3 — Hub Fleet screen

- Add device list, capability inventory, last contact and pairing approval UI.
- Show connecting, pending approval, online, offline and revoked distinctly.
- Reuse generic device bindings for extensions; do not bake a device ID into a ZIP.
- Preserve existing route guards, localization and data-driven navigation.
- Acceptance: multiple Nodes, user/admin visibility, duplicate names and revoked
  credentials. Review desktop/mobile and light/dark UI.

## Stage 4 — Node Web UI

- Local status, Hub connection, inventory, network recovery and diagnostics.
- Render controls from declared capability/action schemas and approved mappings,
  never from a list of concrete applications or unrestricted GPIO numbers.
- Normal physical operations retain Hub authorization, expiry and execution
  journal semantics. A web button does not bypass the command path.
- Local maintenance requires explicit scoped authentication, exclusive ownership,
  short-lived service mode and audit. Offline physical control stays unavailable
  until that contract is implemented and tested; no shared default fleet password.
- An open setup AP exposes provisioning only, never physical controls or secrets.
- Acceptance: unauthorized actions rejected; Hub/local command conflicts cannot
  produce duplicate pulses; network reset retains pairing.

## Stage 5 — Hardware and failure acceptance

- Confirm exact Zero model, OS/architecture, reader model/interface and the
  controller's electrical input requirements before selecting drivers.
- Add the required generic reader adapter through the existing identifier boundary.
- Test scan -> Hub decision -> Node command -> output -> result, measuring
  end-to-end latency separately from heartbeat. Do not promise a latency before
  measurement; this is not a hard-real-time controller.
- Test network loss, Hub restart, Node reboot, duplicate delivery and expired
  commands. Never replay an uncertain physical action or old buffered access grant.
- Existing permitted local workloads may continue offline; access authorization
  does not become an implicit offline permission. Emergency egress remains a
  hardware/site safety responsibility, not dependent on Hub availability.
- Accept clean one-command install -> phone Setup -> pairing -> real hardware on
  two devices. Publish installation instructions only with the tested matrix.

## Stage 6 — Node lifecycle and staged updates

- Device-scoped diagnostics, credential revocation/reassignment and update status.
- Node updates retain immutable activation, bounded storage and rollback.
- Introduce rollout groups only after single-Node updates and mixed-version
  protocol compatibility are accepted. No automatic fleet-wide update by default.

## Work status

- [x] Map existing contracts and capture the agreed Fleet scope.
- [x] Stage 1 dependency audit: Agent required but did not declare `requests`.
- [x] Minimal shared Agent/Setup requirements file, including the Linux GPIO adapter.
- [x] Release-local profile reader and rejection of Hub/Standalone activation on
  a minimal Node before any systemd or Core bootstrap mutation.
- [x] Read-only Node feasibility checker; ARMv6 is a candidate, not certified support.
- [x] Separate Core-independent automatic recovery supervisor and hardened unit
  template; no public control endpoint and no enablement on existing devices.
- [x] Agent, Setup and recovery import smoke check in a fresh minimal Windows
  virtualenv without SQLAlchemy/Core dependencies (not ARMv6 or GPIO acceptance).
- [x] Isolated Zero W runtime smoke: Agent HTTP/identity restart and Setup HTTP
  passed with mock hardware/network.
- [x] Reviewed piwheels alias retagging at build time with source/output hashes;
  binary bytes unchanged, `pip check` passed on Zero without disabling checks.
- [x] Experimental Node branch in the existing immutable release installer,
  with bounded shell regression tests (not target-device acceptance).
- [x] Node installation and real post-health failure rollback on Zero with existing
  Wi-Fi retained; services, identity and environment independently verified.
- [ ] Published one-command clean-media install and phone/AP onboarding acceptance.
- [x] Separate Node artifact/wheelhouse, release workflow and `--profile node`
  bootstrap path implemented locally; publication is separate.
- [x] Setup hides full-runtime roles on Node and rejects them before network mutation.
- [ ] Stages 2–6 implementation and acceptance.

### Stage 1 findings and next work

Target confirmed: Raspberry Pi Zero W Rev 1.1 (ARMv6), reachable at
`rasp-3mmw.local`, running Raspbian 13 and Python 3.13.5. See the read-only
[Zero baseline](FLEET_ZERO_BASELINE.md). Isolated ARMv6 dependency installation
and imports passed. The original piwheels ARMv7 metadata issue is handled by
reviewed release-time retagging with recorded hashes; target `pip check` passed.
USB 125 kHz reader is only a candidate purchase, with HID mode not confirmed.

`deployment/node-requirements.txt` composes Agent and Setup requirements without
SQLAlchemy, PostgreSQL, AI or Node.js/compiler dependencies. It must be tested in
a fresh target virtualenv: the existing Hub environment cannot prove isolation.
Python must be at least 3.11 because Agent uses `datetime.UTC`. Native packages
such as pydantic-core and gpiod need ARMv6 installation evidence; no success on
another architecture substitutes for this.

Run the new diagnostic against a checkout with its Node dependencies available:
`python3 deployment/node_preflight.py`. It does not install packages, change
NetworkManager, contact the cloud or mutate services. Its dependency result is
separate from `installer_ready`, which remains false while installer integration
is unfinished. Do not use the current public installer on Zero W yet.

The default full installer still installs Core dependencies, compiles the extension
toolchain and prepares/migrates Core state. The always-on update helper imports
Core backup/update/application modules and also owns automatic network recovery.
A Core-independent supervisor now exists as `three_mm_runtime.node_recovery`,
with `3mm-node-recovery.service`. It reuses the five-minute link-loss policy and
existing setup activation worker; it does not expose an RPC endpoint or run on
full-profile releases. Node policy is stored under provisioning, not the Core
directory. The experimental Node installer branch selects this unit instead of
the Core update helper. Merely setting the role to Node does not select this
minimal installation profile.

The internal `deployment/install-systemd.sh` sixth positional argument selects
`full` (default) or `node`; bootstrap exposes `--profile node`. Node requires
an archive checksum, binary-only dependencies, successful `pip check`, import/
command preflight and compatible persisted role before stopping existing services.
It skips Core users/database/key creation, npm, migrations and application-host
units. Hub URL and hardware configuration are preserved on Node upgrades.
Cross-profile replacement is rejected before service mutations. Node rollback
restores the previous release/environment/units or removes newly installed units
and its current link on failed first activation; persistent state is retained.

Releases through beta.19 have no Node artifacts. Beta.20 build and bootstrap
support a separate `3mm-node-manifest.json` for ARMv6/Python 3.13;
other combinations fail closed. See [Node installation](NODE_INSTALLATION.md).
Phone AP recovery, durable pairing and physical hardware acceptance remain
separate from installer verification.

The `.3mm-install-profile` marker belongs to the root-owned immutable release,
not user-editable environment state; missing marker retains legacy full-runtime
compatibility. Setup role filtering/pre-network validation is implemented.
The installer writes the marker only to a new release.

Validation: latest scoped run passed 64 tests covering wheel normalization,
deterministic minimal artifacts, existing full release builder, Setup, installer
branches and runtime activation. Real target installation evidence is recorded
in the baseline document. No Hub, payment or business extension was changed.
Target acceptance confirmed the previous release recovered after the injected
failure; the test's exit code 1 is expected, not an unresolved failed deployment.
