# Milestone 9 Report

Date: 2026-08-23

Reference commits:

- `c508b43 feat: make AI extension builds capability-driven`
- `3d9c460 feat: complete capability-based extension builder`

Accepted Raspberry release: `m9-real-gpio-20260823-090627`

Device identity: `dev_a3ad5f8844f1466f847f5f8cf78d6fe3`

## Result

Milestone 9 is complete. The AI Extension Builder now translates a plain
language request into a versioned capability plan and combines that plan with
trusted deterministic runtime foundations. A provider is responsible for
intent and presentation choices; it does not need to recreate package
lifecycle, configuration persistence, permissions, editor wiring or live data
access for every widget.

Existing projects can be reopened, edited, repaired and rebuilt. Versions grow
from project history, validated artifacts are reused where possible, and the
user no longer has to re-enter the entire prompt or assign package versions
manually for a small correction.

## Builder workflow

- A simplified request collects the desired result before exposing technical
  package details.
- Intent planning selects supported capabilities and produces a reviewable
  plan.
- Deterministic generation supplies the trusted package, editor and runtime
  structure.
- Provider, generation, validation, compilation and installation failures are
  reported as distinct stages.
- The exact successful build is bound to its source and artifact hashes before
  Install becomes available.
- Project files and generation history remain editable for incremental repair.
- Capability-aware defaults support common timers, configuration forms,
  persistent values, CRUD data and physical input state.

The Builder still exposes an advanced project surface, but the normal path no
longer requires a user to understand routes, source filenames, schemas or
manual semantic versions.

## GPIO capability vertical slice

The milestone adds a complete generic input-state boundary:

`Digital input driver → Agent capability → Core state API → compiled widget`

The Agent publishes capability snapshots and transitions. Core stores the
latest per-device state with observation and receipt timestamps. Authenticated
APIs enforce device ownership and declared capability access. A public display
receives only the one widget channel allowed by its reviewed package and saved
configuration; it does not expose a general device-state endpoint.

The generated GPIO lamp widget supports a selected device and channel, labels,
colors, active state and stale/offline behavior. Its trusted runtime resolves
the deployed backend dynamically rather than assuming a laptop development
origin.

## Real Raspberry GPIO adapter

The isolated mock contract was preserved and a separate `gpiod` driver was
added for native Raspberry hardware. Real access is opt-in through Agent
configuration. The systemd Agent receives only the supplementary `gpio` group,
and browser, Core and generated code never open `/dev/gpiochip*` directly.

For physical acceptance:

- logical `gpio.input.1` was mapped to BCM17;
- BCM17 used an internal pull-up and active-low input semantics;
- the official `gpiod` Python bindings used `/dev/gpiochip0`;
- mock diagnostics returned `404` while the real driver was active;
- an open input produced `false` and a red `Inactive` lamp;
- connecting physical pin 11 (BCM17) to physical pin 9 (GND) produced `true`
  and a green `Active` lamp;
- disconnecting the jumper restored the red state;
- the user confirmed the physical transition worked.

## Automated verification

At final review:

- 263 of 267 Python tests passed on Windows;
- the four remaining assertions check Unix `0600` modes that NTFS cannot
  represent through the same stat bits;
- the corresponding credential, journal, reconciliation and outbox files were
  verified as owner-only `0600` on `rasp-3mm`;
- all 23 frontend unit tests passed;
- frontend TypeScript checking and the production build passed;
- migration, public capability scope, package identity, Agent publication,
  project repair and GPIO driver tests are included in the suite.

## Raspberry resource snapshot

After more than three days of continuous runtime, all Agent, Core and Web
services remained active and swap use was zero.

| Service | RSS | Observed CPU |
| --- | ---: | ---: |
| Core | 119,320 KiB | 2.4% |
| Agent | 55,456 KiB | 0.8% |
| Web | 20,488 KiB | 0.0% |
| Combined | 195,264 KiB | 3.2% |

The Pi reported 905 MiB total RAM, 326 MiB used by the complete operating
system, and 578 MiB available. These are observations from the current Pi 3B+
test device, not guaranteed production limits.

## Remaining product boundary

Milestone 9 proves reliable composition of registered capabilities. It does not
make arbitrary AI-generated executable code safe. The next stabilization work
must consolidate the extension lifecycle, remove legacy paths, split the large
Builder implementation, unify deployment and strengthen frontend workflow
tests before new extension capabilities are added.

## Post-acceptance stabilization — 2026-08-25

The first real incremental edits exposed two workflow gaps that were corrected
before starting Milestone 10:

- free-provider responses now accept both strict JSON and an explicit 3mm file
  envelope, handle non-string or truncated responses, and fall through to the
  next configured provider when a response does not contain usable files;
- accepting a reviewed modification now saves the source, assigns the next
  patch version, builds the immutable artifact and installs it as one action;
- installing or rolling back a compiled project migrates existing dashboard
  widget instances of the same module and entrypoint to the selected version,
  while preserving their configuration and layout.

The physical acceptance upgraded the existing DoorSensor widget from `0.0.1`
to `0.0.2` and then exercised rollback and forward installation. The dashboard
loaded the new `Open count` behavior without recreating the widget. The accepted
Raspberry release was `worktree-ad7992ad3e03-20260825082710`.

Focused verification passed 37 frontend tests and 18 backend compiled-package,
project lifecycle and public-capability tests. This stabilization remains part
of the Milestone 9 checkpoint rather than expanding the scope of Milestone 10.
The complete cross-project Python suite passed 276 tests; the four remaining
Windows failures are the already documented Unix `0600` file-mode assertions.
