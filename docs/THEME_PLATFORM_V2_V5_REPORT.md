# Theme Platform v2 — V5 local acceptance

Date: 2026-10-07. Status: implementation and local reference acceptance complete;
owner visual review approved on 2026-10-07. Release preparation for beta.41 was
then authorized separately; publication requires the full release gates below.
The local acceptance did not deploy to Raspberry. V6–V8 remain open.

## Two actual packages on one Core build

Both packages use the existing declarative UI manifest and Extensions installer.
They are local handoff artifacts under ignored `.runtime/`, not shipped in Core.

| Setting | Graphite Mint 2.0.0 | Slate Copper 2.0.0 |
| --- | --- | --- |
| Navigation / density | Sidebar / compact | Top navigation / comfortable |
| Buttons / cards | Solid / raised | Outline / bordered |
| Typography | System font, 14px / 1.55 | Local variable sans, 15px / 1.6 |
| Spacing / radii | Unit 4; 8/14/20 | Unit 5; 4/8/12 |
| Assets | Two local PNG marks | One local WOFF2 font and full OFL license |

Graphite ZIP: `.runtime/GraphiteMint-2.0.0.zip`, SHA-256
`0ec872bf9376ff85fc24c558fbbf4ed91afc1504a4cded2b27376d555ef68036`.

Slate ZIP: `.runtime/theme-v5-reference/SlateCopper-2.0.0.zip`, 354,684 bytes,
SHA-256 `8b58f31666adb3c298fcf08cd5ab3bd6ffe6faae855eb38492770f738bb4dcc4`.
The actual shared validator accepts it for `armv6l` via architecture `any`.
No compiler, service, permissions, device capability or SDK change is required.
These artifact paths are local evidence, not committed assets available in a
fresh checkout. The themes continue to be installed separately by the owner.

## Licensed font and Cyrillic

