# Canonical Extension Lifecycle

Date: 2026-08-24

This document defines the extension model used by new 3mm work. It separates
editable projects, immutable packages, device installations and runtime
entrypoints so the UI and APIs no longer use the word "extension" for unrelated
objects.

## User-facing objects

### Project

An editable development workspace owned by one user. It contains the current
specification, capability plan, source files and build history. AI assists a
project but is not part of its installed runtime.

### Build

An immutable result produced from one project revision. A successful build has
validated source and package hashes, a generated version and a complete report.
Only the exact successful build may be installed.

### Module package

The installable archive described by Module Manifest v2. The package declares
compatibility, permissions, capabilities, entrypoints and registrations. A
module ID plus version is immutable; changed content requires a new version.

### Installation

The selected package version and enabled state for a target runtime or device.
Disable and uninstall preserve module data by default. Permanent data deletion
is always a separate explicit action.

### Entrypoint

A package-provided surface such as a widget, widget editor, route, component or
Agent capability service. Navigation and UI discovery are derived from these
registrations rather than concrete module names in Core.

### Capability

A typed permission and data/action boundary supplied by the platform or another
module. AI may select and configure registered capabilities but cannot redefine
their security or lifecycle behavior.

## Supported runtime forms

### Declarative runtime

The old Core-owned `runtime-extension v1` CRUD format is retired. Declarative
records/forms/tables use the optional `libraries/three_mm_crud` dependency in an
ordinary supervised application with compiled UI. Records and migrations belong
to its own SDK-managed database; Core retains current admission and permissions.

### Compiled UI

`compiled-ui v1` provides reviewed Vue widgets, editors, routes and components
as immutable browser artifacts. It is currently a trusted-package boundary,
not a sandbox for untrusted marketplace code.

### Agent runtime

Agent packages may select only registered built-in runtime handlers. Hardware
access remains inside the Agent driver boundary. Package data cannot import or
execute arbitrary Python on a managed device.

## Canonical lifecycle

### Preparing another native application version

For the ordinary supervised native profiles, Extensions uses one stopped-package
path for updates and returning to an older uploaded version:

1. Upload the immutable package. Turn off the current application through its
   normal lifecycle; a running or uncertain lifecycle cannot be prepared.
2. Select the other version and choose **Prepare version**. The admin-only
   `POST /api/v1/application-extensions/packages/{sha256}/stage` request supplies
   a fresh 32-hex `request_id`, `expected_artifact_sha256`, the exact current
   `expected_revision` from authority status (or null when no grant exists),
   and declared device `configuration` overrides.
3. Core rechecks the current administrator, old artifact/revision, installation
   identity/epoch/configuration, candidate metadata and unresolved execution.
   It fences previous command authority and saves a sealed, disabled candidate.
   It does not import a wheel, call the runtime helper, migrate or start code.
4. Review and explicitly allow access for the candidate's exact package and UI
   build. Previous package approval never authorizes new bytes. Preparation
   itself grants no rights; a historical action replay performs no new effect.
5. Activate the reviewed version through the normal activation/health lifecycle.
   Installation identity, configuration, own data and old results remain owned
   by the same instance. The previous package pin remains available.

Returning to an older package uses these same steps and fresh approval; it does
not restore an old execution grant or reverse application data migrations.
An abandoned preparation followed by selecting old bytes also requires current
consent. Revoking that consent before activation prevents helper execution;
an older native-code attestation alone cannot start an inert candidate.
Relational migration and session-provider profiles retain their dedicated
prepared lifecycles and are refused by this ordinary-package preparation route.
Unresolved task outcomes and historical job claims must be reviewed first.
The installation catalog includes `package_sha256`, so a stopped candidate
with no `active_version` is displayed from its exact pin, not the newest upload.

Ordinary activation's helper response budget includes 120 seconds for package
validation, data preimages and systemd preparation, plus the declared
`service.startup_timeout_seconds`. The latter bounds elapsed health polling with
a monotonic deadline, including each probe and retry delay; it is not a retry
count multiplied by a fresh per-probe timeout. A genuine transport timeout or
lost response still requires explicit lifecycle recovery. A running process
alone does not prove that Core committed activation or restored the reviewed
authority; do not repair that state by changing the database or replaying a ticket.

### Explicit web lifecycle recovery

In Extensions, an interrupted `activating`, `disabling`, `uninstalling`,
`recovering` or `recovery_required` installation exposes **Recover application**.
This administration path stays available without a healthy compiled-UI/package
catalog and does not load application code or require its transport key.

The dialog reads the current stage and error from the admin installation catalog.
The administrator must review possible external effects and explicitly confirm
stopping. It calls the existing admin-only
`POST /api/v1/application-extensions/{module_id}/lifecycle/recover` with
`confirmed_external_outcome_reviewed: true`. Core's fenced helper must prove the
exact runtime quiescent before committing `disabled`, `enabled: false` and
`active_version: null`. Data, configuration, package pins and unresolved work
remain preserved; stopping proves neither migration rollback nor external-effect
reversal. No old permission is restored and no business operation is replayed.

After a verified response, Extensions refreshes the catalog and opens a fresh
application-access review when the package is available. Review/approval and
activation are separate explicit actions. A registered candidate without an
active version keeps its saved choices, but obsolete-epoch consent is not
presented as currently saved: fresh approval is required. An ordinary confirmed
disable/enable cycle retains its separate saved-consent behavior. A timeout, malformed reply or helper
failure leaves recovery unconfirmed; the UI requires a read-only status refresh
before another deliberate recovery attempt. It never retries a stop automatically
or interprets a lost response as success. Active/ordinary disabled installations
continue to use their normal lifecycle controls.

### General lifecycle

1. Create or reopen a Project.
2. Describe the desired result and select capabilities.
3. Review the generated plan and permissions.
4. Build and validate an immutable package version.
5. Install the exact successful build.
6. Discover routes, widgets and editors from package registrations.
7. Disable, re-enable or select a previous installed version without deleting
   data.
8. Uninstall while preserving data, or explicitly request permanent deletion.

The Extensions screen should present packages and installations. The Builder
should present projects and builds. These concepts may link to each other but
must not be merged into one ambiguous record.

## Retired prototype boundary

The original `Extension`/`Page` models, arbitrary table/translation engine and
obsolete database scripts are preserved as source-only evidence in
`modules/legacy-content`. They are absent from Core release payloads and are not
a compatibility runtime. Migration `9e74f5c60d64` archives their data and scoped
legacy permissions without live principal FKs; it does not import records into
applications or restore old grants. Custom data ownership must pass preflight.
Populated recovery requires a verified prior backup with matching release and
package files; an empty retirement supports historical downgrade.

Navigation retains its own Core Menu model. Language lifecycle stores only code,
selected immutable package and enabled state; translations come from validated
manifest-v2 packages with the English recovery fallback.

The following are not new extension formats:

- an Extension Project is an editable workspace;
- an AI job is an optional planning/build operation;
- a compiled artifact is a build output;
- a menu entry is a registration consumer;
- a widget instance is saved display configuration.

## Stabilization rules

- Do not add another package, project or installation model.
- Do not hardcode a module or entrypoint name in Core or the main frontend.
- Prefer declarative capabilities over newly generated executable code.
- Keep provider failure outside installed runtime availability.
- Require migration, rollback and data-retention behavior for lifecycle changes.
- Treat same-origin compiled UI as trusted until a production Extension Host
  isolation model is implemented.
