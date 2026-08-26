# Milestone 10 Report

Date started: 2026-08-25

Status: in progress

Reference commit: `93b0fa9 feat: stabilize incremental extension upgrades`

Canonical rollback release: `93b0fa951373-20260825090942`

Active retention-test release: `worktree-93b0fa951373-20260825104929`

Device: Raspberry Pi 3B+ (`rasp-3mm`)

Device identity: `dev_a3ad5f8844f1466f847f5f8cf78d6fe3`

## Current result

The first Milestone 10 reliability slice is accepted. The Standalone Core,
Agent and Web services recover automatically after a controlled Raspberry Pi
reboot. The Agent also survives a controlled Core outage, buffers pending
traffic and flushes its outbox after Core returns.

The tests preserved the device identity, approved registry record, extension
project history, compiled widget version, widget configuration and dashboard
layout. NetworkManager and the saved network profiles were not modified.

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

The procedure has not been run from an erased SD card in this pass because doing
so would destroy the only working test installation. That physical repetition,
the setup-AP reboot boundary and the service transition after real phone setup
remain acceptance work.

## Remaining acceptance work

- configure and physically verify a GPIO output before testing local
  input-to-output automation with Core unavailable;
- repeat the documented Standalone installation, first-boot and pairing flow on
  clean media;
- verify the open setup-only AP and saved NetworkManager profile across reboot;
- verify the physical setup-to-Standalone service transition;
- complete external-Hub credential bootstrap for a Node first boot;
- measure a Pi Zero 2 W if that hardware becomes available;
- close the final Milestone 10 acceptance checklist after the remaining physical
  tests.
