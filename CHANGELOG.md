# Changelog

All notable changes to 3mm are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/) while remaining
pre-1.0.

## [0.3.0-beta.41] - 2026-10-07

### Added

- Theme Customization now combines the selected theme's editable appearance
  controls and live button/form/dialog/table samples, using its real local font
  and independent light/dark palette preview. Save/Discard/Reset remain explicit.
- Optional, closed v2 `customization_options` lets packages declare editable
  variants and semantic colors. Core and browser reject unsupported choices;
  existing v1/v2 packages without the declaration remain compatible. New packages
  using this field require beta.41 or newer Core.
- Read-only administrator installed-package preview with temporary verified
  resources, Cancel cleanup and exact-package Apply. Public asset serving remains
  selected-only; ordinary UI preview bookmarks redirect to Theme Customization,
  while explicit built-in recovery remains protected and independent.
- Carries the merged, physically accepted generic Public Web Runtime foundation
  described under the historical test.1 source section below, without bundling a
  Shop, business extension or concrete visual theme.

### Fixed

- Idle/focused tabs retain the last verified theme, preferences and resources on
  failed or invalid appearance refreshes. A verified explicit fallback is still
  honored; authentication is not cleared and underlying DNS faults are not hidden.
- Valid encoder-produced WOFF2 zero alignment padding is accepted within the
  existing bounded container checks. Excess, nonzero or misaligned padding and
  truncated/unsafe resources remain rejected.

### Compatibility and verification

- V5 was approved after two actual separate theme packages and a licensed local
  font with Bulgarian glyphs passed isolated UI acceptance. The integrated editor
  was checked in desktop/mobile light/dark and EN/BG, including Save and reload.
- All 190 frontend tests, TypeScript checking and the production build passed.
  The complete local Linux/Python 3.14 suite passed 1,438 tests; six route tests
  then passed with temporary sockets on the Linux filesystem rather than NTFS.
  One opt-in HTTPS acceptance test remains skipped. GitHub repeats the complete
  suite on Python 3.13 and gates publication on reproducible full-profile/ARMv6
  Node builds. Physical upgrade/restart/rollback/portable-theme recovery remain V8.
- No new database migration, runtime dependency, device protocol or Application
  SDK change. Child Center, theme ZIPs and local/generated artifacts are excluded.

## [0.3.0-test.1] - 2026-10-07

### Added

- Milestone 19 Public Web Runtime foundation: application extensions can declare
  bounded GET/HEAD public routes and return validated HTML, JSON, XML, plain-text,
  redirect and explicit error responses without registering framework routers in
  Core.
- A Core-owned public route registry with deterministic specificity and
  cross-extension conflict rejection. Route ownership is reconstructed from
  active application state and follows activation, disable, rollback, uninstall
  and restore instead of using a second persistent routing database.
- A separate socket-activated public web surface backed by a local Core
  Unix-socket gateway. The public process uses a dedicated `3mm-public` identity,
  loopback-only listener, private network/device namespaces and no direct access
  to Core database, environment secrets or update-helper mutation paths.
- Neutral `org.3mm.public-web-reference` acceptance package covering root and
  parameterized HTML pages, XML and text resources, permanent redirects, 410 and
  generic 404 behavior without shop or SEO semantics.

### Security and compatibility

- Public requests forward only a bounded allowlist of non-credential headers.
  Authorization, administrator cookies and internal transport headers are not
  exposed to application handlers.
- Public responses use allowlisted content types/status codes/headers, bounded
  response sizes and fail-closed validation for malformed, slow or unavailable
  application services.
- The existing administrative SPA remains on ports 80/8080 and is independent
  from the public listener. Existing Application Extension packages without
  public HTTP routes remain compatible; no database migration or Agent protocol
  change is required.

### Verification

- Raspberry P6 exposed and the branch fixes a production-only systemd wiring
  gap: Core now owns a dedicated `/run/3mm-public-web` runtime directory and
  publishes the bounded gateway socket there for the isolated `3mm-public`
  identity. The installer writes the same socket path into the persistent Core
  environment, preventing stale deployment configuration from overriding the
  systemd boundary. No Core state directory, database or secret permissions are
  widened.
- Immutable full deployments now reconcile application services from the
  persisted `enabled + active` installation state after Core activation, and
  do the same on rollback. This preserves all Application Extension runtimes
  across deploys without reviving disabled or failed installations.
- Milestone P0-P5 Python/frontend CI passed on the focused branch through
  commit `94567a2b`; CI run 129 passed for the final accepted runtime commit
  `996760f6`.
- Raspberry P6 passed on a Pi 3B+ / Debian 13 using immutable release
  `996760f669fd-20261007065735`. HTTP GET/HEAD, redirect/404/410, lifecycle
  disable/re-enable, fail-closed service failure, Admin/Core independence,
  socket activation, idle exit, resource impact and isolation all passed.
- The neutral reference package SHA-256
  `5007ae614b1061d944a6c4f5e3410671b613219e3a32acafca8753bc3a1b6439`
  matched the stored package bytes. Public-process RSS was 36,460 KiB after a
  successful request; the process exited after the 60-second idle window while
  the listener socket remained active.

## [0.3.0-beta.40] - 2026-10-05

### Added

