# Core Theme Platform — delivery plan

Approved: 2026-10-04. Current priority in [MASTER_PLAN.md](MASTER_PLAN.md).
Roadmap reference: Milestone 17. Design context: chat “Предложения за тема”.

Update 2026-10-05: T0–T3 are published in `v0.3.0-beta.36`. The stage records
below retain their development-time checks and limitations. Full visual themes
are planned separately in [Theme Platform v2](THEME_PLATFORM_V2_PLAN.md), still
within Milestone 17. V0–V4 are implemented locally and prepared for beta.37;
publication depends on the release workflow, and no live deployment is claimed.
Concrete theme ZIP packages are excluded from the Core release;
reference packages and live acceptance remain V5–V8. See the
[v2 package contract](THEME_EXTENSION_V2.md).

## Goal and boundary

Themes are separately versioned, installable ZIP extensions. Core owns a small
Theme API, validation, registry, active selection and token application. A
specific palette/design does not require a Core commit.

One local installation can use a theme without CME, Fleet or cloud connectivity.
The same contract serves Standalone, Hub and the central CME installation.

The theme cannot own routes, role rules, business data, device authority,
Command Palette or Vue components. Product and marketing can share a design
language, but marketing routes/content belong to a separate application extension.
No arbitrary stylesheet or JavaScript is part of the declarative v1 package.

## Baseline and compatibility

Current implementation uses `frontend/src/stores/theme.ts` for browser light/dark
mode and `frontend/src/stores/settings.ts` for persisted custom colors, radii and
CSS aliases. ThemeCustomizationSection edits these existing settings; Header
and Menu Customization also own independent settings and localized text.

T1 uses the existing eleven colors and three radii as its initial token API,
not a competing CSS framework. Native Vue/CSS, current Bootstrap Icons and
existing CSS variables remain. There is no new framework or database migration
in T1, and no SDK/device protocol version change.

Before browser activation, implement and verify this precedence explicitly:

1. Built-in legacy theme/settings work unchanged when no package is selected.
2. A selected package overrides only declared tokens; missing tokens inherit
   the built-in light/dark base.
3. Any future administrator overrides must be deliberate, theme-scoped settings; old stored
   defaults must not silently overwrite the entire package. Changing/removing
   a theme must not erase legacy settings. T3 keeps package colors read-only;
   the existing custom-color editors are available only with the built-in theme.
4. Header/Menu content, branding text, colors and layout preferences stay under
   their existing owners. Applying design tokens must not overwrite them.

Theme selection is installation-wide and language-independent. Light/dark mode
remains a separate browser preference. No session invalidation is required.

## Stages

| Stage | Result | Status |
| --- | --- | --- |
| T0 | Inspect existing stores/tokens and fix extension boundary | Recorded; baseline for beta.36 |
| T1 | Strict theme contract and immutable ZIP validation | Published in beta.36; 53 focused development checks passed |
| T2 | Theme catalog, admin install/disable/delete, pinned package identity | Published in beta.36; migration and lifecycle/authorization checks passed |
| T3 | Settings selection, generic loader, legacy precedence and fallback | Published in beta.36; focused checks and isolated desktop/mobile review passed |
| T4 | Separately maintained reference theme and preview | Local Graphite Mint v1 palette/package and isolated preview; live installation acceptance remains open |
| T5 | Incremental shell and screen refinement | V0–V4 prepared for beta.37; V5–V8 remain open, no full screen redesign delivered |
| T6 | Upgrade/recovery/visual acceptance and documentation | Planned |

### T1 — Package foundation, delivered locally

- [theme-extension v1](THEME_EXTENSION_V1.md) is a closed, versioned contract;
- standard `manifest.json` + `theme-extension.json`, immutable SHA-256;
- both light and dark modes; optional safe tokens inherit `builtin.default`;
- no CSS expressions, HTML, code, URLs, assets, permissions or registrations;
- bounded metadata, strict numeric radii and package identity checks;
- existing runtime/compiled/application packages keep their contracts.

**This is validation/staging support, not end-to-end theme installation yet.**
No theme chooser, browser activation or visual change has shipped in T1.

### T2 — Registry and lifecycle

Reuse the existing module-package catalog, upload limits, checksums, version
immutability and admin authorization. Do not create a parallel theme upload store
or misuse Agent ModuleInstallation for a browser theme. Add a generic theme
catalog/API projection from validated packages, without hardcoded theme names.

Pin a chosen version/hash. Reject incompatible Design API versions. Installation
must not require the Vue compiler or spawn a service. Disable/uninstall of the
active package must clear selection/fall back, retain unrelated settings and be
audited. Reinstallation and rollback use the exact immutable package.

Delivered locally: `theme_extension_installations` references the existing
immutable ModulePackage; enable/disable do not rewrite its ZIP or definition.
Persistence is installation-wide, not user/language-specific. It is separate from
generic Settings CRUD, so normal users cannot modify the lifecycle there.
Alembic `a7bf06b7c8d9` follows `96aef5a6b7c8`; its additive migration creates no
automatic installations or selections and preserves existing data. The legacy
baseline excludes this new table so clean installs/older restores build the
schema in the correct order.

Admin-only API under `/api/v1/modules`:

