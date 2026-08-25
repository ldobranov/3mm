# Stabilization Audit

Date: 2026-08-24

## Current evidence

- 573 files are tracked in the repository.
- The full Python suite contains 273 tests. On Windows, 269 pass and four Unix
  permission-mode assertions are platform-inapplicable; the same files are
  verified as `0600` on Raspberry Pi.
- All 36 frontend tests pass. AI Builder planning, Extensions lifecycle and
  Dashboard create/delete behavior now have component-level workflow coverage;
  Settings remains the largest untested view.
- Raspberry Pi 3B+ runs Core, Agent and Web at roughly 195 MiB combined RSS with
  zero swap after more than three days of uptime.
- The new GitHub Actions workflow enforces Linux Python tests plus frontend
  tests, type checking and the production build after it is pushed.

## Canonical paths

- Editable work: `ExtensionProject` and project APIs.
- Package identity: Module Manifest v2 and `ModulePackage`.
- Declarative UI/data: `runtime-extension v1`.
- Trusted compiled Vue UI: `compiled-ui v1`.
- Device deployment: `ModuleInstallation` and Agent commands.
- Hardware state: registered Agent capabilities and scoped Core state APIs.

## First verified cleanup set

Repository-wide reference searches found no import, route, test, build or
runtime use of the tracked root `temp_*` extension directories. They are old
generated experiments and are removed from the working tree; Git history keeps
them recoverable.

The files under `.github/instructions` describe obsolete routes, old extension
layouts, Docker/Tailwind choices and HiveOS-specific experiments. They have no
scope metadata and conflict with the current project rules, so they are removed
in favor of the root `AGENTS.MD` and current architecture documents.

`frontend/scripts/compile-ui-extension.mjs` duplicates the active compiler at
`frontend/compiler/compile-ui-extension.mjs`. Core and both deployment paths
reference only the latter, so the unused copy is removed.

## Deferred cleanup requiring migration or compatibility work

- legacy `Extension` database records and in-process Python loading;
- legacy extension upload, marketplace, update and monitoring routes;
- old Settings and translation APIs still consumed by the current frontend;
- root install/start scripts that may still serve non-systemd development;
- legacy release directories created before the release-local virtualenv
  contract.

These paths must not be deleted from a filename-only audit. Their consumers and
persistent-data migrations must be mapped first.

## Unified deployment boundary

`deploy.ps1` now only prepares and uploads a verified release snapshot. The
single privileged implementation is `deployment/install-systemd.sh`. Every
release owns its virtualenv, Core state remains outside the release, service
activation is atomic, and failed migrations or health checks restore the
database, environment, systemd units and previous current link.

The contract was validated on Raspberry Pi on 2026-08-24 with release
`worktree-3d9c4600d8ae-20260824082414`. Core, Agent and Web started from the
release-local virtualenv, all readiness checks passed, the persistent device
identity remained unchanged and the database/environment rollback backup was
created successfully.

`deployment/release_smoke.py` makes the post-deployment boundary repeatable. It
checks the Web login and Builder shells, the required Core API paths, Agent
readiness, hello and inventory, and identity consistency. It passed against the
running Raspberry Pi with device ID
`dev_a3ad5f8844f1466f847f5f8cf78d6fe3` on 2026-08-24.