Upstream: [Inter at pinned commit 353b61b9](https://github.com/rsms/inter/tree/353b61b9f4430d5f420d56605a6e7993e0941470),
with its full [SIL Open Font License 1.1](https://github.com/rsms/inter/blob/353b61b9f4430d5f420d56605a6e7993e0941470/LICENSE.txt).
The downloaded upstream `InterVariable.woff2` SHA-256 is
`693b77d4f32ee9b8bfc995589b5fad5e99adf2832738661f5402f9978429a8e3`.

The derived **Slate Reference Sans** keeps the outlines and copyright, renames
primary family/full/PostScript names to avoid the reserved Inter name, and embeds
the complete OFL text in font name table 13. The complete license therefore
travels inside the ZIP's WOFF2, and the asset declaration has license attribution.
`Inter-OFL.txt` is also retained beside the local artifact, not as an undeclared
ZIP member. This is a reference font, not a Core-owned special case or new engine.

Derived WOFF2: 353,620 bytes, below the 512 KiB font cap, SHA-256
`487be57fde5647805ebdb1b101740a6ba88eb70f97834873e0a700bddd66a6b6`.
The glyph check finds all 66 Bulgarian Cyrillic codepoints tested:
U+0410–U+044F plus U+040D and U+045D. The browser successfully decodes and loads
the real FontFace; computed shell typography uses its generated package family.
No remote font/CDN is involved.

FontTools/Brotli were used only in an ignored local artifact-building environment.
They were not added to the project or production dependency set. The local
`build_reference.py` creates the package and verifies names, embedded license and
glyph coverage; it is outside the Core release alongside the theme artifacts.

## Generic WOFF2 compatibility fix

The real font exposed a strict end-of-stream check that rejected encoder-produced
zero alignment bytes. The container validator now allows at most three zero
bytes completing 4-byte alignment. It still rejects excess, nonzero or misaligned
padding, truncated streams, metadata/private blocks and invalid bounds/hashes.
Eleven focused tests cover the changed boundary.

Core still does not decode Brotli or sanitize every glyph: final decoding belongs
to browser FontFace. This is a bounded container compatibility correction, not a
new codec or relaxed arbitrary-file upload. No database migration is needed.

## Actual UI flow and persistence evidence

The browser used the real frontend and Core module/theme/settings routes with a
disposable SQLite database and a temporary authenticated administrator session.
Graphite was seeded through the shared package APIs; Slate was uploaded and
enabled through the actual **Extensions UI file chooser and lifecycle control**.

- Both exact immutable packages remained enabled on the same local Core build.
- Preview loaded Slate's design and font while Graphite remained selected.
- Changing the preview's color mode did not persist account mode preferences.
- Cancel restored Graphite's sidebar/light view, removed the preview font
  registration (font set count 1 → 0), and left selection and theme audit count
  unchanged at 3. Existing header sentinel data remained unchanged.
- Apply sent one explicit selection POST/transaction. The existing audit correctly
  records two updates: old selection false and new selection true (count 3 → 5).
  One transaction does **not** mean one audit entry.
- Reload preserved Slate's exact hash, top navigation, browser-loaded font,
  localized BG controls and the authenticated administrator view.
- Desktop EN/dark and BG/light were inspected; mobile BG/light and BG/dark were
  inspected with a 390 × 844 viewport override. Content/scroll width both measured
  375 CSS pixels with the scrollbar present: no horizontal overflow in this view.
  The mobile navigation drawer opened and closed with localized links.

The fixture supplies harmless menu/language/catalog data for unrelated features;
it does not run installed business extensions or real device/payment operations.
Its temporary session is not a production login/revocation acceptance test.
The unrelated external Bootstrap Icons stylesheet is omitted only in this fixture;
this does not claim the whole application has no external icon dependency.
Existing untranslated legacy section labels remain outside this step's scope.
Other screens, role behavior and recovery retain their separate acceptance gates.

Local screenshots under `.runtime/theme-v5-reference/`:

- `slate-copper-selected-en-dark.png` — selected theme, desktop dark.
- `slate-copper-preview-bg-light.png` — temporary preview, BG/light.
- `slate-copper-selected-bg-mobile-dark.png` — selected theme, mobile dark.
- `slate-copper-selected-bg-mobile-light.png` — selected theme, mobile light.

The temporary browser tab and local acceptance servers were closed after review.

## Checks and next gate

Repeated focused backend suite: **56 passed**, including the new 11 WOFF2 cases
and preview/v2 package checks. Thirty existing deprecation warnings remain.
The preview implementation's earlier **42 frontend tests** and TypeScript check
passed; they were not repeated for this font/container-only step.
Frontend `npm run build-only` was repeated successfully (320 modules); its existing
static/dynamic import warning remains. A full release suite was not run here.

Core beta.40 does not contain the installed-package preview or this font alignment
fix. Deliver the pending Core changes before installing Slate on that version.
The new theme must remain a separately uploaded ZIP, not a bundled Core asset.

Follow-up: idle-tab retention and integrated theme editor, including optional
package-declared controls; see [package contract](THEME_EXTENSION_V2.md).
The original two-package/font evidence above describes the V5 review, not the
follow-up changes.

## Follow-up acceptance — integrated editor

The final production frontend build was reviewed against the real local Core
theme/settings APIs with a disposable database. No Raspberry data was changed.

- Theme Customization now contains the live component samples; the ordinary
  `/settings/ui-preview` bookmark redirects to this single editor. Explicit
  `?recovery=1` still opens the protected, untokenized recovery view without
  changing the selected theme merely by visiting it.
- Legacy Graphite Mint 2.0.0 still exposes its compatible controls. A test-only,
  in-memory Slate Copper 2.0.1 variant declares two editable variant fields and
  four colors. The UI shows exactly those fields, keeps its other defaults fixed,
  and loads its actual licensed package font. This variant is not a Core asset
  or a new delivered theme ZIP.
- Editing the dark border color, saving and reloading preserves `#AABBCC`.
  Independent palette preview leaves the personal light/dark choice unchanged.
  Sample dialog focus and controls were checked without business operations.
- EN/BG switching, desktop light/dark and mobile layout were checked with the
  production build. At 390 × 844, document client/scroll width both measured
  375 CSS pixels: no horizontal overflow in the editor.
- Failed/unavailable appearance responses retain the last verified theme,
  preferences and loaded font in regression tests. A verified `theme: null`
  still honors explicit fallback. This does not repair an underlying DNS outage.

Focused checks: **53 frontend tests**, **65 backend tests**, TypeScript check and
frontend build passed (323 modules). Existing import/deprecation warnings remain;
no full release suite was run. The temporary browser tab and local servers were
closed after review.

Additional local screenshots under `.runtime/theme-v5-reference/`:

- `theme-workspace-bg-desktop-dark.png` — offered controls alongside live samples.
- `theme-workspace-bg-mobile-light.png` — production build, mobile controls.

## Authorized release preparation — beta.41

The owner authorized full checks, documentation, commit, push and release on
2026-10-07. All **190 frontend tests** passed, along with TypeScript checking and
the production build. The complete isolated Linux/Python 3.14 suite passed
1,438 tests, with six route tests failing because Unix sockets were placed on
NTFS. All six passed on repetition with temporary Linux socket directories;
this required no production-code change. One opt-in HTTPS acceptance test was
skipped. GitHub must repeat the complete suite on Python 3.13 and prove immutable
full-profile/ARMv6 Node build reproducibility before publishing. Concrete theme
ZIPs, Child Center and ignored local fixtures are excluded. No live Raspberry
update is included.

After delivery, start **V6 / DashboardList only**; do not redesign all screens at
once. V7 extension UI contract and V8 real upgrade/restart/rollback/portable
recovery remain open.