- Installed-theme color editors in Settings → Theme Customization: the 11 v1
  legacy colors or all 17 v2 semantic colors, independent light/dark palettes,
  local preview, explicit Save/Discard and per-palette restoration.
- Sparse version-scoped overrides through the existing audited admin endpoint.
  Original ZIPs, inherited values, built-in colors, branding and theme assets
  remain unchanged. V2 effective palettes retain the package contrast policy;
  invalid restored overrides fall back safely.

### Fixed

- Public uploaded logos are now served from persistent `UPLOADS_DIR` on the web
  origin, including ports 80/8080, instead of returning the SPA or a missing asset.
  Directory listing, traversal and symlinks are rejected; release permissions
  and private storage remain unchanged.
- Image editing preserves URL parameters/data URLs, reloads an unchanged logo
  when reopened, ignores late image callbacks and disables Save until decoding.
  Replacement uploads clear stale errors and release temporary object URLs.

### Compatibility and verification

- No database migration, protocol, SDK, Node runtime or dependency change.
  Existing preferences without color overrides and both theme APIs are compatible.
- Focused backend/web and frontend checks, type checking, production build and
  isolated mobile light/dark color-editor review passed locally. Complete Linux
  and frontend checks plus reproducible Hub/ARMv6 Node builds gate publication.
  Raspberry logo/theme acceptance remains separate from local review.
- Child Center, concrete theme ZIPs and local/generated artifacts are excluded.

## [0.3.0-beta.39] - 2026-10-05

### Added

- Saved Theme Customization controls for navigation, density, button/card
  variants and readable custom header colors, with temporary preview, explicit
  Save, Discard and Reset. Preferences are audited, administrator-managed and
  scoped to an exact package SHA-256 or built-in appearance.
- Shared backend public-asset storage based on the existing `UPLOADS_DIR`, with
  bounded namespaces, safe relative paths and atomic replacement of uploads.

### Fixed

- Header Customization now owns branding text, translations and logo, while
  visual header controls live in Theme Customization. Branding saves do not
  overwrite colors; personal light/dark remains a separate user preference.
- Settings image upload, list, folder, rename and delete use persistent
  `/var/lib/3mm/core/uploads`, not an immutable release directory. Existing image
  URLs and authentication remain; form/query directory inputs share validation.
  A failed write preserves the previous logo, and validation retains status 400.
- UI recovery can clear built-in layout overrides without erasing branding,
  translations, menus or the stored overrides for other installed themes.

### Compatibility and verification

- Existing Settings rows store preferences; no database migration, protocol,
  SDK, Agent runtime or dependency change. Theme ZIPs and release protections
  remain immutable; private extension storage is unchanged.
- Complete isolated Linux suite: 1364 passed, one opt-in HTTPS acceptance test
  skipped. Frontend suite, type checking and production build passed locally.
  Checks include preference authorization/validation and uploaded-logo portable
  export/import/restore with a new key. Python 3.13 CI and reproducible Hub/ARMv6
  Node builds gate publication; local review is not deployed Raspberry acceptance.
- Child Center, concrete themes and local/generated artifacts are excluded.

## [0.3.0-beta.38] - 2026-10-05

### Fixed

- Initial page rendering waits for the selected appearance, saved mode, header
  settings and verified theme resources before mounting navigation and content.
  A neutral loading screen replaces the legacy-layout flash during refresh.
- Startup waiting is bounded to eight seconds. Cancelled or late appearance
  responses cannot overwrite the fallback; settings failures retain the browser's
  existing light/dark mode and language, without clearing authentication.
- System Updates final confirmation now distinguishes the installed version from
  the exact staged version. Missing installed metadata has an explicit fallback;
  cached catalog results no longer replace freshly read installed-release metadata.
- English and Bulgarian labels identify both versions. Existing installation
  acknowledgements, approval identity and maintenance-window checks are unchanged.

### Verification and compatibility

- All 161 frontend tests (including 44 focused checks), type checking and production build passed locally;
  isolated desktop/mobile light/dark review confirmed delayed appearance startup
  and separate current/target versions without executing a real update.
- Complete frontend/Linux checks and reproducible Hub/ARMv6 Node builds gate
  publication. No backend, database migration, Agent, SDK, protocol or deployment
  change. Concrete themes and Child Center remain outside this Core release.

## [0.3.0-beta.37] - 2026-10-05

### Added

- Theme Platform V0–V4: closed Design API 2 with shared backend/browser defaults,
  semantic light/dark tokens, bounded typography/spacing/density and component
  variants, plus an adapter preserving existing v1 palette/radius values.
- Native Vue Button/Dialog and reusable scoped UI classes, with an administrator
  component preview. An opt-in Core-owned sidebar/top-navigation shell and mobile
  drawer retain the existing menu registry, roles, localization and route behavior.
- Strict `theme-extension v2` ZIP support in the existing Extensions installer,
  catalog and lifecycle, without a second upload screen or theme compiler.
- Declared WOFF2/PNG/WebP assets with canonical paths, hashes, byte/dimension
  budgets and bounded container checks. Only the selected, enabled package serves
  assets; the browser loader uses timeouts, cleanup and safe fallback.
- Administrator recovery at `/settings/ui-preview?recovery=1` can permanently
  clear theme selection independently of broken installed styling.

### Compatibility and limits

