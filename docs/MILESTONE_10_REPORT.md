# Milestone 10 Report

Date started: 2026-08-25

Status: completed on 2026-08-28

Closure release: `v0.3.0-beta.9`

Canonical rollback release: `v0.3.0-beta.8`

Active review release: `worktree-4eb350b6a650-20260828075444`

Device: Raspberry Pi 3B+ (`rasp-3mm`)

Current clean-install device identity: `dev_693cbd1cefd74061a2ac38ccbc5daef8`

## Current result

The first Milestone 10 reliability slice is accepted. The Standalone Core,
Agent and Web services recover automatically after a controlled Raspberry Pi
reboot. The Agent also survives a controlled Core outage, buffers pending
traffic and flushes its outbox after Core returns.

The tests preserved the device identity, approved registry record, extension
project history, compiled widget version, widget configuration and dashboard
layout. NetworkManager and the saved network profiles were not modified.

The complete Standalone Beta OTA path is also accepted through official
release `v0.3.0-beta.5`, including persistent operational policy, a retained
official rollback release and the post-install `up_to_date` catalog state.

The administrator-controlled network recovery slice is physically accepted on
the same device. Normal Web access now works on port 80 through both the LAN IP
and `rasp-3mm.local`, while port 8080 remains available for compatibility.

The documented one-command installation has now also been repeated on clean
media. The Wi-Fi-only bootstrap survived the SSH handoff, exposed the open setup
AP and captive portal, and returned to a healthy Standalone runtime after phone
provisioning. The review deployment adds secret-free recovery prefill,
audience-aware menus and audited restart/factory-reset controls. The complete
destructive reset, AP reboot and fresh setup path is physically accepted.

## Controlled reboot acceptance

Before reboot:

- all three services were enabled and active;
- the active immutable release was healthy;
- the Agent reported its persistent device identity;
- DoorSensor project and dashboard widget were both on version `0.0.3`;
- the root filesystem used 7.2 GiB of 29 GiB.

The kernel boot ID changed from
`dd1022de-9759-4452-97c8-5a25d209c5d9` to
`387e334e-6487-440a-8ae5-388b79a8314b`. SSH became reachable again about 29
seconds after the observed disconnect.

After reboot:

- `3mm-agent`, `3mm-core` and `3mm-web` were enabled and active without manual
  service intervention;
- Agent and Core readiness endpoints returned `ready`;
- the Agent retained device identity
  `dev_a3ad5f8844f1466f847f5f8cf78d6fe3` and appeared online in Core;
- DoorSensor remained installed at `0.0.3` and the existing dashboard widget
  still referenced `compiled:org.3mm.generated.doorsensor:0.0.3:widget`;
- the widget retained device, channel and active-high configuration;
- the real `gpio.input.1` capability resumed publication with a fresh
  observation timestamp;
- the complete system used 280 MiB of 905 MiB RAM immediately after recovery,
  with 624 MiB available and zero swap in use.

## Controlled Core outage acceptance

Core was stopped for longer than one Agent heartbeat interval while Agent and
Web remained running.

- Agent readiness remained healthy throughout the outage;
- Core command polling and desired-state reconciliation failed visibly rather
  than terminating the Agent;
- the persistent Agent outbox grew to 1095 bytes while Core was unavailable;
- after Core restarted, the outbox returned to the empty serialized state of
  three bytes;
- Core marked the device online again and received a fresh GPIO capability
  observation.

The test proves buffering and reconnect behavior. It does not yet prove a real
input-to-output automation during Core downtime because the current physical
baseline exposes BCM17 as an input but has no reviewed output wiring and mapping.

## Canonical release alignment

The verified source was committed and pushed to `main` as `93b0fa9`. A clean
immutable deployment then activated release `93b0fa951373-20260825090942` with
`includes_working_tree` set to `false`. All 37 frontend tests, TypeScript checks
and the production build passed during deployment. Agent, Core and Web were
healthy after activation, and the startup outbox drained automatically.

