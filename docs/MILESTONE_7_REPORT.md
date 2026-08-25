# Milestone 7 Report

Date: 2026-08-17

Reference commit: `3fad71c feat: add runtime extensions and refresh application shell`

## Result

Milestone 7 is complete. 3mm can install and run useful declarative extensions
without rebuilding the main Vue application and without executing generated
Python or JavaScript. A `runtime-extension v1` definition describes entities,
fields, pages, navigation, actions, roles and data permissions. Core validates
that definition and the existing frontend renders it through generic table and
form components.

The hand-written Contacts package proves the full package-to-use workflow. It
is installed through Module Manifest v2, appears in the extension catalog,
registers its route and navigation dynamically, and supports validated create,
read, update and delete operations through the generic runtime data API.

## Runtime and data lifecycle

- Published module versions and package hashes are immutable.
- A selected version may be changed without changing the package archive.
- Disable and re-enable preserve both the selected version and entity data.
- Rollback can reactivate an earlier version without deleting records.
- Uninstall preserves data by default; permanent deletion requires an explicit
  `delete_data` operation.
- Runtime routes are checked against Core routes and other active runtime
  extensions before activation.
- Role requirements are enforced by the data API rather than only hidden in
  the frontend.

Installed runtime behavior has no dependency on an AI provider or available AI
credit. AI may produce a candidate definition, but the same strict contract is
validated before it can be published.

## User workflow

The Extensions screen combines installed runtime definitions and available
packages in one catalog. An administrator can inspect status and versions,
activate a reviewed package, disable or re-enable it, select a rollback version,
and uninstall it with an explicit choice about retained data.

Routes and menu entries come from the validated definition. The Core and main
frontend do not contain a concrete Contacts route or component name.

## Automated verification

The Milestone 7 suite covers:

- strict runtime contract parsing and deny-by-default validation;
- immutable version publication;
- authenticated and field-validated CRUD;
- role enforcement;
- route-conflict rejection;
- package-hash activation;
- localized catalog metadata;
- disable, re-enable, rollback and restart-safe selected versions;
- uninstall with retained or explicitly deleted data;
- persistence of records across version changes.

Frontend tests cover runtime catalog normalization and route discovery. The
frontend TypeScript check and production build passed for the accepted release.

## Raspberry acceptance result

The runtime extension workflow was deployed to `rasp-3mm`. The Contacts
reference package was installed and opened from the running application without
rebuilding or restarting the main frontend. CRUD records remained available
after version and enable-state changes, and uninstall behavior was reviewed on
the physical deployment.

## Boundary retained for the next milestone

Milestone 7 deliberately supports declarative pages and data operations only.
Vue source, arbitrary browser behavior and executable backend code are not part
of `runtime-extension v1`; reviewed Vue compilation is handled separately by
Milestone 8.
