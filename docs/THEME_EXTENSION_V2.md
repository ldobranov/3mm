# Theme extension v2 — package contract

V4 is published; Core beta.40 includes the working baseline and installation
color customization. V5 installed-package preview and two actual reference ZIPs,
including a licensed Cyrillic font, were verified locally on 2026-10-07. Owner
approved V5; the follow-up integrated editor and idle-tab fix are local.
Release/deploy are still pending. Full live recovery acceptance
is separate. V1 stays supported; concrete theme ZIPs are installed separately,
not bundled with Core.
Device protocol and Application SDK 1.3 are unchanged.

## Single installer and lifecycle

**Extensions → Upload ZIP → Enable → Settings → Theme Customization → Preview → Cancel/Apply**.
Reuse the existing `/api/v1/modules/packages`, immutable ModulePackage store and
ThemeExtensionInstallation. No new database, Agent installation, compiler,
service, native dependencies or second upload screen.

Selection pins the exact ZIP hash. Enable/update does not auto-select. Rollback
selects an older enabled version. Disable/delete clears selection; broken packages
fall back to saved built-in settings. Existing admin authorization and audits apply.
Header/Menu text/colors, users, mode/locale preferences and other extensions remain.

## Envelope

ZIP contains `manifest.json`, `theme-extension.json` and optionally declared
`assets/` files. Manifest v2 is the same envelope as v1 themes: runtimes `["ui"]`,
entrypoint `{"ui":"theme-extension.json"}`, architectures `["any"]`, JSON-file
health check of the definition. No permissions, registrations, capabilities,
configuration, dependencies or conflicts. Identity/version must match both files.

Minimal `theme-extension.json`:

```json
{
  "theme_extension_version": 2,
  "design_api_version": 2,
  "module_id": "org.example.theme",
  "version": "2.0.0",
  "name": { "en": "Example", "translations": { "bg": "Пример" } },
  "base_theme": "builtin.default",
  "design": {
    "design_api_version": 2,
    "layout": { "navigation": "sidebar", "density": "compact" },
    "header_style": "theme"
  },
  "assets": []
}
```

`design` follows [Design API 2](THEME_DESIGN_API_V2.md): closed semantic colors,
bounded measurements, approved variants, null/default inheritance and contrast.
Backend/browser share `three_mm_protocol/theme_design_defaults.json`. No arbitrary
CSS, HTML, JS, Vue templates, handlers, imports or URLs.

## Asset declarations and validation

Fields: `asset_id`, `path`, `sha256`, `media_type`, `role`, optional `license`.
Id matches `[a-z][a-z0-9_-]{0,63}`; path is exactly
`assets/<ASCII letters/digits/_/->.woff2|png|webp`, ≤160 characters.
Hash is 64 lowercase hexadecimal characters and is checked against actual bytes.
Ids, paths and roles are unique.

| Role | MIME / matching suffix | Limits |
| --- | --- | --- |
| `font` | `font/woff2` / `.woff2` | 512 KiB; nonblank license attribution ≤512 characters |
| `logo_light`, `logo_dark` | `image/png`, `image/webp` | 1 MiB each; 1–2048 px per side |

Ceiling: 16 assets / 4 MiB; current unique roles allow at most three. Definition
≤64 KiB; outer ZIP limits also apply. Missing/undeclared/duplicate members,
symlinks, non-regular files, non-canonical paths and CRC/hash/type/size failures
reject upload. Resources are not extracted onto the filesystem.

PNG: non-interlaced 8-bit RGB/RGBA; IHDR/IDAT/IEND and sRGB/gAMA/pHYs only.
Checks CRC, dimensions, filters and bounded zlib expansion against declared pixels.
Convert indexed/interlaced/metadata-rich logos to this profile before packaging.
WebP: bounded still-image RIFF/VP8/VP8L container/dimensions; no animation or
EXIF/XMP/ICC/arbitrary chunks.

