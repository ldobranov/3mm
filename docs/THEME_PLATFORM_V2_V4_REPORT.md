# Theme Platform v2 — V4 report

2026-10-05. Implemented locally; no deploy/commit/push/release/version bump.
No Child Center changes, SDK change, database change or new native dependency.

## Delivered

- Strict v2 envelope/Design API validation alongside unchanged v1 support.
- One shared defaults JSON for backend and browser.
- Existing Extensions upload, immutable version/hash, enable/select/rollback/
  disable/delete and audits, without a compiler or second installer.
- Declared local WOFF2/PNG/WebP roles, canonical paths/hash/size/container checks
  and selected-only managed-ZIP serving, fixed MIME and no-store/nosniff.
- Installed v2 shell/layout/density/components, legacy alias projection,
  credential-free asset loader, system/saved-branding fallback and cleanup.
- Protected static recovery bypass with permanent built-in selection action.
- Existing encrypted portable backup retains complete ZIP/assets and selection.

## Verification

59 existing backend theme checks plus 37 v2 checks passed. Includes authority,
staged asset denial, corruption, rollback/disable/delete and real local portable
export/import with a new key/restore followed by asset serving. No live systemd
or real device/business operations were invoked.

48 focused frontend tests passed; type-check and production build passed.
Main JS: 274.46 kB / gzip 87.41 kB; main CSS: 259.62 kB / gzip 36.43 kB.
Compared with V1–V3: +6.41 kB JS / +2.15 kB gzip; CSS unchanged.
The existing dynamic-http mixed static/dynamic import warning remains.

Browser review used the actual production frontend with a disposable loopback
API fixture, not Raspberry: installed v2 light/dark, loaded PNG branding,
BG labels, 390px layout/drawer, static recovery and successful permanent clear.
Review found legacy Bootstrap alerts/controls in Dashboard; their redesign is V6.
Recovery screenshot: `.runtime/theme-v4-recovery.png` (ignored local artifact).

## Limits and next step

Font/WebP checks are bounded container validation, not a complete codec sanitizer.
Core does not Brotli-decode fonts; final glyph/image decoding is browser-owned.
Actual licensed font/Cyrillic, reference themes and pre-Apply package preview
remain V5. Complete live auth/extension/upgrade/reset/restore acceptance is V8.
No claim is made that every legacy page or extension has been restyled.

Contract: [Theme extension v2](THEME_EXTENSION_V2.md).
Next: V5 reference packages + isolated installed-package preview/cancel/apply.
