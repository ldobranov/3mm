# Current working state

Updated: 2026-10-29. Start here; follow linked details only as needed.

## Active task and next result

- **CAP09 shared editing slice accepted on Raspberry, 2026-10-29.** Owner completed
  the agreed checkpoint: Core/CAP03 `722c287`, deploy-profile fix `988f9e3`, BG
  1.0.1 `e375cad` (current main). Read-only Git log confirms those three commits;
  unrelated WORKING_STATE notes remain dirty as intended. No agent commit/push.
  Owner approved Reka UI and retained the workflow: agent prepares source,
  owner runs tests. Bounded result: public `UiEditorForm`, `UiRecordPicker` and
  `UiCollectionEditor`, additive behind @3mm/ui/v1 with the existing host Vue,
  theme tokens and credentials-free presentation boundary. No server/API/SDK
  production, auth, schema, version-axis, app migration, hardware or device change.
  Editor exposes local draft save/cancel intents, native validity and externally
  controlled busy/disabled/unconfirmed/conflict gates; recovery slot is outside
  the disabled fieldset. It owns no persistence, retries or request identities.
  Record picker wraps the real Reka combobox, supports keyboard/local/external
  search, single/multiple stable IDs, selected labels outside a result page and
  explicit removal. Popup stays inline in its surface/dialog. No automatic
  search/selection mutation on supplied result pages, theme or locale changes.
  Collection uses stable keys, immutable move/remove arrays, caller-owned add,
  min/max limits, keyboard buttons/focus and fail-visible duplicate-key refusal.
  The neutral ui-reference source adds two editing patterns with EN/BG copy;
  it changes only an in-memory draft. Existing compiled UI manifests/versions and
  immutable ZIPs are unchanged; no example package was built/deployed.
  Approved Reka is pinned to 2.11.0. Registry metadata was read and both lockfiles
  generated using npm 11.17.0 and canonical pnpm 10.13.1 on Windows/Node 24.19.0,
  lockfile-only with dependency lifecycle scripts disabled. No node_modules
  installation, test, type-check or build was run by agent. npm also updates the
  shared Floating UI resolution; pnpm peer-context normalization is recorded in
  its generated lock diff. Existing dependencies' test evidence is NOT claimed
  for this new library/code. The owner has now completed clean Node 22/pnpm
  10.13.1 frozen-lock installation, all frontend tests and type-check/build, with
  exact evidence below; canonical CI remains. The compiler still disallows direct `reka-ui` imports;
  one refusal case was added without changing its production allowlist. Owner
  selected Python checks: backend/tests/test_compiled_ui.py and
  backend/tests/test_ui_reference_package.py (no broad runtime rerun needed for
  this presentation-only slice). New UI regressions and public export/consumer
  checks are included in the owner's passing full frontend run below. Visual light/dark/390px/keyboard and real prebuilt
  import-map delivery remain after owner build/deployment approval. Barsy and
  Crypto Monitor source and devices were not changed; their adaptation follows
  review of these controls and agreement on their independent app versions.
  Ignored .runtime/cap09-editors/check.py reuses dev-lab verified unpack and
  isolated test state. Owner invokes it with the existing unprivileged Ubuntu
  Python and existing Node 22 directory: clean pnpm 10.13.1 frozen install, all
  frontend tests, type-check/build, then only the two Python UI modules. It writes
  logs/JUnit in its private /tmp copy, never the workspace node_modules or live
  installation. Owner's first runner preflight stopped before any install/check:
  its hardcoded historical Node 22.23.3 directory was absent. Read-only Ubuntu
  inspection then confirms /usr/bin/node v22.22.1 and /usr/bin/corepack (also
  /usr/local/bin/pnpm, which this pinned runner does not use). Fixed only the
  ignored runner to discover the existing tools on PATH, retaining explicit
  --node-bin /usr/bin and strict Node-major validation. No system tools changed,
  install or test started; the source checks remain pending owner.
  Owner explicitly confirms Ubuntu is test-only for now, NOT a deployment
  target. Its older installed Core is unrelated to the verified source-copy
  checks; do not update /opt/3mm/current, install services or restart them there.
  Owner's next attempt used source
  `805253bfeae01cb9e7334bbfa6549f08a7271ca61fb79e4732f495d8808915e8`,
  Node 22.22.1/pnpm 10.13.1/Python 3.14.4, run
  `/tmp/3mm-cap09-editors-zc6o_hyu`. pnpm refused before dependency installation
  or tests: frontend/package.json was absent. Agent error: the reused dev-lab
  snapshot was Python-only, not a complete frontend source copy. Fixed the common
  packer with explicit --with-frontend (default Python scope unchanged), retaining
  regular-file/traversal/digest/size/private-state guards and excluding frontend
  build/coverage/cache output. SOURCE_ROOTS consumed by deploy is unchanged.
  Added three provenance/isolation regressions in tools/tests/test_dev_lab.py;
  owner runner now runs those checks before pnpm and refuses missing UI manifest,
  locks or editor sources before any package operation. No check run by agent;
  old incomplete snapshot cannot test this UI and must be repacked with the flag.
  Owner now reports full frontend **78 files / 780 tests passed**, 58.72 s,
  2026-10-29 20:40:01. Vitest stayed in watch mode: the runner incorrectly used
  npm's extra `--` separator with pnpm run. Removed that separator only from the
  ignored runner; no tested application/dependency inputs changed. Owner should
  press q once in the existing watch process so the already-running runner can
  advance to type-check/build and the selected Python UI tests, without repeating
  the successful 780-case run. Those later results are NOT yet supplied/claimed;
  do not reuse the earlier incomplete-archive SHA as this successful run's identity.
  Owner instead reran the runner from the beginning and returned overall success:
  `/tmp/3mm-cap09-editors-2a3uanx0`, exit_code 0, deployment not_requested.
  Read-only inspection of check-1/check-3 logs confirms tooling **13 passed**
  (0.07 s) and full frontend **78 files / 780 tests passed**, start 20:43:45,
  147.09 s. Owner output confirms vue-tsc passed, Vite 6.4.3 production build
  passed (943 transformed modules, 8.00 s), and selected Python UI **13 passed**,
  6 warnings, 2.44 s; JUnit tooling.xml/python.xml under that private run.
  Environment: Node 22.22.1, pinned pnpm 10.13.1, cached Python 3.14.4.
  The verified archive identity is
  `3939d30e21b216285ab39bd7358e148b84ed7eea2437f62dde6f1988de384284`.
  Agent read-only comparison confirms all 1457 manifest source members match
  the completed run's source exactly; no mismatches. No test/build rerun by agent.
  The missing config.json Vite warning is expected in this isolated snapshot:
  live configuration is excluded, normal Vite defaults were used and build
  succeeded. Do not copy device config or change production fallback for it.
  This closes the selected clean-copy automated gate, not whole CAP09, real
  compiled-reference/browser delivery, canonical CI or device acceptance.
  Only handoff/docs edits follow; no execution-input changes or repeated checks.
  Owner now explicitly authorizes Raspberry deployment for visual acceptance.
  Agent still prepares files/commands; owner performs checks and deployment.
  Use the existing standard tools/deploy.py prepare path with aarch64/Python
  3.13/without-images, matching the previous Raspberry full-profile kit; no Agent
  update, version bump, rights approval, reset or sibling-app rollout. Ubuntu is
  only the build/test host, never an installation target. Existing owner proof
  remains valid for unchanged code, but deploy.py's separate npm cache may need
  its own checked frontend build (not a fabricated reuse of pnpm evidence).
  Limit selected Python preparation to tools/tests/test_dev_lab.py and the two
  UI modules already checked; do not request the full backend/runtime suites.
  First handoff is local preparation plus the normal UI-only reference ZIP
  builder. Actual transfer/start follows the ready bundle identity and current
  target/backup preflight; use the standard checksum/immutable installer/rollback
  path, keep the request/key on uncertainty, and do not replay a failed rollout.
  NEXT: owner returns the prepared bundle JSON, then Raspberry rollout and
  visual light/dark/narrow/keyboard review, followed by exact scoped commit review.
  No agent-run preparation/build/test/ZIP/deployment, commit or publication.
  CAP14 and adaptation of the independently developed apps remain out of scope.
  Owner completed standard deployment preparation successfully, 285.795 s:
  key `468e6efe8f771fe91cb274255716225e94da2178460033338345ecc71ef53420`,
  release `local-468e6efe8f771fe91cb27425`, bundle under .runtime/deploy/artifacts/.
  It ran its own npm ci/test/build and the explicit three Python UI/tooling files;
  no full Python selection. Agent read-only hash validation confirms all ready
  payloads, kit and checks.json; kit SHA-256
  `c37c9190b85471acb4d834c7edee7a2fd8caf567c95bee04b0f9f8943066e47d`.
  Manifest is aarch64/Python 3.13, Agent not selected, image_provider false,
  matching the preceding Raspberry kit profile. UI reference ZIP also exists.
  NEXT handoff: owner confirms current backup, verifies the exact kit again,
  records the dispatch key, then uses standard SCP/checksum/deploy_remote start
  --follow to raspberry@rasp-3mm.local. Core/app interruption is expected during
  installation; Ubuntu remains build/test-only. No remote dispatch by agent,
  no installed/visual success yet. On error/lost reply inspect this exact key;
  do not repeat installation or accept a changed SSH host key automatically.
  Owner returned successful Raspberry rollout, 2026-10-29 21:19:17:
  exact key/release above, state succeeded, phase ready; install Core 187.76 s,
  validate/extract 1.201 s, standard worker deactivated successfully. Accept this
  as the Core rollout result, not visual/component acceptance or publication.
  NEXT: owner uploads the already-built UI-only reference ZIP through Extensions,
  enables it and opens /ui-reference as administrator. ZIP SHA-256
  `a3fee93aa5f26c0e76191eaf73a96961f525b97b8df69a1271c3db0c2f059ca1`,
  5617 bytes, module org.3mm.ui-reference 1.0.0. No business service/resources or
  hardware operations; the example edits only in-memory data. If an existing
  same-version package conflicts, inspect instead of deleting/resetting it.
  Visual desktop/light/dark/narrow/keyboard acceptance remains pending owner.
  Owner screenshot at /ui-reference confirms the deployed public editing
  components render in the real Raspberry/Core shell, dark desktop view:
  editor state controls, searchable selection/chip, panel fields, add/remove
  and ordering buttons are present. Search text "asd" retains Article alpha;
  this is the expected separation of search and selected IDs. Treat as initial
  real compiled-UI/import-map/theme delivery evidence, not completed behavior,
  light/narrow/keyboard or contrast acceptance. Muted help text looks faint in
  the supplied capture; verify its readability during theme review before
  declaring visual completion, without guessing contrast ratios from the image.
  NEXT owner manual check: clear search, choose beta with keyboard, edit/reorder
  a panel, verify dirty/save/discard and min/max controls; then unresolved states
  and presentation changes. No application or device mutations by agent.
  Owner then explicitly confirms beta is added and reports the current example
  works normally. Record the real multi-selection smoke as PASS, not evidence
  that open/closed screenshots alone proved failure. Do not repeat that check.
  Explicit unresolved-state, light/narrow and readability review still pending;
  next manual check preserves an unsaved draft through simulated Unconfirmed and
  Conflict, verifies disabled editing/save/discard and explicit Resolve recovery.
  Owner confirms all four unresolved-state manual steps successful ("всичко 6"):
  simulated Unconfirmed/Conflict lock editing/save/discard, preserve the draft,
  and explicit Resolve restores editing with the same draft. Accept this bounded
  real-browser presentation behavior; it is not a real server conflict, command
  reconciliation or new authority proof. Remaining visual gate: live EN/BG label
  switch, light/dark readability (including muted help/placeholder) and 390px
  layout/keyboard without horizontal page overflow or lost draft.
  Owner now confirms the final three requested presentation checks successful
  ("6"): demo EN/BG label switching without lost draft, light/dark readability
  and narrow ~390px layout. Accept this bounded real-device/shared-editor slice;
  do not claim measured contrast ratios, a complete accessibility/browser/theme
  matrix, all CAP09 capabilities, or migrated Barsy/Crypto Monitor.
  Exact commit-scope review is complete, read-only Git at
  e375cad30f8e87415dcefe9ecca2abd7ef08bb03; index remains empty. All 17 changed
  non-Markdown source/test/config/lock files match the checked deployment inputs
  byte-for-byte. No blocking finding; no tests/build repeated. Documentation-only
  updates record acceptance and correct the pnpm CLI example (no extra npm-style
  -- separator that previously entered watch mode). Reuse the owner's successful
  automated and device evidence above; no new code/dependency changes follow.
  Proposed split: CAP09 UI/dependency/reference/docs 18 whole files plus only
  this CAP09 WORKING_STATE entry (19 paths); independent dev-lab frontend-snapshot
  tooling/docs 3 files. Explicit ignored allowlist:
  .runtime/cap09-editors/commit-scope.json. Preserve marketplace direction,
  separate CAP13 notes and older approved CAP09/CAP14 direction outside the
  partial handoff commit; exclude .runtime, dist, node_modules, caches and secrets.
  Owner explicitly authorizes the agent to create both reviewed local commits.
  Keep their messages/scope as recorded above; exact commit IDs belong to Git
  history. No new tests are needed for unchanged checked inputs. NEXT: canonical
  CI and any push/publication only when separately authorized; no tag, version
  change or further deployment. Business-app adaptation and CAP14 remain separate.

- **CAP03 Platform Runtime web update: selected checks + owner live switch passed, 2026-10-29.**
  Exact commit-scope review (read-only Git, no staging/commit/push): initially 22 dirty/new
  source/docs paths at HEAD `395b01b316a82bb7bf03bb43a35435773e4648cc`; index empty.
  Proposed split: Core feature 16 whole files + CAP03-only WORKING_STATE fragment,
  separate tested deploy-profile fix 2 files, and newly owner-requested BG 1.0.1
  package/tests 4 files (23 paths total, including the now-modified BG manifest).
  Explicit allowlist is local
  ignored .runtime/cap03-runtime-web/commit-scope.json. Preserve the pre-existing
  marketplace direction and independent CAP13 notes outside this commit scope.
  Owner explicitly resumed language work and requested BG 1.0.1 so the files are
  not forgotten. Updated modules/language-bg/{manifest,language-extension}.json
  to matching 1.0.1; kept manifest v2, language schema v1 and Core VERSION 0.3.2.
  Restore the three formerly deferred files together with this BG manifest to
  a separate language commit scope. Existing selection stays unchanged until
  explicit enable; no automatic activation, upload or device action.
  Owner-run Windows/Vitest 3.2.7 actual Runtime BG/EN i18n: **2 passed**,
  2026-10-29 19:26:04, 2.82 s. Owner-run selected language package/lifecycle/
  revocation group: **4 passed**, 4.23 s, 12 warnings, source
  `7892fae39df337c3e0b98bed1074d3f5628ee691f15c4151dec8ce5a61d7db22`,
  same cached Ubuntu/Python 3.14.4 and dependency digest recorded below; JUnit
  `/tmp/3mm-cap03-runtime-web-uoexfkrn/results.xml`, exit 0.
  Owner generated the validated data-only BG 1.0.1 ZIP at ignored
  `.runtime/cap03-runtime-web/packages/language-bg-1.0.1.zip`: 117743 bytes,
  SHA-256 `f060633b95f99d1b338be7262b9c3accbfc6e947360b87af24eafbcc5025467e`.
  Agent read-only hashing matches that size/digest. Activation was not requested;
  no device-language delivery/selection is claimed. Existing 24 UI cases/type-check/
  build and Runtime evidence are reused for unchanged UI/code/dependencies, not
  reported as one new 26-case run or a new full release gate.
  Ignored prepare-language.py requires approved 1.0.1 and validates with the actual
  Core package validator; immutable existing output must match or it refuses.
  Agent static AST/JSON/version consistency checks only; no package generation or
  runtime/frontend test execution. The new owner language checks and ZIP are green.
  Review found P2 in Runtime card: same IDs/digests with compatible=false after
  Refresh leave reviewCurrent true and acknowledged Confirm enabled; submit then
  exits at !canApply with no request or clear modal feedback. Server/submit denial
  is intact. Owner then explicitly requested this fix and owner-run test commands.
  Implemented UI-only fix: Confirm also checks current action eligibility;
  a trusted refreshed denial invalidates the review, clears resource/maintenance
  acknowledgements and shows existing review-changed feedback. The invalidation
  is sticky until explicit close/reopen even if eligibility returns; no automatic
  reapproval, resend or request ID replacement. Local sending/unconfirmed outcomes
  do not trigger this refresh invalidation. Existing submit and server checks stay.
  Added three parameterized regressions: compatibility=false, candidate already
  current, and recovery required, with unchanged IDs/digests, zero POSTs, cleared
  acknowledgements and fresh review requirement. Owner then ran the scoped checks
  on Windows, 2026-10-29 19:13:50: Vitest 3.2.7 **24 passed** (13 Runtime card,
  11 SystemUpdates), 4.91 s; vue-tsc/type-check passed; Vite 6.4.3 build passed,
  309 modules, 7.92 s. This verifies the Confirm fix and all three regressions;
  P2 is closed. No language test was included or claimed in that 24-case run.
  Current selected 11 UI/direct-dependency/lock raw-byte input identity is
  `7f0cba69f3131de611eb5172346a063816305f2c5721ba25025d3332eb254f6d`.
  Read-only hashing after the result confirmed these inputs unchanged; only
  handoff/plan/scope metadata edits follow. No agent-run tests/build.
  Historical 23-pass UI/type/build evidence below predates this fix and is not
  claimed for new code. Runtime/API/tooling/device evidence is unchanged/reused;
  no Python reruns, additional device rollback/Apply, dependency installation,
  Git staging/commit/push or Core version changes by agent.
  UI visual check and canonical CI remain. Deploy preparation inventories dirty
  AND untracked source, not only staged paths: a commit allowlist does not filter
  a later local deploy kit. The resumed language files now have the separate owner
  checks above; their selected device version still requires explicit enable.

  The revised UI including Confirm is now owner-tested, NOT yet deployed.
  Matching current/candidate build is shown as already current before
  the stale-binding branch; canApply/authority/worker/Runtime paths are unchanged.
  Status-provided operation ID remains visible after page reload; a locally
  unconfirmed request ID takes precedence over a different server operation.
  Candidate missing declarations now say "Not declared in the Core contract",
  separate from live "Not advertised". The card opts into existing ui-v2 controls,
  theme tokens/disabled styles/dialog styles and narrow-width hash wrapping.
  Added two Runtime-card cases plus actual BG/EN i18n/dialog cases; expanded the
  existing language-delivery check and added generic bundled-new-version staging
  / explicit selection regression. No language lifecycle production code changed.
  Owner's earlier language deferral is superseded by the explicit BG 1.0.1 file
  request above. Source versions are now 1.0.1; Core stays 0.3.2. Existing device
  language package/selection is not silently replaced. Owner completed ZIP generation
  after targeted language checks as recorded above; upload/activation is not claimed.
  Owner-run Windows results for the revised UI, 2026-10-29 18:37:08: Vitest 3.2.7
  **23 passed** in 3 files (11 SystemUpdates, 10 Runtime card, 2 actual BG/EN i18n),
  24.64 s; vue-tsc/type-check passed; Vite 6.4.3 production build passed, 309
  modules, 6.83 s. Selected 14 UI/translation/direct-UI-dependency/lock input
  identity (sorted path->raw-byte SHA JSON) is
  `b904f0596c1ca6cde3e81069d8703f77ac64eab1af949d65401ed756dd84a753`.
  No executable inputs changed after this owner run, only handoff/plan docs.
  This is new UI evidence, not a new full backend/release test run. The added
  language-delivery backend case was not included in that earlier UI run; it is
  now covered by the separate owner four-case language group above. Existing
  Runtime/API/tooling/device evidence remains
  applicable to unchanged execution logic; do not repeat the accepted device
  rollback/Apply just for these UI changes. Light/dark/narrow visual review
  of the updated UI remains after an explicitly requested deployment; live BG
  delivery/visual acceptance awaits the new package's explicit enable. Agent AST/JSON and whitespace
  checks only passed; no pytest/Vitest/type-check/build/package generation run.

  Owner explicitly requested implementation files and commands, with tests run by
  owner. No agent-run pytest/Vitest/build, commit, push or device operation.
  Updates gains a separate Runtime card and admin-only typed no-store API.
  Candidate source is ONLY the root-owned installed Core; no caller source/path,
  upload/URL, dependency installation, bootstrap, host updates or grant changes.
  Real Core SO_PEERCRED is required at the root helper. Fixed bounded systemd
  workers reuse RuntimeStore/global release lock, recheck source/Core generation,
  current Runtime and exact candidate. Preparation cannot switch a service;
  Apply has separate exact-build consent and existing maintenance policy.
  One root-owned candidate/operation is kept; same accepted current request is
  not rescheduled. Scheduling loss stays unknown, status polling never POSTs.
  Interrupted workers/transactions require explicit recovery without update replay.
  Read-only status does not initialize directories or change pins. Core, other
  services, application hosts, grants, DB schema and version axes are unchanged.

  Prepared tests cover real disposable artifacts/Runtime transactions, failed
  candidate rollback, interruption/recovery, queued Core drift, tampered archive,
  stale/conflicting requests, helper peer/scheduler boundary, auth/revocation,
  API audit/redaction, LAN-safe request IDs and explicit browser consent/no replay.
  Owner commands: PowerShell
  `.runtime/cap03-runtime-web/test.ps1 -Group backend`, then `-Group packaging`,
  then `-Group frontend`. Backend/packaging use dev-lab verified source snapshots,
  private /tmp data and the existing cached unprivileged Ubuntu Python (override
  with -LinuxPython); frontend uses existing locked Windows dependencies.
  Scripts install nothing and never deploy. Full canonical CI/release and
  EN/BG/light/dark/narrow-browser review remain required; no visual pass claimed.
  Agent static checks only: Python AST/JSON syntax, sorted unique deployment
  required paths, PowerShell runner parser and diff whitespace passed. No source
  module/test execution, TypeScript check, build or browser run is claimed.
  Owner-run backend on source
  `9671eee58d658f90ca6a5fdaf0d269960e917f5e0aafbc76d9a53098ccc52357`,
  cached unprivileged Ubuntu/Python 3.14.4, unchanged dependency digest
  `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`:
  **107 passed / 1 failed**, 8.84 s, no skips. JUnit
  `/tmp/3mm-cap03-runtime-web-smku8jhc/results.xml`. Failure was the NEW test's
  `with socket.socketpair()` tuple, before any handler/peer assertion executed.
  Fixed only the fixture to enter both individual socket context managers; no
  production, dependency, contract, or assertion change. Runner now offers
  `--group peer` for this ONE case. Reuse the other 107 owner-run passes; do not
  rerun the whole group or call the repaired test passed before owner results.
  Owner then ran the repaired peer case on source
  `8affaa84808512f1918921b361440677f27754e0cdef81f5af2abfdbf84bd74f`:
  **1 passed**, 2.10 s, `/tmp/3mm-cap03-runtime-web-tg7jnn98/results.xml`.
  Reuse the other 107 passes above; not a new single-run 108-pass claim.
  On that SAME snapshot/environment/dependency digest, owner-run packaging:
  **141 passed**, 4.98 s, `/tmp/3mm-cap03-runtime-web-hxyp_p_a/results.xml`.
  Covers release builder, WP4 release contract and frontend-access/installer
  preservation. No skips reported. Only handoff/ignored-runner edits follow.
  Windows execution policy blocks .ps1 loading; owner uses direct console
  commands without changing policy. Frontend commands use npm.cmd, not npm.ps1.
  Owner-run Windows frontend: **19 passed** (11 SystemUpdates integration/catalog,
  8 Runtime-card cases), Vitest 3.2.7; vue-tsc/type-check passed, Vite 6.4.3
  production build passed (309 modules, 6.77 s build). Current 230 tracked/new
  frontend source/config/lock files plus Bulgarian language input identity:
  `47c9ad138436d9f6425454f5a480e6a3abad7976efde2ba155b9134f3e3c4790`.
  No task executable inputs changed after these owner runs; subsequent edits
  are handoff/plan documentation only. Preserve unrelated marketplace notes.
  All selected owner-run automated groups are now green with the explicit reuse
  above; not a new full canonical Python 3.13/Node 22 CI/release run and not native
  root/systemd or final-device acceptance of the new web updater.
  Owner attempted local kit `e676df64e7c419f16121cdd76d347ff1f060cedd410cbc14d0c3cd5c891d34c6`:
  preparation reused frontend `7a5b2100ad71` and exact checks `280a9b2173da`;
  transfer succeeded, remote controller rejected profile/architecture/Python
  BEFORE recording/scheduling a job or invoking the installer. No successful
  deployment is claimed. The separate deploy.ps1 call was blocked by Windows
  execution policy. Do not change policy or repeat deployment before inspection.
  Demonstrated tooling blocker: dispatch required `profile: full` in published
  .3mm-release.json, but build_release does not emit that field. Fixed local
  deploy_remote to read the installer's canonical .3mm-install-profile marker
  instead (no fallback/inference); missing/invalid/Node markers still refuse.
  Architecture and Python checks remain strict with distinct errors. Added
  published-metadata regression and refusal tests in tools/tests/test_deploy.py.
  Owner-run tooling regression on source
  `970d03e409ea58d6d39c22b5831ccf74caf8b087e9d72b4bf73776f25ca3e2d1`:
  **43 passed**, 3.53 s, no skips, same cached Ubuntu/Python 3.14.4 and dependency
  digest above; JUnit `/tmp/3mm-cap03-runtime-web-_842pqrd/results.xml`.
  Owner read-only target preflight: installer marker `full`, machine `aarch64`,
  sudo system Python `3.13.5`, Core `/ready` ready. These match the selected kit
  target; no device operation by agent. Existing CAP03 runtime/frontend evidence
  is unchanged; the old immutable kit still contains the faulty controller and
  must not be reused. A fresh kit must contain the repaired controller; local
  preparation can select only tools/tests/test_deploy.py, reusing other unchanged
  CAP03 evidence above rather than rerunning backend/packaging groups.
  Owner then prepared fresh local kit
  `18ce79ec288d39f485ebd77ddba1d33d92cf3d84a4b853ba5fa05131e30b4853`:
  targeted deploy-module verification succeeded; frontend `7a5b2100ad71` reused,
  preparation 65.264 s. Local artifact at .runtime/deploy/artifacts/<key>/;
  kit SHA-256 `a72098e1b99422acba3ce0e64f5656774683c03f3253b12468d2ff70ce9cc163`.
  Agent read-only file hashing confirms ready/checks/file digests, the packaged
  controller equals current source with LF normalization, and no Agent rollout
  is selected. This is NOT an installer/device acceptance; upload/start commands
  handed to owner, no remote action by agent and no new source/build/test run.
  Owner returned detached deployment success, 2026-10-29 11:20:07 rasp-3mm:
  key above, release `local-18ce79ec288d39f485ebd77d`, state `succeeded`, phase
  `ready`; installer 182.29 s, validate/extract 1.051 s. This controller only
  reports success after its final Core/host/selected-component readiness checks.
  The supplied phases contain no native-host rebuild/publication or Agent update.
  Local CAP03 Core deployment is accepted as successful, NOT the independent
  Runtime web update itself. No published release/version bump is implied.
  Owner Prepare-only device acceptance PASS: before/after Core MainPID `820827`,
  ActiveEnterTimestamp `2026-10-29 11:19:36 EET`, Runtime current `3af4df43...` all
  unchanged. Owner screenshot confirms live Ready, four displayed contracts 1,
  operation Succeeded/candidate_prepared, candidate build equals current exact
  `3af4df434255fa2700f21ffc9b4510382bb5f55d28bc4b248ffc271fd3429e80`,
  candidate SHA `5464bed8dfcb0a0b04f1d3af0b8c6ecdf4d4b972bb356e4e3be2750d8e6e66f3`,
  and explicit already-current/no-update-needed message. This proves installed
  preparation/no-switch/no-op, NOT an actual Apply/switch/rollback test.
  Partial visual evidence: dark desktop layout with BG surrounding Core UI;
  Runtime card remains English fallback. Code inspection: languages are pinned
  data packages, bundled same-version seeding never overwrites an existing
  selection; actual selected device language package not inspected. Track BG
  delivery before claiming translated-device acceptance, no language mutation.
  Candidate Event delivery is Not advertised while live status is 1: the strict
  installed source contract omits event_delivery_contract; candidate reads only
  declarations, live status reads the socket. No missing live events is proven.
  Owner explicitly consented to the controlled Raspberry Runtime-only rollback
  and subsequent web Apply test, acknowledging SDK interruption/CAP13 temporary
  unavailability. Hand off standard installed platform_runtime_component rollback
  with exact current `3af4df43...`, previous
  `3400e4bdb089776b75cdc1b953ae7809de94dfbb7f60f267b7d581b8ee1efe14`,
  installed local Core release, active services and no-pending-transaction guards.
  Record Core PID/start time across both switches. CLI uses the existing global
  release lock, RuntimeStore validation, readiness and automatic failure rollback;
  no hand-edited symlinks, service/Agent/host/grant changes or reset.
  After successful rollback, refresh UI and Prepare a NEW candidate: the previous
  candidate bound current_build_id to `3af4...` and is deliberately stale. Review
  exact `3af4...` build and confirm Apply once. Keep request ID/no automatic replay.
  Owner returned successful standard Runtime-only rollback to exact `3400e4bd...`,
  status ready, Core PID `820827`, same `2026-10-29 11:19:36 EET` start time,
  Core `/ready` ready. Subsequent screenshot confirms fresh web preparation on
  `3400...` with compatible `3af4...` candidate and declared query contract 1;
  live old build correctly advertises no query contract.
  Owner then returned actual web Apply PASS: operation Succeeded/runtime_updated,
  exact current `3af4...`, previous `3400...`, Runtime Ready with all four displayed
  live contracts 1. Console independently confirms Core PID/start time unchanged
  across both switches and Core ready. This closes the agreed Raspberry Prepare /
  same-build no-op / consented CLI rollback / distinct-build web Apply smoke,
  not whole CAP03 or forced-failure/interrupted Recover on the live device.
  The post-Apply stale-candidate message reflects its old current_build_id binding,
  not a failed update; no repeat Prepare/Apply is needed for that message.
  Owner-run post-update CAP13 alpha SDK query PASS: status `returned`, query v1,
  binding `directory`, exact provider `2aa790360ad8655de00819d0`, contract digest
  `187075c507c734a026dc0d2880a3d0cbb01b0fb6e724faa3fe207a4b432aee2f`,
  found true, Unicode label `Здравей · CAP13 alpha`, application caller
  `13642b0f10fe9217fccb93fa` / `org.3mm.cap13-test-consumer`, human_delegated false.
  This proves one real existing application query after the Runtime web switch;
  it is not full SDK-family/load conformance or a repeat of the whole CAP13 smoke.
  The agreed bounded Runtime-only web-update happy path is now functionally
  verified on Raspberry, including application traffic after reconnection.
  NEXT: owner-run three scoped commits; BG 1.0.1 checks/validated ZIP and revised
  core UI checks are green. The ignored stage.py helper verifies frozen source
  hashes and an empty index, stages only the explicit group, and constructs the
  CAP03-only WORKING_STATE index blob without editing the working file. Owner
  invokes ordinary git commit separately; hooks remain enabled. No push, tag or
  release is included. CAP09/Reka and unrelated notes remain outside this group.
  No further
  device mutations or repetitive checks are needed for the accepted happy path.
  Updated-UI visual review, exact commit scope and canonical CI still remain
  before an explicitly authorized release. Reuse unchanged automated evidence;
  no new agent-run tests/build/device action, commit or push.
  Preserve the accepted CAP13 device profile below.
  The only pre-existing dirty file was this handoff.

- **0.3.2 CI regression repair, 2026-10-28.** Owner reported failed main CI and
  explicitly authorized fixing, committing and pushing the correction. Run
  `40764987993` on `c5a2fa2` passed frontend/tooling/selection and compiled-UI
  integration, then stopped after **753 passed / 3 skipped** at
  `test_application_connector_settings.py::test_own_sqlite_bootstrap_and_existing_registration_keep_sealed_provenance`.
  This is a CAP13 integration regression, not evidence of a transient runner.

  `_subject` now resolves query metadata from `_PreparedAuthority`; two inert SQL
  writers still supplied `(pin, package)`, producing an AttributeError hidden by
  the normal `registration_unavailable` refusal. Updated BOTH current callers:
  first registration and candidate adoption use the prepared object from their
  already verified package/pin. No tuple fallback, extra package I/O under guard,
  permission/trust creation, registration provenance bypass or weakened test.
  Other `_subject` consumers use `_prepare` or `dataclasses.replace` and were
  inspected. No frontend/SDK/runtime/schema/version/workflow changes.

  Exact failing case reproduced before the fix on source
  `b77bd5d3cd20575219cbfe9d2d74b1e4928e796688e564805f921c9302378c0a`, unchanged
  cached Ubuntu/Python 3.14.4 dependencies; JUnit
  `/tmp/3mm-public-capacity-ehyptp8d/results.xml`. Candidate executable snapshot:
  `a4cc03908542c5a290b7065795fd99f1603c9d12e6eee62fe8e25d5a76048a39`.
  Final targeted connector settings, inert SQL registration and candidate modules:
  **114 passed / 4 real Root-helper skips**, 146.79 s, unchanged Ubuntu/Python
  3.14.4 dependency SHA-256
  `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`.
  Existing tests cover no execution/grant, sealed provenance, foreign/revoked
  actors, changed keys/configuration, historical receipt replay and rollback.
  JUnit: `/tmp/3mm-public-capacity-1w6wa6wc/results.xml`. A preceding broader
  bounded run had no final JUnit and is NOT counted as a pass. Unchanged hosted
  frontend/tooling and earlier CAP13 results are reused, not rerun or called a
  new full CI pass. Only handoff/changelog edits follow the checked source.
  Staged scope is two production callers plus these two documents; whitespace
  passes. Push is owner-authorized; canonical CI must verify the new commit.
  Preserve all old tags.
  Remote v0.3.2 was absent at inspection; VERSION stays 0.3.2. After push, wait
  for green canonical CI on the NEW commit before tagging it, never c5a2fa2.

- **Core 0.3.2 commit/release preparation, 2026-10-28.** Owner explicitly
  requested the commit and a release command, not push/tag/publication by the
  agent. Scope is the CAP13 local read-only vertical below, its direct consumers
  and checks, plus the previously verified release saturation-test correction.
  Independent Terminal/device work and generated/private `.runtime` artifacts
  are excluded. VERSION is 0.3.2; README/changelog and
  `RELEASE_NOTES_0.3.2.md` describe the exact limits and component requirements.
  No old tag is moved; no dependency/workflow gate, DB or device state changes.

  Before preparation, repacking reproduced checked executable snapshot
  `80bcfbe86dfe25d8b07234bf9142018460524c30d95e3b52565cb3713823d12e` exactly.
  Reuse the attributable checks below; only VERSION/release documentation changes
  afterward. The previously recorded frontend/SDK/Runtime results are targeted,
  not a new full CI pass. Version/build/tag validation is checked separately.
  Preparation checks: Windows/Python 3.13.15, release builder and target WP4
  contract group **105 passed**, `.runtime/cap13-release-prep.xml` (56.55 s).
  Exact reviewed index: 53 source/test/release-documentation paths; no private,
  generated or unrelated files. Staged whitespace check passes. These checks do
  not replace canonical Linux/full release checks or final-tag device acceptance.
  NEXT: owner pushes main, waits for green CI on this exact commit, then creates
  and pushes annotated v0.3.2 on that commit. Tag Release must pass full Python
  3.13/Node 22 gates and reproducible full/Node builds before publication.
  No push, tag, release execution, rollout or hardware acceptance is implied.

- **CAP13 runnable local read-only release candidate, 2026-10-28.** Owner asked
  for a more complete release-ready stage. This supersedes the declaration-only
  and backend-only next actions below. The bounded vertical is now implemented:
  matching local provider/export selection in the common configuration form,
  visible initially-unselected M20 query consent, SDK `platform.query()`, real
  application-host invocation, independent Runtime response wait, and fresh Core
  result authorization. Exact contract/API/rollout limits and usage are in
  `CORE_SIMPLIFICATION_PLAN.md` CAP13; README/changelog label this UNRELEASED.

  No long Core transaction/guard/handler waits for the provider. Runtime receives
  a response-only FD and one-use process-local completion token, no DB/keys.
  Core validates the provider signature/request ID, deadline/schema/size and both
  current package/principal/config/grant bindings before disclosing output.
  Pending limits: 8 global / 4 consumer, response wait <=5 s, no automatic retry
  or durable replay. SDK passes an application caller, not delegated user rights.
  Revoke/renew/disable/drift fence output; they cannot recall already-run native
  code. Query rights never fall back to compatibility/generic effect admission.

  Scope stays one-hop/query-only (<=16 dependencies). No scoped-relational query
  providers, commands, human delegation, entity/deep links, recursive or remote
  composition; full CAP13/M21/WP5 are NOT declared complete. Current independent
  Runtime advertises query feature 1; current application-host/SDK is needed for
  caller context. Core-only deployment does not implicitly update these pins.
  No new tables/migration, credentials, package-specific Core branches or devices.

  Verification, cached unprivileged Ubuntu / Python 3.14.4; dependencies unchanged
  at SHA-256 `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`:

  - Source `cf3dc7510a49b145fc13e2be5f944a3c0798ccbe043b98006f2769cd824562f0`:
    **272 passed / 1 distinct-OS-principals root-proof skip** plus ONE failed test
    assertion: SQL-profile refusal is intentionally exposed by the manager as
    generic `unsupported_authority`, not its private reason. Corrected that
    assertion and separately proved resolver's `query_profile_unsupported`; no
    production denial weakened. Group covers real host + exec'd Runtime, query
    denial/revocation/drift/Unicode/timeout/crash, contracts, resource discovery,
    M20 composition, Runtime artifact/update/rollback and SDK callers.
  - Source `11b19f9bb735782442eac944559b1ec0f8dad1188509f50522942f8cfe5f57f0`:
    **294 passed / 2 skips**, corrected SQL/configuration + shared M20 context,
    sources, subjects, policy, management and consent. Skips: non-POSIX refusal
    on Linux and missing copied Node/compiler for the new cross-language test.
    Its actual HTTP preview was retained and separately decoded with CURRENT
    Windows Node 24.19.0 / installed Vite esbuild + real TypeScript parser:
    **1 accepted / 1 contract-drift refusal**, no projection/selection change.
    This is mixed-platform evidence, not a Linux parser pass. Ignored decoder:
    `.runtime/cap13-preview/decode.mjs`; CI uses the existing locked compiler.
  - Final behavior changes (base listener does not advertise query execution;
    observation preserves the full 96-character authority package version):
    source `02b109e0b087273352c3b5dc41f7f0d7390e97e1b9a7d51ad9edcd0c53786621`,
    **63 passed**, affected transport/resource/SDK/protocol consumers and real
    query. Source `ed7d4258381791d5c316da80f12062ffa674191a0caf4c142940610be37744b0`,
    **8 passed**, explicit reply-FD write denial / invalid envelopes and the
    reproducible self-contained application-host artifact. Only tests and a
    configuration docstring differ from the preceding executable snapshot.
  - JUnit: `/tmp/3mm-public-capacity-{z9nfh6np,x4bh2cmh,caoicxu0,e_2z6p7p}/results.xml`.
    Earlier 78-pass transport/SDK/configuration run overlaps these checks and is
    not added. First test-harness attempts (slow spawn import, graceful stop
    mistaken for crash) were repaired in the fixture; crash uses SIGKILL.
  - Final recovery check: query feature is required by query resource readiness,
    NOT by general deployment health of a previous independently pinned Runtime.
    This keeps rollback available while an absent feature fences new queries.
    Source `80bcfbe86dfe25d8b07234bf9142018460524c30d95e3b52565cb3713823d12e`:
    **3 passed**, actual absent-feature probe, immutable Runtime rollback and
    deterministic/Core-free Runtime artifact. JUnit:
    `/tmp/3mm-public-capacity-z0h0bgk1/results.xml`. Other checked executable inputs
    above are unchanged; only documentation follows this snapshot.
  - Windows Python **3.13.15** / Pydantic **2.13.4**: **122 passed** pure query/
    SDK actor/transport/contract checks, `.runtime/cap13-win-final.xml`.
  - Frontend Node **24.19.0** / installed locked dependencies: **304 passed**
    across all extension authority/settings parsers/dialogs and Extensions view;
    TS + Vite production build passed. A missing BG button label found by the
    first new component run was added before this final pass/build. Real narrow
    browser preview (~401 px), EN/light and BG/dark: optional checkbox, provider
    pins/bounds, long IDs, vertical scroll and wrapped actions visually checked.
    Preview uses fake data/current components, no live approval. No wide desktop
    or physical mobile-device layout claim. All counts overlap, NOT summed.

  Previous unchanged saturation-test fix/evidence below is preserved. No whole
  CI/Release rerun, version/tag change, commit/push, deployment or reset. **NEXT:**
  exact commit-scope review, then owner-authorized commit/version preparation,
  canonical Python 3.13 / Node 22 integration CI and full Release gates, followed
  by owner-run smoke using the exact Core/Runtime/host artifacts. Do not reuse
  or move failed immutable `v0.3.1`; eventual 0.3.2 needs its own new tag.

- **CAP13 M20 backend binding completed locally, 2026-10-28.** Owner requested
  continuation toward CAP13 before 0.3.2. Query dependencies now explicitly name
  two separate manifest string configuration keys for saved provider instance
  (24-hex) and export IDs. Updated current declaration/package consumers together;
  the earlier unreleased dependency shape is superseded, no compatibility shim.
  First consumer profile is query-only, max 16 dependencies and one hop: no other
  resource families/exports; selected providers cannot themselves depend on queries.

  Existing M20 preview/allow and manual review/approve/apply seal authority v12
  `query:<binding_id>:read` resources in the SAME plan/grant/action records.
  Provider must be enabled/active and have a current independently approved M20
  grant. Both principals/incarnations/instances, package/UI digests, exact export/
  contract, provider keyed configuration, epoch and grant revisions are pinned.
  ZIP validation precedes key/guard acquisition; final metadata/grants/configuration
  are reread in the same snapshot. Query scopes start unselected. Drift, revoke,
  disable, stale/corrupt trust, changed bytes/pointers or renewed provider approval
  cannot silently reuse/replace consumer authority. No new tables/migration,
  service start, shared credential or application-specific Core branch.

  This completes only the **M20 backend** slice. Runtime/SDK invocation and
  browser consent DTO/UI remain NEXT; existing strict browser validation rejects
  unknown query resources rather than hiding/approving them. New rights can be
  tested through the admin HTTP endpoint, not yet through the browser dialog.
  Selected saved query rights report `query_runtime_not_connected` / ineffective;
  the generic effect lease refuses them even in compatibility mode. No shell,
  remote composition, user delegation or completed/runnable CAP13 claim.

  Checks: unprivileged Linux/Python 3.14.4, unchanged dependency digest
  `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`.
  M20 consent/management/policy/context/sources/subjects + CAP13 protocol/ZIP group:
  **371 passed / 1 non-POSIX-only skip**, 42.69 s, source `f4528aff01f3d89d805dd617454ccfe8b40ee65fd4ccdc454031ef7e3323866e`.
  After adding the HTTP query-scope parser and final negative cases, **120 passed**,
  25.19 s, source `a6e2e2baa4c5a92762c68812f407877504fcc9cefda70b306efc870de1b2890b`;
  the unchanged pure policy/source/context/management checks above are reused.
  Final additional manual-review/apply case **1 passed**, 3.24 s, source
  `79af32dbc305a5ed150936d1ecf42413040597b424c3d008688b5b1682c7f4a1`.
  Only that test/then documentation differs from the final HTTP-checked source.
  Counts overlap; they are NOT summed or called a full CI/release gate.
  JUnit: `/tmp/3mm-public-capacity-{k2leqx75,53_5c_gd,1uog66is}/results.xml`.
  Initial fixture failures (old SDK declaration and active first manual adoption)
  were corrected in tests, preserving the SDK 1.3/disabled-adoption requirements.
  Whitespace check passes. No frontend build, commit/push/version/tag/deployment.

- **CAP13 first declaration slice, 2026-10-28.** Owner wants CAP13 developed
  before preparing 0.3.2. Bounded result here: typed query exports/dependencies in
  the manifest-v2 application's descriptor and a pure compatibility assessment.
  Protocol implementation: `three_mm_protocol/application_composition.py`;
  contract/limits and next stages: CAP13 in `CORE_SIMPLIFICATION_PLAN.md`.
  Only dedicated internal queries with exact bounded input/output schemas,
  matching deadlines and no human permission/events may be exported. Consumer
  contract identity/version/schemas/budgets must match exactly; no subtyping,
  wildcard/provider fallback or self-composition. Schema rules reuse the existing
  bounded capability dialect. The contract digest is domain-separated and typed.
  Absent composition declarations do not alter unrelated canonical descriptors.

  This is **declarations only**, not a runnable or completed CAP13. Even a
  compatible result explicitly has no evaluated instance binding, permission or
  runtime readiness; invocation is unsupported. No new SDK action, grant, browser
  UI, DB migration, service call or host transport change is included. Reviewed
  native code declaring a query is not a purity/isolation proof. NEXT: current
  M20 approval for exact consumer/provider instances, both package identities,
  export/dependency and contract digest, then bounded Runtime admission/result
  fencing with revoke/disable/upgrade checks. Commands, actor delegation,
  entity/deep-link and remote composition are later stages.

  Verification: new protocol/real ZIP package cases **61 passed**, Windows
  Python 3.13.15 / Pydantic 2.13.4 (`.runtime/cap13-initial.xml`). Linux snapshot
  `9265f5ba734225825cabd02b6e15d8b1aee0a14d10093c1376c3aa065923f2f4`,
  Python 3.14.4 / unchanged dependency digest `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`:
  **293 passed / 1 non-POSIX-only skip**, across new cases, existing application/
  capability schemas, package/gateway and authority context/sources/subjects.
  That run also had one environment failure: dev-lab's source-root allowlist
  omits the optional CRUD library needed by the existing Contacts package test.
  That exact case separately **passed** on Windows/Python 3.13.15 with UTF-8 and
  a private temporary directory (`.runtime/cap13-example.xml`). This is mixed
  platform evidence, not an all-green Linux/full release run. Earlier Windows
  regression attempt also hit protected pytest temp/locale and is not a green
  gate. Linux JUnit: `/tmp/3mm-public-capacity-b_wtv9fi/results.xml`; initial/new
  cases overlap these results and are not additional unique coverage.
  Only plan/handoff documentation changed after the checked executable source.
  No frontend build, commit, push, version bump, tag or device operation.
  Keep the unrelated saturation-test fix below for later 0.3.2 integration.

- **Release saturation-test race corrected locally, 2026-10-28.** Owner requested
  a fix after Release `40703983090` attempts 2 and 3 both failed at
  `test_saturated_public_waits_and_runtime_kill_leave_core_handlers_available`
  (`9 == 8`). Nothing was published. Immutable annotated `v0.3.1` remains on
  `8bcdb91f47ee274c1b23a8f68e62d9ab9b1d6f8a`; never move/recreate it.

  The test counted eight historical sends, but its declared 2 s response waits
  could expire during the intervening Core/SDK probes. A ninth request could then
  legitimately occupy a released slot. Delaying only the test caller by 2.2 s
  reproduces the original `9 == 8` failure; this is not a proven production
  capacity defect. The saturation case alone now uses the supported 30 s response
  window, asserts all eight waits are still live before/after overflow, requires
  the ninth request's refusal within 2 s, and kills/reaps its owned Runtime even
  on assertion failure. Serial admission, Core responsiveness, kill/restart,
  authority and no-replay checks remain. Other cases retain the 2 s fault profile;
  production code, deadlines, pool sizes, dependencies and release gates are
  unchanged. A discarded simultaneous-admission candidate hit a different short
  admission pool; it is not counted as successful evidence.

  Checked executable snapshot
  `b530454a98b35402789438d30a077d53dc8b65cc70d6b2601458b9c821fdc666`,
  unprivileged Linux / Python 3.14.4, dependency freeze SHA-256
  `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`:
  delayed corrected case **1 passed** (9.06 s); deliberately allowing nine slots
  in a disposable copy correctly **fails** the prompt-overflow assertion. Related
  group (`backend/tests/test_application_public_web_transport.py`,
  `backend/tests/test_application_public_web.py`, `three_mm_public_web/tests`):
  **43 passed / 1 distinct-OS-principals root-driver skip** (126.73 s).
  JUnit: `/tmp/3mm-public-capacity-{7cj1e5jc,x3aov01k,0lhcsrd5}/results.xml`;
  ignored reproduction helper: `.runtime/release-public-capacity/check.py`.
  No live service/device changes, frontend build or broad suite repeated.
  Working-state update is documentation-only after that checked snapshot.
  Whitespace check passes. NEXT: owner-authorized commit/version preparation;
  corrected code requires a new version/tag, not a retry of immutable `v0.3.1`.
  Canonical Python 3.13 CI/full Release gates have not tested this correction yet.
  No commit, push, version change or tag mutation performed for this fix.

- **Core 0.3.1 preparation completed, 2026-10-28.** Owner completed merge
  `0c536c9ad07a1dfd9d48c817e80bed2fe46d8c2f` and publication preparation was
  committed/pushed as `8bcdb91`. README/changelog/release notes describe the
  supported scope, independent component/data recovery and M21/WP5 limits.
  Exact main CI `40702947339` succeeded; owner created/pushed annotated `v0.3.1`.
  Release was cancelled once, then failed twice as recorded above. No published
  artifact or final-tag hardware pass is claimed. Preserve source/device state;
  no wipe, reset or deployment is part of this task.

- **Core/SDK 0.3.1 integration prepared on main, 2026-10-28.** Owner approved
  the bounded integration review/preparation, not a release or device rollout.
  Exact parents: main `778c5f0c42c3793c05064a078e931e965fe571b3` and incoming
  `5aa724603619031b56bad175fc85b808decac096` from `codex/core-sdk-0.3.1`.
  Incoming has five commits; main has one independent published-release handoff.
  A virtual merge found only this document conflicted. The local non-committed
  merge preserves both the incoming current state and main's verified beta.57
  publication record below; obsolete pending beta.57 instructions are superseded.
  No runtime/source correction was needed in this bounded review.

  Reviewed the complete change inventory (571 paths), the eight migration steps
  from `3e189f465708` to `b096b7e82f86`, retirement preservation/downgrade guards,
  Runtime/host operation and artifact contracts, and the browser SDK surface.
  Populated task/subject/kiosk and retired-product history can refuse downgrade:
  preserve database/key backups; an old Core pointer alone is not data recovery.
  Independent Runtime, application-host and Agent pins are not implicitly updated
  by a Core-only rollout. A later device plan must explicitly select/probe needed
  components and exact current application consumers; no rollout is authorized here.
  Terminal's existing browser-session adapter and Core session/worker modules have
  no incoming changes. Its separate dirty 1.0.3 repository and artifacts remain
  untouched. The local Fleet 0.1.10 checkout is historical, not evidence that the
  independently adapted Fleet source or every application has been tested here.

  Verification reused: hosted CI `40684871440` SUCCESS on exact incoming `5aa7246`;
  selection, Linux Python (including compiled-UI integration), frontend unit/TS/
  production build and tooling jobs all completed successfully. This preparation
  changes only this document relative to that checked incoming tree. No duplicate
  runtime suite/build, deployment, reset, branch creation, commit, push or tag.
  Local index checks: no unresolved paths or conflict markers; only this document
  differs from incoming. Its whitespace check passes. Whole-index diff --check
  still reports inherited whitespace in ten preserved legacy/reference files;
  the complete output matches incoming exactly, with no active-code findings.
  Those archived bytes are deliberately not reformatted by this integration.
  Owner subsequently created the ordinary two-parent merge commit `0c536c9`.
  Its executable tree still matches incoming; release preparation is tracked above.
  M20/WP4 stays accepted; full M21/WP5/host administration are not newly claimed.

- **Beta.57 published and verified, 2026-10-25.** Owner requested one release
  for the accepted current work and corrected the testing preference: branch CI
  and tag Release are AUTOMATIC; manual device trials remain owner-run.
  Public prerelease: https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.57
  Immutable annotated tag v0.3.0-beta.57 resolves to
  ebb98fb3fffef387976afbc80ce20a7aaf39ea82. Never move/recreate this tag.
  Exact main CI40174475950 SUCCESS: Python5448 pass/611 expected skips;
  deployment+SDK503 pass/4 expected skips; frontend499/TS/Vite and tooling32 pass.
  Release40176016358 SUCCESS repeated the full Python3.13/Node22 gates, both
  byte-identical full3arch+ARMv6 Node builds, clean checkout and complete draft
  upload -> public prerelease. Published2026-10-25T08:42:36Z, release ID423261156.
  All SEVEN published assets were downloaded and verified: GitHub asset digests,
  SHA256SUMS, full/Node manifest sets/URLs/sizes/profiles, four archive metadata/
  VERSION/commit identities, selected exact full/Node source bytes, Node offline
  wheelhouse inventory/provenance and every wheel hash. No artifact was executed.
  Evidence/verifier in the project mirror .runtime/beta57-published/verification.json
  and .runtime/verify_beta_release.py; generated downloads are outside tracked source.
  CI fixes retain automatic triggers and required gates: collect all tooling tests,
  allow cancellation of superseded runs, report first failure promptly, require a
  successful exact comparison base or select FULL in plan AND Python execution.
  Release prep also fixed malformed helper actions and stale migration/systemd
  test expectations without widening the production unit mount allowlist.
  Current release covers accepted P0-P6/setup/AP, common sessions/Node/local relay,
  lifecycle/retained data and simple admin consent. Host/root administration,
  public Cloud, full remote Terminal UI/whole M21/WP5 and capability-foundation
  plans are not claimed complete. Independent Terminal1.0.3 is not a Core asset.
  Devices were not updated during release work. Local beta.57 candidates are a
  different build: strictly-newer catalog won't replace an equal-version candidate;
  release notes give exact-tag full/Node bootstrap and require published commit,
  not VERSION alone. Preserve the existing database/key/Hub backups.
  NEXT: owner-run manual device trials when requested. No further implementation
  is required for this release; do not deploy/reset devices or reopen accepted
  scenarios automatically. This handoff update changes documentation only after
  the immutable release tag; its unchanged runtime checks are reused.

- **CI process-test deadlines and ordering corrected, 2026-10-28.** Run `40673704290`
  passed frontend/tooling and the early compiled-UI integration checks, then
  stopped at operational-status's first HTTP read (`TimeoutError`, outer 2 s
  watchdog). Five isolated CPython 3.13.17 probes completed in 30–36 ms; this
  does not establish the cause of that individual runner delay. A controlled
  response after 2.2 s demonstrated the harness defect independently: a valid
  response inside the configured production 5 s Runtime budget was cut off by
  the test client at 2 s.

  Shared process HTTP and its sibling health client now use a 10 s outer
  watchdog, allowing admission, the 5 s response budget and relay/completion.
  Status tests select the response budget through fixture parameters rather
  than a test-name substring. A real HTTP/Runtime/service regression requires
  the delayed response to remain authenticated, available and delivered once.
  Existing explicit <2 s failure bounds, <1 s administration responsiveness,
  <0.5 s independent DB writer, pool limits, revocation and no-replay assertions
  are unchanged. No production timeout/Core/SDK code, workflow, dependency or
  VERSION change; no device action.

  CPython **3.13.17**, unprivileged Linux: **137 passed / 5 distinct-UID root-driver
  skips** across all seven users of the shared Core process fixture plus response
  relay and health-probe tests (235.06 s). The delayed valid response completed
  in 2.41 s. Checked executable source
  `74e503f9388cb94bd7c309e9075dd138e303bfdc60017fc5b9842bae6ace9d8f`;
  logs, JUnit and old-watchdog negative reproduction are in ignored
  `.runtime/ci-response/`. Earlier frontend/tooling success is reused for their
  unchanged inputs. Separate SDK/deployment group under the same CPython 3.13.17:
  **653 passed / 7 explicit opt-in/image-profile skips** (59.09 s).

  Diagnostic replay of the original suite prefix: 2444 passed / 595 skipped.
  Candidate remainder ran in resumed batches: 338 passed / 2 skipped, 916 passed
  / 3 skipped, then 2242 passed / 11 skipped. These are separate evidence, not a
  successful monolithic gate. The mixed run stalled at the M21 worker stream
  fixture (`TestClient.receive`, line 194). A bounded diagnostic reproduction
  failed on its fifth repeated four-case run: the fixture held the worker send
  lock until a second read, while control could arrive first and block that read.
  The injected 5 s wait then expired, and raw WebSocket receive consumed the
  close before waiting forever for a second message. This is test-created IPC
  ordering, not a changed production session contract.

  The fixture now explicitly observes its second read before admitting control;
  the intended read-before-drain race remains asserted. WebSocket replies have
  a 5 s test deadline and a close fails before waiting for another message.
  Streaming/ACK, crash, audit-redaction, retained ownership, cleanup proof and
  spent-request assertions remain intact. Current executable source
  `2e32ebf399eaf1ce8e2f6a598d1dc680191f621273e6b23138a96e0e07f37f13`:
  **65 passed / no skips** in worker/browser/recovery/private-IPC consumers;
  **20 successive four-case runs passed** (repetition evidence, not 80 new cases).
  The same candidate's preceding mixed prefix also passed: **338 passed / 2
  opt-in systemd skips**, 119.82 s, without the diagnostic scheduling observer.
  Earlier HTTP/SDK/deployment checks retain unchanged executable inputs.

  CPython 3.13 also exposed the local WSL host's protected AP status path in
  network-recovery route tests. The final batch used a private mount namespace
  with empty `/run/3mm`, matching a clean runner; host mounts/services were not
  modified. No skipped assertion or substituted AP parser. Detailed logs and
  reproduction drivers remain ignored in `.runtime/ci-response/`.
  Commit `4924767` is pushed on `codex/core-sdk-0.3.1`; owner saw hosted run
  `40679488529` at 50%, past the former HTTP failure. The fixture follow-up will
  replace that pending run through normal CI concurrency; no full green claim.

- **CI Python compiled-UI prerequisites corrected, 2026-10-28.** Run
  `40666334219` passed frontend/tooling, then Python stopped at Command Probe's
  fixture: it loaded `/var/tmp/3mm-command-ui/source/frontend/compiler/...`,
  an undeclared developer cache absent on the runner. The fixture now resolves
  the current checkout. The compiler's separate npm graph is locked in its new
  package-lock (existing Vite 6.4.3 / Vue plugin 5.2.4 declarations unchanged),
  and CI Python plus Release explicitly install it with npm ci under Node 22.
  No production/Core/application behavior or VERSION changes here.

  The same audit found two HTTP-to-TypeScript consent/provider tests had skipped
  in that hosted run because they expected frontend/node_modules/esbuild. They
  now use esbuild from the locked compiler toolchain. CI runs the real three
  Command Probe scenarios and those two DTO checks early, then retains the full
  selected Python suite. No fake compiler, removed assertion or added skip.

  Clean relocated Linux checkout with ONLY compiler dependencies installed:
  **159 passed / no skips** in Command Probe, consent/provider onboarding,
  compiler/provenance, release-builder/contracts and check-selection tests.
  frontend/node_modules was absent; a Python audit hook refused the old developer
  cache path for the entire run. This verifies actual Vue compilation and signed
  SDK/provider behavior without that old path or a warmed main frontend install.
  Node 22.22.1 / CPython 3.14.4; canonical hosted Python 3.13 remains a separate
  result. Earlier 150-test/120-test runs overlap this final group and are not
  additive coverage. No other developer-only paths found in active Python tests.
  Checked source `d2ddb8d4ef504baf84a4963437476e7aa0f42053f75ec914ebe6ed044cbb8423`;
  exact source/inputs, install/test logs and JUnit are in ignored
  `.runtime/ci-compiler/`. Only documentation follows these checks. Follow-up
  commit/push stays on `codex/core-sdk-0.3.1`; no main/tag/release/device action.

- **CI frontend lock synchronization, 2026-10-28.** After owner-requested push of
  `b0deb84` on `codex/core-sdk-0.3.1`, GitHub run `40664971721` failed at
  `pnpm install --frozen-lockfile`: C3 removed Gridstack from package.json and
  the npm lock, but its pnpm importer remained stale. Removed the unused importer,
  package and snapshot entries for Gridstack only; no other resolved dependency
  version/range changed. The strict CI install requirement is retained.

  Fresh isolated Linux frontend directory, Node **22.22.1**, pnpm **10.13.1**:
  the exact CI frozen installation, **732 unit tests**, standalone type-check and
  production build all passed. No preexisting npm node_modules/cache evidence
  was substituted for this pnpm run. Checked inputs, clean directory and logs:
  ignored `.runtime/pnpm-ci/`. Development checks now explicitly require keeping
  both locks synchronized and running the canonical pnpm commands for dependency
  changes; the local npm deployment cache alone does not establish CI parity.
  Unchanged Core/Python source retains the checkpoint evidence below. Follow-up
  commit/push stays on the same branch; main, VERSION and workflow checks are
  unchanged. The new hosted CI result remains separate from local verification.

- **Owner-requested 0.3.1 checkpoint, 2026-10-28.** Owner explicitly authorized
  a commit outside main with Core version 0.3.1. Working branch:
  `codex/core-sdk-0.3.1`, based on `ebb98fb`. Scope is the accumulated supported
  CAP/Core extraction, setup/deployment, SDK and performance work in this chat;
  independent protocol/SDK/application version axes remain unchanged. No push,
  tag, release, deployment or device mutation is requested. VERSION, changelog
  and README describe the local unreleased checkpoint. Staged scope reviewed:
  accumulated supported CAP profiles, optional-product extraction, onboarding/
  recovery, deployment tooling and SDK optimization. Existing immutable kits retain
  their original version/content; they are not silently relabeled 0.3.1.

  The two previously recorded retained-data fixture failures are corrected:
  backfill/downgrade tests target their own historical migration while separate
  clean/precreated tests still validate head; the activation identity test uses
  a current typed, device-independent declaration and configuration entrypoint.
  Its retained identity/helper-denial assertions remain intact. Full integration
  also exposed a real floating-point countdown boundary: a 600-second diagnostic
  session could initially report 601. Store the requested bound and clamp only
  the displayed remaining time; the actual expiry/rate/ownership rules remain
  unchanged. Three deterministic exponent-boundary cases plus direct consumers
  passed; the protocol/SDK version axes did not change.

  Local checks: **6661 unique primary Python cases passed / 618 explicit skips**,
  covering all existing CI Python/tooling groups. Backend's 4886 collected cases
  were accounted for across resumed batches, with worker-disconnect's 4 cases
  in their own fresh process. The initial stopped runs (2483/690 passes) are not
  called green gates: only their unchanged successful/skipped families are
  reused, with the repaired case and remaining modules checked afterward.
  Fresh diagnostics/direct consumers: **88 passed**; retained-data suites:
  **11 passed**, followed by the exact repaired denial on final product code.
  Other completed groups: **1655 passed / 3 skipped** core/Agent/protocol/runtime/
  provisioning/setup/libraries; **653 passed / 7 skipped** deployment/SDK;
  **68 passed** tooling. Counts overlap where fixtures/direct consumers repeat;
  the 6661 total is deduplicated, not the sum of every run.

  Separate optional image profile: **71 passed / 1 root-driver skip**, including
  real Pillow media and native image-host artifact checks. Pillow 13.0.0 was
  installed only in a disposable test target, not Core's dependency environment.
  **732 frontend tests / type-check / build passed**, cache
  `e61e97f6b29be0253f89b4ae7264ac686d37959d18bdb3fb5fdd9d14d754ced5`.
  Native Windows deployment command doubles passed without network. Environment:
  unprivileged WSL Linux/CPython 3.14.4 and Node 22.22.1; canonical Python 3.13
  CI and opt-in/root/systemd/hardware release acceptance remain distinct gates.
  Existing physical acceptance is retained, not rerun or enlarged here.

  Initial broad source `f23703589af5b455881bb17a64082144a2265120568208d77cb1e47b08703f34`;
  final checked product source
  `2aba6bc2c834a133debca852e83bd009c2f994af5ec931e91a1a076ef1269bf6`.
  Only the retained fixture and diagnostic module/tests changed between those
  executable snapshots; affected checks were rerun. Exact source inputs, JUnit,
  per-family coverage accounting, staged diff/tree audit and logs are in ignored
  `.runtime/checkpoint-031/`. Preserved legacy/reference snapshots retain their
  verified original bytes and inherited whitespace; active-code whitespace is
  clean. No generated archives, databases, keys, access notes or credentials are
  staged. Only this handoff prose follows verification. Next: owner review and
  any separately requested branch publication, merge or new 0.3.1 deployment kit.

- **General Core/SDK invocation optimization completed locally, 2026-10-28.**
  Owner authorized the common optimization below. UI code trust now resolves
  current package/lifecycle, incarnation, Core identity and recovery generation
  without reconstructing unrelated service-resource policy. Full policy and UI
  trust share the same authenticated native-review/binding/risk validation.
  Grant/native records and their revision/seals remain fresh at every boundary;
  service resource use keeps its independent current authority checks.

  A bounded request-local scope reuses verified ZIP/descriptor/build objects
  across both invocation thread-pool phases and nested UI route checks. Reuse
  checks file identity, size, mtime/ctime, owner/mode and protected build inventory;
  detected drift poisons the entry. Scope exit clears retained objects, including
  copied contexts. No actor/grant/approval cache or operation replay. SDK coalesces
  only in-flight getInfo calls on one mounted host and exact origin/credential;
  it binds discovery to that actual credential and refuses actor/origin changes.
  Completion/failure discards discovery, and each invocation still sends its own
  single POST. No application-specific Core branch, app edit, dependency/schema/
  protocol/version change, reset or deployment. Existing M21 proof/transactions
  and owner-accepted reader/AP tests remain intact.

  Matched metadata-only Pi comparison, actual Core UID and connection-enforced
  query_only: old warmed independent UI checks 374.54/382.29/459.04 ms; candidate
  105.29/102.35/101.54 ms. Repeated boundaries in one request fell from roughly
  363–380 ms to 63–69 ms after its initial 112.56 ms check, about 5–6x for the
  repeated verification segment. Initial cold verification was 597.34 vs 186.45
  ms. Candidate modules were injected only into a separate diagnostic process;
  archive audit matched all seven measured module hashes. No business query,
  scan or installed service/config/grant/key change. This is not an end-to-end
  browser latency result; owner measures clients/stays after deployment.

  Final frozen source
  `ac779a1e641a0e42e228065ea35fcdd61a8d5b8213cbe700447a3cad72f97635`:
  **1431 passed / 7 explicit skips** in the affected authority/consent/access,
  administration/session/kiosk, invocation/IPC, resources, package/compatibility,
  relational registration/candidate, compiled UI and controller group (185.33 s),
  evidence `d80694e64b2549300fb6f2581f01f6a100918d65873597164aad138808b87c53`.
  Separate same-source runs: **4 worker-disconnect checks passed**, and **5 root
  checks passed**, supplying the skipped foreign-UID/real relational helper
  coverage. The two non-POSIX refusal cases remain environment-specific skips.
  **732 frontend tests plus type-check/build passed**; preparation reused that
  exact checked build `96fd58a9adffef87d0cf5a3e7b24c10ab982b1bd4cce1259735086b0c8fd2f97`.
  An initial compatibility regression in the default version source was caught
  and fixed before this evidence. A mixed run stalled at the existing ASGI
  worker-stream fixture (py-spy confirmed TestClient.receive line 194); it was
  interrupted and is not a successful gate. Final verification deliberately
  runs that unchanged module in its own fresh process, without weakening tests.

  Ready owner-run Core-only kit:
  `.runtime/deploy/artifacts/0f5e4e5ce7f985e9bc848597680a11df8e03a1d5d4bad02a1939bf4b42ec4207`,
  release `local-0f5e4e5ce7f985e9bc848597`, 14.60 MiB, prepared in 218.812 s.
  Archive audit confirmed all hashes, exact current source/evidence, new frontend
  and retained Agent/default host. Only this handoff prose follows audit.
  Next: owner deploys the kit when ready and measures the ordinary clients/stays
  refresh. Ignored probes/audit live in `.runtime/provider-onboarding/`.

- **Owner acceptance and read-latency diagnosis, 2026-10-28.** Owner confirms the
  UI-build 409 correction works and the real reader test passed. Core is now
  `local-e22b77666d7687b0ed302542`; do not reopen the accepted reader scenario.
  New question: registrations/stays take 10–12 seconds to load. Metadata-only SSH
  timing as Core UID, with DB connection-enforced query_only, measured one ZIP
  read/validation at 26.50 ms, protected compiled-build verification at 25.93 ms,
  application descriptor loading at 23.47 ms, and one full UI trust verification
  at **567.33 ms**. Profiling a separate call shows full `_subject` composition
  dominates that trust check; its instrumented cumulative timings include profiler
  overhead and must not be added to uninstrumented stage durations. Snapshot:
  load average 0.22, 288 MiB memory available, temperature 48.3 C.

  Code-path accounting: ordinary UI-bound operations call `admit` five times and
  invocation preparation three times. Both paths independently repeat complete
  compiled-UI trust, including package/build preparation and full authority
  subject/policy reconstruction. One Desk refresh first calls `host.getInfo`,
  then starts both list queries; SDK `invoke` calls `getInfo` again for each one.
  This is up to 19 full UI trust checks for the two-list refresh, before counting
  relational authority/metadata work. Lists render together after Promise.all.
  These counts come from current code, not an end-to-end HTTP timing trace; the
  observed repeated verification cost explains a substantial part of 10–12 s.
  Existing application list handlers use paged local SQL. No business operation,
  scan, permission change, deployment or app-source edit was performed here.

  Proposed next bounded Core/SDK performance result: prepare/verify immutable
  package, descriptor and UI build once per invocation and reuse those exact
  objects at repeated boundaries; retain fresh actor, native-review, package/
  lifecycle/recovery and resource-grant checks at their current admission and
  completion points. UI code trust should not reconstruct unrelated full service
  resource policy on every read. Coalesce concurrent SDK getInfo requests for the
  same mounted host without caching authorization or replaying operations.
  This is a general mechanism; no Child Center-specific Core fast path. This
  turn is diagnosis only; implementation/performance acceptance remains next.
  Ignored measurement script: `.runtime/provider-onboarding/profile-ui-read-cost.py`.
  Documentation/diagnostic-only work needs no frontend build or runtime suite.

- **Recurring UI-build 409 diagnosed and corrected locally, 2026-10-28.** Owner
  still sees `Application UI build is unavailable; reload the interface` after
  Ctrl+F5 on Child Center query operations. Read-only SSH as the actual Core UID
  confirmed installed release `local-952351ef39ef30d1d4dfb60a`, active app 0.7.9,
  exact ZIP and protected compiled build
  `8f690b1facac83ecf701590f57eb9bdff10388b89ea28005be0d3fa42a5110b2`, matching
  native binding/revision and successful isolated UI trust. Two concurrent trust
  checks on the installed code reproduced one `AuthorityReviewKeyError` at
  0.368 s while the other succeeded at 0.445 s: read-only UI checks used the same
  exclusive key lock and exceeded its 250 ms admission wait. No business queries
  or scans were invoked. Initial standalone probes needed full ORM registration
  and Core's ordinary file engine with connection-enforced query_only; custom
  read-only URI engines are intentionally rejected by the snapshot contract.

  Added a dedicated shared `read_locked` verification lease, used only by UI
  trust verification/read snapshots. Its public adapter refuses new seals and
  encrypted recovery responses; fingerprint/verification/decryption retain the
  current key/DB binding and expiry checks. Approval/effect admission, key
  provisioning/rotation/recovery remain exclusive. No timeout increase, grant
  cache, permission fallback, mutation replay, schema/dependency/SDK change.
  Old code fails both deterministic overlapping-reader regressions; corrected
  verification and exact snapshot paths pass, then refuse revoked native trust.
  Real key tests retain writer/rotation exclusion, no signing through read leases,
  tamper/expired-lease denials. Candidate versions of only the two Core modules
  were loaded in a separate read-only diagnostic process on the Pi: both checks
  passed (0.770/0.689 s); installed files/services/keys/grants were not changed.

  Final frozen source
  `aa706785f273cf1e880b5f2c6432d09b0eacaff17148f62b1a2ea1353b56f282`:
  **1263 passed / 3 explicit root/non-POSIX skips** in the affected authority,
  consent, access, administration, browser session, invocation/IPC, kiosk,
  compiled UI/provenance and controller group. A separate disposable root run
  passed both the real foreign-UID key denial and shared-lease test; remaining
  non-POSIX refusal skips do not assert POSIX coverage. Reused unchanged
  **728-test frontend/type-check/build** cache
  `51dde2a6926fb64a79460c5390bfa2ff9bf66e0b8a6814ba3b0139061412cf47`.
  Ready owner-run Core-only kit:
  `.runtime/deploy/artifacts/e22b77666d7687b0ed302542e7fd4d6ab92d0c3bfe1a12738b16e12622c09e9f`,
  release `local-e22b77666d7687b0ed302542`, evidence
  `780cede587e4f60931af22cdfdd22524f1694b7d95a8ebd0863137e35bea7183`.
  Prepared in 197.534 seconds, 14.59 MiB. Audit confirmed kit/archive/source
  hashes, the exact two candidate module hashes tested on Pi, unchanged frontend
  and retained Agent/default-host specifications. Only handoff prose follows
  audit. No deployment, app ZIP edit, actual app operation, permission/config
  change, reset, publication or commit. Next: owner deploys this kit and retries
  the normal Child Center UI reads; owner retains business acceptance tests.

  Separate existing test maintenance findings: an initial mixed 150-file run
  reached 2747 passes/597 skips but had two retained-data failures and stalled in
  the ASGI worker-stream fixture; it was interrupted, never accepted as a green
  gate. Both retained-data failures reproduce on unchanged pre-fix source
  `1e50704...`: guarded stable-subject downgrade and a mock of the removed
  `resolve_application_configuration` route symbol. Both fixtures are corrected
  at the later owner-requested 0.3.1 checkpoint recorded above.
  The worker case passes separately on both old/new code; its entire module also
  passes in the final affected group. No full-backend success is claimed.
  Ignored diagnostic/check evidence is in `.runtime/provider-onboarding/`.

- **Missing owner capability administration corrected locally, 2026-10-28.**
  Read the last two `child-center` replies: installed Core is
  `local-0a42e1568206f3095e21f375`, Agent pin
  `ed8febbce804770bbf762eee78cc21d762f64ec696247a5243b8ea82ce7b14ec`.
  This is reused sibling read-only evidence, not a new device session here.
  The previous implementation tested administrator selection through API only;
  the owner's normal UI step was missing. Devices now has a Capabilities action
  per device, opening a provider-neutral editor through existing administrator
  provider/configuration/enable and catalog-v3 APIs. It shows reported offers,
  retained selections, enabled state and live readiness independently. Module/
  platform/inventory-only rows are descriptive. Withdrawn retained selections
  require an explicit clear before a new selection can be saved. No app-specific
  branch, API/auth change, schema migration, automatic grant/enable or scan replay.
  Bounded browser decoding binds device/provider/target/revision; one-shot writes
  refuse uncertain/foreign acknowledgements. Conflict/denial/lost response blocks
  mutation until an explicit fresh read. Saving one provider preserves drafts of
  other providers. Admin page/role guards and backend authority remain in force.
  Shared CAP09 controls/tokens retain theme and component settings; EN fallbacks
  and BG language-source labels added. BG installed package is not replaced.

  Verification: **728 frontend tests and type-check/build passed**, cache
  `51dde2a6926fb64a79460c5390bfa2ff9bf66e0b8a6814ba3b0139061412cf47`,
  source `1e50704cae4f4cc935f2b8956d9d42e85ac95231550b6e46df9845b6780cc2cf`.
  Includes the actual Devices button -> editor -> save flow, explicit selection,
  revisions/disable, 409/403/timeout, other drafts, withdrawals, inventory-only,
  non-admin denial and foreign response/target rejection. **53 backend checks
  passed**, including three actual HTTP provider/catalog snapshots decoded by the
  real browser TypeScript (unselected, selected, disabled). That run used source
  `dba41aa74e85cf8e22690de68c1790042098ec51d828a116b615e05381d07eea`;
  only a TS target-compatible own-property check changed afterward, covered by
  final full frontend. Broader unchanged provider/Agent/runtime evidence below is
  reused. Synthetic browser review exercised save/readiness and a lost-ack then
  explicit-refresh path; light/outline and 390x844 dark/BG, maximum identifiers:
  no document/panel/card overflow. Screenshot/evidence in ignored
  `.runtime/provider-onboarding/`. Viewport reset and owned tab/server closed.
  Ready owner-run Core-only kit:
  `.runtime/deploy/artifacts/952351ef39ef30d1d4dfb60a6f485e3488c22adbd13a1a26e86f4973c16f7af8`,
  release `local-952351ef39ef30d1d4dfb60a`. Prepared in 45.677 seconds; 14.59 MiB.
  **89 preparation checks passed** (the 53 backend checks above plus 36 controller
  checks), evidence `25d29679d8232383153e953247de7874c57cdc71eb8958a5b7a37e5569c052e7`.
  Reused the final 728-test frontend build. Independent kit audit confirmed all
  hashes, exact source proof, the actual compiled Devices administration chunk and
  unchanged Agent sources; independent Agent pin remains retained. Only handoff
  prose/plan changed after audit; existing immutable kits are unchanged.
  Next: owner runs the supplied command, then Devices -> Capabilities,
  explicit source selection, fresh application event consent and ONE new scan.
  No SSH, real provider selection, app grant, deployment, publication or commit.

- **Owner-run Core + Agent rollout prepared, 2026-10-28.** Ready immutable kit:
  `.runtime/deploy/artifacts/0a42e1568206f3095e21f375442e52f37e9c463008aad17e45fcd10cc4f4fdd5`,
  release `local-0a42e1568206f3095e21f375`, ARM64/Python 3.13/image host.
  `deploy.ps1 -Action Deploy -Bundle <that folder>` applies the sealed selection;
  no extra flag is required at deployment. Permanent `-WithAgent` preparation
  explicitly includes the independent Agent pin. Core-only kits still retain it.
  The new release's constrained venv builds the exact selected Agent sources and
  dependencies; standard `service_component agent update/probe` owns identity,
  Core continuity and rollback. Agent configuration is preserved. Partial failure
  remains failed/inspect-only, not a successful or blindly replayed deployment;
  Agent rollback is independent and does not undo an already successful Core.
  Other independent services/application pins are not updated by this option.

  New frozen preparation evidence `9cdf688002dd40473b6d3f2954ed9f1f942382fac8d7ce6e8b969519f82a596d`:
  **396 passed / 1 explicit non-POSIX refusal-case skip**, including controller,
  real native Agent build/isolated staging, service-component update/rollback,
  all Agent and focused onboarding/consent/event-authority regressions.
  PowerShell command doubles passed without network. Reused the unchanged
  **715-test frontend/type-check/build** cache recorded below, and the unchanged
  broader integration evidence. Prepared in 75.965 seconds; 14.59 MiB kit.
  Independent audit validated kit members/digests, Core archive, Agent source
  binding, exact workspace against evidence and `Prepare -Bundle ... -WithAgent`.
  Only deploy controller/wrapper and their tests changed after prior product
  verification; README/check policy documented the permanent option. This handoff
  prose is the only edit after package audit and needs no runtime rerun.
  No SSH/device action, deployment, commit, publication, config/grant change or
  scan replay. Next: owner runs the supplied command on `rasp-3mm.local`, then
  explicit provider selection, fresh application event consent and ONE new scan.

- **General Agent provider onboarding and optional-resource diagnostics completed
  locally, 2026-10-28.** Owner authorized implementing the common path discussed
  below. `AgentProviderRegistry` accepts bounded adapter declarations/health,
  reconciles authenticated existing provider v2 endpoints with revision/identity
  checks, and publishes ephemeral health. New offers stay unselected; Core-owned
  enabled/configuration and application consent remain separate. A bounded
  device-bound local journal remembers ownership before publish so lost acks and
  adapter removal/restart reconcile without adopting other providers. Health/report
  faults are isolated across providers and cannot kill the Agent heartbeat loop.
  Normal Agent factory wiring now includes the enabled mock identifier adapter;
  its inventory names come from the same declarations. Disabled mock after restart
  withdraws the previously reported source. No Core app/vendor-specific branch.

  Event source admission reuses current capability availability: v2/C14 providers
  with missing/stale/unhealthy/offline evidence cannot acquire/reuse event access.
  Consent preview now carries bounded redacted `unavailable_resources` for omitted
  optional scopes, including later command-schema mismatches, outside the sealed
  grant subject. Required failures still refuse. Core frontend validates the
  coordinated DTO and shows EN/BG explanations before collapsed permission
  details; it cannot select an unavailable scope or implicitly enable/grant it.
  No device protocol/manifest/application SDK version, DB migration or dependency
  change. BG changes are source only, not a rebuilt language package.

  Evidence: frozen unprivileged WSL Linux/Python 3.14 source
  `a4fe2e5289b0dd225b6f7c88038e2c741e70e5553bb777b0e05b113561dbc5f7`:
  **1178 passed / 2 explicit root-driver/transient-systemd skips** across protocol,
  registry/availability, device/event transports, sealed authority/context,
  consent/lifecycle, event delivery/publication and actual independent Runtime
  processes, resource discovery, startup/release and service component gates.
  Final source `c99b18f59dd33079321898fd5c70e93a7c65a4ffc331083d29cb9e179232a0e7`:
  **323 passed / 1 non-POSIX refusal-case skip**, all Agent tests plus actual HTTP
  onboarding, optional/consent HTTP->TypeScript, event authority and source/subject
  regressions; **715 frontend tests and type-check/build passed**, checked frontend
  cache `c1132df6842eedc1bbf48db350b396bffcec6b0d013180630c5ed1979954e7a3`.
  Groups overlap; not summed. Changes after broad integration are only optional
  diagnostic propagation, its test call/coverage and UI labels/wrapping; final
  focused/full-frontend checks cover these. Other broad evidence is reused.

  New conformance uses actual Agent factory configuration, normal authenticated
  HTTP provider/configuration/event routes and fresh sealed consent, without
  SQL-seeded reader providers. Two distinct app IDs and unrelated identifier/
  measurement adapters use the same Core path. A real signed native peer uses
  public own-SQLite SDK transactions: two subscriptions yield one receipt for one
  fresh event; an earlier unapproved scan is not replayed. Disabled, unselected,
  withdrawn, revoked, conflicting, unhealthy/stale sources and foreign response
  identities are denied; lost acknowledgement/restart and broken adapter health
  do not mint authority. The second sensor is a test adapter, not shipped hardware.
  Browser review used current components in an owned synthetic local fixture,
  desktop light/EN and 390px dark/BG, including a maximum-length subscription ID:
  no horizontal overflow, missing sources clearly explained, unrelated permissions
  remain available. Source matches checked product/tests; whitespace passed.

  Owner-run coordinated Core + independently delivered Agent kit is now prepared
  above; after rollout, provider selection, fresh event consent and ONE new real
  Child Center scan on `rasp-3mm.local`. No Child Center ZIP change is needed for
  this Core/Agent integration. Existing rollout bundles remain immutable and do
  not contain this work. No SSH/device action, deployment, app source edit,
  historical scan replay, version bump, commit or publication. Preview viewport
  reset and owned tab/server closed at handoff; ignored local evidence remains in
  `.runtime/provider-onboarding/`. Public contract/plan updated, no new report.

- **Reader/provider integration review, 2026-10-28.** Owner asked to read the
  latest 2–3 `child-center` replies about `identifier.scan.v1` and explain how to
  avoid repeated Core changes for each application/device. Read the last three
  turns and the sibling's current reader contract; reused its installed read-only
  evidence, without another SSH session or replay. Agent accepts scans and Core
  stores them, but the effective capability registry exposes only GPIO; the
  selected reader scopes resolve `capability_unresolved` and optional event
  choices disappear from consent. Current local `agent/main.py` confirms the mock
  only appends a capability name to legacy inventory; that is not a provider
  report, configured selection, current control revision or application consent.

  Existing Core provider report/configuration/enable APIs and generic `_event`
  source resolution already accept provider-neutral declarations. The bounded
  next result should connect enabled Agent adapters through one shared provider
  onboarding/synchronization path and expose unresolved optional resource reasons
  generally in administration (CAP01 + CAP07). Do not add a Child Center resolver,
  infer grants from ingestion, fabricate a DB provider or auto-replay old scans.
  Acceptance should use normal Agent onboarding, explicit provider selection and
  fresh event consent, then one new scan; include disabled/unselected/revoked/
  conflicting/stale sources and a second unrelated test provider using the same
  path without a Core branch. Driver-specific payload/IO belongs in the adapter,
  business meanings in the app; Core owns shared validation, authority, routing
  and delivery. New providers of supported contracts should need no Core edit;
  genuinely new execution/trust semantics may still require a shared contract.
  Read-only review plus handoff prose only; no product edits, tests, device
  changes, deployment or message to the sibling chat in this turn.

  Follow-up owner-requested generality audit: reviewed the Child Center-driven
  presentation/connector/kiosk contracts and actual shared implementation paths
  for configuration, actor/delegation, staging/recovery and invocation. Those
  mechanisms use manifest declarations and installation/artifact identities;
  no Child Center/Barsy/reader-setting-specific references were found in inspected
  production Core/Agent/protocol/runtime/SDK/frontend/deployment sources. Vendor
  requests and child/bracelet/stay rules belong to the sibling app. Generality is
  bounded: connector settings cover declared connector profiles, same-app
  delegation covers the accepted own-SQLite execution profile, and lifecycle
  families retain their separate contracts. Reader onboarding remains the concrete
  uncompleted integration above; synthetic broker-provider fixtures do not prove
  normal Agent enrollment. An instance-specific administrative recovery is an
  operational action, distinct from the general recovery mechanism it exercised.
  Audit only: existing test evidence reviewed, no tests newly run or code changed.

- **CAP09 button-state review and fixes completed locally, 2026-10-28.** Owner
  requested a broader review of similar presentation defects, fixes and a deploy
  command. Fixed the confirmed secondary hover bug: the shared generic rule
  changed its gray background to white while keeping white text. Primary/danger
  also mixed their backgrounds toward the foreground, reducing contrast; the
  old Core aliases independently always darkened buttons and forced white text
  without a theme package. They now share the effective SDK background/text
  pairs and a bounded hover derivation that never lowers the original contrast.
  Outline foregrounds retain accent/danger when readable on their normal/hover
  surface, otherwise use black/white. No manifest/Theme Design schema or public
  UI version change. Disabled/loading and keyboard focus behavior remain intact.

  Final frozen source:
  `032252d32dacf1ac2ebabc212174aef952dc81a2b51dbbf3ac8cc84d216e020c`.
  New evidence: **714 frontend tests, type-check/build, 188 targeted Python
  checks passed** through the deployment controller. Same Python selection as
  below; new regression coverage includes 100 foreground/background pairs,
  built-in/saved/package light/dark and legacy/SDK projection during preview and
  mode switches. Browser verification used actual production CSS/import-map SDK:
  84 real hover cases across built-in/package/custom, light/dark, solid/outline,
  SDK variants and old Core buttons, all text contrast >= 4.5 (minimum 4.5275).
  Five disabled/loading controls remained disabled and kept their colors under
  the pointer. Keyboard focus is visible; draft preserved. The earlier fixture
  had missed built-in light secondary white text by testing v2 dark foregrounds.

  Ready bundle:
  `.runtime/deploy/artifacts/01e6e984294e8ae1f6df23b127c0af1264c56c8c89e21b717f4bc02e3f63ad15`;
  immutable release `local-01e6e984294e8ae1f6df23b1`. Preparation 52.736 s,
  kit 14.58 MiB. Ready/checks/payload digests validated; new secondary hover CSS
  inspected in the archive. Backend/deployment/runtime sources and native host
  spec equal the prior kit below, so unchanged runtime evidence is reused rather
  than rerun. Only contract/handoff prose changed after checked product inputs.
  This bundle supersedes the previous command and includes its changes.

  Next: owner runs the supplied `deploy.ps1 -Action Deploy -SshHost
  raspberry@rasp-3mm.local -Bundle <ready folder>` command, waits for
  `3mm update succeeded`, Ctrl+C, then Ctrl+F5 and checks Settings/Extensions/apps.
  Device acceptance remains pending; no SSH/device deployment, app ZIP/version
  change, commit or publication. Owned temporary QA tab/server closed at handoff;
  screenshot and detailed measurements remain in ignored `.runtime/cap09-theme/`.

- **CAP09 theme alignment completed locally; rollout kit ready, 2026-10-27.**
  Owner approved the proposed scope and requested a command to deploy personally.
  Settings previews now use the actual public SDK surface/buttons/fields/forms/
  tables/states/dialog, with the same effective design projection and shared
  stylesheet delivered in the public ESM CSS closure. Removed duplicate field,
  table and state styling. Single-line fields align independently of help/error
  height; checkbox layout, readonly/disabled/error/focus, local table scrolling
  and loading/error/empty states use common tokens. Native controls use the local
  palette's color-scheme; nested surfaces own button/card variants. Scoped the
  legacy global header padding/alignment to the Core app header so extension
  semantic headers retain their own layout. Added optional field placeholder and
  autofocus; public UI contract version and existing consumers remain unchanged.

  Verification on the final frozen source
  `e88be5cdef926a144764fa8caf3d8cb411254aadd1c2b76eb4f7d4cd5f80b783`:
  **710 frontend tests, type-check/build and 188 targeted Python checks passed**
  through the deployment controller. Python scope: compiled UI/reference package,
  themes/customization/options/v2, release builder and deploy. New integration
  coverage checks actual Settings save/reload and sibling SDK draft preservation;
  mode/variants/density changes do not remount or submit the draft. Earlier backend
  runtime evidence is reused, not rerun: archive comparison confirms no backend
  change from the prior CAP04/CAP03 kit and the native host specification is equal.

  Browser verification used owned local fixtures with real Settings stores and,
  separately, the final production CSS/JS/import map with the unchanged CAP09
  example. Confirmed light/dark, explicit Settings save, outline/raised variants,
  custom font/size/radius, EN/BG, preserved drafts, keyboard focus and dialog
  validation/focus return. A light palette preview remains light inside dark Core.
  At 390 px, all single-line controls are 44 px, the page has no horizontal
  overflow, and a wide table scrolls locally; desktop compact fields are 36 px.
  Temporary viewport was reset; preview tabs/servers are closed at handoff.

  Ready bundle:
  `.runtime/deploy/artifacts/ed38e7345aba67bbe32341f0bea91d9877c73f2245fd0a4fe5fc39f475c7efbb`;
  immutable release `local-ed38e7345aba67bbe32341f0`. Preparation took 50.874 s;
  kit is 14.58 MiB. Ready/payload/checks digests and shared CSS in the archive
  were verified. This supersedes the prior rollout command below and includes
  that kit's CAP04/CAP03 changes. No app ZIP rebuild/reinstall is needed for the
  shared component fix. Three Bulgarian Settings sample labels were added to
  language source only; no language ZIP/version or installed package was changed.

  Next: owner runs `deploy.ps1 -Action Deploy -SshHost raspberry@rasp-3mm.local
  -Bundle <the ready folder>`, waits for `3mm update succeeded`, closes the log
  viewer with Ctrl+C and reloads with Ctrl+F5. Device acceptance remains pending.
  No SSH/upload/device deployment, schema/auth change, commit, package version
  change or publication in this task. The prior rollout is not assumed installed.

- **CAP04/CAP03 rollout kit ready for owner-run deployment, 2026-10-27.**
  Owner requested a ready `deploy.ps1 -Action Deploy -Bundle ...` command and
  will execute it personally. Prepared with the existing `-Action Prepare`
  controller for ARM64 / Python 3.13 / image-provider profile. Bundle:
  `.runtime/deploy/artifacts/c9be6fdcd856741f181ad690cc8ae73e44291bda89ba35adb822230913727540`;
  immutable release `local-c9be6fdcd856741f181ad690`. Preparation took 128 s.
  **421 targeted tests passed** across invocation/response/peer, actor/UI/access,
  consent/recovery/staging/lifecycle, relational admission and release/deploy
  gates; checked frontend build was reused by exact cache identity. Other
  unchanged-profile evidence remains as recorded below, not newly rerun coverage.
  Checked source snapshot: `0687d5a3a6424ab64c0e7b4276521b059125ecd9133ff45b639dc54aa45d2516`.
  Source audit found no non-document changes since the accepted local result.
  Validated ready/payload/checks digests and inspected the archive: both changed
  Core services match the workspace and the new recovery UI is in the prebuilt
  frontend. Only `application_invocation_relay.py` and `application_consent.py`
  differ in Core production inputs from the previous kit; native host spec is
  unchanged and normal deployment may reuse the installed matching host.
  Kit size 14.6 MiB. No separate component update is needed for this Core fix.

  Target remains `raspberry@rasp-3mm.local`. No SSH connection, upload, remote
  job or deployment was started; target receipt still names the prior kit.
  Next: owner runs the supplied command, waits for `3mm update succeeded`, closes
  only the log viewer with Ctrl+C, refreshes the browser, then checks Child Center
  reads and the supported web recovery/fresh-consent path. Device acceptance is
  pending. No commit, package version change or publication.

- **CAP04 correction and first CAP03 web recovery result completed locally, 2026-10-27.**
  Owner requested the proven CAP04 fix, then work on CAP03. Invocation admission
  now finishes artifact/UI/actor/metadata checks and the final writer fence before
  reserving response capacity, immediately followed by connect/send/FD handoff.
  No DB/artifact work runs inside that short handoff window. Existing 1 s reserve,
  2 s Core / 3 s Runtime handoff, eight slots, signatures and fresh completion
  policy remain. Reservation/connect/deadline refusal before send is explicitly
  not-dispatched; partial send/lost handoff/result remains unconfirmed. No retry.
  No SDK, schema or Runtime contract change; health/status retain their own gates.

  Extensions now offers an explicit recovery dialog for interrupted lifecycles:
  current stage/error, external-effect review, existing admin recovery API,
  verified stop with data/configuration/packages preserved, then fresh access
  review and separate manual activation. Unknown stop replies require read-only
  refresh before another deliberate attempt. No inferred rollback, old grant
  restoration or business replay. Missing/broken optional compiled UI/package/
  theme/language catalogs do not hide installation recovery; catalog requests
  are bounded. Current registered v2 candidates keep saved permission choices,
  but obsolete-epoch consent after recovery is not shown as currently saved;
  fresh explicit approval is required. Ordinary confirmed disable/enable remains
  separate. This also resolves the saved-consent dead end observed below.

  Verification uses frozen WSL unprivileged Linux/Python 3.14 sources, overlapping
  groups (not totals). Gateway bytes match `7f5ed1d7b8f51ce75199aa6b40df1bb24ef74348e93496b940e7e69ad7def0af`:
  its real signed HTTP/Runtime process, two concurrent 2.15 s admissions, response
  slots/FD boundaries, revocation/no-replay, peer callback and lifecycle-authority
  cases passed. A new unit test's thread-bound SQLite fixture was corrected in
  `6d36ca21bcecec22b60269becb168de5231ca15118dac991b858987f39fc30b6`:
  **81 passed** invocation phases/current denial, actor/UI, access/extensions and
  recovery; **46 passed / 25 root-profile skips** relational consumers. Final
  consent/lifecycle/install/staging/scoped-gate group on
  `589478b70b4b4f8583465fb485275686d9b9c047fa71d3ef9c522bcffa9926db`:
  **118 passed**, including real sealed preparation -> HTTP recovery -> fresh
  consent and preservation of an ordinary disabled empty selection. Legacy
  adoption is not converted into inert provenance by recovery; it stays closed.
  **708 frontend tests and type-check/build passed** on
  `21fc56c628fb179414a11a01ab6f98ada7dfd66f12a7b03059ac4acd74f10c36`;
  frontend source bytes are identical in the final backend snapshot. Local UI
  review covered desktop/light and 390 px mobile/dark/Bulgarian, explicit review
  enabling and transition to access review. Temporary preview tab/server closed.
  Only plan/handoff prose changed after those checked inputs.

  Next acceptance: a separately requested rollout, then owner checks ordinary
  Child Center reads and web recovery/fresh consent on `rasp-3mm.local`.
  CAP03 dependency planning and other dedicated lifecycle profiles are not closed
  by this bounded result. No device access/change/deployment, sibling edit,
  commit, version bump or publication in this turn.

- **Diagnosis preceding the CAP04 correction above, 2026-10-27.**
  Owner paused CAP work to diagnose the screenshot and asked to read the last
  2–3 `child-center` answers. Read those answers and its current handoff; reuse
  their verified native/schema/Runtime probes rather than repeat app checks.
  Installed Core remains `local-84228718477a9363de03a33d`, app 0.7.9.

  A bounded isolated probe used the actual Core environment, verified configured
  DB path and real Core UID/supplementary groups, current existing validated
  login, real routes/UI trust/authority fences and the installed Runtime/host.
  It sent only four declared read queries (two serial, then a concurrent pair),
  printing stage/type/stack location/timing/status only: no request/result bodies,
  bearer/key or personal values. Serial registrations/visits reads returned 200;
  Runtime receive was 0.005 s. During the concurrent pair, one request reached
  `_send` with **handoff_remaining=-0.078 s**, then raised `TimeoutError` at
  `application_invocation_relay.py:_send:46` -> wire `remaining:75`, **before
  connect/send**. That HTTP response was 409; the other query returned 200.
  Admission cost for the failed request was 3.495 s (includes work before reserve).

  Confirmed causal path: `ResponseWaiter.reserve()` starts Core's 2-second
  handoff deadline before repeated expensive admission/UI/artifact preparation.
  Concurrent ARM work can consume it before application dispatch. The generic
  `invoke_with_relay` catch then misclassifies this known pre-send timeout as
  `Application result is unconfirmed; do not replay`. Runtime separately allows
  3 seconds from reservation to FD handoff, so changing only Core's timer would
  not resolve the protocol ordering/budget issue. This is a proven failure path,
  not a claim that every possible 409 has this cause or that trust may be skipped.

  The bounded Core fix identified here was to separate costly admission/preparation from the short
  reservation/FD handoff budget while retaining fresh actor/UI/lifecycle/key
  checks and response capacity limits; preserve not-dispatched versus unknown
  outcomes. Regress deterministic slow/concurrent preparation, actual revoke,
  package/key/UI drift and lost/uncertain responses. No automatic mutation retry,
  arbitrary timeout increase or application-specific Core condition.
  Child Center's independent misleading-access UI fix remains in that checkout,
  outside its delivered 0.7.9 ZIP. This turn changed only the diagnostic helper in
  ignored `.runtime` and this handoff; no product code, device restart/deployment,
  new login/grant, business mutation, package version or sibling source edit.

- **Requested Raspberry rollout completed, 2026-10-27.** Owner explicitly asked
  to deploy the completed CAP02/kiosk/optional-reader work. `rasp-3mm.local`
  (ARM64, Python 3.13.5) now runs immutable Core
  `local-84228718477a9363de03a33d`; previous pointer remains
  `local-a752cef1799fd6e5977059f7`. Preparation/deployment used `deploy.ps1` with
  its checked kit, detached systemd worker, ordinary installer backup/migration/
  health/rollback. Kit key
  `84228718477a9363de03a33d9e5ed929e1e0c062d9a3d0c666894a8ca05c30ad`.
  Fresh prepared evidence: **358 passed / 2 other-profile skips**, full frontend
  tests and build. Byte comparison confirmed Runtime/wire/protocol/SDK production
  inputs unchanged from the accepted 1709-test source below; that evidence reused.

  Core publication intentionally retains independent component pins. This rollout
  therefore separately applied the standard update/probe transactions to
  Platform Runtime and connector worker, both now
  `3400e4bdb089776b75cdc1b953ae7809de94dfbb7f60f267b7d581b8ee1efe14`,
  and all five active application hosts (Child Center, Command Probe, File Probe,
  Fleet, Task Probe), now
  `6215a0118d52d9144299d84535f57e8b48131b304e521334fcf022ddd670b37b`.
  Native image provider retained. Every host passed health and the real signed
  `three_mm.delegation.info` contract-1 probe; Core PID/generation stayed unchanged
  through these independent updates. Both detached jobs report succeeded; old
  component pins remain available through their normal rollback journals/pointers.
  The one-shot rollout helper/status is in the protected deployment job directory,
  not a new Core mechanism. Repeating a Core kit does not itself update app pins.

  Post-deploy `/ready` and `/kiosk/connect` return 200; served frontend is
  `main-DRjdNqM4.js`. Anonymous terminal-list request returns 401. Schema head is
  `b096b7e82f86`. Read-only comparison with the installer's persistent DB backup
  confirmed existing account IDs/password hashes/roles and application versions,
  identities/configuration/enabled state preserved; stable user subjects valid.
  Backup: `/var/lib/3mm/deploy-backups/local-84228718477a9363de03a33d/3mm.db`.
  No business command, new permission approval, app package upload, version bump,
  commit or publication. Owner-run Child Center/kiosk/reader tests remain next;
  refresh/re-login for the new login contract and re-pair old kiosk identities.

- **Child Center's two shared Core gaps completed locally, 2026-10-27.**
  Owner asked to implement them after the read-only handoff review. CAP02/CAP09:
  generic exact-artifact terminal management in Extensions, static Core
  `/kiosk/connect`, recoverable original enrollment/claim, single-flight auth-only
  renewal and revocation. Core owns credentials/proof/token, current kiosk catalog
  navigation and mounted-surface checks; applications keep ordinary public SDK
  calls. Human login is separate; no business invocation is replayed. Menu and
  Command Palette use the checked module identity, with no new header link.
  Admin list/revoke remain available when optional UI/key is broken. Encrypted,
  finite response recovery uses the existing sealed action journal, key lease and
  authority writer, not plaintext audit data or a new general-purpose token API.
  Migration `b096b7e82f86` preserves legacy rows without adopting null-incarnation
  credentials; re-pair them after rollout, no wipe/reset. Populated identity
  downgrade is guarded.

  CAP01/CAP03: zero optional reader/device selections work even with no devices;
  every supplied ID remains approved/not-revoked under final activation/staging.
  Explicit empty selection removes optional bindings; omitted configuration
  preserves the saved choice. Required/schema checks and non-device configuration
  remain enforced; defaults cannot restore a cleared optional binding. Selector
  supports clearing a saved optional device. Public contract/examples updated in
  [the existing contracts](EXTENSION_PLATFORM_V2_PUBLIC_CONTRACTS.md#core-owned-kiosk-pairing-and-optional-device-selection-2026-10-27).

  Verification on frozen WSL unprivileged Linux/Python 3.14 sources (overlapping
  groups, not totals): `9c4f444185c70546c2ed8c4436b47158aa67c0e160604e1c10184bcf1d73e367`
  **226 passed / 4 root-profile skips** actor/UI/signed invoke/diagnostics,
  optional resources, staging, relational consumers and migrations/extraction.
  `a1ea8ffa54e1fdccb206ded8c8194b5b86d16f7e55db8fb829b24d6fdce5e237`:
  **174 passed / 2 platform-profile skips** pairing/key/identity denial, optional
  selection, current consent/actor and delegation consumers; **692 frontend tests,
  type-check/build passed**. `8dbc3efe493048a7feb79fc2b0decac57d45929394ca3749d37d4f02b095cbb9`:
  **175 passed** final activation omission/clear, staging, consent, scoped access,
  startup and release builder; **22 passed** controller/bootstrap after explicit
  storage-cleanup failure fix, type-check/build passed. `b13e5299fdce87781e485095c961fd80e3811f5f7ba5013ed5326751d0dc36f1`:
  **25 passed** actual media/neutral-reference kiosk consumers after updating
  request fixtures; **37 passed** host export/credential/no-replay tests. Reused
  unchanged earlier Runtime/SDK evidence below; no new full-backend/root/ARM claim.
  Final source `51ff9006fe34704ea38a16f164dcff396b91d97ea4497f3b4159d826e61ac362`:
  full frontend suite, type-check and production build passed again after the
  dialog link-field layout adjustment and controller cleanup fix. Backend logic
  matches the checked groups above; later backend edits only remove unused
  imports/update current test request fixtures. New-file syntax/whitespace and
  scoped diff check passed. Only this handoff text changed after that check.
  Visual review used actual components with synthetic local HTTP fixtures,
  EN/BG, light/dark and 390px content/358px dialog widths; no device connection.

  Next: an explicitly requested rollout and owner-run Child Center/kiosk/reader
  acceptance on `rasp-3mm.local`. No deployment, package version, commit, branch,
  publication or Child Center edit here; user/M21 source preserved. General web
  installation lifecycle recovery remains the separate recorded CAP03 follow-up.

- **CAP02 closed locally for the current supported profile, 2026-10-27.**
  Finished the owner-requested Core/browser/native actor contract: stable opaque
  `subject_id`, current tracked login/nonce, immutable initiator/executor and
  explicit human application permissions separate from platform administration
  and service grants. Additive migration preserves accounts/passwords/roles/
  sessions/grants and refuses populated downgrade before erasing stable subjects.
  Refresh preserves a login, while numeric account/session reuse cannot inherit
  an older intent. Browser files require explicit permissions even for platform
  admin; connector receipt ownership binds the exact login across refresh.

  Added `host.access.getInfo()` and finite same-app operator delegation through
  `host.delegations.create/lookup/cancel` and native SDK execute/lookup. Existing
  sealed action journal and invoke relay hold the exact operation/input, human,
  executor, artifact/UI/config/grant/boot and expiry. Fresh admission/completion,
  fixed input digest, signed transport and actual host process pin prevent stale
  authority or executor substitution. No admin promotion/redelegation/automatic
  retry; consumed or unknown outcomes cannot run again after restart. A separate
  `three_mm.delegation.info` probe preserves existing host/task metadata ABIs and
  independent health/update/rollback. Required release files and Runtime actions
  are integrated. Public contracts include author examples and budgets.

  Verification: WSL unprivileged Linux/Python 3.14. Full backend on source
  `05cd1b422ab7bdcda10d214dd19b5ee44589d66e79410fe5495518ec4d0282ec`
  produced **4196 passed / 608 skips / 8 failures**. The eight failures were
  diagnosed, repaired and rechecked in affected groups; this is not relabelled
  as a later all-green full-backend run. Fixes cover metadata ABI preservation,
  additive user-column projections/downgrade guard, real tracked-login/valid
  kiosk fixtures and deterministic immutable theme ZIP fixture timestamps.

  Final production source
  `59a22e78f6de3312792ff12989dc083b193fd3d5bfc9261149cc7478fef86fe6`:
  **1709 passed / 7 optional-image/root-profile skips** full SDK/protocol/runtime
  plus independent host/Runtime components, including real update/rollback;
  **78 passed** delegation, scoped rights, diagnostic process, theme fixture and
  native-host/live-task readiness; **21 passed** affected migration/extraction
  group, with its last additive-column test fixture repaired separately below.
  **665 frontend tests passed**, production build and type-check passed on
  `566eae13a5d29e72ce73056a9658092b86fc5eafd52fa1ffb6554118925d24a6`;
  frontend bytes are unchanged in the final source.
  Final fixture source
  `e6ec9f3f6e70f4b6a8b7d1044c331e5cd78114c62c85b74e2a21779e42ce5834`:
  **4 passed** complete CRUD extraction file. Compared production/source files
  against 59a22e78: only that test changed; subsequent edits are documentation.
  Earlier successful backend cases for unchanged inputs are reused. Whitespace
  check passed. No full release/root/ARM acceptance claim.

  Acceptance boundary: SDK 1.3 ordinary own SQLite operator query/command ≤10 s,
  finite delegation ≤300 s. Cross-installation composition is CAP14; named
  guest/customer identities and business ACL remain app-owned. No credentials or
  bearer grant reach the browser/context. No device access/deployment, package
  version, commit, branch or publication in this turn; user/M21 source preserved.
  A later explicitly requested rollout must include Core, Runtime and required
  pinned hosts, then fresh login for pre-nonce prototype sessions and owner device
  tests. Web lifecycle recovery remains the recorded separate CAP03 follow-up.

- **CAP02 first Core HTTP/native SDK profile completed locally, 2026-10-27.** Owner confirms
  the recovered application now works. This closes the pending manual activation
  probe below; it is not acceptance of every lifecycle/profile or external Barsy
  operation. Implemented one bounded CAP02 path: Core forwards the verified human
  or kiosk identity and current declared application permissions into the real
  native SDK `OperationContext`. Frozen `context.actor` and immutable permission
  tuples distinguish user/kiosk/anonymous/service/worker/installation observations;
  `has_application_permission` never infers business rights from platform admin.
  Invalid/mixed human/nonhuman claims are rejected after envelope authentication.
  Removed the implicit platform-admin bypass specifically from operator routes
  and operations; explicitly declared administrator endpoints keep their separate
  platform-role check. `/access` reports platform administration and exact current
  application permission IDs separately. Existing direct/role/group grants and
  fresh relay admission/completion checks remain the authority source. Current
  tests/consumers and the public contract were updated together; no schema change.

  Verification on frozen source
  `80737f02698ad034a6a8c107626c0fdf30116993cbe6a2340d2374234c51b866`:
  **55 passed** HTTP/access/actor/UI-host; **221 passed** group/user/session,
  compiled UI/provenance, real signed UI/service-grant separation, invocation/
  response relay, peer, consent/lifecycle and current app/CRUD consumers;
  **311 passed** browser media/file review/execution/authority, relational and
  peer consumers, transport and startup; **460 passed / 2 optional image-profile
  skips** full SDK plus native host/dispatch/file/relational-session/peer-host.
  Only additional actor tests and documentation changed after that source.
  Final source `7a2ec90208ca92ebf5771d43c6ab4ef8c463b2426c9b54a142af165110be4502`:
  **149 passed / 2 explicit optional-image/root-driver skips** complete actor file
  plus independent host component/release builder. The actor file overlaps 28
  earlier SDK cases and adds 8 worker/peer/invalid-audience cases. Production
  bytes match the earlier checked source; that unchanged evidence is reused.
  WSL non-root Linux/Python 3.14; no full release/root/ARM claim. Whitespace passed.
  No frontend source change or frontend build; no deployment kit, device mutation,
  version change, commit or publication. User/M21 source changes preserved.

  At that first-slice handoff delegation/browser/resource completion remained
  open; the completed local profile is recorded above. Worker/peer actor views
  do not invent a delegated human or bearer token. A later rollout must update
  required independent pinned hosts; matching SDK version alone does not add
  the new actor API to an already installed host. Contract:
  [CAP02 operation actor](EXTENSION_PLATFORM_V2_PUBLIC_CONTRACTS.md#cap02-operation-actor-and-human-application-permissions-2026-10-27).

  Owner additionally requires a future **web recovery mechanism** for stuck app
  installation/activation/update, to avoid dependence on SSH/manual rescue.
  Recorded at [CAP03](CORE_SIMPLIFICATION_PLAN.md#cap03-пакети-и-жизнен-цикъл):
  visible recovery action/status, explicit confirmation, verified stop with
  preserved data/package, then fresh access review and continuation. Reuse the
  existing Core recovery API; no automatic effect retry or grant restoration.
  This is a planned separate step, not a request to implement recovery now or
  interrupt CAP02. That request was recorded without implementing recovery UI.

- **Raspberry updated by owner; explicit recovery completed, 2026-10-27.** Owner
  reported deployment complete and continued the previously described recovery
  step. SSH confirms `/opt/3mm/current` points to
  `local-a752cef1799fd6e5977059f7` and Core is active. Before recovery, native
  Child Center was already inactive after the owner update, while its Core row
  remained `recovery_required` at the same 0.7.8 artifact.

  Used a fresh administrator login and the existing public
  `POST /api/v1/application-extensions/org.3mm.child-center/lifecycle/recover`
  with explicit reviewed-outcome confirmation. Confirmed response: disabled,
  enabled false, active_version null, error null. Independent systemd observation:
  inactive/dead, unit disabled, MainPID 0, no pending job. All **3 application data
  files have identical before/after content hashes**. No direct database repair,
  uninstall, reinstall, rollback or application activation was performed.

  Recovery left the historical grant sealed as active at an obsolete execution
  epoch, so preview still reported `access_saved=true` although fresh stopped-
  candidate activation requires a current grant. Confirmed the epoch mismatch
  read-only and revoked only that obsolete record through the public authority
  API using its exact current revision. Fresh preview now succeeds with disabled,
  enabled false, `access_saved=false`, selected scopes empty. Optional connector
  access remains an owner choice. No new native/resource/account consent was
  granted, no application code was started and no connector request was made.
  Temporary diagnostic administrator sessions were explicitly logged out;
  credentials/tokens were not saved or emitted. Next is **owner** Ctrl+F5 ->
  Application access -> Allow access -> Activate version, then the app probe.
  Device activation acceptance remains pending that manual test. No new code or
  runtime checks in this docs-only handoff; existing kit evidence below is reused.
  Follow-up observation: historical saved-selection presentation after uncertain
  recovery should distinguish an obsolete epoch from currently renewable consent;
  the supported explicit revocation completed this operator recovery.

- **Slow activation timeout fixed locally; replacement kit ready, 2026-10-27.**
  Owner enabled diagnostic SSH. Read-only inspection confirms Raspberry Core is
  `local-434ac4d9b979b0d5f6547ccf`. Logs show native consent succeeded at 17:02:17,
  activation returned 409 at 17:03:09, and helper reported its caller disconnected
  at 17:03:11. The exact Child Center 0.7.8 instance started at 17:03:06, remains
  active without restarts, and has no retained activation rollback preimages.
  Root read-only SQLite/selected metadata inspection confirms candidate/runtime
  sha256 `fc77ca39c64ea0559b9c8ef0a3ffceedbb8607053f8bcc8fbbea726c7e09b90d`,
  health budget 30 s, and Core `recovery_required`, disabled, no active version:
  helper execution finished after Core's 40 s transport wait had expired. The
  later preview 409 is the resulting lifecycle fence, separate from the DTO fix.

  Ordinary activation now reserves 120 s for package validation, data preimages
  and systemd preparation in addition to the manifest health window. Shared health
  polling uses a monotonic elapsed deadline and caps each probe/delay to its
  remaining time; late health success cannot confirm activation. Actual transport
  loss still quarantines execution and cannot replay a consumed lifecycle ticket.
  No authorization policy, schema, automatic retry or recovery bypass was added.

  Reproduced three failures before production edits on frozen source
  `1848a6a73c9a7fe5122f8a77b1d2c3c53f8e9487e71df59384a48d4745935b60`:
  healthy delayed helper response caused 409; 3 s health budget took 33 s; late
  ready response was accepted. Final source
  `0de0b7e38d783d6248669a77cbb96a9eb61a91f356f4f906037a0e8d5502f6ae`:
  **702 passed / 171 explicit root-helper skips** in 150.83 s. Targeted Core
  lifecycle/recovery/consent/UI/connector settings, relational activation/boot/
  reactivation consumers, runtime activation/lifecycle/helper/requirements,
  startup/release/controller checks include all four new cases (including genuine
  timeout staying fenced with no replay). Reused unchanged **635-test** frontend,
  Vue type and build evidence `856e9522835962665df887d80ac565b260bfc42dd2fda8dfa6a9940612a4ca2a`.
  This is local non-root evidence, not full root/ARM acceptance.

  `deploy.ps1 -Action Prepare` completed in **182.661 s** controller time. Validated
  hashes and inspected the packaged production timer code and corrected compiled
  consent decoder. New immutable **aarch64 / Python 3.13 / image provider** kit,
  14.56 MiB:
  `.runtime/deploy/artifacts/a752cef1799fd6e5977059f7b4edcb102001c7c8e20b7581282038d4ab463b6f`,
  release `local-a752cef1799fd6e5977059f7`. Previous kits remain untouched.
  Next: owner deployment of this kit; then explicit lifecycle recovery to verified
  stopped/disabled, fresh access review and owner activation test. Existing public
  `POST /{module_id}/lifecycle/recover` requires current admin and explicit
  `confirmed_external_outcome_reviewed: true`; no direct DB repair or implicit
  acknowledgment is permitted. Current device remains in its observed state.
  No remote activation/stop/restart/reinstall, grant change, reset or deployment,
  sibling app edit, external connector call, version bump, commit or publication.
  SSH diagnostics performed reads only; credentials never enter tracked inputs
  or reports. Documentation updated after source freeze.

- **Consent preview contract fixed; replacement Core kit prepared, 2026-10-27.**
  Owner reports Child Center 0.7.8's Application access cannot load after upload.
  Found a general Core mismatch: current backend consent previews always include
  `optional_resources`, while the strict frontend DTO omitted/rejected that field,
  even when it was empty. Updated the exact DTO/metadata validation and current
  fixtures; preserved explicit scope subsets, native consent and all owner/artifact
  checks. Unconfigured optional connectors are metadata, not offered/granted rights;
  local-only consent remains possible without configuring the external service.

  New cross-language test feeds actual authenticated FastAPI HTTP preview responses
  through the real TypeScript decoder via the existing Node/esbuild toolchain.
  Covers ordinary resources and only an unavailable optional connector with no
  offered scopes. Reproduced the old decoder failure first on frozen source
  `b7946072f5e648297fc48696737befd3c5ff3600169a279c7ba1b5efa6d8fbde`.
  Final source `8f355d47d2434dd65ff76addb3b3be46f7d2fa5e23de002c9f329af8125b77a0`:
  **425 passed / 4 explicit root-helper skips** targeted consent/connector settings,
  UI host/authority, configuration, source/authority, staging/relational candidate,
  startup/release/controller checks, including the new HTTP-to-TypeScript test.
  **635 passed** full frontend suite + Vue types/production build. New negative
  metadata/selection cases and a dialog test confirm no automatic approval and
  one explicit native approval with an empty application-scope selection.
  Reused unchanged broad integration evidence below; no full ARM/root claim.

  Permanent `deploy.ps1 -Action Prepare` completed in **109.267 s** controller time.
  Replacement immutable kit:
  `.runtime/deploy/artifacts/434ac4d9b979b0d5f6547ccf5315aa30fb462c726a5a71af139da30d05d45fbc`,
  release `local-434ac4d9b979b0d5f6547ccf`, **aarch64 / Python 3.13 / image provider**,
  14.56 MiB. Exact commands and content-bound evidence are in `checks.json`.
  Prior kits remain untouched and do not contain this fix. Owner's next step is
  deploying this kit, refreshing the browser, then Application access -> Allow
  access -> activate the reviewed version. No app uninstall/data reset is needed
  for this DTO fix. Live device cause/acceptance remains owner-observed: read-only
  SSH authentication was unavailable; no remote release identity was verified.
  No device mutation/deployment, sibling app edits, real connector call, version
  bump, commit or publication. This handoff changes documentation only after freeze.

- **Earlier combined Core deploy prepared, 2026-10-27 (superseded by the kit above).**
  Owner requested preparation only.
  Ran the permanent `deploy.ps1 -Action Prepare` with an explicit reviewed target
  selection for connector setup, UI host/authority, configuration, source/consent,
  package staging/relational registration/candidate, startup/release and controller.
  No code/test inputs changed since the preceding final verification. Reused the
  broad unchanged integration evidence below; the new kit records its own targeted
  checks: **424 passed / 4 explicit skips**, **627 passed** full frontend suite,
  Vue types and production build. Python 66.457 s; controller 111.159 s; complete
  PowerShell preparation **115.4 s**. Cached dependencies/native wheels preserved.

  Ready bundle:
  `.runtime/deploy/artifacts/f366fc6b45a3f5aede6473c97465cb620ed310da794f17af24c09ecd4050ffbc`,
  release `local-f366fc6b45a3f5aede6473c9`, **aarch64 / Python 3.13 / image provider**,
  14.56 MiB kit. Ready/checks/file hashes validated; inspected the Core archive for
  all three new connector settings/provenance production modules and absence of
  Git/environment/remote-attachment material. Inputs and exact check commands/log
  digests are in its `checks.json`. This remains targeted local evidence, not full
  Root/ARM acceptance or a published release. Locale + connector settings and prior
  current Core work are included; old immutable kits are not altered.

  No SSH, upload, remote observation, deployment, version change or publication.
  Owner can deploy this exact bundle without rebuilding using
  `deploy.ps1 -Action Deploy -Bundle <that folder> -SshHost raspberry@rasp-3mm.local`.
  Completion is **`3mm update succeeded`**, after Core installation and default-host
  publication. Existing independent Runtime/active-host pins remain preserved;
  this is not a claim of their full CAP01 rollout. This handoff changes docs only,
  after the bundle froze; its checked production inputs remain unchanged.

- **Connector settings from Extensions implemented locally, 2026-10-27.** Owner
  requests a settings gear for applications with settings and connector setup.
  The protected package catalog derives `has_connector_settings` from each
  validated immutable artifact. Extensions shows a Unicode gear only for those
  versions; it opens a Core-owned Basic/Bearer/API-key/unauthenticated connection
  form, not application code. Another version must first follow its existing
  stopped candidate/preparation flow. Theme/initial/live language/EN fallback
  remain Core-owned; removing the Extensions language remount key preserves drafts.

  One key/guard/current-administrator transaction saves declaration-owned origin/
  reference keys + binding + optional encrypted credential + sealed receipt.
  Unrelated configuration is preserved. CAS covers artifact/Core generation/app
  incarnation/epoch/configuration/binding/secret revisions. Rotation/revocation
  shows affected bindings and requires confirmation, withdrawing existing access.
  Actor validity is checked again before commit; errors never echo credential
  input. Receipts belong to artifact/incarnation/admin/login session, survive Core
  restart and token refresh within that login, and refuse another login/actor/app.
  The Core client never refreshes/replays mutations. Session storage contains only
  request ID/rejection disposition; lost/malformed/bare-conflict outcomes remain
  pending for lookup. A definite refusal still requires successful outcome lookup
  before another explicit edit. No credential material/digest enters receipts,
  inspect, audit, application components or invoke. Same-origin code is still not
  a browser sandbox.

  First setup creates a stopped, unapproved inert installation without service/
  wheel execution, external HTTP or application SQLite namespace/migration. Partial
  multi-connector setup stays unreviewable until all required configuration is
  supplied. Existing registration/adoption records remain immutable; separately
  sealed configuration transitions preserve their exact other provenance. Own-SQLite
  preparation/recovery remains unchanged. A stopped unreviewed installation can
  configure before first native consent; running compatibility instances must stop
  first. Save withdraws authority; then stop if running, review access and activate.
  No automatic stop/start, grant resurrection, data reset or schema migration.

  Verification: broad application/module backend selection on frozen source
  `3ca0a1cc87a496c108862a8ed5be7d1fca9e5918ceec3ee29d060804d79cef71`:
  **2738 passed / 597 explicit Root/optional-profile skips** in 667 s. Shared source,
  staging/registration/adoption, broker and lifecycle code is unchanged afterwards;
  that evidence is reused. Final source
  `/var/tmp/3mm-connector-settings-tests/sources/bba57f1162cf90d92bf2b01ee0a7a961fb620a8f0ca9b1e02fad82254f37dc8b`:
  **627 passed** full frontend suite + Vue types/Vite build; final connector tests
  had **31 passed / 1 fixture failure** (the stopped-adoption fixture lacked the
  human-permission tables). Only that fixture was completed with full test metadata;
  its rerun on source `dc4688275a54b159f4667ae7e180fce21c944a6096c05dfed9db29e67ce357cc`
  **1 passed**. Thus all **32 connector cases** are verified, including first setup,
  atomic failure, concurrent initial save, real grant withdrawal, CAS/isolation,
  old/new own-SQLite registration, final-session expiry, token refresh and receipts.
  Production files match the final tested source; afterwards only fixture/docs
  changed. Logs: `/var/tmp/3mm-cs-{backend-integration,frontend-final,frontend-build-final}.log`.
  Diff/whitespace checks passed. Isolated fake-data browser review covered desktop
  light/EN and 390px phone dark/BG, scrolling/footer; preview tab/server were closed.

  Scope is the Core entry from Extensions. The proposed in-application public
  `administration.connectors` facade/route allowlists remain unimplemented and are
  not advertised; applications need no private API for this Core settings flow.
  Native connector execution remains the existing SDK broker. No sibling Child
  Center changes, real Barsy check, device/SSH/deploy, version bump, commit or
  publication. Earlier ready kits stay immutable and exclude this work. Next is
  owner-selected combined deployment/device acceptance, then the separate app's
  connector declaration and explicit connection/catalog operation port.

- **Child Center presentation contract implemented locally; connector contract
  audited, 2026-10-27.** Owner supplied the sibling's
  `CORE_PRESENTATION_CONTRACT.md` and `CORE_CONNECTOR_ADMINISTRATION_CONTRACT.md`
  and requested general Core fixes. Completed the bounded presentation result:
  `ApplicationHost.presentation.version = 1`, synchronous frozen locale info,
  live subscription/unsubscribe, cleanup and retained-handle refusal on disposal.
  The actual compiled application route loader supplies the same reactive root
  `locale` prop; updates patch its component instance, preserving form/error state.
  Both use the existing effective Core/header i18n source, including its fallback.
  Host feature metadata advertises `presentation_version: 1`; native SDK/manifest
  versions are unchanged. Existing Core theme tokens/variants remain authoritative.
  Child Center's current `source/frontend/local` roots already accept this prop;
  no sibling code, catalogue, package or version was changed. Catalogue ownership
  and regional/base/EN per-key fallback are documented authoring rules, not a new
  compiler catalogue validator.

  Connector setup is **still open**, not implemented by this slice. Existing
  encrypted Basic/bearer/API-key storage and connector broker are present, but
  separate secret/binding REST calls cannot implement the proposed atomic setup.
  The missing common operation must save configuration keys + secret reference +
  binding together, support installed inert/disabled bootstrap from Extensions,
  preserve sealed configuration provenance and the prepared relational lifecycle,
  and provide explicit route allowlists/CAS/current-actor checks/redacted durable
  outcomes. Do not mount unapproved native UI to resolve a required connector,
  introduce a private application HTTP/token workaround, or claim Barsy readiness.
  No connector credentials, grants or business-network operation were touched.

  New verification on frozen Linux source
  `/var/tmp/3mm-presentation-contract-tests/sources/fa347bab9ef72924bd5368f7cab9909a7309681ddd0c93efdd7c603a249dfe40`:
  **612 passed**, full frontend suite including actual dynamic route binding,
  initial/live locale, draft/error retention, explicit unsubscribe/disposal and
  existing shell/theme cases; Vue type-check and Vite production build passed.
  **60 passed** backend UI-host/UI-authority/administration integration checks,
  including existing denial/revocation boundaries; whitespace checks passed.
  Logs: `/var/tmp/3mm-presentation-frontend-{tests,build}.log`. Afterwards only
  documentation changed; checked production/test files are unchanged.
  No live device/browser acceptance, deployment, SSH, commit or publication.
  The earlier immutable ready kit below is preserved and excludes this new code;
  a later combined deploy must prepare a new kit. Next bounded implementation is
  the connector administration/bootstrap contract, before a Barsy product port.

- **Owner-operated Raspberry Core deploy prepared; Child Center contract review,
  2026-10-27.** Owner asks for deployment instructions and review of the other
  `child-center` chat (local thread `01a17b8c-3664-7bf0-ad39-35f743afd21a`).
  Read that chat and the sibling's presentation/connector contracts; no message
  sent to it and no application source edited. Current Child Center 0.7.7 has
  Core-owned presentation and EN fallback catalogues, but initial/live locale
  is absent from the public Core host. Barsy connector execution already exists;
  missing generic administrator setup/credentials UI and bootstrap/atomic binding
  are CAP06/09/12 gaps. Current Child Center declares no connector and its Barsy
  catalog/account/payment operations are not ported. No live Barsy test occurred.
  Owner's rule is no private HTTP/token/CLI workaround for application integration.

  Repaired the three stale deploy-template assertions to follow the permanent
  controller/immutable installer rather than the retired PowerShell monolith.
  **51 passed** systemd-template/deploy-controller checks plus Windows command
  doubles (no network). Local `deploy.ps1 -Action Prepare` completed in **92.763 s**:
  `.runtime/deploy/artifacts/06b4bba745029044ee43e9c5be4b4023a936236122e9421e8af007cd4344bc4d`,
  release `local-06b4bba745029044ee43e9c5`, aarch64 / Python 3.13 / optional image
  provider included. New checked evidence: **1338 passed / 2 explicit optional
  Pillow skips** targeted Python selection (previous isolated-provider conformance
  remains valid), **610 passed** full frontend tests plus types/production build.
  Selection, exact source, environment, hashes and logs are in its `checks.json`.
  This is a local, unpublished ready kit, not a release/full Root/ARM acceptance.

  No SSH, transfer, device change or deployment was performed. Owner can run
  `deploy.ps1 -Action Deploy -Bundle <that exact folder>` against
  `raspberry@rasp-3mm.local`; Status/Logs observe the detached job. This controller
  updates Core and publishes the native host default, while preserving existing
  independent Runtime/host pins. Do not describe its success alone as a complete
  CAP01 native-component rollout. After the owner's Core result, inspect current
  component/active-instance identities and complete the explicitly selected
  Runtime/host health/rollback updates through their existing CLI. Locale and
  connector-administration contracts are reviewed next work, not implemented here.

- **CAP01 supported profile implemented locally, 2026-10-27.** Owner requested
  both remaining parts: optional resources at installation and remaining current
  provider observations. Deployment is still explicitly deferred. SDK 1.3
  `optional_resources` accepts up to 16 exact declared command/connector/event/
  session scopes. Missing/incompatible optional resources can be omitted from
  review; required resources and the author's configuration schema still apply.
  Empty optional device selectors are omitted by the existing configuration UI.
  Optional scopes default unselected. Their loss/replacement does not withdraw
  required authority, but each optional use must match the exact sealed approved
  resource. A newly appearing/replaced provider requires fresh explicit consent;
  no automatic selection, fallback, grant, mutation retry or data reset.

  Resource rows now include `required`. Current connector/event/task workers have
  bounded local nonce/contract/kernel-principal probes; event/task observations
  also verify the exact signed host instance/artifact/configuration. Task probes
  cannot claim, dispatch or tick work and expire after lost Core connectivity.
  The task unit owns `/run/3mm-tasks`; Core remains administrable when probes fail.
  Publications and status/peer metadata use the actual Core-local journal/read
  profile, without business HTTP, remote reporting or a remote-connectivity claim.
  Optional session loss no longer makes the required grant globally ineffective.

  Current profile is explicit: owned data/prepared SQL and peer-consent lifecycles
  cannot be waived through this optional field; unresolved sensor commands and
  unsupported combinations reject. Browser discovery remains reviewed admin
  opt-in, not operator/kiosk delegation. Current SDK/frontend and applicable
  independent Runtime/host components are required; matching version labels alone
  do not install new APIs into old components. Later rollout must explicitly
  update/probe/rollback those components. No Root/ARM/live acceptance is claimed.

  Evidence: broad Linux source
  `/var/tmp/3mm-cap01-final-tests/sources/ad9a24aa65a52735c01890d659cdd8d50fb5623e24f1cd5a0284d94959a19feb`:
  all `backend/tests/test_application_*.py` plus module packages, startup, release
  builder, transport and Runtime/event processes completed at **2788 passed /
  599 explicit skips / 1 failure**. The failure was an outdated retained-data
  test double missing `platform_requirements` and keyword support; it was updated,
  with the full retained-data/optional-resource set **14 passed**, including a new
  incompatible-provider case. This broad run was not initially green.
  Final frozen source `ff25cfad6648fb7dd7acba93e2a491ea6bef287b120e97cd541d7bc8e7f9e18d`:
  **118 passed / 24 deselected** focused authority/consent/session/resource/native
  worker/retained-data checks. The only production changes after the broad source
  were the optional-session status filter, avoiding a redundant nonoptional
  resolution, and stricter provider contract scalar validation; affected checks
  were rerun on the final code, other evidence reused for unchanged inputs.
  Full SDK/protocol: **1046 passed**, isolated Pillow profile; frontend **113
  passed**, type-check and Vite build passed. Runtime/native component group:
  **598 passed / 4 explicit skips / 3 pre-existing deploy-template failures**,
  completing the initially interrupted run's suffix rather than rerunning passes.
  The three assertions expect the retired monolithic deploy.ps1 implementation
  (`test_installer_owns_the_atomic_release_and_rollback_boundary`,
  `test_deploy_accepts_setup_or_application_runtime`,
  `test_deploy_records_the_validated_project_version`). Their file and deploy.ps1
  were byte-identical to the previous handoff. Record for the deployment-tooling
  scope before its next release gate; do not claim a fully green runtime suite.

  No deployment preparation/rollout, device/browser actions, version bump, commit
  or publication. Preserve independent Child Center/M21 and accepted AP/setup/
  menu/Fleet work. Pending CAP11 Download change still awaits combined rollout.
  Next owner-selected CAP can proceed; device acceptance remains a later step.

- **Earlier CAP01 resource observations and administrator browser access complete locally,
  2026-10-27.** Owner authorized continuing CAP01; deployment remains deferred.
  `platform.discover_resources(scopes)` observes at most 16 exact own scopes via
  the existing signed `platform.discover` subrequest, without another registry,
  Runtime action, grant, selection, namespace creation or business operation.
  The shared report separates declaration/configuration, application service
  access, readiness/reasons, provider contract and the selected resource identity.
  Unapproved scopes are redacted; configured-but-unobserved executors stay unknown.

  Current probes reuse command catalog/health, signed file-worker metadata,
  prepared SQL host status and trusted session connectivity. Optional image
  readiness is separate from files: a bounded child checks in-memory PNG/JPEG/
  WebP encode/decode; missing -> unavailable, broken/timeout -> unknown. Neither
  Core nor the file executor imports Pillow. Core-local checkpoint/identity reads
  can report ready; other resource families have no invented readiness. IPC holds
  no DB/key leases; current package, grant, authority/recovery/resource and runtime
  bindings are reread before returning. Authority change discards the response.

  Reviewed administrator UI routes explicitly opt in with
  `administration_reads: ["resources.inspect"]`; browser callers use
  `host.administration.resources.inspect(scopes)`. Core checks the current human
  session and source/build trust before and after observation. No caller-selected
  other installation, secret, private path or delegated service credential; the
  browser validates/correlates a bounded public projection. Service access remains
  separately required. No screen/menu addition or application version change.

  New evidence, frozen source
  `/var/tmp/3mm-cap01-resource-tests/sources/7162e897b7f84fc799f74896980d47ea6d693062b011e18ad53b42f81c6f8a6a`:
  **501 passed** SDK plus affected protocol contracts, with Pillow 13.0.0 only in
  isolated `/var/tmp/3mm-cap01-image-provider` (Core test venv unchanged);
  **190 passed** affected Core/resource/UI/admin/transport/media/requirements,
  relational-status and session-runtime integration; **138 passed / 1 explicit
  skip** release-builder/native host/Runtime components and application-host
  consumers (isolated-root host driver not run). **75 passed** browser host/UI
  contract checks; frontend type-check and Vite build passed. Frozen source
  `73bb6ec58c079079bf64609dd7ada011b3769856f29ef9f797f19339bf0bd126`
  adds documentation and two packaged-host tests only: **2 passed**, both with
  and without the image provider, clean isolated interpreter, codecs absent from
  the parent and no Core imports. Prior green evidence is reused for unchanged
  content; no Root/ARM/hardware/browser visual acceptance is claimed.

  **At that handoff CAP01 remained open:** actual optional resource dependencies at installation,
  real probes for remaining families and any needed operator/kiosk browser
  profile. Existing source composition can remain unreviewable/redacted if a
  declared resource is unresolved; transport optional flags do not waive that.
  Next bounded result: optional-resource composition with exact retained choices,
  fresh consent and healthy/missing/revoked scenarios for the chosen profile.
  No deployment preparation/rollout, device/browser actions, commit, version bump
  or publication. Preserve Child Center/M21 and accepted AP/setup/menu/Fleet work;
  pending CAP11 Download correction still awaits the later combined deployment.

- **Earlier CAP01 SDK discovery and pre-activation dependency gates complete locally,
  2026-10-27.** Owner asks to close CAPs in order and authorizes continuing CAP01;
  deployment remains explicitly deferred. The first SDK observation composes
  signed platform/command reads with required/optional outcomes, a single <=35 s
  deadline and final identity fence; no selection, grant, retry or effect dispatch.
  Core reports only the listener's actual allowed operation set.

  The second slice adds `platform_requirements` to SDK 1.3 application descriptors:
  at most 16 unique transport needs, exact contract version/operations, required
  missing -> blocked and optional missing -> degraded. A shared pure assessment
  now serves both Core and SDK. The administrator-only package report revalidates
  exact bytes and is read-only/no-store; it is never accepted as an activation
  ticket. Standard stage/activation checks precede lifecycle/key/helper changes.
  Native activation rechecks before application paths/keys, stop or database work.
  Prepared relational registration/adoption and preparation/start/upgrade issuers
  check before issuing work; their native helpers check before package effects.
  Outcome callbacks, disable/uninstall and recovery keep their existing rules.

  Validated author declarations reach `context.platform_requirements` as a tuple,
  with host validation before importing application/migration code. No startup RPC
  is added; absent declarations leave existing metadata unchanged. The deployment
  contract requires the shared model/SDK files and the new Core assessment helper.
  No database migration, new grant scope, resource waiver, service or transport
  action. Optional dependencies do not bypass normal fresh consent or restore an
  old grant. Unsupported installed applications remain stoppable/removable.

  Limits: the persistent field checks **Core transport support only**, explicitly
  leaving permission approval, resource bindings and runtime readiness unevaluated.
  It forbids resource `binding_id`; optional transport flags do not make existing
  command/session/SQL resources optional. Actual independent Runtime/host/provider
  availability, other resource-family observations, optional-resource composition
  and browser SDK exposure were left for the third slice above. Optional-resource
  composition and remaining profile gaps still prevent marking the whole CAP closed.

  Evidence on unchanged Linux dependency environment: runtime snapshot
  `/var/tmp/3mm-cap01-dependency-tests/sources/89ca03281c7783ba9030487f4d220ef7a2b9d0856ff9ce61c91d486f5270211a`;
  final `101bf769fd2f0130977a2fc30f497f3c3b518bc93989be38d085a7a552489a55`
  was verified to differ ONLY in deployment-contract required-file ordering.
  The initial broad run was interrupted after **70 builder failures / 756 passed /
  215 skipped**; it was NOT a green run. Canonical ordering was repaired. Reused
  737 unchanged passing cases and 215 explicit skips; reran ALL 89 builder tests
  plus every unfinished node, asserting the same 1697-node collection: **371
  passed / 374 skipped / 952 evidence-reused deselections**. Thus the chosen Core,
  lifecycle, protocol and relational set completes at **1108 passed / 589 explicit
  privileged-profile skips**. Two later tests-only stop/removal regressions passed
  on unchanged runtime code (**1110 passed** including these additions). Separate
  complete SDK/native component/Node groups: **451 passed / 2 explicit skips**
  (optional image dependency, isolated-root host driver). Additional staging,
  privileged archive validation, release-smoke and Node readers: **112 passed**;
  these overlap the Node group, so do not sum all groups as unique tests. Initial
  focused 27/12 checks are included, not extra totals. No Root/ARM live acceptance
  is newly claimed. Declaration parsing, denial before effects, current consent,
  unchanged old data/keys, report auth/integrity and continued administration are
  covered. Source/runtime checks were not repeated for subsequent docs-only edits.

  No frontend changes/build, device/browser actions, deployment preparation,
  rollout, version bump, commit or publication. Preserve independent Child Center
  and M21 source. The third slice above continues family/provider readiness and
  browser access; retain explicit deployment deferral and the pending local CAP11
  Download correction. Do not reopen accepted AP/setup/menu/Fleet checks.

- **Child Center checkout and migration assessment, owner-requested 2026-10-27.**
  Cloned `https://github.com/ldobranov/3mm-child-center` into sibling Desktop
  `3mm-child-center`, HEAD `15349d0`; no application source edits, commit, push,
  deployment, live Barsy request or hardware action. Scope ends at assessment.
  The deterministic builder, rather than the historical 0.6.7 JSON templates,
  produces 0.7.6 / schema 0020 / SDK 1.0, ReliableRuntime, 70 operations,
  eight routes, two event subscriptions and three legacy jobs. Domain covers
  kiosk/client registration, bracelets, visits/stays, Barsy accounts/consumption/
  payment, optional sensor-confirmed access and privacy/reconciliation journals.

  Current working-tree Core's real `validate_module_package(...,
  architecture="aarch64")` rejects the generated bytes with `scheduled application
  jobs are retired; no supported scoped scheduler`. Replacing jobs with CAP08
  tasks alone is invalid: current task declarations exclude connectors, events
  and scoped relational composition (`three_mm_protocol/application_extension.py`).
  Sensor-bound commands also fail scoped source composition with
  `sensor_contract_unresolved` (`application_authority_subjects.py`). These are
  generic capability gaps, not grounds for restoring legacy jobs or app-name
  branches in Core. SDK 1.0 alone is not the demonstrated package rejection.

  Migration direction: one authoritative current descriptor/build instead of
  cumulative release patch scripts; current SDK/resource declarations and
  scoped storage preparation/migrations; route operations via the public
  `@3mm/application-ui/v1` host instead of app-managed authToken/HTTP calls.
  Connector/secret administration and kiosk enrollment/renewal need a separate
  public-host coverage audit, since invoke alone does not replace those flows.
  Preserve durable business IDs, uncertain-outcome review, access confirmation
  and payment safeguards. First bounded implementation candidate: registrations,
  clients and local visits on the public host/scoped storage, followed separately
  by generic recurring effectful-work composition and sensor command support.
  Existing 2026-09-23 incident also identifies equal 10-second operation/connector
  budgets; migration must use bounded durable steps and slow/lost-reply checks.

  New evidence: WSL cached test environment, **71 passed / three existing
  Pydantic deprecation warnings / 14.60 s**, current sibling source plus current
  Core SDK, exact suites `test_billing_units`, `test_closure_reconciliation`,
  `test_privacy`, `test_access_journal`. These are synthetic domain checks, not
  complete application, native activation, UI, ARM execution or device acceptance.
  No frontend build needed for this assessment/documentation handoff.

- **Permanent local deployment path implemented, owner-requested 2026-10-27.**
  Owner explicitly requested the `deploy.ps1` implementation while testing CAP11.
  The wrapper now supports Prepare / Deploy / Status / Logs, defaulting to
  `raspberry@rasp-3mm.local`, ARM64 / Python 3.13 with interactive SSH/sudo.
  Current working source is frozen without Git mutation/publication or version
  changes. `tools/deploy.py` reuses the existing release builder and lab source
  exclusions. Immutable ready kits retain source/check inventories and checksums.
  Content/environment caches cover frontend dependencies/output, Python evidence,
  and ABI-specific offline native wheels. Explicit reviewed TestPaths selections
  get distinct targeted evidence; unchanged local inputs can reuse the last
  successful selection. Published release gates remain unchanged. Node generated
  `.tmp`, `.vite`, `.vite-temp`, `.vue-global-types` directories are excluded from
  dependency integrity comparison; actual package files remain checked.

  `tools/deploy_remote.py` runs a root-private verified snapshot as a detached
  systemd job, uses the existing immutable Core backup/health/rollback installer,
  retains the kit when the installer consumes its separate archive copy, preserves
  installed frontend origin/networking and reuses an exactly matching native host.
  Changed native code is built/checked offline before Core activation, then the
  existing journaled publisher selects the default for new applications only.
  Existing instance pins/grants/data/menu remain unchanged. A repeat observes
  active work; failed/uncertain dispatch is never blindly replayed. Status/Logs
  do not prepare/upload/start work. Final success is `3mm update succeeded`.

  CAP11 owner reports uploads/deletion and other checks work, but Download did
  not save and publish/transform returned 403. Owner confirmed the separate
  permissions were unchecked and will enable them; await their result. Do not
  weaken grants or call CAP11 fully accepted. Download had a separate Core CORS
  defect: `X-Content-SHA256` / `X-Chunk-SHA256` were hidden across UI/API ports.
  Expose these integrity headers alongside the existing auth header; preserve
  origins/auth and SDK checksum enforcement. Real signed-worker HTTP regression
  checks actual Core CORS options, checksums and untrusted-origin denial.

  New final bounded Linux checks **231 passed / 1 explicit isolated-root skip**:
  deployment controller (25), media HTTP/admission, Core startup, release builder,
  native component and installer checks. Wrapper parse/transfer/observation/hash
  refusals pass Windows command doubles without network. Frontend **598 passed**
  and type-check/build passed on the first preparation; exact unchanged frontend
  evidence/output reused for the final source. First cold preparation ~102 s;
  final changed-tool preparation 62.383 s, then identical default Prepare
  **24.265 s**, same kit/release bytes, no test/build execution. These are local
  preparation measurements, not Raspberry install timing. Standard installer and
  host-boundary evidence is reused unchanged; no new ARM/root/systemd-device or
  browser acceptance is claimed.

  Ready `.runtime/deploy/artifacts/f494d43e4e5b13efc439df0ab1b4928dced5a25b78d352c385c3c1d3430ddb4f`,
  release `local-f494d43e4e5b13efc439df0a`, VERSION remains beta.57. Kit 15239547 B,
  SHA256 `d75b0a67e431a310ef5abc129c92faa290e039baef90e7fadbd28ae24ea6bb73`;
  Core SHA256 `da7f905582bbc409c59147b45c45f6a0a8bae1c9bcdceeb12bff71125b48e30b`.
  No agent device read/mutation/browser action, commit, push or version bump.
  Prior `.runtime/cap11-deploy` artifacts remain unchanged. Owner clarification:
  deployment is deferred until after further development; the current request
  was to make deployment easy, not to perform or schedule another rollout now.
  Keep the Download correction local until that later deployment. Await owner
  permission-check results and selection of the next bounded development step.
  Do not reopen accepted AP/setup/menu/Fleet tests.

- **Owner-authorized CAP11 Raspberry rollout, prepared 2026-10-27.** Owner now
  explicitly asks to install the new Core on `rasp-3mm.local`, superseding the
  previous local-only CAP11 scope for this rollout. The known SSH host responds,
  but batch authentication fails (`publickey,password`); no usable device
  credential is recorded. No agent device read/mutation or browser automation
  occurred. Deliver the checked owner-run PowerShell launcher; it prompts locally
  for SSH/sudo and runs a detached systemd job. Do not call the deployment done
  before owner logs/health confirmation. No commit/publication/version bump.

  Immutable local Core release `local-cap11-20261027-arm64-r1`, VERSION remains
  beta.57. Archive `.runtime/cap11-deploy/3mm-local-cap11-20261027-aarch64.tar.gz`,
  **3617836 bytes / 1465 files**, SHA256
  `72e5e1ba729f95101b7bc4a19cf6076dac9417758c8f6b6095839684b0226fbe`.
  Source hashes match the accepted CAP11 baseline except the necessary generic
  default-host publisher and its tests. Reuse prior implementation checks.
  Re-emitted prebuilt frontend/type-check pass after temporary WSL source cleanup;
  new staging uses persistent `/var/tmp`. No independent user code was changed.

  CAP11 requires a new native host for fresh file-profile-v2 applications; merely
  retaining the old default bootstrap would leave new apps on the old worker.
  Added explicit CLI `publish-default` / `recover-default` with the shared release
  lock, existing component journal, native artifact verification and previous
  pointer. Existing instances remain on their own pins and no application is
  started/enabled/granted by default publication. Component suite **20 passed /
  1 explicit isolated-root skip**, including interrupted publication rollback and
  preserved existing bindings. Prior separate-principal host evidence is reused
  for the unchanged stage/process boundary.

  Separate offline native-host builder bundle
  `.runtime/cap11-deploy/3mm-cap11-host-wheels-aarch64-cp313.tar.gz`, **13911320
  bytes / 9 pinned wheels**, SHA256
  `1e779b408be29c065f6da889914bb8559bc6a9093c833ec1b14d1b5070b63e6b`.
  Includes the separately locked Pillow provider; CPython 3.13 ARM64 binaries were
  downloaded and hashed, not executed on this x86_64 machine. The detached device
  job verifies/installs them in a separate builder and builds/tests the native
  image dependency **before changing Core**. It then uses the normal Core
  backup/health/rollback installer, preserves installed frontend URL and networking,
  publishes the verified default for new applications and checks Core readiness.
  Core and existing application host environments are not given Pillow implicitly.

  `.runtime/cap11-deploy/Deploy-Raspberry-Cap11.ps1` checks/uploads Core, host-wheel
  bundle and `Update-Cap11.sh`, then starts the root detached job. Full success is
  the distinct final line **`CAP11 update succeeded`**, after the installer and
  host publication; the installer's earlier success line alone is insufficient.
  Closing SSH/PuTTY only closes the journal viewer. Existing stage/unknown base,
  wrong architecture/Python, corrupt bytes or host build failure refuse rather
  than blindly retry. Stage/journal: `3mm-cap11-20261027-r1`.
  Launcher checks pass using real files/hashes/archive parsing/shell and command
  doubles, including failure-before-Core ordering and no network override.
  PowerShell parse/hash/target/failure checks pass with mocked scp/ssh only.
  Archive byte roundtrip, deployment contract, public ESM closure and no host ELF
  in Core pass. Device installation and the owner's File Probe UI acceptance are
  still pending. Next: owner runs the supplied PowerShell command and reports the
  final job result; do not automatically install File Probe or repeat accepted AP
  tests. The rollout creates no new saved menu items.

- **CAP11 files/media implemented and checked locally, 2026-10-26.** Owner confirms
  Task Probe works, closing its delivered consent correction. Owner authorizes
  CAP11 and then explicitly expands from the initial <=1 MiB private-file path
  to the complete CAP11 result, **without deployment on Raspberry**. Include
  bounded streaming/resumable uploads, checksum/atomic finalize/interrupted-upload
  lifecycle, ownership/quotas/metadata, private/public access, expiring links,
  revoke/uninstall/retained-data semantics and optional media transformation
  worker/provider with traceable originals/derivatives. Keep ordinary Core
  administration independent and use generic contracts, never app-name branches.
  Owner performs browser/device visual checks; no agent UI automation or device
  mutation. No commit, publication, version bump of existing packages or deployment
  is authorized by this scope. New shared file permission/auth changes are in scope.

  Delivered file-contract-v2 on the existing current-grant/file-worker boundary:
  raw 256 KiB chunks, durable offset/resume, full checksum/CAS atomic finalize,
  bounded staging/expiry/cancel/cleanup, metadata/pagination and original/derivative
  quotas. Browser and Python public SDKs use the same generic mechanism. Human
  route/session/build permissions remain separate from read/write/publish/transform
  service scopes. Fresh normal consent leaves publish/transform unchecked. Public
  links pin owner/incarnation/package/grant/file revision, expiry and download
  count; bearer secrets stay in fragments/POST bodies and only hashes are stored.
  Revocation stops later chunks. Missing/unsafe metadata fails closed; no reset.

  Optional Pillow image provider runs outside Core with pixel/byte/CPU/memory/time
  bounds; source/derivative/job provenance is retained. Native application-host
  build can explicitly bundle its separately pinned dependency. Files/media
  participate in normal activation snapshots, SQL recovery/rollback proofs,
  retained-data uninstall and explicit erasure. No Core DB migration was needed.
  [Public contract and limits](APPLICATION_FILES.md).

  Verification uses disposable WSL Linux/Python 3.14.4 sources and native workers,
  not Raspberry. Ignored `.runtime/cap11` keeps source inventories and logs.
  Broad Python gate on its frozen baseline: **6244 passed / 615 explicit profile
  skips**, with two new fixture/test-expectation failures subsequently corrected
  and passed in affected reruns (real kiosk fixture, wrapped filesystem fault).
  Reuse unchanged broad results; do not relabel that initial command all-green.
  Final affected integration **198 passed** and final complete SDK/direct-host/
  native/browser-file integration **356 passed**, including those repaired cases,
  actual >1 MiB streaming, lost ACK/no replay, human/service denial, mid-download
  revoke, CAS/checksum, snapshots and explicit retained-data erasure. These groups
  overlap; their counts are not additive. Later SDK changes are covered by the
  final SDK/direct-consumer group, not the earlier broad run.

  Isolated root SQL preparation/recovery/upgrade/rollback slice: **174 initial
  passes + all 15 exact failures passed after fixing test-source traversal**, plus
  the separate-principal application-host case passed. The failures came from a
  0700 temporary source root preventing the dropped-UID worker importing code;
  changing only that disposable public-code directory to 0755 repaired it. No
  production permission bypass or installed account/service change. Other
  disposable systemd/root profiles remain explicitly unrun, not claimed passes.
  Frontend full **598 passed**, then **103 passed** for the final affected consent,
  file host and route boundary changes; type-check/production build pass. Reuse
  unaffected frontend checks. Actual install-time compiler and public prebuilt
  ESM SSR pass for empty and saved-upload states; this is not visual acceptance.
  A clean native x86_64 application-host artifact with the locked optional Pillow
  dependency passed Core-dependency isolation and actual PNG -> WebP resize.

  Separate local reference `org.3mm.file-probe` 1.0.0, route `/file-probe`, uses
  only public SDKs and adds no saved menu items. ZIP
  `.runtime/cap11/file-probe-1.0.0.zip`, **5612 bytes**, SHA256
  `2d82f10f16548d5d6941b687acb46d3186749a3acc1e81c195bb5e7f31dd27cb`.
  Source is `modules/file-probe`; instructions are in its README. The demo has
  an 8 MiB/file ceiling; streaming was exercised above 1 MiB locally, not at the
  structural 1 GiB ceiling or under Raspberry power-loss/performance conditions.
  Existing published packages/releases are untouched; no new Core deployment
  archive or ARM provider artifact is implied. Finish point: complete local CAP11
  implementation and evidence. Later owner-run phone/Raspberry acceptance requires
  an explicitly updated Core/application host (and optional image-provider host
  artifact). No device deployment or browser automation was performed. Stop here;
  choose the next capability or rollout separately with the owner.

- **First CAP09 UI slice accepted, owner-confirmed 2026-10-26.** Owner reports
  that both named form checks and the other demo checks pass on the Raspberry
  test page. This closes the bounded manual acceptance for the delivered shared
  fields/forms, table/pagination and UI states. It is owner-observed acceptance;
  no agent screenshots, exact viewport dimensions or separate per-theme/keyboard
  matrix were supplied. Do not reopen this accepted slice to repeat the same
  checks. The broader CAP09 catalogue remains separate.

  Owner clarified
  that they want to operate the visual checks themselves. Stop agent browser
  automation; before this correction only app/browser inventory and skill/docs
  reads occurred, without navigation, input, screenshots, upload or device action.
  Prepared a separate UI-only manifest-v2 demo `org.3mm.cap09-ui-check` 1.0.0,
  route `/cap09-ui-check`, in ignored `.runtime/cap09-manual`.
  ZIP `cap09-ui-check-1.0.0.zip`, 4,306 bytes, SHA256
  `7f0a0a65d6389e227c03a0a9dd9e90b5e4bc42099c1cf3516832cff48dc7166f`.
  It imports the delivered public UiField/Form/Table/State/Surface/Button,
  declares no permissions/capabilities/backend service and uses in-memory sample
  data. No automatic menu links or Core changes are needed. Owner-run acceptance
  uses Extensions and `http://rasp-3mm.local:8080/cap09-ui-check` as administrator.

  Native required/email/number controls, readonly/disabled/checkbox/select/date/
  multiline fields, explicit busy release, local preview, two table pages, empty
  table and loading/error/empty examples are available in BG/EN. Core's own theme
  switch supplies appearance; the demo does not emulate it with hardcoded colors.
  Automated demo checks **2 passed** (validation/local draft/language/pagination/
  state/busy/escaping), manifest-v2 validation and actual install-time compilation
  passed; source hashes and build metadata are in ignored `package.json`.
  The first local build correctly refused unprotected Windows-mounted output;
  recompiling to a real Linux-owned temporary artifact passed without weakening
  provenance checks. Prior Core checks are reused for unchanged code; no Core
  frontend rebuild, publication, version bump of an existing package or agent
  deployment occurred. The later owner confirmation above supplies the previously
  pending manual visual acceptance. This closure changes documentation only;
  diff/whitespace checked, prior successful checks reused unchanged. Fleet,
  Digital Output and AP/setup acceptance stay closed. Uploads/file picker, task
  progress, filters and editors remain future scoped results; no new work or demo
  removal is started by this acceptance message.

- **Raspberry Fleet version-update acceptance complete, owner-confirmed
  2026-10-26.** After the combined Core deployment instructions, the owner reports
  completion on `rasp-3mm.local`: removed Fleet 0.1.12 to establish the starting
  state, installed 0.1.11, then successfully updated that installation to 0.1.12.
  Subsequent repeated tests for `org.3mm.digital-output` also succeeded. The
  0.1.11 -> 0.1.12 transition is now real-device owner acceptance of the normal
  version-update path, extending the earlier fresh-install-only acceptance.
  The selected Fleet update / Digital Output scenario has no remaining reported
  blocker; do not repeat it solely to close the same issue.

  This closes the owner-run rollout/update acceptance pending below for the
  delivered `local-cap03-cap09-20261026-arm64-r1` candidate. The agent has not
  authenticated to the device or independently read its installed release/logs.
  No additional measured data-preservation, failure/rollback, Task Probe consent
  or CAP09 visual scenario was reported; their previous evidence/limits remain.
  CAP09's first UI slice is delivered with this candidate, without acceptance of
  the entire CAP09 catalogue. Existing AP/setup acceptance stays closed.

  Documentation-only closure: update this state and the CAP03 plan status,
  inspect diff/whitespace and reuse unchanged implementation/package/launcher
  checks. No runtime test/build, device action, package replacement, commit,
  publication or version bump is needed for recording the owner's result.

- **Owner-authorized Raspberry rollout preparation, 2026-10-26.** Owner now asks
  to deploy the combined result and explicitly selects CAP09 forms/tables/UI
  states. Prepare one immutable ARM64 Core candidate from the checked source and
  prebuilt frontend, including the earlier Task Probe consent UI correction.
  Reuse the recorded implementation checks for unchanged inputs; verify the
  delivered bytes, deployment contract and detached upgrade launcher separately.
  Existing AP/menu or Task-access local installations are the two known bases;
  preserve the installed frontend URL, networking backend, data and native pins
  through normal installer backup/health/rollback. Batch SSH authentication to
  `raspberry@rasp-3mm.local` failed; no device state was read or changed. Owner-run
  PowerShell/PuTTY deployment is the available path unless access changes.

  Prepared immutable release `local-cap03-cap09-20261026-arm64-r1`, archive
  `.runtime/package-staging/3mm-local-cap03-cap09-20261026-aarch64.tar.gz`, SHA256
  `293664bed2fc733ab995c04fd463c1844b4b14f3f58a3209478d93398af2d757`,
  3,572,167 bytes / 1,447 delivered files. VERSION remains beta.57; metadata
  identifies the local working tree, ARM64/Python 3.13 profile and two accepted
  bases. Existing archives stay immutable. Source hashes, deployment contract,
  every delivered byte/metadata roundtrip, absence of host ELF, generic staging
  path replacement and prebuilt public UI CSS links pass. No runtime code changed
  during packaging; reuse the 237/584/8, type/build and actual API/compiler evidence.

  Companion `Update-Cap03-Cap09.sh` verifies checksum/architecture/base, copies
  root-owned staging inputs, then launches an independent systemd job. The
  standard installer handles backup, current-release switch, health and rollback;
  stored frontend origin/network backend are preserved. Launcher verification
  accepts both known full bases, refuses unrelated/node/already-target bases,
  missing URL/wrong architecture/corruption/existing stage, and checks detached
  normal-installer delegation with command doubles. No live services were used.
  `Deploy-Raspberry-Cap03-Cap09.ps1` verifies both local file hashes, copies them
  using owner SSH authentication, then invokes the launcher with sudo. PowerShell
  parsing, exact arguments and refusal after failed copy pass with command doubles.
  At preparation handoff SSH authentication was unavailable to the agent and no
  agent transfer/deployment occurred. The later owner confirmation above closes
  the previously pending owner-run rollout and normal version-update acceptance.

- **Combined local CAP03 update path + first CAP09 UI slice, 2026-10-26.**
  Owner confirms Fleet 0.1.12 and the following probes succeeded after completely
  uninstalling 0.1.11. This closes the HTTP LAN button correction/device trial;
  it does not accept an in-place version update. Owner reports the same activation
  refusal on VM 0.1.10 -> 0.1.11; the previous manual VM intervention is not proof
  of the normal update flow. Owner wants further original-plan progress before
  another Core rollout. That hold is superseded by the owner's rollout request
  above. CAP09 was initially the announced default recommendation; the owner has
  now explicitly selected that scope.

  CAP03: ordinary stopped native applications now share the sealed inert package
  preparation previously limited to tasks. Extensions shows stop -> prepare ->
  review exact new access -> activate; it does not auto-start or inherit previous
  artifact consent. Preparation rechecks live administrator, old package/grant,
  configuration/epoch/identity and unresolved execution, fences old command rights
  and registers the exact candidate without helper/wheel/migration execution.
  Missing grants allow preparation only, never code approval; corrupt grants or
  provenance fail closed. Inert activation additionally requires the current
  effective-for-this-stopped-instance grant. Two reproduced regressions (abandon
  an update and return to old bytes; revoke approval before startup) initially
  reached the helper through old native trust. Both now refuse helper execution
  until fresh consent. Same-artifact non-inert lifecycle rules remain unchanged.
  Instance/incarnation, data and historical results stay
  owned by the same installation. The exact public package SHA is exposed so a
  stopped candidate is not confused with a newer upload; activation preserves the
  previous package pin. Returning to a prior package also needs fresh consent.
  Relational migrations/session providers retain their dedicated prepared paths.
  One shared service replaces the task-only service; existing opaque v1 sealing
  tags remain the persisted provenance format, without a second adapter.

  CAP09: public `@3mm/ui/v1` now additionally exports UiField/UiForm/UiTable/UiState.
  They supply labelled native controls, local drafts/validation, controlled table
  pagination, busy/error/empty semantics and public theme tokens. They expose no
  Core stores, credentials, private clients or automatic fetch/mutation/retry.
  Current optional CRUD renderer consumes these primitives while preserving its
  SDK permission/outcome/pending-ID rules. Its same HTTP LAN randomUUID defect
  was a demonstrated consumer blocker; secure byte IDs now fail visibly before
  dispatch if generation/persistence fails. No Contacts/application version or
  immutable ZIP was changed. Fresh renderer builds require the new UI exports.

  Real production bundling exposed a necessary delivery dependency: import-map
  ESM does not invoke Vite's dynamic-import stylesheet loader. The existing public
  entry plugin now includes each exposed entry's CSS closure in prebuilt HTML.
  A neutral disposable v2 package goes through the actual compiler and links the
  actual prebuilt public ESM, verifying the eight exports, loaded hashed CSS and
  four EN/BG/card-variant server renderings. This is presentation structure, not
  browser layout/theme-color/mobile or Raspberry visual acceptance. Existing
  declined preview permission was respected; no alternate browser was used.

  New evidence: **4049 unique backend cases passed, 608 explicit profile/root
  skips**, combining 4028 initial passes with 21 repaired environment cases.
  The initial broad run's 21 failures were all AF_UNIX path-length errors from
  the helper's overlong TMPDIR. All exact 21 passed with a short owned basetemp;
  no runtime production repair or suppressed case was needed. Preserve both raw
  logs; this is combined coverage, not one uninterrupted clean run. The 14 new
  staging/security cases and earlier 163 direct-consumer passes overlap this
  total. Later amendments expose the selected public package SHA through one
  outer join rather than exposing internal package IDs, and require a current
  grant on the inert-only activation branch. Final direct-consumer gate **237
  passed**, including all 16 staging cases, old/native/relational denial, tasks,
  command rebinding, lifecycle and consent. Its two additional regressions bring
  combined unique backend coverage to **4051 passes / 608 skips**. The earlier
  full run is reused for unchanged consumers, not relabelled as testing these
  later amendments. Frontend amendments have separate final checks.

  Final Core frontend **584 passed**, type-check/production build passed; optional
  CRUD **8 passed** and its separate public-import TypeScript check passed.
  Exact immutable Fleet 0.1.11 -> 0.1.12 -> 0.1.11 API/consent/lifecycle cycle
  passed locally, with real keys/logins/SQLite/package bytes and actual UI
  compilation. Runtime helper I/O is a double, not a live VM/Pi process trial;
  no manual grant/database workaround is used between lifecycle requests.
  Neutral prebuilt ESM/compiler checks pass. Logs, helper sources and exact
  frozen inputs are in ignored `.runtime/package-staging`; source snapshot is
  `/tmp/3mm-package-staging-0jz2y7hw`. Prior unrelated Runtime/SDK/Agent evidence
  remains prior evidence for unchanged inputs, not new suite passes.

  No schema/reset, owner-device access, Core archive replacement, version bump,
  commit or publication. Accepted AP/setup/navigation work stays closed. This
  supersedes the pending Fleet/GPIO acceptance statements below; the separate
  Task Probe consent correction is included in the delivered Core candidate.
  The later package preparation and owner-run acceptance above close the selected
  rollout/version-update result. CAP09 uploads,
  task monitor, filters/editors and the broader CAP catalogue remain separate.

- **Fleet HTTP LAN button failure fixed; local 0.1.12 ZIP ready, 2026-10-26.**
  Owner clarified that `Install selected module` does nothing. The shared Fleet
  mutation handler called secure-context-only `crypto.randomUUID()` before its
  error handling/persistence. On HTTP LAN browsers the call fails before any host
  request. Three regression cases without `randomUUID` reproduce this for
  install/disable/output actions. Fleet now derives the existing 32-hex request ID
  from 16 bytes of `crypto.getRandomValues`; IDs are still saved before one
  dispatch, with lookup-only recovery of pending requests. Failure to obtain
  secure randomness displays a localized local error and sends nothing.

  Owner explicitly approved local Fleet **0.1.12** without publication. Source
  VERSION/README updated in sibling `3mm-fleet`; schema/SDK versions, Core,
  Digital GPIO package, permissions and pending-request storage keys are
  unchanged. Old immutable 0.1.11 ZIP retains SHA256 `a33d5c0129d7cb79d625f5ffff78b5c0b2a85f9709e638799a6cc6abf8faf6da`.
  New ZIP `C:/Users/SIMPLEX-3260/Desktop/3mm-fleet/dist/3mm-fleet-0.1.12.zip`,
  SHA256 `f2927292be602e67754382406beeb497d13ccbe2101906e075a41e610ef7733a`,
  compiled UI SHA256 `5b87b4d7d254e54a103ee77b9efefd293c1829d1abc940420fa7ee732b075f6e`.
  An identical copy and evidence are in ignored `.runtime/fleet-http`.

  New checks: Fleet **22 UI cases passed**, including HTTP LAN and failed-RNG
  refusal; **3 package build cases passed** at approved 0.1.12. Type-check passed
  before the VERSION/docs-only update and is reused for identical TS/Vue/import
  inputs. Final actual 0.1.12 ZIP builds deterministically, validates and compiles
  through the current Core pipeline. Both repositories' whitespace checks pass.
  No Core change or full Core build was needed for this Fleet correction. No
  real-device mutation, module retry, GPIO command, commit or publication occurred.
  Next: owner uploads/selects 0.1.12 and confirms the install request now appears
  and reaches a device result. Physical-device acceptance remains owner-run;
  Task Probe's separate Core consent correction below is prepared, not deployed.

- **Task consent UI failure reproduced and fixed locally, 2026-10-26; rollout
  pending.** In response to the GPIO diagnostic question the owner supplied
  `Result task probe` / `Application access could not be loaded`. Actual Core
  consent responses were exported from real disposable authority/key/SQLite
  fixtures and the exact Task Probe 0.2.0 ZIP. The unchanged non-task response
  passes the frontend; task response fails with `Unsupported authority status`.
  The initial hypothesis that every non-task response includes empty tasks was
  disproved: `_resources` includes only subject fields. This confirmed defect is
  specifically the missing frontend task scope/resource contract, not proof of
  the separate reported Digital GPIO failure.

  The shared frontend DTO validator now supports bounded task rights, exact owned
  package/handler bindings and matching scalar schemas/limits. Task profiles
  continue to reject other resource families; malformed, foreign, duplicate and
  mismatched resources fail closed. The consent dialog displays the task details
  and sends only the reviewed selection. No server auth/admission, grants,
  schedules, worker enablement, application ZIP or manifest version changed.

  New evidence: real backend consent export 1 passed; initial frontend regression
  failed only for Task Probe and passed for non-task; repaired targeted 84 passed,
  final full frontend **570 passed**, TypeScript/production build and whitespace
  passed. Initial type-check issues in a test fixture type and ES target helper
  were repaired; final build replaces that failed build. Backend/runtime/Agent
  Python bytes match the accepted AP/menu snapshot, so their existing evidence
  is reused, not rerun/relabelled. Component test loads the real response and
  checks exact permission submission; no new browser/device acceptance is claimed.

  Prepared immutable local ARM64 Core update, release
  `local-task-access-20261026-arm64-r1`, archive
  `.runtime/consent-ui/3mm-local-task-access-20261026-aarch64.tar.gz`, SHA256
  `503be2470f524fef659045f97f7fbfcd9f957427c8fa60b554115b885144eec5`.
  Companion `Update-Raspberry.sh` accepts only the AP/menu base, detaches its job,
  preserves the stored frontend URL/backend, and delegates to normal immutable
  installation/backup/rollback. Archive contract/byte roundtrip, unchanged-Python
  audit, shell syntax and isolated launcher command doubles passed. Logs/input
  hashes/package metadata are in ignored `.runtime/consent-ui`; new DTO fixtures
  are disposable Core responses with no user credentials. Existing artifacts
  remain immutable. Nothing deployed, no SSH credentials available, no commit,
  publication/version bump/delegation. AP/setup remains accepted. Next: owner-run
  Core update and permission-dialog confirmation. The separately clarified Fleet
  no-op button now has a local 0.1.12 correction, recorded above.

- **Active: Digital GPIO installation failure through Fleet on fresh Raspberry,
  2026-10-26.** Owner reports failure after receiving Fleet 0.1.11 and Digital GPIO
  Output 1.1.0. The reply instead shows Task Probe's consent loading failure; its
  fix is recorded above. Owner subsequently clarified the Fleet button no-op;
  its HTTP request-ID failure and local correction are recorded above.
  The exact supplied GPIO ZIP (`e7ab19b266db360fc76b87204080c3ac863d13ad8c2a8c3657525e697da6991a`)
  passes current frozen Core validation for aarch64/protocol 1.0 and installs to
  active in a disposable local AgentModuleRuntime with MockDigitalGpioDriver.
  This excludes a general ZIP/declared-ARM-architecture failure in that local
  profile; it is not evidence of successful installation on the device. Helper:
  ignored `.runtime/ap-menu/inspect_gpio_package.py`. Batch-mode read-only SSH
  could not authenticate, so no device log/state was obtained and no remote
  installation, retry, GPIO command or configuration change occurred. The failed
  stage is now reproduced in Fleet before dispatch; next is owner acceptance of
  the 0.1.12 package. AP/setup acceptance below stays closed.

- **Fresh Raspberry AP/setup acceptance complete, owner-confirmed 2026-10-26.**
  After the clean Linux installation and owner-run installation trial, the owner
  reports that everything works as intended and explicitly closes the initial AP
  and automatic setup-opening tests. These two scenarios are accepted on the real
  Raspberry Pi 3B+; no additional AP/captive-portal test remains required for this
  correction. This is owner-observed hardware acceptance, not an agent-run probe
  or an extension of the historical C5 matrix to other hardware scenarios.

  Owner requested direct installation commands with owner execution. Prepared
  ignored `.runtime/ap-menu/3mm-local-ap-menu-20261026-aarch64.tar.gz`, release
  `local-ap-menu-20261026-arm64-r1`, SHA256
  `5b30b518f6ea2437d5f1694f7d90e503a89d00c9414196f259e000298a2cb77a`.
  It contains the checked frozen AP/menu correction and prebuilt frontend, 1438
  delivered files/3543884 bytes; source VERSION beta.57 is unchanged and metadata
  truthfully records local working-tree source and ARM64/Python 3.13 trial scope.
  No host ELF binaries are delivered: independent native components bootstrap
  from their source on the Raspberry through the existing immutable installer.

  Companion `Install-Raspberry.sh` verifies the archive and clean-install scope,
  stages root-owned inputs and detaches the job **before** APT/NetworkManager
  changes. It installs the same bootstrap dependencies with NetworkManager/
  dnsmasq, runs host preflight and delegates to shipped `install-systemd.sh` with
  explicit managed backend. One SCP command copies both files; owner then runs
  `sudo bash ~/Install-Raspberry.sh`. The SSH connection may close when initial
  AP starts; installation/logging remain independent of PuTTY.

  New checks: archive/source manifest hashes, deployment contract, every delivered
  file byte and metadata roundtrip, no host ELF, shell syntax and launcher command
  doubles (detachment before packages/network, backend/installer argument flow,
  corruption refusal) passed. These doubles do not exercise root services or real
  ARM/AP. Reuse the correction's 496 Python/547 frontend/type-check/build evidence
  for unchanged source/dependencies; no additional runtime-suite claim. Details in
  ignored `.runtime/ap-menu/package-arm64.json` and helper sources. The owner's
  real-device confirmation above closes the previously pending AP/setup trial;
  Raspberry has not been accessed by the agent. This acceptance update changes
  documentation only; diff/whitespace checked, no runtime rerun needed. Existing
  automated evidence is reused unchanged. No new device action, publication,
  commit, version bump, reset or delegation occurred during closure.

- **Installer/AP and empty navigation correction complete locally, 2026-10-26.**
  Owner rejected the host-only Raspberry installation instructions and compulsory
  header links. The public one-command bootstrap was still present; the supplied
  `THREE_MM_NETWORK_BACKEND=host` disabled managed Wi-Fi/AP. Standard fresh
  bootstrap and immutable installation now default to `network-manager`; explicit
  `host`, stored choices and older installations without a backend remain
  preserved. First-setup AP selection accepts the connected Wi-Fi adapter carrying
  SSH after the job is detached. Provisioned roles/recovery do not enter this AP
  path; no reset or role inference was added.

  Header/sidebar/mobile navigation now renders only the active saved menu, with
  no automatic Core/module/app append, inactive-menu fallback or generated error
  fallback. Removing every item, deleting the active/last menu and leaving no
  active menu are supported. Removed compulsory appearance-recovery links from
  both shells; Settings, route registry, editor choices, auth/audience filtering,
  themes and Command Palette remain available. `/settings` and Ctrl+K provide
  administration with an empty menu. The previous C5 conclusion that fresh header
  links should be compulsory is explicitly superseded by the owner's preference.

  New evidence from frozen current inputs in `/tmp/3mm-ap-menu-3j621xe_`, existing
  local Linux/Python 3.14 and npm environments: **496 Python passed, four explicit
  root/systemd acceptance skips; 547 frontend passed; TypeScript/production build
  passed; diff/whitespace passed.** Python scope includes all deployment,
  provisioning and setup-service tests, direct runtime activation/services/
  bootstrap/unit consumers, menu routes/items, first-boot preflight and network
  recovery routes. Consumer audit: `setup_interface` is used only by initial AP
  start and runtime activation/health; menu deletion retains its existing admin
  dependency. These are bounded regressions, not a rerun of all historical Core
  suites. A strengthened connected-Wi-Fi AP test reran successfully (three cases,
  replacing its earlier evidence); no production Python changed after the 496
  gate. Final frontend run replaces an intermediate failure from two old shell
  expectations of automatic module navigation. Logs/XML and input hashes are in
  ignored `.runtime/ap-menu`; previous C5 archives remain immutable.

  At this local-code handoff browser permission for the localhost preview was
  declined; no agent visual inspection is claimed and the owned preview was
  stopped. Physical ARM Wi-Fi/AP was then pending; the later clean-install trial
  and explicit owner acceptance above now close initial AP/automatic setup
  opening. The agent did not access or change Raspberry. No distributable,
  commit, version bump, publication or delegation occurred at that earlier handoff.

- **C5 local acceptance complete for the selected bounded Linux x86_64 profile,
  2026-10-26.** Owner requested C5 after the four bounded C3 extractions. Actual
  filtered candidate boots under systemd in an owned nspawn machine with private
  networking, no owner-state mounts and the same checked dependency environment.
  Administration/login/admin denial remains available without optional Runtime or
  applications; essential DB failure is visible and recovers after access returns.
  The actual r2 browser confirms EN/BG, light/dark, 390x844 mobile navigation without
  horizontal overflow, viewer filtering and Settings route denial.

  Historical C5 r2 navigation added Settings/Extensions labels to the common route
  registry and exposed them automatically alongside Devices. Its 541 frontend
  cases/type-check/build passed at that time. The owner subsequently rejected
  compulsory navigation; the correction above removes automatic header links
  while retaining route metadata for Settings/Command Palette discovery. C5 r2's
  archived checks do not validate the later correction.

  New delivered-payload evidence: 64 unique named outer Python cases passed,
  combining initial/repaired runs; the Terminal harness additionally proves two
  real M20 browser-to-sandbox human/service revoke cases. Terminal provider source
  is pinned to public commit `715c3fb9e5eab3408e89c02939ab16b546509cea`. Real PTY
  prompt/resize/asynchronous output/EOF/close, dynamic identity, private-path/network
  denial and cgroup cleanup/link-loss pass. Two v2 reference packages run actual
  hosts through install/update/rollback and explicit executor stop/restart while
  Core/Runtime/peer PIDs and own data survive. That package fixture uses the
  existing compatibility review profile; scoped command/task/data admission and
  cross-principal denial are separately exercised. One helper namespace failure
  was a missing installer-created directory in the manual lab; corrected there,
  the exact failing case passed without changing production hardening.

  Real stopped symlink cutover from CAP08 r2/schema5a to candidate/schema9e passed
  with every value from 82 predecessor tables preserved under explicit mapping.
  Populated downgrade refused unchanged; exact snapshot restore plus the production
  authority fence restarted the old release successfully. A second upgrade, current
  admin/user denial, blocked/revoked sessions and required-DB failure/recovery pass.
  Same-lab three-start medians: readiness 1.954 -> 1.740 s, idle RSS 178740 ->
  164060 KiB. Separate import-only file-module closure is 1158 -> 1006 (backend
  177 -> 149); delivered frontend 44/1408221 -> 30/1138188 files/bytes. These are
  isolated idle/import observations, not capacity, hardware or credit estimates.

  Reuse the previous 6131 Python passes, tooling 32 and shared CRUD UI 5 for
  unchanged inputs; counts overlap the newly executed cases and are not added.
  Python source/dependencies match the full C3 gate, including its documented
  whitespace-only Menu amendment; no later Python fix invalidates that evidence.
  New frontend evidence replaces its previous 535 cases/build. Source audit keeps
  all 78 moved originals and finds no additional pre-C3 runtime deltas against
  the installed CAP08 baseline. Native x86_64 Runtime/host/Agent/session/public-web
  candidates build and deployment-contract/pip checks pass. Platform Runtime build
  remains `82cd97b95ff353f7e625f7bbce7bb62d81f51f574e8ee52d8fa23ad2505ed245`.

  Immutable local package `core-c5-local-20261026-r2.tar.gz`, SHA256
  `9805a5562ae55b29de0136fe77fac4d46d4ac75ea2d571ecb0f9e00bded74b00`, is in
  ignored `.runtime/c5` with checksum, XML/logs, screenshots and final evidence.
  It has 1425 delivered files from 1536 frozen source inputs; truthful working-tree
  metadata and source VERSION beta.57 are retained. R1 is preserved. The owned lab
  and preview are stopped; private recovery evidence remains in
  `/var/tmp/3mm-c5-20261026`. Diff/whitespace checks pass.

  Limits: C5 did not execute/deploy ARM/ARMv6, physical GPIO, remote Terminal or
  additional capability profiles; it reused the checked dependency venv rather
  than rerunning a fresh full installer. These are not new passes for historical
  P6 devices. Next explicit result is owner-VM rollout with fresh task/quiescence
  preflight and the immutable installer's backup/rollback coordination. Owner VM
  remains CAP08 r2/schema5a (zero unresolved task runs at read-only final inventory).
  No owner deployment/reset, commit, branch, version bump, tag, publication,
  delegation or A1 product SDK port occurred.

- **C3 Page/Extension/universal-translation extraction complete locally,
  2026-10-26.** Owner approved this next bounded stage. Fourteen original sources
  and ten mixed reference files are preserved in source-only
  `modules/legacy-content`; all 78 moved originals across C3 pass the source audit.
  Core no longer imports the old models, Page/translation APIs, arbitrary table
  engine or obsolete database scripts. Menu has its own Core model with unchanged
  table/API/localized items/audience. Language state now contains only code,
  selected immutable package and enabled flag; validated v2 packages still supply
  translations, with current lifecycle/denial and English recovery fallback.
  Common roles, settings, application authority and UI contracts remain.

  Migration `9e74f5c60d64` archives eight old tables and page/extension subsets of
  direct/role/group permissions without live principal FKs; an optional historical
  multilingual table is preserved when present. Archive values survive deletion
  of current principals. Unknown actual registered custom tables/incoming FKs
  refuse preflight before schema changes, preserving independent data. No old
  grants or executable extensions are restored. Empty rollback preserves all
  predecessor column/type/default/nullability/key/index semantics and supports
  full downgrade; populated history or optional prototype schema requires a
  verified prior backup with matching release/package files.

  Twelve-suite Linux nonroot gate: 6123 passed, 615 explicit profile/environment
  skips. All four worker cases passed across three runs: the grouped run stalled
  on the known streaming-test race after two passes; the remaining cases passed
  separately. Four isolated real root-helper/nonroot-host relational cases passed
  (SQL/receipt, revoke, restart, lost completion), replacing four profile skips.
  Combined unique Python evidence: 6131 passed, 611 remaining skips; tooling 32
  passed. Populated retirement, preflight refusal and current language/menu API
  checks pass. Clean upgrade/check/downgrade and a second empty schema roundtrip
  pass. Raw logs/XML and exact 1535 frozen inputs are in ignored
  `.runtime/c3-content` and `/var/tmp/3mm-c3-content-20261026/source`.

  A protected owner DB copy passed upgrade/check with all values from 82 source
  tables preserved under explicit mapping, including one language selection and
  11 task rows. Populated downgrade refused without changing that copy; another
  disposable copy restored every original row/schema version from the verified
  backup. Owner data has no registered custom table rows. Actual filtered Core
  payload (1393 source/30 frontend files) excludes products/optional libraries/
  legacy sources and passes boot/readiness/admin access/nonadmin denial. Reused
  frontend 535 cases, shared CRUD UI 5 cases and production type-check/build:
  all 189 relevant source/test/dependency inputs and delivered frontend files are
  unchanged. Only docs and one verified whitespace-only Menu cleanup followed
  the gate; its AST is unchanged. Diff/whitespace checks pass.

  Next separate result: C5 integration/release acceptance and an explicitly scoped
  VM deployment; product SDK ports remain separate. Unrelated unreferenced
  `backend/utils/extension_relationships.py` is recorded for a later review, not
  reopened here. Owner VM remains CAP08 r2/schema5a. No deployment, owner reset,
  automatic import, commit, branch or delegation occurred.

- **C3 declarative CRUD extraction complete locally, 2026-10-26.** Owner
  approved the next bounded stage. Preserved 12 original sources (Core models/
  routes/service/tests, protocol/renderer and old Contacts declarations) with
  hashes, plus six mixed references. The optional `libraries/three_mm_crud` owns
  typed validation, per-entity declarations, scoped own-data engine/migration and
  Vue renderer. Contacts builds as an ordinary application/compiled UI candidate
  at its unchanged, unpublished source version; no catalog artifact is replaced.
  Generic localized UI metadata moved to `three_mm_protocol/ui_metadata.py` for
  current application, compiled UI, theme, event and session consumers. Core no
  longer registers the old CRUD API/ORM/frontend/catalog/schema-export paths.
  Unknown UI entrypoints fail closed. Page/Extension/universal-translation legacy
  paths are separate consumers and remain outside this bounded removal.

  New migration `8d63e4b5fc53` preserves definitions/records in two FK-free
  `retired_` archives; exact historical package dependencies use existing generic
  pins. Populated retirement refuses automatic downgrade/import/grant conversion;
  empty rollback restores the complete historical schema/indexes. Existing Core
  admission and scoped relational authority remain unchanged. Personal-data
  descriptors can explicitly choose inert `retention_policy:
  until_explicit_erasure` alongside required administrator export/erasure; this
  does not add task+SQLite support or change CAP08 execution limits.

  CRUD commands use exact actor/payload identity, optimistic revisions, bounded
  journals and read-only outcome lookup. Erasure removes payload/provenance while
  retaining random request tombstones against delayed replay. UI persists only
  pending IDs, requires outcome review and clears records on fresh access failure.
  Import preserves original IDs/data/timestamps/provenance, validates current
  limits and refuses collisions; no owner data or old authority is imported.

  Combined current Python evidence: 6123 unique passes and 611 explicit remaining
  environment/profile skips. The twelve-suite nonroot gate passed 6114/615 skips;
  the previously stalled worker module ran separately (4 passed). Later optional
  library refinements confirm routine refusals without ambiguous transactions,
  localize outcomes and keep administrator erasure available at the normal command
  journal limit. All three affected library/package consumer modules were rerun
  from current sources (34 passed, including one added case), replacing their
  earlier results. Four isolated real root-helper/nonroot-host relational tests
  passed (normal SQL/receipt, revoke, restart, lost completion), replacing four
  profile skips. Core/SDK/public-contract inputs remained unchanged after the broad
  gate started; only five optional consumer/test files and docs changed later.
  Raw XML/logs and initial/amended hashes are in ignored `.runtime/c3-crud`;
  `/var/tmp/3mm-c3-crud-20261026/source` retains all 1518 frozen input hashes.

  Frontend 535 cases, current shared CRUD UI 5 cases and production type-check/
  build pass; unchanged clean npm dependency closure is reused. Tooling 32 cases
  plus complete clean migration upgrade/check/downgrade pass (33 cases together).
  Actual compiled Contacts table/form, Bulgarian labels/outcome and light/dark
  themes passed browser inspection with a fixture-local host and no owner API
  writes. Verified ZIP `contacts-c3-local-verified.zip` has SHA256
  `b557e7bf25a79f643bce0ae50a48bfded35df8fe4af5f7853d6cadd0af718cc0`;
  its UI compiles through the existing pipeline and own-data import runs from the
  delivered wheel with private Core/Agent/Runtime imports forbidden. This is a
  local, unpublished 1.0.0 candidate, not replacement of an immutable old version
  or a claim of Contacts-specific owner-VM activation/hardware/systemd acceptance.

  A protected owner DB copy passed upgrade/check/full downgrade, preserving all
  82 original tables and 11 task rows under explicit mapping. Owner has no old
  CRUD rows; populated fixtures cover preservation, FK isolation, package pins,
  guarded recovery and explicit own-data import. Actual filtered Core payload
  excludes products/optional CRUD (114 files) and passes boot/readiness/admin
  access/nonadmin denial. Source audit verifies all 64 moved originals and six
  current mixed references, unchanged runtime dependencies and no old CRUD API
  in compiled Core UI. Whitespace checks pass. Next separate C3 candidate:
  Page/Extension/universal-translation ownership and its real consumers. Other
  product SDK ports and overall C5 remain separate. Owner VM remains CAP08
  r2/schema5a; no deployment, release, commit, branch, delegation, reset or automatic
  owner data migration.

- **C3 Dashboards extraction complete locally, 2026-10-26.** Owner
  approved the next proposed bounded C3 result. Moved 19 product route/model/
  schema/frontend/store/test sources into `modules/dashboards/source/legacy`,
  preserving original hashes in `modules/product-source-map.json`; 11 mixed
  access/security/palette originals are retained as reference sources. Removed
  live Dashboard routes/ORM registration, owner cleanup, dedicated role grants,
  security selectors and rendering/editor imports. Common application roles/
  grants, compiled UI packages/contracts, themes/i18n and current declarative CRUD
  remain. Declarative data/contacts are a separate later ownership extraction;
  their old product route reservations are removed and current Core administration
  paths remain protected. The Command Palette now reads current routes/audiences
  and localized metadata on open, retaining common keyboard/theme behavior.

  New migration `7c52d3a4eb42` preserves three product tables and dashboard/widget
  subsets of direct/role/group permissions as six `retired_` archives without
  cascading FKs into live Core principals. Empty retirement can downgrade;
  populated evidence refuses automatic authority restoration and requires verified
  backup recovery. Matching compiled-widget dependencies become inert generic
  `module_package_retained_references`; package retirement refuses pinned resources
  even for damaged packages. Admin-only bounded reference inspection is available;
  no unreviewed pin-release API or application authority is created. Historical
  baseline DDL is frozen explicitly so clean migration does not import product
  models. Original uploads/build artifacts and owner data are preserved.

  Targeted existing schema/access/retirement/history checks 36 passed; four new
  populated-retirement cases passed after fixture corrections. Runtime/retirement
  consumer gate 39 passed. A protected copy of the owner DB passed upgrade/check/
  downgrade with all 82 original tables/11 task rows preserved under explicit
  mapping. Owner has no dashboards/widgets; populated fixture acceptance covers
  layout/config/grants, exact package pins, no principal-delete cascade and
  populated-downgrade refusal. A filtered Core payload physically excludes all
  three product directories and AI library (78 files), then passes boot/readiness,
  real admin access and nonadmin denial with optional services unavailable.

  Linux frozen source `/var/tmp/3mm-c3-dashboards-20261026/source`; input hashes
  and raw logs/XML in ignored `.runtime/c3-dashboards`. Clean npm lock install
  excludes gridstack; production type-check/build and all 538 frontend cases pass.
  Actual Users/Security/Command Palette components passed isolated browser review
  in light/dark themes; fixture-local changes used no owner APIs/credentials.
  The eleven-suite Python gate covers 6131 unique passes and 615 explicit
  environment/profile skips. Its first run was interrupted at a stalled existing
  worker-disconnect case after 2545 passes/597 skips; all four worker cases passed
  independently. The remaining run passed 3586 cases/18 skips, excluding exactly
  3142 completed cases from the first XML. Both raw results remain intact; this
  is combined coverage, not a claim of one uninterrupted clean run. Tooling inputs remain
  unchanged; reuse the previous 32 successful tooling cases. Source audit verifies
  all 52 moved sources and 11 original reference copies; only gridstack was removed
  from the frontend dependency closure. All 1491 frozen input hashes remain intact.
  Later Python changes trim two trailing blank lines only, with equal ASTs; docs
  and source-map scope metadata also changed. Whitespace checks pass. The next
  separate C3 candidate is declarative CRUD ownership/current consumers; SDK/data
  ports into runnable products and overall C5 acceptance remain separate work.
  Owner VM remains CAP08 r2/schema5a; this is local work,
  without deployment, commit, branch, publication, delegation or reset.

- **C3 first extraction complete locally, 2026-10-26.** Owner
  approved the proposed next bounded result: Builder and Automations, including
  their shared AI clients; Dashboards follow separately. Removed their Core
  router/ORM registration and frontend routes/provider controls. Preserved 33
  moved source/test files with original SHA256 mapping in
  `modules/product-source-map.json`; product sources are in
  `modules/{builder,automations}/source/legacy`. Shared clients have a single
  optional owner, `libraries/three_mm_ai`, with independent tests and no Core
  dependency. These preserved product sources still require a public-SDK/data
  port before becoming runnable application packages. Source-only markers keep
  all three directories out of Core release payloads; normal compiled UI/package
  validation remains common Core behavior.

  Additive retirement migration `6b41c293da31` renames nine product tables to
  `retired_` recovery evidence and moves the three provider settings/associated
  translations out of live settings, preserving their values. Live Core metadata
  does not register them; Alembic excludes reserved retired tables from destructive
  autogenerate proposals. Guarded downgrade refuses current setting/ID collisions.
  Existing `AI_SETTINGS_MASTER_KEY` provisioning/recovery remains unchanged:
  it also protects Core identity/application secrets. Generic HTTP/crypto
  dependencies used by Core, Agent and coordinated bootstrap are retained.

  Targeted migration/registry/command/public-widget/release gate 115 passed;
  optional AI library 9 passed; tooling 32 passed. A private copy of the real owner
  DB passed upgrade/check/downgrade, preserving all 82 tables and 11 task rows.
  Actual filtered Core payload excludes 45 product/library files; boot/readiness,
  real admin login/access and nonadmin denial pass with those sources physically
  absent and optional services unavailable. Type-check/production frontend build
  passed. Browser inspection of actual Settings/Extensions components in isolated
  fixtures passed in light/dark themes; no live owner credentials or API writes.
  Frontend gate had 558 passes and one old AI-control expectation; repaired
  Settings suite 7 passed, giving 559 unique successful frontend cases. Broad
  eleven-suite Python gate produced 6119 passes, 615 explicit environment/profile
  skips and five test-expectation failures: four historical authority snapshots
  needed the explicit retired-table transition; the source-only test also needed
  to respect the intentional stale frontend exclusion. All three affected Python
  test modules then passed: 91 cases, including all five failures and the corrected
  temporary uploads fixture. This gives 6124 unique successful Python cases;
  raw failed XML remains intact beside repair evidence. No production changes
  followed the full gate; its successful evidence is reused only for unchanged
  content. Exact source preservation and initial/amended input hashes are checked
  by `final-evidence.json` in ignored `.runtime/c3-ai`. Linux source snapshot:
  `/var/tmp/3mm-c3-ai-20261026/source`. `git diff --check` passed.

  Built independent `three_mm_ai-0.1.0-py3-none-any.whl`, SHA256
  `f69d3066b75bf9395e51b1fdb25975bcea91e04cc48801ff33840bf40f9fdd7d`;
  unpacked/imported with Core imports forbidden. It is not installed into Core.
  Generic release source-only/required-file checks and compiled frontend confirm
  the retired AI endpoints/routes are absent. Owner VM remains accepted CAP08
  r2/schema `5a30b182c920`; no deployment, commit, branch, publication, delegation
  or reset in this extraction. Existing Agent automation execution is preserved;
  no historical proposal/job/effect is converted or replayed. Dashboards and its
  declarative consumers are the next separate C3 result. Full C5, new external
  Terminal, ARM/hardware/root-systemd acceptance remain outside this result.

- **CAP08 complete in the agreed bounded profile, deployed and verified,
  2026-10-26.** Owner scope is CAP08 and its associated Core cleanup; full C3
  extraction of Builder/Automations/Dashboards is excluded. `bounded_task_v1`
  supplies one-shot, interval and IANA weekday-calendar work, fixed skip-misfire/
  gap and earliest-fold policies, durable occurrence cursors and explicit bounded
  history retention. One journal/start/result path serves manual and periodic
  work. The optional independent worker computes schedules and invokes code;
  Core retains admission, current authority and durable outcomes, with no timer
  loop or application execution. Task command composition uses the existing
  command queue and one-use physical permit, separately approved command scope
  and exact live task lease. Unconfirmed issued effects hold the owner unknown;
  no automatic handler/effect retry. Historical jobs retain recovery evidence
  only, without an execution path. Contract: [Application tasks](APPLICATION_TASKS.md).

  Current immutable Core is `/opt/3mm/releases/core-cap08-complete-20261026-r2`,
  archive SHA256 `df09cb2b61d4f555b2b8aded22c0d675518b504820630b3f451b9c60c7a228c8`;
  schema `5a30b182c920`. Runtime/connector build
  `82cd97b95ff353f7e625f7bbce7bb62d81f51f574e8ee52d8fa23ad2505ed245`;
  default/task-host build
  `38fd949275153798f9f561188c1f735e9a056e95dac801bf970da2619119eb4b`.
  Normal immutable installer and additive retained-data migration passed.
  Runtime validation now validates each artifact's own bounded source map/hash;
  actual old/new payload-layout rollback and forward passed without restarting
  Core. The separate task worker remains explicitly enabled for this owner VM.

  Upgraded Task Probe to 0.2.0, SHA256
  `c12ae446eb714176618d6c56e01fa68be609454cd176e90d6257060994a02347`, preserving
  instance `157f6b9d9ea8f27a240caff5`, incarnation, local data and all four old
  task records. The old exact-artifact native activation guard correctly refused
  an unreviewed replacement. Added generic admin/CAS staging for a stopped task
  package: sealed inert registration, fresh exact-artifact consent, then normal
  activation. No application code runs during staging. Unresolved task/legacy
  claims block it. Installed independent Task Command Probe 0.2.0, SHA256
  `36dd724fed9caadea2666cdc2d87124a611a7b3dd7044054febcba7596b2c08d`, with
  only `task:switch_output`/`command:output` on the existing co-located mock Agent.
  Existing Fleet 0.1.11 and Output button 0.1.0 retain their instances, host pins
  and sealed grants. Owner users/roles, Core/device identities, configuration/key
  file hashes, Agent/public-web/session-worker pins and prebuilt frontend remain
  unchanged. All four app health checks, eleven services, Core readiness and
  Runtime/connector probes pass. Final journal: 9 succeeded/2 cancelled tasks;
  2 exhausted/2 cancelled schedules; no queued/running/unknown tasks or live
  schedules. No delegation, commit, publication, reset or frontend build.

  Evidence is frozen by per-file hashes in ignored `.runtime/cap08-complete`;
  staging payload `/var/tmp/3mm-cap08-complete-20261026/payload`. The ten Python
  suites produced 6139 passes, 615 explicit skips and one stale
  migration-head test assertion. Corrected that test to use the actual head;
  all 3 retained-data migration tests then passed, giving 6140 unique successful
  cases for those inputs. Raw failed XML is retained, alongside the repair XML.
  After adding stopped-task staging, reran the 20 affected authority/source/
  consent/lifecycle/registration/task/schema modules: 636 passed, 7 explicit
  isolated-root/non-POSIX skips. This rerun covers the later production edits;
  earlier full-suite evidence is reused only for unchanged content. An initial
  stale inventory test import was repaired to the already-extracted service,
  without production inventory changes. `git diff --check` passed.

  Actual owner VM SDK acceptance: three interval results 5050, one next-minute
  Europe/Sofia calendar result 5050; Core/host/worker restart preserves receipts
  and attempt counts; Core remains administrable with the worker stopped;
  three late occurrences skipped with zero handler attempts/no catch-up burst;
  queued cancellation never enters the handler; revocation refuses admission
  and fresh consent does not revive an old schedule. Task-mediated ON then OFF
  each has one handler attempt and one confirmed Agent command/delivery with
  task provenance. `live-result.json` records 21 passed assertions;
  `final-audit.json` records 33 preservation/artifact/health/authority checks.
  This is Linux x86_64/WSL and mock GPIO acceptance, not new ARM/physical GPIO,
  hostile-native sandbox, arbitrary workflow or scheduler-UI acceptance.
  General C3/C5 and other capability families remain separate future scopes.
  Owner test: `modules/task-probe/Test-VM.ps1 --interval 5 --runs 3`;
  calendar: `--calendar --timezone Europe/Sofia`; `--lookup` observes saved intent.

- **CAP08 first task profile deployed and owner-tested, 2026-10-26.**
  Owner explicitly requested VM rollout and a usable test. Current immutable Core:
  `/opt/3mm/releases/core-cap08-20261026-r3`; schema `4f29a071b819`. Built the
  candidate from the exact previous accepted Fleet release plus scoped CAP08
  files, retaining its verified prebuilt frontend and independent M21 source.
  Runtime and connector-worker use immutable build
  `bbdd4d247473fc9c342945d71b273b854ddbb59cb9cd9f08ecb7f3915f33872d`;
  new default native host and Task Probe use build
  `398b000fefdd92919a08a5b899645bd50b1c4e495f0fe4ec40f5140b31d3ce44`.
  Existing Fleet/output host pins, Agent/public-web/session-worker pins, owner
  accounts, Core/device identities, roles and configuration are retained.
  Added explicit optional `deployment/systemd/3mm-task-worker.service`, installed
  and enabled only for this authorized rollout, outside automatic installer unit
  selection. It runs as 3mm-platform with app-socket group access, independent
  Runtime code/environment, private network, resource limits and inaccessible
  Core DB/configuration/application keys. Core readiness survives stopping it.
  No new account, device, framework, frontend build or version-axis change.

  Deployment preparation found two actual integration omissions and fixed them:
  the shipped Runtime contract now lists all five task SDK actions; the shared
  public consent/review HTTP scope validator admits `task:<id>`. Added regression
  coverage for the shipped manifest and public request models. Final frozen
  candidate task/schema/consent gate: 56 passes. Deployment Runtime/native-host/
  release-builder gate: 115 passes, one explicit isolated-root driver skip.
  Earlier 977 protocol/SDK/task/migration and 1390 authority/Runtime checks are
  reused for their unchanged production inputs; they do not claim to cover the
  later HTTP-validator fix, which has the new focused gate and live API proof.
  Additive migration first passed on a copy of the actual owner DB without
  changing existing rows, then ran through the normal installer on VM.

  The first installer attempt rejected the old Runtime payload's file set after
  `tasks.py` was added and rolled back. Its readiness diagnostic was conservative;
  the old Core/Agent/Runtime were subsequently confirmed active. Per the existing
  recovery contract that rollback fenced old authority. A coordinated second
  rollout staged immutable Runtime/connector/default-host artifacts, recorded
  their old pins and provided restoration on installer failure. Final r3 includes
  the HTTP consent fix. Used the existing authenticated/audited `recover-key` CLI
  as the Core UID with CAS, then normal current-administrator consent APIs to
  restore ONLY the previous exact Fleet/output scope and human-permission
  selections for unchanged package/configuration/instances. Old seals were not
  reactivated; no database reset or fabricated native manual review occurred.

  Installed unchanged Task Probe ZIP0.1.0, SHA256
  `56b22afd96a34d576aa2cd160f3642c2f147604f43371abd4e9dc73f876d430d`, through normal
  upload/activation/current-owner consent. Exact scope: `task:calculate`, no human
  extension permissions or external resources. Instance:
  `157f6b9d9ea8f27a240caff5`. Two delayed real SDK requests reached queued ->
  running/progress50 -> succeeded/progress100/result5050. One queued request was
  cancelled with no handler attempt. Core/native-host/worker restart preserved
  the first request/result with exactly one original attempt. Final app journal
  has two handler attempts; Core has two successes and one cancellation, no
  unresolved work. Actual distinct worker UID, seccomp/NoNewPrivileges, separate
  network namespace, namespace-denied Core DB/application keys and absent Core
  imports were checked. Final 56 VM state checks pass, including seven services,
  all three application health/grants, Fleet's actual device read and Output
  button's granted observation. Browser/physical GPIO/new scheduler UI are not
  claimed by this SDK/terminal acceptance.

  Owner test: run `modules/task-probe/Test-VM.ps1` from PowerShell. It launches the
  installed CLI as the app UID using its independently pinned SDK. Default delay
  five seconds, upper100, expected total5050. `--lookup` reads the saved request;
  `--cancel` cancels it only while queued. The UUID is fsynced before the single
  submit; pending/unknown requests cannot be overwritten by another test. No
  secrets are exposed in the command/output. See modules/task-probe/README.md.

  Recovery: `/opt/3mm/previous` points to r2 (same additive schema); original
  `core-fleet-actions-20261025` remains immutable. Pre-upgrade DB backup:
  `/var/lib/3mm/deploy-backups/core-cap08-20261026/3mm.db`; later r2/r3 backups and
  a private pre-key-recovery backup remain on VM. Crossing the old/new Runtime
  payload file-set boundary requires coordinated Core/component pin recovery;
  the strict component validator is not an automatic compatibility adapter.
  In particular, the old `previous` Runtime artifacts are retained as recovery
  evidence, not a claim that a standalone current-helper update/rollback across
  that boundary is supported. Do not destructively downgrade populated task
  history. The recorded coordinator/pins are in ignored
  `/var/tmp/3mm-cap08-20261026/{before-state.json,coordinated-rollout.json}`;
  source/evidence/scripts and final VM results are in ignored `.runtime/tasks`.
  Final archive SHA256:
  `07884bd2c890523231a579afc8523bc539fce55dcb7eae3c91ba20ca2d56db0e`.
  Owner subsequently ran the documented PowerShell command and supplied its full
  successful output: request `0c7e31708dd545e595aa1124fbcc7b63`, task run
  `task_9a94b28b48604eada77de7ee773633c1`, queued/progress0 -> running/progress50 ->
  succeeded/progress100 with total5050 and `PASS`. This confirms owner acceptance
  of the first deployed one-shot SDK path. The earlier two-success/one-cancellation
  journal counts describe pre-handoff verification, not current totals after this
  new owner request. This follow-up updates documentation only; prior executable
  checks are reused, with no new runtime test or deployment.
  The bounded rollout and owner acceptance are complete; broader CAP08,
  recurring/calendar work and systematic C3 extraction remain separate scopes.
  No branch, commit, push, tag or publication.

- **CAP08 first bounded task profile implemented locally, 2026-10-25.** Owner
  authorized continuing the original Core/SDK plan with a narrow task contract
  and working example. Implemented `bounded_result_once_v1`: dedicated descriptor
  `tasks` / internal `kind: task`, exact sealed `task:<id>` consent through the
  existing authority manager (new internal task-only context11), persistent
  request/result journal, UTC due/deadline, progress, queued cancellation and
  one-use dispatch/start permits. Compatibility, schedules and old `kind: job`
  remain refused. The first artifact profile admits result-only tasks, with no
  command/connector/event/session/peer/checkpoint or scoped file/relational mix.
  External effects, recurring/calendar scheduling and composition require another
  bounded contract; CAP08 as a whole is not complete.
  Core owns admission and journal state, not execution or waiting. A separate
  optional unprivileged worker is included in the independent Runtime artifact
  via `--task-worker`. It performs signed host probes/RPC outside Core; it receives
  no Core DB access or signing keys. Separate `three_mm.task.info` verifies live
  start support plus exact instance/artifact/configuration; the existing host-info
  shape remains unchanged. The native host consumes a current one-use start permit
  before application code. Leases use UTC plus boot-monotonic time including
  suspend, with boot/worker/epoch/grant/incarnation fencing. Claimed work is never
  blindly redispatched. A provably unexposed invocation can fail not_dispatched;
  exposed uncertain work stays unknown and holds its owner's slot until stopped
  administrator reconciliation. The same current-administrator sealed action
  ledger provides idempotent resolution without manufacturing success.
  One execution per incarnation; pending budget8 per owner,32 live owners and1024
  history records per incarnation. Dedicated tasks are not an OS hostile-code
  sandbox or a hard CPU termination guarantee. Handler progress is0–99; only a
  valid in-time result becomes success/progress100. SDK lost-reply recovery is
  lookup-only. Historical lookup is owned by installation AND incarnation.
  Added explicit migration4f29a071b819 after3e189f465708. It creates only the new
  journal, with no grant backfill/reset. Updated the dynamic legacy baseline's
  exclusion list so older schema history stays unchanged. Empty downgrade works;
  populated task history refuses destructive downgrade. Adjusted the existing
  head-migration test expectations for the added empty catalog. The broader gate
  caught and corrected a misplaced duplicate-policy validator before completion.
  No production/test source edits followed the final passing gates.
  Verification:977 passes for new task/schema scenarios, migration history,
  complete protocol/SDK suites;1390 passes/7 explicit skips for affected authority,
  consent, platform/access, old-job refusal, module packages, real Runtime process
  and complete Runtime tests. The skips are non-POSIX alternatives or explicit
  root/distinct-UID/systemd ownership gates; this same-user functional acceptance
  does not claim those proofs or full release CI. Final tests use actual sealed
  consent, signed SDK through packaged Runtime, packaged worker, self-contained
  native host under `-I -S` with vendor locks and no visible Core dependencies,
  durable one-use permits and an own SQLite attempt journal. They confirm delayed
  arithmetic result5050, progress, restart without replay, lost admission reply,
  strict idempotency/timing, revocation/reconsent, foreign owner/incarnation,
  deadlines/budgets, worker loss/unknown, current start denial before code,
  one-use permits, forged worker frames, boot/time rollback and guarded resolution.
  A real-Core fingerprint test was rerun with frozen source after it correctly
  detected source edits during the earlier run; final independent update/rollback
  gate passes. No frontend changes/build or runtime UI acceptance was needed.
  Neutral source: examples/task_probe and modules/task-probe; contract:
  docs/APPLICATION_TASKS.md. Local initial0.1.0 ZIP:
  modules/task-probe/dist/task-probe-0.1.0.zip, SHA256
  56b22afd96a34d576aa2cd160f3642c2f147604f43371abd4e9dc73f876d430d.
  Evidence/input hashes: ignored .runtime/tasks/{checked-inputs.json,final-tasks.xml,
  regressions.xml}. Matching new Core/Runtime/native-host artifacts and an explicit
  optional worker rollout are the next target-environment gate. This task did not
  deploy/migrate the owner VM, alter component pins, or add an always-on installer
  service; /opt/3mm/current remains core-fleet-actions-20261025 with the previously
  accepted Fleet/output application. No branch, commit, push, tag, publication or
  release/SDK version bump. Independent M21/source work preserved. This closes the
  local first C1/C2 task result; systematic C3 extraction and broader C5 remain.

- **Independent operator output application accepted on VM, 2026-10-25.** Owner
  approved the proposed next bounded step: a small application using the existing
  CommandProbe/SDK, one explicitly approved output, durable command results,
  revocation/restart and a second provider with the same application package.
  Added modules/command-probe: deterministic Manifest-v2 package0.1.0, public-SDK
  service and minimal English/Bulgarian operator UI at /output-button. The wheel
  reuses examples/command_probe. One declared binding `output` requests
  gpio.digital.control1.0/set_output, channel gpio.output.1 and a boolean value.
  Device selection, exact resource consent and resource replacement reuse existing
  Core mechanisms. The application has no administrator route/reads/actions,
  raw HTTP, browser credentials, inventory enumeration or additional Core branch.
  The service scopes browser UUIDs to the trusted operator user; lookup does not
  disclose another actor's request. Pending UUIDs are saved before the single send;
  lost responses/reload use status reads, with explicit outcome review for uncertain
  work. Displayed values are command results, not live GPIO state. Background
  observation preserves usable idle buttons while current authority is rechecked
  by Core at effect admission/permit. No shared contract, SDK or Core production
  source change; no Core schema migration or version change.
  New Linux checks: three integration scenarios pass with actual final ZIP/UI
  compiler/native loader, ordinary-user operator admission, separate signed SDK
  Runtime, command queue, execution permits, journals and real mock Agent runtimes.
  They cover ON/OFF, request conflicts, actor isolation, permission/resource/session
  revocation, Core authority socket restart and no effect replay. Explicit sealed
  resource replacement from a native provider to an embedded_firmware provider
  executes the same package/binding on a second mock Agent; old requests stay on
  the original device. External helper systemd start and response peer are simulated
  in these isolated tests; their Core fencing/result checks remain real. Final UI
  nine cases and vue-tsc pass. Install-time UI compilation succeeds both locally
  and on owner Core. Browser inspection covers the exact final compiled package,
  ordinary user, pending/confirmed ON/OFF, revoked-resource clearing/denial,
  Bulgarian, desktop/light and390px/dark. The POSIX skip marker/import cleanup
  followed the passing Linux integration run; executable scenario logic and package
  are unchanged, so that evidence is reused. Unchanged prior Core/SDK checks remain
  applicable; no broad release gate is claimed for this independent package.
  Installed the new application through normal owner Core upload, activation and
  current-administrator package consent APIs, selecting vm-3mm and ONLY
  `command:output` plus `control_output` for the existing owner. No new account,
  fabricated owner-registry device, Fleet change or other application grant change.
  Core remains /opt/3mm/releases/core-fleet-actions-20261025. Instance:
  bdb37806a297418a4bc01910. Source ZIP SHA256:
  efa0a5cd5119373dbc7097df4d88e29f4f89dae1fadadc2966f388823cdf7979;
  compiled UI1f2ffc14ad5b2900265ae59bfdb8f5fad5b0c438f3d626b4f8e68bb3cae3cafa.
  Local ZIP: modules/command-probe/dist/output-button-0.1.0.zip (not published).
  Owner WSL acceptance uses the actual installed service, signed Runtime and
  Agent-module Digital GPIO Output1.1.0 with verified mock driver. Agent confirms
  ON/OFF; actual application systemd restart preserves the original result with
  no additional command. The first query immediately after Type=simple startup
  was unconfirmed before the socket was ready; query-only recovery found the same
  receipt, with no command resend. Resource revocation then returns access-required
  and refuses a new command without queueing. Fresh normal consent restores access;
  final OFF is confirmed and Agent state reports false. Three commands total for
  this acceptance, all succeeded. DB integrity, existing users/Core identity/Fleet
  installation, six main services and both application health checks pass. Backup:
  /var/lib/3mm/deploy-backups/output-button-20261025/before-install.db.
  Owner subsequently supplied screenshots of the installed Output button showing
  both On and Off as "Confirmed by the device", with distinct request IDs on
  dev_e5cd9f422fae44dd822fbf99acfb5ed9 / org.3mm.digital-output. This independently
  confirms owner UI acceptance of both effects in the VM mock profile. Screenshot
  order does not establish the current output state. This follow-up changes only
  documentation; the implementation and previous verification evidence are reused.
  Overall-plan review: updated CORE_SIMPLIFICATION_PLAN to mark the first working
  path accepted. This closes the selected command mechanisms, not the whole
  application platform: systematic C3 removal of product imports/routes/models/
  dependencies and broader C5 acceptance remain ahead. Current Core still includes
  Builder, Automations, display and extension-project routes/models. This is a
  status clarification only, not authorization for another implementation scope.
  Owner uses the operator contract from their administrator account on VM; the
  isolated test separately proves normal-user permissions. Second-provider
  replacement is isolated acceptance, not a second live owner device. Physical
  GPIO and OTA remain outside scope. No further implementation is pending in this
  bounded result; owner can open http://localhost/output-button. No branch, commit,
  push, tag or publication. Independent M21/source work preserved. Evidence is in
  ignored .runtime/command-probe; temporary acceptance server stopped at handoff.

- **Fleet Agent module path accepted on owner VM, 2026-10-25.** Owner
  approved this bounded next path and explicitly approved local Fleet0.1.11,
  retaining manual Fleet installation. Added generic current-administrator
  ApplicationHost module catalog/install/disable, capability discovery/state/invoke
  and command-status methods. Manifest-v2 route declarations gate each operation;
  service scopes remain separate and Fleet receives no browser token or URL proxy.
  Writes recheck the tracked administrator, active exact package/build/native
  approval and declared route/action inside the existing authority write lease.
  They reuse shared module lifecycle/command queue mechanisms with sealed,
  app/actor/request-bound receipts. Changed requests cannot reuse an identifier;
  uncertain replies are resolved by status reads without automatic mutation replay.
  Capability admission and first dispatch pin the selected provider/declaration
  and device control generation. No Core-specific Fleet/GPIO branch, new database
  schema, migration or reset; no separate module registry or Agent runtime update.
  Fleet device details expose target confirmation, module selection/install/disable,
  schema-derived boolean controls and distinct pending/confirmed/failed/unknown
  outcomes. Persisted requests survive reload; storage failure blocks sending.
  Physical GPIO and Node OTA remain outside this acceptance point.
  New checks: affected Python gate220 passes, followed after final small backend
  changes by focused131 passes (overlapping gates, not351 unique cases). These cover
  authority denial/revocation/isolation, idempotency, module lifecycle, provider
  replacement before dispatch and real mock-Agent install/ON/OFF/disable. Core
  frontend63 and Fleet frontend18/build3 pass; both vue-tsc checks and Core Vite
  production build pass. Final Fleet ZIP validates/compiles against current Core,
  exact native approval with empty service scopes and native loader health pass;
  final package probe confirms install -> Core queue -> real AgentModuleRuntime
  with MockDigitalGpioDriver -> ON -> OFF and confirmed results/state. Browser
  acceptance exercised that actual compiled package/public host in disposable Core
  data, including pending locks, recovery after a missing response, Bulgarian,
  desktop/light and390px/dark controls. Existing unchanged evidence was reused;
  no full release CI or physical-output acceptance is claimed.
  Local artifacts (no publication):
  C:/Users/SIMPLEX-3260/Desktop/3mm-fleet/dist/3mm-fleet-0.1.11.zip,
  SHA256 a33d5c0129d7cb79d625f5ffff78b5c0b2a85f9709e638799a6cc6abf8faf6da;
  dist/digital-output-1.1.0.zip in the same checkout,
  SHA256 e7ab19b266db360fc76b87204080c3ac863d13ad8c2a8c3657525e697da6991a.
  Previous Fleet0.1.10 ZIP remains preserved.
  Updated owner WSL Core with the standard immutable installer, retaining role,
  host-managed networking and six independent component pins. Current release:
  /opt/3mm/releases/core-fleet-actions-20261025; rollback:
  /opt/3mm/releases/core-fleet-host-20261025. Installer exited0; source1435 and
  frontend44 files match payload, all199 frontend inputs match the checked build.
  Still beta.57 with the working tree over ebb98fb; archive SHA256
  ed260c6791115d7727294951da605175cc6dd6e6929a2a90e4c01e02fc4d2f9e.
  Six main services, Core/Agent readiness, Core health, public UI modules and the
  current Fleet native host are healthy. New protected routes are installed and
  unauthenticated mutation is denied. DB integrity, installer backup, previous
  users/packages/identities and stable session/application identities verified.
  During verification the owner independently installed/approved the exact
  Fleet0.1.11 ZIP and uploaded the exact Digital GPIO Output1.1.0 ZIP; normal owner
  consent/session changes explain changed rows. Current exact UI approval passes.
  This agent did not install/approve Fleet or change its grants. Agent GPIO driver
  is configured mock; module_installations and device_commands were empty at the
  initial handoff. The owner subsequently confirmed that Install, Disabled,
  Switch on and Switch off work on the VM. This user-reported acceptance closes
  the bounded Fleet -> Core -> Agent module path; no additional implementation
  is pending in this scope. Physical GPIO and OTA remain unverified. Recording
  this acceptance changes documentation only; existing checks are reused without
  a runtime rerun. No commit, push, tag, branch, release or independent M21 change.
  Evidence: ignored .runtime/fleet-actions and
  .runtime/fleet-actions-deploy; temporary acceptance server stopped at handoff.

- **Core device-read host deployed; owner installs Fleet, 2026-10-25.** Owner
  explicitly requested the Core update and reserved Fleet installation for themself.
  Deployed the current beta.57 working tree with the standard immutable full-profile
  installer on owner WSL Ubuntu-26.04, retaining host-managed networking and role.
  Current: /opt/3mm/releases/core-fleet-host-20261025; rollback previous:
  /opt/3mm/releases/core-sdk-resources-ui-20261025-r2. Installer unit
  3mm-core-fleet-deploy-20261025 exited0. Source1432 files and all44 emitted frontend
  files match the prepared payload; all199 frontend inputs match the checked build,
  which was reused with the previous bounded Core/Fleet verification evidence.
  Fresh installed checks: six main services active; Core/Agent readiness, Core health,
  Web and public host module HTTP200; both administrator device-read routes installed
  and unauthenticated reads denied. Runtime is bound to the current Core PID.
  DB integrity and installer backup verified; existing users, sessions, package rows,
  identities and grants preserved. All six independent component pins retained.
  Before deployment there were0 installed applications. During final verification
  the owner uploaded the exact Fleet ZIP c89d2dc5… and activated/approved it through
  the normal administrator flow (activation/consent audit evidence). This expected
  addition explains changed whole-table fingerprints; previous rows and pre-update
  backup fingerprints were checked separately. Fleet0.1.10 is active and its native
  host signed health probe passes. This agent did not upload/activate/approve Fleet
  or modify its grants; only read its resulting status. No reset, new account,
  version bump, branch, commit, push or release. Independent M21 source preserved.
  Core archive SHA256:
  4dabedc1279c8e3dca70b57894cd459efe70d3e21e7e222e6b2cc93ae64d4587.
  Evidence: ignored .runtime/fleet-deploy and /var/tmp/3mm-fleet-core-20261025.
  Owner screenshots now confirm the installed list and detail at localhost/fleet:
  vm-3mm is Online/Hub, with live inventory, CPU/RAM/storage and the device-module
  section. The section is correctly empty; Core applications are separate from
  Agent modules on that device. This closes the first read-only path on the VM.
  Next: select the next bounded management contract with the owner; no further
  implementation is authorized by the screenshots alone. No physical actions or
  Fleet management contracts were added or exercised during this deployment.

- **Fleet first ApplicationHost path, 2026-10-25.** Owner approved starting the
  bounded list/detail adaptation. Implemented generic, per-administrator-route
  `administration_reads` declarations (`devices.list`, `devices.detail`) and the
  credential-free `host.administration.devices.list/detail` contract. Each GET
  binds the source/build hashes and rechecks current tracked login/role/session,
  active installation, native UI approval and declared route in the same
  DB-enforced read-only snapshot as the registry projection. Service scopes remain
  separate. Existing device routes reuse the shared projection; no new tables,
  migration, duplicate registry, generic URL proxy or Fleet-specific Core case.
  Fleet on Desktop now declares SDK1.3 and uses that host for paged devices,
  inventory schema2 and installed modules. Removed the direct-token HTTP helper
  and its former approval/GPIO/capability/module-mutation/Node-update controls as
  a complete obsolete path. No token fallback remains in Fleet source. Kept
  administrator routes, explicit menu navigation, Bulgarian and public UI theme
  tokens. Management actions are a later bounded contract, not silently available.
  Checks on Ubuntu-26.04/Python3.14 and the installed Core Vue toolchain: focused
  Python gate52 passes (51 unchanged passing cases plus the corrected native-revoke
  fixture case rerun alone); earlier affected regression gate149 and the initial ui-host cases
  remain valid for unchanged consumers, with overlap rather than an extra total.
  Core frontend82 pass (unchanged65 reused, new host17 after fixture correction),
  Fleet UI11/build3 pass; Core/Fleet vue-tsc and Core Vite production build pass.
  The real final Fleet ZIP validates and compiles through the install-time compiler;
  native host loader health is ready. Exact native approval with empty service
  scopes admits list/detail and denies each route's undeclared counterpart.
  Browser acceptance uses disposable Core data, actual compiled Fleet assets,
  built public UI modules and current Core host source: list/detail SPA navigation,
  Bulgarian, light/dark, 390px layout and clearing data after real session revocation.
  Final ZIP: C:/Users/SIMPLEX-3260/Desktop/3mm-fleet/dist/3mm-fleet-0.1.10.zip,
  SHA256 c89d2dc55a2df59843e0a655de0d0b659f8e5718d219fd63da7b4822105b71af;
  emitted UI fa47a49d49d2b595516626e48ebc36536091864e3fa33a6633e24df282d74bf8.
  Ignored evidence: .runtime/fleet; temporary preview server stopped. Visual
  evidence predates only unused-CSS/locale cleanup and the corrected loading label;
  the final ZIP was recompiled/rechecked afterwards. No full release CI, installed
  VM/native service or physical-device acceptance is claimed. No version bump,
  branch, commit/push, release, reset or VM change. Preserved independent Core/M21
  source changes. Next gate: matching immutable Core update on the owner VM,
  Fleet installation and normal application access approval, then owner-device
  acceptance. Current VM still uses core-sdk-resources-ui-20261025-r2.

- **Fleet checkout and readiness assessment, 2026-10-25.** Owner asked whether
  Fleet can be checked out on Desktop and adapted to the new Core. Cloned
  https://github.com/ldobranov/3mm-fleet to
  C:/Users/SIMPLEX-3260/Desktop/3mm-fleet at b67f467 (0.1.10); preserved its main
  branch/source. Its Manifest v2/application/compiled-UI package validates against
  current Core beta.57. Existing Fleet build3 and UI20 cases pass using the
  installed Core toolchain. Baseline ZIP built in Fleet's ignored dist directory.
  This establishes build/schema readiness, not native startup or live integration.
  Fleet is an administrator UI over generic device/enrollment/capability/module/
  GPIO/Node-update APIs; Core retains those authorities and registry ownership.
  Current Fleet still declares SDK1.0 and reads browser authToken directly.
  The credential-free ApplicationHost currently exposes application operations
  and sessions, not the generic administrator device-management surface Fleet
  needs. The proven command-binding vertical alone does not cover that surface.
  Next bounded adaptation: define/use the common current-administrator UI contract
  for device list/detail, preserving active-package/role/revocation checks and
  avoiding credential exposure, then extend the same path to management actions.
  No Fleet-specific Core exception, authority downgrade, commit/push/version
  change or VM/Fleet installation was performed during this assessment. Fleet's
  reviewed-native direct HTTP mode remains a distinct existing profile; do not
  label it a completed migration to the credential-free SDK/host model.

- **Administrator command resource UI and VM update, 2026-10-25.** Continued
  the accepted command vertical with Extensions → Command resources for installed,
  administrator-managed applications. The dialog reads declared requirements,
  pages compatible candidates without automatic selection, separates readiness,
  and reviews both exact devices/providers before explicit restart approval.
  Changed/expired/foreign previews cannot apply. Lost apply/recovery replies lead
  to status reads without mutation replay. Current pending changes are found
  server-side after browser/Core restart; stale historical interrupted records
  are discarded once a different epoch/recovery supersedes them. Recovery requires
  a separate acknowledgment, then leaves fresh consent/activation to the owner.
  Added only command metadata to configuration, versioned admin observations and
  an admin-only read-only current-pending projection; no registry/schema change.
  Existing initial-install device configuration remains its own dialog.
  Checks: 112 frontend cases (final dialog13, reused99 unchanged cases), 87
  affected Python cases (rebinding/current-pending32 and direct regressions55),
  vue-tsc and Vite production build pass. Browser inspection covers desktop/light
  and a 390px iframe/dark with disposable provider data; fixtures are absent from
  the production bundle. Prior broader Core/SDK evidence remains for unchanged
  mechanisms; no full release CI or physical provider trial is claimed.
  Installed with the standard immutable installer on owner WSL Ubuntu-26.04.
  Final current: /opt/3mm/releases/core-sdk-resources-ui-20261025-r2; previous:
  /opt/3mm/releases/core-sdk-resources-ui-20261025. The first UI deployment was
  superseded by the final historical-pending refresh correction. Installer exit0,
  all six main services active, Core health/readiness and Windows :8080 return200.
  Source/frontend match the prepared package; the new protected pending GET is
  installed; DB integrity, users, provisioning/Agent/Core identities, packages and
  grants match pre-update fingerprints. Backups and older releases are retained.
  Independent Runtime and native host inputs/pins match and were retained. Still
  beta.57, includes_working_tree=true over ebb98fb; no commit/push/tag/reset or
  independent M21 change. Archive SHA-256:
  9019ca5acb1701887d79e560fea85417d125d23901db07f5f5627824ba42f2e5.
  Evidence: ignored .runtime/command-ui and /var/tmp/3mm-resources-ui-20261025-r2.
  VM currently has no installed applications; visible resource workflow was
  inspected with isolated fixtures. Next: owner application/provider acceptance
  on the updated VM, then choose the next bounded capability scope.

- **Core/SDK deployed to the owner VM, 2026-10-25.** Owner explicitly requested
  deployment of discovery and command resource replacement to the local VM.
  Installed current ebb98fb working tree on WSL Ubuntu-26.04 with the standard
  immutable full-profile installer, host-managed networking and existing Hub
  setup. Installer unit 3mm-core-sdk-deploy-20261025 exited 0. Current release is
  /opt/3mm/releases/core-sdk-rebinding-20261025; previous is
  /opt/3mm/releases/setup-access-ap-20261025. Version remains 0.3.0-beta.57 with
  includes_working_tree=true; no version bump, commit, push, tag or reset.
  All 193 frontend inputs matched the installed build, which was reused exactly;
  prior checked Python inputs also matched, so the 3817-case evidence below is
  reused rather than rerun. Full source payload: 1422 files, archive SHA-256
  a72eb105719210648af42e2ce945d2ecaedaabd5d4dff93f00cef9847cf05117.
  Updated the independent Platform Runtime through its transactional updater to
  1ad17d048894abbbb6cc3374920562a125f00cffad6873d235482e426a8db932,
  retaining its previous pin and proving unchanged Core PID during that update.
  Staged the native application-host bundle with its real isolated 3mm-app probe,
  then moved the default for new instances under release/component locks to
  b53a0ec571cd6c416f7ab2cd73dac7cdd4f75492aeb21baf935aa5577aabb0b6.
  Previous default/pinned instances were preserved; there are no installed apps.
  Fresh verification: SQLite integrity; provisioning/Agent identity, users,
  packages, Core identity and authority-grant fingerprints unchanged; installer
  DB backup present; installed source and frontend match the prepared package;
  six main services active; Core/Agent/Web/Runtime have no automatic restarts.
  Core health/readiness and Windows http://localhost:8080 return 200. All five
  new API paths are present, unauthenticated discovery/rebind is denied, live
  Runtime exposes command.discover and the isolated host imports the new SDK.
  Evidence: /var/tmp/3mm-core-sdk-20261025 and ignored
  .runtime/vm-core-sdk-20261025; backup: /var/lib/3mm/deploy-backups/core-sdk-rebinding-20261025.
  This is VM deployment acceptance, not a live hardware/provider rebinding trial.
  Next: owner use of the updated VM; no new frontend chooser was added.

- **Explicit command resource replacement, 2026-10-25.** Owner authorized the
  next bounded vertical: replace a resource of the same running application.
  Added admin preview/apply/status/recover endpoints over existing sealed plans,
  grants and helper lifecycle tickets. Preview shows both resources/providers;
  explicit approval retains the selected scopes and human grants. Core retires
  the old epoch, saves desired configuration behind an inactive lifecycle fence,
  then enables it with a fresh resource grant only after confirmed same-artifact
  restart and current actor/resource/policy checks. No automatic failover or
  replay. Interrupted work requires positive quiescence evidence, followed by
  fresh ordinary consent/activation. Late old activation cannot overwrite that
  recovery. Shared lifecycle ticket code is reused by ordinary routes and rebind.
  Command lookup exposes original target and execution receipt separately from
  invalidated authority. A retained logical request cannot move to another target;
  claimed commands retain their original result path under existing expiry rules.
  Scope is an active installation with a current grant, isolated command config
  key and exact compatible contract. Shared-resource config changes, relational
  applications and sensor authority are refused. No UI chooser, schema migration,
  deployment, commit, reset or independent M21/setup/AP change.
  Verification: affected application/authority/lifecycle, device broker, Runtime,
  protocol and SDK selection has 3817 distinct passes and 598 expected skips
  (596 require root/distinct OS principals/systemd, 2 are non-POSIX refusals).
  Includes all 29 rebinding cases and 286 SDK cases. Initial broad run stopped
  at an old lifecycle expectation that claimed work becomes failed; corrected
  it to retain the original receipt path. Reused its 1038 unaffected passes and
  4 skips; final rebind/lifecycle/remainder run has 2493 passes/594 skips, plus
  286 SDK passes. Final active-installation restriction is covered by that fresh
  rebind run. Linux Ubuntu-26.04, Python3.14.4/pytest8.4.1, base ebb98fb plus
  preserved local work. XML, exact commands, input hashes and aggregate evidence
  are under ignored .runtime/command-rebinding. Final hash comparison found no
  subsequent production/test changes; only docs followed. Whitespace passes.
  New local documentation links resolve. Existing references to sibling project
  repositories in the simplification plan are unavailable on this checkout.
  External systemd/device effects are simulated; no live hardware, root-helper
  ownership proof or full release CI is claimed. Next: owner review of this
  bounded result; further capabilities/UI/device acceptance remain separate scope.

- **First Core/SDK command vertical, 2026-10-25.** Owner accepted proving one
  working path with a second provider before broader capability design/cleanup.
  Added admin-only, paginated command requirement discovery over the existing
  capability registry; exact versions/canonical argument schemas, source
  resolvability and current readiness remain separate. Missing/stale health is
  unknown. Signed SDK command.discover uses a DB-enforced read-only snapshot and
  current sealed command grant; it returns only the selected resource, or a
  resource-free access-required observation. No compatibility grant fallback,
  key creation, configuration write, provider switch or execution from discovery.
  Existing activation configuration + administrator consent select/authorize a
  resource for a fresh installation. The SDK-only examples/command_probe client
  submits through the existing queue/one-use permit and recovers durable results.
  Two native/embedded provider profiles are candidates without special Core or
  client names. Tests use real admin HTTP selection/denial, package validation,
  consent seals, a separate packaged Runtime process, signed SDK, queue, permits
  and journals. Simulated installer/effects do not claim live systemd or hardware.
  Restart, no replay, revoked grants, provider drift, offline/stale health,
  isolation, no discovery writes/key creation and bounded pages are covered.
  Final affected Linux/Ubuntu-26.04 Python3.14.4/pytest8.4.1 selection: 1417 passed,
  1 expected non-POSIX-refusal skip, 87.14s. Includes full protocol/SDK suites,
  command/authority/consent/configuration/access/capability regressions, Runtime
  transport/component and Agent journal. No production/test edits followed;
  only documentation/evidence. XML and final input hashes are under ignored
  .runtime/command-discovery. Base ebb98fb plus the existing setup/AP changes and
  this scoped change; no full release CI, frontend build, commit or deployment.
  Material limits: exact schema equality, existing device command profile,
  no new UI chooser. The later resource-replacement entry above supersedes the
  initial no-rebinding limit. Ordinary activation still refuses unreviewed staged
  configuration. This evidence describes that earlier tree, not the later edits.

- **Refresh local setup/AP work onto latest main, 2026-10-25.** Fetched and
  fast-forwarded d68468c to ebb98fb, then reapplied all local setup/AP changes.
  The single conflict in the helper writable-path test preserves both upstream's
  application-host scope assertion/comment and our recovery DNS directory.
  Compared with the saved pre-sync tree, only the five upstream CI/docs/test
  files changed; application code, dependencies and frontend remain identical.
  Fresh Linux systemd-template check: 26/26 pass; prior setup/AP/auth/frontend
  evidence below is reused for unchanged inputs. Diff whitespace and unresolved
  conflict checks pass; origin/main was reconfirmed at ebb98fb after integration.
  No commit, push or additional deployment. WSL retains setup-access-ap-20261025;
  the upstream changes require no application update. Next: owner's acceptance,
  including the previously outstanding physical Wi-Fi captive-popup check.

- **Code-free setup and AP captive portal, 2026-10-25.** Owner requested removal
  of the temporary code and automatic portal discovery after joining an AP.
  Removed code store/CLI/bearer form/API fields and URL fragments together.
  Setup APIs now follow live initial/recovery/pending-activation state, deny
  changed state and closed recovery, and retain same-origin JSON mutation checks,
  fixed recovery identity/admin, existing admin proof and transaction fencing.
  Both initial and recovery APs direct HTTP captive probes to 10.42.0.1:8895/setup.
  Existing Web handles only requests arriving on the active recovery AP address;
  Node/no-Web uses the optional port-80 listener. Recovery DNS configuration is
  loaded for AP startup, removed afterward/on failure and cleaned on recovery.
  Full and Node installers prepare its directory; helpers retain scoped writes.
  Linux setup/provisioning/role/routes/web/runtime selection: 234 pass, one stale
  DNS-template expectation corrected; final systemd/admin/Node installer group
  80/80 passes, reusing unchanged passes from that selection. Earlier stale
  helper writable-path assertion was aligned with the existing application-host
  path plus the new DNS path. Frontend final affected tests 13/13, TS and Vite pass;
  the accidentally broad initial run had 498 passes and one old code-link case,
  corrected by the final affected run. Browser preview shows the form directly.
  Installed via standard immutable installer (exit 0) on Ubuntu-26.04:
  current /opt/3mm/releases/setup-access-ap-20261025, previous
  local-d68468c-20261025, still beta.57 with reviewed local changes over d68468c.
  Owner had completed Hub setup as vm-3mm before this update. Provisioning,
  Agent identity and administrator rows match pre-update fingerprints; SQLite
  integrity, Core readiness, five primary services and Windows :8080 pass.
  No reset, commit, push, release or physical-device deployment. Actual phone/
  laptop captive popup on Wi-Fi remains a hardware check; WSL has no AP adapter.
  OS policy controls popup/notification; manual AP URL remains available.
  Inputs/check logs: /var/tmp/3mm-local-build; deployment/backup evidence:
  /var/tmp/3mm-setup-update-20261025 and ignored .runtime/wsl-install.

- **Local owner WSL installation, 2026-10-25.** Installed clean Ubuntu-26.04
  (Ubuntu 26.04.1, systemd, x86_64) from local clean commit d68468c using the
  standard full-profile immutable installer, host-managed networking and origin
  http://localhost:8080. Current: /opt/3mm/releases/local-d68468c-20261025,
  version 0.3.0-beta.57. Owner will perform setup; no role was selected here.
  Locked pnpm 10.13.1 install, frontend type-check/build passed. Installer unit
  3mm-local-install-20261025-r3 exited 0; setup-local/update-helper active,
  Linux readiness and Windows localhost:8895/ready returned ready, and
  http://localhost:8895/setup returned 200. Earlier launch attempts failed before
  installer mutation (relative path and launcher line ending), corrected in r3.
  Build inputs/logs are in /var/tmp/3mm-local-build and ignored .runtime/wsl-install.
  No full suite, owner setup, reboot persistence or extension acceptance claimed.
  A hidden WSL keepalive launch was blocked by execution policy; leave an Ubuntu
  terminal open during owner setup if the distribution otherwise stops.


- **Simple administrator application consent accepted on rasp-3mm, 2026-10-25.**
  Owner explicitly approved administrator consent for the exact native Linux
  package/UI in place of a mandatory manual code audit. Normal App access now
  has one Allow access action and collapsed resource details; initial checkboxes
  select all declared scopes/current administrator permissions, later visits
  load the saved subset (including empty choices). Existing role grants remain
  separate; account choices edit direct grants for the current administrator.
  Fresh route installations explicitly use review_required. Missing first Core
  key is provisioned by authenticated/audited consent preview; existing stale,
  foreign/corrupt keys are not overwritten. Preview creates no native/resource
  grant; Allow rechecks current tracked admin, exact artifact/build/configuration/
  resources/human grants, boot+expiry/guard/fingerprint in one key/write scope.
  Truthful administrator_approved Native/evidence/profile never fabricates a
  completed manual audit or isolation. Existing typed resource checks, including
  whole relational profile, remain. No other users/roles assigned. UI opens after
  first activation if access is missing, and separates saved consent from a
  stopped/unavailable runtime. No consent on upload/open/refresh; preview may
  initialize infrastructure. Old manual review remains an optional path.
  Same approved artifact/config/resources survives confirmed disable/enable:
  exact saved consent captured before helper, fresh immutable bytes and current
  native/grant/resource pins rechecked at completion, only execution epoch and
  sealed envelope rebound. Numeric consent revision, original approved subject,
  scopes and human permissions remain. Old commands/session bindings stay stale;
  revoked/replaced grants, code/resource/key changes and unknown lifecycle do
  not resume rights. Stop still works with unusable review metadata/key.
  Verification: initial coordinator/context/policy/keys 238 cases =236 pass,
  2 expected skips (foreign-UID needs root-run fixture, non-POSIX refusal).
  Final 28 consent cases (including added relational guards) pass. Boundaries
  initially126/127 pass; the one actual stop/start positive case exposed strict
  Python parsing of sealed JSON tuples. Corrected to existing JSON _parse; final
  lifecycle87 cases (22 new plus corrected positive and existing fences) pass.
  Fresh-install denial test1 pass. Unchanged passing boundary/pure-key cases
  reused with source SHA pins; no full release CI claim. Initial lifecycle
  collector used the old renamed node ID and ran0; final87 supersedes it.
  Frontend54 targeted dialog/DTO cases (48 final affected+6 unchanged peer/session)
  and35 Extensions cases pass; Vue/TS and prebuilt Vite pass. Details/collapsed
  view and actual checked rights visually verified in live browser.
  Physical Terminal1.0.3 used exactly its prior session:console:open + terminal_use
  choices: one Allow produced truthful administrator grant5; disable/enable
  retained numeric5/scopes/approved-subject SHA/human rows with fresh envelope/
  epoch, access_saved/effective true and target available. No second Allow and
  no Terminal feature work or interactive session launched. Core PID236267
  remained throughout. Current immutable /opt/3mm/releases/simple-consent-20261025,
  still beta.57; previous retained-data-20261025-r2 kept. Only Core restarted;
  Agent29317/Web29319/Runtime29335/helper227678/relay144368 unchanged, all active,
  NRestarts0. Identity/pairing/provisioning/key/worker/env preserved; SQLite and
  readiness pass; schema remains3e189f465708, no SDK/schema/version change.
  Old code rejects new administrator-native records on code-only rollback;
  preserve keys/data and use the kept backup/new code rather than rewriting seals.
  DB backup /var/lib/3mm/update-helper/simple-consent-20261025/3mm.db. No reset,
  commit/push/branch/publication. Owner Ubuntu /opt/3mm-dev/Node/network untouched.
  Own lab stopped at handoff; Ctrl+F5 needed in old Extensions browser tabs.
  Evidence simple-consent-{core-candidate,core-installed,live,final}-20261025.json;
  common-sessions-consent-{coordinator,final,boundaries,lifecycle-final,install}
  -20261024.json (actual runs25th). Public contracts updated with current flow.

- **Capability foundation before cleanup, 2026-10-25.** The owner clarified
  that this is a fundamental platform design, not only Core renames/removal.
  Current apps except Terminal are treated as outdated requirements sources,
  not compatibility targets. [The expanded plan](CORE_SIMPLIFICATION_PLAN.md)
  now catalogs CAP01-CAP21: common contracts/discovery, principals/grants,
  lifecycle, operations, own data/config/secrets, events/outbox, tasks, UI,
  public ingress/sessions, media, connectors/webhooks, app composition,
  devices/workloads, streams, peer/offline, notifications, search/reports,
  audit/recovery, resource profiles and development tooling. It separates Core
  authority from optional executors/providers and SDK helpers. Existing useful
  capabilities need a proven generic replacement before removal; retired
  implementations stay retired. Current scoped jobs are unsupported, public web
  is GET/HEAD, and generic media/public-mutation/composition are design gaps,
  not features claimed as complete. C0-C5 now cover contracts and executable
  foundation before source cleanup/acceptance; A1 builds current apps afterward.
  The earlier proposed CAP08 design is superseded by the first working command
  vertical above; task/schedule claim/lease, retry and lifecycle design remains
  a later candidate, with no old scheduler revival or mass rename. Preserve Terminal and the accepted
  M20/P0-P6/common-session/removal/retained-data boundaries, app sources/data,
  independent repositories and installed devices. Verification: static current
  contract/source review and documentation links/whitespace/consistency only;
  no runtime implementation, test/build, deployment or commit in this handoff.

- **Retained application cleanup fixed and accepted on rasp-3mm, 2026-10-25.**
  Owner requested access to data cleanup after last package deletion and removal
  of the disposable Session platform probe. The probe app, temporary DB and ZIP
  were removed through ordinary uninstall -> erase -> package DELETE. Fleet had
  no data files; its empty retained directory and our failed-removal fixture are
  now erased through the normal API, with no direct SQL repair/forced deletion.
  New application_retained_data ownership survives all package deletion. Admin
  GET /application-extensions/retained-data and a separate Extensions section keep
  orphan data discoverable; active owners are excluded and failure retains the
  cleanup entry. Uninstall records ownership atomically; actual stored instance
  mapping remains authoritative. Conflicting fresh runtime identity refuses
  activation before helper effects. Erasure holds Core's authority writer and
  binds the helper to the exact committed guard generation/revision + retained
  pair + fresh absence of an installation. Shared native release/runtime locks,
  positive systemd quiescence, rollback/path/symlink checks and anchored removal
  protect data; deletion errors are not silently accepted. No new user grants.
  Migration 3e189f465708 follows 2c078e3546f7, backfills latest historical uninstall
  unless later erased/currently installed, and refuses nonempty downgrade. The
  legacy baseline exclusion was corrected so this table appears only at its
  actual revision. No reset: database backup retained under
  /var/lib/3mm/update-helper/retained-data-20261025/3mm.db.
  Current immutable Pi release /opt/3mm/releases/retained-data-20261025-r2, still
  beta.57; previous application-removal-20261025 retained. Core PID 227674/helper
  227678; Agent 29317/Web 29319/Runtime 29335/relay 144368 unchanged, all active,
  NRestarts0. Identity/pairing/provisioning/review key/worker/environment preserved.
  The unused first candidate was removed after exact path/current checks.
  Verification: 88 Linux runtime/helper cases pass; initial 92 API/lifecycle/
  migration cases had 90 pass + baseline-precreation and synthetic-reinstall
  fixture failures. Production baseline and the fixture were corrected; all 9
  migration cases plus the corrected reinstall case pass in a separate frozen
  source/DB. Unchanged successful cases reused; candidate SHA pins checked.
  Frontend 33 component cases (4 new), TS and Vite pass. Real helper erased an
  owned test file with no package/installation remaining; final catalog/packages/
  data directories are absent, SQLite integrity and readiness pass. Mobile UI
  visually verified before/after cleanup; served frontend matches candidate.
  Terminal package/human permission remain available: first final check observed
  grant3 active but effective=false, while separate normal/mount-namespace
  read-only diagnostics confirmed its sealed grant/current local runtime. Later
  fresh HTTP observed grant4 effective=true and target console available=true.
  This task issued no approval/apply/regrant calls; cause of 3->4 is unproven.
  Do not claim grant3 was preserved or a permission repair was performed.
  No Terminal session opened. Optional Node/relay component/configuration kept;
  the removed probe application was the visible consumer test fixture.
  Evidence retained-data-{initial,core-candidate,core-installed,live,final,
  terminal-review,terminal-diagnostic,terminal-namespace,terminal-http}-20261025.json;
  session-probe-cleanup-20261025.json; common-sessions-retained-{runtime,final,
  corrections}-20261024.json. No full CI claim/commit/push/version/publication.
  Owner Ubuntu and /opt/3mm-dev untouched; own WSL test lab stopped at handoff.
  Old Extensions tabs need Ctrl+F5 for the new data cleanup section.

- **Failed application removal fixed and accepted on rasp-3mm, 2026-10-25.**
  Owner deferred Terminal work. Fleet 0.1.10 installation 2/ZIP
  b741c01ec89fda87f9674bbdbae768fc1f08925c21e473ca5d7db442c8a7c01b
  had recovery_required/active_version null. UI inferred installed from the
  version and wrongly attempted package deletion while the row referenced it.
  The generic fix uses installation-row existence, shows recovery state/removal,
  blocks activation while pending and refreshes after failed activation.
  DELETE now first obtains exact fenced helper quiescence, stays recovering
  across the removal gap, pins owner/state and checks outstanding jobs twice;
  no activation retry, authority restoration or forged external-outcome review.
  Unknown cleanup/jobs/rollback evidence stay protected. Unused application/UI
  package retirement also supports service-only/obsolete/missing/corrupt ZIPs
  without parsing their payload. Current/previous app, device and widget refs
  block deletion; strict managed identity/path/symlink guards remain. Upload,
  activation and asset validation are unchanged. No app-specific Core exception.
  Real Fleet was removed with one normal application DELETE, then normal package
  DELETE. No data-erasure call, direct SQL repair or filesystem bypass was used.
  A separate controlled missing-factory service-only package also failed startup,
  remained a visible failed first installation, uninstalled via normal DELETE,
  then its deliberately corrupted own archive retired normally. The entire
  fixture is removed. Core stayed PID 217947/start tick 8259010 through this
  regression. Fleet/fixture runtimes are inactive/PID0/empty cgroups; their
  installation/package rows are absent. Terminal grant revision 3 and permission,
  identity/pairing/provisioning/review key/environment and independent services
  remain preserved. No Terminal/Node/relay/network implementation changes here.
  Current Pi immutable release /opt/3mm/releases/application-removal-20261025,
  still beta.57; previous session-platform-startup-20261025 retained. Only two
  backend route files + prebuilt frontend changed. Core PID 217947; Agent 29317,
  Web 29319, Runtime 29335, helper 83457/relay 144368 unchanged. Owner Ubuntu and
  /opt/3mm-dev untouched; own test machine/proxies/WSL stopped.
  Verification: final 65 Linux lifecycle/authority cases (21 new), 20 package
  retirement cases, 29 frontend component cases (8 new), TS/Vite pass. Reused 36
  unchanged successful application-access/gateway/helper cases from initial
  100-case slice; its 2 obsolete DELETE expectations were corrected, not ignored.
  Candidate/current backend SHA match exact successful frozen inputs. No full
  release CI claim. Evidence fleet-removal-{core-candidate,core-installed,live,
  final}-20261025.json; application-removal-live-regression-20261025.json;
  common-sessions-{removal-final,packages-final}-20261024.json. No commit/push,
  branch/version/tag/publication. Reload an old Extensions browser tab (Ctrl+F5)
  for the new installed/recovery action logic.

- **Common boundary + real Node + local relay accepted, 2026-10-25.** The
  process/release values below are that acceptance snapshot, superseded by the
  removal fix above. This
  completes the owner's selected scope, not full M21, root host administration,
  public Cloud or installed remote Terminal UI acceptance. No further work is
  required for this bounded gate; do not automatically expand its scope.
  Core uses a trusted exact-source runtime directory with no ambiguity/fallback;
  current M20/UI/user/runtime checks continue during startup/output/operations.
  Optional Node TLS uses the existing Hub identity and exact registry wheel/cert;
  Node/worker and encrypted loopback relay have independent update boundaries.
  Read-only tracked-admin cleanup reconciles only exact failed owned sessions,
  with real OS proof and a barrier against late startup. Unknown local startup
  stays fenced until only the optional Node generation ends, followed by proof.
  Physical direct and relay independent-SDK probe sessions pass ready/delayed
  output before input, binary echo 1024, resize 99x31, DynamicUser UID 63972,
  denied private paths/IPv4/IPv6, scrubbed environment and normal OS cleanup.
  Relay drop, human revoke/403, service revoke/403, Node restart and revocation
  DURING cold startup all pass cleanup, explicit restoration/current review and
  fresh sessions without input replay. Startup revoke gets no opened/data and
  sends zero input; its unknown fence correctly returns 409 despite cgroup absence,
  then reconciles after Node-only restart. Actual TLS refuses missing Hub identity.
  Core stays PID 142048/start tick 5936021 through all faults/recovery and later
  independent Node/relay updates. Agent 29317, Web 29319, Runtime 29335 and helper
  83457 remain unchanged. Immutable Pi Core session-platform-startup-20261025,
  still beta.57; previous session-platform-20261025 retained. Measured Zero W cold
  worker startup was 37s: bounded worker/Node/link/Core/browser budgets are
  90/95/100/110/120s, with relay opaque read 120s. Only frontend opening changed;
  input/control/close remain 10s. Advertised expiry includes startup in total 900s.
  Actual Zero W is paired to Pi 192.168.1.88, not owner Ubuntu VM. Node build
  7715f8523542b15d77589c70db5e1e7eec49a650e11381b09398887e2df6ee12 (PID 28627),
  Agent 26ab24b4ad00a8347f94845cf22dbaabf7f9ed7deeb6784f2ae2904989f171d3
  (PID 26425), original helper 19277; no Core runs on Node. Relay build
  8826e3d91959a546cd1e4c2b08659a6d9f96cc13f8d8525704b4149487736498 (PID 144368)
  listens only 127.0.0.1:8899, fixed Node 192.168.1.81:8898, no TLS keys/Core data.
  Running Node/relay bytes live in their independent component service.pyz;
  optional-component source copies in the Core release are snapshots, not their
  running code. Use the reviewed component artifacts for updates, not stale
  rebuilds from a Core source snapshot; no Core restart is needed for them.
  Final identity/credential/provisioning/Hub pin checks pass. Terminal 1.0.3 exact
  ZIP/UI/native review, local service grant revision 3 and user 1 terminal_use are
  preserved. No local/Node workers remain. Own probe installation 3 is disabled
  and only its test user 1 session_use removed; Node/relay remain available.
  Verification: 214 Linux integration passes before the last advertised-expiry
  correction; final 39 browser covers that correction. Final 39 TLS/worker/support,
  51 packaging, 90 delivery, 32 credentials and 17 frontend pass; TS/Vite pass.
  Counts overlap; no full release CI claim. Compiled frontend matches the previous
  Pi files after asset-hash normalization except opening 10s->120s. Test-only
  trailing whitespace cleanup after the final TLS run changes no test behavior.
  Evidence: .runtime/dev-lab/evidence/session-platform-final-20261025.json,
  session-probe-{direct,relay,physical-*,fault-*,startup-revoke}-20261025.json,
  common-sessions-{integration-startup-final,browser-startup-expiry-final,
  tls-startup-cancel-final,packaging-health-final,delivery-credentials-final,
  credentials-shared}-20261024.json. See M21 plan section16/local trial guide.
  Own private machine 3mm-p6-20261024, browser proxies and test WSL 3mm-WP4-Test
  are stopped. Independent /opt/3mm-dev, owner Ubuntu, P2/network/roles untouched.
  No branch/commit/push/version/tag/publication. Known status-only finding:
  unresolved runtime sources can be labelled review_key_unavailable by the M20
  ValueError wrapper; the key is intact and must not be reset to repair a source.
- **Terminal local browser acceptance passes on Ubuntu VM and physical Pi 3B+.**
  Exact Terminal 1.0.3 ZIP remains
  9aefe11acfec58664883f91923f830817171a9853133a280315847e398d6ece9.
  VM installation 8/UI build 64e741b1bcba0c25aedc4e6ae5209bebbb2d8bead43b8d43601415210f90471a
  keeps native review 1045b4fd572c2c74cf201dbf65762188 and owner rights.
  VM local Core terminal-ui-snapshot-20261024 (still beta.56) fixes the shared
  UI trust snapshot; old method reproduces two failures, corrected group passes
  97 Linux tests. Installed prompt/commands/delayed output/resize/cleanup and the
  owner's fresh Chrome connection are confirmed. Its console slot is released.
  Pi helper first-install EROFS was fixed through safe instance-parent bootstrap
  and a narrow instances/journal write closure; 5 scoped Linux checks include a
  real systemd first-binding/immutable-path test. Normal recovery/activation
  succeeded without resetting authority or data. The live helper drop-in remains.
  Pi installation 1 is now active: optional local-session flag/socket enabled,
  first local review key explicitly provisioned and exact native/UI review
  166786acf71f4f32bc1ebe42fe6cc345 recorded. Pi compiled UI is
  bd8ed04ec090117cf1c8a82415b93df87e234d72e15f76d9d58ce1798021dc48;
  code review is /var/lib/3mm/core/authority-review/documents/terminal-1.0.3-20261024.md.
  Only session:console:open for its own dev_4f4d108bbdda46d8ae19951c353e5dfe,
  exact provider 1.0.3/write/resize/80x24, plus user 1 terminal_use, is approved.
  Missing human permission returns 403. Final service grant revision 3 is
  8656d5b62d8d2e686dd7354eddc032e3 and effective; no review-key recovery/reset.
  Real Pi output initially failed: legitimate current-authority checks queued
  behind resize/another check exceeded the pump's reused 1-second idle interval.
  Physical controlled contention reproduces a 1003 ms timeout without reading
  or sending output. The fix separates a bounded 5-second authority deadline
  from the 1-second poll cadence, still checks before/after reads and while
  reads/sends wait, and classifies authority timeouts without private log text.
  Two behavior regressions fail before the fix; the exact corrected output,
  Agent/UI/auth/session group passes 127 Linux tests (zero skips/failures).
  Pi now runs local immutable /opt/3mm/releases/terminal-authority-20261024,
  still beta.57; previous p2-recovery-20261024-full is retained. Only two Core
  source files and local release metadata differ; source hashes match tests.
  Core PID 112520, Agent 29317, Web 29319, Runtime 29335, helper 83457 are healthy.
  Installed Pi browser proof: prompt before input, pwd/id/printf, delayed output,
  dynamic UID 61502/scratch workspace, PTY 24x158 -> 23x116, private paths and
  release writes refused, IPv4/IPv6 socket creation refused (errno 97).
  Human and service revocation each close the idle session, with exact workers
  inactive/dead, successful exit and empty/absent cgroups. Rights were restored
  explicitly; fresh sessions have new IDs, and normal Disconnect also cleans up.
  After forced close the browser adapter intentionally fences the current page:
  Refresh access alone does not clear unconfirmed. After confirmed cleanup and
  restored rights, explicitly reload the page for a NEW session; never replay
  old input. Final browser verification logged out, console free, no workers.
  Identity, provisioning, network/role, independent worker binaries, exact ZIP/UI
  and other service processes are preserved; no Wi-Fi/AP operation or Zero W
  change. Environment backup: /var/lib/3mm/update-helper/terminal-sessions-20261024/3mm.env.before.
  Private test machine and 3mm-WP4-Test WSL are stopped. Before future private
  tests mask its outer Core/Web/Agent to avoid owner forwarded-port competition.
  Reused unchanged 41 frontend/TypeScript/compiler and private PTY/M20 evidence;
  the fresh 127-test run covers the new Core output change. This accepts only
  the restricted ephemeral local profile, not full M21/Node/Cloud or unrestricted
  host administration. Independent /opt/3mm-dev remains untouched.
  Evidence under .runtime/dev-lab/evidence/: terminal-installed-pi3-acceptance-20261024.json,
  terminal-pi3-native-review-20261024.json, terminal-pi3-rights-20261024.json,
  terminal-pi3-authority-contention-20261024.json, pi-output-timeout-fixed-20261024.json,
  terminal-pi3-output-installed-20261024.json, terminal-pi3-revocation-20261024.json,
  terminal-pi3-cleanup-{human,service,normal}-20261024.json. Earlier VM/helper
  evidence is retained. No commit, push, version bump, tag or publication.
- **Node OTA trust/bootstrap and helper crash correction is complete, 2026-10-24.**
  Installed `node-ota-20261024-node` on Zero W (bootstrap exit 0), still candidate
  0.3.0-beta.57. Shared exception/file definitions remove the module-launch import
  cycle; missing/invalid trust stays refused without crashing the service. Live
  missing-pin support/status probes and the subsequent explicit Hub pin kept the
  same helper PID, with zero restarts. The selected Hub key was verified through
  pinned SSH; root trust is bound to the current Node ID and stored mode 0600.
  A real Hub signature verifies on Zero W/OpenSSL; altering the signed request
  returns invalid_approval. Hub receives fresh matching support; Node is approved,
  Online and ready with unchanged provisioning hash. Linux targeted OTA: 183 passed.
  See the Node OTA section below for exact source/artifact evidence and limits.
  No official release installation through OTA, commit, push or publication.
- **P2 is complete and accepted by the owner, 2026-10-24.** The owner reports
  several successful variants, attributes the earlier portal-access problem to
  their own side and explicitly accepts P2 as ready. This closes the AP portal
  investigation and supersedes the earlier pending hardware acceptance items.
  Setup/pairing, the observed AP/DHCP/five-minute return, prior targeted checks
  and the owner's final trials form the acceptance record. The exact final
  scenario/device matrix was not enumerated; do not invent individual fault or
  per-device passes. The proposed two-device peer probe is no longer required
  and was not executed. The passive observer had already exited successfully.
  No further P2 action remains. This handoff changes documentation only.
- **The configured-device recovery/AP correction is installed on both Raspberry
  devices.** P2 acceptance used `p2-recovery-20261024-full` and
  `p2-recovery-20261024-node`; Zero W has since advanced to the Node OTA fix above.
  The candidate version is still 0.3.0-beta.57. Both P2 installers
  exited 0; no OS package upgrade or Wi-Fi/AP actuator was run. Provisioning
  file hashes, roles, device identities and active Wi-Fi profile UUIDs match
  the pre-upgrade baseline. Both approved devices are Online; Core and Agents
  are ready. See the recovery correction section below. The subsequent owner
  trials and explicit P2 acceptance close the portal investigation.
  No commit/push/publication. Browser visual review was not completed because
  Computer Use returned `app approval timed out`.
- **Owner setup and pairing are successful and independently observed.** The
  owner corrected the admin email to the agreed example account, completed setup
  on both devices and reported successful trials/pairing. Read-only checks show
  both devices provisioned, credential_available and Online with fresh heartbeats.
  Pi 3 is currently **Standalone**, Zero W is **Node**; both selected preserve
  networking. Core health/readiness and both Agent readiness endpoints pass.
  At that earlier observation setup-local/AP were inactive and the owner had
  tried only setup/pairing through the existing network. Later AP trials and the
  final owner acceptance above supersede that initial acceptance boundary.
  No fault or network mutation was performed by those read-only checks.
- **First Pi 3 login report diagnosed and verified.** After owner setup, Core,
  Agent, Web and Platform Runtime are active. The reported POST login 404 is
  `User not found`: the example email entered at login differs from the real
  administrator email chosen during setup. Login with the recorded account and
  the owner's prototype password returned 200, profile verified admin, and only
  the verification session was logged out. No code/account/password change.
  Evidence: `.runtime/dev-lab/evidence/p2-first-login-verified.json`. The frontend
  currently maps this credential 404 to a generic error message; routing itself
  is present. Node setup/radio acceptance is not rechecked by this diagnosis.
- **Fresh-device installation and owner setup/pairing are complete.** The
  owner reflashed both cards and supplied new console-verified SSH fingerprints.
  Both are reachable at their previous IPs with Python 3.13.5 and active
  NetworkManager. There was no installed 3mm on either fresh system. Separate
  local full/aarch64 and Node/ARMv6 bundles are installed and both r2 jobs exited 0.
  See the installation section below for the pre-setup baseline; owner setup and
  pairing have since completed; P2 is now accepted as recorded above.
- **P6 is complete in the agreed stabilization/acceptance scope.** No required
  P6 implementation or acceptance action remains. P2 real Wi-Fi/AP was deferred
  at the P6 gate and is now accepted by the owner. Independent M21 integration
  remains separate.
  Final source `52ab108b…`; production bytes match `c72a69fc…`. Composite evidence
  covers 6336 distinct successful Python cases and 495 frontend cases; three
  external Terminal/M21 cases are explicitly excluded, not counted as passes.
  See the P6 evidence section below for fixes, exact artifacts and limits.
  P6 evidence/state are retained. The private machine in `3mm-WP4-Test` was
  reused for isolated checks and is now stopped. Owner
  WSL stays on beta.56. At P6 completion ARM64 was beta.56 and temporary ARMv6
  acceptance restored beta.53; the owner has since reflashed both physical cards. M21 remains `m21-beta51`, 22 dirty status lines.
  No commit, push, version bump, tag, release or permanent fleet rollout.
- **P3a-P3c are complete locally in the selected stabilization scope.** Core
  administration survives optional startup failure and SDK connection saturation.
  Legacy in-Core Python loading and its direct lifecycle/frontend paths are
  retired. Bulgarian is a separate manifest-v2 language extension, with English
  available for recovery.
- P3c fixes one current Core/SDK transport contract: signed discovery, bounded
  framing/connections, absolute deadlines, fixed reasons and current generation
  metadata. Existing current operation admission/revocation remains mandatory;
  discovery grants no rights. Compatibility-only scheduled jobs are retired,
  with historical records and outcome resolution preserved.
- **P4a is complete locally**, with a separate stdlib-only Runtime for signed
  discovery and scoped identity read, private Core admission, dedicated OS
  principal, immutable artifact, own environment and independent update/rollback.
  Real process and distinct-UID tests preserve Core administration/PID/source.
  The final service-directory fix also passed a real transient systemd check.
- **P4b signed transport is complete locally:** all 25 current SDK operations use
  one Runtime endpoint/private ABI 2; Core's old public SDK listener and its
  configuration are removed. Relational boot passes the original accepted Unix
  socket with SCM_RIGHTS; Core reads its actual SO_PEERCRED. No forwarded PID/UID
  substitutes for credentials. Current domain authority adapters stay in Core.
- **P4c application-host packaging is complete locally.** Native immutable host
  artifact with its own eight locked dependencies/venv, shared read-only releases
  and independent per-instance current/previous pointers. One host can update or
  roll back while Core, Platform Runtime and another host keep the same processes.
  Existing wheels, active metadata and authority decisions are not replaced.
- **P4d1 public-response execution is complete locally.** Core's old public
  listener/configuration is removed. Runtime owns the bounded public socket and
  response waiting, using one already connected FD from Core. Core selects and
  sends the admitted invocation, then validates the original signed result in a
  separate short request. No app key, DB access or replay capability leaves Core.
- **P4d2 durable event delivery is complete locally.** Runtime pulls one current
  admitted invocation and waits on its connected socket. Core matches/enqueues,
  records attempt ownership before send and commits the signed result exactly
  once. The old Core event executor/retry task is removed; admin drain now queues
  pending work. Additive migration `1bf67d2435e6`, no reset or grant backfill.
- **P4d3 connector network execution is complete locally.** Core commits current
  admission, sends one selected plan to a distinct network worker and hands Runtime
  the connected FD. Core does not wait for HTTP. Signed result-only completion,
  durable CAS and duplicate receipts prevent blind replay after failures. Runtime
  keeps its closed network namespace. Additive migration `2c078e3546f7`; no reset.
- **P4d4 admin operational-status response I/O is complete locally.** Core
  reserves a response-only Runtime slot, admits/sends the signed host query once
  and passes a write-half-closed FD. HTTP waits asynchronously without a borrowed
  Core thread or DB transaction; current signed results are verified in Core.
  Unavailable/changed/inactive telemetry is explicit. No SDK/schema/permission change.
- **P4d5 admin health response I/O is complete locally.** The declared internal
  query uses the existing response-only Runtime relay. Core preserves package/UI
  trust and original HMAC/schema checks, with fresh admission after reservation
  and an atomic lifecycle/package fence before writing `health_checked_at`.
  Health obtains no relational host-metadata/SQL ticket; a real prepared host
  remains observable after service resource revocation without acquiring SQL rights.
- **P4 is complete locally in the agreed extraction/independent-delivery scope.**
  Human/kiosk operations and peer bootstrap/report callbacks use the existing
  response-only Runtime relay. Core retains fresh policy, signing, relational
  admission and signed completion. Agent, public HTTP and isolated session workers
  have native immutable artifacts, own venvs/pins/journals and independent updates.
  Real Linux process, distinct-principal and owned systemd sandbox checks pass.
  The scoped installed/clean-setup/ARM/resource/cold-service-boot acceptance is
  now complete in P6, with the limits below. P5 is also complete locally.
- P2a/P2b implementation and prior local evidence remain intact; P2 is accepted
  by the owner. P6 added scoped installer/device faults below. Debug UI is
  complete in P5; independent process/release boundaries are complete in P4.
  [Single action plan](CORE_STABILIZATION_ACTION_PLAN.md); architecture detail is
  read on demand. M21 stays separate.
- P0 adds `tools/dev_lab.py` and its isolation/provenance checks, plus an optional
  isolated test DB path in `backend/tests/conftest.py`. No application runtime code
  was changed in P0 and no installed services, networks, commit or publication.
- Workflow, context and check-selection package is applied in the laptop checkout
  and verified against the prepared package; it is not committed.
- First Core simplification is complete in the worktree: command-schema
  canonicalization has one implementation shared by context, policy and provider
  comparison. P0 does not perform additional application runtime cleanup.
- M21 was preserved separately during P0-P6. The owner now authorized Terminal
  continuation above. Preserve the independent /opt/3mm-dev checkout; a local
  Terminal correction does not close remote/cloud or the complete M21 milestone.
- Device access is authorized; read-only access checks succeeded (see below).
  No commit, push, version bump, tag or publication is requested. P6's reversible
  device acceptance is documented below; it leaves the owner fleet versions intact.

## Terminal local acceptance and Raspberry installation, 2026-10-24

Terminal's HTTP ID correction replaces secure-context-only randomUUID with
16 cryptographic bytes for open/resize IDs; unavailable randomness refuses
before dispatch. No transport, permission or SDK change or input retry.
Reference: https://w3c.github.io/webcrypto/#crypto-interface . The three regressions
failed first; 41 frontend tests/TypeScript and actual Core package/UI compilation
pass. Existing prepared dist ZIPs and wheel/descriptor bytes remain unchanged.
Candidate: .runtime/terminal-http-20261024-r2/3mm-terminal-1.0.3-http-candidate.zip.
ZIP SHA 9aefe11acfec58664883f91923f830817171a9853133a280315847e398d6ece9;
wheel SHA 5b490d9fe39845c16c2cf9eb1f13069c98eb03ed23ac042dd2da38cd272d0900.
Development compiled UI SHA is 391ce2052cf995520c8f367915a4bafdf74feecdc9cd7778cfe42ffb7f4a0ee4;
actual VM build is separately verified/pinned at
64e741b1bcba0c25aedc4e6ae5209bebbb2d8bead43b8d43601415210f90471a.

The earlier private-systemd PTY proof used frozen Core source
9a01e75c539cfc8c5a3c36d685e0b049667c236b024779510cee4c09dd707678:
one outer Root test including two nested real M20 human/service revocation cases,
prompt, delayed output, resize, denied private paths/network and owned cleanup.
That fixture pass remains distinct from the later installed Terminal Vue proof.

Installed Ubuntu beta.56 lacked the already-checked UI snapshot correction.
Old verify_ui nests readers while a SQLite writer can hold a pending commit.
The exact old method reproduces two failures; the corrected four direct test
modules pass 97 Linux tests, including DELETE/WAL writer and exact-proof denials.
The local Core candidate changes application_browser_sessions.py,
application_authority_management.py and compiled_ui.py only, plus honest local
release metadata. Native review, ZIP/UI build, service/human grants and keys are
retained. Actual IAB prompt/input/delayed output/resize/close and owner Chrome
reconnection now pass. The single console reservation explains the overlapping
owner 403. A separate busy/error presentation improvement remains a later task;
no extra console slot, authority bypass or automatic input replay was introduced.

Rollout safety lesson: starting the outer test WSL also started its Core.
It stole 8887 during owner Core restart, yielding a false generic ready response.
That attempt was rejected and rolled back; the test WSL was stopped. Final
activation additionally pins listener PID/current cwd and checks the exact
application, UI build, current grants and target. Later helper tests runtime-mask
only the test WSL's outer Core/Web/Agent before starting the private nspawn guest.
All private tests are now stopped. Owner browser session was not closed; only our
verification session was disconnected/logged out and our IAB tab closed.

The Pi first-install error is separate: new instance pointer/journal paths were
outside the hardened helper's writable closure. New bootstrap prepares a safe,
owned, non-writable-by-others instances parent even when a default already exists.
The helper unit adds only that pointer subtree and the host-update StateDirectory;
default/release binaries remain EROFS in the actual systemd test. Four directory
guards plus that real first-bind namespace case pass (5 tests). The initial broad
host-suite harness hit temp-parent ownership/PrivateTmp/report-output issues;
that invocation is not a passed full host-update suite or a new P5/P6 total.
Unchanged prior host-update evidence remains separate.

Live rasp-3mm: package is the same 1.0.3 SHA, instance
978e34d8736805f669216c15. Existing metadata guard/revisions were valid; no SQL
repair/key reset was used. The root drop-in
/etc/systemd/system/3mm-update-helper.service.d/application-host-binding.conf
plus prepared pointer parent implements the tested writable closure. Only helper
restarted. Existing AP journal phase inactive was checked against recovery code,
which skips it. Normal API lifecycle recovery proves quiescence, then activation
succeeds and explicit disable leaves 1.0.3 installed with error null/data retained.
Core/Agent/Runtime, host binary hashes and identity/provisioning/environment are
unchanged. Optional local runtime, native/UI review and resource/human consent
are still separate Pi gates. No Raspberry session or Node/Cloud path is claimed.

## Node OTA trust and helper correction, 2026-10-24

The owner authorized the separate Node OTA finding after P2 acceptance. Zero W
had no root-pinned Hub key and its helper had 432 automatic restarts; Agent/role
were still healthy. The actual service uses `python -m`: the helper defined
NodeUpdateError in its launch namespace while the trust verifier imported a
second helper module and raised a different class. The intended missing-pin
catch and outer RPC catch therefore missed it. A regression loading the helper
in a second namespace reproduced both missing/invalid-pin failures.

- `node_update_common.py` owns the shared error and bounded root-file checks;
  helper and verifier import it without a cycle. AST comparison proves those
  checks/class definitions are unchanged. No unsigned fallback, trust on first
  use, arbitrary root path/command or changed wire/schema contract.
- The ARMv6 builder and archive admission require the shared module. The new
  local Node archive differs from the installed P2 Node payload only in
  helper/trust/common; existing native wheels and all Agent/setup/network bytes
  are retained. Bootstrap kept the role and pairing and changed no Wi-Fi/OS
  packages. The old restart loop was paused during environment preparation;
  the installer started the corrected service. The Hub was not redeployed.
- The Hub public key was independently read through the owner-confirmed SSH
  host key and loopback Core API, then compared during the existing explicit
  root bootstrap on Zero W. Root-private 0600 trust binds that key to the known
  Node identity. The runbook now uses the Core origin on port 8887, rather than
  the frontend port. Fresh cards still need explicit root trust after pairing;
  reassignment/key rotation never silently replaces an existing pin.

Verification: Linux/Python 3.14.4, frozen source
`9a01e75c539cfc8c5a3c36d685e0b049667c236b024779510cee4c09dd707678`, dependency digest
`157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`:
**183 passed, zero skips**, covering helper/trust, real OpenSSL, signing/denials,
Agent RPC/execution/transport, Hub routes/approval/delivery/catalog, Node build,
installer/rollback and detached apply worker. The two new launch-namespace cases
first failed on source 13a5a10c… and pass after the correction. No frontend or full
CI run was needed/claimed; this work does not reopen accepted P2/P6 or M21.

Live ARMv6/Python 3.13.5:
- immutable `node-ota-20261024-node` bootstrap exited 0; archive SHA
  `84adf7e2c9b6ae704a9d01022998f72f13d12da71a45e40b4202d843ebbe41cf`.
  Local folder `.runtime/node-ota-fix-20261024/`, includes_working_tree=true.
- Before pinning: three support requests with null trust, a refused arbitrary
  action and a successful status response kept helper PID 19277 / NRestarts 0.
- After pinning: the same process reports the verified key and current Node ID;
  Agent is ready and provisioning SHA matches the before snapshot. Hub sees the
  matching fresh reported-state, Node Online and its original approval time.
- A short-lived test message signed on the selected Hub verifies with the real
  Node/OpenSSL verifier; a changed release field is rejected as invalid_approval.
  It did not stage an archive, create an update operation or schedule installation.

Evidence under ignored `.runtime/dev-lab/evidence/`: `node-ota-before.json`,
`node-ota-reproduction.{json,xml}`, `node-ota-fixed.{json,xml}`,
`node-ota-boundary-equivalence.json`, `node-ota-payload-diff.json`,
`node-ota-bundle.json`, install start/observe receipts, SSH-verified public-key
record and `node-ota-live-{missing,pin,signature,hub}.json`.
No private key/session/signature material is in tracked docs. Normal verification
login was logged out. A full official-release OTA installation remains for the
publication gate; the unpublished working candidate is not advertised as an
official OTA payload, and the official-metadata admission rule is unchanged.
No commit/push/version bump/tag/publication or independent M21 change.

## Configured-device recovery/AP correction, 2026-10-24

**Closed by owner acceptance.** After the investigations below, the owner
reported several successful variants, confirmed that the portal-access issue
was on their own side and explicitly accepted P2 as ready. No extra product fix
or two-device peer probe was needed for that closure. The final variants were
not individually enumerated. The following diagnostics retain their original
scope and are not a new exhaustive hardware test claim.

Subsequent owner trial: AP association/DHCP and expiry return are corroborated by
`p2-ap-owner-portal-failure.json` and `p2-ap-owner-network-path.json`. The portal
failed at all three attempted addresses, with no AP client HTTP logged. Current
listener and LAN checks pass. A read-only observer records bounded TCP/ARP metadata
and GET status, without payloads or codes; its receipt is `p2-ap-observer-start.json`.
The owner repeated with explicit HTTP and mobile data disabled and reported
failure again. Evidence `p2-ap-owner-repeat.json`: the observer spans almost the
entire AP interval, 288 self-HTTP 200 checks (loopback/AP IP), bidirectional ARP,
zero captured TCP on 80/8895; the AP is now inactive. No packet payload was stored.
Observer exited successfully. These are server self-checks, not external portal
acceptance; traffic on other ports was outside the observer filter.

A root diagnostic client is prepared locally in `.runtime/p2-ap-peer-probe.py`:
Zero W would join a two-minute Pi 3 AP via a temporary non-autoconnect profile,
perform only public HTTP GET/denial checks and restore its original UUID. An
independent restore timer is required before adding/changing the profile, with
a separate worker runtime limit. Five isolated stdlib Linux guard tests passed
(timer refusal, activation failure, normal restore, preserving an independent
connection, cleanup after restore failure). Preflight records both roles, device
IDs, provisioning hashes and original network UUIDs. Plan/source/test hashes:
`p2-ap-peer-plan.json`, baseline `p2-ap-peer-preflight.json`. No live peer probe or
product-code change was run during that investigation. The proposed peer test
is now canceled as unnecessary following explicit owner acceptance of P2.

The owner reported Settings -> Open local recovery failing and requested AP and
an honest automatic-recovery control. Read-only inspection found provisioning
read-only inside the Core service namespace. Issuing the short-lived setup code
therefore fails before scheduling. The update helper also lacked the network
backend EnvironmentFile. No live setup POST was executed: automatic approval
review rejected the diagnostic actuator because the only access is Wi-Fi.
The owner cannot provide Ethernet. At that handoff no agent-initiated AP trial
had been approved; the owner subsequently performed the manual trial above.

- Core now has a scoped writable provisioning directory. The helper and its LAN
  recovery worker inherit the installed backend configuration. Setup links use
  the device hostname rather than loopback. Existing protected LAN setup remains
  a separate action from the new manual temporary AP action.
- The AP worker uses a root-owned UUID journal, the same Wi-Fi transaction lock,
  a non-autoconnect profile and an independent systemd expiry scheduled before
  radio mutation. It restores the original connection when available; a newly
  committed Wi-Fi connection wins. Stale stop timers cannot close a later AP.
  Pending Wi-Fi is rolled back/rebased before AP deletion; startup recovery is
  independent of the browser/Core. Roles, account and pairing are not reset.
- AP admission is administrator-only with strict bounded RPC fields. Core does
  not obtain arbitrary root commands. The normal UI requests five minutes,
  shows join instructions with the temporary capability in a URL fragment, and
  offers early stop. The minimal Node includes the same root CLI controller;
  it does not acquire a Core Settings UI.
- The checkbox is shown only when automatic recovery is available for saved
  3mm-managed Wi-Fi. Preserve networking shows a clear effective-off message.
  A stored enabled policy does not mean it was running on these preserve devices.

Verification: Linux/Python 3.14.4, frozen source
`77f65092d8ab730429f299da72a2fdcd59fa267887338fa7523f83345dd6074a`:
144 targeted AP/recovery/helper/API/service/Node packaging cases and 52 direct
NetworkManager/transaction consumers passed, zero skips, disjoint groups.
Dependency freeze remains `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`.
A further 26 service-hardening template cases passed after updating the two
existing writable-path expectations to the intended permission fix. Their source
is `de7cf408a8f1f9cdfb0f194c31bd1248ad6d18c1c484a6374ca65a8f2f1b8b3a`;
archive comparison proves only `test_systemd_templates.py` differs from 77f65092,
with every runtime input unchanged. Total: 222 distinct Python passes. The original
196 cases and deployed artifact provenance remain valid without another rollout.
Six relevant Vue cases, TypeScript and production build passed. In the private
P6 systemd machine a disposable store reproduces EROFS with ProtectSystem=strict
and successfully issues/validates a code after the scoped writable path is added.
It does not use real provisioning or radios. This is targeted evidence, not a
new full P6/CI pass. At that verification point physical radio acceptance was
open; the next observed trial covered Pi 3 association/DHCP/return. The owner's
later successful variants and explicit acceptance close P2; no unenumerated
scenario is relabeled as an independently observed pass.

Local full archive SHA `e8a202d4e3bbfb70ae934f3a11e971b12354bd08caaeafd36692787426869f5c`;
Node SHA `d7513999b41b6683a61c5a4908072081d4b8b38171f4029cddc42ab25726ba69`.
Folder `.runtime/p2-recovery-install-20261024/` and sibling ZIP contain separate
verified targets, existing native Node wheels, rebuilt frontend and immutable
install/health/rollback. Existing configured state was checked before installation;
no AP journal, pending Wi-Fi or active setup existed. No APT/NM restart was used.
After installation the real Core namespace reports provisioning **rw**; installed
frontend hashes match the build. Status GET exposes `wlan0`, AP inactive and
automatic_setup_available=false. Only the verification login session was logged out.

Evidence: `.runtime/dev-lab/evidence/p2-recovery-{final,network-consumers}.{json,xml}`,
`p2-recovery-service-hardening-final.{json,xml}`,
`p2-recovery-final-source-equivalence.json`, `p2-recovery-systemd-permissions.json`,
`p2-recovery-bundle.json`, per-device
before/start/after JSON and `p2-recovery-installed-final.json`.
Browser layout review remains unperformed (`Computer Use app approval timed out`).
A separate pre-existing Node OTA issue was observed during this AP correction:
missing pinned Hub trust caused helper exits. It was unchanged in the P2 work
and has now been fixed in the separately authorized Node OTA section above.

## Owner setup/pairing observation, 2026-10-24

Owner reported completing setup and pairing on both fresh devices, and later
explicitly clarified this used the existing network; the separate AP/rollback/
outage/reboot scenarios were not tried. The administrator email was corrected
to the agreed prototype example. Login with
that account succeeds. The verification session alone was logged out.

- Authenticated Core device list: two approved, non-revoked devices, both Online
  with recent heartbeats and inventories. Core /health is ok and /ready is ready.
- Pi 3: snapshot provisioned/standalone/preserve, Agent identity
  `dev_4f4d108bbdda46d8ae19951c353e5dfe`; Core, Agent and Platform Runtime active.
- Zero W: snapshot provisioned/node/preserve, Agent identity
  `dev_a5b5bbfb25c94f299f31be8eaab381ef`, saved endpoint
  `http://rasp-3mm.local`. Agent active/ready; Core/Runtime inactive as expected
  for the minimal Node. Both Agents report credential_available.
- Local setup and AP units are inactive on both. Persistent roles match the
  running Agent roles. Existing network selection is preserve on both; that
  current state does not prove past AP/client switching or rollback trials.
- Evidence: `.runtime/dev-lab/evidence/p2-owner-paired-hub-raw.json` and
  `p2-owner-paired-devices.json`. These are read-only observations plus a normal
  login/logout, not replayed configure, radio failure injection or restart.
- Owner clarified: setup and pairing through the existing network only. Accept
  that concrete path, corroborated by the read-only observations. AP association/
  DHCP, wrong-password rollback, Wi-Fi outage/reconnect and reboot are untested
  physical P2 scenarios, not passes. This observation did not mutate runtime.
  The configured-device correction adds a bounded manual AP path without
  clearing the accepted pairing. Later owner trials and final P2 acceptance are
  recorded above; no further peer trial is required.

## Current fresh Raspberry local installation, 2026-10-24

The owner prepared new Linux cards and asked how to install the unpublished
working-tree version. They supplied fresh ED25519 fingerprints for Pi 3B+ at
192.168.1.88 and Zero W at 192.168.1.81. Explicit-key PuTTY probes confirmed
models/architectures, Python 3.13.5, active NetworkManager, empty 3mm installation
and about 25 GB free on each. Both currently use wlan0; no Ethernet link on Pi 3.
Trusted keys are in private Git metadata; global known_hosts is unchanged.

- Current delivery folder `.runtime/p2-local-install-20261024-r2/` and sibling ZIP
  contain `rasp-3mm/` full/aarch64 and `rasp-3mmw/` minimal Node/ARMv6.
  Local release IDs are `p2-local-20261024-full` and `p2-local-20261024-node`.
  Version metadata remains the existing working candidate 0.3.0-beta.57.
- Full archive SHA `353adb763e1daac223d75f2888a78c9c3da98d1bc1f9c19a901ac4d008120231`;
  Node archive SHA `a750263cbcd811d16990a17e155b6648974d0afa6cb47e73195dd99b3b55cb0f`.
  Payloads derive from accepted P6 archives e770a1ac… and d627956b…. All 1042/153
  non-metadata member bytes are retained, including prebuilt frontend and Node
  wheels. Only full architecture labeling and local release IDs changed. One
  shipped non-runtime WP4 test fixture differs from the later laptop fixture;
  the laptop fixture was separately verified against final accepted source
  52ab108b…. Runtime inputs match; no new production source/version change.
- The ignored `install.sh` entrypoints verify file hashes and target platform,
  require active NetworkManager, stage private root-owned copies, then start
  detached systemd jobs. Revision 2 explicitly uses umask 0022, matching the
  normal bootstrap. Existing immutable installer bytes are unchanged.
  APT runs in the job; full also needs pip/npm Internet. Selected network backend
  is network-manager. Source transfer requires no Git checkout or publication.
- Verification: all Bash syntax and bundle hashes passed in Linux; both wrong
  architecture attempts were refused before any target/service mutation. The
  same checks passed again on the matching physical target before job launch.
  P6 broad evidence is reused for unchanged production inputs.
- Each current copied bundle is `/home/raspberry/3mm-p2-install-20261024-r2`. Job pointers are
  `/var/tmp/3mm-p2-last-unit` and `/var/tmp/3mm-p2-last-stage`; `result.exit` inside
  the stage records completion. Current retry units: full
  `3mm-local-p2-3mm-p2-full-byv3eh`, Node `3mm-local-p2-3mm-p2-node-rfbrcr`.
  Observe before replaying installation.
  Both r2 receipts are 0. Their current pointers and metadata profiles match the
  intended full/aarch64 and Node/ARMv6 targets. Setup-local/network-helper are
  active and AP remains inactive. Windows LAN requests to /health and /ready
  return 200, public status shows setup with role null, and protected capabilities
  returns 401 without a console capability. Both wlan0 links remain connected.
  Node has no Core DB or SQLAlchemy. Exact native Agent IDs and final checks are
  in `.runtime/dev-lab/evidence/p2-local-installed-final.json`. This verifies
  installation/initial portal readiness, not completed role/admin setup or radio
  AP/DHCP/rollback acceptance.
- The first local launcher incorrectly set umask 0077 for the immutable installer.
  Both attempts failed when the distinct Agent principal could not execute its
  fresh venv. Their result.exit values are 1; neither is a successful install.
  Main installer rollback removed the incomplete Core/Node release and restored
  configuration. Two remaining empty root-owned `/opt/3mm-agent{,/releases}`
  directories had mode 0700. After verifying no current pointer, no active
  Core/Agent and an empty releases directory, only those two directories were
  restored to 0755. No recursive permission change or data reset was used.
  The r2 wrapper uses 0022; app archive bytes/hashes remain unchanged. Old ZIP is
  named `p2-local-install-20261024-obsolete-umask.zip` and is diagnostic only.
  Successful completion evidence must come from r2, not the superseded failures.
- Default setup URLs are `http://192.168.1.88:8895/setup` and
  `http://192.168.1.81:8895/setup`. Console-issued capability is still required.
  Role/admin/network configuration is not automatically submitted; no Node Core
  login is promised. Actual AP/DHCP/rollback acceptance remains a later live step.

## P2 radio test preparation, 2026-10-24

Before reflashing, the owner asked how to try P2 Wi-Fi/AP on both Raspberry
devices. The following was read-only readiness against the old cards; current
fresh-device installation is recorded above. Real P2 radio acceptance remains open.

- Live inventory: `rasp-3mm` is Pi 3B+ Rev 1.4, aarch64, Debian 13/Trixie,
  beta.56; `rasp-3mmw` is Zero W Rev 1.1, ARMv6, Raspbian 13/Trixie, beta.53.
  NetworkManager 1.52.1 is active on both and reports AP support for wlan0.
  Driver is brcmfmac; both SSH return routes currently use wlan0. Pi 3 eth0
  exists but has no link. No service or network profile was changed.
- An OS reinstall is not required for initial checks. For repeatable first-boot
  AP acceptance prefer spare microSD cards, retaining the current cards intact:
  Raspberry Pi OS Lite/Trixie 64-bit on Pi 3B+, 32-bit on original Zero W.
  Initial pair is full Hub on Pi 3B+, minimal Node on Zero W; Standalone is a
  separate fresh-state case on the full-capable Pi 3. Minimal Node cannot be
  promoted to Hub by changing only its selected role.
- Before a live radio transition provide a separate management path: Ethernet
  on Pi 3, USB-Ethernet/OTG or local console on Zero W. A laptop/phone joins the
  setup AP and a 2.4 GHz test network is used for client/reconnect trials.
- Deploy the accepted working-tree candidate with the network-manager backend
  for managed Wi-Fi/AP; do not mistake the current fleet beta.56/beta.53 or the
  loopback VM for the actual radio candidate. Preserve old OS profiles. The
  host-managed path remains a separate keep-existing-network acceptance case.
- Planned cases, one device at a time: existing-network preservation; fresh
  unprovisioned AP (SSID `3mm Setup XXXX`), DHCP and console-capability protected
  setup; AP-to-client connection with selected role; bad password/unconfirmed
  transaction rollback; runtime link loss/reconnect without role/identity reset;
  reboot with committed state preserved. Lost-response recovery is reconciled
  rather than blindly replaying configure. Previous connectivity must remain
  physically available for rollback. A healthy configured Wi-Fi adapter is not
  forcibly taken for AP; first-boot AP requires prepared unprovisioned state and
  an available adapter. Actual AP/DHCP/address/driver behavior is still untested.
- Read-only inventory evidence is in
  `.runtime/dev-lab/evidence/p2-radio-{rasp-3mm,rasp-3mmw}-readonly.json`;
  privileged tool/package observations are separate `-tools.json` files.
  nmcli reported AP support, not a successful live AP/DHCP trial.

## Current manual VM review, 2026-10-24

The owner requested a practical VM trial, allowing a clean VM if needed. Reuse
of the existing clean P6 machine is sufficient for the first UI/debug/resilience
review. It is already configured **Standalone/local, host-managed networking**;
this is not an unconfigured first-boot wizard. Initial setup/Hub/Node trials
should use separate fresh synthetic state, preserving this accepted baseline.
P2 actual Wi-Fi/AP and independent M21 integration remain outside this review.

- Machine `/var/lib/machines/3mm-p6-20261024` in `3mm-WP4-Test` is running with
  the accepted `p6-full-warm-20261024` artifact. Its network remains private
  loopback; standard systemd socket proxies expose only outer loopback ports.
- Browser entry: `http://127.0.0.1:18080/user/login`; Settings → Diagnostics.
  The isolated Core is `http://127.0.0.1:18887`. The setup portal is not exposed
  or reset; the existing synthetic lab administrator is retained.
- Ignored local launcher: `.runtime/P6Demo.ps1` accepts `start`, `status`, `stop`,
  `runtime-off`, `runtime-on`. From the repository, use
  `& .\.runtime\P6Demo.ps1 start` (change the final action as needed).
  Stop powers off only this machine and releases its owned hidden WSL keepalive.
  Start recreates transient units/proxies and browser overrides after reboot.
- WSL systemd services alone did not keep the distribution alive when the
  starter exited. The launcher now starts an owned hidden WSL client, with a
  guarded `/run` PID/start-time record and a stop signal; repeated starts retain
  one keeper. No Windows firewall/portproxy or host network profile changes.
- Demo-only transient web bind mount supplies backend port 18887 without editing
  immutable frontend files. A transient Core environment file allows only the
  two loopback browser origins on 18080. Both stay inside this private machine.
- New evidence: actual Windows-loopback UI/config/API, browser admin login,
  Standalone device Online and live diagnostics. Deliberate Runtime stop showed
  Runtime Unavailable while Core stayed Ready; admin API replied in 49 ms and
  Core PID 247 stayed the same through stop/restore. Runtime is running again.
  `.runtime/dev-lab/evidence/p6-browser-demo.json` records the bounded trial;
  accepted P6 broad suites are reused unchanged, not rerun or relabeled.
- Primary Ubuntu remains beta.56 with Core/Agent active, M21 remains
  `m21-beta51` with 22 dirty status lines. No hardware deployment, source runtime
  change, commit, version bump or publication is part of this browser setup.

## P6 acceptance evidence, 2026-10-24

The agreed software acceptance is complete. This is composite integration with
explicit unchanged-input reuse, not a single tagged/full-CI run. The initial
interrupted run, superseded failures and successful case evidence remain intact.
`p6-acceptance-summary.json` and `p6-final-coverage.json` under
`.runtime/dev-lab/evidence/` account for the current collection and exclusions.

| Suite | Successful distinct cases | Explicit exclusions |
| --- | ---: | ---: |
| Default Python collection | 5823 | 2 external M20/M21 session-provider cases |
| Deployment and application SDK | 481 | 1 external Terminal sandbox case |
| Tooling (pytest includes the 25 unittest cases) | 32 | 0 |
| Frontend | 495 | 0 |

Python total: **6336**, without counting repeated hardware/root cases twice.
Frontend type-check/production build passed; frontend inputs are unchanged.
Linux gates use isolated source/data on x86_64/CPython 3.14.4, a fresh Ubuntu
24.04 systemd machine/CPython 3.12.3, plus real aarch64 and ARMv6/CPython 3.13.5.
The reused main environment has freeze SHA `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`;
all component-lock versions were checked. Per-run source/dependency hashes,
commands, timings and JUnit remain in the JSON/XML evidence. Generated ZIP
parameter IDs were reconciled only with unchanged test bytes and a complete
matching per-function case count. Skips never become passes.

Real blockers repaired:

- Node wheel preparation uses the same dependency lock as installation; the
  full builder environment also applies the component constraints. Fresh offline
  installation no longer selects a different certifi version.
- Validated archive members are read with their bounded declared size, rather
  than allocating a 128 MiB buffer per small file. This removed a real ARMv6
  MemoryError. Native Agent startup/component-info has a 90 s ARMv6 budget;
  ordinary transport/admin deadlines were not widened.
- Trusted local bootstrap establishes the Core installation pin before Agent
  startup. Installer/transient activation receive the Core environment/key
  without putting secrets in argv. Real signed local publication was verified.
- A separate committed `setup-activation.json` preserves activation intent until
  readiness. The role/network transaction remains visible to compatible Agents.
  SIGKILL restores protected local setup through systemd OnFailure; a new console
  capability can `/finish` the same intent without replaying configuration,
  changing role, recreating an administrator or restarting a healthy Core.
- FastAPI included-router dependency/schema compilation happens before readiness.
  A real ARM64 first-admin timeout exposed this lazy startup cost. Warmup runs
  no dependencies/handlers and caches no authority decision. The regression,
  76 direct Main-consumer cases, 102 process cases plus 6 distinct-UID cases,
  and all 4 ARM64 Core/Runtime cases pass with the original response deadlines.

Fixture repairs follow current contracts: current Alembic head with unchanged
history guards, identical ZIP bytes for repeated inspection, fresh signed frame
IDs with unchanged business idempotency, fixed SDK error reasons, and isolated
sockets selected before preparation. The CLI harness accommodates its existing
180 s helper budget; production worker/IPC deadlines are unchanged. Actual
PrivateTmp hardening tests run source outside protected home/tmp paths.

Final source snapshot:
`52ab108bd20395e62226ce55578c2ed44e171e7341f90433f057886d2b9ff5a8`.
Production bytes match snapshot
`c72a69fccd7150a79edb4602159fa1d48c4bcb4ef47b57a94805caae68967cef`;
later edits only repair the WP4 acceptance fixture. AST, shell syntax and scoped
whitespace checks pass; the Git index remains empty. The checkout already had 351 dirty
status lines at P6 start; P6 did not stage unrelated user work.

| Local artifact | Archive SHA-256 |
| --- | --- |
| `p6-full-warm-20261024.tar.gz` | `e770a1ace5899a7e03edf6850f2e5b934a639927ddfb385f164b6bd9afec3471` |
| ARMv6 Node, working-tree candidate | `d627956beaa65dc49be71afaea766f3f2ab1797e3ed46a4a2ffbd515eb5dd3a5` |

Native Agent build/archive identities are in
`p6-aarch64-handoff-evidence.json` and `p6-armv6l-handoff-evidence.json`.
The Node install's native Agent is a separately identified build, recorded in
`p6-node-cgroup-observation.json`; do not relabel it as the isolated probe bytes.

Clean systemd setup passed Standalone/local, Hub/preserve and Node/preserve with
no Wi-Fi interface/AP requirement. Runtime absence, hang, kill, pressure, A→B→A
and failed-candidate rollback preserved Core administration/PID/generation/code.
Installed first-admin responses were 25/20 ms with Runtime present/absent.
Core-stopped export worked from the independent Agent environment without
Core/SQLAlchemy. After poweroff/new init, Standalone role, snapshot, device ID,
release and pins were unchanged; first admin was 16 ms. Actual OOM scores were
Core -500, Runtime +300. This is a private machine cold service boot on a shared
WSL kernel, not a hardware power-cut/kernel reboot claim.

| Measured idle fixture (20 s) | Max RSS, KiB | CPU seconds |
| --- | ---: | ---: |
| ARM64 Core HTTP/SDK fixture | 158568 | 0.09 |
| ARM64 native Runtime | 18684 | 0.01 |
| ARM64 native Agent | 67320 | 0.04 |
| ARMv6 native Agent | 46692 | 0.19 |

Agent readiness was 9.255/51.205 s (ARM64/ARMv6). These are isolated idle
observations, not a fleet-capacity benchmark. ARMv6's tested P6 kernel exposes
cpu/io/pids, no memory controller: configured MemoryMax is **not** an enforced
cap there. Both native Agents passed real loopback Hub HTTP loss/reconnect and
SIGKILL/restart with the same identity/enrollment request; pending enrollment
received no credential. This is not a physical radio outage test. Existing
signed reconnect/no-replay/local safe-state cases also passed on both targets.

The real ARMv6 Node installer reached native health, intentionally failed, then
restored `/opt/3mm/current` to beta.53 and a healthy Node Agent. Configuration
and all host network profiles were byte-identical; no Core DB was created.
Private recovery backup stays on that device at `/var/backups/3mm-p6-node-20261024`.
The unused new native component pin is retained; old beta.53's unit runs again.
ARM64 Core/Agent kept original PIDs 77052/2541 on beta.56. Owner Ubuntu remains
active on beta.56; `/opt/3mm-dev` remains `m21-beta51` with 22 dirty status lines.

P2 real Wi-Fi/AP remains deferred. Three external Terminal/M21 artifact/socket
integration cases remain in that separate work; the neutral actual systemd
session sandbox passed. Broader Node image/release-readiness status was not
promoted, and no hardware power/disk/OS survival guarantee is claimed. Core
still owns the accepted authority/domain/control plane, including outbound peer
HTTPS; P6 does not claim every I/O path was extracted.

At P6 completion the owned machine `/var/lib/machines/3mm-p6-20261024` and its
evidence/state were retained inside stopped `3mm-WP4-Test` (now running only
for the separate manual browser review above); owned device labs retain no
candidate processes running. No commit/push/version bump/tag/release/publication.

## Owner decisions and development access, 2026-10-23

- Unreleased prototype; no production use. Installed extensions and old
  manifest/SDK/API compatibility are not preservation requirements. Target
  manifest v2 and coordinated current contracts; clean resets can be planned in
  an implementation scope. Do not renumber unrelated protocols just to match v2.
- Owner clarification, 2026-10-23: Bulgarian translations are an extension too.
  Keep them in a generic data-only language package; do not embed Bulgarian as a
  privileged Core/frontend dictionary. English remains the built-in recovery base.
- Primary source: laptop `C:\Users\LAZ-DELL\Desktop\3mm`. Use Ubuntu in WSL for
  Linux runtime checks with isolated code/data. Owner's "yes" was interpreted as
  confirming this Ubuntu is the VM discussed in this chat.
- Read-only checks: WSL Ubuntu (`raspberry`, x86_64) and `rasp-3mm`
  (`raspberry`, aarch64) resolve `/opt/3mm/current` to beta.56; `rasp-3mmw.local`
  (`raspberry`, armv6l) resolves it to beta.53. These are installed-link
  observations, not fresh health, sudo, UI-login or release-publication checks.
- `/opt/3mm-dev` in Ubuntu contains independent dirty M21 work on `m21-beta51`.
  Preserve it; do not use it as a disposable Linux checkout for this task.
- Owner-provided prototype login conventions, host aliases and known-hosts paths
  are recorded only in the local Git metadata file: use
  `git rev-parse --git-path 3mm-development-access.md` to locate it.
- Resilience goal: provider/extension failures and compatible component updates
  must not require a Core restart or full-platform release. No software can ensure
  uninterrupted operation through loss of power/OS/storage on a single machine.

## Accepted baseline

- M20/WP4 was functionally accepted on **2026-10-21**, in reviewed-native scope
  with recorded limits. Old checkpoint/audit statuses do not reopen it.
  [Final acceptance](EXTENSION_PLATFORM_V2_WP4_FINAL_ACCEPTANCE.md) is authoritative.
- This does not close all M20 work, WP5 or M21. Reviewed-native execution is not a
  malicious-code sandbox. These limitations are not new work for the active task.
- Keep the monorepo structure. No broad directory reorganization is authorized.

## Checkout snapshot (refresh before modifying or committing)

- Inspected local HEAD: `2fdc3df`; main was one commit ahead of local origin/main.
  This is a local observation, not a fresh remote-state check.
- Existing user changes: `.gitignore`, `CHANGELOG.md`, `README.md`, `VERSION`;
  untracked `docs/M20_ADMIN_TRUST_UX_PLAN.md` and beta.57 release notes.
- Worktree VERSION was `0.3.0-beta.57`; this does not prove a published release.
- Preserve those changes. Inspect the current diff before staging; a dirty
  worktree does not imply that every file belongs to the active task.

## Checks and evidence

- Policy and commands: [development checks](DEVELOPMENT_CHECKS.md).
- At handoff, record checked content/base, command, environment, result and limits.
  Reuse evidence while relevant inputs remain unchanged.
- Historical beta.55 totals are evidence for that version, not current passes.
- Automatic production Python selection remains broad until its dependency groups
  are audited. Local checks can target the actual changed behavior.

### P5 unified diagnostic/dev workflow, 2026-10-24

- Final source **8387d16a495caab95ee79912d5704d109439a81688294f50605208ab69c535eb**,
  997 files / 9,097,838 bytes; **17 source paths** differ from accepted P4 `d579de18...`.
  Frontend is separately pinned by source/lock/dist hashes in `p5-frontend.json`.
  No schema migration, SDK action, authority/host ABI or installed change.
- Settings diagnostics now combines versions/pins, bounded component observations,
  Core service state, scoped TTL recording, stop/export, a shared timeline, explicit
  missing/dropped/truncated data and merged snapshot download. Imported producer
  exports are labelled snapshots, with wall-clock/hop-correlation limits. They are
  not automatically enabled or authenticated authority. Unknown provider/session
  health is explicit rather than inferred from an installed pin. English/light/dark/
  mobile and the Bulgarian extension are covered; Bulgarian remains outside Core.
- Closed current metadata schema covers all 25 signed SDK actions and application
  relay admission/dispatch/response. Current Core/SDK authorization remains in its
  existing paths. No raw body, file, SQL, terminal/PTY content, exception text or
  credential enters the recorder. Startup is inactive, TTL <=1800 s, <=1 MiB and
  10 events/s per selected process; no spool. Stop retains export until TTL.
- Observer and import each have one non-queued allocation. Observer includes
  metadata reads and fixed absolute probes; imports are <=4 MiB with a 5 s read
  deadline, decoded in a worker, with no auth DB transaction across I/O. Admin
  denial/revocation, unsafe fields/framing, TTL/rate/full/busy/drop/export and an
  unavailable collector are checked. Debug does not alter grants or execution.
- Installed offline command `python -m three_mm_protocol.diagnostic_snapshot`
  reads fixed passive metadata plus an optional current producer export, imports
  no Core/SQLAlchemy, contacts no service and does not overwrite reports. The
  source-tree `tools.extension_dev` validates and uses the existing upload/activate/
  trace/explicit-old-package APIs, with an explicit isolated URL, hidden token,
  normal TLS, no proxies/redirects/retries and unconfirmed transport outcomes.
- **208 distinct successful Python cases + 12 frontend cases**, deduplicated across
  identified targeted runs, not full CI. Final `p5-core`: **55 passed**, 20.05 s lab;
  `p5-boundaries`: **136 passed**, 107.41 s, source `e57e9e4e...`; `p5-packaging`:
  **94 passed**, 53.77 s, source `15abcf45...`; real `p5-process`: **1 passed**,
  85.05 s, source `acc5b327...`. Those successful operation/transport/native-package
  inputs are unchanged or have separately checked observation/CLI-only follow-ups.
  No latest failure or skip remains. Current final type-check/production build pass;
  visual checks use fixed test data, including desktop and 390px dark/Bulgarian UI.
- Two actual existing packages run in separate immutable host processes with own
  wheels/data through install→trace→A/B/A→bad candidate recovery; Core/Runtime and
  the other host keep their process identities/source. Compatibility reference
  fixtures explicitly prepare the existing helper and Core records; this does not
  claim new protected-review/coordinator acceptance. Scoped identity success→revoke
  denial is real with diagnostics active. Old failures were an incorrect admin
  audience, missing restored-host readiness observation and a missing offline import;
  each has a successful corrected run. No command was automatically replayed.
- Environment: WSL Linux x86_64/CPython 3.14.4, unchanged dependency digest
  `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`;
  frontend uses the existing local Node/Vue/Vite lock. Commands/source IDs/results
  and provenance: `.runtime/dev-lab/evidence/p5-*`. Native artifact targets remain
  Linux x86_64/CPython 3.14. Five native archives and four exact neutral package
  candidates are saved under `.runtime/p5-*`; `p5-artifacts.json` has full hashes.
  Runtime/connector executable remains byte-identical to P4 (`d1e185e6...`).
- No installed rollout, radio/network change, account/service change, reset,
  commit, push or version bump. P6 full installed/clean-image/ARM/ARMv6/resource/
  reboot/power acceptance and deferred P2 radio remain open. Current diagnostic
  collection is explicit pull/import; absent Runtime/Agent/session exports remain
  missing. M21 broker/stream and independent development are untouched.
  [Operator/dev commands and limits](DIAGNOSTICS.md).

### P4 completion: operation/callback relay and independent services, 2026-10-23

- Final source **d579de181ff54a9f68c5b527f804f6e536ac411c7e09030b1ea8cce5fe093351**,
  989 files / 9,039,992 bytes. Exactly **45 source paths** differ from accepted
  P4d5 `488a4466...`; every snapshot byte matches the laptop worktree. HEAD remains
  `2fdc3df`, index empty; existing user changes and independent M21 are preserved.
- Production administrator/public/operator/kiosk HTTP operations and peer
  bootstrap/report callbacks use one prepare/async-wait/finish relay. Core refreshes
  token/session/role/permissions, kiosk terminal, UI trust and pending/live peer
  ownership/generation before dispatch and before disclosure. Original context,
  command key and outcome rules remain. Post-dispatch refusal is 409/unconfirmed,
  without automatic replay or direct synchronous handler-response fallback.
- The existing eight response slots are shared with status/health, separate from
  SDK/public/event pools. Core reserves before send and transfers a write-half-closed
  connected FD. Runtime reads one original signed frame under the declared absolute
  1–30 s budget. No Core thread/DB transaction spans handler-response waiting;
  Core checks HMAC/request/schema and current policy behind a conditional fence.
  Relational host-metadata stays a short Core admission exchange with one absolute
  **2 s** connect/send/read deadline and no DB/key lease. Health still gets no SQL ticket.
- New Agent/public-web/session-worker artifacts reuse the shared stdlib immutable
  pointer/journal transaction: own roots/vendor/venvs/current/previous/health/recovery,
  closed contract/target/source/dependency hashes, common installer mutation lock.
  Updates require an already active component and never enable one. Bad-candidate
  recovery resets only that component's systemd failure counter. Compatible updates
  preserve Core PID/generation/source and do not change business data or replay effects.
- Agent has a filtered own environment with coordinated installer backup/restore,
  retaining trusted OS account `3mm`; this is not hostile-code Agent isolation.
  Public adapter has no Core Requires/PartOf. Session retains actual DynamicUser,
  cgroup/namespace/AF_UNIX/no-new-privileges, no network/Core files and current Core
  authority lifecycle. Reserved public identity route: `/__3mm_component__/health`.
  Core OOMScoreAdjust -500 versus optional workers +300 and finite per-service
  budgets favor management; aggregate hardware limits still require P6 measurement.
- Fresh groups on `1dc926dd...`: peers/metadata **235 passed**; packaging **164 passed**;
  real prepared relational runtime plus actual session systemd sandbox **14 passed**;
  component/store suite **49 passed / 1 stale expectation failure / 1 root skip**.
  The sole expectation is corrected to include reset-failed; its final targeted
  rerun passed **1 case** on `d579de18...`. The separate host-principal proof closes
  the host skip. Native artifacts
  are unchanged by the final test-only edit from `1dc926dd...` to `d579de18...`.
- Reused identified results: initial HTTP policy **124 passed**, affected HTTP routes
  **59 passed** after the last relay edit; human process **10 passed** plus **5 passed**
  replacing the wrong-admin-token fixture cases and checking late 409; boundary
  processes **145 passed / 6 root skips**; Agent/public/session unit group **184 passed**
  plus corrected role fixture **5 passed**; recovery controls **31 passed**. Root
  principal/update and actual Agent/public update reruns are recorded separately.
  **931 distinct successful targeted cases** are deduplicated across these runs;
  no latest failure remains. Six older distinct-UID boundary cases are skipped in
  this package; prior P4 root evidence is retained without adding new passes.
  Exact cases and repaired earlier fixture/path/packaging attempts are recorded in
  `.runtime/dev-lab/evidence/p4-complete-results.json`.
- WSL Ubuntu Linux x86_64, CPython **3.14.4**; unchanged dependency digest
  `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`.
  Commands/source IDs/JSON/XML and byte comparisons: `p4-end-*` / `p4-complete-*`
  under that evidence directory. This is targeted local acceptance with evidence
  reuse, not full CI or clean installed-device acceptance. Skips are not passes.
- Five local archives `.runtime/p4-complete-{platform-runtime,application-host,agent,
  public-web,session-worker}.tar`; exact builds/digests/bytes/native targets are in
  `p4-complete-artifacts.json`. Runtime/connector executable is byte-identical to
  P4d4 (`d1e185e6...`, archive `dfa9c6d0...`, 20,480 bytes). Host/services target
  Linux x86_64/CPython 3.14; other architectures/Python versions need native builds.
- Core authority/domain/control-plane adapters, including outbound peer HTTPS,
  remain Core work. Existing M21 broker/stream ownership is unchanged; separating
  its worker artifact is not a new streaming architecture. No installed rollout,
  schema migration/reset, Wi-Fi/AP test, commit or release. P2 radio remains deferred;
  P5 debug/dev workflow and P6 installed/hardware/resource/reboot/power gates remain.
  Historical sections below retain their original handoffs; this completion is current.

### P4d5 admin health response relay, 2026-10-23

- Final source **488a4466c9488f5a60a8aa2ab5a475efe554d804d14049e098b1d29c54a34b73**,
  979 files / 8,961,346 bytes, HEAD `2fdc3df` unchanged. Nine source inputs differ
  from the P4d4 `af989...` baseline; every saved source byte matches the worktree.
  Source comparison and exact JSON/XML evidence: `.runtime/dev-lab/evidence/p4d5-*`.
- `POST .../{module_id}/health` retains actual admin authorization and the declared
  health result shape. Core performs short prepare/finish in its thread pool and
  asynchronously awaits Runtime; no Core thread/DB transaction spans the response
  wait. Initial and post-reservation admission retain the shared package, internal
  audience, key and native UI trust checks. Runtime receives only an already-sent,
  write-half-closed FD. Missing/full Runtime refuses before app send; no automatic
  replay, synchronous fallback, SDK action, permission or schema migration.
- Health shares P4d4's **eight** response slots, <=1 s reservation and <=2 s remaining
  connect/send/handoff budget. The declared operation's **1–30 s absolute** response
  budget is preserved; Core's async IPC wait is at most that budget +1 s. Original
  app HMAC/request ID/time, dict result and declared output schema are verified in
  Core. Fresh instance/incarnation/epoch/mode/module/version/package/socket/key/UI
  trust checks and a conditional SQL update fence `health_checked_at`; changed or
  invalid results return 409 without overwriting health success.
- Relational review confirmed health is an internal query with no host-metadata
  IPC or SQL ticket. Real prepared-host coverage after resource revoke passes with
  Core UID1000, Runtime UID65534 and host UID1200/GID1201. The root driver prepares
  only disposable resources; actual factory/migration/host code runs non-root.
  Separate HTTP tests also use existing `3mm-app`, deny Runtime DB/key reads and
  preserve Core PID/digest through Runtime kill/update/rollback.
- **280 distinct successful targeted cases**, deduplicated across identified runs,
  not a fresh full suite. WSL Linux x86_64, CPython **3.14.4**, unchanged dependency
  digest `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`:
  - `p4d5-core`: **66 passed**, 16.72 s, snapshot `01f6ffee...`.
  - `p4d5-process`: **18 passed / 1 root-only skip**, 75.26 s, snapshot `d6fcd81c...`;
    the skipped health UID case passed in the final root proof. Production health,
    Runtime and applicable process inputs stayed byte-identical afterward.
  - `p4d5-boundaries-before-contract-sort`: **123 passed**, with 70 packaging
    failures caused by my unsorted required-file insertion, snapshot `01f6ffee...`.
    All 70 failures were resolved by the complete affected `p4d5-packaging` rerun:
    **78 passed**, 4.74 s, final `488a4466...`. Successful response/lifecycle/status/
    startup/lab checks are reused with unchanged relevant inputs. No open failure.
  - Final root proof: **5 passed**, 35.49 s, final `488a4466...`. An owned temporary
    venv copy with identical dependency digest made UID1200's Python executable
    traversable; original home/cache permissions and installed accounts were untouched.
  - The older status distinct-UID case remains skipped in this unprivileged run;
    P4d4's root evidence is retained without adding it to the new pass count.
- Mixed health/status pressure holds eight responses while Core borrowed thread
  tokens stay <2, admin diagnostics/settings work and an independent DB writer
  finishes <0.5 s. Faults include timeout/trickle/size/signature/request/schema/
  error results, absent/killed Runtime, stale admission/completion, key/package/
  mode/socket drift, lifecycle CAS races, native UI trust refusal and non-admin denial.
- Runtime's eight executable inputs are unchanged. Reuse the exact P4d4 artifact
  `.runtime/p4d4-platform-runtime.tar`, 20,480 bytes, build `d1e185e6...`, archive SHA
  `dfa9c6d085b80d808adfd5b71bf32adc74905663203efd7de3585d792904d4f2`.
  No new Runtime feature/version or binary rebuild is required by P4d5. The full
  release contract now requires the Core health helper; missing-file/reproducible
  packaging checks pass. No frontend/SDK/app-host production changes or full CI claim.
- P4d5 profiles: `p4d5-core|p4d5-process|p4d5-boundaries|p4d5-packaging`. Saved
  evidence includes initial failed fixture/environment attempts and their repaired
  reruns, source/input comparison and deduplicated result summary. Completed owned
  temp labs and the test-only venv were removed after evidence capture.
- No device rollout, migration, account/service/network mutation, commit or release.
  P2 Wi-Fi/AP remains deferred; P4d6 is the next bounded result, P5–P6 remain open.

### P4d4 admin operational-status response relay, 2026-10-23

- Final source snapshot **af989f8161fe9f13c9a9f814d3ada42c1d00255de47d45c52cf310bbc370753d**,
  976 files / 8,928,871 bytes, HEAD `2fdc3df` unchanged. All bytes match the saved
  source archive. Documentation is outside the lab snapshot. Source comparison
  and artifact input identity are recorded in `.runtime/dev-lab/evidence/p4d4-*`.
- The audit selected `operational-status`: its direct synchronous app response
  read is removed. The HTTP endpoint remains admin-only and waits asynchronously.
  Short Core preparation commits admission before app I/O; completion uses a fresh
  metadata snapshot. No Core thread/DB transaction stays held during response wait.
  The remaining human/kiosk/health/peer paths are listed in action-plan section 19.
- New **application_response_contract 1** on private ABI **2**, with no SDK action,
  grant or DB migration. Runtime readiness negotiates enabled support; production
  health requires its protected response listener. Separate **8 slots**, Core
  reservation <=1 s before any app send, <=2 s remaining Core handoff budget,
  one <=1 MiB application response with absolute 5 s status deadline, Core receive
  <=6 s. Generic relay can wait at most 30 s, but this path selects 5 s.
- Core authenticates Runtime's actual UID before reservation; Runtime authenticates
  actual Core UID before metadata/FD receipt. Only the already-sent connected FD
  leaves Core. Core shuts down its write direction first, which applies to all
  duplicates and prevents extra writes through the transferred socket. No app key,
  DB, request signing or grant/retry state enters the response worker.
- Completion verifies current instance/incarnation/epoch/package/lifecycle/key and
  original HMAC/request ID. Stale/foreign/invalid results are not disclosed. A
  disabled app is not probed; missing/full Runtime cannot dispatch an extra query.
  `runtime_observation` distinguishes available/unavailable/inactive telemetry and
  `outbox_inspected`; unknown/uninspected outboxes are not claimed as observed zero.
  Only explicit new admin reads can create a fresh read-only probe; no loss/restart
  automatically repeats an existing query. This is observation, not resource authority.
- Runtime stays PrivateNetwork/AF_UNIX-only, without extra Core groups. Its existing
  unit adds a setgid Core-group response socket directory, TasksMax 48 / NOFILE 192.
  The stdlib artifact adds `responses.py`, retaining independent update/rollback and
  unchanged Core PID/code. Initial Core/unit/artifact activation must be coordinated.
- **362 distinct successful targeted cases**, deduplicated across identified runs,
  **not one fresh full suite**. Linux x86_64 CPython **3.14.4**, dependency digest
  `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`:
  - `p4d4-core`: **56 passed**, 11.73 s; `p4d4-process`: **12 passed / 1 root-only
    skip**, 54.74 s, on snapshot
    `85ba2e28ff4fa21f2bdc65a99257d78dcb2e8510ad5bc6dae8aee54014babe04`.
  - `p4d4-boundaries`: **294 passed / 4 root-only skips**, 184.03 s, on snapshot
    `49c38b6c965e2b8c26ab1b0c728accfbdb642cbb2f1ef590dd54ec7afdd6e886`.
    Reused after the final Core-only write-half-close line: that line is called
    only by the status response path, whose full affected suites were rerun on
    `85ba...`. Runtime/artifact and the other domain paths are byte-identical.
  - Separate owned root driver on `85ba...`: **3 passed**, 20.76 s. Actual Core
    UID1000, Runtime UID65534, host under existing `3mm-app`; Runtime/host have no
    supplementary groups. Actual DB/key/socket denials, full pool, independent
    Runtime kill/update/rollback, unchanged Core PID/digest. No installed mutation.
  - `p4d4-auth` on final `af989...`: **1 passed**, 7.44 s, including a real signed-in
    non-admin denied 403 before any app I/O. Only test/lab-profile inputs changed
    after `85ba...`; all production inputs remain byte-identical.
  - The status root-only skip passed in the separate root proof. Four older
    SDK/public/event/connector UID cases remain skipped in this unprivileged run;
    previous evidence is retained, not presented as fresh passes.
- Pressure tests hold all eight app responses concurrently while authenticated
  admin diagnostics/settings work, Core thread-pool borrowed tokens stay <2 and
  an independent DB writer completes in <0.5 s. Overload is refused before extra
  app dispatch. Tests cover timeout/trickle/size/signature/request ID, stale
  admission and result, revoked/disabled state, key drift, FD cleanup on malformed
  handoffs and shutdown, no write/replay through the half-closed FD and absent Runtime.
- New runnable profiles: `tools/dev_lab.py run --archive <snapshot> --profile
  p4d4-core|p4d4-process|p4d4-boundaries|p4d4-auth`. JSON/XML/check summary/source
  comparison are saved under `.runtime/dev-lab/evidence/p4d4-*`; completed owned
  temp labs were removed afterward, so their logged `/tmp` paths are historical.
- Local artifact `.runtime/p4d4-platform-runtime.tar`, **20,480 bytes**, build
  `d1e185e6ef2e6b9ff8f4923e1329db904d5bf164c2e04b502892ce7387991a1d`,
  SHA `dfa9c6d085b80d808adfd5b71bf32adc74905663203efd7de3585d792904d4f2`.
  CPython >=3.12 stdlib payload; executable inputs match final source. No device,
  ARM/cgroup acceptance, installed activation, new migration, release or commit.
  Frontend/SDK/application-host inputs are unchanged; no unrelated build/full CI claim.

### P4d3 connector network worker, 2026-10-23

- Current source snapshot **b40a3ed915719b71c1cdc0e3dac403c1f03e11228da1bcdd9e2bac2cda0e8adf**,
  971 files / 8,890,746 bytes, HEAD `2fdc3df` unchanged. Compared with the P4d2
  snapshot: 33 changed source inputs. All source bytes match the saved archive.
  Subsequent documentation edits are outside the lab source snapshot.
- Feature **connector_execution_contract 1** on private ABI **2**; no SDK action
  or permission added. Core validates its existing declaration/binding/current
  grant, commits the unique attempt and releases authority locks before a <=3 s
  Unix connect/send to the actual expected worker UID. Only that selected target
  credential and a derived result-only key leave Core; Runtime gets neither.
- Four network slots, disposable children, declared 1-30 s absolute deadline,
  verified TLS, no redirect/proxy environment/automatic retry. The coordinated
  manifest response cap is **4 MiB** within the existing 6 MiB SDK frame. The
  Runtime remains PrivateNetwork/AF_UNIX-only and its request budget is <=35 s.
  Core's 40 s boot-clock attempt expiry records ambiguous mutations/unconfirmed
  reads on later connector/status access, without resending. A duplicate settles
  its own expired attempt even behind a full unexpired 100-row status batch.
- Current key admission is intentionally nonblocking. The saturation proof first
  admits each request, then holds all four HTTP responses concurrently; signed
  discovery, settings and authenticated admin component diagnostics remain usable.
- Completion checks stored owner/instance/dispatch/deadline/limit and receipt +
  worker HMAC before one CAS outcome. Revocation/disable cannot reauthorize a
  dispatch; already admitted effects can still be accounted. Rebinding cannot
  overwrite the new binding's telemetry. Missing/late/invalid results never replay.
- Migration **2c078e3546f7** preserves history and adds nullable JSON correlation
  only; no plaintext credential/header/body. In-flight new attempts refuse schema
  downgrade before DDL. Upgrade/check/downgrade run on isolated test databases.
- Same tiny stdlib executable, **independent process roles**: dedicated
  `3mm-connectors` account/unit, own `/opt/3mm-connector-worker` releases/venv/pins
  and `/var/lib/3mm-connector-updates` journal. The updater's
  `--component connector-worker` selector switches/rolls back only that service;
  it verifies unchanged Core fingerprint. Runtime/worker health reject unsupported
  contracts/builds. Initial Core/schema/unit/component activation must be coordinated;
  incompatible old sets fail readiness. No installed activation is claimed here.
- **412 distinct successful targeted cases**, deduplicated across the identified
  runs below, **not one fresh full suite**. Linux x86_64 CPython **3.14.4**, dependency
  digest `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`.
  `tools/dev_lab.py run --archive <snapshot> --profile <name>`:
  - `p4d3-core`: **81 passed**, 75.54 s; `p4d3-process`: **12 passed / 1 root-only
    skip**, 73.07 s; `p4d3-focus`: **46 passed**, 29.66 s, all on snapshot
    `6f8f3b7c02e7f53b91087568cb5b1cb46b5fc1a03291adbb5d80228cb6d156e8`.
  - `p4d3-boundaries`: **288 passed / 3 root-only skips**, 144.79 s;
    `p4d3-last`: **3 passed**, 11.24 s, on snapshot
    `4118c8de035e4cf13396d6bfe65ea4900b1603325fbfdd3d7d2a10226469f43f`.
    Extra coverage: TLS refusal, trickle deadline and expired duplicate beyond batch.
  - Separate owned root driver on `4118...`: **4 passed**, 29.06 s. Actual Core
    UID1000, Runtime UID65534, network worker UID65533, no supplementary worker
    groups; real DB/key/worker-socket denials, Core restart/crash and independent
    worker kill/update/rollback. No account/service/network mutation.
  - `p4d3-admin` on final `b40a...`: **1 passed**, 8.85 s, authenticated admin
    diagnostics/settings while all four HTTP response slots are occupied.
  - Production inputs are byte-identical across these final snapshots. Later
    changes add tests/lab profiles only; existing successful cases are reused.
    The connector root-only skip passed in the separate root proof. The other
    three skips concern prior SDK/public/event distinct-UID cases; their earlier
    P4b/P4d1/P4d2 evidence is retained, not presented as fresh passes.
- Evidence JSON/XML, deduplicated case summary and source comparisons are saved
  under `.runtime/dev-lab/evidence/p4d3-*`. Completed owned temp labs were removed
  after saving evidence; referenced `/tmp` paths in logs are historical.
- Local artifact `.runtime/p4d3-platform-runtime.tar`, **20,480 bytes**, build
  `7ba37016285a7676ebc20ed40ec4b3c4c9fa2f93cf8345b4bb7a871766cd7b87`,
  SHA `aeae510c8f27a37cd97ce66301b0a8da2318c28e76c084be6b08ffb66cb1ba0b`.
  All executable inputs match the final snapshot. No release, migration of an
  installed DB, deployment or device test. Frontend, app-host and SDK implementation
  inputs are unchanged; prior relevant evidence is retained. No full CI claim.

### P4d2 durable event response worker, 2026-10-23

- Event feature contract **1**, negotiated over the existing private ABI **2**
  gate; no new SDK permission/action. Only the expected Runtime UID may claim or
  settle work. The stdlib Runtime artifact includes `events.py`; production unit
  passes `--events`. Its one response worker is separate from SDK/public pools.
  Readiness validates Core support and a successful claim handshake, including
  cold startup with a blocked optional handler; it does not await application work.
- Core device-event background work now matches/persists only. No Core event
  handler execution loop remains. `/api/v1/application-events/drain` is admin-only
  and returns `status: queued`; it makes pending retries eligible without resetting
  attempts, taking an in-flight claim or dispatching in the HTTP request. Backlog
  counts pending + delivering. Paused pending subscriptions do not consume the
  selection batch, while unresolved heads continue to fence their own FIFO.
- Each attempt stores an opaque dispatch ID plus original instance/package/
  request/operation, kernel Runtime generation and boot-clock deadline. The Core
  DB/key admission lease is released before the bounded <=3 s connect/send. Core
  passes the already-sent socket to Runtime; it never reads the handler response.
  No app transport key, Core DB or authority cache leaves Core.
- Runtime response budget <=30 s, entire step <=35 s, frame <=1 MiB. Durable lease
  **40 s**, retry backoff **30 s**, at most **5 attempts**, including pre-dispatch
  failures. Reboot/expired lease marks the old attempt unconfirmed; a fresh retry
  needs current declarations/source/grant/epoch again. A previously exhausted
  pending row cannot dispatch a sixth time. Original event ID is the idempotency
  key on every attempt: delivery remains **at least once**, not exactly-once
  application effects. No blind Runtime resend of a lost claim/result is added.
- Completion checks stored owner/token/deadline, original response HMAC/request
  ID and admitted package operation schema. CAS commits outcome + cursor/counts
  once; repeated completion cannot double-count or start code. Already admitted
  successful work may be accounted after disable/revocation, without authorizing
  another attempt. Rotation/missing keys/invalid result fail closed and retain
  bounded retry/terminal evidence. Data/effects are not undone by code rollback.
- Migration `1bf67d2435e6` adds four nullable fields, preserving old queue/attempt/
  epoch/cursor data. Downgrade refuses before DDL while any delivery is in flight.
  Full artifact contract requires the migration and worker; old Runtime artifacts
  must be rebuilt. Initial coordinated Core/schema/unit installation is required
  before independent compatible Runtime updates. No installed DB was migrated.
- Final source **`7612dced64f6ce91afb290fa045bd55579e2355d70b2bbd5532a30fcc04e7be4`**,
  964 files, 8,827,470 bytes; HEAD `2fdc3df7cfa7200c617f4edd8739f8a1037dacf8`.
  Ubuntu CPython **3.14.4**, dependencies unchanged:
  `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`.
- Core events/grants/publication/migration: **87 passes** on `2fa8247e...`,
  `/tmp/3mm-lab-_0as0db9`, 79.36 s. One migration test fixture/expected exception
  was corrected; its complete upgrade/check/guarded-downgrade test then passed on
  `85d28912...`, `/tmp/3mm-lab-1ie7qh8g`, 9.55 s. Migration runtime code unchanged.
- SDK/public/Runtime updater/full+Node packaging: **259 passed / 2 root-only skips**,
  `/tmp/3mm-lab-v_wgmvfz`, 103.96 s; real event processes **11 passed / 1 root-only
  skip**, `/tmp/3mm-lab-rrmzcdvk`, 80.96 s, both source `85d28912...`.
  Separate root driver: **4 passed**, `/tmp/3mm-p4d2-principals-ysll947h`, 35.38 s.
  Core UID1000, Runtime UID/GID65534, existing service UID994/GID985 with no extra
  groups. Both non-Core users are refused DB/key reads. Runtime kill, Core restart,
  crash after durable send/before FD handoff, update/rollback/bad candidate preserve
  the journal. Lease expiry is forced in the owned test DB, not a 40-second wait or
  power/cgroup test. Normal source/grant reapproval/revocation negatives remain.
- Later narrow queue guards (exhausted pending row, paused-head selection) and
  required migration packaging were tested: **132 passed** on `419d077b...`,
  `/tmp/3mm-lab-aq6lamx_`, 85.60 s; final event-state/FIFO/fairness/current signed
  process followup **36 passed** on final source, `/tmp/3mm-lab-os6j5ksu`, 13.15 s.
  **364 distinct successful current targeted cases** after overlaps/corrected
  failures; not one fresh 364-case full run. Exact commands/source deltas/JSON/XML
  are in ignored `.runtime/dev-lab/evidence/p4d2-*`. Unchanged host/SDK/protocol/
  frontend evidence is reused. No frontend build, full CI or hardware acceptance.
- Initial attempt failed because WSL `/tmp` tmpfs was full; it is not counted as
  evidence. Only named completed owned labs were cleaned after evidence capture;
  installed state and M21 were untouched. Evidence/archives remain on the laptop.
- Local `.runtime/p4d2-platform-runtime.tar`, **20,480 bytes**, build
  `e92552c13233f5fec68d09865b1bff96ed6caa616467c22015e9dac878faa216`, SHA256
  `3c0294b58c24550a0e40d5c9678d35cfefed976916ef7d1e98feb0e68031b1ff`.
  All executable inputs match final source. Stdlib CPython >=3.12, locally checked
  on x86_64 only. No commit/release/deployment, installed account/service/network,
  DB reset or M21 change. P2 Wi-Fi/AP and device/ARM/cgroup/boot/power remain open.

### P4d1 bounded public response handoff, 2026-10-23

- Private authority ABI remains **2**. Public-web feature contract **1** adds
  begin/result-only requests from the already authenticated Runtime UID and a
  negotiated health probe. An old ABI-2 Core without this feature is not ready.
  SDK boot is still the only SDK request carrying an original-client FD; public
  begin replies carry a separate, already admitted service connection.
- Core checks current active route/package/mode, uses the shared invocation
  preparer and current compatibility row admission, signs/sends once (connect +
  send total <=3 s), commits and closes its duplicate after SCM_RIGHTS handoff.
  Core keeps no pending socket or authority transaction while the handler runs.
  Unsupported scoped public or public/relational paths refuse before host IPC.
- Runtime waits in a separate **8-slot** public pool, independently of the 16-slot
  SDK pool. Public frames <=1 MiB, absolute read deadline 5 s, selected operation
  <=30 s and whole request <=35 s. Client trickle cannot renew deadlines. There
  is no automatic retry after loss. Private Core admission remains bounded to 4
  handlers; overload can refuse a new request without starting its application.
- The Core-signed result-only receipt binds request/instance/package/epoch/route,
  current Core listener generation and kernel Runtime process generation. It
  exposes no transport key and is never accepted as dispatch permission. Finish
  rechecks current state/key, original response HMAC/request ID, output schema,
  declared content type, byte limit and safe headers. Already admitted handler
  effects are not recalled by later disable/rotation or Runtime rollback.
- Root prepares a second setgid socket directory owned by `3mm-platform`, group
  `3mm-public`; Runtime gets no app/key supplementary group. Its independent pyz
  now includes the stdlib public relay. The full initial installation must supply
  the matching Core/units; old P4a/P4b Runtime archives must be rebuilt. There was
  no installed P4 upgrade or deployment in this task.
- Real isolated Core HTTP + Runtime artifact + neutral signed service cover GET/
  HEAD/header filtering, invalid signatures/IDs/content/size/headers, trickle,
  disable/adoption/epoch/package/key changes during a pending response, malformed
  requests, result-receipt forgery/expiry/foreign generations, saturation, kill,
  compatible update/rollback and failed candidate. Current SDK identity read and
  admin HTTP remain available while eight public handlers wait. A distinct-UID
  proof denies Core DB/key access to both Runtime and the application principal.
- Final source snapshot **`89aa29c0da5c66ce450705e5d82f6b40e1c404f650ae49e5624cfd8e36196c1f`**,
  961 files, 8,787,491 bytes; HEAD `2fdc3df7cfa7200c617f4edd8739f8a1037dacf8`,
  no staged changes. Ubuntu CPython **3.14.4**, dependency digest
  `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`.
- Main `tools/dev_lab.py run --profile p4d`: **337 passed / 2 root-only skips**,
  source `1d17a1256cb9e8c9f6a9697e619cb7c6230d0399e57321aa7d48d1e8ac5ea4fa`,
  `/tmp/3mm-lab-ln_7z5rm`, 153.65 s pytest. The sole later production change adds
  the early public/relational refusal. Its new case and direct invocation/peer/
  relational/UI/lifecycle/host consumers ran on source `13651553...`:
  **312 passed / 15 root-only skips**, 154.83 s, `/tmp/3mm-lab-hesa535s`.
- That consumer run found two stale SDK test expectations, reproduced on the
  untouched P4c source `9ef0719d...` (`/tmp/3mm-lab-bg2e_4ko`). Current SDK sends
  `operation_failed` for internal failures and no reply to unauthenticated input.
  Only the tests changed. Followup source `c4d6e72c...` passed **86 cases** including
  early refusal, updated peer cases, feature mismatch and current SDK under public
  saturation; its last stale unauthenticated-response assertion was then corrected
  and that complete test passed on final source (`/tmp/3mm-lab-g888pzxe`, 2.25 s).
- Separate root driver on source `13651553...`: **3 passed**, 17.99 s pytest,
  `/tmp/3mm-p4d-principals-0xbsiavx`. Actual Core UID1000, Runtime UID/GID65534 and
  existing application UID994/GID985, with no application supplementary groups.
  No installed account/service/network mutation. Public principal denial is now
  covered; other pre-existing root-only/installed relational acceptance is not closed.
- **653 distinct successful current targeted cases across these runs**, after
  overlaps and corrected failures; this is not one fresh final 653-test run.
  Exact commands, JSON/XML and per-source changed-path/reuse audit live under
  ignored `.runtime/dev-lab/evidence/p4d-*`. Remaining historical root-only skips
  are not counted as passes. Unchanged SDK/protocol/wire/frontend evidence is
  reused from P4b/P3b; no frontend build or full CI was run.
- Local **20,480-byte** `.runtime/p4d1-platform-runtime.tar`, build
  `c64333918ee36a06f69cae8c20f60a5b99af9fe0bc850f1701d987e8650ed70c`, SHA256
  `0adb143fa5024b6bc4d5e704a6d17e62ba69a4d5ebcc29bc759e3859f4a00398`.
  All executable inputs match final source. Stdlib CPython >=3.12 artifact, not
  ARM/device/cgroup/clean-image acceptance. No commit, release, deployment,
  installed networking or M21 change; P2 Wi-Fi/AP stays deferred.

### P4c independent application-host artifacts, 2026-10-23

- Native builder `deployment/application_host_component.py` creates a reproducible
  `host.pyz` plus exactly eight locked dependency distributions (316 vendor files)
  from a prepared Linux CPython build environment. No Core/provisioning packages
  or fallback to Core site-packages; isolated self-check imports Pydantic,
  cryptography's Rust extension and CFFI, with no backend/SQLAlchemy/FastAPI visible.
  Root staging executes candidate self-check code as `3mm-app`, never root.
- `/opt/3mm-application-hosts/releases/<build-id>` holds shared read-only code,
  vendor files and its own pip-free `.venv`. Each instance has independent
  `instances/<id>/current` and `previous`. A compatible full bootstrap preserves
  its default and existing pins; changing the default does not switch old hosts.
  Generic start/enable/restart validates/binds a host before systemd, including
  prepared/relational starts. Missing default refuses startup before unit mutation.
- Application unit no longer resolves `/opt/3mm/current` or has Core PartOf/
  Requires; it keeps After ordering, no global environment, AF_UNIX/private network,
  Core state inaccessibility and resource limits. Applications still share the
  existing `3mm-app` principal: this is not a new hostile-code/multi-tenant sandbox.
  Runtime package exports are lazy; root-only boot publication imports stay off
  the worker reader path. Current protected boot/lifecycle/SDK authority is retained.
- Per-instance update/rollback reuses the proven Runtime pointer/journal mechanism,
  validates native target, exact source/vendor hashes and host-contract 1/private
  authority ABI 2 before switching. It only operates on an already active
  application and targets its one unit. Fingerprints retain Core process/release,
  Platform Runtime process/build and active application metadata. An invalid or
  unhealthy candidate reverts only the host; interrupted updates reconcile via
  explicit `recover`/next update. There is no automatic installed boot recovery.
- Signed internal `three_mm.host.info` reports own build/instance/PID/UID and active
  metadata hash; it grants nothing. Root verifies the same connection's SO_PEERCRED,
  original app transport signature and expected build. Probe/health frame waits
  use absolute deadlines, including trickled responses. Root validates health
  and the verified application UID before accepting a candidate.
- **271 passed / one skipped**, final `p4c` profile, Ubuntu/CPython 3.14.4,
  80.54 s pytest / 82.27 s process, 1.16 s preparation. The one root-only case
  passes separately: **one passed / 0 skipped**, 21.44 s pytest / 23.45 s driver.
  Therefore **272 distinct successful current cases**, across two runs, not a
  single newly run 272-case suite. Main/root checked source:
  `893be001f3ea9af90e349a121d4fd8208bb25761083b71187781b983b6791c9b`
  (960 files), HEAD `2fdc3df7cfa7200c617f4edd8739f8a1037dacf8` unchanged.
  Final narrow prepared-start follow-up: **one passed**, 7.65 s pytest / 8.90 s
  process, source `9ef0719d0bc5f2667d00746b78d21866c7d7d9f771b64f174b2f61f11762376b`.
  Only the systemd active-state predicate and its expanded prepared-start test
  changed: a manually active host with boot disabled is updatable, and update
  never changes enable/disable state. Worker/HostStore/artifact inputs are
  unchanged; reuse the other 270 main passes plus the separate root pass.
  This supersedes the old prepared-start case, not an extra 273rd distinct case.
- Actual two-host proof: independent update/rollback, bad-candidate recovery,
  updater interruption/recovery and hung-host replacement preserve exact Core
  PID/source, Platform Runtime PID/build, other-host PID, wheel/active metadata
  and neutral fixture data. An inactive host update is refused, not enabled.
  The root driver uses Core UID 1000, Runtime UID/GID 65534, host UID 994/GID 985
  (existing `3mm-app`), no supplementary host groups. That host cannot read Core
  SQLite or transport keys. Production host health runs against the real seeded
  host socket/key; only the continuity observer uses the isolated Core controller.
  These neutral fixtures are not fresh installed review/device/boot acceptance.
- Unchanged dependency digest:
  `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`.
  Compared with P4b, all production Core services/routes/DB, SDK, protocol/wire and
  Platform Runtime files are byte-identical. Reuse P4b's unaffected 965 regression
  passes; changed host/lifecycle/deployment consumers are covered above. Frontend's
  187 inputs are unchanged: reuse P3b's 489 tests/57 files and TypeScript/build.
  No new full CI, frontend build or browser check.
- Evidence: ignored `.runtime/dev-lab/evidence/p4c-{final,principals,start-final}.{json,xml}`,
  `p4c-source-comparison.json`, `p4c-artifact.json`. Earlier helper API errors are
  corrected/superseded by these passing final runs, not unresolved failures.
- Local native artifact `.runtime/p4c-application-host-linux-x86_64-cp314.tar`,
  23,685,120 bytes; build
  `2aedee3286cc3e5fe65ae5791844c94509d3b2e547171beea916322dabcf1d63`,
  SHA-256 `4966092a938bd64d9e019ec3de897022899c746a2cfbd4d17d56a64a4cc7f4d9`.
  Target: Linux x86_64 / CPython 3.14. ARM/ARMv6 or another Python needs its own
  native build. Build environment must match `application-host-requirements.txt`;
  target self-check rejects missing/incompatible native dependencies before switch.
- Limits: rollback restores host code/environment, not application effects/data.
  Factory/migration/health code runs as on ordinary restart; existing application
  lifecycle/receipts govern its effects. No wheel/schema/config/grant update or
  replay is part of host update. Full clean-image/installer/cgroup/reboot/power/
  device boot acceptance remains open. No staging/commit, version change, push,
  publication, deployment, installed account/service/network or M21 modification.
  P2 Wi-Fi/AP remains explicitly deferred. Commands: action plan section 15.

### P4b complete signed SDK transport, 2026-10-23

- One SDK destination (`socket_path`), including discovery, commands, checkpoints,
  files, events, connectors, peers/status and relational admission/completion/boot.
  The split `runtime_socket_path` argument and `platform_runtime_socket` metadata
  are removed. Current activation writes Runtime's endpoint into `platform_socket`;
  old locally generated host metadata must be regenerated by reactivation. No
  implicit old-socket fallback, caller-selected admission, retry or grant cache.
- Core starts only the Runtime-UID-protected authority listener for these calls;
  the public SDK listener/factory, old socket setting/environment and its writable
  service path are removed. Private ABI **2** rejects ABI 1 before update mutation;
  incompatible P4a local artifacts must be rebuilt, not silently retained.
  SDK wire/discovery version 1 and SDK 1.3 remain separate version axes.
- Boot carries exactly one connected AF_UNIX stream FD via SCM_RIGHTS; Core reads
  kernel SO_PEERCRED from that duplicate and uses its own configured application
  root. Runtime cannot supply a PID/UID/root in place of it. No FD on other actions;
  missing, multiple, truncated, wrong-type/listening/unconnected descriptors refuse
  admission and close received FDs. MSG_CMSG_CLOEXEC prevents exec inheritance;
  closing the duplicate does not shut down the original application's connection.
- Shared 6 MiB frame ceiling, 16 Runtime handlers/four private Core handlers,
  five-second absolute frame read, 35-second SDK/Runtime transport deadline.
  Health probes retain a three-second private-hop budget. Rejected structured
  action values close cleanly without an unhandled worker exception.
- **144 passed / 0 skipped**, final P4b/host/Core-startup/lab checks, Ubuntu/Python
  3.14.4, 43.20 s pytest / 46.23 s process (1.13 s preparation). Real kernel FD
  passage from an independent pyz process, all 25 signed family routes, current
  grant refusal, >16 KiB transport, real checkpoint CAS/write/revocation across
  Runtime artifact update, invalid ancillary frames and FD leak/close-on-exec tests.
- **241 passed / 0 skipped**, final shared Runtime/component/install/role/unit
  checks, 32.38 s pytest / 34.73 s process (0.75 s preparation), same final source.
  Real update, rollback, bad-candidate recovery, kill/hang and private-gate outage
  preserve Core PID/source and HTTP administration. With the 144 group there are
  **358 distinct successful cases**, plus the separate-principal case below:
  **359 distinct final targeted passes**, not one newly run single 359-case suite.
- **One additional distinct-principal test passed**, 7.46 s pytest / 9.63 s driver:
  production Core gate factory UID 1000 and Runtime UID/GID 65534, no supplementary
  groups. Runtime still cannot read Core SQLite/keys, wrong UID cannot bypass the
  gate, and app-signed checkpoint input without a current grant is denied. Real
  Runtime artifact update preserves the Core process/source and HTTP readiness.
  Root orchestrates only owned temporary files/processes, with a temporary uploads
  directory owned by the Core UID; no installed accounts/services change.
- These final checks use source
  `0e7514c3e3302a7463fe023ea2b38b35eb3edd6f56e3df65348f10df2276c58b`
  (955 files). Current snapshots/AST reuse comparison is in the evidence below.
- Current-consumer regression: **965 passed / 0 skipped**, 281.35 s pytest /
  291.80 s process, 1.15 s preparation. Boot/relational consumers: **91 passed,
  76 skipped**, 121.44 s pytest / 125.11 s process. Those skipped cases require
  the separate root helper boundary and are not accepted passes or device boot
  proof. Both runs used source
  `5ce438306e1515b3f82f1ea8eee4e8b0131128b5bd179bbef1d8e4cd738f3072`.
  Only two private malformed-action guards, their test, and lab endpoint isolation
  changed afterward. Core/SDK domain adapters are unchanged; reuse their passes,
  with final boundary/host/Core-startup checks covering the changed paths.
- Linux dependency digest remains
  `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`.
  Frontend's 187 recorded inputs remain byte-identical: reuse P3b's 489 tests /
  57 files and successful TypeScript/build; no frontend rebuild/browser changes.
  Counts across profiles overlap; this is not full CI or a single summed run.
- Evidence: ignored `.runtime/dev-lab/evidence/p4b-{final,shared,principals,regression,boot}.{json,xml}`,
  `p4b-source-comparison.json`, `p4b-artifact.json`. The earlier shared-check
  saturation-helper failure used a public frame against the new private protocol;
  the corrected private-header case passes in final Core-startup and regression.
- Local artifact `.runtime/p4b-platform-runtime.tar`, 10,240 bytes, build
  `cfa398a530f9a3b2c1ffe011a446c905a4d1871a111abd5825b0304024cfff9c`,
  SHA-256 `14daa5673a83b3f0c78027e14d28dfe00e03b419cb1672ba7eb8ba52b313d9a5`.
  Commands/current scope: action plan section 14. No staging, commit, version bump,
  push, release, deployment, installed service/network change, reset or M21 edit.
  P2 Wi-Fi/AP remains deferred; installed boot/cgroup/ARM acceptance remains open.

### P4a independent discovery/identity Runtime, 2026-10-23

Historical P4a checkpoint; P4b above supersedes its selected routing/ABI limits.

- Path: SDK -> `/run/3mm-platform/runtime.sock` -> private Core authority socket.
  Old direct Core selected dispatch is refused; there is no fallback or retry.
  Core authenticates the original app signature and current scoped identity grant
  each time. Compatibility cannot initialize/sign identity through this gate.
  Other SDK families retain their current Core path pending P4b.
- `three_mm_platform_wire` is stdlib-only. Runtime imports no Core/SDK, holds no
  DB, grants or private keys, and has a separate root-owned artifact and `.venv`
  under `/opt/3mm-platform-runtime/releases/<build-id>`. Public/private metadata
  frames are limited to 16 KiB, with 16 Runtime and four private Core handlers;
  the private hop has a three-second deadline and no automatic replay.
- Dedicated `3mm-platform` user/group, no supplementary app/key group and no global
  environment. Root prepares the client directory with app-group setgid ownership;
  `ReadWritePaths=-/run/3mm-platform` preserves it across systemd exec phases.
  Core verifies actual SO_PEERCRED UID before reading requests; Runtime generation
  comes from kernel boot/start-time/effective UID. Both directions verify the peer.
- Component archive validates exact files, sizes/hashes and Core-authority ABI 1.
  Update/rollback switches only Runtime pointers/service, verifies health and exact
  Core process/release continuity, and rolls Runtime back on failure. Interrupted
  updater transactions reconcile on the next explicit `recover`/update invocation;
  automatic boot recovery has not been installed/proved. Host service policy is
  fixed separately from the replaceable Runtime executable artifact.
- **240 passed / 0 skipped**, profile `p4`, Ubuntu/Python 3.14.4, 32.87 s pytest,
  0.79 s preparation / 35.69 s test process. Includes real Core+Runtime update,
  rollback, unhealthy candidate, kill/hang, revocation, recovery fence, private
  gate loss, no fallback and compatibility identity denial. Source:
  `b599b9efeb01ad9fc814d2c96ee244f3aafbfec3a46a1b75b89aa4748b3924e5`.
- **One additional distinct-principal case passed / 0 skipped**, 5.94 s pytest:
  real production Core gate factory at UID 1000; Runtime UID/GID 65534 without
  supplementary groups. Runtime cannot read actual test Core SQLite/transport
  keys, root cannot bypass the private peer check, and even an app-signed
  checkpoint request from the Runtime UID is refused without creating a record.
  Actual artifact update preserves Core PID/source and HTTP readiness. Root only
  orchestrates the isolated test; installed accounts/services are unchanged.
- Final service-only correction: **94 passed / 0 skipped**, systemd templates
  and release-builder checks, 2.36 s pytest / 2.98 s process, plus a successful
  real transient systemd 259 sandbox with nonroot Runtime UID and inherited
  socket group. The transient unit and its own empty `/run` directory are removed.
  Final source: `49108bc23fc17fc4c60d4c309df27c78885fdbe9c0ea25cbaa016ea10325a3a4`
  (954 files); only the Runtime unit and its template test changed after the
  240+1 results. Those unchanged process/authority results are reused.
- Broad current-consumer regression: **964 passed / 0 skipped**, profile `p3`,
  258.38 s pytest / 268.31 s process, source
  `234c8f781daece9f8939ea65697afe1b82fabeb9f37e8dc33d54fd8d586e029c`.
  Reuse unaffected cases, not a claim of a new full run against final bytes.
  Subsequent changed production definitions are private Core admission/factory,
  Runtime group setup and component/pair packaging; the P4 checks above cover
  these. Exact paths/AST changes are in `p4-source-comparison.json`. Counts overlap.
- Same dependency digest across the Linux labs:
  `157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f`.
  Frontend's 187 recorded inputs remain byte-identical: reuse P3b's 489 tests in
  57 files and successful TypeScript/production build; no frontend changes.
- Evidence: ignored `.runtime/dev-lab/evidence/p4-{main,principals,regression,unit-final}.{json,xml}`,
  `p4-systemd-socket.json`, `p4-source-comparison.json`, `p4-artifact.json`.
  Local standalone artifact: `.runtime/p4a-platform-runtime.tar`, 10,240 bytes,
  build `b91f1983e1ff3c9d630069e66eaead61002eb6dfa5570de5a664a57cb953bb80`,
  SHA-256 `d997a0e2be6b1ae07aa89bc330d35a8cff818948b1fd4c6093206b02d6747f58`.
  Build/update/probe/rollback/recover commands: action plan section 13.
- Limits: no clean-image, installed full-service/cgroup or reboot/power acceptance,
  ARM/ARMv6 Runtime trial or full CI. P2 radio test is deferred. No commit, staging,
  push, version bump, release, deployment, installed service/network or M21 change.

### P3c current transport contract and retired jobs, 2026-10-23

- The shared model/limits live in three_mm_protocol/platform_transport.py;
  ApplicationPlatformClient.discover_platform() and Core validate the same
  contract. See the [current public contract](EXTENSION_PLATFORM_V2_PUBLIC_CONTRACTS.md).
  Transport contract 1 is independent of manifest v2/SDK 1.3 and the package schema
  catalog. Supported operation names and current generations are metadata only.
- Enforced bounds: one signed JSON frame per connection, 6 MiB including newline,
  16 active handlers, five-second absolute read deadline and 35-second total SDK
  deadline. No unbounded handler queue or deadline extension from trickled bytes.
  The replay set retains up to 4096 IDs for 60 seconds and fails closed at capacity.
  SDK failures expose fixed reasons, conservative dispatch phase and no auto-retry.
- Discovery reflects the listener generation, current Core recovery guard and
  application incarnation/epoch/mode. It cannot mint/cache a grant. Existing
  sealed current admission, key/guard order, revocation and receipt/status
  adapters remain authoritative. Exact signed success fields and original Unix
  peer credentials remain intact for the relational boot transport.
- Shutdown closes pending sockets and drains handlers within a bounded wait.
  An unfinished native/DB handler keeps its capacity slot and blocks in-process
  listener restart. An absolute transport deadline cannot kill an external effect;
  independent process containment and update/rollback remain P4.
- Removed the compatibility-only scheduler, Core worker, readiness-only dispatch
  branch, engine tests and obsolete benchmark. Current package validation and
  direct gateway calls refuse jobs in every mode. The neutral reference and test
  packages no longer declare jobs. Historical rows/restore fencing and explicit
  stopped-admin outcome resolution remain, with jobs_supported=false and no new
  scheduling or retry. A new scoped scheduler is a separate feature contract.

Verification and exact reuse:

- Ubuntu WSL / Python 3.14.4, expanded p3: **957 passed / 0 skipped**, with seven
  old socket/authentication test-helper failures, 258.10 s pytest, 0.86 s
  preparation, 267.65 s test process. Base snapshot:
  **2e3c16f3ac9f25ebc6ba797680e94f6af51eb2aed2bf98c3a51413798639cb23**.
  Those seven helpers/expectations were corrected for absolute deadlines and no
  unauthenticated signed reply; no production input changed afterward.
- Follow-up: **26 passed / 0 skipped**, 6.01 s pytest, 0.78 s preparation,
  7.59 s test process. This includes all seven repaired cases plus 19 diagnostic
  checks. Final snapshot:
  **ac8281e109eecb2bbd68a7f1798d7108ff7bc990ff26d7762fc112971361df1b**.
  At the P3c handoff all 945 snapshot inputs matched. Between snapshots only six
  test files changed; their changed functions/class are recorded in the source
  comparison. The unchanged 957 passes are reused: **983 distinct current
  passing cases**, not a newly run single 983-test suite or full CI.
- Same verified dependency digest:
  157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f.
  Actual signed Unix/HTTP transport, Core survival under full SDK connections,
  malformed responses, overload/replay/deadlines, identity/command/peer/status/
  checkpoint/event/file authority, revocation/recovery and domain receipts are
  covered. Boot transport preserves real original SO_PEERCRED and exact success
  fields; this is not a new full privileged boot/device acceptance.
- Windows/Python 3.13.15: **20 passed** for framing and lab-tool checks during
  implementation. Frontend inputs are byte-identical to P3b, so reuse its
  **489 tests in 57 files and successful TypeScript/production build**; no rebuild
  or browser run was needed for this backend/SDK package. Only the reference
  module's retired-job declaration and README changed outside backend/SDK/tests.
- Evidence: ignored .runtime/dev-lab/evidence/p3c-{base,repairs}.{json,xml} and
  p3c-source-comparison.json. Base failures are explicitly superseded by the
  passing repaired cases, not hidden or relabeled. HEAD remains 2fdc3df with
  prior dirty work preserved. Diff whitespace and handoff links pass.
- No device/live service/network changes, deployment, reset, release or commit.
  Independent M21 and deferred P2 hardware acceptance remain untouched. P4 must
  still had to prove independent Runtime process/artifact/update/rollback and Core
  PID/digest continuity; P4a above now proves the selected local boundary.

### P3b legacy execution retirement and language packages, 2026-10-23

- Removed the legacy Python loader/manager, updater/monitor, install/toggle/
  update/rollback/marketplace endpoints and their direct frontend consumers.
  Enabled legacy Python payloads stay inert at startup; retired routes return
  404. Existing Extension rows/tables remain inert metadata for current menus,
  translations and historical records. No user database or archive was wiped.
- Current compiled UI/widget, declarative, application and theme contracts remain.
  Device management is a Core admin route at /devices using the existing registry,
  pairing and diagnostics contracts. No filesystem component fallback or legacy
  upload fallback remains. The AI Builder creates current compiled UI pages and
  widgets; old generated archives are download-only. Server data/relationships
  require current Runtime/application contracts, not generated in-Core Python.
- Added generic data-only language packages: strict language-extension.json inside
  manifest v2, immutable ZIP validation, admin enable/disable/delete and current
  public dictionaries. Bundled modules use the same mechanism; an operator's
  disable/delete survives restart. Bulgarian dictionaries and UI helper labels
  live in modules/language-bg, not embedded frontend/Core language branches.
  Disabling the selected language falls back to English and removes stale data.
- LanguagePack gains a nullable ModulePackage projection through migration
  0ae56c1324d5. Clean migration, existing-row upgrade and downgrade are checked;
  no migration was applied to installed devices or their live databases.

Verification and reuse:

- Ubuntu WSL / Python 3.14.4: expanded p3 profile **332 passed / 0 skipped**,
  142.87 s pytest, 1.04 s preparation, 147.30 s test process. Snapshot:
  **a5404698f28003ff3b101aa5da9aab91e8178c26200ec4be1541cb861f79af16**,
  946 files. Same dependency digest as P0-P3a:
  157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f.
  Scope includes package/language lifecycle, migrations, negative authority and
  revocation, actual lifespan/HTTP/Unix listeners, current themes/compiled UI,
  Builder and M21 production route-exclusion regressions. Lab tooling: **10 passed**.
- Windows / Node v24.19.0: pnpm exec vitest run **489 passed in 57 files**;
  pnpm run build passes TypeScript and the production build. Current frontend+
  module input identity:
  c7b591fee3775ce05e145ee5895f0dcc6dc5d09c01b1299b62b7fa583d4061fc.
  Browser review against the actual Core with disposable SQLite covered device
  management, EN/BG, light/dark, language disable -> English, re-enable -> Bulgarian
  available again, without a Core restart. Preview is stopped and its session
  tokens revoked. This Windows preview is not native Unix transport acceptance.
- Reuse is explicit: since the Linux run only trailing EOF whitespace changed in
  backend/db/language_pack.py (identical Python AST); all other snapshot inputs
  match. Since Vitest, one test-helper type assertion changed with no JavaScript
  behavior; the successful build includes it. Subsequent edits are handoff docs.
- Evidence: ignored .runtime/dev-lab/evidence/p3b-linux.{json,xml},
  p3b-source-comparison.json and p3b-frontend.json. Local HEAD remains 2fdc3df plus
  preserved dirty/new work. This is not full CI, P2 hardware acceptance, a new
  release, deployment or commit. Installed services/networks and M21 are untouched.

### P3a optional-component startup and cleanup, 2026-10-23

- One Core-owned lifecycle tracks the SDK listener, public-web gateway, existing
  update/monitor workers, legacy startup loader, event broker and job scheduler.
  Startup/factory/import failures of the two listeners and startup failures of
  optional workers no longer prevent the HTTP administration from starting.
  Constructors/imports of the SDK/public transport and job scheduler are deferred
  to their managed startup boundaries. Core DB initialization remains mandatory.
- Partial starts are cleaned immediately. Shutdown attempts every registered
  cleanup even when another fails. Task exit/failure and event/job iteration
  degradation are observable; successful iterations clear their transient state.
  This bookkeeping does not retry a failed listener or supervise/hard-kill code.
- GET /api/v1/diagnostics/components extends the existing admin diagnostics.
  It reports component states and fixed reasons (startup/worker/iteration/shutdown
  failure), with no paths, exception text, credentials or trace authority. Cache
  is disabled. Existing user revocation/blocking and admin checks are retained.
  /health remains liveness; /ready requires the Core database, not optional features.
- Both local listeners share stale-path and ownership cleanup rules. They preserve
  regular files, active listeners and replacement paths. Failed bind/permission/
  thread starts close their resources; controlled restarts can reclaim a stale
  socket. Socket permissions, signed request format, authority checks and SDK
  version 1.3 are unchanged. This is not the P4 transport/process extraction.
- At the P3a checkpoint, legacy Python loading and its consumers still remained.
  P3b above subsequently retired that path. Lifecycle exception handling itself
  is not process isolation; full P3 and the P4 extraction are not complete.

Verification:

- Ubuntu/WSL, Python 3.14.4: profile p3 **114 passed / 0 skipped**, 93.03 s pytest
  (1.36 s preparation, 96.58 s test process), snapshot
  **475f734cff8489033ab2e0d2e0fbb4989a888baa9bffb5a6d696f598dd67c57b**.
  Real FastAPI lifespan/HTTP and native Unix listeners; individual startup/import
  failures, required DB failure, healthy admin/settings/menu routes, viewer denial,
  blocked/revoked admin, signed SDK/authority reads, public read-only transport,
  existing job/update lifecycle and M21 production route-exclusion regressions.
- Additional **3 passed / 0 skipped**, 3.44 s pytest (0.78 s preparation): managed
  background-task failure after successful start and thread-start failure for each
  real listener. Final snapshot
  **60057ee5bc4d359d5c353e4e8a672a448203197511976dddb7d79343b6540a4b**.
  Only these test cases were appended after the 114 run. Runtime bytes and original
  test content match, so the earlier 114 passes are reused, not rerun or relabeled
  as one new full-suite run. All 974 snapshot files match the current source.
- Same isolated dependency digest as P0–P2:
  157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f.
  Local HEAD is still 2fdc3df plus preserved dirty/new work. Lab provenance tooling:
  **10 passed**, Windows/Python 3.13.15. Compilation and diff whitespace passed.
- Evidence: ignored .runtime/dev-lab/evidence/p3a-{base,supplement}.{json,xml}.
  No frontend changes/build, full CI, P2 hardware test, installed service/network
  change, deployment, reset, commit or publication. Independent M21 source is intact.

### P2b portal, administrator and network transaction, 2026-10-23

- EN/BG portal: Standalone/Hub/Node according to installed profile; preserve OS
  connection / explicitly managed Wi-Fi / local Standalone. Actual managed
  adapters and AP support are discovered; multiple AP adapters require explicit
  selection. Active host Wi-Fi is not repurposed as an AP. Missing AP falls back
  to LAN/console setup. No wlan0 requirement in bootstrap/preflight/activation.
- Read-only legacy status remains available as an explicit CLI option. Installed
  recovery now uses a protected LAN portal alongside healthy Core/Agent services.
  The root helper is needed for activation even on a host without NM; it has no
  mandatory NM service dependency and no steady-state Node workload requirement.
- Mutable APIs, prefill, scans, capabilities and diagnostic export require a
  15-minute console/admin-issued capability. Only its digest is persisted; issue
  rotates the previous code, completion revokes it. No public token-mint route.
  The admin UI supplies a fragment link; the portal immediately clears the
  fragment and keeps the code only in memory. Requests are bounded to 16 KiB.
- Initial Core roles create the chosen administrator against the migrated DB or
  prove the existing, unblocked administrator without changing its password.
  No implicit schema creation or promotion/reset of existing users. SQLite write
  serialization makes interrupted/concurrent setup retryable. Installer no longer
  creates a default administrator automatically. Prototype short passwords remain
  permitted by owner instruction. Minimal Node setup imports no backend or Core DB.
- Node setup records the Hub without pairing/approval. Initial response is awaiting
  pairing; recovery reports preserved enrollment, not a new enrollment claim.
  Recovery freezes role, name, locale, administrator and Hub, including an unset
  legacy Hub. Finish/cancel never invokes local Agent bootstrap for an existing role.
- Snapshot schema 2 adds secret-free network ownership/interface. Schema 1 loads
  as preserve, retaining identity. Automatic link recovery requires saved managed
  Wi-Fi, not merely an installed NetworkManager capability.
- Wi-Fi: root-owned journal outside the service user's data tree; one POSIX-locked
  transaction, provisional non-autoconnect profile, external 120-second rollback,
  local profile/address verification without Internet probes, durable metadata
  before network commit. Root receipt resolves lost replies; startup restores or
  finishes the transaction. Deletion is limited to previously owned profiles on
  the selected adapter; the ownership ledger is bounded to 16 adapters.
- A separate secret-free setup journal keeps uncommitted roles out of activation
  and suppresses AP changes during reconciliation. It survives until activation
  is acknowledged; committed setup can be finished after restarting the portal.
  Failure/reboot cannot be advertised as success just because the browser disconnected.
  The previous profile must still be usable to reconnect; storage/OS/radio failures
  remain physical recovery limits, not an uptime guarantee.
- Bootstrap diagnostics reuse P1 allowlists/budgets with setup_<attempt> IDs and
  device.setup stages. Explicit --diagnostics enables a 10-minute memory session,
  at most 1 MiB / 10 events per second. No SSIDs/passwords/accounts/tokens in events;
  zero disk spool and no Core/collector dependency.

Verification:

- Linux/Ubuntu, Python 3.14.4: **404 passed / 0 skipped**, 13.76 s pytest;
  1.06 s environment preparation, 15.46 s test process. Expanded lab profile p2
  includes provisioning, portal, account denial/concurrency, runtime, installer,
  full/Node packaging, SDK diagnostic and first-boot regressions. A separate CLI
  process uses real loopback HTTP and a disposable journal: denied public access,
  console code, host-network Node setup, revoked code, no Core DB, clean stop.
- Exact source snapshot **cf7628591741277bdbacf411a5c526169bc3d17749acaf9873365b1f53f201dd**,
  970 source files; HEAD 2fdc3df plus dirty/new source. Dependency digest remains
  157780b7b0276402845e07a72c374b5a646690a1683b64ebb6423e6dc57a2f3f.
- Shared P1 integration: **71 passed / 0 skipped**, 34.67 s on snapshot 6d27e2c9…;
  recorder/SDK/Core diagnostic inputs are unchanged in the final snapshot, so this
  evidence is reused. P1/P2 counts overlap and are not distinct coverage totals.
- Frontend: 9 portal/component checks passed; TypeScript/production build passed.
  Actual browser inspection: protected access, EN/BG role switching, no-Wi-Fi host
  choices, and preserved light/dark theme. No mobile-device or real radio test.
  Windows/Python 3.13.15 lab tooling: 10 passed, unchanged since that run.
- Evidence: ignored .runtime/dev-lab/evidence/p2b-* JSON/XML; browser previews use
  disposable .runtime/setup-preview data. No installed services or networks were
  changed, no M21 source was touched, no commit/push/release/deployment was made.

### P2a model and local activation, 2026-10-23

- Role services survive a recovery request; recovery uses a separate read-only
  loopback setup status unit, without AP/network mutation or Agent re-pairing.
  The same applies when optional status activation fails and is compensated.
- Explicit host/NM ownership controls installer packages, preflight and monitors.
  No hardware-derived Standalone default. Initial console role selection supports
  Standalone/Hub/Node; Core requires an existing DB admin, Node remains awaiting
  pairing. Journal, Hub, identities and prior recovery/policy are preserved.
- Admin recovery API and EN/BG Vue text match local recovery; full/Node packaging,
  health and older-package rollback account for the new optional status unit.
- Ubuntu/Python 3.14.4: **283 passed / 0 skipped**, 11.26 s; cached preparation
  1.19 s. Source digest `4efe69347eb623e5443122f5a2f2a4325a2b90f4b0e4a7a778d50d8552db5e86`;
  all 961 snapshot inputs match the current tree. Targeted profile is in
  `tools/dev_lab.py`; JSON/XML evidence is `.runtime/dev-lab/evidence/p2-*`.
- Real CLI process smoke on isolated WSL loopback: ready 200, configure 403,
  missing network helper, no provisioning state created; process stopped.
  Smoke's setup/CLI inputs are unchanged; final recovery pairing guard is covered
  by the final Linux tests. No installed services or networks were changed.
- Frontend/Node v24.19.0: **4 component tests passed**, TypeScript + production
  build passed. Windows/Python 3.13.15 lab tooling: **10 passed**. Shell/PowerShell
  syntax and whitespace passed. No full CI or live AP/network/hardware acceptance.
- Next is P2b (portal/admin, adapter capabilities, bounded apply/verify/rollback,
  recovery completion and local bootstrap diagnostics). Existing writable portal
  still requires Wi-Fi; explicit legacy AP still assumes `wlan0`. Do not mark P2
  complete or claim a new onboarding/deployed release. No commit/publication.

### P0 lab and audit, 2026-10-23

- Full bounded map, current contract versions, reproduction commands, initial P1
  budgets and limits: [action plan section 6](CORE_STABILIZATION_ACTION_PLAN.md#6-резултат-от-p0--2026-10-23).
- Linux user `raspberry`, Ubuntu/Python 3.14.4: P0 **77 passed / 0 skipped**,
  25.16 s pytest; first dependency setup 32.09 s. Real signed SDK identity read,
  revocation/negative cases, setup/planner/bootstrap and metadata diagnostics.
- Reused dependency environment: smoke **11 passed / 0 skipped**, 7.90 s pytest;
  preparation 1.60 s + test process 10.62 s. Smoke overlaps the P0 set.
- Windows/Python 3.13.15 tooling: **10 passed**. Source snapshots differ only by
  the new tool test file; runtime/fixture/runner/dependencies did not change.
- Exact source/dependency digests and commands are in the plan and copied JSON/XML
  under ignored `.runtime/dev-lab/evidence/`. No full CI, frontend build or live
  fault/network scenario was run; the dirty M21 copy is preserved.

### Minimal P1 diagnostics, 2026-10-23

- Shared stdlib recorder, opt-in SDK instrumentation, authenticated Core request,
  authority admission and public identity read. Admin session start/status/stop
  and bounded streaming NDJSON export extend the existing diagnostics router.
  Metadata bundle/UI are unchanged; no full debug UI yet.
- TTL 10 min default / 30 min max; two reserved allocations (Core + one SDK),
  each ≤1 MiB / 10 events/s, record ≤2 KiB, export ≤4 MiB. No disk spool.
  This does not implement a multi-worker Node quota controller (P4/P5).
  Full buffer/contended lock/rate limit drops metadata, never business work.
- Ubuntu/Python 3.14.4: P1 **71 passed / 0 skipped**, 31.19 s; complete SDK
  **275 passed / 0 skipped**, 2.74 s (4 tests overlap). Windows recorder/API
  **25 passed**, 5.09 s. Existing P0 checks of unchanged setup/planner and earlier
  command-schema cleanup evidence are reused, not reported as fresh runs.
- ARMv6/Python 3.13.5 recorder microbenchmark: 20 events/s over 15 s, 300 accepted,
  no drops; +1.709 CPU percentage points; ~3.23 MiB RSS increase with two full
  buffers. This is two allocations in one process, not full-system overhead.
- Contract, activation, exact hashes and limits: [action plan section 7](CORE_STABILIZATION_ACTION_PLAN.md#7-резултат-от-минималния-p1--2026-10-23).
  Ignored JSON/XML evidence: `.runtime/dev-lab/evidence/p1-*`.
- No installed service/network changes, frontend build, full CI, commit or
  publication. Device execution was an unprivileged stdin-only recorder probe;
  full workload/hardware recovery and persistent bootstrap diagnostics remain.

### Workflow package verification, 2026-10-23

- Content: workflow rules/docs, selector and its tests, CI scheduling; no runtime
  implementation changes. Prepared against the checkout snapshot above.
- `python -m unittest discover -s tools/tests -v`: **15 passed**, Windows/Python
  3.14.7. Results reused after documentation-only edits; selector/tests unchanged.
- Both workflow YAML files parsed; required-job failure guards and existing full
  release gates inspected. `git apply --check --whitespace=error-all` passed.
- No hosted Linux CI, full application suite, commit, push or release was run.

### Laptop continuation, 2026-10-23

- Working repository: `C:\Users\LAZ-DELL\Desktop\3mm`, HEAD `2fdc3df`.
- All eight workflow-package files match the prepared `workflow-package/after`
  content after line-ending normalization. No patch reapplication was needed.
- `git diff --check` passed. The recorded 15 selector checks remain prior-run
  evidence for unchanged selector/tests; no runtime checks were repeated here.
- Existing user changes remain in place. At this handoff Core dependency review
  had not started; the completed bounded result is recorded below. M21 is separate.

### Core simplification: exact command schemas, 2026-10-23

- Bounded dependency map: installed sources -> subjects/provider comparison ->
  policy evaluation -> context review; policy-review history also consumes the
  policy scope serializer. Key/snapshot ownership and durable grant enforcement
  remain separate responsibilities, outside this cleanup.
- Three copies of the command-schema normalization rule now call
  `application_authority_context._command_schema_data`. Removed subjects'
  `_schema_bytes`; no new module, external contract or dependency was introduced.
- Preserve typed scalar/bound differences, default empty `required`, set order,
  duplicate-enum rejection, bounded input copying and caller input immutability.
  Legacy declaration-diff reviews keep their separate advisory semantics.
- Checked content: HEAD `2fdc3df` plus the worktree changes in authority context,
  policy, subjects and `test_application_authority_subjects.py`. No runtime or
  test edits followed the successful run; only this handoff changed.
- Command: `.venv\Scripts\python.exe -m pytest -q` with
  `test_application_authority_{context,policy,subjects}.py`,
  `test_application_policy_reviews.py`, and the expanded
  `backend/tests/test_application_*_authority_context.py` file list.
- Windows / project venv Python **3.13.15**: **521 passed, 19 skipped**, 32.36 s.
  Existing fixed context/policy fingerprint vectors passed unchanged. The
  provider-schema test now exercises actual command composition and exact denial
  codes instead of only the removed private serialization helper.
- Limits: skips require real POSIX key ownership/locking; no Linux grant/lifecycle
  integration run is claimed. No full suite, frontend build, commit or push.

## Historical material

Consult detailed plans/reports only for a specific contract, decision or failure.
A dated open item does not supersede the accepted baseline. Keep unrelated
findings out of the active queue.