- `POST /packages` — existing ZIP upload; theme remains staged;
- `GET /themes/catalog` — staged/enabled/disabled/unavailable versions;
- `POST /themes/packages/{sha256}/enable` — register that exact validated ZIP;
- `POST /themes/packages/{sha256}/disable` — clear selection even if ZIP is broken;
- `DELETE /themes/packages/{sha256}` — remove that version and its managed artifact.

Catalog/enable revalidate the bounded ZIP, checksum and manifest identity. A
broken ZIP does not block catalog access or disable/delete recovery. Lifecycle
changes are audited; enabling a new version never silently selects it. Schema
constraints permit only one selected theme and prohibit a disabled selection.
Themes cannot install onto an Agent or start a service/compiler. Deletion is
confined to the managed upload store and refuses other installation references.

78 focused checks passed: contract/package regressions, admin/non-admin/blocked
user boundary, immutable uploads, exact-version registry, migration up/down and
ZIP member corruption, and older portable restore with migration to current head. UI controls and actual
browser fallback are T3, not claims of T2. No live deployment performed.

### T3 — Selection and loader

Add an administrator theme selector in Settings alongside—not replacing—the
light/dark control. Render localized names using current i18n. A Core-owned
adapter maps validated tokens to known CSS variables and existing aliases.
Never apply arbitrary user-supplied keys/values through `style` or inject CSS.

Bootstrap/load must work on login/public pages and authenticated application
pages without disclosing private catalog/configuration information. Reuse the
existing public appearance boundary where available; define a narrowly bounded
projection otherwise and test its authorization separately.

Failure to load a package must leave the application usable with the built-in
theme. Keep selection separate from browser mode, locale and authentication.

Delivered locally on 2026-10-04:

- Extensions owns the single ZIP upload and the shared catalog. Theme versions
  appear alongside runtime/compiled/application extensions, with localized names,
  exact-version enable/disable/delete and a separate selected marker. Enabling
  is not selection. Broken selected packages retain disable/delete recovery;
- Settings → Theme Customization → Installed themes only selects an enabled exact
  version or returns to built-in. There is no second upload or lifecycle list;
- upload uses the existing generic `/packages` endpoint and package detection.
  The optional API `expected_kind=theme` guard remains available to callers that
  need it, but the common Extensions upload accepts all supported package types;
- admin `POST /api/v1/modules/themes/selection` accepts `{ "sha256": "…" }` or
  `{ "sha256": null }` for built-in; enable is required, selection is audited,
  idempotent and transactional, with the existing unique-selection constraint;
- public `GET /api/v1/modules/themes/appearance` returns only `{ "theme": … }`
  or `{ "theme": null }`, with `Cache-Control: no-store`; it exposes no catalog,
  storage path, lifecycle error, user/configuration data or credential;
- the browser loads this projection without credentials/auth-refresh handling,
  with a five-second fetch timeout and strict version/token/value validation;
- initial load, local theme actions, settings refresh, reload and returning to a
  visible browser tab refresh appearance; there is no continuous polling;
- declared package tokens override the immutable built-in mode defaults; legacy
  saved colors are untouched and resume on built-in/failure. Both modes use
  current CSS aliases, with contrast-aware package button foregrounds;
- header/menu ownership, locale, light/dark preference, routes and sessions are
  unchanged. Themes still cannot provide scripts, stylesheets or components.

Verification: 23 focused backend checks (selection, lifecycle, authorization and
migration), 27 frontend adapter/store/Settings/Extensions checks, `npm run type-check` and
`npm run build-only`
passed. Actual component/store browser review used disposable API fixtures,
desktop and a 390px viewport, light/dark, EN/BG, long names, Extensions cards,
the delete confirmation, Settings selection and return to built-in. This was not
a live deployment or a full-application/portable-restore
acceptance; T4/T6 remain open.

### T4/T5 — Reference design, then incremental UI

The separate design chat builds a compatible reference package. Visual direction:
graphite/white surfaces, restrained accent, compact product controls, excellent
dark mode and mobile layout. Product shell evolves toward a left sidebar;
Display Editor later becomes palette/canvas/properties. Theme tokens alone do
not restructure App.vue or replace extension components.

Graphite Mint v1 now exists locally as a separately validated palette package.
Its isolated component/token preview is not an installed full-application theme.

The [v2 delivery plan](THEME_PLATFORM_V2_PLAN.md) expands this stage: shared
UI primitives, Core-owned shell variants, typography/density, safe local assets
and one versioned design contract. Layout slots, fonts and packaged assets are
v2 additions prepared for beta.37, not v1 features. Themes remain non-executable; they choose
Core-owned variants rather than replace Vue components or application behavior.
V1 compatibility and existing Header/Menu ownership are explicit acceptance gates.
Review one screen before moving to the next; do not redesign the whole application
or the deployment process. T6 live/portable acceptance is not closed by this plan.

### T6 — Acceptance

Upload -> select -> light/dark -> change language -> reload -> upgrade/rollback
-> disable/uninstall -> built-in fallback. Backup/portable restore must preserve
the package and selection without changing users, sessions or device state.

Review desktop/mobile, long labels, forms, modals, focus/contrast and extension
pages in both modes. Check navigation/role filtering, public/login pages and
Command Palette. Offline use must not depend on fonts/assets from an external CDN.

Use focused tests and `npm run build-only` for frontend steps. No full-suite run,
live deployment, commit or release is implied by this plan.
