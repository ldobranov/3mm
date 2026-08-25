# Milestone 8 Report

Date: 2026-08-21

Reference commit: `b9d00b4 feat: add compiled extension project workflow`

## Result

Milestone 8 is complete for reviewed, trusted Vue packages. 3mm can validate a
versioned `compiled-ui v1` source package, compile its Vue entrypoints during
installation, publish content-addressed JavaScript and CSS artifacts, and load
widgets, editors, routes and reusable components without rebuilding or
restarting the main frontend.

Module Manifest v2 remains the package envelope. The compiled UI contract binds
the module ID and version to named entrypoints and their kinds. Core serves only
artifacts whose source archive, manifest and compiled artifact metadata agree
on the reviewed SHA-256 identity.

## Compilation and artifact lifecycle

- Source archives are validated before the compiler starts.
- Entrypoints must remain inside the package and use the declared kinds.
- Non-allowlisted bare imports are rejected before execution.
- The compiler runs in a temporary workspace with a bounded timeout.
- Failed compilation does not publish a partial artifact.
- Successful artifacts use immutable, content-addressed paths outside the
  application release directory.
- Reinstalling an identical source hash reuses the existing artifact.
- The catalog exposes the exact source hash and hashed asset URLs.
- Disable, rollback and uninstall use package identity rather than hardcoded
  component names.

The browser loader discovers entrypoints through the generic catalog, loads
their styles once, imports the reviewed module URL, and registers dynamic
routes, widgets and editors from package metadata.

## Project workflow

Extension projects preserve their editable source files, specification,
generation history and build results. A build produces a new immutable package
version rather than overwriting the installed artifact. Validation and compile
errors remain attached to the project so the user can correct the existing
project instead of starting again from an empty prompt.

The Digital Clock package is the reference compiled widget. It includes normal
widget and editor entrypoints and demonstrates that a `.vue` widget can be
installed and rendered by the prebuilt application.

## Automated verification

The Milestone 8 suite covers:

- compiled source contract and path validation;
- manifest/contract identity agreement;
- allowlisted imports;
- content-addressed, atomic artifact publication;
- failed-build cleanup;
- immutable catalog and asset delivery;
- project creation, file editing and version history;
- reviewed-build identity before installation;
- generic frontend catalog, component and project clients.

Frontend TypeScript checking, unit tests and the production Vite build passed
for the accepted implementation.

## Raspberry acceptance result

The compiler toolchain and immutable artifact store were deployed on
`rasp-3mm`. Reviewed Clock Vue source compiled during installation and rendered
inside the dashboard through the generic loader. Editor and route entrypoints
used the same artifact pipeline, and a failed build did not replace the active
version.

Follow-up testing exposed Builder usability, translation, edit and uninstall
gaps. Those were treated as lifecycle and Builder integration work rather than
as a reason to bypass the compiled artifact boundary, and were continued in
Milestone 9.

## Security boundary

This milestone does not claim that same-origin compiled JavaScript is a sandbox
for untrusted marketplace code. Packages are explicitly reviewed and trusted
before installation. Strong isolation, signing and a restricted Extension Host
for genuinely new executable code remain future production work.