- V1 themes and built-in/custom appearance remain supported. An update does not
  activate the v2 shell or change the selected version. Saved Header/Menu content,
  translations and overrides remain; unrelated settings and sessions are not reset.
- No database migration, runtime dependency, Agent/deployment redesign, device
  protocol or Application SDK change. Concrete theme packages, including Graphite
  Mint, and Child Center remain outside this Core commit/release.
- Font/WebP validation checks containers, not every glyph or codec property;
  final browser decoding may fall back. Licensed font/Cyrillic acceptance, a second
  reference theme, installed-package preview and screen/extension UI migration
  remain V5–V7. Live upgrade/reset/portable recovery acceptance remains V8.

### Verification

- 96 focused backend theme tests and all 151 frontend tests passed locally;
  frontend type-check/build and isolated desktop/mobile light/dark/BG/EN browser
  review passed. A local encrypted portable export/import/restore verifies v2
  selection, package bytes and asset serving with a new recovery key.
- Complete clean-source Linux/frontend checks and reproducible Hub/ARMv6 Node
  artifact builds gate publication through the existing workflows. Local preview
  and recovery checks are not a claim of deployed-device acceptance.

## [0.3.0-beta.36] - 2026-10-04

### Added

- Theme Platform T1–T3 with a closed `theme-extension v1` contract: bounded
  localized names, light/dark colors and radii, without arbitrary CSS, JavaScript,
  assets, routes or runtime permissions.
- Immutable theme ZIP validation through the existing module package upload,
  administrator-only audited enable/disable/delete and exact-version selection.
- Additive Alembic migration `a7bf06b7c8d9` for theme lifecycle and selection;
  existing packages, settings and historical backup upgrades remain supported.
- Public safe appearance projection and a Core-owned browser token adapter.
  Missing, corrupt, disabled or removed packages fall back to built-in/custom
  appearance without changing authentication or existing Header/Menu settings.

### Changed

- Extensions owns the single ZIP upload and theme version/lifecycle cards.
  Settings → Theme Customization only selects enabled themes or built-in appearance.
- Light/dark switching, English/Bulgarian labels and existing custom colors remain
  supported. Theme packages do not start an Agent service or invoke the compiler.
- Product roadmap records the separate reference-theme and future Embedded Nodes
  extension stages; neither concrete design nor firmware is bundled.

### Verification and compatibility

- Focused package, lifecycle, authorization, migration/recovery and frontend
  checks passed locally, including type-check/build and isolated desktop/mobile
  light/dark browser review. Full clean-source Linux checks and reproducible
  Hub/ARMv6 Node builds gate publication in the release workflow.
- Device protocol 1.0 and Application SDK 1.3 are unchanged. Child Center and
  local/generated artifacts are excluded. Real reference-theme, deployed-device
  and portable theme recovery acceptance remain separate work.

## [0.3.0-beta.35] - 2026-10-04

### Fixed

- Historical portable-recovery fixtures seed the schema actually present in the
  backup, verify the current Alembic head and compare every original column after
  additive upgrades. Coverage retains old-schema restore/rollback and adds current
  explicit capability selection preservation; no recovery migration is bypassed.
- Node OTA regression tests use genuinely registered capability commands to verify
  pending-work rejection, update-time mutation blocking and terminal unblocking.
- Historical oversized-command tests isolate size rejection from missing capability
  authority and retain both never-dispatched and already-dispatched evidence checks.

### Compatibility and publication

- Includes all C10–C14 and installer changes documented under beta.34. This correction
  changes test fixtures and release documentation only, not Core/Agent behavior,
  protocol 1.0, Application SDK 1.3 or database migrations.
- The beta.34 tag failed six Python regression cases in CI and Release before asset
  publication. It remains an immutable failed attempt; beta.35 is a new candidate.
- Forty focused recovery, command-history, Node OTA and Core-route checks passed on
  WSL/Linux with Python 3.14. Unix socket checks used an isolated Linux temporary
  path, not the Windows-mounted checkout. The complete suite was also exercised;
  final Python 3.13 CI and tag-driven artifact publication remain required.
- Real Hub/Zero/Fleet acceptance remains pending successful artifact publication.

## [0.3.0-beta.34] - 2026-10-03

> Failed publication candidate: no release assets were published. The changes below
> are carried forward by beta.35 without moving or reusing this tag.

### Added

- C10 common logical Device Protocol operations, replaceable transport boundary
  and compatible HTTP adapter; no MQTT/WebSocket implementation or Fleet dependency.
- C11 bounded versioned capability contracts, exact action/schema validation and
  contract-digest checks at queue, dispatch and local runtime boundaries. Linux
  modules and the independent firmware mock serve the same application binding.
- C12/C13 installation authority binding, signed management, explicit reassignment
  and recovery, separate connectivity/lifecycle and generic reset policies.
- C14 registry v3 distinguishes supported offers, Core-owned selection and fresh
  availability. Provider reports v2 cannot automatically activate new firmware
  capabilities; health-aware commands wait within their original expiry.

### Fixed

- Wired-only Linux/VM first boot initializes Standalone without requiring a Setup
  AP, creates required service groups and starts the local Agent safely. Upgrade
  rollback restores the previous service set; identity and pairing are preserved.
