# Core 0.3.1

Core 0.3.1 consolidates the common application platform and SDK work since
beta.57. Core owns current authority, resource selection and lifecycle; optional
providers and workers perform execution. This remains a pre-1.0 development
prototype. The Stable update channel selected by `v0.3.1` is not a claim of
production maturity or completion of every planned capability.

## Changes

- Common resource/provider discovery and explicit device capability selection.
  A saved selection does not silently change when another provider appears or
  one becomes unavailable. Discovery grants no execution authority.
- Reviewed resource rebinding for installed applications, with explicit consent,
  lifecycle recovery and original-resource outcome lookup rather than replay.
- Current human actors, stable user subjects, bounded delegation and Core-owned
  kiosk access. Human permissions remain separate from service resource grants;
  obsolete kiosk credentials require pairing again, not implicit adoption.
- Result-bearing one-shot tasks, interval/calendar schedules and a separate
  bounded task worker. Restarts, revocation and uncertain effects retain explicit
  outcomes and do not authorize blind retries.
- Streaming private files, temporary bounded downloads and optional image
  derivatives. Image-provider dependencies belong to their separate host profile,
  not the Core dependency environment.
- Shared themed/localized UI forms, tables and loading/error/empty states;
  application connector settings and provider readiness administration.
- Recoverable exact-package upgrades and uncertain lifecycle administration,
  without requiring uninstall to replace an application version.
- Shared read-only UI trust leases, request-local reuse of verified immutable
  code and coalesced in-flight SDK discovery. Current identity, approvals and
  resource authority remain checked at effect and response boundaries.
- Builder, Automations, Dashboards, declarative CRUD and legacy content extracted
  from live Core into preserved optional sources/libraries and historical data.
  Their extraction does not mean each product is ready as an installable app.
- Raspberry setup/recovery improvements and content-verified local deployment
  tooling. Existing upgrade network choices remain preserved; device role and
  network ownership are separate.

## Versions, installation and components

Core is **0.3.1**, Device Protocol remains **1.0**, and Application SDK remains
**1.3**. These version axes are independent; unchanged numbers do not imply
unchanged source or independent component artifacts. Terminal 1.0.3 is a separate
application and is not a Core release asset.

Full-profile archives include the prebuilt frontend and exact component sources
and contracts. The minimal ARMv6 Node archive has its own manifest and wheelhouse.
Use the published immutable `v0.3.1` artifacts, not an unrelated local candidate
with the same VERSION. Verify the installed release commit and component pins.

Existing Runtime, connector worker, application-host, Agent and session components
have independent update boundaries. A Core-only update retains their existing
pins; it does not enable new workers, approve application access or update every
application host. Select and probe corresponding components explicitly when a
current application needs their new contracts. A device already running the
accepted matching components does not need those components replaced again.

## Data and recovery

Schema history advances from `3e189f465708` to **`b096b7e82f86`**. Migrations add
task/schedule history, stable user subjects and kiosk incarnations; retired
product data is retained rather than silently erased or reactivated as authority.
Registered custom data with unresolved ownership can refuse retirement and needs
an explicit export/ownership plan, not a forced reset.

Keep a verified database/key backup before updating a device whose state matters.
Populated task, identity, kiosk and retired-product history can intentionally
refuse downgrade. Selecting an older Core directory alone does not recover its
database or independent component versions. No device wipe, key reset or
automatic restoration of old permissions is part of this release.

## Verification and limits

Hosted branch CI [40684871440](https://github.com/ldobranov/3mm/actions/runs/40684871440)
passed for `5aa724603619031b56bad175fc85b808decac096`: Linux Python, real compiled-UI
integration, frontend tests/type-check/build and development tooling. Merge
`0c536c9` preserves that executable tree; integration and release preparation
change documentation only. Scoped and owner-device evidence remains recorded
with its actual snapshots in [WORKING_STATE](WORKING_STATE.md), not relabelled as
an independent final-tag hardware test.

After automatic main CI succeeds, an annotated `v0.3.1` tag starts Release.
Configured Python/frontend/tooling checks and two reproducible full/Node build
passes must succeed. All seven assets must upload before the draft becomes
public. See [RELEASING](RELEASING.md). A tag or draft alone is not publication.

The accepted Linux session profile is a restricted temporary workspace. Full
M21/remote Terminal UI, host/root administration, public Cloud, whole WP5 and the
complete capability roadmap are not newly claimed. Native application approval
permits Linux code execution and is **not a sandbox**. Publishing this release
does not itself deploy it or expand device/application acceptance.