WOFF2: single-font signature/flavor, bounded directory/lengths, declared expanded
size ≤4 MiB, transformed table budget and stream boundary; no collection,
metadata/private blocks. A compressed stream may be followed only by up to three
zero bytes completing 4-byte alignment; excess, nonzero or misaligned padding is
rejected. Core **does not decode Brotli or validate every glyph**;
nor is its WebP check a complete codec. Container validation is not a full font/
image sanitizer. Browser `FontFace` / `createImageBitmap` performs final decoding.
Failure retains the system font/saved branding and shows a notice in Installed
themes. V5 locally verified a real licensed variable font with Bulgarian Cyrillic
through the actual ZIP validator, authenticated preview and browser FontFace.
This reference proof is not a universal glyph/codec validation guarantee.

References: [WOFF2](https://www.w3.org/TR/WOFF2/),
[WebP container](https://developers.google.com/speed/webp/docs/riff_container).

## Serving, projection and cleanup

V1 appearance `{ "theme": ... }` is unchanged. V2 adds `package_sha256` and
safe asset declarations; no OS paths, catalog errors, configuration or credentials.
Assets: `GET /api/v1/modules/themes/packages/{sha256}/assets/{asset_id}`.
Only the **selected, enabled** version is public, including for admin requests.
Staged/disabled/older versions are not public asset catalogs.

Serving checks the managed path, ZIP hash/manifest and asset from the same bytes;
no loose file or arbitrary path serving. Fixed MIME, `nosniff`, restrictive CSP
and `no-store` headers. Browser uses Core-generated URLs/families, credential-free
fetches, five-second fetch/font timeouts and streamed byte caps. WebCrypto adds
hash checks on secure origins; LAN HTTP relies on Core's verified artifact bytes.
Font registrations/blob URLs are cleaned on switch, fallback and store disposal.

V2 opts into the Core-owned shell; v1/custom colors stay legacy. Saved Header logo
overrides the mode-specific packaged logo. Header/Menu retain text/translations;
`header_style` changes visual precedence only. Component samples now live inside
Theme Customization, using the displayed package, its font and effective palette.

## Installed-package preview (V5)

An administrator can read an enabled exact package using
`GET /api/v1/modules/themes/preview?sha256=<hash>`; omit `sha256` for built-in
appearance. The response includes that package's saved customization. The
projection is read-only: no selection, enable, settings or audit writes.

Preview resources use
`GET /api/v1/modules/themes/packages/{sha256}/preview/assets/{asset_id}` with
administrator authentication. They use the same managed-path, ZIP/hash/type/
size checks, fixed MIME and restrictive no-store/nosniff/CSP headers. Public
asset serving remains selected-only; no token is sent to public asset endpoints.
Missing, staged, disabled or invalid packages fail closed.

Settings displays the localized package name/version and temporarily applies
its design, saved preferences, local font and logo in this browser only. Asset
decode failures retain readable fallbacks and show a preview notice. Cancel,
leaving the section or an apply failure aborts outstanding preview work,
disposes its font/blob resources and restores the selected appearance and
previous browser color mode. Late responses cannot resurrect a cancelled preview.
Selected resources remain available for immediate restoration.

The selected-theme color editor is hidden during package preview. The temporary
color-mode control does not write account preferences. Apply uses the existing
admin-only selection POST, revalidates the package and refreshes appearance;
preview itself never commits a selection. No new upload flow, database migration
or SDK version is needed. V5 now has two actual enabled reference packages on one
local Core build, not merely two layout fixtures. Preview/Cancel leaves selection
and audit unchanged; Apply submits one selection transaction, auditing both the
old and new selection rows. See [V5 report](THEME_PLATFORM_V2_V5_REPORT.md) for
the real upload/enable/reload/font checks and the isolated environment limits.
These local checks do not replace live installation/recovery acceptance.

## Installation color customization

Settings → Theme Customization offers the selected theme's supported color
parameters, reusing the Core ColorPicker. v1 exposes its 11 legacy colors;
v2 without an options declaration exposes all 17 semantic colors, including
button foregrounds, status and focus. New packages can restrict editable tokens
and variants using the declaration below. No concrete theme name is special-cased.
Built-in colors retain the existing light/dark editors and storage.

Light/dark palettes are edited independently. Changes preview locally, and
**Save appearance** persists them through the existing admin-only customization
endpoint. **Discard changes** and leaving the section remove the unsaved preview.
**Restore this palette** removes only the currently edited mode's overrides from
the draft; Save is still required. **Use theme defaults** clears the selected
theme's appearance overrides, not its ZIP, branding or old built-in colors.

The existing per-SHA settings JSON gains an optional sparse `colors` object:
`{"light":{"border":"#123456"},"dark":{"border":"#ABCDEF"}}`.
Missing colors inherit the original package. Existing preferences without
`colors` remain compatible. Unknown tokens/modes, CSS values, non-hex values and
wrong types are rejected. v1 cannot set v2-only tokens and retains its existing
legacy color validation; v2 overrides must pass the original Design API 2
contrast validation after merging with the actual package. Both modern tokens
and legacy CSS aliases receive the effective colors. Fonts, assets, geometry,
translations and authentication are unchanged.

The immutable ZIP is never rewritten. Settings remain independent per exact
package version, survive reload and are covered by existing database backups.
Invalid restored overrides are ignored without disabling a healthy theme.
No database schema migration, SDK bump or new installer is required.

## Package-declared editor options

Optional root field `customization_options` in `theme-extension.json`:

```json
{
  "navigation": ["sidebar", "top"],
  "density": ["compact", "comfortable"],
  "button": ["solid", "outline"],
  "card": ["raised"],
  "header_style": ["theme"],
  "colors": ["border", "accent", "accent_text", "focus"]
}
```

The example belongs inside that field, not inside `design`. All choices are
closed Design API 2 variants; colors are the 17 allowlisted semantic tokens.
Nonempty variant lists must include the package's normalized default.
Duplicate, unknown, wrong-type and unsafe declarations fail upload.
Core renders controls generically: multiple variants show a selector, a single
variant is fixed, missing/empty variants are fixed at the package default.
Only declared colors are editable, independently for light/dark.
An explicit empty object means no editable package appearance options.
Personal light/dark preference is independent and remains available.

An omitted declaration preserves existing v1/v2 controls; immutable old ZIPs
do not need rewriting. Packages that use this new field require a Core build
supporting it; older Core validators correctly reject the unknown field.
No SDK/device protocol bump is involved.

Backend customization validation enforces the same choices, not merely hidden
UI controls. Restored incompatible preferences are ignored without losing the
healthy theme. The selected package must be applied before editing and saving
its installation preferences; previewing another package remains read-only.

The editor and component samples share one Theme Customization workspace.
Palette selection changes the samples' local colors without saving the user's
personal mode. Save persists appearance; Discard or leaving removes the draft.
Old `/settings/ui-preview` bookmarks redirect to `/settings?section=theme`.
The explicit recovery route below remains separate and administrator-only.

## Foreground refresh failure

Network/DNS failures, timeouts, HTTP errors and malformed appearance responses
are not evidence that the theme was disabled. During a running tab, retain the
last verified theme, customization, font and logo, and show a notice in Settings.
A successful appearance response with `theme: null` still switches to built-in
(explicit deselection, disabled or invalid package). Verified resources for an
unchanged immutable hash are reused on focus refresh; fallback is still used on
first load when no verified theme is available. This does not repair LAN DNS.

## Recovery and portable restore

Admin-only `/settings/ui-preview?recovery=1` bypasses installed styling and shows
static readable controls. **Use built-in permanently** calls existing selection
API with `{ "sha256": null }` and clears built-in layout overrides without
requiring a healthy artifact or erasing branding, package overrides or data.
Returning to Settings without this action restores the installed view.

Existing encrypted/portable backup includes the database and complete immutable
ZIP. A local export → import with a new key → restore test verifies v2 selection
and asset serving. Live Raspberry upgrade/reset/restore is V8, not performed here.
V5 reference/font proof is complete locally and owner-approved; delivery is
pending. Core beta.40 does not include the new installed-package preview or WOFF2
alignment fix. Install the new reference ZIP after delivering those Core changes;
it is not bundled into a Core release. See [V5 report](THEME_PLATFORM_V2_V5_REPORT.md).
