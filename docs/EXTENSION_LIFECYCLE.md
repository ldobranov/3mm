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

`runtime-extension v1` is the preferred form for CRUD records, forms, tables,
lists and simple pages. It contains data and presentation declarations only and
does not execute package-provided Python or JavaScript.

### Compiled UI

`compiled-ui v1` provides reviewed Vue widgets, editors, routes and components
as immutable browser artifacts. It is currently a trusted-package boundary,
not a sandbox for untrusted marketplace code.

### Agent runtime

Agent packages may select only registered built-in runtime handlers. Hardware
access remains inside the Agent driver boundary. Package data cannot import or
execute arbitrary Python on a managed device.

## Canonical lifecycle

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

## Legacy compatibility boundary

The original `Extension` database model, ZIP installer and in-process Python
loader are legacy compatibility features. New features must not depend on them.
They remain frozen until existing installations and data are migrated to Module
Manifest v2 or explicitly archived.

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