## Storage finding

The canonical deployment increased the Raspberry history to 89 immutable
releases. Overall root filesystem usage is still safe at 27%, but unbounded
release growth is not acceptable for Milestone 10.

A dry-run-first retention tool now protects the active release, an explicit
rollback release and a configurable number of additional recent releases. It
reports the exact candidates and their combined logical size, never traverses
outside `/opt/3mm/releases`, and requires a separate `--apply` flag for deletion.
Deployment and cleanup use the same exclusive mutation lock. Persistent data
below `/var/lib/3mm` is not part of the cleanup scope.

The first physical dry run used a history count of three and completed without
changing the device:

- active release: `93b0fa951373-20260825090942`;
- protected releases: four;
- deletion candidates: 85;
- estimated reclaimable storage: 2.3 GiB;
- dry-run duration: about nine seconds.

The existing release initially predated the explicit `/opt/3mm/previous`
rollback link. The first dry run therefore reported `rollback=missing` and
correctly blocked apply.

The tested worktree was then deployed as
`worktree-93b0fa951373-20260825104929`. The installer preserved the prior clean
release `93b0fa951373-20260825090942` as the explicit rollback target. A second
dry run protected both releases plus three recent historical releases and
reported the same 85 deletion candidates. That exact plan was applied.

After cleanup:

- exactly five protected release directories remain;
- `/opt/3mm/releases` uses 728 MiB instead of 3.1 GiB;
- root filesystem usage fell from 7.2 GiB (27%) to 4.8 GiB (18%);
- 23 GiB is available on the 29 GiB root filesystem;
- active and rollback links still resolve to their protected directories;
- Agent, Core and Web remain active and the public login page returns HTTP 200;
- the release smoke test passes with the persistent device identity unchanged.

Seven focused retention tests and the two release-smoke tests pass. The full
backend suite passes with 130 tests. The candidate installer also passes
`bash -n` on the Raspberry, and the retention tool compiles and executes with
the device's system Python.

## Interrupted deployment acceptance

A deterministic rollback test was run without interrupting a filesystem write
or cutting device power. The reserved candidate
`rollback-test-worktree-93b0fa951373-20260825110144` completed extraction,
release-specific Python and frontend compiler dependency installation, state
backup, environment update, database migration, atomic activation and runtime
health verification. The installer then injected an expected failure after the
new runtime was healthy.

The error trap automatically:

- stopped the candidate runtime;
- restored the SQLite backup and service environment;
- restored `/opt/3mm/current` to the exact pre-test release
  `worktree-93b0fa951373-20260825104929`;
- reinstalled the prior systemd definitions and reactivated the runtime;
- removed the failed release directory and uploaded archive.

After rollback, the explicit `/opt/3mm/previous` target remained the clean
`93b0fa951373-20260825090942` release and the release count remained five. Agent,
Core and Web were active, the public login page returned HTTP 200, the release
smoke test passed and device identity remained
`dev_a3ad5f8844f1466f847f5f8cf78d6fe3`. The Agent outbox returned to its empty
three-byte state. The exact test-only deployment backup was removed after
verification.

## Deployment backup retention acceptance

The rollback test exposed a second bounded-storage requirement: 17 historical
deployment backups still used 163 MiB after immutable release cleanup.

A separate root-only, dry-run-first retention tool was added. The first physical
dry run correctly prompted a policy review because it treated a backup matching
one of the five retained releases as a deletion candidate. No data was changed.
The policy was tightened before apply so it always protects:

- the backup named for `/opt/3mm/current`;
- the backup named for `/opt/3mm/previous`;
- three additional recent migration recovery points.

The corrected dry run protected backups corresponding exactly to all five
retained release directories and selected 12 older backups representing 106.4
MiB. That exact plan was applied. After cleanup:

- five release directories and five matching deployment backups remain;
- deployment backup storage fell from 163 MiB to 57 MiB;
- root filesystem usage is 4.7 GiB (18%) with 23 GiB available;
- release smoke verification passes and Agent, Core and Web remain active;
- the persistent device identity is unchanged.