- Inventory-only capabilities cannot authorize raw commands or application binding.
  Stale/unhealthy providers retain configuration without rewriting dispatched
  evidence or replaying uncertain physical effects.

### Compatibility and verification

- Protocol 1.0, HTTP `/api/v1`, Application SDK 1.3 and existing Node Update remain.
  Legacy providers retain selection until opt-in; unknown health is not fabricated.
- Additive Alembic `859de4f5a6b7` and `96aef5a6b7c8` preserve existing identities,
  credentials, modules, registrations and desired state. Once explicit capability
  selection exists, downgrade requires the pre-upgrade database backup: dropping
  the selection column would silently activate unapproved offers and is refused.
- C10–C14 plus installer integrated local gate: 68 passed. C14/C11/provider/security
  regression gate: 61 passed; separate transport/runtime/migration gate: 52 passed.
  Suites overlap. Frontend type checking and production build passed. Linux CI
  still runs the complete release checks before publication.
- Prepared for full-profile Hub and ARMv6 Node assets. Real mixed-version
  Hub/Zero/Fleet acceptance remains pending; no real ESP firmware, concrete
  business extension package or business data is included.

## [0.3.0-beta.33] - 2026-10-03

### Added

- Platform-neutral inventory schema 2, legacy schema 1 ingestion and generic
  inventory presentation. Embedded reports need no invented Linux values.
- One provider-neutral capability query for installed Agent modules and
  device-owned native/firmware providers, with revision, conflict and Core-owned
  disable semantics. Standalone, local Agent, Hub/Fleet and applications share it.
- Device-authenticated schema discovery and runtime feature advertisement,
  separate from capabilities. Unsupported new work is rejected before dispatch;
  application execution still requires the existing one-time live permit.
- Independent mock embedded reference client with durable identity, receipts,
  bounded outbox and optional application execution permits; no Agent runtime
  dependency, real firmware, GPIO or firmware OTA implementation.

### Fixed

- Bounded device JSON/HTTP payloads, fresh credential revocation checks,
  content-bound Agent receipt replay and protection against device-spoofed Core
  audit events. Pending outbox work is retained instead of silently evicted.
- Historical invalid/oversized state, commands and receipts remain preserved
  with explicit recovery conflicts; they do not trigger destructive cleanup or
  automatic replay of uncertain execution.

### Compatibility and verification

- Additive Alembic revisions `637bc2d3e4f5` and `748cd3e4f5a6` add provider and
  runtime feature tables. Existing identities, credentials, module installations
  and desired state are preserved without re-pairing. Protocol 1.0, HTTP `/api/v1`
  and Application SDK 1.3 remain compatible; legacy unadvertised support is unknown.
- New Linux inventory stays opt-in/negotiated. Before downgrading Core, stop
  schema-2/provider clients or return Linux clients to schema 1; an older release
  cannot restore a backup containing unknown newer migration revisions.
- C8 migration, mixed-version portable restore/rollback and legacy recovery gate:
  61 passed, one POSIX-only check skipped on Windows. C9 local Linux/mock/application
  and dependency-boundary gates: 56 passed. Detailed limits are in the C0–C9 reports.
- Hub/Zero/Fleet deployment acceptance remains pending. Publication builds the
  full-profile and ARMv6 Node packages; it does not update devices. No Child Center
  package or business data is included.

## [0.3.0-beta.32] - 2026-10-02

### Added

- Generic installation peer v2 / Application SDK 1.3: bounded opaque application
  intent and normalized exact consent selection, revision and hash are bound
  into the signed start, both possession proofs, pending receipt and credential.
- Verified metadata is available before approval through the receiver bootstrap
  handler and SDK/admin inbound reads. Approval checks generation plus the
  reviewed metadata revision/hash, including idempotent approval retries.
- Shared v2 schemas, administrator consent-create API, explicit capability
  discovery and receiver manifest version selection; no silent v1 downgrade.

### Changed

- Every actual v2 consent change, including reduction, clears outgoing credentials
  and cached reports, stops export and requires a new receiver approval generation.
  A reordered but identical selection is an idempotent no-op.
- V2 receivers reject projections whose revision or selected fields/Nodes differ
  from the reviewed consent. Late replies and old bootstrap callbacks remain fenced.
- SDK runtime 1.3 continues supporting manifests 1.0–1.2 and legacy peer v1 wire
  behavior. Applications embedding older protocol parsers must accept the actual
  G1 runtime SDK version; see the v2 compatibility guide.

### Compatibility and verification

- No new database migration. Existing peer JSON stores v2 metadata; backup restore
  retains its audit record but quarantines trust, credentials and cached reports.
- 154 targeted/regression tests and five additional malformed-credential cases
  passed on Windows; the production frontend build and diff checks passed.
  Real v2 TLS/Linux/public-ingress acceptance is not claimed.
- Intent issuance, expiry/reuse, organization mapping and Owner authorization
  remain receiving-application rules, not concrete business logic in Core.
- Prepared for tag-driven Hub and ARMv6 Node artifact publication. Node Update
  checks are retained from beta.31; no Node pairing, hardware authority, live
  deployment or Child Center package changes are included.

## [0.3.0-beta.31] - 2026-10-02

### Added

- Stable Core installation identity and bounded Ed25519 proof of possession,
  with encrypted private keys, lazy creation and actual Core version checks.
