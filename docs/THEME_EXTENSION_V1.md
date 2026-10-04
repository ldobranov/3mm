# Theme extension v1 — package contract

Status: T1–T3 implemented locally on 2026-10-04, including the Settings chooser
and safe browser loader. Reference theme/live acceptance remain in T4/T6.

## ZIP layout

```text
manifest.json
theme-extension.json
```

Exactly these files; no executable source, stylesheet, script, font, image or
remote asset. Package limits/checksums are the existing Module Manifest v2 ones;
the theme definition is additionally limited to 64 KiB.

Example manifest:

```json
{
  "manifest_version": 2,
  "module_id": "org.example.theme",
  "name": "Example Theme",
  "version": "1.0.0",
  "runtimes": ["ui"],
  "entrypoints": {"ui": "theme-extension.json"},
  "compatibility": {"protocol": "1.0", "architectures": ["any"]},
  "health_check": {"type": "json_file", "path": "theme-extension.json"}
}
```

Permissions, registrations, provided/consumed capabilities, dependencies,
conflicts and configuration must be empty. No Core service, Agent module or
compiled UI is mixed into a theme package. The package name is illustrative;
Core does not know any concrete theme name.

Example definition:

```json
{
  "theme_extension_version": 1,
  "design_api_version": 1,
  "module_id": "org.example.theme",
  "version": "1.0.0",
  "name": {"en": "Example Theme", "translations": {"bg": "Примерна тема"}},
  "base_theme": "builtin.default",
  "light": {
    "body_bg": "#F5F6F8",
    "card_bg": "#FFFFFF",
    "text_primary": "#20242B",
    "button_primary_bg": "#356AE6",
    "radius_md": 8
  },
  "dark": {
    "body_bg": "#181B20",
    "card_bg": "#242932",
    "text_primary": "#E8EBF0",
    "button_primary_bg": "#7198F2",
    "radius_md": 8
  }
}
```

Identity/version must match the manifest. Both modes must provide at least one
token. Missing/null token values inherit the built-in base; a radius of zero is
a valid explicit override. Inheritance from another installed theme is not v1.
Names use current localized-text shape, with at most 32 bounded translations.

## Allowed tokens

| Contract token | Existing CSS variable |
| --- | --- |
| `body_bg` | `--body-bg` |
| `content_bg` | `--content-bg` |
| `card_bg` | `--card-bg` |
| `panel_bg` | `--panel-bg` |
| `button_primary_bg` | `--button-primary-bg` |
| `button_secondary_bg` | `--button-secondary-bg` |
| `button_danger_bg` | `--button-danger-bg` |
| `card_border` | `--card-border` |
| `text_primary` | `--text-primary` |
| `text_secondary` | `--text-secondary` |
| `text_muted` | `--text-muted` |
| `radius_sm` | `--border-radius-sm` |
| `radius_md` | `--border-radius-md` |
| `radius_lg` | `--border-radius-lg` |

Colors are six-digit `#RRGGBB` only. Radii are strict integers, 0–50 pixels;
strings, floats and booleans are not numeric radii. Unknown fields/tokens and CSS
expressions (`url`, `var`, selectors/declarations) are rejected. Alias derivation
remains Core-owned; the T3 adapter applies it, not the extension. Package button
foregrounds are derived for contrast; no arbitrary CSS is emitted from the ZIP.

The design API version is independent of package version, Core/SDK version and
device protocol. Unsupported design API versions fail validation. A new theme
version does not change Core code. Assets/layout slots/component variants require
a separate reviewed contract addition; marketing content belongs to an application
extension, not this schema.

## Verification

```powershell
python -m pytest backend/tests/test_theme_extension_packages.py backend/tests/test_module_packages.py -q
```

53 passed locally on 2026-10-04. Includes light/dark, localization, zero-radius,
bounded values, identity mismatch, unsafe content, authority escalation and
existing runtime/compiled/application package regression checks.

## Registry/lifecycle (T2)

Use the existing administrator `POST /api/v1/modules/packages` upload endpoint.
Uploading stages a theme; it does not change application appearance. The registry
and lifecycle API are documented in [THEME_EXTENSION_PLAN.md](THEME_EXTENSION_PLAN.md).
Package versions/hashes are immutable and installation-local status is protected
by the same normal-user/admin boundary as module management, with audit records.

Alembic migration `a7bf06b7c8d9` is required before using the new lifecycle API on
an existing database. Old packages, settings, users and device trust are not
migrated into themes or reset. SDK/device protocol versions remain unchanged.

T1/T2 plus existing package/model and backup-compatibility checks: 78 passed
locally. This includes a real older portable-archive restore followed by the full
Alembic upgrade chain. T3 selection/appearance is documented in the delivery plan;
theme-specific portable acceptance remains in T6.

## Install in Extensions; select in Settings (T3)

An administrator uploads the ZIP using the common upload in Extensions. Each
theme version has its own card and enable/disable/delete controls. There is no
separate theme upload page. Enable the required version, then open Settings →
Theme Customization → Installed themes, select it and press Apply theme.
Uploading or enabling alone does not change appearance. Updates do not
automatically replace the selected version. Disabling/deleting the selected
version returns to built-in; unrelated saved settings remain intact.

Package colors are currently read-only in Core: the built-in color editors are
hidden while a valid package is active, not repurposed as global overrides.
Create a new immutable package version to change its tokens. Optional missing
tokens inherit the built-in defaults, not legacy administrator values.

Public/login and authenticated pages load the same validated appearance, without
requiring access to the administrator catalog. Missing/corrupt/unsupported
definitions and network failures use built-in settings; disable/delete clear the
persisted selection. Open tabs refresh on becoming visible or on reload.
