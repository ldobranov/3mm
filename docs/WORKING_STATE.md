# Current working state

Updated: 2026-11-26. Start here. For a dated decision, test run or device
receipt, search the [complete record through November 25](WORKING_STATE_HISTORY_2026-11-25.md).
It includes handoffs that were local at the time; historical open items are
not a task queue.

## Active task and next result

The Core pilot is published. Keep these three baselines separate:

| Where | Last verified state | What that proves |
| --- | --- | --- |
| Published Core | [v0.3.18](https://github.com/ldobranov/3mm/releases/tag/v0.3.18), `387011e` | Verified pilot code from `a3526de`, with only `VERSION` changed. Public assets verified; not deployed to `rasp-3mm`. |
| Owner's `rasp-3mm` | Last recorded on Nov 24: `local-b73cc455215a51c20f88a05c` over 0.3.17 | The scoped CAP21 compiler and package-upload fixes were deployed. Core/Web/Agent were ready; package and permission fingerprints were unchanged. No device check during cleanup. |
| Separate Linux pilot | Nov 26, public 0.3.17 → 0.3.18 on Ubuntu x86-64, Monitor 0.8.4 | The already-open Monitor received a fresh result. A second copy automatically returned to 0.3.17 on a controlled web startup failure. Both copies stopped; the 0.3.17 baseline was preserved. |

**Local cleanup after publication (November 26).** No push, release, Pi
deployment or permission change. The published version is still `v0.3.18`.

- `c931936`: rollback review preselects only previously verified connectors.
  Reused the 227 checks recorded below; not a second run.
- `b59d2ec`: the pilot install examples pin 0.3.18; only the historical
  layout transition from 0.3.11 pins 0.3.12. Checked local links, anchors
  and both tagged installers.
- `ca268ed`: read-only diagnostic collection, offline report comparison and
  archive observations; 72 tests passed on a clean Linux source copy.
- `f65d68a`: an uncertain reset keeps the controls locked and shows how to
  reconnect. Five disposable Linux Note recovery scenarios passed, including
  user services, rollback and fresh protected-package approval. The separate
  working-tree panel run passed all 1,006 tests, type checking and build;
  the reset component accounted for eight tests. No device reset was run.
- `68a7d42`: source-only application examples, the packaging helper and
  checks for missing, revoked or unavailable access. In an isolated Linux
  copy, 236 tooling/library/worker tests and 21 scaffold/starter integration
  tests passed. The starter UI passed 19 tests. All five Note recovery
  scenarios also passed with this packaging helper and the recovery changes
  together.

CAP15 remains parked: the Devices link, OS login/certificate component,
tests and translations are the only local source left outside these commits.
Next decision: whether to share these commits for CI independently of CAP15.

**First cleanup slice verified against the installed pilot archive:** the three
Core files for consent preview/connector settings match its contents; the two
admin dialogs, connector client and labels, and Extensions view match its build
sources. All 39 built UI files also match the archive. Comparing all 1,807
entries with the public x86-64 kit found no other product payload changes.
Keep the four direct regression files with this slice: `test_application_connector_settings.py`,
`ApplicationAuthorityDialog.test.ts`, `ApplicationConnectorSettingsDialog.test.ts`
and `Extensions.component.test.ts`.

**Second cleanup slice verified:** compared the public ARM64 archive, both
successive local kits and their retained post-deploy file hashes (no Pi access).
Across all 1,807 entries only `backend/artifacts/{api,compiled_ui}.py`,
`backend/system/diagnostics/catalog.py` and release metadata changed. Take
the **later** versions of those three modules once. Their contents and four
regression files match the [143-test Linux gate](../.runtime/cap-batch-1124/gate.json);
no local authoring/diagnostics CLI edits were part of that gate.
The two slices have no overlapping product paths: [exact selection, 11 source
files and 8 test files](../.runtime/core-cleanup-map/scope.json).
Two of those regressions are new files: `test_package_admission.py` and
`test_ui_build_failure_cases.py`. Keep them with the existing module-package
and installation-compatibility test edits; a tracked-only diff omits both.
New combined source check: **48 passed, no skips** (Linux x86-64, non-root,
no external network); package admission, UI build refusals, and connector
settings/consent on the clean tag plus exactly those 19 files. This was not an
installed update or a frontend rerun.

**Combined installed rehearsal before the cache fix.** Two isolated
x86-64 copies of the published 0.3.17 Monitor pilot used the real installed
updater, a local test catalog and the same scope-selected archive
(`845397ef06b9…`, local-only). The update preserved the package, saved settings
and approvals. The already-open Firefox tab showed a fresh Coinbase quote
(59,188.20 → 59,252.74 USD); the new Extensions page offered **Open**.
An ordinary reload of `/monitor` still used the previous interface. No request
for that page reached the server during the reload, while the new Extensions
page fetched the candidate bundle. Reproduced with a correctly ordered archive
timestamp; disabling cache was not used to pass the check.

Forced post-health failure restored the published files and 0.3.17. App data
and the owner's permission survived; the old execution session received 409 and
needed a new review. Its last price remained on screen until reload; no new
sample was observed. Separately, the restored web server returned 304 for
`/monitor` with the candidate's later Last-Modified date, although its HTML
differs. [Installed and browser evidence](../.runtime/combined-update-dated/result.json).
No Pi access, Monitor change, public release or production catalog test.

**Admin entry cache fix — verified locally, with a one-time 0.3.17 limitation.**
Only `components/admin_web/server.py` changed in the candidate product payload
versus the combined rehearsal. The root, explicit index and history routes send
the current HTML with no storage or date validator; versioned assets retain
conditional caching. All 24 admin-web tests passed on both Linux and Windows.
Two isolated installed Linux copies and headed Firefox with a native F5
confirmed data/rights retention on update and a tab loaded **during** the
candidate's lifetime returning to the public shell after forced rollback.
A separate same-URL Firefox control using the archived handlers and UIs passed
both directions from pages served by the fix, including programmatic reload.
Public 0.3.17 can still reuse its own already-stored page without a request;
native F5 alone did not migrate that tab. Opening `/monitor?check-update` on
the same device loaded the installed candidate without clearing browser data.
[Browser and install evidence](../.runtime/admin-shell-cache/result.json) ·
[user instructions](INSTALLATION_GUIDE.md#if-a-browser-tab-still-shows-the-old-panel).

**Pilot source candidate prepared; first-upgrade exception accepted.** Frozen
on public `v0.3.17` (`fb18c38`): 12 product files, 9 regression files (including
both additions) and only the browser-reload paragraph from the installation
guide. Other guide edits, separate CAP work and handoff notes are not in the
candidate. The [reviewable patch](../.runtime/pilot-release-candidate/core-pilot.patch)
applies with strict whitespace checks to the baseline; the
[source archive](../.runtime/pilot-release-candidate/core-pilot-source.tar.gz)
(`c97a6c68edf4…`) is the same tree. [Exact scope and hashes](../.runtime/pilot-release-candidate/manifest.json).
This is source, **not** an installable archive; the public version is unchanged.

Fresh [admin UI check](../.runtime/pilot-release-candidate/ui-check.json): 111
tests, type check and production build passed; all 39 built files match the
installed browser rehearsal byte for byte. Fresh [Linux Core/web check](../.runtime/pilot-release-candidate/linux-check.json):
273 passed, no skips, on the same source archive as a non-root user with only
loopback networking. Reuse the installed update/rollback and legacy-tab
observations above for the matched runtime code; no new Pi or public artifact test.

**Pushed to main:** `a3526de`, parent `fb18c38`; exactly the 22
candidate files. The committed tree matches the [independent Git check](../.runtime/pilot-release-candidate/git-review.json)
(`99f12cc1dc6617f1d69b795fa50c3e3ba55f6b7c`), so the checks above are
reused. [CI #235](https://github.com/ldobranov/3mm/actions/runs/45679375574)
passed on the first attempt: frontend and Linux Python checks passed; the
development tooling group was not selected. Only this commit was pushed.
Separate local work was not committed. On Nov 26 the version-only child `387011e`
passed [CI #236](https://github.com/ldobranov/3mm/actions/runs/45760509543).
[Release #80](https://github.com/ldobranov/3mm/actions/runs/45764378262) built the assets twice and published stable `v0.3.18`.
All three public manifests identify that commit; the five archives and three manifests match GitHub's SHA-256 digests in `SHA256SUMS`. No Pi deployment.

## Pilot evidence and remaining friction

- **Local Core fix: permission review after rollback (not released).** The first-review
  defaults no longer replace a missing/unverifiable prior selection. During explicit
  same-installation key recovery, Core can preserve evidence of a verified historical
  grant solely to suggest unchanged connectors for the same installed package. The
  grant and native review are not renewed. Without verifiable history (including
  recovery with an older Core), no previous connector is preselected.
  On a fresh private x86-64 copy the published updater rolled back to 0.3.17;
  only the three changed Core modules were applied to the running service for this
  check. After key recovery the [Firefox receipt](../.runtime/review-choices-lab/rollback2/preview.json)
  and [dialog](../.runtime/review-choices-lab/rollback2/preview.png) show Coinbase
  checked, CoinGecko offered but unchecked and the owner's existing configuration
  permission checked. No approval request; access remained ineffective. Package,
  settings, user permissions and historical grant/native review matched the rollback
  snapshot; the private test guests were stopped. No Pi or Monitor changes.
  Verification: 227 current cases passed across runs. The broad Linux run had
  223 passes and one superseded assertion expecting a preview for a physically
  missing enforced grant. Its [two replacement cases](../.runtime/review-choices-lab/damaged-grant.xml)
  confirmed refusal for a missing row and empty choices for an invalid seal.
  Both environment-specific skips passed separately (foreign Linux UID and
  Windows refusal). No product code changed between these runs.
- **Published 0.3.18 installed check, Nov 26:** the installed 0.3.17 updater
  staged and applied the public x86-64 archive (`e19bb472e72d…`). Catalog and
  download transport used copies of the real GitHub stable responses/artifact in
  the private guest; the market feed was live HTTPS. [Firefox evidence](../.runtime/public-0318-monitor/forward2/after.json):
  the same tab displayed a later Coinbase BTC/USD sample, 60,557.80 → 60,535.54.
  The fresh URL loaded the new interface. Monitor package, persisted settings,
  configuration, user permission, native review and application grant were unchanged.
- **Automatic rollback:** a test-only startup refusal for the new web service
  triggered the real installer's rollback. Core, Agent and Web recovered on
  0.3.17. Settings, package and recorded permissions survived, but the execution
  authorization epoch changed: the [old tab received 409](../.runtime/public-0318-monitor/rollback2/after.json)
  and retained only its last value until reload. No reapproval was performed.
  This was neither a manual downgrade nor an ARM/device test.
- **Follow-up on the same 0.3.17 rollback copy:** before any permission change,
  the persisted Monitor settings, package, and owner permission matched the
  post-rollback snapshot. Extensions → Application access refused the preview
  with HTTP 409 `review_key_recovery_required`; the read-only Core status
  returned `recovery_required` and the page offered **Restore application access
  reviews**. This replaces the installation-wide review key; it is separate
  from granting Monitor access. With owner approval **on the test copy only**,
  the admin UI recovered the key without granting permissions. A separate UI
  review for the same Monitor 0.8.4 package then submitted only
  `connector:coinbase` and `monitor_configure` (the initially selected
  CoinGecko scope was unchecked). Core returned 200, saved and effective.
  The [Firefox result](../.runtime/public-0318-monitor/rollback2/reapproved-monitor.json)
  showed a fresh live BTC/USD quote of **60,408.22**, received 27 seconds after
  approval. Stored and displayed settings matched the previous revision and
  hash; user rights, package, instance and configuration were unchanged. The
  temporary feed was closed and the same test copy stopped. No Pi access.
- Standalone Setup → first login → upload → activate → review → **Open** → live
  Coinbase quote **BTC / USD 59,029.96**. Both missing connectors were named
  and their HTTPS addresses explicitly confirmed. Only `connector:coinbase`
  and the owner's `monitor_configure` were approved; saving an address did not
  grant access. [Result](../.runtime/monitor-guided-final/result.json) ·
  [address on a phone-width screen](../.runtime/monitor-guided-final/suggested-address.png) ·
  [Open on the card](../.runtime/monitor-guided-final/active-open.png) ·
  [visible quote](../.runtime/monitor-guided-final/monitor-result.png).
- Evidence for those changes: 106 backend and 123 frontend tests, Vue type
  check and production build passed. These were not rerun for this docs cleanup.
- Opening the access review before activation finished gave a temporary refusal;
  review worked once activation finished. Monitor still requests a display
  device even for web-only use. It is an independent application; do not add a
  special case to Core. ARM/physical display was not part of this pilot.

## Scope decisions to carry forward

- CAP16 is accepted for reviewed v2 status reports; CAP19 for Standalone/Full
  recovery on the trusted LAN; CAP20 for the supported resource profiles.
  CAP21 is closed for the supported authoring profile, not every future app.
  See the [CAP plan](CORE_SIMPLIFICATION_PLAN.md) for boundaries and the
  [authoring guide](APPLICATION_DEVELOPMENT.md) for the supported workflow.
- CAP03/04 upload-contention work is a checked slice, not full CAP closure.
  CAP15 Terminal/Cockpit is parked. Keep the local Devices link, optional
  console, independent modules, and other tools out of the pilot release set
  unless separately selected. Preserve their source, tests and rollback data.
- Product direction: a separate extension marketplace (server and client)
  with sales and 3mm commission. It is distinct from the e-commerce 3mm Store;
  pricing, payments, licensing, review and delivery are not in pilot scope.

Keep this file focused on what changed, where it was verified, and the next
decision. The historical file stays in `docs/` so its relative links keep
their original meaning. `.runtime` receipts are local evidence, not releases.
