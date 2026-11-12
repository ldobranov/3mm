# Application development instructions

These rules apply to this application project, including copies created by
`tools.extension_dev init`. Read this file, the project README and
`development.json` before changing code. Use the current platform checkout's
`docs/APPLICATION_DEVELOPMENT.md` for the overall workflow; run its tools from
that checkout and pass this project's path. Do not assume the project lives
inside the platform repository.

## Scope and ownership

- Implement the requested domain in this application's service, UI and tests.
  The template is a shared demonstration note until you replace its behavior.
- Do not modify Core, Agent or another application to support a concrete app.
  First use a public contract; report a missing generic mechanism separately.
- Preserve unrelated source, installed data, identities and current approvals.
  Development does not authorize reset, deployment, grants, hardware or Git work.
- Keep module ID and version aligned in all three descriptors and the service
  artifact path. Choose a distinct ID/route for a separate product. Never replace
  different published bytes under one version or hand-edit a ZIP.

## Public boundaries

- Service imports use its own package, the standard library and supported public
  `packages.application_sdk` / `packages.protocol` interfaces in this profile.
  Do not import private `backend`, `agent`, `components`, `deployment` or `tools`.
- UI imports use `vue`, `@platform/ui/v1`, `@platform/application-ui/v1` and local
  application files. No removed `three_mm_*` / `@3mm/*` imports, Core stores,
  router, credentials, private frontend aliases or a second Vue runtime.
- UI calls use the declared generated client. Regenerate after descriptor/version
  changes; never edit generated methods or cast away a mismatch to make it pass.
- Resolve configured resources through SDK discovery. Device selection, provider
  availability, human access and native-code/resource approval are distinct.
  Never hardcode a device, open Core's database or bypass access through direct
  HTTP/GPIO/I²C. Stable operational identifiers are not cosmetic branding.

## Data and recoverability

- Declare bounded operations, audiences, permissions and idempotency. Derive
  identity from the supplied context; check domain rules and current permissions.
- Use supplied application storage and explicit forward migrations. Test clean
  creation, reopen, failed migration rollback and retained data on upgrades.
  Do not silently drop tables, reset data or change prior applied migrations.
- Keep transactions short and exclude network/provider waits. Optional provider
  failure must not disable unrelated own-data operations.
- Commands keep one original request ID and actor-scoped durable receipt.
  Changed input under the same ID refuses; shared edits use expected revisions.
  Retain drafts on refusal. A 409, timeout, `not_found` or lost reply alone never
  proves non-execution or authorizes an automatic replay with another ID.
- Separate normal controls from diagnostic details. Use explicit unavailable,
  denied, conflict and unconfirmed states; do not report them as success.
- Use bounded background work and intervals, not a busy loop. Declare scheduled
  work/events through their public contracts. No effects on preview or route load.
- Do not put personal data into this demo. A real product needs its own data
  classification, retention/export/erasure policy, quotas and privacy tests.

## UI and checks

- Use existing themed controls and scoped `--ui-*` tokens. Preserve drafts while
  locale/theme changes; read presentation from the public host and clean up
  subscriptions/timers on unmount. Check EN/BG, light/dark, keyboard and narrow UI.
- Pick single/multiple selection according to the actual data, not convenience.
  Inspect public component props instead of guessing or importing private ones.
- Keep tests, preview scenarios, generated types and declarations in sync with
  real behavior. Never skip denial/revocation/provider cases to obtain a pass.
- Use the existing Python/Node/locked frontend/compiler toolchain. Do not install
  dependencies or share native Node modules across Windows/Linux implicitly.
- From the platform checkout, replacing these path placeholders:

  ```text
  python -m tools.extension_dev catalog PATH_TO_PROJECT
  python -m tools.extension_dev generate-client PATH_TO_PROJECT --replace
  python -m tools.extension_dev preview PATH_TO_PROJECT --frontend PATH_TO_FRONTEND
  python -m tools.extension_dev check PATH_TO_PROJECT --frontend PATH_TO_FRONTEND --output OUTPUT_OUTSIDE_PROJECT/app-1.zip
  ```

  Generation is needed when declarations changed; preview is a disposable
  simulation, not a running service or authorization proof. Stop with Ctrl+C.
  `check` produces new files only; inspect its report/log and exact package hash.
- For an update, preserve the previous exact ZIP and use
  `check ... --previous-archive OLD_ZIP --output NEW_ZIP`, plus `compare OLD_ZIP NEW_ZIP`.
  Adapt the upgrade fixture to real domain data/receipts. No previous archive
  means no historical-upgrade proof. Unsupported profiles need separate checks.
- Report changed behavior, executed/reused checks, exact artifact identity and
  remaining limits. Local trusted-code tests are not isolation or live acceptance.
  Upload/configuration, exact-code consent and activation remain separate owner
  actions in the admin panel. Do not perform them unless explicitly requested.
