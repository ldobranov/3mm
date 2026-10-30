# Core 0.3.3

Core 0.3.3 packages the reviewed Runtime-update and shared-editor work, unified
theme/Header/Menu settings and connector upgrade correction. Bulgarian language
pack 1.0.2 carries the final administration labels. This is a pre-1.0 development
prototype, not completion of every CAP03/CAP09 capability or a sandbox claim.
Publication occurs only after the exact tag's full checks and reproducible builds.

## Changes

- System updates has a separate Platform Runtime card with current/previous
  builds, live feature probes and a candidate prepared from the installed Core.
  Preparation is not activation. Apply needs separate exact-build confirmation
  and current maintenance policy; the privileged worker rechecks the source and
  selection, uses immutable activation/health/rollback and leaves Core running.
- Runtime preparation does not download code, install dependencies, replace
  application-host pins or approve resources. Lost replies retain the original
  request ID for status reads, not another update request. Interrupted operations
  have explicit recovery without replaying application operations.
- Public UI components provide draft forms, searchable single/multiple record
  selection and ordered collections, including keyboard controls and caller-owned
  save/cancel/conflict/unconfirmed states. Reka UI is an internal implementation
  detail; applications retain the public 3mm UI contract and host theme/locale.
- One built-in light/dark theme and one appearance editor replace competing
  prototype defaults. Draft previews are local; Save is explicit. Installed theme
  packages and their preferences remain, as do retired color records in the DB.
- Named menus can occupy header/sidebar/footer regions with independent sticky
  settings. Existing audience, role, route, kiosk, localization and Command
  Palette behavior remains. The page is not remounted when layout changes.
- Header and Menu settings use shared editors, preserve multilingual drafts and
  provide explicit save/discard/delete. Uncertain writes require a saved-state
  read before another mutation. The existing settings API is not made atomic.
- Connector upgrades prefer the exact staged package's sealed registration over
  an older initial-registration marker. Invalid current proof fails closed;
  historical consent is not a fallback. Saved configuration and separate current
  approval remain required. Deployment profile detection uses its canonical file.

## Versions, data and upgrades

Core is **0.3.3**, Bulgarian pack **1.0.2**, Device Protocol **1.0** and
Application SDK **1.3**. Version axes remain independent. Terminal and optional
Runtime/application-host/Agent components are not silently upgraded by this tag.
CAP13 retains its existing local, read-only, one-hop profile and still requires
the corresponding current Runtime/host components and approvals.

BG 1.0.2 includes the Runtime, theme and Header/Menu labels. Existing devices
keep their selected language package; a new bundled version is staged, not
automatically selected or re-enabled. Enable BG 1.0.2 explicitly through
Extensions after upgrade. The earlier local test BG 1.0.1 ZIP remains immutable.
The standalone BG ZIP uses canonical LF source bytes to match bundled release
delivery independently of the developer's Windows/Linux checkout.

There is no new DB migration relative to 0.3.2. Preserve verified database/key
backups and independent component versions. An older Core pointer alone does not
restore a database or those components. No wipe, key reset or automatic resource
approval is requested. See [releasing and device acceptance](RELEASING.md).

## Verification and remaining boundaries

Main commit e615d72 passed [CI run 41031237540](https://github.com/ldobranov/3mm/actions/runs/41031237540):
Linux Python checks, frontend (81 files / 812 tests, type-check and build), and
development tooling. The event-process test fixture now isolates its claim lock
from a multithreaded parent's forked state. An owner-run before/after comparison
reproduced the refusal and then passed five cases, without changing production
deadlines, admission, leases, attempts or retries.

Owner Raspberry trials accepted the limited Runtime web-update path and the
theme/Header/Menu work. They precede this final metadata preparation and do not
claim an installation of the published 0.3.3 artifact. Final metadata/BG package
checks passed: 98 tests on owner Ubuntu/Python 3.14.4, 17.34 s. BG 1.0.2's
standalone ZIP was validated and built without activation. The exact tagged
Release gates remain required; this local run does not replace them.

The tag workflow repeats the configured checks and requires byte-identical
architecture/Node builds before publishing all seven assets. A tag or draft is
not publication. Smoke-test the published Core and selected independent
components after publication, without replacing saved selections or grants.

Full CAP03/CAP09/CAP13, I2C display hardware/CAP14, public Cloud, host/root
Terminal administration, full M21 and WP5 isolation remain separate work.