- Application SDK 1.2 installation-peer enrollment, separate local consent and
  receiver approval, expiring credentials, revocation, replay protection and
  durable completion/report/rotation retries. SDK 1.0/1.1 services remain supported.
- Explicitly selected installation/Node status projections over verified HTTPS;
  machine audiences cannot acquire human permissions or physical command authority.
- Read-only administrator Node Update check for the latest official release and
  the last confirmed OTA version. Missing or uncertain history stays unknown;
  preparing an already confirmed selected release does not download it again.
- General product plan and installation identity/peer integration contracts.

### Fixed

- Valid module IDs containing the `3mm` component now work in peer consent requests.
- Registration/login/profile logs exclude credentials, tokens, decoded claims and
  raw exception details, without changing authentication or session behavior.
- Peer HTTPS transport dependencies are included in production requirements,
  not only development installations. Node dependencies remain minimal.

### Compatibility and verification

- Alembic revisions `4159a0b1c2d3` and `526ab1c2d3e4` add identity and peer tables.
  Recovery preserves the identity/key pair but quarantines peer trust in both
  directions; restored links require fresh approval. Retire the source before
  running its restored replacement; identical active SD/database clones are unsupported.
- Release preparation: 199 scoped tests passed, with two Linux/opt-in tests
  skipped on Windows; the production frontend build passed. Isolated Raspberry
  HTTPS/Unix-socket acceptance also passed. Four Linux acceptance/schema tests and eight authentication
  logging tests passed without changing the live Hub, Zero or application data.
- Cloud Manager consent/ownership UI, reporting schedules and public HTTPS ingress
  remain separate integration work. No concrete business extension or automatic
  cloud connection is included; local Hub/Node operation remains independent.
- Node check uses Hub OTA history, not a new live Agent version contract. Manual
  installs and unconfirmed results cannot be advertised as up to date.

## [0.3.0-beta.30] - 2026-10-01

### Fixed

- Device state API now restores UTC timezone information when SQLite returns a
  naive `reported_at` timestamp. Fleet no longer interprets fresh Node reports
  as several hours old and incorrectly disables GPIO configuration.

### Verified

- 29 relevant device-state, registry and Node OTA tests passed locally.
- Physical GPIO pin reconfiguration remains to be verified after deployment.
- beta.29 -> beta.30 is the first physical OTA transition that can validate the
  beta.29 Node startup-order fix, because the OTA worker uses the installer from
  the source release.

## [0.3.0-beta.29] - 2026-10-01

### Fixed

- Node immutable deployment now starts the privileged update helper and recovery
  services before activating the new Agent. This prevents Agent OTA outcome
  reconciliation from racing helper startup after release activation.
- Full-profile Hub deployment retains its existing activation order.

### Verified

- 142 scoped Node OTA and installer tests passed; two POSIX-only security checks
  were skipped on the Windows development host.
- Physical beta.26 -> beta.28 OTA installed and activated beta.28 successfully,
  preserving Agent identity and pairing, but final verification remained
  `unknown / postflight_unverified` because of the helper startup race.
- Final durable `succeeded` acceptance remains pending. Because the OTA worker
  runs the installer from the source release, beta.29 must first be installed
  on the test Node before validating a subsequent OTA release.

## [0.3.0-beta.28] - 2026-10-01

### Fixed

- Node OTA approval now considers only an enabled `gpio.digital.control`
  capability. Historical stale state from a disabled GPIO module no longer
  blocks installation.
- When `gpio.digital.control` is enabled, OTA still fails closed unless a fresh
  state report exists and every reported output is confirmed inactive.

### Verified

- 105 scoped Node OTA tests passed; two POSIX-only security checks were skipped
  on the Windows development host.
- Physical Node OTA acceptance remains pending until a real beta.26 Node
  completes an update through Fleet with a durable final `succeeded` outcome.

## [0.3.0-beta.27] - 2026-10-01

### Verification target

- No behavioral OTA code change from beta.26. This release exists as the first
  physical signed Node OTA target for validating the beta.26 Hub/Agent path.
- Physical acceptance is not claimed until the Node reports a durable final
  `succeeded` outcome after installation.

## [0.3.0-beta.26] - 2026-10-01

### Added

- Explicit administrator-approved Node runtime apply with a short-lived,
  device/operation/release/hash-bound Ed25519 Hub authorization. The privileged
  helper and detached worker verify independently pinned root trust before execution.
- Root-only one-time Hub key/device binding bootstrap, no silent key replacement,
  and signed-helper readiness reported to Core before remote apply is permitted.
- Durable Agent tracking and independent authenticated final installation reports,
  distinct from successful command handoff. Restart/offline reporting never
  repeats installation; unknown outcomes block further updates.
- Node OS OpenSSL prerequisite and trust files/tools in the minimal artifact,
  without adding Core or native cryptography Python dependencies to Zero.

### Compatibility and limits

- No database migration; existing command JSON retains handoff and outcome
  separately. Existing prepare/status APIs remain compatible.
- Both Hub and Node need a newly published signed-path bootstrap release and an
  explicitly verified Hub key pin. Beta.25 alone does not implement signed apply.
- No deployment, Fleet OTA UI or physical OTA acceptance is claimed by this change.

## [0.3.0-beta.25] - 2026-10-01

### Added