Fourteen focused retention and release-smoke tests pass. The complete backend
suite is green with 137 tests.

## First-boot preflight and installation procedure

A dependency-free, read-only preflight now checks the prerequisites that the
immutable installer and setup runtime actually require. It verifies Linux on a
supported Raspberry architecture, Python 3.10 or newer with `venv`, Node.js 20
or newer, npm, the required system commands, active NetworkManager, the
hardcoded `wlan0` setup interface and, when requested, every required release
file plus compiled frontend JavaScript.

The preflight was copied to `/tmp` and executed as the normal `raspberry` user
against the active physical release. All checks passed:

- Debian GNU/Linux 13 on `aarch64`;
- Python 3.13.5 with `venv` available;
- Node.js 20.19.2 and npm 9.2.0;
- NetworkManager active with `wlan0` connected;
- all required installer, migration, service and compiler files present;
- 20 compiled JavaScript assets present in `frontend/dist/assets`;
- final result `ready` with zero failures.

No package, service, connection profile or network setting was changed by the
check.

Four focused preflight tests and nine runtime/deployment structure tests pass.
The complete `backend/tests` suite is green with 141 tests. A broader Windows
collection passes 293 tests and retains four pre-existing failures that assert
POSIX `0600` mode bits on NTFS; the same private-file mode path was exercised
directly on the Raspberry and passed with mode `0600`.

The Windows deployment wrapper also had a genuine clean-device defect: after a
successful install it always expected Core and the login page, although the
shared runtime planner correctly starts only the setup portal on an
unprovisioned device. The wrapper now identifies the active runtime and accepts
either a healthy setup portal or the complete Core/Web/Agent runtime.

The repeatable procedure is recorded in
[RASPBERRY_PI_FIRST_BOOT.md](RASPBERRY_PI_FIRST_BOOT.md). It covers host
preflight, immutable deployment, the open setup-only access point, Wi-Fi and
Standalone role selection, interactive administrator creation, local Agent
pairing and final smoke checks. It explicitly requires wired Ethernet during
the remote first install because setup mode takes ownership of `wlan0`.

Two product boundaries remain visible rather than being hidden by the guide:

- the setup form's administrator name is metadata; the first login account is
  still created through the secret-free interactive bootstrap;
- Node provisioning stores the Hub address, but external-Hub credential pairing
  is not yet a complete single first-boot flow.

The procedure was subsequently repeated from an erased SD card. The public
one-command bootstrap installed official `v0.3.0-beta.8`, switched the Wi-Fi-only
host to the open setup AP without depending on the SSH session and completed the
real phone setup-to-Standalone transition successfully. The setup-AP reboot
boundary remains separate acceptance work.

## Standalone OTA operational acceptance

Official `v0.3.0-beta.4` was installed as the exact clean OTA base, preserving
the existing persistent database, extension state and Agent identity. The
administrator then completed the in-application Beta update to published
release `v0.3.0-beta.5`.

Independent post-install verification confirmed:

- the root-owned operation reached `succeeded` for commit
  `dbb530db90a84b14db87e5aa7409349751060947`;
- `/opt/3mm/current` resolves to release `v0.3.0-beta.5` and
  `/opt/3mm/previous` resolves to the official `v0.3.0-beta.4` base;
- Core, Web, Agent and update-helper are active and the complete release smoke
  test passes;
- device identity `dev_a3ad5f8844f1466f847f5f8cf78d6fe3` is unchanged;
- the persisted Beta policy retains six-hour checks and the Europe/Sofia
  03:00–05:00 maintenance window;
- policy and cache files remain owned by `3mm:3mm` with mode `0600`;
- a fresh authenticated Beta catalog check reports current and latest version
  `0.3.0-beta.5`, status `up_to_date` and no available update.

## Network recovery and captive portal acceptance

