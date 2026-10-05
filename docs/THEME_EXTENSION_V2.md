# Theme extension v2 — package contract

V4 implemented locally on 2026-10-05 and prepared for Core beta.37; publication
requires a successful release workflow. No live deployment is claimed. V1 stays
supported; concrete theme ZIPs are installed separately, not bundled with Core.
Device protocol and Application SDK 1.3 are unchanged.

## Single installer and lifecycle

**Extensions → Upload ZIP → Enable → Settings → Theme Customization → Apply**.
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
metadata/private blocks. Core **does not decode Brotli or validate every glyph**;
nor is its WebP check a complete codec. Container validation is not a full font/
image sanitizer. Browser `FontFace` / `createImageBitmap` performs final decoding.
Failure retains the system font/saved branding and shows a notice in Installed
themes. Real licensed font/Cyrillic acceptance remains V5.

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
`header_style` changes visual precedence only. Temporary preview uses system-font
design and does not change installed selection.

## Recovery and portable restore

Admin-only `/settings/ui-preview?recovery=1` bypasses installed styling and shows
static readable controls. **Use built-in permanently** calls existing selection
API with `{ "sha256": null }`, without requiring a healthy artifact or erasing
settings. Temporary preview restore is a separate action.

Existing encrypted/portable backup includes the database and complete immutable
ZIP. A local export → import with a new key → restore test verifies v2 selection
and asset serving. Live Raspberry upgrade/reset/restore is V8, not performed here.
Reference packages and installed-package preview before Apply remain V5.