- Separate root Node update helper, bounded root staging and detached immutable
  installer worker with durable success/rollback/unknown outcomes.
- Official Node catalog and verified Hub staging, authenticated per-device archive
  delivery, Agent prepare command and persistent prepare status.
- ARMv6 Node helper packaged alongside full Hub assets in the published release.

### Limits

- Prepare/execution foundation only: no signed Hub apply authorization, remote
  apply/final-report integration or Fleet OTA UI in this published version.
- Physical Node OTA acceptance remains pending; bootstrap publication is not proof
  that a real device was updated successfully.

## [0.3.0-beta.24] - 2026-09-30

### Added

- Generic Agent GPIO configuration command and reported revision, consumed by
  the optional Fleet 0.1.6 extension. One inactive-LOW, active-high output can be
  configured without SSH, using mock or gpiod on the reviewed Zero W / Pi 3B+ boards.
- BCM/physical-pin mapping, disabled-module and fresh-state checks, explicit
  wiring approval, persisted configuration, inactive startup and rollback.
- ARMv6-compatible GPIO package metadata, output-only reference package and
  lifecycle-probe fixture. Core remains independent of concrete extension names.
- Fleet GPIO operator guide and local-first business delivery plan.

### Fixed

- Module install/disable accepts scoped request identities and fresh lifecycle
  episodes, allowing repeat disable/re-enable without replaying an old result.
- GPIO configuration uses the durable physical-command journal and bounded
  authorization; uncertain execution is not automatically retried.

### Compatibility and acceptance

- Update both Hub/Core and Node/Agent, then upload Fleet 0.1.6 separately. No
  database migration, credential reset or change to extension business data.
- The earlier GPIO17 LED test passed with environment settings. The new Fleet
  configuration flow still requires physical acceptance; Milestone 13 stays open.
- Older Agents ignore the managed configuration file. Review hardware and the
  previous environment mapping before downgrading a configured device.

## [0.3.0-beta.21] - 2026-09-30

### Fixed

- Allow only the exact Setup AP directory preparation in the installer's
  architecture test; direct network mutations remain forbidden. Tag beta.20
  failed this test and published no assets; beta.21 includes the Node work below.

### Added

- Minimal Node installation profile for Raspberry Pi Zero W ARMv6 / Python 3.13,
  selected with `install.sh --profile node`, without Core, database or npm.
- Separate Node release artifact and manifest, with an offline binary wheelhouse,
  recorded source/output hashes and reviewed piwheels alias metadata correction.
- Core-independent network recovery service, immutable activation and rollback.
- Node-only Setup role selection and rejection of full-runtime roles before any
  network mutation. Existing full-profile installation remains the default.

### Verified and limits

- 64 focused tests passed. Real installation and an injected post-health failure
  rollback passed on Zero W with Wi-Fi retained; identity and environment survived.
- Clean-media phone/AP onboarding is pending. Durable Hub pairing and permanent
  Node web administration remain separate Fleet stages; installation is not pairing.
- No concrete business extension, Hub deployment or physical GPIO operation changed.

## [0.3.0-beta.19] - 2026-09-24

### Fixed

- Automations and System updates are no longer automatically appended to the
  header. Manually configured links can be removed through Menu Editor without
  returning on refresh. Existing saved menu entries are not deleted by the update.
- Both pages remain available at `/automations/proposals` and `/system/updates`,
  with their existing administrator guards. Dynamic extension navigation is unchanged.

### Verified

- Ten focused navigation tests and the production frontend build passed locally.
- No backend, database, payment or concrete extension changes are included.

## [0.3.0-beta.18] - 2026-09-15

### Fixed

- Application jobs wait for authenticated host readiness after startup/OTA.
  Proven pre-send failures release only the owned claim and retry with persisted
  5–30 second backoff, preserving the occurrence's idempotency identity.
- Typed transport phases distinguish connect failure from partial send, lost
  responses and invalid output. Uncertain executions remain quarantined; old
  unknown records are never automatically unlocked.
- Lifecycle and claim ownership are checked again after readiness. Diagnostics
  distinguish waiting for the service from execution requiring manual review.

### Verified and compatibility

- Twenty focused local tests passed, plus six real Unix-socket tests on Raspberry
  in isolation. No production service, domain record or physical output changed.
- No new migration; concurrency limits and physical deadlines are unchanged.
  Existing unknown jobs still require explicit administrator reconciliation.

## [0.3.0-beta.17] - 2026-09-15

### Added

- Due-time application job scheduling with a one-second discovery bound and two
  executor threads per Core process, using separate database sessions.
- Database-atomic claims serialize jobs per installation across Core processes.
  Renewable leases outlive short job intervals; uncertain/expired claims are not
  automatically retried. Restore fences old executor completions.
- Scheduled/start time, duration, lateness and safe error categories in existing
  operational diagnostics. Audited administrator resolution requires a disabled
  application and explicit confirmation of external-outcome review.
- Migration `2f37e8f9a0b1` preserves legacy in-flight jobs as unknown outcomes.

### Verified and compatibility

- Seventeen focused tests cover scheduling, concurrent claims, lifecycle,
  catch-up, restore, resolution authorization and migrations.
- Isolated Raspberry mock test: fast-job gaps 4.980/4.992/5.034 seconds alongside
  a six-second job; benchmark process averaged 3.24% of one CPU core.