The network recovery worktree was deployed as immutable release
`worktree-f433dada70b5-20260827170249`. The physical acceptance covered a
provisioned, Wi-Fi-only Raspberry Pi with no Ethernet fallback.

The accepted operator path is:

1. an administrator opens **Settings → Network Configuration**;
2. the page reports local link state and the usable
   `http://rasp-3mm.local` address;
3. **Start setup Wi-Fi** asks the narrow root helper to schedule setup mode;
4. Core, Web and Agent stop and the open `3mm Setup XXXX` AP starts;
5. setup-only DNS resolves phone captive checks to `10.42.0.1`, where port 80
   redirects to the setup portal on port 8895;
6. the phone opens the portal, scans nearby Wi-Fi networks and applies the
   selected profile;
7. the recovery marker clears and the normal Standalone runtime returns.

The setup portal used the saved application theme. The complete phone flow was
physically accepted, including automatic portal opening, successful save,
reconnection to the normal network and application access afterward. A
previous false `Setup could not be applied` result was corrected so the client
does not treat the expected AP disconnect as a failed save.

Automatic recovery is enabled by default after 300 continuous seconds without
either an active Wi-Fi or Ethernet link. It is administrator-selectable because
a Raspberry Pi powered by a UPS can legitimately outlive its router. The
monitor checks local link state only, not Internet reachability, and resets its
timer as soon as either link returns.

Normal Web access returned HTTP 200 at all accepted entry points:

- `http://192.168.1.88/`;
- `http://rasp-3mm.local/`;
- `http://192.168.1.88:8080/`.

The Web and setup services remain unprivileged and receive only
`CAP_NET_BIND_SERVICE` for port 80. Network mutation remains in the existing
root boundary. The captive DNS file is installed only while the setup AP unit
is active and is removed when that unit stops. Thirty-eight focused
setup/systemd tests and all 47 frontend tests passed before deployment.

## Clean-media and device-administration acceptance

On 2026-08-28, `rasp-3mm` was rebuilt from clean media and installed with the
documented public one-command Beta bootstrap. Setup completed over Wi-Fi and the
new installation returned to the normal Standalone application. Official
release `v0.3.0-beta.8` was then used as the rollback base for immutable review
release `worktree-4eb350b6a650-20260828075444`.

Post-deployment verification confirmed:

- Core, Web, Agent and update-helper are active;
- Agent health, versioned hello and inventory expose persistent identity
  `dev_693cbd1cefd74061a2ac38ccbc5daef8`;
- ports 80 and 8080 and `http://rasp-3mm.local/` return HTTP 200;
- the dynamic menu endpoint remains readable before authentication while each
  configured item can declare public, authenticated or administrator scope;
- restart and factory-reset endpoints exist and reject anonymous requests;
- the privileged helper contains only fixed restart and factory-reset actions;
- the factory-reset worker is present in the immutable release;
- service logs contain no post-deployment errors.

The user accepted recovery prefill, menu visibility and restart behavior. The
factory-reset request and worker are covered by automated permission, command
boundary and filesystem-scope tests. Physical execution also confirmed that
old 3mm state is removed, setup Wi-Fi returns after reboot, phone provisioning
can be completed again and the fresh Standalone login works.

Sixty focused backend/provisioning/deployment tests, all 54 frontend tests,
TypeScript checking and the production frontend build passed for this slice.

## Closure and deferred boundaries

Milestone 10 is closed on the available Raspberry Pi 3B+ baseline. The accepted
boundary includes clean-media installation, real GPIO input, immutable runtime,
reboot/reconnect, Core outage buffering, storage retention, OTA rollback,
network recovery, captive setup, restart and factory reset.

The following are deliberately moved out of this milestone:

- external-Hub credential bootstrap and multi-device orchestration move to the
  Hub/Node milestone;
- additional native output wiring and device integrations move to capability
  expansion and require their own hardware acceptance;
- Pi Zero 2 W measurements remain conditional on that hardware becoming
  available and do not block the accepted Pi 3B+ baseline.
