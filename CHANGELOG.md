# Changelog

All notable changes to 3mm are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/) while remaining
pre-1.0.

## [Unreleased]

## [0.3.0-beta.8] - 2026-08-27

### Added

- A Beta-only first-install administrator for a brand-new empty database, with
  the documented `admin@example.com` / `admin` test login. Existing databases,
  users and passwords are never replaced or reset.
- A Wi-Fi scan cache captured before the device changes `wlan0` into the setup
  access point, so the phone setup page can still list nearby networks while
  the single radio is serving the setup AP.
- Complete administrator user-management controls for listing users, assigning
  roles, optionally changing passwords and creating or deleting accounts.

### Fixed

- The setup scan now combines cached and live results and excludes the device's
  own `3mm Setup` network.
- Provisioning cache permissions now allow the setup service to read the scan
  prepared by the privileged network helper.
- User Management now calls the current authenticated user API, displays the
  initial administrator and enforces self-delete and last-administrator
  protection.
- User forms, feedback, English/Bulgarian text and the mobile layout are
  consistent with the current application shell.

### Verified

- Passed 57 focused backend, provisioning and deployment tests, all 50
  frontend tests and the production frontend build.
- Verified the Users API against the physical Raspberry deployment and
  reviewed the setup scan and initial-login flow on the clean Pi baseline.

### Documentation

- Updated the one-command installation, first-boot and release guides with the
  current Beta version and initial-account behavior.

## [0.3.0-beta.7] - 2026-08-27

### Fixed

- The detached bootstrap now uses the immutable installer's expected `0022`
  umask, allowing the unprivileged `3mm` service account to traverse and run
  the release-specific virtual environment during first-install migration.
- Failed first installation remains rollback-safe and can be retried without
  cleaning partial application state manually.

## [0.3.0-beta.6] - 2026-08-27

### Added

- A one-command Raspberry Pi bootstrap that selects the official architecture
  artifact, installs a fixed reviewed clean-host baseline, verifies release
  identity, size and SHA-256, runs the host preflight and delegates activation
  to the immutable installer.
- Wi-Fi-safe detached installation so first-boot setup can take ownership of
  `wlan0` without terminating the installation together with the SSH session.
- Administrator-only network recovery controls in Settings, including current
  Wi-Fi/Ethernet link state, manual setup-Wi-Fi activation and an optional
  automatic trigger after five continuous minutes without either local link.
- Nearby Wi-Fi scanning in the setup portal and reuse of the saved application
  theme while recovery mode is active.
- Captive-portal DNS and an HTTP entry point on port 80 during setup mode so a
  phone can open the setup page automatically after joining the open AP.

### Changed

- Replaced the legacy mutable source-tree installer and its obsolete guide with
  the official release-artifact bootstrap and current immutable layout.
- The normal web application is now available on port 80 at both the device IP
  and `<hostname>.local`; port 8080 remains a compatibility listener.
- Network recovery is coordinated through the existing root helper and runtime
  planner. The captive DNS override exists only for the lifetime of the setup
  AP and is removed when setup stops.

### Fixed

- Successful setup no longer reports a false apply failure while the device is
  already switching from the setup AP to the selected Wi-Fi network.
- Frontend URL normalization and CORS now support the device hostname without
  requiring an explicit port.

### Verified

- Deployed immutable review release
  `worktree-f433dada70b5-20260827170249` on `rasp-3mm` and verified HTTP 200 on
  ports 80 and 8080.
- Physically completed the manual AP, automatic phone captive portal, Wi-Fi
  selection, save, reconnect and normal application access flow.
- Passed 38 focused setup/systemd tests and all 47 frontend tests before the
  accepted deployment.

### Documentation

- Added the Network Recovery operator guide and updated first-boot, roadmap and
  Milestone 10 acceptance documentation.
- Added the single-command clean-install path to README and the dedicated
  installation guide. Clean-media physical acceptance remains pending.

### Known issues

- The first physical clean-media attempt inherited an overly restrictive
  transient-unit umask. Migration could not execute the release Python as the
  `3mm` user, so activation rolled back before setup AP startup. This is
  corrected in `v0.3.0-beta.7`.

## [0.3.0-beta.5] - 2026-08-27

### Added

- Persistent Standalone OTA policy for Stable/Beta/Test automatic catalog
  checks, configurable intervals and daily maintenance windows.
- Cached read-only update results with persistent exponential retry backoff.
- Server-enforced maintenance-window gating with a separate audited override
  for administrator-initiated installation outside the saved window.
- English and Bulgarian System Updates controls for the policy, cache state,
  next check and next maintenance window.

### Changed

- Opening System Updates can reuse the last trusted cached catalog result
  without making a new network request.
- Automatic update work is intentionally limited to catalog checks; staging,
  dependency changes, activation and rollback remain explicit administrator
  operations through the existing root helper.

### Fixed

- Included the IANA timezone database on Windows so maintenance-window policy
  validation behaves consistently in local development and on Linux devices.

### Verified

- Deployed the operational controls as an immutable review release on
  `rasp-3mm` and kept Core, Web, Agent and update-helper healthy.
- Physically exercised automatic Stable and Beta checks, cache persistence,
  zero-failure retry state and out-of-window apply rejection.