- Event retries and physical command deadlines are unchanged. No concrete
  extension or production Raspberry state is changed by this release task.
- Stop old Core processes during upgrade; reconcile uncertain jobs before
  resuming or rolling back to a scheduler without these safeguards.

## [0.3.0-beta.16] - 2026-09-15

### Added

- Optional UTC-normalized `not_after` command deadline in Core/SDK. Delayed
  submissions cannot restart the original authorization lifetime; identical
  retries preserve expiry and changed deadlines conflict.
- Signed, read-only `command_lookup(request_id=..., binding_id=...)` for lost
  submit replies. Lookup uses the original device association, not the current
  configuration, and reports ambiguous historical matches explicitly.
- Disabled installations may read their own invalidated command history through
  authenticated lookup without regaining execution authority. Restore preserves
  discoverability without replaying commands.

### Compatibility and verification

- Existing relative-TTL callers and beta.15 command history remain supported;
  no new database migration or concrete extension change is required.
- Forty focused tests cover deadlines, conflicts, expiry, signed lookup,
  original device bindings, restore and lookup racing an uncommitted submit.
- A not-found lookup is only a snapshot: callers must synchronize the submitting
  worker and respect the original deadline before clearing uncertain work.

## [0.3.0-beta.15] - 2026-09-13

### Added

- Application SDK command submit/status through the existing signed platform
  socket and device queue. Packages declare device bindings, exact actions,
  bounded argument schemas and a maximum ten-second authorization lifetime.
- One-use live Agent execution authorization, scoped to the active installation,
  package, generation and approved target device; no administrator token is used.
- Generic `access.passage.v1` sensor evidence with command/generation, binding,
  direction and sensor correlation. Duplicate confirmations and delivery to an
  unrelated installation are rejected.
- Migration for application command generations and correlated requests.

### Fixed

- Queue-delivered capability actions persist their attempt before invoking the
  driver. An interrupted attempt remains unknown and is never automatically
  repeated; conflicting reuse of a command identity is rejected.
- Disable/update invalidate outstanding application authority. Restore rotates
  generations and cancels both application and direct pending capability commands.
  Old passage deliveries cannot cross the restored generation.

### Limits

- Driver success is not proof of passage or exactly-once physical execution.
  Compatible passage adapters, extension domain transitions and real two-device
  acceptance tests remain separate work. No concrete extension is changed.
- Core and Agent must both be updated. Already-issued in-flight permits cannot
  retract a hardware action; see the command contract for recovery and rollback.

## [0.3.0-beta.14] - 2026-09-13

### Fixed

- Correct the checkbox element type in the new access-management test. Tag
  `v0.3.0-beta.13` failed frontend type checking and published no release assets;
  this revision contains the complete access changes below.
- Ignore expired and NONE dashboard grants in listings, direct reads and widget
  mutations. Resolve dashboard-list administrator status from the current user
  record instead of stale JWT role claims.
- Restrict Core Users, Settings and Extensions management screens to admins.
  Public dashboards and dynamically registered application routes are unchanged.

### Added

- Users now includes custom role/group creation, direct user-role membership,
  user-group membership and group-role assignment, with immediate audited saves.
- Shared live resolution combines direct application grants with personal roles
  and group roles. Application access shows the origin of effective permissions.
- Resource-scoped role grants for application permissions and dashboard widget
  read/edit/delete operations; NONE remains absence of a grant, not a deny.
- Migration and cleanup for scoped grants, including safe application uninstall.
- Documented explicit delegated application management through permission-gated
  operator routes and operations. Existing administrator-only declarations stay
  system-admin-only; extensions must opt in and update their own interface.

### Compatibility

- No extension business logic is included. System settings, user management,
  package lifecycle and recovery are not delegated by custom roles.
- Dashboard ownership, sharing and bulk layout remain owner-only. Legacy
  role/group permission tables are not automatically converted into new grants.

## [0.3.0-beta.12] - 2026-09-11

### Added

- Dynamic per-user application permission controls and an own-access snapshot
  for extension interfaces, with shared route/operation authorization rules.
- Administrator-controlled account blocking, unblocking and termination of all
  sessions, with audit entries and protection against self-blocking.
- Persistent token generations prevent revoked tokens from returning after
  unblocking or logging in again, including legacy sessionless tokens.
- Migration preserves existing users as unblocked; shared HTTP request guards
  enforce account and session revocation on legacy routes as well.

### Verified

- Raspberry grant/revoke test used the same login token throughout; temporary
  test user was removed. Device testing of account blocking remains pending.

## [0.3.0-beta.11] - 2026-09-07

### Fixed

- Prepare the recovery key and export directory before service startup on clean
  installation and Master reset; preserve existing keys for retained backups.
- Accept older backups within the same major/minor release series when a known
  database migration path exists; reject newer or incompatible archives clearly.
- Keep compatibility checks read-only by deferring legacy database initialization
  until migration execution.
- Log portable import failures and distinguish storage, validation and version
  compatibility errors instead of a generic helper rejection.

### Verified

- User confirmed successful restore from their portable backup on Raspberry.
- Tested cross-version portable restore with real database migration and
  application data, plus read-only compatibility checks under systemd.
- Fresh-card installation of this published version remains to be tested.

## [0.3.0-beta.10] - 2026-09-02

### Added

- A strict `ApplicationExtensionV1` contract for supervised services,
  versioned operations, audiences, extension permissions, event subscriptions,
  connectors, jobs, storage and lifecycle declarations.
- Cross-file application package validation for service artifact integrity,
  compiled routes, declared capabilities, exact permissions and secret-safe
  configuration references.
- A separate `3mm-app` Extension Host, stable service SDK, signed local
  transport, administrator-only Core gateway and transactional activation with
  health checking and rollback. Uploaded application UI stays hidden until its
  service is active.
- Extension-owned SQLite storage, forward-only SDK migrations and a
  transactional outbox, with database rollback on failed activation and
  encrypted backup/restore participation for mutable application data.
- Extension-scoped operator grants, one-use kiosk enrollment, renewable
  short-lived kiosk sessions and immediate terminal revocation, with kiosk JWTs
  kept separate from normal user authentication.
- Server-filtered application compiled routes and data-driven public, kiosk,
  operator and administrator navigation policies.
- Administrator backup preview, encrypted local backup catalog, bounded
  retention and transactional restore with automatic rollback.
- Password-protected `.3mmrecovery` downloads and bounded restore-from-file
  uploads for recovery after a failed or replaced SD card.
- Deterministic administrator diagnostics downloads with explicit secret
  redaction and no persisted diagnostic payload.

### Fixed

- Host configuration restore now stages data on the destination filesystem,
  avoiding cross-filesystem directory replacement failures.
- Restore startup failures restart the existing services before returning an
  error, and one-time recovery exports can be removed by Core after download.

### Verified

- Restored a real local backup on `rasp-3mm` and returned Core, Web, Agent and
  update-helper to a healthy state.
- Deployed review release `worktree-50f841dce023-20260828175806` and completed
  a real portable export/import round trip with a fresh device key, archive
  authentication, private export permissions and cleanup.
- Completed the final browser download → clean installation → portable upload
  and restore acceptance on `rasp-3mm`, closing Milestone 11.
- Passed 160 focused application-extension protocol, SDK, runtime,
  authorization, backup/restore and deployment tests for Milestone 12 Stages
  1–4, plus 10 focused frontend tests and the production frontend build.
- Passed all 60 frontend tests, TypeScript checking and the production build;
  focused backend, protocol, helper and deployment tests passed before the
  Raspberry review deployment.

### Documentation

- Added the backup/restore contract, diagnostics boundary, closed Milestone 11
  report and the Milestone 12 application-extension plan/report.

## [0.3.0-beta.9] - 2026-08-28

### Added

- Recovery setup now pre-fills the previous device name, locale,
  administrator metadata, role and Hub address without persisting Wi-Fi
  credentials.
- Menu Editor visibility audiences for public visitors, signed-in users and
  administrators, while protected routes remain protected by router metadata.
- Administrator-only Raspberry restart and 3mm factory-reset controls backed
  by the narrow privileged helper, exact confirmation phrases and audit logs.

### Changed

- Factory reset removes persistent 3mm users, settings, dashboards,
  extensions, Agent identity, provisioning and update state, then returns the
  installed release to first-boot setup. The immutable release and Raspberry
  Pi OS are preserved.

### Verified

- Repeated the one-command installation on clean Raspberry Pi media and
  completed setup-to-Standalone successfully.
- Deployed immutable review release
  `worktree-4eb350b6a650-20260828075444` on the clean device; Core, Web, Agent
  and update-helper are healthy, ports 80/8080 and `rasp-3mm.local` return HTTP
  200, and the new system-control endpoints enforce authentication.
- Passed 60 focused backend/provisioning/deployment tests, all 54 frontend
  tests, TypeScript checking and the production frontend build.
- Physically completed the factory-reset path: persistent 3mm state was erased,
  the open setup AP returned across reboot, phone setup completed again and the
  fresh Standalone login worked.

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

[Unreleased]: https://github.com/ldobranov/3mm/compare/v0.3.0-beta.41...HEAD
[0.3.0-beta.41]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.41
[0.3.0-test.1]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-test.1
[0.3.0-beta.40]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.40
[0.3.0-beta.39]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.39
[0.3.0-beta.38]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.38
[0.3.0-beta.37]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.37
[0.3.0-beta.36]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.36
[0.3.0-beta.35]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.35
[0.3.0-beta.34]: https://github.com/ldobranov/3mm/tree/v0.3.0-beta.34
[0.3.0-beta.33]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.33
[0.3.0-beta.32]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.32
[0.3.0-beta.31]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.31
[0.3.0-beta.30]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.30
[0.3.0-beta.29]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.29
[0.3.0-beta.28]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.28
[0.3.0-beta.27]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.27
[0.3.0-beta.26]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.26
[0.3.0-beta.25]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.25
[0.3.0-beta.24]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.24
[0.3.0-beta.21]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.21
[0.3.0-beta.19]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.19
[0.3.0-beta.18]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.18
[0.3.0-beta.17]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.17
[0.3.0-beta.16]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.16
[0.3.0-beta.15]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.15
[0.3.0-beta.14]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.14
[0.3.0-beta.12]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.12
[0.3.0-beta.11]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.11
[0.3.0-beta.10]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.10
[0.3.0-beta.9]: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.9
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