- Completed the physical in-application Beta OTA path from
  `v0.3.0-beta.4` to `v0.3.0-beta.5` on `rasp-3mm`.
- Preserved the persistent device identity and retained `v0.3.0-beta.4` as
  the rollback release while Core, Web, Agent and update-helper passed health
  checks.
- Confirmed the persisted update operation reached `succeeded` and a fresh
  post-install Beta catalog check returned `up_to_date` with no retry failure.

### Documentation

- Replaced the legacy project README with the current product, development,
  Raspberry deployment and release overview.
- Documented the release/version policy and the accepted Beta OTA workflow.

## [0.3.0-beta.4] - 2026-08-26

### Changed

- Published the follow-up Beta release used to exercise the complete
  in-application update path from an already channel-aware installation.

### Verified

- Published a complete Beta release for all three supported architectures.
- Completed the physical OTA path from `v0.3.0-beta.3` to
  `v0.3.0-beta.4` on `rasp-3mm`.
- Preserved the device identity and `v0.3.0-beta.3` rollback target while
  Core, Web, Agent and update-helper passed health checks.

## [0.3.0-beta.3] - 2026-08-26

### Added

- Explicit Stable, Beta and Test update-channel selection in the
  administrator API and System Updates interface.
- Channel-aware release discovery, manifest validation, staging and
  privileged apply-time revalidation.
- Release manifest channel assignment for stable, beta and test versions.

### Changed

- Preview releases remain subject to the same checksum, architecture,
  dependency, preflight and explicit-approval requirements as stable updates.
- The privileged update helper is refreshed when an immutable release changes.

### Fixed

- Preserved the tag-only release trust boundary after a rejected manual
  workflow-dispatch experiment.

### Verified

- Used this version as the manually installed Beta bootstrap for the first
  channel-aware OTA acceptance test.

> Tags `v0.3.0-beta.1` and `v0.3.0-beta.2` did not produce accepted
> published releases. They remain immutable historical tags and are
> intentionally omitted as release sections.

## [0.2.3] - 2026-08-26

### Changed

- Published the corrected OTA acceptance release after the protected-home
  installer fix.

### Verified

- Completed staged OTA installation and rollback acceptance on the physical
  Raspberry device.

## [0.2.2] - 2026-08-26

### Fixed

- Allowed OTA installation to create its isolated build environment while the
  service account uses a protected home directory.

## [0.2.1] - 2026-08-26

### Changed

- Prepared the first physical OTA acceptance candidate.

### Known issues

- Installation exposed the protected-home build-environment defect corrected
  in `v0.2.2`.

## [0.2.0] - 2026-08-26

### Added

- Deterministic, architecture-specific release artifacts for `aarch64`,
  `armv7l` and `x86_64`.
- GitHub release catalog checks and strict update-manifest validation.
- Download, checksum, size, archive identity, dependency and preflight
  verification before staging.
- Separate explicit administrator approval for applying a staged update.
- A privileged systemd update helper with immutable activation, health checks
  and rollback.
- System Updates UI for status, review, staging, approval and operation
  progress.

## [0.1.0] - 2026-08-26

### Added

- Core API and Vue application with authentication, roles, settings, dynamic
  menus, dashboards and extension management.
- Persistent Agent identity, privacy-conscious inventory, device pairing,
  heartbeat, commands, desired-state reconciliation and offline outbox.
- Headless provisioning with Wi-Fi rollback and Standalone, Hub and Node
  runtime roles.
- Open setup-only access point and browser-based phone provisioning.
- Manifest-driven mock and native Raspberry GPIO input capabilities.
- Declarative runtime extensions with authenticated CRUD, dynamic routes and
  data-preserving disable, rollback and uninstall.
- Reviewed compiled Vue extensions with content-addressed artifacts, dynamic
  widgets, editors and routes.
- AI-assisted automation and Extension Builder workflows with Groq and
  OpenRouter provider support.
- Editable extension projects, automatic patch versions, reviewable changes
  and incremental build/install/rollback.
- Immutable Raspberry systemd deployment, state backups, automatic recovery
  and dry-run-first release/backup retention.
- First-boot preflight and Raspberry installation procedure.

### Verified

- Real compiled Clock and DoorSensor widgets on the Raspberry dashboard.
- Physical BCM17 input transitions through Agent, Core and a generated GPIO
  lamp widget.
- Service recovery after reboot and Agent buffering during a controlled Core
  outage.
- Deployment rollback and bounded storage retention on `rasp-3mm`.

[Unreleased]: https://github.com/ldobranov/3mm/compare/v0.3.0-beta.8...HEAD
[0.3.0-beta.8]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.8
[0.3.0-beta.7]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.7
[0.3.0-beta.6]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.6
[0.3.0-beta.5]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.5
[0.3.0-beta.4]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.4
[0.3.0-beta.3]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.3
[0.2.3]: https://github.com/ldobranov/3mm/releases/tag/v0.2.3
[0.2.2]: https://github.com/ldobranov/3mm/releases/tag/v0.2.2
[0.2.1]: https://github.com/ldobranov/3mm/releases/tag/v0.2.1
[0.2.0]: https://github.com/ldobranov/3mm/releases/tag/v0.2.0
[0.1.0]: https://github.com/ldobranov/3mm/releases/tag/v0.1.0
