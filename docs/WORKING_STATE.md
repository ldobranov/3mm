# Current working state

Updated: 2026-11-12. Start here; follow linked details only as needed.

## Product direction: extension marketplace

- Owner requirement, 2026-10-29: create a separate extension-store application
  with server and client parts. Developers can sell their own applications and
  3mm earns a commission. This is distinct from 3mm Store, the e-commerce
  application. Pricing, payments, review, licensing and delivery remain to be
  designed; this product direction does not authorize implementation now.

## Active task and next result

- **Neutral Core integration checkpoint, 2026-11-12, local checks complete.**
  Owner requests installer/updater audit, managed component transition, reviewed
  commit and push. Terminal latency particulars are set aside. No release/tag,
  version bump, deployment, reset or application/rights change is authorized.
  Keep independent `docs/CORE_SIMPLIFICATION_PLAN.md` edits outside this commit.
  Scope includes the neutral `backend/`, `components/`, `packages/` organization,
  cleanup and subsequent Core/session/diagnostic fixes already accepted below.
  Installer rollback now uses the selected immutable release's own interpreter,
  activation file and probe. Full/Node builders and installer require the complete
  activation/planner/helper closure; no runtime old-import adapters were added.
  A protected installer-only component journal covers fixed services, both Runtime
  stores and default/all instance hosts. Prove historical artifacts through the
  previous immutable release, stage neutral candidates, preserve compatible pins,
  data, scopes and disabled hosts. Stop all changed live components before restoring
  exact old pairs; resume original active roles only. Optional native host vendor
  reuse requires matching validated metadata, dependency locks and Python/platform
  identity. Completed rollback retry is explicitly requested with bootstrap
  `--retry-rolled-back`; it reaches the detached installer, retains bounded attempt
  evidence and cannot clear an interrupted transition. Existing published 0.3.11
  web/Node validators safely refuse this source-layout boundary: after publication
  use the one-time verified console bootstrap, not a forced old web/OTA operation.
  Application wheels with old SDK imports require separate adaptation; an active
  incompatible app causes global rollback, never silent app/grant rewriting.

  Checks use disposable Linux source/data, CPython 3.13.18, Node 22.22.1,
  pnpm 10.13.1 and dependency digest
  `66358e23c75f2c6e25d0349c2b6cbbd5b02fc7a792a131d87a80413858d6377b`.
  Frontend 946, starter 19, CRUD 8, strict types and build passed on original seal
  `6a64e0b1456b419e8941a373304d92ae1b1cef5570d3bdf30cca8844ebe51812`;
  all relevant inputs remain identical after CRLF normalization, so reuse them.
  Compiled UI integration 5 and direct process consumers 36/4 skipped also passed.
  Full default Python on exact-index seal
  `2731b7e9ef6f45eb5b63f750d3fddc5dced1cab8b81617a1710543f94c6fc8d2`
  completed with 7622 passed/612 skipped/3 failed/1 setup error, 2958.12s. Failures were
  a stale activation-path assertion, a test's 3s HTTP watchdog versus its intentional
  5s Runtime budget, and an inherited FastAPI route-cache mutex in forked fixtures.
  Deterministic held-parent-lock red/green proves the latter. Rebuild derived
  wrappers only in the test child; preserve endpoints, overrides and parent state.
  Use the shared 10s outer test transport watchdog, retaining explicit latency
  assertions and bounded owned thread/startup evidence. No production timeout or
  authority relaxation. Earlier incomplete/interrupted runs are not passed gates.

  Final installer/SDK/builders/tooling group: **2020 passed/8 skipped**, 448.15s,
  seal `91225cca1bced3a6e32b4b02f93544b59114b0493b7d5e4cefd004317c6af89e`,
  evidence `ci13-transition-gates-07b2924920364a009b684c7e5c8c0c43`.
  This includes the 440-pass transition/installer precheck; do not add overlapping
  totals. Actual old/current builders and validators passed for seven existing
  b134 component stores with exact pointer restoration, no services/app execution.
  Final process consumers, systemd templates, Node installer and bootstrap options:
  **580 passed/6 skipped**, 406.53s, 1724-input exact-index seal
  `063e351037d0e9c720bbb38982957c351cdc0bc777000aac543131a3121ccae9`, evidence
  `ci13-fixture-consumers-62c472dd8cf44ac2b16ab435f9c7a06d`. All four earlier
  failing scenarios now pass. This seal differs from 91225 only in bootstrap retry
  forwarding/tests. Both final groups report no source drift. Root/systemd and
  optional image-provider skips are explicit limits, not physical acceptance.
  The full default group was not rerun after these test-only fixture corrections;
  reuse its unchanged passing coverage plus all affected final consumers.
  Independent review found no remaining transition blocker. Staged Git archive
  passes actual Full builder/408-file contract closure (1720 payload files),
  with no old source roots or mutable DB/prices/output/uploads/IDE contents;
  dev launchers retain 100755. Only handoff/installation documentation changed
  after checks. Git execution and exact CI run are reported in this chat.
  Next: exact-commit main CI, then a separately agreed release/C5 installation.
  Never create a tag before green CI. No release artifact or device action here.

- **Interactive latency, 2026-11-12, bounded fix deployed; residual latency remains.**
  Owner explicitly authorizes measurement, Core fix/tests and rasp-3mm deployment;
  Terminal source/package and all rights remain unchanged. Pre-fix approved live
  probe opened in14.576s; two spaces without Enter/command got ACK in2.793s/7.912s.
  Independent read-only profiling measured current input authority563/1397/949ms;
  profiled957ms includes grant469ms, bounded JSON325ms and UI269ms (nested, not
  additive). These observations do not establish every earlier20-30s report.
  Deterministic async regressions reproduced device management/signing/direct
  polling blocking unrelated event-loop work plus a DB transaction retained
  while waiting: initial5failed/2passed. Core now runs complete sequential DB
  phases off-loop, captures plain IDs and ends snapshots before notification
  waits, then rechecks after waiting. Cancellation joins the original worker
  before dependency DB cleanup; it never repeats work. New device regression
  group11passed on Linux, including repeated cancellation and revocation.
  Per-check immutable code reuse does not cache authority across inputs; closed
  stream timing stages distinguish input/provider/ACK, queues and fresh authority.
  Inner key/SQLite/grant failures are preserved without payload/exception text.
  Existing revocation checks/timeouts/cleanup/admission remain. Frozen Linux
  integration:966passed/no skips; unchanged frontend proof reused. Core rollout
  `07a36470d0276a24b6035d3d9b43cf96ebe26fe669374c20c90c135e533daec8`
  succeeded; independent pins, four app hosts/packages and rights hashes preserved.
  However post-rollout probe opened13.986s, firstspaceACK6.753s/provider12.961ms,
  before620ms/after1089ms/ACKphase5021ms. ConcurrentCorehealth66ms; then stream
  closed before secondspace (retainedstream/deadline_exceeded25922ms). Separate
  read-only status confirms no retained session/recovery reservation. This is NOT
  accepted as fixed latency. Freshcheckprofiling964ms:47boundedJSONcopies337ms,
  4617recursiveleaves/59557Unicodegeneratorcalls. Next bounded optimization uses
  identical C JSON ASCII encoding/Unicode checks instead of per-leaf Python
  encoder/generator overhead, not cached authority. Local pure/boundary vectors
  159passed. Same actual read-only authority adapter with only that pure function
  replaced in its isolated process measured437/425/430/423ms, not an installed
  performance claim. Empty provider responses now combine the fresh post-input
  check with ACK admission after acquiring the send lock; no intervening I/O and
  no second identical check. Nonempty output retains pre-output and fresh ACK
  checks. Current runtime/UI/login/grant/human/resource checks still run before
  every input and at the post-effect boundary. New regressions cover next-input
  revalidation, revocation during provider work and revocation while ACK queues
  behind a send. Final frozen Linux/Python3.14: **1978passed,3skipped**,704.66s;
  skips are foreign-UID/root and non-POSIX refusal harnesses, not session tests.
  Focused159pure/4ACK passes overlap this run and are not added to it. Unchanged
  frontend tests/type/build proof reused; no new frontend build. Checked all1886
  frozen inputs: exactly6 source/test/docs files differ from the first latency
  rollout (context/browser, their tests, diagnostics/diary). Default host inputs
  and every independent component input remain identical to that first rollout.
  Standard immutable Core deployment **succeeded** on owner-pinned192.168.1.88,
  key `9ee7efe7f62b298c4c9c64dc0637ccca7d86e19e15242573a1c530ecea86443d`,
  release `local-9ee7efe7f62b298c4c9c64dc`, install199.875s. Six base/four app
  services active, zero restarts; Core/Agent/Web smoke ready. Agent/Runtime,
  active/inactive executor pins, four app-host pins/active metadata, host policy,
  local-session flag and native/service/human rights hashes match preflight.
  Terminal1.0.5 package and its host are unchanged; no app/permission approval.
  Final approved probe opened13.080s and ACKed two spaces in**965.90/3609.67ms**;
  input-provider9.599/6.592ms, concurrent readiness27.75/58.93ms. Both inputs
  succeeded, normal close completed, read-only recovery confirmed no owned lease,
  own diagnostic recording stopped and own login logged out (exit0). No Enter
  or command executed. Output timing is not correlated echo; it does not prove
  end-user visible per-character latency. Recorder dropped9/1rate-limited spans,
  so phase evidence is partial and nested/concurrent spans are not additive.
  Improvement is measured, not proof of instantaneous typing or that every
  earlier20-30s spike is eliminated. Residual per-check/current-authority cost
  and queueing remain; do not hide it by disabling checks/increasing timeouts.
  Next: owner practical typing/connection acceptance; further optimization must
  preserve fresh UI/login/human/M20/resource/runtime checks. No Terminal source,
  Agent/executor update, rights, reboot/reset, separate backup or Git/version
  action. Only normal automatic installer rollback copies. Evidence/helpers are
  `.runtime/diagnostic-cases/input{,-fast}-{prepared,baseline,dispatch}.json`,
  checked bundles, `review-input{,-fast}.py`, `accept-input.ps1` and the bounded
  read-side/live latency probes. Only this handoff documentation changed after
  final checks/input review; no later production code is claimed as tested.

- **Terminal connected, slow input inspection, 2026-11-12, read-only.** Owner
  confirms a successful connection and command, but reports 20-30 seconds per
  character and several attempts to connect. `diagnostic-cases (4).json` retains
  two post-opening failures: `session.input/session_runtime_failed` and
  `session.input/session_authority_unavailable`. Their40s/144s durations cover
  the session attempt, not measured individual keystrokes. No retained opening
  failure in this export does not disprove the owner's failed attempts. Concurrent
  Agent authority exchanges include409 and500; three500s took about5057ms, one
  provider read also500/about5057ms. The export does not establish SQLite lock
  contention or revoked rights; detailed recording was inactive, no dropped cases.
  Pinned-device read-only inspection: Core/Agent/Runtime active, zero restarts;
  ten-second sample Core85.8%of one CPU, Agent2.1%, Runtime0.6%. This is total
  process load, not proof that Terminal alone caused it. Bounded retained-journal
  filtering yielded no allowlisted exception/stack evidence for that interval.
  Source has at least three current-authority checks per input plus independent
  output checks, serialized by the session service's authority lock. Each check
  verifies UI and current M20 authority; the stream does not use existing
  operation-local immutable-code reuse. Separately, async device exchange still
  does synchronous DB/signing work on its event loop. Neither finding alone
  demonstrates the reported20-30s delay. A separate low-priority read-only
  process, using Core's actual unprivileged UID, measured warm package/UI
  verification at about26ms versus3.5-4ms for same-operation reuse (first cold
  package120ms). This improvement cannot explain the whole delay. Earlier helper
  setup/ownership refusals occurred only in standalone diagnostics; they are not
  installed Core failures and produced no valid latency measurement.
  No production code, Terminal package, grants, session, service or deployment
  changed; no tests run for this inspection. Owner's live command acceptance is
  distinct from agent-driven verification. Helpers are ignored
  `.runtime/diagnostic-cases/{inspect-terminal-latency,profile-terminal-code}.py`.
  Next bounded proposal: Core per-input queue/current-authority/provider/ack and
  output timing plus preserved closed inner authority-failure categories, then
  fix the demonstrated bottleneck. Keep fresh revocation/login/resource checks;
  no cached grants, blind timeout increase or claimed root cause yet.

- **Session executor early ownership, 2026-11-12, deployed.**
  Owner requested Core/executor startup diagnostics, tests and rasp-3mm deployment;
  Terminal package/source and all rights remain out of scope. Private worker IPC2
  separates trusted session/profile/cgroup ownership from final provider readiness.
  Core retains ownership before transferring/loading the reviewed wheel; this
  permits existing OS cleanup proof after pre-ready cancellation, never session
  I/O or admission. Closed startup categories distinguish initial/repeated current
  authorization, connection/bootstrap/ownership, artifact verification, provider
  import/open and ready. Preserve original failure before later checks/cleanup;
  no exception messages, terminal text or tokens cross the diagnostic channel.
  Existing authority, startup deadlines, policy pins, immutable component delivery
  and OS cleanup fences stay in place. This supersedes the check-only scope of
  the immediately preceding inspection below, not its observed evidence.
  Frozen Linux/Python3.14 source checks: **505 passed, 2 skipped**, 260.21s;
  skips require the separate disposable root/systemd acceptance harness. These
  include real stream cancellation before ready, exact identity/policy rejection,
  first-failure redaction, current permission/revocation, recovery, remote stream
  consumers and immutable component packaging/control. OS cleanup observations
  in the new stream fixture are explicit doubles, not physical systemd proof.
  Earlier102/15/4 targeted passes overlap this run and are not added to it.
  Unchanged checked frontend/type/build proof reused; no new frontend build.
  Reviewed all1884 frozen inputs against the immediately installed bundle:
  exactly11 scoped source/test/diary files differ. No Agent update selected;
  the default-host source delta is solely the diagnostic vocabulary, not app code.
  Only handoff documentation changed after these checks and exact-input review.
  Normal immutable Core deployment **succeeded** on owner-pinned192.168.1.88,
  key `1f4fd8de12ff772ec6fd5276afe894458deda627710cad8a23b86d2712c9030a`,
  release `local-1f4fd8de12ff772ec6fd5276` (Core install200.819s).
  Then the active host-account executor updated through its standard journal/
  health/rollback controller from `f03e538bb87de50255aeb56fd3fd267682373104f4f830cbed951e61bc967fb6`
  to `aec51dd4a0d27d5009fa3ebac8529d600dadd2ce833e2821abf19178ed8166e9`.
  Core PID134674/generation stayed unchanged across this independent update.
  All six base/four app services active, zero restarts; release smoke ready.
  Agent/Runtime pins, four existing application-host pins, active app metadata,
  enabled host policy and local-session flag match immediate preflight. The normal
  rollout published default template `16bd387a2963db4d38d93a1cd8ecbb6f009e930094b9b111bbc427b3a8b2d94f`
  for new instances only (catalog-only source delta); Terminal's own host and
  package1.0.5 were not updated. Inactive isolated executor remains inactive and
  pinned to its old artifact; rebuild/update it before separately enabling that
  profile with the new private IPC. No enabling of unused components is implied.
  Fresh read-only authenticated Terminal discovery: HTTP200, one available
  target, trace `invoke_9c24f8303b2e4fc2ad46b797dbc9c3b5`, no retained Core refusal;
  own diagnostic logout succeeded. No ticket/session, Terminal source/package,
  permission or grant action, timeout increase, reboot, reset or Git/version action.
  Only normal installer rollback copy; no separate backup. Two helper transport/
  import refusals preceded any executor mutation; read-only inspection confirmed
  old pin/no pending transaction before the successful standard update.
  Evidence is `.runtime/diagnostic-cases/startup-{prepared,baseline,dispatch,plan}.json`,
  bundle checks, `review-startup.py` and `startup-executor.ps1`. Next: owner opens
  Terminal again and tries Connect once; retain a fresh diagnostic case if refused.
  Live PTY execution and resolution of the earlier unknown inner timeout are not
  claimed by metadata readiness or discovery alone.

- **Opening/cleanup inspection, 2026-11-12, read-only owner request.** Bounded
  retained Core journal inspection returned only closed allowlisted labels:
  `opening/timeout` at08:07:28.194983UTC and
  `provider_cleanup_unconfirmed` at08:07:28.214203UTC. The latter is provider
  close/proof failure, not the distinct cleanup-audit failure branch. The same
  attempt's host worker is failed/exit1/MainPID0 with no retained cgroup identity;
  no Connect, cleanup confirmation, service action or rights change was performed.
  Source establishes a recoverability gap: `SessionChannelProvider.open()` stores
  `self.cgroup` only after the final ready response, which the worker sends only
  after `provider.open()`. A timeout/cancellation before that response leaves no
  trusted worker identity. `_wait_empty()` and later `confirm_cleanup()` correctly
  refuse when it is absent; they cannot resolve that missing evidence merely
  because a worker has exited. Existing private-fixture cases reproduce this
  fence: **4 passed**, Windows, 0.16s; not Linux/systemd acceptance or a new
  production fix. This does not directly inspect the retained Core object's
  cgroup or establish which inner deadline caused the first opening failure.
  Per-startup authorization and executor substeps are merged as `opening`, while
  worker exceptions/stdio are discarded. No exact root-cause claim beyond these
  observations is justified by the retained evidence. Proposed scoped follow-up:
  trusted pre-ready worker ownership evidence and closed startup failure phases,
  preserving admission, cancellation and OS cleanup proof. No implementation or
  deployment authorized by this check-only turn. Helper is
  `.runtime/diagnostic-cases/inspect-opening.py`; no separate tracked report.

- **Terminal startup after reader fix, owner export10:08 EET, 2026-11-12.**
  `Downloads/diagnostic-cases (3).json` has no retained key-busy/empty-target
  refusal: the owner now reaches a redeemed WebSocket attempt. Trace
  `invoke_617565e4a9ca4e3f89df55736bba1515` records `session.opening /
  deadline_exceeded` at17655.346ms, then `session.cleanup /
  session_cleanup_unconfirmed` at17673.053ms. The later ticket403 under
  `invoke_2a621713f8964f48870aea2c8eef5700` is `session_binding_busy`,
  not evidence of human permission denial. It is the subsequent reservation fence,
  not the first startup failure. All probed Core/Agent/Runtime/Public Web were
  ready; detailed recording inactive and no dropped cases.
  Read-only installed inspection confirmed one `console` recovery entry
  `ses_761def5fa72cfdcb8045a6e1e0c3a41d`, `cleanup_required`. A host worker was
  active10:07:13→10:07:29 and ended with exit1, MainPID0; two older failed units
  are historical, not new failures. This does not prove whether a PTY ever
  started or authorize removing the reservation. No cleanup/retry/Connect,
  restart, rights/application/source behavior change; own inspection login closed.
  Existing worker deliberately discards all exception detail/stdio, and Core's
  opening category covers initial authorization, periodic authorization and
  executor startup. Neither the export nor status alone identifies which inner
  deadline/worker stage failed; do not assume slow startup, permission denial,
  Terminal code or increase timeouts blindly. Next bounded proposal: instrument
  and reproduce the host-session startup/authorization/cleanup boundary with
  closed safe categories, then fix the demonstrated failure. A worker-component
  change/deploy is separate from the completed Core reader-only rollout below.
  Inspection helper: `.runtime/diagnostic-cases/inspect-session-recovery.py`.

- **Session verification readers, 2026-11-12, deployed.** Owner
  approved the bounded Core fix and deployment to rasp-3mm. Genuine POSIX shared
  key leases reproduced both failures before the fix: HTTP discovery omitted its
  target and M20 admission refused another reader. Both now pass after changing
  only session browser `_resource` and authority `_resolve` to `read_locked()`.
  Fresh key-before-DB snapshots, current grants/login/package checks, exclusive
  writers and no provider work under a lease remain unchanged. New regressions
  also cover writer exclusion, post-reader cleanup and human permission removal.
  Frozen-source session/keys/revocation/diagnostics checks: **247 passed, 2
  skipped**, 291.38s. The skips are the separately root-run foreign-UID case and
  the non-POSIX-only refusal; actual Linux shared-reader/exclusive-writer,
  rotation and denial/revocation checks passed. The two initial red/green
  regressions are included, not added again. Identical frontend proof reused:
  946 tests, type-check and production build; no frontend inputs changed.
  All1883 frozen inputs reviewed against the immediately installed bundle:
  exactly the two production readers, their two test files and this diary differ.
  Native-host inputs identical; no Agent update selected. Only this handoff
  documentation changed after the frozen checks/delta review.
  Normal immutable Core-only deployment **succeeded** on owner-pinned
  192.168.1.88, key
  `3d679e1b5fd0cc87b2584c0c0beaa030bfd462ab294bccf41d849c2d2c41eca7`, release
  `local-3d679e1b5fd0cc87b2584c0c` (install201.537s). Core PID121842; six base and
  four application services active, zero restarts; release health smoke passed.
  Agent/Runtime/app-host/default-host pins, active app metadata, enabled host
  session policy/flag all match immediate preflight. One authenticated installed
  Terminal1.0.5 discovery read returned HTTP200, one target, one available, no
  Core refusal for trace `invoke_f871b5b039034f98b9ba08db4006b77e`; own login
  closed successfully. No ticket/terminal session/app invocation, grant change,
  Terminal source/package edit, timeout increase, reboot or Git/version action.
  Only the normal automatic installer rollback copy; no separate backup.
  Evidence: `.runtime/diagnostic-cases/session-readers-{prepared,baseline,dispatch}.json`,
  immutable checks and `review-session-readers.py`. Next: owner reloads Terminal
  and tries Connect once; if a different boundary fails, retain the fresh case
  before hard reload/logout. Live terminal execution has not been claimed.

- **Terminal contention identified, 2026-11-12 09:39 EET export.** Read-only
  analysis of `Downloads/diagnostic-cases (2).json` now correlates browser
  `session.resolve / targets_empty` and Core `authority.key_acquire /
  review_key_busy` under `invoke_b466d85a493f4725b30a99d45af6faf0`. Two discovery
  refusals coalesced, latest HTTP200 duration2517.131ms, `handled_refusal=true`,
  phase `not_dispatched`; no detailed recording or loss counters. The specific
  refusal is key-lock contention, not an observed human-permission denial or a
  started/failed Linux terminal. Inspection found exclusive `keys.locked()` in
  the read-only browser `_resource` and M20 session authority `_resolve` paths,
  whereas the existing key adapter already supports verification-only shared
  `read_locked()` leases and enforces no sealing on them. The export does not
  identify the competing lease holder; do not claim an exact writer or a proven
  deadlock. Proposed bounded next fix: audit these read consumers and use shared
  verification leases where no write occurs, retaining fresh snapshots, key→DB
  order, revocation/current-package checks and exclusive writers. Check real
  concurrent shared-reader/writer exclusion and session denial/revocation before
  rollout; do not merely increase timeouts or change rights. Core/Agent/Runtime
  probes were ready. Public Web probe was unavailable, a separate observation
  not established as Terminal's cause. Offline CLI explanation passed; no source
  behavior, device, rights or Terminal application change in this analysis turn.

- **Handled discovery refusals, 2026-11-12, deployed.** Owner requested
  implementation and deployment after the Terminal export triage. Core now
  explicitly retains a handled discovery-resource refusal in the existing bounded
  admin ring even when its public response is HTTP200; it preserves the original
  closed reason/stage and response trace, marks `handled_refusal`, and does not
  expose the rejected target. Ordinary successful reads remain unrecorded.
  Browser `targets_empty` now differs from a nonempty-list ID mismatch; Settings
  and the offline CLI distinguish HTTP success from resource admission. No access
  check, public target schema, ticket behavior, timeout or replay fence changed.
  Frozen final preparation passed **946 frontend tests**, type-check/production
  build and **345 targeted Linux diagnostics/session authority/CLI/deployment
  checks**, no skips. This includes real sealed-grant revocation with no provider
  start. Earlier targeted46/47 runs are not added again; Windows-only temp/
  permission issues were superseded by the Linux run, not counted as acceptance.
  Compared all1883 inputs against the prior accepted bundle: exactly the agreed
  15 files differ; native-host inputs identical and no Agent update selected.
  Normal immutable deployment **succeeded** on owner-pinned192.168.1.88, key
  `34dd1d41ad3fd7c7ac1942d3842fcacd654cc9ee043885a2b36c45c0957a12b1`, release
  `local-34dd1d41ad3fd7c7ac1942d3` (Core install209.474s). Core PID107056, all six
  base/four app services active, zero restarts; release health smoke passed.
  Agent/Runtime/app-host/default-host pins, active application metadata and
  enabled host-session policy/flag match immediate preflight. Actually served
  browser assets match the exact checked hashes and contain `targets_empty`.
  One normal authenticated read of installed Terminal1.0.5 discovery returned
  HTTP200, one target, one available; no retained Core refusal for trace
  `invoke_4ed8f0853b324270a446f56d4686b0ec`. This does not prove the browser caller
  selected the right ID or exclude a transient earlier refusal. Own diagnostic
  login was closed; no ticket, terminal connection, app invocation or grant
  action. Evidence: `.runtime/diagnostic-cases/discovery-prepared.json`,
  `discovery-baseline.json`, `discovery-dispatch.json`, immutable bundle checks
  and `review-discovery.py`. Normal automatic rollback copy only; no separate
  backup, reboot, Terminal edit, Git or version action. Next: owner hard-reloads
  Terminal once, attempts Connect once and collects within the same page without
  another hard reload/logout if it fails. Underlying Terminal cause remains open.

- **Browser-local diagnostic gaps, 2026-11-12, deployed follow-up.** Owner approved
  capturing the generic Core browser adapter's missing boundaries; no Terminal
  source, rights or session invocation is in scope. Local refusals now retain
  closed first-failed stage/cause, optional last-passed stage and whether an HTTP
  response was observed. This covers missing injected host/build, host identity/
  feature/operation validation, target decoding/duplicates/resolution, exact
  request mismatch, ticket validation, socket setup and stream/callback failures.
  Each successful response keeps its own validated Core trace; concurrent reads
  do not share a last-response identifier. Wrapped errors preserve the first
  diagnostic observation without duplicate causes. Public errors, validation,
  access checks, existing timeouts and no-replay fences remain unchanged. Browser
  history stays bounded to100 entries/15min, page-local, with no background upload,
  payloads, addresses, target options, terminal text or exception messages.
  Settings displays these checks separately from authenticated Core outcomes;
  its JSON and offline CLI expose safe browser observations without trusting
  imported descriptions or claimed execution. CLI checks reject unknown labels.
  **225 targeted frontend tests across14 files +10 CLI tests passed**; final92
  changed-boundary tests, type-check and production build also passed after the
  last label-validation hardening (not counted twice; unchanged133 consumer tests
  reused). Built public entry reexports exactly the same four runtime symbols;
  host/Settings share one emitted browser diagnostic module. Earlier backend/
  device evidence is not relabelled as testing this frontend follow-up. Actual
  card layout checked in light desktop/dark390px with fixed local data, including
  trace filtering and long IDs; preview stopped and temporary tab closed.
  Owner then explicitly requested deployment. Normal frozen-source preparation
  passed **944 frontend tests**, type-check/build and **61 targeted Python/CLI/
  deployment checks**, no skips. Compared all1883 source inputs against the prior
  bundle: only the agreed13 diagnostic frontend/CLI/test/doc files differ; native
  host inputs remain identical and no Agent update is selected. Immutable deploy
  **succeeded** on the same owner-pinned192.168.1.88, key
  `e2c066b779884dcf7dfd36654b2ec29494d163920d9f255ea9a8b816d296e24b`, release
  `local-e2c066b779884dcf7dfd3665` (Core install201.400s). Core PID100528, six base
  services and four application services active with zero restarts. Read-only
  release smoke passed. Agent/Runtime, existing app-hosts/default host, active
  application metadata, enabled host policy and local-session flag all match
  immediate preflight. Served index/public entry/shared diagnostic assets match
  the exact checked build hashes; new browser cause/stage labels are present.
  Only normal automatic installer rollback copy; no separate backup or reboot.
  Evidence/dispatch: `.runtime/diagnostic-cases/browser-prepared.json`,
  `browser-baseline.json`, `browser-dispatch.json` and immutable bundle checks.
  No application source/package, approval, session opening, Git or version action.
  The follow-up export below captures the failed browser boundary; the underlying
  reason for the absent target remains unproven. The source's empty-backend socket
  refusal is distinguishable but intentionally not changed or assumed to be the
  installed failure.

- **Terminal export triage, 2026-11-12 07:51 EET.** Read-only analysis of
  `Downloads/diagnostic-cases (1).json` and the current adapter/server consumers:
  browser trace `invoke_96276153b3c640808d0f9b1f72a5312b` records
  `session.resolve / target_not_found`, last passed `session.targets.response`,
  response observed. The adapter received a schema-valid target response but
  found zero matching binding/device IDs; it failed before ticket dispatch or
  WebSocket setup. This client observation does not establish whether the list
  was empty or the caller supplied a different ID. Server `targets()` silently
  omits resources when current grant/human permission/device admission fails,
  so HTTP200 does not exclude an authority failure. Runtime absence alone instead
  marks a returned target unavailable. Detailed recording was inactive; no Core
  failure for this trace is retained because the endpoint can return HTTP200
  after handling a per-resource refusal. The separate backup-preview503 belongs
  to another trace and is not evidence about Terminal. Next bounded result:
  retain closed per-resource discovery refusal categories/correlation without
  exposing undisclosed targets, and distinguish an empty response from a caller
  ID mismatch. Do not assume a socket, Linux-account or Terminal-source defect.
  No code/device/rights change or runtime test; offline CLI explanation passed.

- **Owner diagnostic export, 2026-11-12 06:57 EET.** Read-only review of
  `Downloads/diagnostic-cases.json`: no Core cases, detailed records or browser
  observations; recording has no session identity and is inactive. Two failure
  groups expired under15min retention. Core history identity matches the installed
  acceptance export from00:21 EET, so the current empty ring is not explained by
  a different history instance. Ready probes do not prove Terminal execution.
  This export contains no new ticket403 or evidence establishing its cause.
  Source inspection found an actual remaining coverage gap: local target-response
  validation and `resolveTarget` refusals occur outside the HTTP request catch and
  `open` catch; successful HTTP followed by UI-contract refusal can therefore be
  absent from both rings. This is not proof that this exact Terminal failure took
  that path. Next proposed result: capture those generic Core browser-adapter
  boundaries with closed stage/cause labels and original validated trace when
  available; no Terminal edits, authority bypass or repeat/open action. Only
  analysis performed in this turn; no runtime change or deployment.

- **Shared diagnostic cases, 2026-11-12.** Owner approved implementation and
  deployment to the verified `rasp-3mm`, without Terminal application edits,
  approval changes or opening a session. Extended the existing bounded failure
  ring/recorder/workspace, not a second service. HTTP4xx/5xx (including403) and
  session target/ticket/WebSocket refusals now retain closed stage/cause labels,
  correlated server identifiers and explicit dispatch uncertainty. Repetitions
  coalesce for30s, retain a count/latest8 identifiers; bounds remain100 groups,
  128KiB,15min with loss counters. No bodies, terminal text, credentials or
  arbitrary exception messages. Browser metadata is separately marked untrusted,
  page-local and bounded; network absence is not labelled DNS/non-execution.
  Admin-only `/api/v1/diagnostics/cases` and `/cases/export`, the Settings case
  cards and read-only `python -m tools.diagnostics collect/explain` share the
  versioned evidence/catalog. Detailed next-user-attempt recording expires after
  two minutes; collection never invokes an app, replays or changes rights.
  Missing/partial observations and uncollected remote producers are explicit.
  Linux Python3.14 frozen source `ec6f0ffdba8e…`: **156 diagnostics/CLI +124
  session authority/browser/runtime +108 consumers =388 passed, no skips**.
  Final preparation passed **921 frontend tests**, type-check/production build
  and **51 targeted case/failure-ring/deployment checks**. Compared all1233
  Python files shared by the frozen lab and prepared source: hashes match;
  the388 Linux checks are reused on unchanged Python, not relabelled as full CI.
  Light desktop/dark390px layout, long route/IDs and empty filtering were
  visually checked. Windows-only fixture/permission limitations were superseded
  by the successful Linux runs, not counted as acceptance. The normal immutable
  deployment **succeeded** on pinned192.168.1.88: bundle
  `32179317806fb5b18a04a47b372f5a041a1d50f7827a2867b7ce45a90e09a6fb`,
  release `local-32179317806fb5b18a04a47b` (Core install243.960s, host prepare
  31.676s/default publication40.814s). Core PID40288, all six base services
  active with zero restarts; all four existing application services are active
  with zero restarts, and read-only release smoke passed. Agent/Runtime and
  all four existing app-host pins, active.json hashes, enabled host policy and
  running local-session flag match the immediate preflight. Normal publication
  created default host `93f515a26831cedd2800fda144ba0207b7961b769a0fd99ae9eae4c484636096`
  for future instances; existing application hosts were not switched. Only the
  normal automatic installer rollback copy; no separate backup or device reboot.
  Installed admin-only case read/export and a controlled invalid read (422)
  passed; the same exported evidence was explained by the local CLI. Temporary
  admin login was closed; no app/session/LCD invocation or approval was performed.
  Local dispatch/evidence: `.runtime/diagnostic-cases/` (`prepared.json`, checked
  bundle, `baseline.json`, `installed-case.json`). Lab temporary XML files were
  cleaned with their disposable runs; the runner results above are observed
  stdout evidence, not claimed permanent XML. The original Terminal refusal is
  not claimed fixed: a fresh owner attempt will supply its new case. No Git or
  version action. No background browser preview remains running.

- **Terminal connection triage, 2026-11-11, Core-only scope.** Owner installed
  Terminal1.0.5 and reports `Application host: unavailable`; do not edit that
  separately maintained application or change its approvals. Read-only checks
  on the verified `rasp-3mm` found current Core PID24496 and all four application
  services active with zero restarts; host socket is listening. Running Core's
  local-session flag and root host policy are now enabled by the owner (this
  supersedes the deployment-time disabled state below). Last30min bounded Core
  initial access metadata showed session-target GETs returning200, no ticket POST
  in that initial window, and no active host workers; later checks below found
  three ticket403 refusals. Neither observation proves a host crash. Owner supplied a valid200
  target response (`console`, available=true, reviewed80x24). Current Core adapter
  plus the separate app's read-only transport reproduced that response through
  the mocked ticket POST; **18 session-browser adapter tests passed**, including
  a new named-binding/open regression. The served Core main asset also contains
  the expected binding-or-device lookup. Owner's hard reload still fails with
  `main-DQXtKx1d.js`; served code's decoder/open matcher matches source. Installed
  Terminal source matches the local1.0.5 ZIP; public build
  `9671c09f99bfaf5b97482f56122498e2680e623a37c2f39493ca64618e2b33a4`
  entry `terminal-BybsgaMv.mjs` also matches the relevant transport logic.
  Frontend type-check passed; prior18 adapter checks reused unchanged. Owner's
  temporary DevTools breakpoint captured the actual rejection in the Core HTTP
  wrapper (`request -> targets -> resolveTarget`), not target decoding. Read-only
  browser Console inspection confirmed `ERR_NAME_NOT_RESOLVED` for the session
  GET, appearance and login refresh at `rasp-3mm.local`. DNS currently resolves
  to the pinned192.168.1.88 again; name resolution is intermittent. Three earlier
  ticket POSTs also returned403 (confirmed in bounded server access metadata),
  but their original response bodies are unavailable in the current Network log.
  Both IP80 and hostname80 are already in running Core's exact allowed origins;
  FRONTEND_URL is http://192.168.1.88. Owner confirms the same failure through IP,
  so intermittent DNS is incidental, not the explanation for the terminal refusal.
  Owner export `3mm-operation-records (7).ndjson` covers23:15:14-23:15:52 EET:
  all22 records are successful Crypto Monitor operations (one invocation's four
  spans,7 discoveries,8 lookups,3 submissions); none is a Terminal/session record,
  and no records were dropped. The session target/ticket handlers currently do
  not emit operation diagnostics, while the recent-HTTP ring records409/5xx,
  not403. Thus this export cannot identify the observed ticket403's underlying
  cause. Next: inspect a fresh ticket403 response/payload without headers/tokens;
  distinguish UI binding, current authority/runtime, and reservation refusal.
  No production
  fix is demonstrated yet; do not bypass admission or treat DNS as the403 cause.
  A separate same-origin empty-backend WebSocket guard issue was noted, but it
  occurs after ticket issuance and is not treated as this pre-ticket refusal.
  No session opened, app invocation, rights change, restart or Terminal edit.

- **Host-profile platform deployment authorized, 2026-11-11.** Owner asked to
  deploy to `rasp-3mm` while the separate chat adapts Terminal. This is a bounded
  **CAP15 (sessions/streams) + CAP20 (execution/resource profile)** result;
  historical **M21** is the interactive-session mechanism, not CAP21 authoring.
  Target identity was verified against the owner's fresh host pin. Existing
  Core0.3.11 `local-134d26bd7c708fbbbf40a4a5` was ready, all observed base services
  active and no conflicting rollout was present. Normal checked bundle:
  `5c9767f037a3450644d1090ab94c94cf6a99aafd7ff965fb2b03d99f9ee099f0`,
  candidate `local-5c9767f037a3450644d1090a`. Fresh preparation passed **916
  frontend tests**, type-check/build and **63 deployment/provisioning checks**;
  source evidence from the preceding bounded work is retained, not relabelled
  as a full CI/release gate. The standard detached immutable deployment
  **succeeded** (345.478s Core install,31.713s host preparation,30.047s default
  publication). Installed read-only acceptance passed: Core PID19625, Core/
  Agent/Web ready, six base services active with zero restarts. Agent/Runtime
  and all three pre-existing application-host pins match the baseline. Default
  host `4dae3b8d9e0f961e95f0d992bf8c9598fed424d77a0098b2b4d36e031139ed68`
  has the exact current SDK guard and checked host spec. Separate worker
  `f03e538bb87de50255aeb56fd3fd267682373104f4f830cbed951e61bc967fb6`
  imported successfully as the fixed password-locked account UID993/GID980,
  without loading a provider or opening a session. Root policy, running/disk
  local-session flag and host socket are all disabled; no host worker runs.
  No Terminal activation, grants, separate backup,
  device reboot, Git action or version change; only the normal automatic
  installer rollback copy. PiWheels had intermittent verified-HTTPS disconnects
  during dependency installation; standard retries completed, no TLS bypass or
  second deployment was used. All SSH/log observers are closed. The host memory
  controller is still absent: installed RAM-limit enforcement is not proven;
  actual systemd/PTY/file/revocation acceptance remains separate after Terminal
  adaptation and explicit host opt-in. Evidence/dispatch receipt and
  `installed-acceptance.json`: `.runtime/host-session-deployment/`.

- **Local host-account session profile implemented locally, 2026-11-11.** Owner
  confirmed a separate unprivileged account, not raspberry/root. The generic
  `host_account_session_v1` profile now resolves one fixed `3mm-terminal` account,
  private persistent home and root policy generation into exact M20 review.
  A separate immutable executor/socket and SDK process guard retain current
  package/resource/human admission, bounded streams, lease/policy checks and
  cgroup cleanup. Changed policy/account invalidates the old grant; remote
  executors explicitly refuse host identity. Isolated resources retain their
  previous wire shape and executor, with no automatic fallback. No browser
  account/shell/environment selection, root, sudo, IP networking or device access.
  Installer preparation is disabled by default and preserves prior root policy
  decisions. UI approval shows real-file/native-code access and shared account
  warning outside collapsed details. Canonical scope/opt-in/acceptance guide:
  `docs/HOST_ACCOUNT_SESSIONS.md`.

  Linux source evidence: protocol/local authority group **42 passed**, then an
  existing cold mounted-source router subprocess hit its unchanged30s budget;
  that exact router **passed alone** without a timeout change. Channel/browser/
  session admission group **128 passed**; context/source/recovery/catalog group
  **178 passed**; remote guard **7 passed**. Worker/SDK/isolated stream group
  **84 passed**, then **23 focused cases passed** including the final shared-UID
  alias refusal (overlapping coverage, not additive totals). Deployment evidence:
  **391 release/provisioning**, **16 final host profile**, **18 native artifact/
  rollback** checks passed; original390-case group retains unchanged full Node
  installer evidence. The **18 native artifact cases passed again** after the
  final UID check (`artifact-final.xml`), no skips. Evidence folders: `.runtime/host-session-profile/`,
  `.runtime/host-session/`, `.runtime/host-session-deployment/`. Frontend **91
  targeted tests**, TypeScript and production build passed with existing
  dependencies. Responsive/theme/source review only, no browser visual trial.

  These are source/transport/artifact tests with OS identity and systemd doubled,
  not installed Linux/shell acceptance. Reviewed native code shares one home
  across users/apps and is not hostile-code isolation; a blocked provider may
  last until the OS900s limit. Cleanup remains fenced without exact OS evidence.
  Persistent home is not part of Core/application backups. External Terminal
  still needs its declaration/SDK guard adapted separately. Fresh ordinary
  SDK-storage session apps use service activation then consent; generic inactive
  staging for session-provider upgrades/configuration and required relational+
  self-session first registration remain unsupported. Do not silently weaken
  inert provenance to bypass these limits. No commit, deployment, live account,
  service/grant change, shell or external Terminal/Monitor source edit this slice.

- **Optional resource preparation fixed locally, 2026-11-11.** Owner authorized
  the generic fix after confirming Child Center0.7.23 activates without readers.
  Changed optional device/query selections on the same stopped package now go
  through `/stage` and fresh consent, not direct `/activate`. The Core preserves
  the exact configuration/approval fence, original signed registration, previous
  package pointer, instance identity and own data. Configuration-only transitions
  authenticate existing provenance before mutation and never repair corrupt or
  missing inert proof. Active/stale/unauthorized requests are refused; uncertain
  UI replies do not trigger automatic activation or repeated preparation.
  Dedicated relational/session-provider preparation remains separate.
  Relevant UI checks: **58 passed**, TypeScript and production build passed on
  the existing Node24.19/Vite6.4.3 toolchain, no dependency changes. Existing
  responsive dialog/theme classes and new EN/BG text were reviewed; no browser
  visual trial was performed. Linux targeted
  staging checks: **37 unchanged cases reused + 4 current first-registration
  cases passed** (both inert/previously active and staged/connector provenance).
  Adjacent authority/configuration/activation consumers: **168 passed**, no
  skips. These are source tests with real seals/HTTP/database and doubled runtime
  helper/compiler, not a physical installation trial. Evidence folder:
  `.runtime/optional-device-configuration/`. No commit, deployment, new package,
  live grant/activation, SSH or Child Center/Monitor source edits.

  Diagnosis preceding the fix: exact local Child Center ZIP validates with current
  rules: `3e879053bbc1e805e31e16c4712017313ed04f4a20bb69d27914e4ca5c5dfb23`.
  Both reader event resources and Barsy are optional. The common UI prepared
  missing REQUIRED choices, but optional reader changes went to `/activate`.
  `native_activation` correctly rejects a proposed configuration different from
  the saved/approved one (`staged_authority_not_supported`), then the route hides
  that cause behind the generic exact-package access409. Thus adding optional
  readers falls into a prepare/review gap; do not weaken the fingerprint fence.
  Supplied recent-failure JSON also contains earlier consent preview/allow409s,
  but no classified causes; this diagnosis does not explain every recorded409.
  A physical Child Center activation trial of the new source has not been run.

- **Application authoring instructions aligned, 2026-11-11.** Owner requested
  the application-building guidance after the successful clean Note data trial.
  `docs/APPLICATION_DEVELOPMENT.md` is the canonical current workflow: neutral
  public imports, app-owned service/data/UI, declarations/generated client,
  permissions versus resource/code approval, migrations/receipts, shared themed
  controls, preview/check/upgrade and separate admin acceptance. The official
  starter now carries `AGENTS.md`; normal `init` copies it with the source and
  points its generated README to it. Existing projects are not rewritten.
  Root instructions/README/check guidance link the entry point. Corrected stale
  public imports in current UI/file/diagnostics guides and the obsolete claim
  that application uploads remain unavailable. Note optional-resource setup and
  candidate configuration instructions match the actual bounded lifecycle,
  rather than promise a universal inactive configuration-save shortcut.
  No Core/Agent/SDK/runtime or service/UI behavior change, external Monitor edit,
  installed-device action, dependency install, version, Git write or publication.
  Targeted scaffold/CLI/project checks: **87 passed + 3 Windows symlink skips**
  (Python3.13.15); those exact three cases **passed on Linux/Python3.13.18** using
  the existing environment. First Windows attempt could not use the shared Temp
  directory; successful evidence uses a dedicated local test directory. XMLs:
  `.runtime/application-authoring-instructions/{targeted-results,linux-symlinks}.xml`.
  Regression confirms instructions reach a newly generated project but not its
  installable ZIP. Real deterministic Note build/validator still yields exact
  `bb600d57e2561de13d79a62f40175603dee60469a3030ce81f68eda4c841b4ef`;
  the preceding live data proof remains evidence for unchanged application bytes,
  not a new runtime trial. Fourteen guide/Note links and whitespace passed;
  independent simplification-plan diff remains139/1. Full runtime/frontend gates
  were not repeated for documentation/template guidance. Next: owner review/use
  of this workflow; new application scope, restart trials and Git remain separate.

- **Clean physical neutral-layout trial: installed and Note round-trip passed, 2026-11-11.** Owner supplied a
  newly installed Linux target and its new host fingerprint after asking for a
  pre-commit installation trial. Identity was verified with a separate local
  known-hosts file; no global SSH trust or Git history/index changes. This new
  scope authorizes installation on that clean target, not publication or Monitor
  changes. Host is Debian13/aarch64/Python3.13.5; current LAN is preserved.
  Built `local-134d26bd7c708fbbbf40a4a5` from exact checked36ef source and its
  passed frontend build, reusing all four content-bound local gates. No new
  version. Archive SHA256 `169895d3951dcfe13afd190d197f4d59d1e82e50754fac72e7c37e3a51d4bec5`;
  752 delivered files, no old package roots or workstation data. Normal immutable
  installer is used directly: deploy.ps1's dispatcher is update-only and requires
  an installed baseline. Explicit host networking, no AP, reboot or reset.
  Host prerequisites installed through the normal reviewed APT set. First
  attempt failed on the OS's PiWheels SSL connection; normal rollback removed
  its release and left no current pointer. Repeated only after inspecting that
  result, with the SAME checked archive and official PyPI in the transient
  installer's environment; no SSL bypass or permanent pip configuration edit.
  The second install succeeded and selected the exact immutable local release;
  target metadata confirms checked36ef source, unchanged0.3.11 version and
  published=false. Initial LAN Setup `/ready` and `/setup` both returned200;
  Core/Agent initially waited for protected owner setup, not failed. The owner
  subsequently completed Standalone setup. Core, Agent, Platform Runtime,
  connector-worker, Web and update-helper were active with zero restarts;
  Core `/ready` passed, and authenticated Devices showed the local device online
  and synchronized. A mistaken read-only probe of port8891 failed; that is NOT
  Agent's actual loopback port8890 or an Agent failure. No direct Agent HTTP
  readiness proof is claimed from that mistaken probe. The installer log observer was closed only after systemd reported
  successful deactivation; closing that observer is not another install failure.
  Read-only preflight passed with one existing
  warning: host cgroup-v2 memory controller absent; no RAM-limit enforcement or
  boot-configuration fix is claimed. Local trial artifacts/evidence are under
  `.runtime/core-domain/fresh-install-908e83909bc2491f8dde8097e442f6be/`.
  The neutral Note starter common check passed on protected Linux storage:
  Python6/UI19/types/real compiler/packaged migration reopen+rollback; ZIP SHA256
  `bb600d57e2561de13d79a62f40175603dee60469a3030ce81f68eda4c841b4ef`.
  Earlier output on the Windows mount correctly failed protected-build checks;
  no ownership rule was weakened. The owner explicitly chose to upload, approve
  and activate Note personally, then requested its live data checks. Active1.0.0
  was observed in Extensions. Through the real reviewed operator UI, two distinct
  synthetic notes (Cyrillic and newline) each returned Saved; each exact value
  survived a separate full browser reload. Original note was empty; the second
  synthetic note remains visible for owner review. Optional resource was not
  selected and required separate approval, without blocking note editing. No
  direct SQL, permission changes, hardware command or blind write retry.
  Screenshot: `fresh-install-908e83909bc2491f8dde8097e442f6be/note-roundtrip.jpg`.
  An old cached HTML entry at the reused address referenced missing old JS;
  fresh query navigation loaded the exact current build. Cache policy was not
  changed; this remains a separate pre-commit browser-cache finding.
  Next: owner review and any separately requested service/device-restart trial;
  persistence across such a restart has NOT yet been tested on this image.
  No Monitor, device reboot, Git write, version bump or publication. Do not repeat
  installation; continue from the installed working system.

- **Product layout/cleanup completed locally, 2026-11-11.**
  Owner requests the whole cleanup in small checked steps without another "go".
  Source moves, consumer/package updates, audited cleanup and final gates passed.
  **No commit, push, branch, version, release, deployment or device action.**
  - Neutral sources: `components/{admin_web,public_web,platform_runtime,setup,
    system_runtime}`; `packages/{protocol,platform_wire,provisioning,application_sdk}`;
    optional `libraries/{ai_clients,crud}` expose `application_ai/application_crud`.
    No old-name forwarding imports. Public UI IDs are `@platform/ui/v1` and
    `@platform/application-ui/v1`; operational cross-bundle symbols are unchanged.
  - Core is organized under accounts, applications, appearance, artifacts,
    devices, installation, localization, sessions, settings, storage and system.
    The former flat routes/services/utils sources and parents are gone.
    Per-family captured bodies match after namespace-only substitutions; lazy
    imports, locks/ContextVars, key-before-database fencing and optional session
    mounting are preserved. ORM registration and persisted identities stay central.
    The unused database sys.path append outside the workspace was removed.
  - Full has **399 strictly sorted, unique required paths**, with builder,
    installer, omission and three real extracted-release import/API/CLI proofs.
    Public bootstrap/guest/kiosk endpoints retain their intentional boundaries.
    Independently minimal Host, Agent, Runtime, Public Web, Node/session/relay
    inventories remain different and Backend-free; parents are inert.
  - Cosmetic defaults come from `config_templates/product.json`, with bounded
    validated text/assets and safe HTML/script encoding. Saved localized branding,
    logos and theme settings retain precedence. Five remaining fixed-brand UI
    messages are neutralized in English/BG source. This is not an instruction to
    rename SQL, service/path IDs, provider IDs, signing domains, Setup SSID or
    update trust. BG source is a draft: use a new version at a future explicitly
    requested publication, not a previously published ZIP.
  - Root launchers are `tools/dev/{start,agents}.sh`; preserve their original
    executable mode at any later requested commit. Development defaults are
    `config_templates/development.json`. Current guides/links are updated;
    obsolete docs/scripts are marked under `docs/archive/legacy/`.
    Audited obsolete launchers, duplicate instructions and uncollected invalid
    early tests were removed (Git-recoverable). No current acceptance was removed.
    Old bytecode/build caches and the old BG ZIP are retained under
    `.runtime/cleanup-retained/` and earlier layout-retention folders. The final
    664 Backend bytecode files are in `backend-obsolete-source-caches-7520bb515c634b59b6cd2d9519a88b91`.
    Existing `backend/{mega_monitor.db,prices.json,output.json}` remain unchanged;
    these data are excluded from future source/deployment archives. User uploads,
    environments, IDE settings and independently preserved product history remain.
  - **External Monitor stays unchanged**, per the owner's explicit answer. No
    sibling source edits, version, package build, upload or activation. It needs
    separate import adaptation/rebuild/review before any future coordinated deploy.
    The independent simplification-plan diff remains **139 additions / 1 deletion**.
  - Final candidate: **`36ef13611e423bac057648c904e6f33229257fa7f52e755ad2128c1a37ff2d11`**,
    1,701 verified files, 14,599,947 bytes, based on HEAD `b134338a...`.
    Actual schema comparison permits only source-module/public-import renames;
    six schema/contract payloads and theme JSON are otherwise unchanged.
  - Earlier scoped evidence is retained, not relabelled as final-source testing:
    `990685ce...` packaging **750 + 2 existing skips**, plain SDK **426 + 2
    optional-image skips**, artifacts245, appearance146, accounts47,
    Core/compiler114 +13 root skips, authoring241 and actual starter common check
    (Python6/UI19/types/compiler/packaged migrations). `eb5cd392...` accounts47,
    devices150, management279. `7accc2da...` packaging312, authority559 +3,
    installation655 +1, storage/telemetry/templates146, source drift empty.
    Earlier Runtime/Setup/provisioning/Agent group:1,353 +3 root-only skips.
    Raw permanent evidence is under `.runtime/core-domain/runs/`.
  - Intermediate `eb10d019...`: packaging332 passed plus one outer30s extracted
    child timeout; that unchanged case passed alone in16s. Relational677 passed,
    595 existing root skips and2 strict old-ZIP fixture failures. Later phases of
    those stopped serial runs did not execute; these are not green whole runs.
    The fixture now pins current namespace bytes AND independently reproduces
    historical bytes by reversing only two exact import statements in disposable
    test inputs. No service execution or compatibility shim. **7 focused cases
    passed** on final36ef, `neutral-wp4-fixture-223efb02...`.
  - **Final Python3.13.18 local CI gates PASSED** on36ef:
    `ci13-series-5a7543da54244d5fbec7212c8189bcda`. Groups are tooling, whole
    frontend/types/examples/build, deployment+SDK, then compiled-UI preflight and
    whole default Python suites. Exact four dependency inputs/freeze are verified;
    existing environment/pip check passed without dependency installation.
    Completed on this exact snapshot: tooling **347 passed**; frontend **891**,
    starter UI/client **19**, CRUD UI **8**, both type checks and build passed;
    source drift empty. Deployment/SDK **1,159 passed + 8 existing opt-in/root/
    optional-image skips**; real compiled-UI integration **5 passed**. Whole
    default Python suites: **7,426 passed, 612 skipped, no failures**, 46m03s.
    The skips retain the existing separate root/systemd/distinct-principal,
    platform and opt-in acceptance boundaries; they are not conformance passes.
    All four controller groups exited zero; source drift is empty. Permanent
    broad Python log/XML/evidence: `ci13-python-84a59ee456ea43fd98e474231b5a5cfa`.
    A final live-source repack still matches36ef (1,701 files); whitespace passed.
    Final read-only package/workflow/entrypoint review found no blockers.
    This is not actual four-architecture Release/wheelhouse reproduction or
    root/systemd/hardware acceptance. No device or Git write is claimed.
    Next: owner review of the organized source. Commit/deploy need a separate
    request; any future deployment also needs external application import
    adaptation, rebuild and exact-code review. Monitor remains untouched.
  - Unrelated findings remain OUT OF SCOPE: entity-history audit lacks the listing
    endpoint's own-user/admin filter; compiled UI cache is not automatically
    revalidated against a changed compiler/import policy. Do not silently alter
    auth, purge trust caches or transfer approvals to different code.

- **Device hardware layout completed locally, 2026-11-11.** Owner requests
  continued domain-by-domain Core organization, not a mass rewrite. Keep each
  coherent slice behavior-preserving: audit consumers, move current ownership,
  update imports/registration/package closure, verify affected behavior and
  extracted release before the next slice. No commit or deployment authorized.
  Moved the unchanged hardware-interface admin API from
  `backend/routes/hardware_interfaces.py` to
  `backend/devices/hardware_interfaces.py`, with an inert parent initializer.
  Runtime worker, device/SQL identities, HTTP paths, admin rights, confirmations,
  request IDs and lost-ACK/no-resend behavior are unchanged. No obsolete alias.
  Full builder, target contract and direct installer require both new files;
  Node remains Core-free. Added current-admin revocation coverage on all three
  endpoints, helper-loss coverage for restart and extracted-release import/
  OpenAPI/401/omission checks. Existing optional-failure startup checks also
  verify the real router's 401/403 boundaries. Frozen source
  `f8095d4b7991d42160e02062f3e0809a4631dec147d7af8d7e2f762368179278`
  passed **347 tests, no skips**, in reused unprivileged WSL Python 3.14.4:
  hardware routes, Runtime hardware doubles, system control, Core startup,
  release/staging/smoke, doubled installer, minimal Node and deployment contract.
  Permanent XML/log/command evidence:
  `.runtime/core-domain/runs/core-device-hardware-layout-9868bb665b04408ea4f76ac3d59dd5a1/`.
  Independent review found no blockers. Earlier pilots and independent
  simplification-plan edits are preserved. Next candidates are a cohesive
  diagnostics slice, then bounded system/update and device registry areas;
  identity/application authority need separate broader consumer audits.
  No frontend build, dependency install, live I2C/reboot/service/device action,
  Git write or version change. This slice is complete; do not treat it as
  completion of the entire Core reorganization.

- **System control layout completed locally, 2026-11-11.** Owner requested the
  next bounded area; no commit or deployment remains authorized. Moved the
  unchanged 112-line restart/factory-reset API from
  `backend/routes/system_control.py` to `backend/system/control.py`. This small
  domain stays one file rather than gaining empty layers. Updated Core router
  composition and direct test imports; no obsolete import alias remains.
  API paths/methods, current-admin authorization, exact confirmations, audit,
  helper protocol and state/SQL identities are unchanged. Full builder, target
  contract and direct installer now require this module. Added regression cases
  for demoted/blocked/token-version-revoked admins and helper refusal without a
  successful audit; extracted release proof checks both current system domains.
  Frozen source `bba8980e7f87bc29829e075f1173d3074e4db697f1a70f19c40f40d3049de3ca`
  passed **268 tests, no skips**, using reused unprivileged WSL Python 3.14.4.
  Scope: control/network routes, real Core startup, release build/repro/extracted
  imports/omission checks, staging/smoke, doubled installer, minimal Node,
  deployment contract and fixed Runtime system-action request/command doubles.
  Permanent XML/log/commands:
  `.runtime/core-domain/runs/core-system-control-layout-15659bc8451d4713ae0b11cd37f72ce2/`.
  Independent review found no blockers; source comparison confirmed no control
  logic change. Earlier Web/network work and independent simplification-plan
  changes are preserved. Only README/this handoff followed the checked snapshot.
  No frontend build, dependency installation, real reset/restart, helper/device
  invocation, Git write, version change or deployment. This area is complete.

- **First Core domain layout completed locally, 2026-11-11.** Owner authorized
  one small area, imports and checks, again without commit or deployment. Chose
  network recovery: moved `backend/routes/network_recovery.py` and
  `backend/services/network_recovery.py` to
  `backend/system/network_recovery/{api,service}.py`, with inert package
  initializers. Updated main composition and the existing route-test imports;
  no compatibility shim or obsolete production imports remain. Exact comparison
  with the former sources shows identical service code and only the API's
  relative service import changed. All five API paths/methods, current-admin
  checks, confirmations, audit behavior, state paths and shared provisioning/
  Runtime helpers are unchanged. No model move or database migration is needed.
  Full builder, deployment contract and direct full installer require the four
  domain files; minimal Node/native closures stay Core-free. Earlier Web pilot
  and independent `CORE_SIMPLIFICATION_PLAN.md` changes are preserved.
  Frozen source `b587c658d1efb6a3b097ab929e1c26a9a9f20630063a9fc44079c30f5514f8e0`
  passed **280 tests, no skips**, in reused unprivileged WSL Python 3.14.4:
  network-recovery routes, Core startup/denial under optional failure, real
  extracted-release domain import/OpenAPI/401, builder/repro/omission checks,
  staging/smoke, doubled installer, minimal Node, deployment contract and shared
  provisioning/AP/Runtime recovery. Permanent XML, logs and exact commands are
  in `.runtime/core-domain/runs/network-recovery-6b076bfd8ab74f7ab98c65e4e71d9309/`.
  Final test-harness-only refinement prunes local environments/data/symlinks
  while collecting its extracted-release source fixture. That single changed
  test passed again against snapshot
  `26dc7b1ea35e6417ebb4025dc9bfe857fe2f38abf6c61b23987b63f1ec282688`;
  evidence `.runtime/core-domain/runs/network-recovery-343269e36ecf4597ac00c4fa231c74f7/`.
  The other unchanged cases reuse the 280-test result, not a claimed full rerun.
  Only explanatory docs followed these runs. No frontend build, dependency
  installation, live network/AP/setup/device/systemd action, Git write, version
  change or deployment. This small domain is complete; further areas are separate.

- **Administrative Web layout pilot completed locally, 2026-11-11.** Owner
  authorized this component only, including imports, packaging and checks;
  explicitly no commit or deployment. Moved `three_mm_web` source/tests to
  `components/admin_web`, with an inert regular-package parent and entrypoint
  `python -m components.admin_web`. No historical import alias remains. Unit
  `3mm-web.service`, immutable paths, ports, frontend build, uploads and AP
  redirect behavior remain unchanged. Full builder, target contract and direct
  installer require the four package files plus existing setup/captive helper;
  Node artifacts remain separate/minimal. Snapshot/deploy inventory explicitly
  includes only this nested component and its parent initializer. Default pytest
  and conservative CI selection use the moved tests; unknown components still
  expand to full checks. Updated current service/security/entrypoint guidance.
  Frozen source `62a8c65f53bd876b304bed32b9362c81f189d281646e7e4739db7b777cd33407`
  (base `b134338a`) passed **390 tests, no skips**, in unprivileged Ubuntu WSL
  with reused Python 3.14.4 environment/dependency digest
  `f91ccaad806c25f0057f8f802db6ed3ad6733a89fd44d3bd934d14d1b8c8c5f7`.
  Scope: moved HTTP/denial cases, setup captive portal, release build/repro/
  omission refusal and clean extracted-release subprocess HTTP launch, staging,
  smoke, frontend-origin policy, doubled installer, minimal Node, deployment
  contract, systemd templates and tooling snapshot/selector/deploy checks.
  Captured result: `.runtime/admin-web/check-result.json`; local runner
  `.runtime/admin-web/check.py` and frozen source archive retain inputs. The
  transient WSL run `/tmp/3mm-lab-yl90rl1k` disappeared before copying its raw
  XML/log, so the saved summary explicitly records stdout provenance instead.
  Checked executable drift was empty. Only explanatory docs followed
  the checked executable snapshot. No frontend rebuild, real systemd/device
  acceptance, dependency install, Git write, version change or deployment.
  Independent `CORE_SIMPLIFICATION_PLAN.md` changes are preserved. This pilot
  is the bounded result; other component moves and branding remain future work.

- **Brand-independent layout review, 2026-11-11.** Owner preserves released
  0.3.11, dislikes `three_mm_*`, rejects proposed CONERAX/KORENOS naming and
  defers choosing a product brand while requesting structural cleanup. Do not
  introduce `conerax.*` or another tentative brand as the new import namespace.
  Latest "Планирай опростяването на ядрото" proposals provide components/packages
  and domain-oriented Core ownership, not authorization for a mass move.
  Proposed source names describe responsibilities (e.g. `admin_web`,
  `application_sdk`, `platform_wire`), independent of public product branding.
  Central product metadata should supply default names/logo/title to build and
  setup consumers while preserving explicit localized site/header settings.
  Current branding is dispersed: header defaults/store, `frontend/index.html`
  ("Vite App"), setup HTML/API and installer messages. Brand data must remain
  separate from repository/update trust, module IDs, wire/cryptographic domains,
  SQL names, service IDs and installation paths; these are not display labels.
  Next bounded implementation candidate is static admin-web (3 source files,
  2 test files), including all entrypoint/build/import consumers and checks;
  Core domain grouping and mixed Runtime ownership follow as separate steps.
  No source move, SDK/API, identity, device, Git or release change in this review.
  Independent `CORE_SIMPLIFICATION_PLAN.md` work is preserved. Documentation
  handoff only; no runtime tests or frontend build were needed.

- **Core 0.3.11 published, 2026-11-10.** Runtime commit
  `6ec8e87d2c9d07051186be8956bed43caf2a8b89` passed all four main-push CI jobs
  on the first push: [CI 42773833497](https://github.com/ldobranov/3mm/actions/runs/42773833497).
  Only after that success was annotated tag `v0.3.11` pushed.
  [Release 42778364259](https://github.com/ldobranov/3mm/actions/runs/42778364259)
  succeeded and [0.3.11](https://github.com/ldobranov/3mm/releases/tag/v0.3.11)
  is public/stable with all nine assets. Published descriptor bytes match GitHub
  asset digests; SHA256SUMS matches all eight archive/manifest digests. All three
  catalogs identify the exact runtime commit and the expected five archives.
  No device deployment, reset, grant change or hardware invocation in this task.
  Monitor 0.8.3 source/ZIP stay unchanged; its separate repository/publication
  is explicitly deferred. Accepted 18–27s button latency also remains deferred.
  Independent `docs/CORE_SIMPLIFICATION_PLAN.md` remains local and uncommitted.
  Release work is complete; wait for the owner's next bounded task.

- **Core / Monitor release preflight, 2026-11-10.** Owner explicitly accepts
  Crypto Monitor functionality, reports remaining button latency **18–27s**, and
  defers that latency issue. Do not reopen performance work in this release.
  Prepare Core **0.3.11** and preserve accepted Monitor **0.8.3** ZIP bytes. Owner
  asks to find/fix local CI failures before push, then use green exact-commit CI
  before an annotated tag/release. **Local preflight is complete; next is the
  reviewed commit/push, then exact-commit green CI before any tag/release.**
  The index contains 128 verified Core files, not the independent simplification
  document. No commit, push, tag or publication at this preflight checkpoint. Frozen
  candidate `9234a9b1422d…` contains full public source (including docs, workflows,
  frontend and optional libraries), excluding private/legacy DB files. Separate
  disposable Linux lanes use Python **3.13.18**, Node **22.22.1**, pnpm **10.13.1**;
  test requirements/constraints and pip check passed. Evidence/logs live under
  `.runtime/release-0311/`. Frontend gate passed: **879 main + 19 CAP21 UI tests**,
  both strict type checks and production build, no frozen-source drift. Tooling
  (including real generated-client acceptance) initially found one unit test
  reading the installed Ubuntu Agent journal. Its paths now use disposable data;
  no production/permission change. Changed `tools/tests/test_deploy.py`: **43
  passed** on `eb15b05fcfd8…`; **293** unchanged outside-file successes reused
  from the initial run, covering all **336** tooling cases. Deployment/SDK full
  lane: **765 passed, 1 failed, 8 existing root/optional-profile skipped**. The
  failure was the absent image-provider native-host probe; exact original child
  timing/exit category is unreconstructed. SDK now returns unavailable on a
  definite top-level PIL metadata absence without starting a child or importing
  codecs. Uncertain/present metadata keeps the existing bounded child and 2s
  timeout. Final probe tests **8 passed, 1 optional-profile skipped**; unchanged
  packaged-host assertion **1 passed**, media/resource/revocation consumers
  **105 passed, 1 optional-profile skipped**, no source drift. Original Python
  full lane finished: **7,066 passed, 612 existing skipped, 21 failed, 13 errors**;
  it is not a green gate. Two failures (signed
  publication lost-ACK and signed checkpoint CAS) are reproduced as **AF_UNIX
  path too long before dispatch**: default nested pytest paths make 109/115-byte
  socket names. Same cases pass with short basetemp, including full 7,712-item
  module collection (2 passed, 7,710 deselected). Controlled original-length
  reproduction failed both at server.bind; no Core/auth/deadline defect inferred.
  Task-local runner now sets a short explicit basetemp for future commands.
  Do not claim the original run used the corrected harness. Evidence:
  `runs/platform-long-path-`
  `9e719fae4a874a39b70d8a428352893c/` and `runs/platform-full-collection-`
  `a702a53537b14cb78e93b467c868a4e1/`.
  Three further original-run failures in UI diagnostics were reproduced with
  short paths: typed `AuthorityReviewKeyBusy` was classified as its generic base
  error. The classifier now preserves `review_key_busy`; public 409, current
  rights, dispatch denial and deadlines are unchanged. Existing assertions were
  not edited. Full affected diagnostics/key/privacy group **170 passed, 2
  existing platform/root-only skipped**, no source drift; evidence
  `runs/key-classification-28eba79251a44f4dbdf40e6259e74c0b/`.
  Fifteen further state-publication failures came from manual integration test
  drivers omitting the accepted independent Agent telemetry cycle. Two test
  files now assert the publication wake, drive the real queued publisher and
  retain their original receipt/state/role/revocation assertions. Full affected
  Node/Agent group **45 passed, no skips**, snapshot `ad0ae16b8647…`;
  `runs/node-drivers-9840a50ef8db4f46b22d43f5e29202cc/`. No production Agent
  telemetry reversal. Twelve host setup errors also had overlong Unix socket
  paths; the entire host-failure file plus both signed cases then **33 passed,
  no skips** on short ext4 paths, unchanged production;
  `runs/host-short-3ac811e3ca6e47948b3638128c8d9141/`.
  One optional AP-status permission failure exposed a real unguarded stat.
  Absent stays inactive; inaccessible now reports safe unavailable status without
  breaking admin recovery. Route fixtures use only disposable paths. Provisioning,
  setup, helper and route consumers **219 passed, no skips**, snapshot
  `1ba5ed57fd69…`; `runs/ap-status-c9dea7c3fefb4426b7d44dfd61cb110b/`.
  A shared RAM-backed /tmp capacity incident caused one DB setup error and could
  affect apparent passes. Build scratch moved recoverably to owned ext4 storage;
  no user/installed data changed. All **132 whole test files / 1,516 original
  cases** in the generous incident band were rerun, not just failed cases;
  `runs/capacity-band-0dc10a8541fb4f9381aea1b247195009/`: **1,491 passed, 9
  unchanged root-boundary skipped, 16 known old-snapshot Node/AP failures**.
  Those 16 cases pass in the current 45-case Node and 219-case AP groups above;
  no new failure/error or newly skipped former pass. The original disk-full case
  passed. Machine mapping resolves all **34** original failures/setup errors to
  explicit successful follow-ups. This is combined unchanged-input/retest
  evidence, not a new single green 7,712-case run. Original failed logs remain.
  Candidate `f9455dd0b078…` contained the initial scoped fixes. Nonpublishing packaging
  rehearsal passed: both ARMv6 compiler builds, all four Full architectures and
  ARMv6 Node built twice identically; actual manifest models, archive metadata,
  URLs, size/hash checks, checksums and source/dist drift checks passed. Evidence:
  `runs/packaging-db711ea2838347db917c2f893135f4d6/`. Subsequent `c043545d358c…`
  packaging also passed on ext4 after the RAM-capacity failure;
  `runs/packaging-4e603618898e43d299b3271ff62c7295/`. Final planned Git-export
  candidate `c6179ecb6eb1…`, including AP hardening, also passed the complete
  double-build/manifest rehearsal; `runs/packaging-e041e6c856f9491a82380e05129f73ff/`.
  Frontend reuse compares all
  275 audited build/test inputs. Rehearsal artifacts use old HEAD metadata and
  must not be published. Git export exclusions now omit root editor rules,
  the historical tracked DB and uploaded settings images without deleting local
  data. Canonical staged export has all **1,841** checked public paths and no
  extra data files. Runtime/test bytes match the rehearsal; only root-anchored
  export attributes and this handoff changed afterwards (HEAD document line
  endings are compared canonically). Actual committed-export verification and
  exact-commit hosted CI remain mandatory before tag/release.
  All new scene/GPIO/template/connector source files must enter the reviewed Git
  snapshot; a local dev-lab pass does not prove `git archive` completeness.
  Preserve independent `docs/CORE_SIMPLIFICATION_PLAN.md` work. Monitor source is
  a separate local directory without Git metadata; it is not in the Core release.
  Owner confirmed `C:\Users\LAZ-DELL\Desktop\3mm-crypto-monitor` as the source;
  all 15 packaged inputs match accepted 0.8.3. The exact accepted ZIP is also now
  in that project's `dist/`, with SHA-256 unchanged. No source move was needed.
  Owner chose a separate Monitor GitHub repository **later**: do not initialize
  or publish Monitor now. Current active release work is Core 0.3.11 only;
  preserve the accepted Monitor source/ZIP unchanged. No device changes here.

- **Button latency fix deployed; functionality accepted, 2026-11-10.**
  Owner timed the accepted button/LCD/seconds scenario at 20–30s. Read-only Pi3
  metadata identified accumulated edge telemetry, repeated immutable package
  verification in Core, and up to 10s old-scene gating in Monitor. Agent now
  coalesces optional telemetry on its existing publisher, outside the event and
  physical-command queues. Core reuses immutable verification within one event
  RPC only, never caching current rights. Monitor 0.8.3 atomically supersedes
  older desired scenes with higher sequences and retains uncertain history;
  generation-fenced timer reservation/backoff prevents stale work restoring the
  10s delay. Fresh grant admission, Stop, event ordering/deduplication, finite
  leases and local seconds remain intact; no per-second Core polling was added.
  Focused real Core scope checks: **5 passed**, including revocation and three
  immutable-file drift denials. Initial integration: **153 passed, 1 failed,
  1 root-only skipped**. The failed synthetic restart was reproduced: fixture
  readiness waited on an unused full-tree digest beyond the paused handler's
  declared 10s budget. Removed only that unused startup digest, preserving real
  explicit fingerprint assertions and all timeouts; event-process plus direct
  Runtime consumers then **18 passed, 2 existing root-only skipped**. Evidence:
  `.runtime/cap14-clock-recovery/runs/restart-diagnostic-260db74a528c41bcb72b8669115ba095/`.
  Production Core bytes remain the checked `a47332801052…` snapshot. Exact Agent
  closure `dd192933fd9c…`: **413 passed, no skips**, preserving absence of an
  unrelated new wire module. Monitor final backend **119 passed**; unchanged UI,
  strict types and build evidence (**80 UI tests**) reused after input comparison;
  exact new ZIP passed actual Core validation, reproducibility and UI compilation.
  Final package: `.runtime/cap14-clock-recovery/packages/latency-final/3mm-crypto-monitor-0.8.3.zip`,
  SHA-256 `68f74cac6f0770919350cf050f9afde3b6fe7d1f8eeac352d694f9d3a5236917`.
  Owner explicitly authorized Core/Agent deployment and catalog upload only,
  reserving activation. Catalog upload succeeded through the normal admin API;
  owner then independently activated 0.8.3 during preparation and confirmed it.
  First safe preflight refused that concurrent change; refreshed reviewed
  baseline preserves the owner's exact package/config/grant transition.
  Pinned Pi3 immutable Core `local-pi3-gpio-5c301dab2291b4c74141` is installed,
  ready and exact-file verified (only `application_events.py` payload delta).
  Independent Agent `ce5529f2b427453155631a4844b479f37bf484dfbf26361893b7fce63386193a`
  is ready through standard offline activation/health/rollback (only
  `agent/core_client.py` delta), preserving dependencies/vendor/providers,
  Runtime, other/default hosts and application settings/rights. Core PID 147233
  stayed unchanged during Agent activation. Automatic installer rollback
  preimage only: no separate backup, device reboot, reset, Start/Send, grant
  change or Git action by the agent. Final read-only acceptance
  `acceptance-1794287137289.json` records enabled/running scene sequence 3885,
  no pending frame, three successive successful scene renewals, four active
  services with zero restarts and zero sampled current-invocation traceback,
  BrokenPipe, DB-lock or event-authority/result-error categories. This is not
  optical or button latency acceptance. Owner subsequently measured **18–27s**,
  explicitly deferred that remaining latency and accepted Crypto Monitor's
  functionality for release; no claim of immediate screen switching.

- **Combined Pi3 LCD / local seconds / GPIO17 recovery, 2026-11-09.** Owner
  requires the three functions accepted together, not another one-frame fix.
  Confirmed native button edges/current event rights; the selected Monitor host
  died on a reply to a disconnected caller, delaying queued button events beyond
  Monitor's freshness budget. Candidate contains socket reply failures without
  rerunning handlers or clearing replay protection. Event handoff now has an
  explicit finite claim deadline/caller-liveness fence and a fresh handler wait
  after FD transfer, bounded by the original boot-clock lease with completion
  reserve. Expired/disconnected unsent claims cannot silently start dispatch;
  lost sent outcomes remain durable. Previous Runtime remains healthy-idle
  during the Core-first transition, never dispatching deadline-less requests.
  Exact ext4 snapshot `e97a6e519986…`: event/process/authority group **138 passed,
  1 separate-root case skipped**; native host/Runtime/rollback consumers **109
  passed, 2 optional-image/separate-root cases skipped**. Durable evidence:
  `.runtime/cap14-clock-recovery/runs/`. Three combined Monitor/native-policy
  regressions also passed: blocked scene/quote SDK I/O does not block button
  selection or Agent local ticks; duplicate input does not switch twice. No
  Monitor production change. Existing Agent clock evidence remains applicable.
  Scoped immutable Core `local-pi3-gpio-1752ddcd45fd15848265` installed and exact
  files/readiness verified on pinned `rasp-3mm`. Selected host + Runtime rollout
  completed through standard independent controllers: host `5435cca48972…`,
  Runtime `e7b9617c8ad2…`, unchanged Core PID 54111 during both independent
  updates. Agent artifact, Monitor
  0.8.2 package/config/grants, providers, other hosts/default/connector pins and
  old terminal event receipts are fenced unchanged. Automatic installer rollback
  preimage only, no separate backup, reboot, explicit Start/Send, grant change
  or event replay. Live read-only acceptance `acceptance-1794248706808.json`
  under the task folder records real GPIO17 screen advances, new events
  acknowledged on their first attempt, continuing successful scene renewals,
  all four services active with zero restarts, and zero current-invocation
  traceback/BrokenPipe/database-lock error categories. Initial interruption
  during the Runtime switch recovered automatically under existing LCD consent;
  no manual Start, hidden frame replay or consent cleanup. Old event failures
  remain retained. Owner asked for two physical presses and visible seconds;
  Six screen advances are now observed; final `acceptance-1794248802744.json`
  confirms every new input settled on attempt 1, no new host/Core/Runtime/Agent
  restart or recorded traceback/BrokenPipe/DB-lock category, and scene sequence
  215 with continuing successful renewals. One unconfirmed scene was skipped
  without stopping enabled output; subsequent fresh scenes succeeded. No claim
  that all command outcomes were confirmed or that a brief sample proves
  indefinite reliability. Owner subsequently confirms visible local seconds and
  physical button screen switching, but reports 5–10s response delay. This accepts
  combined functionality, not latency. Read-only timing probe
  `.runtime/cap14-clock-recovery/inspect-latency.py` separates the remaining path:
  latest press reaches Core in about 44ms, its release waits about 8.4s before
  Core ingestion; isolated earlier release samples wait about 4.4–5.8s. Core
  then takes several seconds through admitted dispatch/completion; boot-clock
  lease-to-wall mapping is approximate and receipt timestamps have 1s precision.
  Agent currently serializes full capability health/state publications between
  individual edges. Monitor also independently reproduces up to 10s pending-scene
  expiry gating after a button selection: wake/reset already occurs, but a queued
  or unconfirmed previous scene blocks the newer desired content. Next bounded
  candidates: decouple/coalesce telemetry outside the edge queue; let an atomic
  desired-content generation supersede only an older set_scene, preserving its
  receipt/history and using a new higher sequence with fresh admission. Stop,
  revocation, lease expiry and unknown original outcomes remain fenced. The
  Core claim path also repeats immutable package/build verification without the
  existing request-local `code_verification_scope` used by invocation relay;
  bounded same-request immutable verification reuse is a third candidate, not
  permission caching or removal of final admission checks. No new
  production change, deployment, rights change or Git action in this latency
  diagnosis; do not promise subsecond latency without remeasuring Core stages.

- **Pi3 Agent-only clock rollout completed, 2026-11-09.** Owner authorized only
  Agent on pinned `rasp-3mm` and catalog upload of the new provider; approvals,
  provider replacement and Monitor activation remain owner actions. Offline
  immutable update `0d28d8097c78…` completed through the installed standard
  controller with health/rollback: Agent `37324174b1b8…` -> `96a787155b45…`.
  Exact nine changed Agent/protocol sources match the checked closure; target,
  dependencies and vendor bytes match the previous Agent. Core PID 36819,
  Core/Runtime/connector/host pins, app/config/grant and device-provider install
  metadata remained unchanged; no reboot or explicit hardware command.
  Monitor 0.8.2 was already active at preflight and was left untouched.
  Reused the clock evidence below; 24 additional Agent controller/rollback/
  release-lock checks passed (32 unrelated cases deselected), durable evidence
  `.runtime/cap14-clock/runs/controller-dc351c24d7904baba33b3271f7509d06/`.
  New exact provider SHA `8af876cf4a2f…` uploaded via normal admin API and verified
  visible in Devices: **Character display with local clock (pcf8574)**,
  schema 3, 16x2, profile `00da8fe24bed…`; approval supported, not installed.
  Existing providers are not disabled or deleted. Next owner step: replace the
  old static display provider, approve Monitor scene/Stop bindings, enable LCD
  and inspect visible seconds. No device optical acceptance or Git action claimed.
  Follow-up read-only inspection: the old static `ac1937994d21…` is still the
  enabled/succeeded Agent owner of `display.character`; no new disable command
  was submitted. New clock `00da8fe24bed…` and another static template instance
  both failed on that ownership conflict, with no installed version or saved
  active Agent state. UI `failed · Enabled` reflects desired enabled state, not
  successful activation. Agent remains active with zero automatic restarts.
  Owner must disable the actual old owner and wait for confirmed completion,
  then review/install the new clock provider; no automatic disable/retry/removal.
  Subsequent owner report: button does not switch. Read-only Pi3 trace proves
  GPIO17/channel `gpio.input.1` edges reach Core (native provider healthy),
  Monitor has two screens and current claimed deliveries pass `event:button`
  admission. Not an Agent input/configuration gap. App host `9900483793e5…`
  restarted six times with uncaught BrokenPipeError at application_host.py:459
  -> application_transport.send_message:110 (reply to disconnected caller).
  Core/Agent/Runtime have zero restarts. Button head deliveries show
  `delivery_unconfirmed`, retrying behind 40s claims; later edges queue and
  eventually exceed Monitor's 30s freshness filter. Queue still advances at
  retry exhaustion, not a permanently stuck database row. Installed host and
  Runtime event-worker source hashes match local source. Runtime's 4s Core
  claim/completion handoff budget is a suspected contributing boundary, not
  yet a proven original timeout cause. Next: owner-authorized host disconnect
  containment and event handoff timing reproduction; no code/device fix,
  rights change, event replay or hardware command performed in this diagnosis.

- **Local seconds / Monitor 0.8.2 prepared, 2026-11-09.** Owner selected a
  maximum 30-second local LCD lease, renewed every 10 seconds; package version
  0.8.2 (not 0.9.0). No deployment/upload/activation, rights change, physical
  command, reboot or Git action in this step. Monitor source is updated in the
  sibling `3mm-crypto-monitor`; the isolated working copy/evidence is under
  `.runtime/cap14-clock/`. Other existing source work remains untouched.
  Browser preview now uses coherent UTC/monotonic anchors and explicit clock
  cells, with local aligned second ticks, IANA/DST formatting and separate
  visibility-aware data polling. Neither slow polls nor locale/theme changes
  stop local seconds; draft epochs prevent an old response restoring a preview.
  New generic Agent provider entrypoint `builtin:display.character.scene.v1`
  implements `display.character` 3.0/profile 3. It runs finite scenes locally;
  normal SDK/M20 admission renews them every 10 seconds. Stop and manual-frame
  actions remain independent. Absolute and monotonic deadlines bound ticks;
  disable, failure or Agent restart never restores a scene. Strict scene IDs,
  increasing sequences and bounded Stop tombstones fence delayed commands.
  Unknown original commands are retained, not replayed or called successful;
  higher-sequence desired scenes require fresh access. No Core runtime change
  or per-second Core/SDK/market call was introduced. Compact clock-cell data
  stays within the existing 512-byte scalar contract budget. Native writes
  use acknowledged-frame dirty spans; identical frames do no I2C access.
  Migration 0010 preserves settings, quotes, input/command journals and resets
  old frame-only consent: autonomous scenes need explicit new profile/access
  review. Existing LCD content interval stays separate (effective minimum 10s);
  seconds tick locally between renewals. Current static 2.0 provider stays a
  distinct frame-only option; old immutable ZIPs are not overwritten.
  **Checks:** Linux snapshot `1dd76aa91bc7…`: 553 passed, no skips, including
  all Agent tests, native transport/syscall doubles, profile/package/authority
  consumers and Agent native artifact. Production inputs are unchanged since
  that run. Final scene timer/close test added afterwards: 8 Linux scene checks
  passed (7 overlap the previous run). Monitor final source: 103 backend checks
  passed; unchanged final UI/compiler inputs reuse 80 UI checks plus strict
  TypeScript and production build. The final ZIP also passed the real Core UI
  compiler locally (`built_ui_sha256=7c6350995e2b…`), with no installation.
  Local preview fixture was adapted to the
  new plan and syntax checked; no new optical/device or browser-layout acceptance
  is claimed. Durable logs/input lists are under the task run folders.
  **Final Monitor ZIP:** `.runtime/cap14-clock/packages/3mm-crypto-monitor-0.8.2.zip`,
  SHA256 `5d14c02d9fb50fb186359a8ea773e97ec16f14a01d4bc8b93a8c44d10f0cf777`.
  Exact 16x2 PCF8574/I2C-1/0x27 inert provider:
  `.runtime/cap14-clock/character-display-clock-16x2.zip`, SHA256 `8af876cf4a2f…`.
  Separate data-only admin template: `character-display-clock-template.zip`,
  SHA256 `eb9d8ac187d9…`. The earlier ZIP in the task root is only a superseded
  local candidate; use the final `packages/` ZIP. Next, only on owner request:
  update the chosen Agent, disable/review-replace the static provider, review
  Monitor 0.8.2 scene/Stop rights, then owner enables and checks visible seconds.
  A standalone Monitor activation against the old 2.0 provider cannot run scenes.

- **Core 0.3.9 tagged, not published; 0.3.10 published, 2026-11-06.**
  CI `42173867312` passed for `92dab4846afc`; the latest published release
  was `v0.3.8`. Prepared only VERSION, README, changelog and release notes
  in `70ba0e53b0f9`, pushed to `main`. Release/bootstrap/contract/tooling
  checks: 174 passed on exact prepared Linux snapshot `6806b5410492…`.
  Exact main CI `42178909304` passed and annotated `v0.3.9` was pushed.
  Release `42182885219` failed before building assets: a real signed
  negative health result was refused, but the end-to-end HTTP test took
  2.80 seconds against an unrelated two-second wall-clock assertion.
  Public release lookup returned 404; leave the immutable tag untouched.
  Owner requested a working release before CAP20 device work. The fix keeps
  the HTTP denial/no-replay/no-stamp checks and verifies the actual Runtime
  deadline with a continuously trickling peer; no production deadline changes.
  Exact 0.3.10 source scope passed 213 Linux checks; 1 separate-root test
  skipped. All six staged blobs matched the tested source. Commit
  `8f9693cc9077` pushed to main; exact CI `42185027896` passed.
  The watcher pushed annotated `v0.3.10`; the remote peeled tag is the same
  exact commit. Release run `42189083611` passed; the watcher confirmed
  publication and all nine expected assets, including full ARMv6 and Node.

- **Zero W clean-install follow-up, 2026-11-06.** Owner installed published
  `0.3.10` and Crypto Monitor `0.7.0`; read-only device checks confirmed the
  active services and enabled 16×2 provider installation. The owner has not
  accepted price updates or LCD output. Repeated Coinbase connector attempts
  hit the worker's five-second child budget without an HTTP result; one
  anonymous direct request from the Zero W as the worker user returned HTTP
  200 in 0.81 s outside the service sandbox. The installed one-shot executor
  spent 2.75 s starting with no request outside the worker quota; the live
  worker has a 50% CPU quota and recorded throttling. For the existing LCD
  command, Core consumed the one-use permit, but Agent recorded `not_executed`
  at authorization; command completion was 3.28 s after delivery, against a
  two-second Agent authorization wait. I²C adapter, device node and Agent
  group were present. Investigate the startup overhead and the distinct live
  permit deadline; retain revocation, expiry, and no-replay guarantees. No
  device changes, new LCD command, rights change, restart or deployment.
  **Candidate prepared and tested.** Agent uses one permit budget of up to
  10 seconds in both HTTP paths, shortened to the remaining command lifetime.
  Late/mismatched replies, denial, and duplicate delivery still cannot reach
  the driver. Connector subprocesses use a stdlib-only entrypoint without
  loading Runtime or Python site; worker identity, five-second deadline, TLS,
  result signing and no-retry behavior are unchanged. WSL: 417 Agent and
  authority regressions passed (`104144ed9b51…`, inputs unchanged), and 152
  connector/release checks passed (`41664e3686a3…`, plus the distinct-UID case
  passed under the isolated root test driver). On Zero W, two disposable user
  scopes enforced 50% CPU with the same five-second execution budget: the
  installed executor timed out; the candidate (`eb592ca9f346…`) returned
  HTTP 200 in 4.12 s.
  **Independent updates and one-frame acceptance, 2026-11-07.** With owner
  approval, verified the pinned Zero W and exact installed baseline, then used
  the existing immutable update/health/rollback controllers. Connector is
  `eb592ca9f346eda9f1db042d4cb7416f60795b36fd7c6f6543359bd6133b354b`;
  Agent is `84fe74adc3cf2ce0db5d4d46c4cb57d2707271ec36a5273f1f85bebdf72b7d00`,
  built offline on-device from tested sources and unchanged locked vendor
  dependencies. Core 0.3.10 PID 825, application 0.7.0/package/configuration,
  grant revision/payload, SDK Runtime and host pins were unchanged. Normal
  administrator API reads reported a fresh quote (45–58 seconds old), no
  source error and the reviewed 16×2 display ready. Submitted exactly one new
  saved-screen frame, request `afd3ba482d806a4c153ab1f240d16df2`, command
  `cmd_fcf9f58e8c75404ebbe37456926069bc`; read the same command through
  queued/delivered to `succeeded`, `executed=true`. No replay, settings/grant
  change or live-loop start. Software execution is confirmed; owner optical
  confirmation remains separate. The test request evidence is retained on the
  device; persistent live output remains stopped. No commit, push or release.
  Final read-only follow-up: application active with zero restarts; the new
  LCD command remains succeeded and the old failure remains retained. Quotes
  now arrive (four HTTP-200 results among the latest eight attempts), but the
  latest connector attempt again hit its unchanged five-second deadline and
  the app retained its cached quote. Do not claim sustained quote stability:
  residual connector deadline pressure on the Zero W remains to address.
  **Owner reports later crash/reboot/login failure, 2026-11-07.** Owner
  confirmed the visible LCD frame, then reported a later crash and manually
  restarted Zero W. Pinned read-only checks on boot `2c4ecc45…` found Core
  enabled but inactive/dead, PID 0, no failed systemd units and no Core start
  record in the current journal; web, Agent, Runtime and connector are active.
  Core loopback port 8887 refuses connections, so login currently cannot reach
  authentication. Core/app SQLite quick checks both passed. Available memory
  was about 204 MiB with unused swap; no OOM/SD error was recorded in this boot.
  Only the current boot journal is retained, so the preceding crash cause is
  not established. Monitor is active without restarts; LCD is blocked with
  `restart_pending`, enabled false and an unresolved frame. No reset, password,
  grant, service-start or frame-replay action. Asked owner approval to start
  only Core and then test normal login; do not clear the pending LCD outcome.
  **Access restored after explicit approval.** Issued one nonblocking start
  of Core on the same boot; no Raspberry reboot. Cold startup exceeded the
  probe's 120-second readiness window, but a subsequent read returned HTTP
  200 `/ready`, PID 1309, active/running and zero restarts. Agent, connector,
  SDK Runtime and Monitor service invocations were unchanged. Frontend runtime
  configuration points to Core port 8887; ordinary administrator login and
  authenticated profile reads passed through that API, then only the probe's
  session was logged out successfully. No password, grant, configuration,
  LCD action or pending-frame cleanup. Access recovery is confirmed, not the
  cause of the preceding crash or missing boot start; those remain unresolved.
  **Blocked live frame diagnosed read-only.** For the screenshot's exact
  `cmd_35f916f4ba7548d6a1efe9c47199d708`, the application-owned pending
  request was read from its DB and its hash matched Core's immutable
  idempotency identity (not a manually copied screenshot ID). Core reports
  expired/claimed with no result or completion time. The same Agent journal
  identity has a completed failed/unknown driver receipt at
  `2026-11-07T04:24:05.038105Z`, 26 ms after the command deadline; that result
  remains in the one-entry outbox. Monitor is blocked/outcome_unconfirmed,
  enabled false, retaining the same request/command. Current Core receipt code
  discards a delivered command's late completion, then rejects later receipts
  once expired; application lookup consequently remains unknown. This explains
  the recovery dead end, not the underlying driver failure or previous crash.
  No command replay, state cleanup, app invocation, service restart, grant
  change or deployment. Next bounded fix needs late-result evidence retention
  separate from execution permission, plus explicit recovery for an unknown
  LCD frame without silently treating it as successful or retrying that ID.
  **Owner-approved recovery fix prepared locally.** Core acknowledges and
  retains the first late Agent result under `result.late_completion` for an
  already delivered attempt, even after poll expiry. Status remains expired;
  deadlines, one-use permits, module/control authority and the original receipt
  are not renewed/overwritten. Undelivered and foreign-device reports remain
  refused; application lookup also exposes the stored completion timestamp.
  Monitor's new `display_live_release` is an administrator/monitor_display
  control with exact run/request identity and fresh original-command lookup.
  It requires a completed Agent receipt and elapsed deadline, never mere
  absence/expiry or a lifecycle invalidation without completion. Explicit
  review retains the old intent/result in the existing control journal and
  stops durable output; it neither submits a frame nor resumes output. A fresh
  enable separately checks current access/profile and uses a new live run.
  No table/column change, manual journal cleanup, version bump or device action.
  Linux snapshot `10f6a407778a…`: 149 command/device/authority/SDK recovery,
  rebinding/provider, module-lifecycle and task-time checks passed. Final
  `13509e674582…` adds one real HTTP receipt acknowledgement check, passed;
  production inputs are unchanged, so the previous 149 are reused. Monitor:
  105 backend checks passed on frozen copy `3mm-crypto-display-d5e8af1…`
  (input-list SHA256 `8535f8031c6fa119adf17038c0daa3fa49f19c62fd269497ef43844e31bd7600`);
  48 UI checks, strict types and isolated build passed on `cf5fe0be…`, whose
  UI/tool/test inputs remain unchanged. The refusal tests caught and fixed
  old handling that could clear a synthetic failed/unknown lifecycle fence.
  Initial Windows checks stopped after 10 passes at a protected pytest temp
  parent; this is not a Windows acceptance claim. Browser visual inspection
  could not run because local browser use is disabled; the disposable fixture
  server was stopped. No live recovery, LCD write, deployment, commit or Git
  publication. Optional Monitor 0.7.1 proposal awaits the owner's choice;
  current source/package version is still 0.7.0 and no old ZIP was overwritten.
  **Owner requested deploy + Monitor 0.7.1, then prohibited backup.** Changed
  only the app's version declaration/header and regenerated its three package
  descriptors. Both exact-version package/schema/reproducibility consumer
  checks passed on frozen copy `3mm-crypto-display-7755a4c…`; the previously
  passed 105 backend and 48 UI checks are reused for unchanged behavioral
  inputs. New ZIP is `.runtime/cap14-crypto/3mm-crypto-monitor-0.7.1.zip`,
  SHA256 `9c66701550d7e86d691e861c7aaacaba81c01ee300bd65cbe70eaba3452d901b`.
  Pinned read-only Zero W preflight still shows Core v0.3.10 and app 0.7.0,
  active but LCD blocked/enabled false. The two Core baseline hashes and
  independent Agent/connector/Runtime/host pins were observed; no device
  mutation, code export, backup, application upload or restart was performed.
  The standard immutable Core installer always creates a local DB/environment
  rollback preimage and has no skip-backup option. Stopped before deployment
  rather than altering/bypassing this boundary; asked whether the owner allows
  only that automatic rollback copy or wants Core deploy left stopped. Do not
  treat the earlier deploy request as permission overriding the later no-backup
  instruction. No commit, push, Core version change or release publication.
  **Owner approved only the automatic installer rollback copy.** No separate
  backup/export of device data or installed code was made. Downloaded and
  verified published ARMv6 0.3.10 (`413e5d62088a…`) and replaced only the two
  tested Core service files; all other payload bytes, including the frontend,
  dependencies and installer, remain from that published artifact. Candidate
  `local-lcd-review-6a9286750d90ff9555cb` archive SHA256 `7d32ac4b6ff0…`.
  Pinned preflight compared every published file to the installed release,
  verified disabled LCD output and the exact pending identity, then launched
  unchanged `install-systemd.sh` under `3mm-lcd-review-6a9286750d90.service`.
  The launch client timed out waiting for the oneshot start; a separate status
  confirmed the installer still running, preparing its release-specific Python
  environment. Do not repeat Deploy. Monitor 0.7.1 ZIP is transferred only;
  API upload/activation and final Core/receipt acceptance are still pending.
  Asked whether to approve the new package with the same scopes/human rights
  or leave activation to the owner. No grant change or LCD Start/Send/replay.
  **First deployment rolled back; launcher mistake isolated.** The task-local
  systemd launcher set `UMask=0077`, incompatible with the unchanged installer's
  `tar --no-same-permissions` extraction/venv creation. The service-user migration
  failed with Python `Permission denied` (126), before candidate activation.
  The normal installer restored 0.3.10/data and fenced stale recovery authority;
  do not silently renew the old grants or erase that fence. All six services
  are active with zero restarts, Core/Agent readiness 200, DB quick check `ok`;
  administrator login/profile/logout also passed. Existing device identity and
  credential remain active. No hardware frame or manual DB repair was sent.
  Corrected the local launcher to normal `0022` and nonblocking systemd-run.
  A disposable Linux extraction check reproduced refusal with 0077 and verified
  access with 0022. The same two tested production files are unchanged. Retry
  identity is `local-lcd-review-6a9286750d90ff9555cb-r2`, archive SHA256
  `d97b77cafdb0…`; transfer/API package upload are in progress, not yet a
  successful second Core deployment. Only normal automatic rollback copies are
  in scope. New native package/same-rights approval question remains unanswered.
  Ordinary administrator API upload/compilation of Monitor 0.7.1 has now passed;
  its exact SHA256 is in the catalog while 0.7.0 remains active. No activation,
  native consent, human permission mutation or LCD action was requested by that
  upload. The corrected r2 Core installer was launched once with normal 0022;
  final activation/health/late-receipt acceptance still awaits completion.
  **R2 reached activation, then standard rollback again.** Actual `3mm`
  read/execute checks passed throughout; the permission defect is fixed. The
  target was selected, but `three_mm_runtime.activate._wait_setup_ready` raised
  `Setup runtime readiness deadline exceeded`. That published path waits only
  90 seconds when a committed setup-activation journal remains. The installer
  returned to 0.3.10 and fenced recovery authority normally. Do not claim the
  late-receipt Core fix deployed, do not retry a third time, and do not delete
  the setup journal or renew grants to force success. New bounded blocker is
  setup/runtime readiness on Zero W; inspect the committed handoff and restore
  administrator readiness before requesting further implementation scope.
  Monitor 0.7.1 remains uploaded/compiled, not activated. No new LCD command,
  manual Core/Agent journal edits, separate backup, commit, push or release.
  **Safe handoff after R2 rollback.** The r2 unit finished failed/exit 1;
  `/opt/3mm/current` is again `/opt/3mm/releases/v0.3.10`. Old Core/Agent,
  SDK Runtime, connector and Web processes restarted with zero restarts; Agent
  readiness was 200, then Core readiness became 200. Ordinary administrator
  login, authenticated profile and logout all passed after that final rollback.
  Core/app DB status checks passed; no device credential was revoked. The
  application remained desired active at 0.7.0, but current resource/code
  approvals need fresh review after recovery fencing; do not claim effective
  access restored or activate 0.7.1 automatically. The earlier native-approval
  question is deferred until the Core readiness blocker is fixed. No third
  deployment attempt, new LCD command or security/journal bypass. Next result
  requires owner scope for the setup/runtime readiness correction and checks.
  **Owner decision: upload only, owner activates.** The delayed consent reply
  explicitly chose no agent-side activation of Monitor 0.7.1. Its normal API
  upload/compilation is already complete; leave its code/resource/human approval
  and activation to the owner. The Core late-receipt fix is still not deployed,
  so do not present 0.7.1 as ready for full recovery acceptance on this device.
  No further deployment, permission or LCD action is authorized by this reply.
  **Owner reports disabled LCD checkbox after activation.** Pinned read-only
  inspection now confirms Monitor 0.7.1 active/enabled/enforced (owner activation,
  not ours), while Core is still published v0.3.10 without `late_completion`
  handling. The exact original command `cmd_35f916f4ba7548d6a1efe9c47199d708`
  remains expired/claimed, one delivery, no completion or late receipt in Core.
  The app retains pending=true, enabled=false, blocked/outcome_unconfirmed;
  last check is invalidated after lifecycle changes. The UI's canEnable requires
  no pending frame, so this is the unresolved Core recovery blocker, not a new
  checkbox layout defect. No app invocation, grant change, frame, restart or
  deployment in this diagnosis. Core setup/readiness correction remains next;
  do not force-clear the app/Agent journal or silently repeat that command.

  **Owner-authorized Zero W activation correction, 2026-11-07.** Read-only
  inspection confirmed a committed setup-activation handoff with no pending
  setup transaction. R2's Core process was stopped before completing startup;
  the rollback Core needed about 218 seconds from systemd start to HTTP startup.
  A healthy Core health request also took 1.155 seconds, above the old one-second
  probe cap. Setup now permits a finite 300-second ARMv6 startup (90 elsewhere),
  probes Core's database-backed `/ready`, keeps the exact Agent role check, and
  caps each loopback probe at five seconds or the remaining shared budget.
  One-second backoff reduces startup polling; late replies cannot acknowledge
  the handoff. Failures and concurrent journal changes keep the durable intent.
  Frozen Linux source `46d1e6cd2d0a…`: 397 activation/planner/setup/provisioning/
  profile/bootstrap/recovery/installer/service-component checks passed, no skips.
  The two late-receipt production files match the previous 150-check candidate;
  that evidence is reused. No main frontend or Monitor changes were needed.
  Candidate `local-zero-ready-3678081b1256cd4d272f` replaces only those two Core
  files and `three_mm_runtime/activate.py` in the verified published ARMv6 artifact;
  archive SHA256 `46d5ef09a7eb…`. Started the unchanged standard installer once
  under `3mm-zero-ready-3678081b1256.service`, with normal 0022 permissions and
  only its approved automatic rollback copy. **Deployment completed successfully,
  exit 0, no rollback.** Core PID 31223 and all six checked services are active,
  with zero restarts; Core/Agent `/ready` both return 200. Ordinary administrator
  login/profile/logout passed, SQLite quick check is `ok`, and device control is
  still bound/active with its credential intact. All three exact code hashes and
  independent Agent/connector/Runtime/application-host pins were verified. The
  normal activation acknowledged the committed setup handoff; no manual journal
  deletion or security bypass. The original expired/claimed LCD command now has
  its first late failed Agent receipt and completion timestamp; it exactly matches
  the Agent journal, remains at one delivery and is no longer in the Agent outbox.
  This is completion evidence, not confirmation of physical execution. Monitor
  0.7.1 is active/enforced, still enabled=false with the original pending frame.
  Owner next: refresh `/monitor`, read the original outcome, explicitly acknowledge
  the uncertain completed attempt with output off, then separately enable a new
  live run. No grant approval/change, new LCD command, forced pending cleanup,
  separate backup/export, Git action, Core version bump or release publication.

  **Owner reports blank LCD after enabling, 2026-11-08 — diagnosis only.**
  Monitor 0.7.1 is active with zero service restarts, live enabled=true but
  blocked/outcome_unconfirmed on sequence 1. The new original command is
  `cmd_95b09af4cb104935939456514106b6d6`: 10-second TTL, one delivery after
  1.108 s, claimed, failed/unknown Agent completion 8.941 s after delivery
  (49 ms after expiry). Core correctly retains its late receipt; this is not
  the previously fixed receipt-loss defect. The installed 16x2 PCF8574 profile
  is I2C-1/0x27 with the expected pin map; adapter, node and running Agent group
  access are present. Module remains installed/enabled without a saved startup
  error; the native driver latches unavailable after an invocation exception.
  Basic Agent hello inventory is not the module capability catalog. Agent is PID
  31222, NRestarts=0; cgroup contains only the main process, no stuck LCD child.
  The physical journal intentionally replaced the concrete exception with
  `Driver outcome is unknown; automatic retry refused`, so worker deadline vs
  device I/O failure is not established. The failure's deadline proximity is
  evidence for investigation, not proof of a specific kernel/transport error.
  Import-only probes as the service user passed: normal isolated startup 1.230 s;
  no-site 1.652 s. These ran outside the service cgroup and did not open I2C or
  call write_once; they are not a timing/physical acceptance of a full frame.
  Two diagnostic helpers initially hit missing command/proc-children paths;
  corrected with an absolute runuser path and cgroup process metadata. Neither
  error reached hardware or changed services. Next bounded work is safe driver
  phase/reason evidence and an evidence-based Zero W execution budget/recovery
  fix, not blindly replaying this frame or treating expiry as non-execution.
  No production/app edits, grant change, journal cleanup, LCD write, service
  restart, deployment, backup, commit or publication in this diagnosis.

  **Prepared LCD worker fix and Agent-only update, 2026-11-08.** Compared the
  working receipt/Agent baseline: Python worker startup consumed part of every
  frame's bounded budget. Native activation now prepares one private idle child,
  without opening I2C; authorized writes reuse it. Three-second I/O and absolute
  command deadlines, one-use permits, failure fencing and no replay are unchanged.
  Frozen Linux snapshot `366cfc4870ed…`: 474 checks passed, no skips (Agent,
  display/profile, device/authority/commands and immutable component delivery).
  Windows targeted checks: 94 passed, 13 Linux-specific skips. Evidence is in
  `.runtime/cap14-crypto/prepared-worker-evidence`; behavior inputs unchanged.
  Owner approved only Agent, reserving the display action. Pinned Zero W update
  used the standard immutable controller, offline locked dependencies and exactly
  three Agent production files. Loaded build `ed039b24c1ced6be068e4e69f148018bde324c4d4f5219bf170574de3798f621`,
  PID 1116, active/ready, zero restarts; Core remains PID 31223. App/package/data,
  grants and connector/Runtime/default/application-host pins were unchanged.
  Read-only module health is fresh/healthy=true; the prepared child is sleeping
  with no I2C FD open. Original `cmd_95b09…` remains expired, one delivery and
  completed receipt; it is still the latest frame. No Start/Send, pending cleanup,
  grant change, Core update or new frame. Owner next: refresh Monitor, explicitly
  finish review of that completed uncertain attempt with output off, then enable
  a new live run. Visible output and sustained operation await the owner's test;
  the precise old driver exception was not retained, so do not claim it proved.

  **Owner sees clock frozen at 16:24; read-only diagnosis, 2026-11-08.** Current
  run reached sequence 24, with several successful frames, not one frame only.
  Last success `cmd_2802f027…` was admitted at 16:24:17 Sofia, completed in
  6.122 s. Next `cmd_b393fb5f…`, admitted 16:25:05, was delivered after 0.171 s;
  its one-use Core permit was claimed, but Agent's authorization wait failed.
  Agent's completed receipt explicitly says failed/not_executed (no driver call),
  received 0.263 s after the ten-second deadline. Core retained that late receipt.
  Monitor remains enabled=true but blocked/outcome_unconfirmed/review_required.
  `LiveDisplay._review_receipt` maps every matching late success/failure to unknown,
  ignoring the explicit not_executed output; `_check_pending` consequently fences
  this skipped frame. A local pure-method fixture reproduced that exact projection
  without creating an app or accessing hardware. This explains why automatic
  updates stopped; the reason for the slow permit response still needs profiling.
  After the owner's reboot, Agent still loads `ed039b24…`, PID 823; its private
  worker is sleeping without I2C open, module health fresh/healthy. Core PID 825
  and Monitor PID 828 are active, zero restarts. No new production edit, app call,
  command replay, frame, grant change, service action or deployment. Next proposed
  scope: distinguish an exact completed not-executed receipt from unknown output,
  retain original evidence and current-rights checks, and allow a later fresh
  frame with bounded backoff instead of permanently stopping durable output.

  **Monitor skip correction implemented at owner request, 2026-11-08.** The
  application now recognizes an exact completed failed/not_executed Agent report,
  including Core's matching late receipt; aware completion/deadline timestamps,
  command/device identities and consistent output are required. It clears only
  its resolved pending intent, retaining the original Core/Agent records and the
  last confirmed LCD content/time/digest. Five-second monotonic backoff makes no
  SDK calls; the next tick rechecks access, readiness and the same profile, then
  renders current saved content under a new sequence/request. No original replay,
  catch-up queue, authority bypass or change to TTL. Stop wins during lookup;
  retired grants, malformed/missing receipts and unknown execution stay fenced.
  Added EN/BG skipped-frame feedback and backend/UI regressions. Before the fix,
  the regression reproduced blocked instead of running; final isolated Windows
  run `3mm-crypto-display-4d24bb0…`: all 112 backend checks passed, including real
  Core package validation/reproducibility. UI copy `aa603cef…`: 49 UI checks,
  strict types and Vite build passed. The first Vitest start hit sandbox temp
  ancestry access denial; reran only Vitest on the unchanged copy with permission.
  Published exactly five checked files to `../3mm-crypto-monitor` after original
  hash/concurrent-edit and complete executed-input checks; evidence/input lists
  and copy guard live under `.runtime/cap14-crypto`. Core/Agent production source,
  manifests, schema and version remain unchanged. No ZIP build/upload, deploy,
  service action, LCD frame, commit or release; installed Monitor remains 0.7.1
  without this correction until a separately scoped new package/activation.

  **Owner requested Monitor 0.7.2, upload only, 2026-11-08.** Set the builder
  version/README to 0.7.2 and regenerated the three package descriptors. Package
  review caught the missing `last_check.status=not_executed` declaration; added
  it and a real Core validator regression for each live-operation nested status
  and get_state. Exact isolated run `3mm-crypto-display-bfd1bb15…`: all 113 backend
  checks passed. The 49 UI/type/build checks are reused for identical UI inputs,
  verified byte-for-byte; no service behavior changed after those passed checks.
  Exact ZIP passed Core package validation, repeat-build equality and wheel/UI
  source checks. SHA256 `1cf489da09882d86ee20b2a7ff231bca6c402f595b90ae98e7ef5d110fd06106`,
  46,260 bytes; saved in `.runtime/cap14-crypto/3mm-crypto-monitor-0.7.2.zip` and
  `../3mm-crypto-monitor/dist/3mm-crypto-monitor-0.7.2.zip`. Guarded publishing
  preserved other source and older ZIPs. Pinned Zero W transfer and normal admin
  upload/compilation succeeded with that exact hash/version. Installation remained
  active at 0.7.1, unchanged; probe session logout confirmed. No activation,
  consent/grant change, app invocation, LCD frame, Core/Agent update or Git action.
  Owner next: select/approve/activate 0.7.2 in Extensions and test LCD updates.

  **Monitor-only continuous output / load reduction, 2026-11-08.** Owner
  confirmed 0.7.2 displays correctly, then reported high Zero W CPU and another
  missing/unconfirmed live admission. Requested configurable intervals and no
  permanent stream stop for an uncertain LCD frame. Only the independent
  `../3mm-crypto-monitor` source was changed (plus this handoff); Core/Agent,
  rights and the installed device are untouched. New saved LCD/web intervals
  are 1–300 seconds, default 10; price requests retain their separate period.
  Browser polling is sequential, suspended when hidden, with immediate manual
  controls. Unchanged LCD content is checked locally before any SDK discovery;
  the worker no longer polls twice per second. Each new live intent commits an
  absolute SDK `not_after` of 10 seconds before dispatch. After an uncertain
  deadline, retain the original intent/outcome in bounded own history (last
  200), wait at least five seconds and respect the configured LCD cadence,
  then render a fresh state update under a new ID. This explicitly replaces
  the old permanent-unknown fence for this replaceable LCD stream only; it is
  not a generic retry policy or proof that a missed frame did not execute.
  Core/Agent journals and last confirmed content remain unchanged. Each later
  admission requires fresh rights/readiness and the originally approved
  target/profile. Access/provider faults wait and recheck without submitting;
  restored current authority can resume, never by trusting a retired receipt.
  Stop wins during SDK calls and after restart. Additive migration `0008`
  preserves settings, quotes, consent and receipts; an older pending intent
  without an absolute deadline is retained in history, never replayed, before
  the newly deadline-bound stream resumes if its checkbox was already enabled.
  Windows frozen run `3mm-crypto-display-14c55915…`: 125 behavior checks passed;
  three package consumers found an overlong permission description. Only that
  text was shortened; all three real package/schema/reproducibility cases then
  passed (`4dd41afd…` plus the live status-schema case). UI run `f673b09e…`:
  53 passed, strict types and Vite build passed. Earlier UI fixture errors were
  repaired, not ignored. Local browser mock checked dark/light and 390px layout
  with no horizontal overflow; preview server/tab were closed. Guarded copy
  verified executed input hashes and unchanged original source before publishing
  exactly 14 files. No version change, distributable ZIP, upload, activation,
  device frame, service change, commit or push. CPU benefit is not measured on
  Zero yet. Optional owner choice pending: prepare Monitor 0.7.3 next; do not
  overwrite the existing 0.7.2 ZIP with the changed schema/code.

  **Monitor 0.7.3 package prepared, owner approved, 2026-11-08.** Changed only
  the version/README and regenerated the three descriptors for schema `0008`.
  Exact package run `3mm-crypto-display-e6345bc0…`: both real Core validator and
  reproducibility checks passed. Reused the 125 behavior cases, live output-
  schema check, 53 UI cases, strict types/build and local visual review above:
  every service/UI/test/tool input is byte-identical, and the builder differs
  from the final checked candidate only at `VERSION = '0.7.3'`. Exact ZIP was
  rebuilt byte-identically, validated by Core, and its wheel/source/descriptors
  verified against those inputs. SHA256
  `cac05a293140a2a12c9455248e75d92f4d6c3ed89a0ad8cede09afbfcddecc4d`,
  48,099 bytes. Saved `.runtime/cap14-crypto/3mm-crypto-monitor-0.7.3.zip` and
  `../3mm-crypto-monitor/dist/3mm-crypto-monitor-0.7.3.zip`; guarded source copy
  updated the five version/metadata files and preserved the existing 0.7.2 ZIP.
  No upload, activation, LCD action, service restart, Core/Agent change, commit,
  push or release. Owner can upload/review/activate 0.7.3 separately; actual
  Zero W CPU and continuous-output acceptance remain to be measured there.

  **Monitor 0.7.4 — simple default / Debug-only tools, 2026-11-08.** Owner
  reports 0.7.3 currently working and is leaving it running for observation.
  Requested minimal normal controls and technical settings/one-frame tools
  only in Debug. Changed only the separate Monitor frontend, related UI tests,
  local fixture, README and version/package metadata. Normal mode now has the
  preview, one persistent LCD switch with short status, content presets,
  currencies, LCD cadence and rotation when multiple screens exist. Debug is
  local page state, off on opening; it reveals original status/IDs/receipts,
  recovery and one-frame controls, source/precision/row/timezone/other advanced
  settings. It does not weaken checks, change saved preferences, start/stop or
  send a frame. Hidden custom arrangements are preserved; draft preview can
  return to the saved view without discarding edits. The normal cold page
  performs one read-only display discovery when geometry is absent, rather
  than depending on mounting the Debug-only one-frame component.
  Frozen UI run `3mm-crypto-display-e7d0228d…`: 61 passed, strict types and
  Vite build passed. Exact-version package run `def02cc4…`: 2 real Core
  package/schema/reproducibility cases passed. Reused 125 backend behavior
  cases and the live status-schema check for byte-identical Python inputs;
  builder differs from checked 0.7.3 only in version. Schema remains `0008`.
  Local mock visual review covered normal/Debug, light/dark, desktop and
  390px width; no physical device/API was used and preview server was stopped.
  Guarded publication copied exactly 11 files after concurrent-edit/input
  checks. Deterministic ZIP/wheel/UI/descriptors passed exact-byte validation:
  `.runtime/cap14-crypto/3mm-crypto-monitor-0.7.4.zip` and
  `../3mm-crypto-monitor/dist/3mm-crypto-monitor-0.7.4.zip`, 50,039 bytes,
  SHA256 `f0bbab612f35cf9b02bc6dd3caee17301842efd28e7a38a16d367630eb5b505d`.
  Older ZIPs are unchanged. No upload, activation, LCD write, Core/Agent change,
  device/service action or Git publication. Owner's ongoing stability/CPU
  observation is not replaced by these local checks.

  **LCD stops again on Monitor 0.7.4 — Agent recovery, 2026-11-08.** Pinned
  read-only Zero W checks found Core/Monitor active without restarts, working
  price requests, present I2C and unchanged effective grants. Persistent output
  was enabled but waiting for the provider; Agent reported display unavailable
  and had no private LCD child. A failed/unknown write permanently latched both
  the display service and native transport closed. The old generic journal
  does not establish the original driver exception or an electrical cause.
  Only four Agent sources changed: separate recoverable worker retirement from
  permanent close; trusted heartbeat maintenance prepares code after a 10-second
  backoff, never from readiness/readback; do not replace an unreaped worker.
  Preparation sends no frame and does not open I2C. Only a newly authorized
  command can write, with full LCD initialization after replacement. Original
  unknown receipts and duplicate-delivery fences remain unchanged; disable wins.
  Windows targeted checks: 116 passed, 15 Linux-only skips. Isolated Linux
  snapshot `4d0fcd05f9f2…`: 462 Agent/protocol/authority/command/release checks
  passed, no skips. Its complete Agent delivery inputs exactly match the built
  candidate. Final snapshot `230dee8deceb…`: 6 worker-recovery checks passed,
  including three real private-child timeout/replacement cycles and 60 fresh
  successful frames, without physical I2C. No dependency or deadline changes.
  Owner explicitly approved Agent-only deployment and possible resumption from
  existing LCD consent. Standard immutable update/health/rollback completed:
  `ed039b24…` -> `fda365a79ede2593bda5741c952f75ad647f492042448a6e4ce0f7f278fc5b79`,
  artifact SHA256 `5a1dc892dd092582f367f5013cef7746da731ca1b8a4167da1d4b7c9a0ad3a1c`.
  Agent PID 4362 is active, no pending update journal. Core PID 825 and Monitor
  PID 827 stayed unchanged, as did package/configuration, grants, consent, other
  component pins and the original expired receipt. No Start/Send, replay, Pi
  reboot, reset, Core/Monitor update or Git action. Automatic output resumed.
  Bounded observation through 19:48:15 UTC: sequence 9 -> 22, nine fresh
  executed successes and four expired commands; later successes followed the
  earlier expiries without manually restarting output. Provider stayed healthy;
  final mode is running/frame_unconfirmed_skipped, enabled true, no pending
  frame. Last confirmed write advanced to 19:47:51 UTC. Core/Monitor kept their
  PIDs and all three services had zero restarts. Thus missed deadlines remain,
  but did not permanently stop this observed stream. No real hardware fault
  was injected; repeated worker recovery is covered by the isolated tests.
  This is software evidence, not optical readback or long-duration uptime.
  Separate deferred
  finding: Core command lookup scans existing history (313 records observed);
  do not broaden this Agent repair into a Core performance change.

  **Owner confirms LCD continues; physical-button gap, 2026-11-09.** Owner
  reports occasional errors but working display. Local Monitor 0.7.4 inspection
  confirms `button_gpio` is saved and the pure `Button.edge` policy is tested,
  but the service never instantiates it and declares no event subscriptions.
  README explicitly marks GPIO/AP/reset as unconnected. Existing generic Agent
  GPIO input event support is separate from this missing Monitor integration.
  Suggested next slice: approved input binding and short-press next-screen
  behavior; AP/reset remain separate authority and acceptance. No live pin read,
  hardware action, service change, implementation, tests or deployment here.

  **Button slice prepared, 2026-11-09 (superseded by the general slice below).** Owner confirmed GPIO17 / physical
  pin 11 to GND and approved Monitor 0.8.0 preparation, not activation or rights
  changes. Added a generic input-only `gpio.button` Agent provider and inert
  admin-panel templates, advertised only by Agents with its trusted handler.
  Exact device/package/profile approval precedes opening GPIO; no direct app pin
  access or polling. Pull-up/active-low, debounced release after 30 ms to under
  8 seconds; native duration uses monotonic kernel edge timestamps. Held-at-boot
  and long holds produce no action; no AP/reset. Generic Agent ownership checks
  refuse cross-module capability takeover before opening a new driver; disabling
  an obsolete module cannot close another owner's service or borrow its health.
  Monitor declares optional `event:button`/`BUTTON_DEVICE_ID` and an internal-only
  event handler. Migration 0009 atomically stores selection and bounded event
  deduplication; retry/restart cannot advance the same press twice. It wakes the
  existing LCD worker only after commit and never enables stopped output. LCD
  contracts/consent/receipts, prices and existing settings are preserved.
  Final isolated Linux snapshot `9c66abcd9836…`, lab `3mm-lab-ghre19lf`: 469
  Agent/profile/event/denial/revocation/optional-resource/native-artifact checks
  passed, no skips. Monitor frozen source `3mm-crypto-display-0a52128b…`: 138
  backend tests passed; unchanged exact source/UI inputs verified against that
  run and `6a43be17589b…` (61 UI, strict TypeScript and build passed). Final
  mock-Agent-to-Monitor/dedup group rerun: 11 passed. Main provider form: 20
  targeted UI checks, type-check and build passed; no new browser visual
  acceptance. Reproducible, Core-validated ZIP `3mm-crypto-monitor/dist/
  3mm-crypto-monitor-0.8.0.zip`, SHA256
  `588a794bbe64bd6f630fb9760cae3492f73614f59a4a5bf4a4881ab932a77a7b`.
  Guarded source publication verified every original baseline file before
  copying only the 14 scoped files; old ZIPs untouched. Next requires reviewed
  Core/Agent update for the new provider/template, then owner install/resource
  approval and physical button acceptance. No device action, upload, activation,
  grants, Git mutation, Core version change or release in this slice.

  **General CAP14 input/provider slice prepared, 2026-11-09.** Owner rejected
  repeating Core changes for individual peripherals and approved Monitor 0.8.1,
  preserving the earlier 0.8.0 ZIP. Replaced the unshipped button-specific
  handler/contracts with profile-configured `gpio.digital.input` 2.0 and generic
  `gpio.input.changed` edges. One approved profile maps 1–7 logical inputs to
  distinct supported BCM pins, with configurable debounce. Native edges retain
  kernel monotonic timestamps, per-channel sequence and activation stream ID.
  Exact profile/ownership/board checks precede opening GPIO; partial construction
  releases claimed lines. There is no application GPIO polling or AP/reset logic.
  Monitor owns short-press interpretation, current device/channel/pin filtering,
  gap/reorder/duplicate rejection and atomic migration 0009 state. Restart
  disarms an unfinished press. Existing LCD consent, receipts and output remain
  separate; a button never starts stopped output.
  Core now reads inert package-supplied form definitions, not a Python registry
  of drivers. Five public starter resources live in `backend/provider_templates`;
  an uploaded third template with a different logical channel works through the
  same admin catalog/preparation path without Core/Agent source changes. Bounded
  typed scalar bindings cannot change privileges, entrypoints or contract shape.
  Exact source-ZIP SHA pins selection; a distinct derived instance namespace
  avoids immutable-ID conflicts even for default settings. Corrupt descriptors
  and health-marker CRCs are refused as validation failures; a broken optional
  source cannot take down the catalog and remains visible for removal. Preparing
  bytes does not install, approve, open GPIO or queue a command. The authoring
  generator is not imported at runtime; release/deploy inclusion was inspected.
  Final Linux template/package-consumer group: 65 passed, no skips, snapshot
  `bc5cd108dabc6c68cb4080b6f4409ffac30e62f92105b325a510c6f7fdab1753`;
  evidence `.runtime/cap14-gpio/runs/cap14-generic-templates-731a6113f0024113822318f954ec3922`.
  Final broader Agent/profile/event/authority/artifact integration: 552 passed,
  no skips, 142.09 s on the same source/dependency environment. Evidence:
  `.runtime/cap14-gpio/runs/cap14-generic-input-c3ba8c3e1fbb4c35b333e0e031854833`.
  The initial integration failed because private-data snapshot filtering also
  omitted starters placed under `backend/data`; moving public assets to
  `backend/provider_templates` fixed delivery without weakening that filter.
  Main provider UI: 20 targeted checks, type-check and build passed; no new
  browser visual acceptance. Monitor frozen checks: 143 backend and 61 UI plus
  strict TypeScript/build passed. Exact input comparison permits their reuse
  after the version-only 0.8.1 edits; 2 exact-version package checks also passed.
  Deterministic ZIP validated twice with current Core:
  `../3mm-crypto-monitor/dist/3mm-crypto-monitor-0.8.1.zip`, SHA256
  `9a26530280730ef99ae6bcfd3a1c4c7acd56bc9be0e3264cc34699554c31cd96`.
  Guarded publication verified sibling baseline hashes and copied only 9 scoped
  source/descriptor files plus the new ZIP; old 0.8.0 ZIP remains unchanged.
  Limits: arbitrary new native driver loading is not implemented; current
  primitives still need one reviewed foundation rollout. Older GPIO event
  sources lack the new timestamp/stream guarantees; general event-schema
  compatibility preview remains a separate discovery gap, not physical input
  acceptance. Next: separately approved Core/Agent rollout, then owner provider
  installation/event approval and GPIO17 physical trial. No device action,
  upload, activation, rights change, Git mutation, Core bump or release here.

  **Owner-approved dual-device rollout completed, 2026-11-09.** Pinned SSH
  identities verified separately for Zero W (`rasp-3mmw`, ARMv6) and Pi 3
  (`rasp-3mm`, aarch64); no state/rights migration between devices. Standard
  immutable Core deployments succeeded as `local-zero-gpio-191d694d32e8aa0eb73b`
  and `local-pi3-gpio-570e061c22d437f8202b`. Exact inventories, readiness,
  independent pins and existing app/configuration/grant digests were verified.
  Owner independently activated Monitor 0.8.1 on Pi 3 during preparation;
  preflight caught the changed baseline and the fresh plan preserves that
  choice and all three installations. Zero retains active 0.7.4. No app
  activation or grant change was performed here.
  Agent updates stopped in isolated staging imports, before publication,
  pointer changes or update journals; old Agents remain healthy. Measured old
  and candidate Pi 3 imports both succeed in about 20.4 s against a 20 s stage
  limit; Zero's healthy old import succeeds in 90.63 s against 90 s. This is a
  demonstrated controller deadline defect, not failed GPIO startup. Agent
  stage/readiness now allow bounded 60 s (180 s ARMv6), retaining exact build/
  PID checks, final deadlines, rollback and unchanged other-component budgets.
  Linux checks: 101 unchanged successes reused from source `29a0033a8cd0…`,
  plus two corrected Public Web budget assertions passed on `2f4194831e98…`;
  only that test file changed, all production/dependency inputs identical.
  Includes real artifact/update/rollback consumers, timeout no-publication,
  wrong identity and late correct-identity refusal. Second immutable Core
  candidates change only `deployment/service_component.py`; no installed
  controller patch/bypass. Pi 3 second Core deployment and Agent continuation
  succeeded: Core `local-pi3-gpio-87b412bd29235429867c`, PID 7569, ready;
  Agent `37324174b1b8bb12492163ac3dc6e6d05fd516e3a72e4337f6e2bf135c612aca`,
  PID 8168, running with zero restarts. Final independent inventory/source/
  dependency/app/grant/pin proof is `.runtime/cap14-gpio/pi3-final.json`.
  Monitor 0.8.1 remains owner-selected and active; all three installations are
  unchanged. Zero second Core installer also succeeded as
  `local-zero-gpio-72faf364491568e394d0`; full inventory, ready response and
  unchanged Monitor 0.7.4 settings/grants/pins were verified before starting
  its standard Agent continuation. One three-second cold-start HTTP probe
  timed out, then the installer completed successfully without rollback.
  Zero Agent continuation succeeded with build
  `a4f3044711536ab66ac362407e90fe6f3958f66269fbd79e0870508f27b8ac80`,
  artifact SHA256 `390b0fb7ad3330db5ff6e19a7275b33185350fb5faed4e78f8686fd0b77a6cb1`;
  Core PID 27499 stayed unchanged during Agent activation. Final read-only
  rollout verification passed for exact Core files, native source/dependency
  binding, readiness, original app/settings/grants and other component pins.
  Monitor 0.8.1 ZIP above was uploaded/compiled through the normal Zero Core
  catalog API, not activated. A follow-up template check initially used the
  wrong read-only route and returned 404; inspection at the correct route
  confirmed the exact package already present, so no second upload occurred.
  The normal admin API reports five templates including native GPIO input;
  the probe session was logged out. Zero still runs 0.7.4 for owner activation.
  Owner next: install/review the GPIO input profile in Devices (GPIO17 / pin
  11 to GND), activate Monitor 0.8.1, select the optional input resource and
  approve its event access, then test short presses with multiple saved screens.
  No provider installation, event approval or explicit hardware command was
  performed; existing persistent LCD consent could resume after service starts.
  Only automatic installer rollback preimages, no separate backup, device
  reboot, state migration, Core version bump, commit, push or publication.

  **Pi 3 reactivation failure diagnosed read-only, 2026-11-09.** Owner later
  reported Monitor cannot activate. Fresh pinned snapshot still has the exact
  Core/Agent deployment and Monitor 0.8.1 ZIP/configuration digest, but Monitor
  is now disabled, `authority_mode=review_required`, with no grant; Core/Agent/
  Runtime are healthy and the stopped app has no crash/error record. Package
  preparation, compiled UI files and review-key read lease pass. The current
  authority status itself raises ValueError, so fresh consent cannot proceed.
  Strict read-only composition and safe stack/schema metadata identify the
  exact defect: `_registration()` bounds the ENTIRE effective device capability
  registry before selecting `display.character`. Installed `gpio.digital.input`
  declares public schema `monotonic_ns.maximum=9223372036854775807`; the generic
  authority-context JSON copier rejects numbers over `2**53-1`, including that
  unrelated schema bound. Thus a GPIO provider prevents even LCD review, not
  merely the optional button scope. Missing optional providers alone are already
  omitted correctly. Do not remove the provider, weaken grants or blindly retry
  activation. Next bounded correction needs distinct bounded contract-schema
  handling and real combined GPIO/LCD fresh-consent coverage; ordinary authority
  values must retain their safe-integer/size/depth limits. No production code,
  rights, app activation, service, package or hardware changes in this diagnosis.

  **Owner-approved Core schema-metadata correction, 2026-11-09.** Explicit
  schema slots come from trusted protocol/model annotations, never arbitrary
  configuration key names. Only integer numeric bounds/enums in those slots
  accept signed-64 values; ordinary JSON, configuration, request values,
  revisions and clocks retain `2**53-1`. Finite-float, byte/node/depth limits,
  typed canonical encoding and old fingerprint vectors remain unchanged.
  Registry resolution, source/control identities, consent/subject/policy
  comparisons, sealed plan/grant/action roundtrips and direct query/relational
  consumers share this rule. No protocol, SDK, Agent, API or DB migration.
  Real Linux fresh-consent coverage uses validated LCD/GPIO Agent packages,
  optional absent/unhealthy input, real protected seals/native admission,
  non-administrator refusal, revocation and another application's isolation.
  The LCD-only test with the exact old 13 Core files reproduces the refusal at
  preview; the same test passes with the fix. No provider removal workaround.
  Final focus snapshot `207d3bd0d0c7…`: 26 passed. Authority, contexts and
  consumers: 539/402/397 passed on `bcbf3897df6d…`; only the new focus fixture
  changed between these snapshots, verified before reuse. Final query/relational
  group: 184 passed. Across overlaps: **1405 distinct passed, 30 skipped**
  (separate-root/foreign-UID or non-POSIX boundaries, not executed acceptance).
  Python 3.14.4/Linux, dependency digest `f91ccaad806c…`; retained JSON/XML/logs
  and the expected old-Core negative result under `.runtime/cap14-schema/`.
  Exact scoped diff/whitespace reviewed; no main frontend changes/build.
  Pinned Pi3 preflight matched all files, component pins, three apps' package/
  configuration/grant digests and both provider installation records. Prepared
  only these 13 tested Core files over the exact installed immutable archive;
  unchanged Core runtime dependencies match the test source. New archive
  SHA256 `96187ba822c1d9efb201982f8e8ebb79bd2e9c8cdeac6645c819d060a5b3d422`,
  release `local-pi3-gpio-a77670c29bf2fb7306a9`. Normal installer
  `3mm-pi3-gpio-a77670c29bf2.service` succeeded; exact installed Core files,
  `/ready`, all independent pins, three apps' package/configuration/grants and
  both provider installation records passed post-deploy verification.
  Read-only current Core inspection now reports Monitor `review_available=true`,
  no review blockers, and all four scopes (LCD, two connectors, button event).
  Monitor remains disabled on exact 0.8.1 ZIP, no grant or access saved: the
  missing UI trust record is expected until owner approval, not a new refusal.
  Only standard automatic rollback preimages; no separate backup, reboot,
  Agent/Runtime/host update, app activation/approval, hardware command or Git.
  Owner next: reopen Application access, approve the exact selected resources
  and separately activate Monitor. Live LCD/button acceptance remains theirs.

  **GPIO17 no-visible-response follow-up, read-only, 2026-11-09.** Owner has
  now approved/activated exact Monitor 0.8.1. Current signed grant is valid and
  includes `event:button`; selected device/channel match native GPIO17 and
  the app has two saved screens. Core, Agent, Runtime and Monitor have zero
  restarts. Enabled native GPIO provider is healthy without a runtime error.
  Core contains eight real `gpio.input.changed` edges, contiguous source
  sequence 1–8. Four deliveries were acknowledged (one app result `advanced`,
  three `ignored`); three deliveries became `dead_letter` with zero attempts
  and generic event-authority refusal; one edge has no delivery row. Missing
  press/release halves explain the app's later ignored pairs. This is evidence
  of successful capture/transport, not a broken pin or missing owner approval.
  Source audit: `effect_admission()` uses a shared verification key lease for
  command/connector only, unnecessarily exclusive for events. Its broad catch
  erases transient key/DB errors into ValueError. `_event_granted()` converts
  that to false: enqueue silently omits the event, while claim/final admission
  permanently dead-letters it. A disposable Linux test on unchanged deployed
  production code reproduced this with a real independent shared key reader:
  valid grant succeeds before/after, fails only while the reader holds the
  lease, and enqueue retains no delivery. The one passing diagnostic case
  proves the bug, NOT a repaired implementation. Original WSL temporary
  evidence disappeared before durable copy; retain the returned tool-output
  only, explicitly marked recovered (no claimed original XML), under ignored
  `.runtime/cap14-gpio/button-lease-diagnosis/`. No live event replay or state
  mutation. Next bounded fix: general event verification should not conflict
  with unrelated readers; distinguish temporary admission unavailability from
  real revocation/binding change and retain bounded pending unsent work without
  invoking a handler before fresh admission. Keep real denials fail-closed and
  old terminal evidence intact. No production edit/deploy/permission change in
  this diagnostic follow-up; request owner scope before the next Core rollout.

  **Owner-approved Core-only event delivery fix, 2026-11-09.** Event grant
  verification now shares the read-only key lease used by commands/connectors.
  Only actual flock contention and SQLite BUSY/LOCKED are typed temporary
  admission failures; missing/corrupt keys, revoked rights, epoch/artifact changes
  and missing authority storage remain real refusals. Unsent pending heads keep
  their original ID/epoch, FIFO position and attempt count, with a one-second
  admission backoff. Runtime still admits freshly before a durable claim/send.
  HTTP captures each NEW device event and its initial declaration/epoch matches
  in one transaction before 202, without key admission or handler execution in
  that transaction. Contention rolls both back and returns 503 for the Agent's
  existing same-ID outbox retry. Exact duplicates never rematch historical events
  under later rights. No migration, historical sweep or terminal replay.
  Final isolated Linux groups: **774 passed, 4 skipped**. Snapshot
  `1756b0775c6a…` includes the final 17 real-lock/SQLite/HTTP regressions and
  onboarding with two adapters/apps. Authority/effects/UI results on
  `4b60f98995f8…` are reused: the only subsequent source difference is the
  standalone onboarding test's bounded second Runtime poll, not production.
  Skips: distinct-UID/root boundaries, non-POSIX-only refusal and the optional
  browser decoder's absent Node/esbuild toolchain. No frontend code/build change
  or full hosted CI claim. Exact XML/log/input hashes are in the ignored
  `.runtime/cap14-events/runs/` and deployment plan.
  Prepared five-file delta over the exact installed Core archive, preserving all
  other payload bytes. Candidate `local-pi3-gpio-da5bc57e32111fb7dbd4`, archive
  SHA256 `d0edec1f59ebb8bea643c3c7e0ce24c295f167029e0903c24e3c88d40ba87109`.
  Pinned Pi3 preflight and standard immutable installation completed successfully:
  `3mm-pi3-gpio-da5bc57e3211.service`, Result=success, exit 0, SubState=exited.
  Exact installed payload/metadata checks and Core `/ready` passed (PID 36819).
  Core, Agent, Runtime, connector and both enabled app hosts are active/running,
  each with NRestarts=0. Standard installer service restarts occurred, but all
  independent component pins, three application packages/configurations/grants
  and two native provider installations are unchanged. Monitor remains 0.8.1;
  Agent remains `37324174b1b8…`. All seven old terminal deliveries were compared
  exactly and retained, not replayed. Final read-only snapshots are ignored
  `cap14-schema/event-final.json` and `cap14-events/final-extra.json`.
  Automatic rollback preimage only; no separate backup, Agent/Monitor update,
  rights change, explicit hardware command, reboot, Zero W action or Git action.
  Owner's physical short-press GPIO17 acceptance remains separate; do not claim
  a new hardware edge or visible screen switch from the software checks alone.

  **Queued next, owner request: smooth clock with seconds.** Separate the clock
  from data/status polling: local web ticking and occasional time synchronization;
  physical LCD ticking must be local to its provider, with I²C writes but no
  per-second Core/internet request. Current Monitor source is under the sibling
  `3mm-crypto-monitor/source/frontend` and `service/crypto_monitor` directories.
  Read-only design audit only so far; no clock code, contract, package/version,
  provider authority or device change is included in this Core-only rollout.

- **CAP20 — read-only application-host resource report, 2026-11-06.**
  `tools.application_resource_report` reports the current unit's CPU, memory
  and task caps from Linux cgroup v2. It distinguishes a finite kernel cap, a
  cap not set at this cgroup level and an unavailable observation. Changed
  unit/cgroup identity discards the sample. No new service, admin endpoint or
  isolation claim. Final Linux snapshot `020453279ae7…`: 11 report checks
  passed; same 11 passed on Windows. The unchanged systemd templates passed
  26 regression checks in the preceding Linux run (`54cd31949f04…`). Exact
  final report was run read-only over pinned SSH on `rasp-3mm`: one active
  application host showed one CPU-equivalent bandwidth and 64 tasks. systemd
  reported MemoryMax=256 MiB, but the memory controller is absent at the root
  and the running kernel command line contains `cgroup_disable=memory`; the
  tool reports the memory limit as unavailable, not enforced. No boot change,
  restart, load test, deployment, commit or push; owner runs Zero W acceptance
  separately. Suggested next CAP20 slice: surface missing controllers before
  an operator relies on a configured cap; live memory enablement is separate.
  **Preflight warning added locally.** The standalone full-profile bootstrap
  preflight reports unavailable/unverifiable cgroup v2 memory as `WARN`, not a
  required failure; available at the root is not proof of per-unit enforcement.
  The last-line format and required failure exit remain unchanged. Exact Linux
  snapshot `b517b4dd6c03…`: 186 preflight/bootstrap/packaging/report checks;
  Windows: 23 checks. Exact standalone checker on `rasp-3mm` over pinned SSH
  reported `WARN resources.cgroup-memory` and `result=ready failed=0` with exit
  zero. No boot, network, service, Node profile, deployment or Git change.
  **On-device memory cap accepted on rasp-3mm.** With explicit owner approval,
  verified the mounted Pi 3B+ boot partition and saved the original as
  `/boot/firmware/cmdline.3mm-cap20.bak`. The default `cgroup_disable=memory`
  was present only in the live boot arguments; appended one
  `cgroup_enable=memory` to `/boot/firmware/cmdline.txt`, preserving the rest
  and verifying both checksums. Issued one restart and confirmed a new boot ID,
  unchanged Core release, Core `/ready` and active Core, Runtime, Agent and
  the same application. Its signed health/Core-Runtime probe passed; the
  kernel now exposes memory at the cgroup v2 root and application
  `memory.max=268435456` (256 MiB). The exact preflight changed from WARN to
  PASS, still `result=ready failed=0`; CPU and tasks caps are unchanged.
  No stress/OOM trial, installer change, Zero W action, commit or push in this
  device acceptance. Restore the saved cmdline and restart only if rollback
  is separately requested; the original remains on the boot partition.
  **Report and preflight pushed.** Commit `b54f27451c50` on `main`; CI run
  `42163321645` was in progress at handoff. Reused the 186 Linux and 23 Windows
  checks for the exact code/test inputs. The mixed work log and simplification
  plan remain local. The ignored `.runtime/cap20-memory-boundary/` probe and
  runbook are prepared: 32 MiB, no swap, one transient unit, Core readiness and
  unchanged service invocations. The dry plan and simulated limit, outcome and
  cleanup checks passed. **Live memory-boundary trial accepted on `rasp-3mm`.**
  With owner approval, ran the reviewed probe once over pinned SSH. The
  temporary unit verified its own kernel limits and ended with `Result=oom-kill`;
  cleanup verified inactive. Core `/ready` passed before and after and at all
  10 active-probe samples. Boot ID and all five service invocations (Core,
  Runtime, Agent and two application hosts) were unchanged. This checks process
  continuity, not application requests under sustained load. No deploy, reboot,
  release or Zero W action. CAP20 CI `42163321645` later failed on the lost
  task-admission reply test; see the scoped follow-up below.
  **Supervision reporting added locally.** The same read-only command now
  distinguishes stopped, starting/stopping, automatically restarting and failed
  hosts. It reports the bounded systemd result and restart counter separately
  from live kernel limits, and discards both observations if the unit changes
  during the sample. Linux snapshot `7eb4c5be74b9…`: 47 report/template checks
  passed; Windows: 21 report checks passed. Also checked the property format
  of a stopped and an active standard service in WSL, read-only. No Raspberry
  Pi acceptance, service policy change, deploy, commit, push or release change.
  **Application restart budget added locally.** Each app unit keeps a 3-second
  retry delay and allows five starts per 60-second systemd interval; exceeding
  the limit stops automatic restarts for that unit without a host/Core action.
  Reviewed activation and rollback rearm only their selected units before start;
  no new API or authority path. Backup resumes Core/Agent first and does not
  rearm failed/auto-retrying instances. Linux snapshot `889b0a7317c9…`: 400
  checks passed, 43 skipped for separate root/optional image profiles; installer
  syntax passed. A disposable WSL systemd fixture confirmed exhaustion via the
  manager journal (unit result retained `exit-code`), refusal before rearm,
  and successful start after an exact-unit reset. Fixture stopped and removed.
  No Raspberry Pi acceptance, deployment, commit, push or release change.

- **Zero W clean-install login loop, 2026-11-06 — diagnosed read-only.**
  Owner reported two successful clean installs, then repeated logout after
  Crypto Monitor activation. On the current `rasp-3mmw` card, pinned SSH
  confirmed v0.3.8 and Crypto Monitor 0.7.0 active. In the retained boot,
  Core and the application had no restarts, Core `/ready` returned 200 and
  there was no kernel OOM record. At 06:55 EET two successful logins were each
  followed within a second by HTTP 401, including `/api/user/refresh`.
  The active SQLite DB (`b096b7e82f86`) contains one unblocked administrator
  with NULL `subject_id`; the recent sessions are active and unexpired.
  Installed first-boot SQL omits `subject_id` when creating the administrator
  after migration, while both application access and token refresh require
  it. The application exposes the provisioning defect; it did not crash Core.
  Owner requested the clean-install fix only. `065b528b6c3e` assigns a fresh
  subject in the first-boot insert. No backfill, migration, or change to existing
  identities, permissions, or login checks. The regression reproduced 401 after
  login on a fresh database migrated to head; final test verifies application
  access, refresh preserving the subject, and denial after logout.
  CI `42163321645` failed separately in `test_lost_admission_reply_uses_original_lookup_only`.
  `99925678529d` removes the test's dependence on cold worker process startup
  and result polling: the real worker claims once through Core's socket and
  the original lookup verifies success, no second execution. No production
  task changes or widened deadlines. Linux snapshot `e92a1346808e…`: 193
  checks passed, one superseded assertion in the new first-boot test; final
  snapshot `f02b2ac09210…` passed the corrected first-boot test and three
  lost-reply runs. The corrected first-boot test also passed on Windows.
  Both commits pushed to `main`. CI `42168210102` advanced past the Core
  suite, then failed `agent/tests/test_role.py::test_setup_service_role_is_consumed_by_agent`:
  the copied test table omitted `subject_id`, so setup correctly returned 409.
  `92dab4846afc` uses Core's current user-table definition in this integration
  test; production code and checks are unchanged. Exact Linux snapshot
  `6b8dff552982…`: 2,865 passed, 11 skipped (root/systemd/optional media)
  across the Agent and remaining Python suites plus first-boot/session tests.
  Windows Agent-role and Setup API: 53 passed. Follow-up pushed to `main`;
  CI `42173867312` in progress. No device changes, restore, restart, reinstall,
  deployment, tag or release. Physical clean-card acceptance awaits the next
  published artifact.

- **Zero W upgrade to published v0.3.8, 2026-11-05.** At the owner's request,
  upgraded the existing full-profile `rasp-3mmw` using the published v0.3.8
  ARMv6 release and tagged bootstrap. The archive checksum and preflight passed;
  the detached installer reported deployment succeeded. Core, Agent and Platform
  Runtime are active, Core `/ready` and the frontend returned HTTP 200. Current
  points to `v0.3.8`; previous remains `experimental-037-armv6-r6`. The existing
  Crypto Monitor installation row remains disabled and requires access review;
  no recovery, access approval or activation was performed in this upgrade.
  This is an upgrade on existing media, not clean-install acceptance or proof of
  Crypto Monitor activation on the published release.

- **Core 0.3.8 candidate — ARMv6 Hub and stopped-package recovery, 2026-11-05.**
  Owner requested installer fixes, deploy to `rasp-3mm`, then commit/push and
  an immutable release only after green CI. The bounded CAP10 guest draft is accepted separately.
  The new ARMv6 Hub archive includes pinned Rollup WASM 4.65.1 and esbuild
  0.25.12 built with Go 1.24.12 and GOARM=6. Bootstrap selects the separate
  full-profile ARMv6 catalog, keeps the OS network by default, and installs
  ARMv6-only Python build prerequisites. The compiler is exercised before
  switching services. Python 3.13 is required; Node and other Hub architectures
  retain their previous artifact selection. Coordinated ARMv6 time budgets
  preserve actual health checks. The new exact release still needs hardware
  clean-install acceptance on Zero W; earlier r4/r6 trials are not that proof.
  Explicit recovery can return a verified stopped ordinary package to access
  review, including the previously recovered disabled state without inert
  provenance. It does not replay activation, approve access or erase data.
  Rechecked the real sealed lifecycle, prior-grant fencing and explicit
  reapproval before activation. First Linux snapshot `92c5a6323a44…` passed
  388 focused cases; Windows UI 24 and TypeScript passed. Final checked
  aarch64 deployment kit `720cd778e409cf15f3579200…` passed 219 Linux checks
  and reused the exact-input frontend build and 876 frontend tests. Independent
  builds of the four Core archives matched byte-for-byte; only the ARMv6
  archive contains the compiler bundle, and only its catalog offers ARMv6.
  Owner independently confirmed the new SSH fingerprint. The first aarch64
  rollout returned to healthy v0.3.7: after a prior restore, the installer had
  preferred a stale sidecar key over the Core environment that matches the
  restored database. Read-only checks confirmed the environment key unlocks
  the identity and the sidecar does not. The installer now validates the
  preserved key before downtime and leaves the legacy file unchanged. No key,
  grant or identity was changed manually. Corrected kit `d307005fd76990d0…`
  passed 322 Linux checks and reused the same 876-test frontend build. The
  `rasp-3mm` rollout ended `succeeded`; Core, Runtime and Agent were active and
  `/ready` responded. The restored key still verified the database identity.
  Commit `a7caecc4f833…` is on `main`; CI run `42024060565` failed on CAP10
  checking a public form route before refusing a retired job. The follow-up
  restores the early denial and passed 199 focused checks, with one distinct
  OS-principal test skipped locally. Kit `f57ea2449db6253a…` deployed and
  reached `ready` with Core, Runtime and Agent active. Follow-up commit
  `05c818eee995…` is on `main`; CI run `42027324166` must pass before tagging
  `v0.3.8`. Stopped the local publisher on the owner's new Crypto Monitor
  report; left CI running and confirmed no remote tag. On `rasp-3mm`, Crypto
  Monitor 0.7.0 is stopped with its verified package and saved configuration.
  The review key is readable and belongs to this installation, but it does
  not match the current authority generation, which exactly matches the first
  deployment rollback. This blocks approval/activation independently of the
  installer encryption-key fix or LCD. Three installed applications use scoped
  access. Owner explicitly approved recovering the review key. Ran the
  authenticated/audited `recover-key` once as the Core service account with the
  expected old key and installer mutation lock; confirmed the new key is bound
  to the current generation and closed the temporary login session. Installed
  package pins, configuration and application states were unchanged. Crypto
  Monitor remains disabled; its review is available and its old grant is not
  effective. No new grant, activation, device command or deployment occurred.
  Next: owner reviews access in Extensions and separately chooses activation;
  keep release paused until application acceptance and owner direction.

  Follow-up: Extensions now offers explicit admin recovery for a readable,
  stale review key belonging to this Core. Confirmation is bound to the key
  ID and current recovery generation; the existing grants remain invalid,
  application state/data are untouched, and nothing is started or replayed.
  CI run `42027324166` failed only the Linux job `127244787537`: the first
  event dispatch was never attempted (`pending`, attempts 0). An isolated
  baseline did not reproduce the intermittent timeout. The process fixture
  no longer shares pooled SQLite handles across fork and has a regression
  check for ownership; startup failures now reap their own child. The
  production event code and test deadlines are unchanged. Final Linux snapshot
  `7cbc790dcbe5…`: 181 passed, 4 platform/privilege checks skipped. Extensions
  and authority UI: 84 tests, TypeScript and production build passed. A fresh
  remote CI result is required before release. With owner approval, pushed
  only the two fixes and their documentation to `main` in `997cdc5e337e…`;
  CI run `42066690157`: the first Linux suite passed (6717 passed,
  611 skipped), including the event regression. The deployment/SDK suite
  stopped at the CORS environment test, which referenced the removed
  master-key sidecar branch. The test now supplies a synthetic preflight
  value and checks the staged environment before the live write. The exact
  corrected Linux snapshot `65e990c2e89e…` passed the entire deployment/SDK
  group: 745 passed, 8 optional or privileged checks skipped. No installer
  behavior changed. Owner requested push and CAP12 work while CI runs.
  Pushed only the test fix to `main` as `9e1f02b5f05a…`;
  Exact main push CI `42075813285` completed successfully. Owner requested
  release; annotated `v0.3.8` pushed at `9e1f02b5f05a…`, starting Release
  `42080617487`. Publication not yet confirmed; no CAP12 or device deployment.

- **CAP12 — signed callback verifier, 2026-11-05.** First local slice:
  fixed HMAC-SHA256 profile binds the exact bounded body, trusted endpoint
  audience, event ID and timestamp. The first verifier-only slice did not
  change CAP10. See the
  [Public Web contract](PUBLIC_WEB_EXTENSION_PLAN.md#cap12--signed-callback-verifier-local-contract-only).
  Windows: 29 verifier cases passed. Exact Linux snapshot
  `fadfa5c589a9…`: 894 protocol and Public Web tests passed, no skips
  (includes the verifier cases). CAP12 changes stay local.
  Follow-up: `tools.webhook_lab` serves one literal loopback-only POST with a
  read deadline, strict framing and a versioned, separate SQLite inbox.
  `202` follows commit; fresh signed retries get the original receipt, changed
  bytes conflict, and a failed commit or full inbox never returns success.
  Real HTTP tests cover lost acknowledgement, key replacement, malformed
  framing, and stopping/reopening in a separate process without a second row.
  Windows: 50 focused tests passed. Exact Linux snapshot `1173ef95e22d…`:
  915 lab/protocol/Public Web tests passed, no skips. Tests used synthetic
  data and terminated the local listeners. No Core migration, installed route,
  application dispatch, deploy, commit, push or release for CAP12.
  Reviewed-lab follow-up: explicit exact instance/package binding, pinned to
  Core generation, incarnation, epoch and grant record revision. Current sealed
  approval and active state are checked for each valid signed request under the
  existing authority fence through the local inbox commit; no app invocation.
  Disable, revoke, package drift and revoke-before-admission deny without
  exposing receipts. Fresh consent cannot reopen the old inbox. Version-2
  disposable inbox uses a fresh directory; old files are not migrated or reset.
  Windows: 51 focused checks. Linux snapshot `923dc554f106…`: 178 CAP12,
  authority/consent, lock-order, CAP10 and Public Web tests passed, no skips.
  Declaration/delivery follow-up: the opt-in SDK 1.3 package profile declares
  one literal `/webhooks/` path and an exact redacted internal handler.
  The reviewed lab accepts only that path; the generic gateway refuses the
  dedicated handler. A current admin separately reviews, confirms and can
  revoke delivery for the exact binding. The current decision and historical
  receipt use the existing sealed journal; replay, stale approval, a changed
  grant/audience and corrupt seals do not authorize delivery. Revoking delivery
  does not delete receipts or stop ingress for a still-reviewed installation.
  Windows UTF-8: 120 focused tests passed. Exact Linux snapshot
  `918f876c006b…`: 1133 passed, 2 environment-specific key tests skipped.
  This declaration/approval slice did not invoke an application.
  One-shot delivery follow-up: a separate local caller claims one exact
  reviewed receipt in the v3 lab inbox, releases the Core authority fence,
  then sends one bounded signed invocation to the pinned disposable host.
  The receiver writes exact bytes to its own SQLite data. Signed matched
  results are persisted; lost or mismatched replies keep the durable attempt
  unconfirmed. Reopening, repeating or racing the caller cannot resend it;
  revocation while waiting prevents a new claim. Matching v2 inboxes upgrade
  in place without replacing receipts. Windows: 105 focused passes. Linux
  snapshot `e9dfdcaf7f28…`: 1012 passed, 3 failed in an old dispatch test
  double missing the optional declaration. After correcting only that double,
  snapshot `4ba252fb4d77…`: 21 dispatch and CAP12 integration tests passed.
  Retention follow-up: the v4 lab caps bodies at 128 and metadata at 4096.
  It clears raw bodies on terminal outcomes or after the one-hour window
  without reusing receipt IDs or losing unconfirmed attempts. New signed
  copies never rearm an expired receipt. Matching v2/v3 inboxes upgrade in
  one transaction; v1 stays untouched. Windows: 107 passes. Isolated Linux
  snapshot `777523a605c0…`: 76 passed, including actual host non-delivery
  after expiry, preserved unknown outcomes, and v2/v3 upgrades.
  **Loopback candidate ready to close:** `consume_pending` picks eligible
  receipts without caller-supplied IDs, at most four per explicit cycle,
  rechecking the current review on each claim. An absent host does not take
  new work; revocation blocks the next claim. In the process-boundary test,
  the first consumer exited after the real receiver committed but before the
  acknowledgement was persisted. A fresh process sent only the next receipt;
  the first remained unconfirmed. Windows: 107 passes. Broader Linux snapshot
  `8870b42d3172…`: 1020 passed, one restart fixture lacked Core ORM relationship
  imports. Corrected fixture only; final snapshot `957a35f745e3…`: all 19
  CAP12 Core integration tests passed, including the restart. No Core migration,
  installed public route or worker, or deployment. On owner request, the scoped
  checkpoint `e683045` was pushed to `origin/main` and the remote ref was
  verified. No tag, release or deployment. Public route ownership, key
  provisioning/rotation and supervised deployed operation are a separate
  acceptance gate. Proposed next: one isolated Public Web pilot with synthetic
  events, explicit opt-in and a tested stop path; no live exposure by default.
  **Public Web pilot passed locally.** An independent Public Web process ran
  on an ephemeral IPv4 loopback port, off by default. The private Unix ingress
  broker owns the synthetic key and durable inbox; Public Web owns neither.
  The real HTTP/host test confirmed dedupe, malformed/unsigned refusal,
  process exit after receiver commit without replay, and new-claim denial
  after revoke. Stopping only the broker closed webhook intake; a real CAP10
  form on a pilot-configured listener still submitted through Runtime/Core.
  Windows: 82 passed, one Linux-only test skipped. Isolated Linux snapshot
  `6de2d8b10f92…`: 152 passed (including service packaging), one pilot test
  used the standalone lab URL for refusal cases. Corrected the test URL only;
  snapshot `605ee3ed8b08…`: both pilot integration checks passed.
  **Local closure gates:** activation reserves webhook and HTTP paths,
  rechecks concurrent ownership under the lifecycle fence before helper I/O,
  and leaves ordinary forms working when a legacy conflict blocks pilot startup.
  A replacement synthetic key refuses old signatures without changing receipt
  identity or replaying delivery. The split-principal Linux probe uses existing
  test UIDs: Public Web cannot open the broker's key or inbox, and the socket
  refuses the wrong UID even within the authorized group. Final isolated
  snapshot `9e78c49f454b…`: 260 passed; the two privileged-only cases skipped
  in that run both passed separately with the disposable Linux root driver.
  This is loopback acceptance only; no external listener, installed service
  or device change. On owner request, committed and pushed only the CAP12
  pilot and its scoped plan as `f56e72f53c6e…`; verified `origin/main` at that
  commit. CI `42159045386` was in progress at handoff. No tag, release or
  deployment. Proposed next: clean-install acceptance of published `v0.3.8`
  on a spare Zero W card, keeping the working card intact. Real key
  provisioning, service units, worker supervision and public exposure
  remain separate CAP12 deployment scope.

- **Zero W Crypto post-recovery access deadlock, 2026-11-05 — diagnosed.**
  Owner reported no observed LCD/output during failed first activation and
  explicitly completed UI recovery. Core journal confirms recovery HTTP200;
  later consent preview/authority and activation requests returned409, connector
  settings returned403. No new application service start was recorded. Read-only
  DB shows exact Crypto0.7.0 installation disabled, active_version NULL,
  review_required, no active.json, no rollback directories. The actual installed
  Core `_package_pin` refused this state; read-only probes confirmed all four
  accepted sealed registration markers absent. Thus the recovered first-ever
  activation has neither an active version nor registered inert provenance, so
  access preview cannot prepare a review and normal activation requires one.
  This is a product lifecycle/recovery deadlock, not proof of a missing user
  permission or a failed ARMv6 compiler. Configuration has three existing keys;
  no application permission grants, connector bindings or secret-reference rows
  and no files in its data directory at inspection; do not expose values.
  Uninstall UI path is documented to preserve data/uploaded package but removes
  the installation/configuration and associated app grants; not performed and
  no assumption it will meet 10s helper deadline on Zero. No manual metadata,
  security bypass, grants, device action or reactivation performed. Owner-facing
  409 says exact package access required; 403 connector settings is separate and
  unproven. Current r6 remains active. Any generic recovery-provenance repair is
  an auth/lifecycle change and needs explicit scope, denial/revocation/isolation
  tests and recovery acceptance; do not fabricate sealed registration or mutate
  the DB. Ask owner before removing the existing application/configuration.

- **Zero W Crypto slow-start correction, 2026-11-05 — owner recovery pending.**
  Following the owner's successful upload and failed activation, non-activating
  `--component-info` as 3mm-app/PrivateNetwork took 33.483s. A separate fake
  instance using exact Crypto0.7.0 ZIP, disposable data/key, no platform socket,
  PrivateNetwork/PrivateDevices and no real Core/hardware access exposed its
  socket at 34s and returned signed health `ready`; fake process then stopped.
  Real package's default health deadline is 30s. This demonstrates a slow-start
  cause and a healthy isolated start, not a successful real activation or proof
  of no external effects from the original attempt.
  Experimental local r6 archive SHA 4f86981d144c9143446ef13b2bd207bb26e0861a06b36c1c48fae2767dcc2aa8
  adds a shared startup budget: on ARMv6 at least 120s, elsewhere unchanged;
  both activation and its Core helper callers use coordinated budgets, retaining
  health/denial/no-replay behavior. On Zero four focused tests passed (real ZIP
  metadata, slow-ready, denial and synchronized caller budgets), plus four
  original v0.3.7 activation/deadline/failure tests passed (15 deselected;
  one unrelated pytest-asyncio marker warning). Exact source/archive diffs checked.
  Applied r6 via standard immutable installer/backup, success; current r6,
  previous r4, Core/Agent ready HTTP200 and Runtime active. Real Crypto remains
  recovery_required/disabled and its service inactive; no permission approval,
  retry, recovery, output, reset or tracked product change by assistant. Owner
  was asked to review any external effects then explicitly use existing UI
  Recover application once and report the result, without reactivating yet.
  UI recovery confirms an operator-reviewed outcome and only reconciles to a
  verified stopped state; no automatic confirmation. If result is uncertain,
  refresh status; do not repeat recovery/activation. The 90s frontend command-
  rebinding request limit was not modified and can still be insufficient on slow
  ARMv6 for that later separate operation. No end-to-end real activation or
  physical LCD success claimed. Device artifacts are experimental/local only.

- **Zero W Crypto activation failure, 2026-11-05 — diagnosis, no replay.**
  Owner screenshot confirms Crypto0.7.0 upload succeeded on experimental r4,
  then activation failed and UI shows Recovery Required. Helper journal at
  09:19 shows signed health transport could not find the application socket;
  health deadline expired and helper reported previous version restored. Unit
  3mm-application-extension@46e92c9bdffd26e204800468 started 09:18:06 and
  stopped 09:18:59, no app exception/OOM in inspected journal. Read-only DB:
  status recovery_required, enabled false, error outcome unconfirmed; no
  active.json or rollback directory, stale run/service.sock exists and service
  is stopped. No conclusion about hardware effects from socket or status alone.
  Crypto package omits startup_timeout_seconds; protocol default is 30s. A
  separate non-activating same-host `--component-info` run as 3mm-app under
  PrivateNetwork/CPUQuota measured 33.483s and passed; host import alone can
  exceed the declared health budget. This supports slow-start as likely, not a
  proof that longer time alone makes the full service healthy. Core and Agent
  remain active; no user access/grants, recovery, re-upload, application start or
  output action. The lifecycle explicitly requires reviewed operator recovery;
  do not replay activation, erase retained state or treat stale socket as live.
  Any ARMv6 timing fix must coordinate the actual health wait, Core-to-helper
  deadline and command-rebinding/other consumers; preserve health, deadline and
  no-replay guards. Reconcile to verified stopped state through existing UI only
  with owner review, then perform a distinct explicit activation acceptance.

- **Zero W ARMv6 Crypto compiler trial, 2026-11-05 — installed, owner upload
  pending.** Owner requested the trial directly on Zero. Installed Go 1.24 there
  and built esbuild 0.25.12 locally with GOARM=6, single-worker/low-priority;
  resulting executable SHA 7a3c7be6d75f14d9eeb48a0b815d70ca5f5d6935c3e4022bba6290b269118c2a
  reports 0.25.12. Downloaded Rollup wasm-node 4.65.1 directly to Zero, npm
  SHA-512 verified, tar SHA 8fd2e64dfeaa6334a683ce198e4b6487df44c63f02f3b7843339300b3e5f459a.
  Exact Crypto0.7.0 ZIP SHA 6c919b56f1e1e4316c5865fa0d0d04625594625ea914fc686da7013d2a082891;
  actual isolated UI build passed in 92.894s, real Core compiler under 3mm UID
  using isolated toolchain passed in 93.64s. First experimental r3 deployment
  timed out at setup readiness during slow Core cold start; normal rollback
  restored r2, fenced recovered authority (applications0/connectors0/devices1),
  and eventually Core/Agent readiness and authority exchanges returned 200.
  Experimental r4 archive SHA 4901c140f23b88a195bac14d5608ed031f96043c99d7edbdf702a131281b2d94
  retains exact verified tool bytes, sets ARMv6 compiler timeout300s and increases
  ARMv6 activation/installer readiness waits without bypassing health checks.
  Installed via immutable installer with backup, host network preserved; r4 unit
  success, `/opt/3mm/current` r4, `/opt/3mm/previous` r2. Core/Agent ready200,
  Core/Agent/Runtime active; swap73 MiB and available174 MiB in post-check.
  Actual installed Core `compile_ui_package` under 3mm UID, normal installed
  compiler and default timeout300, passed same ZIP in 123.25s into an isolated
  artifact root; this is not an HTTP upload/activation or physical display test.
  Owner asked to retry ZIP once via UI and allow 3–5min; no auto-install, grants,
  commands or display output by assistant. Rollback authority fencing can require
  owner review of access: do not silently regrant. Archives, scripts and evidence
  on Zero in `~/3mm-zero-hub-trial/compiler-test`; this is an experimental local
  deployment, not a published release or general ARMv6 support. No tracked code
  changes, commits, tags or pushes. Future updates must carry the toolchain rather
  than assume standard published ARMv6 support.

- **CAP10 — bounded public form, 2026-11-05.** Owner approved the first
  anonymous form slice locally. One explicitly declared literal POST route on
  the separate Public Web listener, off by default; exact Host/Origin, bounded
  form fields and admission, no forwarded credentials or platform resources.
  Exact reviewed package checked before dispatch and before confirming the
  response. The reference `/demo-request` stores only a preset choice and an
  idempotency key in its own SQLite; no Core DB migration or automatic replay.
  Reproducible local ZIP `.runtime/cap10/public-form-reference-1.0.0.zip`, SHA-256
  `5241bf7299ad2b1624427c019a5c36b1a69cded6da942c2082ac3ad37660afcb`.
  [Contract](PUBLIC_WEB_EXTENSION_PLAN.md#cap10--bounded-anonymous-form) and
  [reference build and checks](../modules/public-form-reference/README.md).
  Verified Linux-native snapshot `0314f2e7b52d…`: 317 targeted contract,
  consent, form, packaging and release-builder tests passed; 29 existing
  Public Web process checks passed, 1 separate-OS-principal test skipped.
  The form test uses actual HTTP, Unix socket handoff, signed packaged host and
  disposable SQLite, including no grant, duplicate, cap and in-flight revoke.
  Direct execution from the Windows-mounted source hit old fixture startup
  deadlines; the same source passed on the native Linux disk. XML evidence is
  saved under `.runtime/cap10/` as `checks-linux.xml` and
  `public-web-regression-linux.xml`.
  Owner requested a local browser trial: the exact ZIP on a temporary loopback
  listener refused before lab approval, served the form after approval, and
  returned 404 for the admin API path. One browser submission returned
  `Form received.` and the disposable database contained exactly one record.
  Owner then completed the browser trial; the disposable database reported
  two records total. The local form slice passed acceptance. The temporary
  listener auto-stops after 30 min.
  Follow-up lifecycle acceptance: real Core upload/activation/consent/disable/
  reactivation/uninstall routes, real signed host and Public Web on loopback.
  Only privileged helper IPC and systemd were doubled. Upload alone left no
  route, unapproved requests did not write, a non-admin could not upload or
  review, and disable/uninstall hid the route. Reactivation of the same package
  kept the original submission without duplicating it; uninstall removed the
  runtime and transport key while preserving SQLite. CAP10 HTTP/form suite:
  35 passed, no skips; `.runtime/cap10/lifecycle-linux-f0da6d1a6b9045c5ad6a9204c68d0cf7.xml`.
  Test and documentation changes only in this follow-up; the demo ZIP is unchanged.
  No device changes, public exposure, live grants, commit, push, version or release.

- **CAP10 — opt-in guest draft, accepted 2026-11-05.** Added a 15-minute anonymous guest session
  scoped to the exact reviewed package, installation, authority epoch, form and
  origin. The browser cookie stays at the trusted edge/Core boundary; the SDK
  receives only the guest ID and expiry. The example saves one draft per guest
  in its own SQLite database. Expired, replaced or revoked sessions cannot save;
  a different browser session cannot read the draft. Existing anonymous forms
  and their reference ZIP are unchanged. Guest mode requires explicit
  `--guest-forms` and `--form-origin` on the separate Public Web listener.
  Built `.runtime/cap10/public-guest-reference-1.0.0.zip`, SHA-256
  `abf954f67f5a51c40178e2ce1d8a3049e2dfb1a6996e4cc7733302315d005a60`.
  Linux: 131 targeted and 66 regression/packaging checks passed, no skips;
  two independent HTTP cookie jars verified guest isolation. Evidence:
  `.runtime/cap10/guest-0779af5afc26464195fcc28d92c9ea66.xml` and
  `/tmp/3mm-cap10-bidt1m7_/results.xml`. Browser acceptance on loopback with the
  exact ZIP: the in-app browser saved `Morning` and showed it on reopening;
  a separate Chrome incognito session at the same URL showed `No saved draft`.
  Browser control stopped before testing an expired form submission. The owner
  accepted the bounded slice using the passing HTTP expiry regression for this
  case; no expired browser submission was exercised.
  No device install, public ingress, live grants, Git publication or release.
  Customer accounts and a deployed HTTPS ingress remain separate work.

- **CAP21 Git integration, 2026-11-05.** Owner closed the bounded authoring
  profile and requested commit/push. Exact 26-file scope (including two
  selected documentation hunks) committed and pushed to main as
  `d205b9cc7e1919eab17a5c8871b5029125e47700`. Previous exact-base CI
  41911873152 completed successfully; new push CI 41974902960 is in progress
  for this commit. Reused the local evidence below for unchanged sources;
  staged and committed blob identities and whitespace were verified. No tag,
  release, version or device change. The mixed working diary and independent
  plan/check-policy/dev-lab edits remain local. Suggested next bounded work:
  CAP10 one declared, bounded public form on the separate Public Web surface,
  with schema/abuse/replay checks and app-owned data. Design only at this point;
  no authorization for implementation, public exposure or live deployment.

- **CAP21 → CAP03 local package review, 2026-11-05.** Added
  `tools.extension_dev compare OLD_ZIP NEW_ZIP [--json]` after the authoring
  workflow. Both bounded archives use the same current Core package validator.
  The result identifies exact ZIP/wheel hashes and data revisions, lists changed
  declaration fields and named permission/operation/resource differences, and
  does not emit configuration values or schema contents. Unrelated apps,
  invalid packages and same-version/different-byte replacements refuse. This
  static comparison neither runs code/migrations nor decides upgrade order,
  live rights or installability. Windows targeted reviewer and CLI checks:
  24 passed; final 8 reviewer cases rerun after wording-only change. Real CLI
  on two synthetic 1.0.0/1.1.0 ZIPs showed permission replacement, operation
  checks, resource TTL and data revision change. Evidence under `.runtime/cap21/`
  `package-compare-tests-final.xml` and `package-compare-recheck.xml`. No Core,
  SDK, version, device, or Git changes; independent Zero W work is separate.

- **Zero W Crypto UI compiler diagnosis, 2026-11-05.** Owner completed Hub
  setup, enabled I2C and rebooted; Crypto Monitor 0.7.0 upload displayed
  `compiled UI build failed: compiler failed`. Read-only live observation:
  experimental-037-armv6-r2 selected, Core/Agent/Runtime active; 426 MiB total,
  ~122–140 MiB available during checks, no swap in use. On actual ARMv6 Zero,
  isolated `require('rollup')`, Vite import and installed esbuild `--version`
  all terminate with illegal instruction / exit132. Rollup native ELF attributes
  explicitly specify ARMv7-A / VFPv3-D16; package installation succeeded but the
  installed compiler binaries cannot run on this CPU. Core falls back to generic
  `compiler failed` when a failed compiler has empty stdout/stderr. This directly
  explains the observed message; no claim that fixing only Rollup is sufficient,
  since esbuild also fails. User-supplied operation-records (6) has one session
  header and zero events, so adds no failure details. No application re-upload,
  permission changes, device modification or product source change during this
  diagnosis. Next scoped fix would need ARMv6-compatible Rollup AND esbuild and
  an actual Crypto UI compile/install check under Zero's RAM/time limits.

- **CAP21 authoring profile v1 — local completion, 2026-11-04.** Owner requested
  finishing CAP21 locally and deferring all Git work. Complete current profile is
  Manifest v2/public SDK1.3/Python service/own SQLite/Vue UI:
  init → catalog → preview → generate-client → check, with explicit previous-ZIP
  upgrade verification. No Core/SDK/version change, staged changes, commit, push,
  tag, release, deployment, installed DB, grant or device action in this turn.
  Preserve independent dev-lab/simplification/M21/Zero W work and historical notes.
  Generated UI methods derive from actual validated operations, schemas and
  idempotency; internal-only operations are excluded, commands need the original
  caller key and invoke exactly once. No retry, authority claim or runtime-schema
  replacement. Unsupported type constructs refuse instead of widening to any.
  Optional development.json generated_client/type_tests/upgrade_fixture are used
  by the common runner: stale/missing generated source refuses before execution;
  strict positive/expected-negative type cases execute with current host types.
  Scaffold regenerates the copied client for each new module identity. Starter
  Notes.vue actually uses it; standalone fixture verifies note/actor receipts.
  Explicit client replacement retains displaced source in project-local ignored
  .runtime/client-recovery and publishes exclusively; concurrent edits are not
  overwritten. A brief absent target and recoverable backup are documented.
  --previous-archive pins actual old/new ZIP+wheel/fixture hashes and runs old
  seed and candidate verification in separate -I processes with disposable data.
  Checks same identity/newer version, revision prefix, new-migration interruption,
  immutable domain verification, integrity and reopen. Fixture-specific, not
  arbitrary historic-data proof, installed config/provider proof or hostile-code
  isolation; same-schema rollback is explicitly not_applicable. No previous ZIP
  reports not_requested. Failure gates exclusive ZIP publication and retains logs.
  Current source hashes: client15a2bfd1c6a7..., upgrade918927d875ee...,
  controller119190190cb5..., CLIccafb2592c05.... Linux targeted tooling184 passed,
  upgrade23 passed, check/release/frontend-access contracts65 passed, actual
  Core/SDK permission/revoke/provider-loss/own-data integration1 passed, all with
  zero skips. XML evidence under .runtime/cap21/: finish-tools-linux.xml,
  upgrade-final-linux.xml, finish-gates-linux.xml, core-final-native-linux.xml.
  That Core integration doubles external service launch/response transport;
  compiler is exact copied current script with existing Linux Vite6.4.3 deps.
  Windows controller100 passed3 symlink skips replaced by POSIX coverage; Windows
  Git Bash timeout replaced by65-case Linux pass. No test weakening. Windows real
  starter UI19/type checks passed; generic real TS/one-dispatch2 prior unchanged
  render checks reused; filesystem/race fixes have separate passing evidence.
  Actual generated org.example.cap21-upgrade-trial1.0.0→1.1.0 common workflow
  passed each Python6/UI19/strict types/real UI compiler. Old ZIP58f521aa519e...,
  candidate4e9120498f6a..., candidate source1ac3a9b90d3e...; schema0001→0002,
  old note/original actor receipt/new column retained, reopen/integrity and new
  migration rollback probe passed. Reports: .runtime/cap21/finish/trial-v1-3.report.json
  and trial-v2.report.json; these are local synthetic artifacts, not install requests.
  Integration caught a repository-relative CI tsconfig copied into new projects;
  moved it to frontend/tsconfig.cap21.json, outside template. CI frontend gates
  now run actual starter/client types+UI with existing dependencies; Release also
  opts into real generator TS cases. Workflow files are only prepared locally,
  not remotely executed; all prior release gates remain. Guides/check policy/CAP21
  plan updated. Native/scoped-relational adapters and universal capability
  templates remain explicitly outside this completed authoring profile. Next:
  owner review, then only explicitly requested Git integration/release gates.

- **CAP21 source-derived authoring catalog, 2026-11-04 — local ready.** Owner
  approved the migration commit/push and continued catalog work. Added local
  `python -m tools.extension_dev catalog [PROJECT]`: actual public model schemas,
  model-validator references (not an exhaustive duplicate policy), SDK/UI error
  literals, transport and migration limits, raw source-file hashes. A project
  freezes source, builds its exact wheel/ZIP and runs actual package semantics
  against the explicit current Core version; returns full declarations, lifecycle,
  permissions/resources and exact identities. No app import, tests, migrations,
  compiler, credentials, network, grants or installation. Scoped relational is
  explicitly outside this migration-check profile; other module types refuse.
  Inspection is not a check pass, native-code isolation or installed readiness.
  New Windows CLI/preview/remote-command boundary run28 passed; helper19 passed,
  then the final nonapplication refusal regression1 passed. Linux combined
  catalog/CLI/scaffold/preview/remote-command run67 passed/0 skips before that
  final refusal guard; final helper20 passed/0 skips replaces its19-case evidence,
  unchanged48 consumer cases reused. Evidence: .runtime/cap21/catalog-final-linux.xml
  and catalog-helper-final-linux.xml. Helper SHA317e64e14f91..., CLI SHAa117d2115907....
  Actual global/project CLI inspection and nonzero JSON refusal checked. Starter
  sourcebe01a408... changed only in its guide; actual packageb40dd42f... unchanged,
  so prior service/UI/compiler/migration evidence reused; no main frontend build.
  Guide/check policy/generated-project guide updated. Catalog remains local,
  uncommitted/unpushed. No tag, version, release or device action. Next bounded
  candidate: typed operation client generation; real v1-to-v2 upgrade later.

- **CAP21 packaged migration checks, 2026-11-04.** The prior authoring commit
  9290426db8e8b09551162405bc2d1eedb340b1b2 passed full CI41903345802. Owner
  approved a separate migration-check commit/push:2a031ce017878f1d5a65bbb7f2f776c60d72d088
  is pushed and exact remote ref verified. CI41911873152: selection/frontend/tooling
  passed; Python remains in progress. Continued bounded catalog work locally.
  check now tests the exact packaged wheel via public SDK ApplicationStorage
  on disposable SQLite before artifact publication: clean/final-target/stable
  revision plan, current-prefix upgrade, reopen, integrity/FK and per-revision
  rollback after injected failure. No service factory, installed data or authority
  changes. Scoped relational is explicitly unsupported by this local profile.
  Limits:32 revisions,16MiB per database,60-second direct worker; not hostile-code
  isolation or historical business-data migration certification. Linux five-suite
  run111 passed before final coherence fix; final helper21 passed/0 skipped
  replaces helper evidence; unchanged consumers reused. Final common workflow for
  source8cc2e256... passed Python6/UI15/types/real compiler plus migration checks;
  packageb40dd42f... unchanged. No version/tag/release/deployment. Preserve unrelated
  dev-lab, simplification, device experiments and mixed historical notes.

- **Experimental Zero W Hub feasibility, 2026-11-04 — setup pending.** Owner
  requested direct installation on a newly prepared Zero W system; new SSH key
  was owner-confirmed and old Node card preserved. Official 0.3.7 ARMv7 archive
  SHA a54bc696d402c8c0084832680b421c7f2e8c0cde53020a42e8b357d36c074000
  matched GitHub metadata. Locally derived experimental full ARMv6 r2 archive
  SHA 80d5e06f0e6f443830a1ae51e52f26c8508153ce91037eded8ff7c264b3cc4ea;
  explicit experimental metadata, preflight architecture addition, and only
  ARMv6 application-host component-info timeout 15->120s differ from original.
  Other archive files verified unchanged. First attempt needed gcc/Python headers
  for psutil; second timed out on host component-info after 15s; both installers
  rolled back Core and inactive services. Added build-essential/python3-dev,
  then r2 passed actual package install, psutil native build, npm package install,
  application-host preparation and DB migration; installer finished successfully
  with host networking preserved. `/opt/3mm/current` points to
  experimental-037-armv6-r2. Setup service is ready; LAN `/setup` returned HTTP200.
  Core/Agent are inactive before role provisioning, not claimed healthy. Owner
  asked to complete Hub setup at 192.168.1.81:8895/setup; next verify real Core
  health, RAM and crypto-monitor on that system. No reboot, full runtime/UI
  compiler execution, crypto-monitor installation, release support or benchmark
  is claimed. Experimental script/archive are ignored in `.runtime/zero-hub-experiment`.

- **CAP21 pushed / migration verification follow-up, 2026-11-04.** User explicitly
  requested commit/push and continued work while CI runs. Scoped28-file commit
  9290426db8e8b09551162405bc2d1eedb340b1b2 is pushed to remote main, exact ref verified.
  Included only CAP21 source/tests/guides and selected check-policy/current-state
  hunks; independent dev-lab/simplification and historical diary remain local.
  Previous installer99de0b7 CI41890096828 verified success. New CI41903345802 has
  selection/tooling/frontend successful; Python still in progress at handoff.
  No tag/release/version or device action. Fresh-checkout audit caught one missing
  .runtime parent prerequisite in a real nested-pytest test; fixed and that Linux
  regression passed before committing. Existing unchanged89-pass authoring and
  Python6/UI15/types/real-compiler/authority-denial evidence reused.
  Continued one bounded local CAP21 result: check now runs the exact packaged
  migration factory using public SDK ApplicationStorage on disposable SQLite,
  before project tests/artifact publication. Clean creation, final-target and
  stable revision sequence, each prefix upgrade, reopen without changed logical
  state/history, integrity/FK and injected per-revision rollback are checked.
  Premature commit/executescript partial persistence fails. No service factory,
  Core/SDK/runtime/auth changes or installed database access. Explicit local
  SQLite profile only; scoped relational refuses.32 revisions,16MiB per database,
  60-second direct worker; not hostile/process-tree isolation or historical-data
  upgrade certification. Reports contain counts/flags, not database row contents.
  Windows helper20 passed, controller/CLI/scaffold88 passed3 environment symlink
  skips. Linux five suites111 passed0 skips before final plan-coherence fix;
  final helper21 passed0 skips replaces its pre-fix evidence, unchanged consumers
  reused. Final actual common command passed Python6/UI15/strict types/compiler
  and migration clean/reopen/rollback for source8cc2e256...; ZIPb40dd42f... unchanged.
  Evidence: .runtime/cap21/migration-authoring-linux.xml,
  migration-plan-coherence-linux.xml, migrations-final-2.report.json. No broad
  Core rerun for this developer-tool-only follow-up; previous real authority
  boundary evidence reused unchanged. This follow-up and its guide remain
  committed/pushed as2a031ce after the owner's approval; see current CI note above. Existing
  installed starter1.0.0 and its immutable artifact are not replaced by local ZIPs.

- **CAP21 local authoring cycle accepted, 2026-11-04.** Official source-only
  application-starter demonstrates UI, own SQLite data/revisions/receipts and an
  optional observed resource, using public SDK/UI only. Developer commands init,
  preview, check and schemas create a distinct project, simulate six UI states,
  run executed denial/UI/type/compiler checks and report actual validated
  declarations before exclusive artifact publication. Existing local dependencies
  only; no credentials, install, grants, physical output or automatic retry.
  Linux authoring/controller/scaffold/preview/CLI89 passed/0 skipped; Windows
  starter and separately generated application each Python6/UI15 plus strict types
  and real compiler passed. Real Core/SDK permission/revoke/provider-loss/own-data
  integration passed; external process transport doubled, no device acceptance.
  Owner confirmed installed note persistence/edit denial and accepted local preview.
  Source-only developer templates are not installed runtime modules. Pure-Python
  profile and mock are not hostile-code isolation or universal conformance.
  User now requests scoped CAP21 commit/push and continued local development while
  CI runs. Reuse unchanged evidence, retain full CI/release gates; no tag, version
  bump, release or device deployment requested. Preserve independent dev-lab,
  simplification and mixed historical notes outside this commit.

- **CAP21 complete local authoring cycle, 2026-11-04 — ready for owner review.**
  Owner requested a more finished CAP21, with no further publication/device action.
  Added `tools.extension_dev init` (new identity/route/source, real package rules,
  atomic no-clobber destination), `preview` (explicit loopback Vite, project mock,
  EN/BG/light/dark/narrow UI) and `schemas` (existing public structural catalog).
  Preview demonstrates six states including opened-editor revocation, missing
  resource approval/provider, revision conflict and completed-but-unconfirmed save;
  it is disposable memory, not a Core/permission/provider/physical proof. No token
  or Core URL, automatic install, grants or replay. Check reports now include actual
  validated operations/permissions/idempotency/resource/storage/compatibility details;
  exact failure phases and clean nonempty executed JUnit are required. Evidence is
  prepared before exclusive ZIP publication; late output failures retain truthful
  published/unconfirmed identity, never overwrite/delete another output. Existing
  dependencies only; Windows/Linux init and hard-link-supporting output filesystem.
  Real nested-snapshot regression exposed inherited repository pytest root; fixed
  explicit snapshot root, not application tests or authority checks. Final Linux
  controller/scaffold/preview/CLI89 passed/0 skipped (existing WSL3.14.4), evidence
  .runtime/cap21/authoring-linux-final.xml. Windows preview/CLI22 passed. Actual common
  workflow passed separately for official starter and CLI-generated org.example.owner-note:
  each Python6/UI15, strict Vue types including mock and actual package UI compiler,
  Windows3.13.15/Node24.19/Vite6.4.3. Official checked source454d2e67..., unchanged
  ZIPb40dd42f...; generated ZIPc80da37e... and reports under .runtime/cap21. Local
  artifacts only, not replacements for installed immutable starter1.0.0. Reused
  unchanged service/contracts/Core/SDK real authority-denial integration evidence;
  no new live acceptance. Browser review confirmed light EN, dark BG/narrow390,
  draft retention on revocation and editable own data on provider loss, no console
  errors; owned temporary tab/server stopped. Guide and check policy updated.
  Acceptance: a separate new source project can be created, simulated, checked and
  reviewed before optional manual installation. Native dependencies, hostile-code
  isolation and universal capability conformance remain outside this pure-Python
  profile. No Core/SDK/package version, commit, push, tag, release or deployment;
  independent simplification/dev-lab/M21 work preserved. Next: owner previews this
  local cycle; integration/versioning only when explicitly requested.

- **CAP21 bounded acceptance closed, 2026-11-04.** Owner confirms /starter-note
  edits/saves correctly after restoring note_write, while Command resources
  shows no currently compatible/available GPIO target. The disabled control
  was the separate resource-rebinding dialog, not the note editor. Own data
  remains usable without that optional resource; no additional application,
  provider, deployment, upload or permission change performed by the assistant.
  Together with the accepted common command, actual Core/SDK software denial
  checks and owner install/persistence/edit-revocation trial, this closes the
  agreed minimal CAP21 authoring slice. Do not claim a live healthy-provider
  disconnection test: no such provider or exact observed-resource state was
  established. No new tests for this evidence-only handoff. Retain local CAP21
  sources and wording fix for the next expressly requested integration, with
  no wording-only version, commit/push, release or new test request now.

- **Fresh-SD installer correction / accepted trials, 2026-11-04.** Owner's
  explicit Stable0.3.7 install and restore from a file on a new card succeeded.
  LCD start then failed because I2C was disabled on the new host; owner enabled
  it through Settings and confirms the display now works. Close those owner
  trials as successful, not as an unresolved Core409 regression. Export
  recent-http-failures(7) contains prior host_value_error/command-result409;
  owner supplied the missing-host-interface cause and successful recovery.
  No new LCD/restore fix, automatic host-interface restoration or device command.
  The plain public installer previously defaulted to Beta and chose beta.57.
  Corrected install.sh only: Stable/latest default, inferred exact-tag channel
  unless explicit, no fallback or weakened manifest/size/SHA checks; fresh
  default host networking preserves current LAN, -ap/--ap explicitly selects
  managed initial AP setup. Saved backend/role/data survive upgrades; -ap is
  not a reset or forced AP on a provisioned device. Worker receives the resolved
  backend even when installing an older immutable release. README and current
  Raspberry/Node guides updated. Final bounded Linux checks154 passed/0 skipped
  in13.85s on existing WSL3.14.4: real shell/Python selection and immutable
  consumer sections with disposable files/command doubles; no APT/systemd/
  network or clean-card acceptance of these new defaults. Evidence:
  .runtime/bootstrap-defaults/checks-final.xml. No new release/version needed.
  Committed/pushed installer/docs-only99de0b7e4c9a43890ae8c110e2920513735eed44;
  remote main verified exact. Excluded all CAP21/dev-lab/simplification/M21
  and this mixed diary. Owner then clarified no further publication/deployment
  until the next release and chose to keep this already-pushed commit. No tag,
  release, live reset/restore/deployment or further upload here; do not repeat.
  Core0.3.7 release run41868681396 is now confirmed completed/success for
  5f91cb43...; published non-draft stable assets include all full architectures
  and Node, manifests and checksums. CAP03 remote Node acceptance stays deferred.
  CAP21 minimal profile: local common command plus owner install/persistence/
  edit-revocation checks accepted. Manual selected-provider outage not performed;
  software Core/SDK coverage already passed. Owner resumes CAP21 selected-resource
  review: current Command resources screenshot shows configured device currently
  unavailable/incompatible with gpio.digital.control1.0/set_output, not the LCD
  contract. No compatible live provider or exact cause established by screenshot.
  Owner now confirms own-note editing works independently in this state. Do not
  install another provider, stop LCD or treat unconfigured/unapproved access as a
  proven provider outage. Wording correction stays for a future combined example
  package, per owner; no wording-only1.0.1 and no source deletion.

- **CAP21 owner denial acceptance / starter feedback, 2026-11-04.** Owner's
  common command passed with canonical ZIPc3e77d22..., then manual install,
  note persistence and removal of only human note_write correctly blocked a
  new save while preserving the previous note. After reload the editor is
  correctly read-only through retained note_read. Owner found the starter's
  catch incorrectly called this explicit access refusal an unconfirmed save.
  Fixed only the example UI: public ApplicationHostError/access_denied gives
  clear EN/BG editing-access refusal, retains the draft and turns editing off;
  all other failures retain the unknown-outcome fence. Explicit permission/
  saved-note reload can restore editing, never replay a save. Added EN/BG
  stale-permission and typed-unconfirmed regressions; guide updated. Final
  common pipeline passed Python6/UI8, strict types and actual compiler on
  Windows3.13.15/Node24.19; report note-denial-local-2 under .runtime/cap21.
  Initial limited execution could not read the Windows temporary directory;
  normal-access rerun passed, no product workaround. Core/SDK/service and
  existing installed ZIP are unchanged; prior real Core permission/data
  evidence reused for unchanged behavior. Versions unchanged, local output
  is a check artifact only, not an immutable replacement for installed1.0.0.
  No commit, deploy, approval change or live device action. Owner declined a
  wording-only version; retain for a future combined example package. The
  bounded note/persistence/edit-permission owner trial is closed as accepted;
  no manual provider-outage acceptance is claimed. Independent source preserved.

- **CAP21 minimal authoring cycle, 2026-11-04 — implemented locally.** Owner
  requested one official UI/own-data/selectable-resource example and a common
  check/build command with denial/revocation/unavailable-provider scenarios.
  New source-only modules/application-starter is a shared demonstration note:
  public SDK1.3, own SQLite migration/revision/actor-scoped receipts, public
  themed EN/BG UI, optional command:resource binding configured through existing
  administration. It observes availability only; no command-submit operation,
  hardware writes, polling, auto-grants or app-specific Core runtime branches.
  Explicit saves use current human permission and optimistic revision; lost
  acknowledgement retains the draft and requires an explicit saved-state read.
  tools.extension_dev check now freezes a pure-Python project, builds a canonical
  wheel/ZIP, uses actual package semantics, checks executed/no-skip denial cases,
  UI tests/strict vue-tsc and actual install-time compiler, then exclusively
  creates ZIP/report/local log. No downloads, dependency installation, API login,
  upload, activation or deployment. Unknown outcomes are not retried. Human
  summary and --json distinguish local project tests from live conformance.
  Guard tests22 passed/0 skipped, Windows Python3.13.15; actual common workflow
  passed project Python6/UI5 plus strict types/compilation with existing Node24.19,
  Vite6.4.3/plugin5.2.4. UI/service/package inputs unchanged since that real run;
  final controller diagnostics covered by22. Real POSIX packaged-service/Core/
  sealed-consent/signed-Runtime regression1 passed on WSL3.14.4/Node22.22.1:
  human permission denial, resource health loss and grant revocation with own
  data intact and zero DeviceCommand rows. External launch/response transport
  doubled, no actual systemd/device acceptance. Linux compiler used exact current
  script0a46e94a... with isolated cached locked dependencies, not mixed Windows
  node_modules or a changed production compiler. Synthetic browser review passed
  light EN1280 and dark BG390, including provider-unavailable state; temporary
  browser/server closed. Canonical example ZIPc3e77d22... is
  .runtime/cap21/note-verified.zip; reports/XML nearby. Guide in the example README.
  No new framework, Core/SDK version change, commit, push, release or device action.
  Independent simplification/dev-lab/M21 edits preserved; owner continues CAP03
  device review separately. This closes only the agreed minimal CAP21 profile,
  not a universal semantic catalog, dependency/native-wheel builder, hostile-code
  isolation or every capability's conformance. Owner has now repeated the single
  command, installed the example, confirmed note persistence and write denial
  with saved text intact. This bounded trial is closed, with the feedback-only
  correction retained for a future package and no manual provider outage claim.

- **Core0.3.7 release published, 2026-11-04.** Owner explicitly requested release
  after successful CI. Verified run41860057684 completed/success with all four
  jobs successful for exact current remote main5f91cb43ee13f3987a5f03b0d3d2f1ce24b95e0a.
  Only then created/pushed annotated v0.3.7 (tag object89bedb56ef268e97d5572cda1de27e3e2d2328e2);
  remote peeled tag matches that commit. Release run41868681396 completed/
  success; stable v0.3.7 publication/assets confirmed through GitHub. Existing
  full release gates remain unchanged; publication alone is not device acceptance.
  Reused green CI; no new tests/build, source commit, device command or deploy.
  Independent dirty dev-lab/simplification/checks/M21 work is not in the tag.
  Owner subsequently accepted a fresh-card install and portable restore.
  Remote Node acceptance remains deferred; release publication trial is closed.

- **CAP03 / CAP14 release preparation, 2026-11-04.** Owner approved scoped
  commit/push, then green main CI before any tag/release; CAP21 follows closure.
  Committed c79fd00 (provider administration), 402133e (independent component
  updates) and a9bc0b4 (Core0.3.7 + distinct BG1.0.6 and release notes). Pushed
  main at a9bc0b48cf8e511fc3de504448bb2896739da3f1. CI run41853809476 had successful
  selection/frontend/tooling jobs but Python stopped at the obsolete Unix-only
  expectation in test_systemd_templates.py (6485 passed,611 skipped,1 failed).
  Updated only that test to require AF_UNIX/AF_INET plus IPAddressDeny=any and
  IPAddressAllow=localhost; other service isolation assertions remain unchanged.
  Affected systemd templates/component-helper checks33 passed/0 skipped in8.91s
  on existing WSL3.14.4; no production/dependency/version change or new build.
  Evidence: .runtime/release-037/systemd-policy-fix.xml. Committed and pushed
  5f91cb43ee13f3987a5f03b0d3d2f1ce24b95e0a; new CI run41860057684 is in progress.
  No v0.3.7 tag or publication yet. Final release/language/delivery checks121
  passed/0 skipped on existing WSL3.14.4; prior unchanged provider/UI/native/
  denial/rollback evidence reused by exact content. All45 scoped committed blobs
  match .runtime/release-037/review.json. Canonical BG ZIP844942f5... matches the
  already accepted Raspberry package. Existing local Agent/selected-host real
  update/rollback and root/systemd network acceptance remain valid; remote Node
  device acceptance is explicitly deferred. No further device action, hardware
  output, rights change or reset. Mixed working diary, simplification/checks and
  dev-lab edits remain uncommitted and preserved; no M21 changes included.
  Next: verify all applicable CI jobs for exact pushed SHA; only then create
  annotated v0.3.7 and push that tag, retaining full release gates. Do not infer
  publication from a successful push or from targeted local checks.

- **CAP03 / CAP14 trial rollout and local component acceptance, 2026-11-04.**
  Owner approved the next rollout step. Prepared and selected distinct BG1.0.6,
  retaining published1.0.5 bytes. Canonical LF/Linux bundled ZIP SHA844942f5...
  matches the package actually staged and enabled on Raspberry. Core version
  remains0.3.6; this is an unpublished local working-tree rollout, not a release.
  Final immutable Core is local-7aa54654d91f53f30677dc1b; normal installer backup
  exists, Core/Agent/Web/Runtime/helper are active. Core PID61551 stayed unchanged
  during the subsequent component tests. Checked prebuilt frontend is delivered
  byte-for-byte and new component/provider BG messages are available.
  Real acceptance found the helper's Unix-only address-family restriction blocked
  Agent's fixed loopback identity endpoint. Corrected only its network allowance:
  AF_UNIX/AF_INET with IPAddressDeny=any and IPAddressAllow=localhost. A permanent
  opt-in root/systemd regression test passed on Raspberry (three subtests: original
  refusal, local readiness, nonlocal denial); ordinary Windows run skips it,
  not counted as a pass. Added bounded request/component/phase/type/function/line
  failure logging, never exception text, artifact bytes, app responses or keys.
  New affected source checks: language13, helper/unit consumers8, workflow34
  passed/0 skipped. Earlier unchanged UI47/types/build, provider and native-builder
  evidence reused by content; .runtime/component-updates contains exact proofs.
  Actual web-API preparation/update/manual rollback succeeded for selected host
  46e92c9b... (5319e993... ->3e0cc7ba... ->5319e993...) and local Agent
  (dfc8fcad... ->015e76c4... ->dfc8fcad...). Both current builds were deliberately
  returned to the inspected working originals after acceptance. Runtime/default
  host/Child Center host pointers and both application active-metadata hashes
  are unchanged; no app package/data/rights change or Start/Send command.
  An initial host update under the first trial Core3c510961... failed and safely
  restored the old healthy build with no pending transaction; its original cause
  was not retained, so do not claim it conclusively diagnosed or silently retry
  it. A newly prepared exact request under the final Core succeeded; new bounded
  failure locations are available if it recurs. Both initial and final Core
  deployments used normal backup/health/rollback; no device reboot or live restore.
  Anonymous new-control reads correctly return401. No registered remote Node is
  present; known Zero W192.168.1.81 timed out. Remote signed OTA implementation
  is therefore NOT target-device accepted yet; do not enroll/reset/repin a device
  or publish a package implicitly. Next bounded result: owner UI review and a
  reachable enrolled supported Node for explicit remote update acceptance.
  No commit, push, tag or publication. Independent dev-lab/simplification/M21
  source preserved. Evidence: deployment-result.json, postflight.json and exact
  operation receipts in .runtime/component-updates; no credentials/tokens recorded.

- **CAP03 independent component web management, 2026-11-04 — local implementation.**
  Owner requested application hosts and Agent alongside the accepted Runtime
  control, then explicitly included remote Node Agents. System Updates now has
  a selected local Agent/application-instance control and a separate per-Node
  signed OTA control. No default-host publication or update-all action.
  Local preparation uses immutable installed Core sources and the selected
  component's validated native interpreter/vendor; no dependency installation
  into Core or downloads. Exact candidate/build/target confirmation, previous-
  build rollback and explicit interrupted-transaction recovery reuse existing
  component stores and health/rollback paths. Current committed admin revision,
  app incarnation/epoch/package/enablement and Core generation are rechecked;
  APIs are current-admin only and helper observes the kernel Core UID. Status
  opens stores read-only, with no bootstrap directories or application invocation.
  Unknown accepted results retain their identity across remount, bounded status
  reads never replay mutations. Proven pre-acceptance refusal is distinguished
  from uncertain persistence/scheduling; only the former releases the UI fence.
  Local updates preserve Core/Runtime, default/other-host pins, app metadata,
  data and rights. Saved app hardware consent may resume output on reconnect.
  Remote management reuses the existing signed, exact-device ARMv6 Node package
  and installer (Agent plus Node service files, not arbitrary native architectures).
  Catalog checks/download/preparation/install are explicit; no network catalog
  request or update on page load. Latest durable per-device operation is readable;
  only verified installation outcome, never command acceptance, indicates success.
  Existing trust/bootstrap, freshness, revocation, conflicting-command and rollback
  guards remain. Added maintenance-window approval and no-store status responses.
  No schema/auth model/SDK change, version bump, live service action or deployment.
  Final targeted boundary64 passed/0 skipped; helper7 passed/0 skipped, with
  separate actual-systemd acceptance1 skipped (not a pass). Node/catalog/API/
  release-contract groups passed (75 before final no-store change; final affected
  group82 passed/0 skipped). Runtime consumers/helper109 passed/0 skipped reused
  for unchanged Runtime behavior. Native host/Agent/Runtime process, artifact and
  rollback checks80 passed; optional-image and distinct-root-principal2 skipped.
  Initial NTFS fixture startup failure was resolved by running a verified Linux
  source snapshot ace2d4d0...; native checks then passed. Its one required-file
  ordering failure was fixed and the final14 contract cases passed in group82.
  Final real selected-interpreter/vendor preparation and helper13 passed/0 skipped;
  worker/builder disable bytecode writes, preserving existing immutable artifacts.
  Final frontend47 distinct cases passed across six affected suites, reusing
  unaffected cases and rerunning the final local-control12; types/build pass.
  Actual local synthetic UI reviewed EN/light1280 and BG/dark390, including exact
  unchecked confirmations and no horizontal overflow. No live device data used.
  Evidence and preview helpers: .runtime/component-updates; independent CAP14,
  simplification/dev-lab and M21 work preserved. Remaining acceptance: explicitly
  authorized rollout, actual root/systemd boundary and target-device update/
  rollback tests. Changed local dependency locks require separately verified
  component dependency delivery; unsupported Node architectures stay refused.
  EN/BG source labels added without republishing BG1.0.5: a distinct language
  version is required before rollout. No commit, push, tag or release this task.

- **CAP14 admin provider setup, 2026-11-04 — local implementation completed.**
  Owner authorized the proposed bounded result. Devices -> Hardware providers
  now renders an allowlisted template form using existing UiForm/UiField controls:
  installed PCF8574T/HD44780 driver or simulation, display ID, geometry, bus,
  hexadecimal address and backlight polarity. Prepare adds only an immutable
  catalog package; it does not install, approve, enable an interface, reboot,
  grant app rights, scan a bus or send a frame. Existing exact device/package/
  profile review and module lifecycle remain the separate installation step.
  Existing ZIP upload is retained under a collapsed Advanced disclosure.
  The CLI and admin path share a pure protocol package builder with no Agent/
  Core import or I/O. Existing 16x2 package SHA edaaef54... is unchanged. Driver
  geometry remains parameterized, not an application/16-versus20 Core branch.
  Invalid/extra/executable settings, unknown templates and revoked devices are
  refused. Repeat preparation is deterministic; immutable version conflicts are
  refused. Pending installation identities still fence new mutations; no retry,
  silent replacement or new application consent is introduced.
  Linux3.14.4 targeted checks118 passed/0 skipped in48.56s; catalog/upload/
  lifecycle/removal/authority/transport consumers114 passed/0 skipped in43.64s;
  final immutable-conflict case1 passed in16.30s. Independent suites total233
  cases, not repeated attempts. XML in .runtime/provider-setup. Final Windows
  frontend targeted cases36 passed, Extensions/inventory54 passed; type-check
  and production build passed after final client changes. Actual components
  visually reviewed using synthetic local data: light/dark, EN/BG, 1280px and
  390px; no horizontal overflow at390px, explicit confirmation remains unchecked.
  Preview: .runtime/provider-setup/preview-dark-bg.png. EN/BG source labels and
  provider README updated; no language/Core version bump or ZIP publication.
  Before a rollout, new BG content needs a distinct bundled language version,
  not replacement bytes under published1.0.5. No deployment, hardware acceptance,
  live installation/disable/removal, rights change, commit or push this task.
  Independent simplification/dev-lab changes are preserved. Next: owner review
  and an explicitly authorized test rollout; installed Agent contract is unchanged.
  Separately, release run41804579423 completed/success. GitHub confirms published
  v0.3.6, draft=false, published_at2026-11-04T09:41:39Z, seven assets. That release
  is commit3867dee and does NOT contain this later local provider-setup work.

- **Core0.3.6 release start / plan review, 2026-11-04.**
  Owner authorized publication after successful main CI and reports Crypto Monitor
  and Child Center installed and working. Verified all four CI jobs in
  run41799731475 completed/success for exact main commit
  3867deeabc2b0075265cdefa427c0722d6eb2838. Only then created and pushed annotated
  v0.3.6 (tag object efe72c44b02d3359aa69f43b154ef5562a212ff4); remote peeled
  tag matches that commit. Release run41804579423 is in_progress; publication
  is NOT yet confirmed. Normal frontend/Python/deployment/artifact gates remain
  enabled. No new source changes, tests, device commands or second deployment.
  Reviewed CORE_SIMPLIFICATION_PLAN against newer acceptance records: old
  local-only/pending-deployment notes do not invalidate later CAP03 Runtime web,
  CAP09 UI, CAP13 local query or CAP14 I2C/LCD acceptance. The two real consumers
  validate their supported profiles, not every CAP or hostile-code isolation.
  Main remaining directions: easier independent component lifecycle in the admin
  UI (CAP03); supported hardware-provider configuration without locally generated
  ZIPs (CAP14); composition effects/events beyond local read queries (CAP13);
  public forms/session ingress and inbound webhooks (CAP10/12); explicit device
  budgets and a consistent public SDK authoring/conformance workflow (CAP20/21).
  CAP11 target-device acceptance and additional CAP09 helpers remain scoped to
  actual consumers; CAP17/18 notifications/search/documents are optional later.
  Proposed next bounded result: configure an existing supported display-provider
  profile through administration using the existing review/install lifecycle,
  keeping host-interface setup, app rights and physical writes separate. This is
  a recommendation, NOT authorization to implement. Independent plan/dev-lab
  changes and this mixed log remain unstaged; no new commit/push requested.

- **Core0.3.6 commit/push, 2026-11-04 — completed.**
  Owner explicitly authorized commit and push. Commit3867deeabc2b0075265cdefa427c0722d6eb2838
  contains exactly27 reviewed paths (1574 insertions/28 deletions); staged Git
  blobs matched the frozen review and whitespace checks passed. Reused unchanged
  targeted UI, Agent, restore and release evidence; no redundant tests/build.
  Standard non-force push to origin/main succeeded; remote main matches exactly.
  CI run41799731475 is in_progress for that exact SHA; no green result claimed.
  No tag/release publication. Independent docs/CORE_SIMPLIFICATION_PLAN.md,
  docs/DEVELOPMENT_CHECKS.md, tools/dev_lab.py, tools/tests/test_dev_lab.py and
  this mixed working log remain unstaged/local. Next: green exact-commit CI,
  then owner-authorized release tag. No additional device action.

- **Extensions rollout / Core0.3.6 release preparation, 2026-11-04 — completed.**
  Owner authorized deployment and release PREPARATION, not commit/push/tag.
  Guarded normal immutable Core rollout local-eb89bbefce8be4d6802e926a succeeded
  on rasp-3mm (189.384s install,0.883s extract). Reused the checked frontend;
  HTTP-served Extensions-CGQBcNTw.js matches local SHA5821c13a... exactly.
  Live release smoke passes: Core/Agent/Web ready; five main services active,
  NRestarts0; same device identity. Agent dfc8fcad..., Runtime3af4df43... and
  default host666ec3da... retained; no host/Agent update, reboot, restore,
  approval, removal or LCD command. The UI candidate reports Core0.3.6.
  Public preparation: VERSION0.3.6, changelog, release notes, and BG1.0.5.
  Local rollout reserved BG1.0.4 with raw Windows-checkout JSON bytes; public
  BG1.0.5 uses separate canonical Git/LF archive bytes to avoid an immutable
  language version collision. Same translation dictionary apart from version.
  Existing language selection is NOT changed automatically; no manual ZIP install
  is needed for the bundled package. Source release/language checks118 passed,
  16 warnings in42.44s (WSL3.14.4). After final BG metadata bump its actual bundled
  staging/selection case passed again:1 pass/7 warnings in10.29s; not119 unique
  tests. Canonical final BG archive validates through actual package validator,
  SHA4494cf64...; reused UI54, type-check/build/visual and prior Agent/restore
  evidence for unchanged code. Full main CI has not run for this dirty candidate.
  Reviewed27 intended paths are frozen in .runtime/release-036/exact-scope.json
  and commit-paths.txt. Excluded independent simplification/dev-lab documents and
  tools; WORKING_STATE has substantial unrelated history and is excluded too.
  No branch, staging, commit, push, tag or publication. Order remains authorized
  commit/push -> green main CI for exact commit -> separately authorized tag and
  release gates. v0.3.6 does not exist remotely; v0.3.5 publication was verified.
  Next: owner Ctrl+F5 in Extensions and authorize the scoped commit/push when ready.

- **Extensions inventory layout, 2026-11-04 — local UI completed.**
  Owner requested applications first, with Agent modules/providers below in a
  compact, initially collapsed disclosure with count. Each package now has a
  name/device/status summary and separately expandable Details for identifiers,
  installed/requested versions, command/error information and removal controls.
  Original confirmation, acknowledgement, pending/unsupported-Agent guards and
  original-outcome lookup are unchanged. Unresolved removal or load failure
  opens the inventory automatically; stale loaded rows remain visible.
  New EN/BG Details label in source only; no language/version/publication change.
  Targeted Extensions49 checks passed; after the disclosure correction its final
  inventory5 checks passed (54 applicable cases, not overlapping rerun totals).
  Type-check and production build passed using existing Windows dependencies.
  Browser review used actual Vue components and theme tokens with synthetic,
  read-only local fixtures: light/dark, BG, collapsed/expanded and390px layout;
  long IDs wrap with no horizontal overflow. Local screenshot:
  .runtime/agent-inventory/layout-dark.png. No Raspberry/network API actions,
  ZIP installer redesign, removal, rights change, deployment, commit or push.
  Deployed by the later authorized rollout above; unrelated source preserved.

- **Raspberry deployment / real restore trial, 2026-11-04 — completed.**
  Owner approved Core + Agent rollout and chose a NEW backup, not the historical
  failed archive. Standard immutable rollout local-3d54a71ccbc5cb746d9e6fad
  succeeded (Core198.14s, Agent build5.23s/update45.90s). Agent pin is now
  dfc8fcadd37b98b8d7e17d754b599d77253c1e5f60f16d99bdc2ff011623f81c;
  Runtime3af4df43... and default host666ec3da... preserved. Bundled BG remains
  byte-identical611876b4... (new Agent labels fall back to EN until a language
  version update). Reused owner169 backend/53 UI and228 restore checks and
  owner-built Extensions-qfIM-maE.js; added Agent artifact test1 passed/6 warnings
  in17.27s. No duplicate frontend build or broad test run.
  Before trial /ready was ready, all observed Core/Agent/Runtime/helper services
  active with NRestarts0. Admin Agent catalog:1 package/1 installation, uninstall
  support confirmed; NO removal command sent. Fresh encrypted backup
  bkp_20261104T061429Z_da1e843d completed. One restore was dispatched through
  normal API with exact archive confirmation, not replayed. Both restored and
  rollback runtime activation completed, but the stale release_smoke requirement
  /access made BOTH completion checks fail; status restore_rollback_failed.
  Previous files were returned and Core/Agent are active/ready. Refreshed only
  update-helper after diagnosing that false health failure. Retained first
  operation status/recovery evidence; do not call the first restore successful.
  Proven blocker fix: require current /api/v1/devices instead of removed /access.
  Real current Core OpenAPI now exercises restore completion (not mocked health),
  with missing-required-API and mismatched-Agent denials retained. Targeted
  smoke/restore/backup checks30 passed/0 skipped,5 warnings in38.77s (WSL3.14.4),
  .runtime/restore-recovery/smoke-fix-results.xml. Scope adds no retired API adapter.
  One-file Core follow-up local-1a9d35add659ab46cb798217 succeeded (189.16s);
  no additional Agent/frontend/Runtime/host update. Actual live release smoke
  passed before the next trial. One first cold OpenAPI GET exceeded5s; a later
  read returned HTTP200/365215 bytes in0.051s and the15s-budget smoke passed.
  Owner explicitly approved a NEW backup and second restore AFTER the fix.
  Fresh bkp_20261104T063625Z_e4e97f8a completed; its one restore request ran
  06:38:10.826566Z–06:39:07.056450Z and returned completed/error_code null.
  Receipt comparison confirms this is the new restore, not its backup result.
  Final live smoke: Core/Agent/Web ready, same dev_c35c582dbdc544f0a44263c065993623,
  aarch64. Core, Agent, Web, Runtime and update-helper active/NRestarts0.
  Admin catalog still1 package/1 installation/uninstall_supported1. Agent pin
  dfc8fcad..., Runtime3af4df43... and default host666ec3da... unchanged by restore.
  This proves the real systemd write/environment boundary and successful
  restore completion on this device, not just doubled-systemd tests. Standard
  recovery authority fences remain; no app rights were automatically approved.
  Next: owner Ctrl+F5 and inspect Extensions/provider inventory; any destructive
  removal trial or new app approval is separate. Private receipts/prepared kits:
  .runtime/restore-recovery/device-trial.json and /tmp/3mm-restore-trial.oVOEouFW.
  No factory reset, device reboot, rights approval, LCD command, commit or push.

- **Restore recovery follow-up — owner source checks passed; deployed in trial above.**
  The failed Raspberry restore first hit EROFS creating an application-host
  update.lock: its transient service allowed /var/lib/3mm but not the separate
  host journals or per-instance pointers. Files rolled back, but reactivation
  then lacked AI_SETTINGS_MASTER_KEY because restore children did not load
  /etc/3mm/3mm.env. Previous state was manually reactivated; the selected backup
  was NOT successfully applied. These are separate from deferred LCD409 work.
  Local fix: shared restore/child systemd hardening permits only mutable host
  journals and instance pointers, leaving host releases/default read-only.
  Each migration/activation child gets the CURRENT EnvironmentFile via PID1,
  including after rollback; no shell parser, secret argv or cached parent key.
  Before stopping services, validate current rollback identity/key, probe both
  host write roots, and prove child namespace/environment startup. Preserve
  health verification, authority fences and failed-rollback evidence/status.
  Added real encrypted archive/switch/identity regressions with a doubled
  systemd manager for success, migration/app/bootstrap/health failure, current
  key mismatch, read-only mount, child startup failure and failed rollback.
  Owner runner: .runtime/restore-recovery/test.ps1 (default all), retaining
  JUnit/logs and relevant before/after source hashes under its runs directory.
  Python AST, PowerShell parsing and scoped whitespace checks passed. Owner
  completed all-f9d97ab01fbb4d11aba9fdc710a9d3d4 on WSL Python3.14.4:
  228 passed, 0 skipped/failed, 10 warnings, 85.06s. Inspected saved evidence
  and JUnit: 228 cases, exit0, no relevant changes during the run; all21 recorded
  source/test hashes still match. Reuse this result; no tests rerun by agent.
  These were source checks, not original hardware acceptance. The authorized
  deployment, real restore acceptance and completion-check fix are above.
  Version/commit/push unchanged; no automatic factory reset.

- **Agent inventory and complete removal — owner checks passed; deployed above.**
  Owner deferred LCD 409 work and requested that installed providers never be
  hidden and that complete removal be available. Extensions now has a separate
  Agent catalog showing uploaded versions and per-device installations,
  including missing-package records, installed/requested versions and errors.
  New explicit module_uninstall feature/command: exact administrator request,
  original-outcome lookup, stop/purge only the selected Agent module's versions,
  state and data, then confirm a tombstone in Core. Core refuses stale requests,
  unresolved lifecycle deliveries and package retirement while any device still
  references that module. Package retirement also removes archived install bytes
  from terminal command payloads, retaining receipts/audit. Older Agents require
  update; they are never assumed to support deletion. No schema migration,
  version bump, commit, push, deployment, device removal or LCD write requested.
  EN/BG labels added without changing package versions. Python/runner syntax,
  language key parity, frontend type-check and diff checks passed. Owner ran
  .runtime/agent-inventory/test.ps1: backend 169 passed (332 warnings, 86.24s),
  frontend 53 passed (49 Extensions + 4 inventory), type-check/build passed.
  Reuse those unchanged Agent/UI checks; do not repeat for this restore-only
  follow-up. Core + Agent rollout and read-only catalog verification are above.
  This does not fix backup/restore or the remaining Agent execution-permit 409.

- **v0.3.5 release gate.** v0.3.4 was tagged but not published; leave its
  tag unchanged. Corrected the revoked device-source authority error and
  included the missing hardware/HTTP diagnostics labels as BG 1.0.3.
  Commit b2887a6 passed frontend but failed Linux CI on the administrator
  module action for a revoked device. Follow-up d7d4160 returns a controlled
  denial before queuing any command. CI run 41595822796 reached 1161 passes
  then failed the health pool drain at a 2 s per-future watchdog. Follow-up
  4694586 aligns only the test drain with its HTTP watchdog, retaining
  the live latency bounds and eight required successes. Local WSL hit the
  fixture startup timeout before exercising the test. CI run 41598356557
  passed the health test but failed missing peer schema handling after
  1177 passes. Follow-up b7ab609 refuses the entire status authority decision
  if its SQL snapshot cannot be read; 16 identity-authority tests passed in WSL.
  All four main CI jobs passed in run 41600344781 for b7ab609.
  Only then was annotated v0.3.5 pushed; verified it resolves to b7ab609.
  Release run 41609122055 subsequently published v0.3.5; verified via the repository
  release API on2026-11-04 (published2026-11-03T09:36:57Z).
  Staged diff and BG manifest/key parity checks passed locally.
  No device deployment was performed.

- **Post-install 409 follow-up.** Owner confirmed Monitor installation succeeded.
  Export (6): 11 of 15 retained failures report review_key_busy; one of those
  is execution_unconfirmed, not safe to replay. Three older authority requests
  and one UI access request are unclassified. Export does not identify the
  exclusive lock holder. Local Core change: command and connector admissions
  verify under a shared key lease, keeping the same SQLite write fence and
  cleanup-before-key-release order. Key/authority changes and signing still
  use exclusive leases. Extended real-lock tests for both admissions and
  overlapping UI trust. Owner Linux checks: 122 passed, no skips/failures.
  Core-only rollout local-151177dd48645dcbe4e5e87c on rasp-3mm succeeded;
  Core active and /ready ready. Payload diff against local-b0582a77f...
  contains only application_authority_management.py plus release metadata;
  frontend bytes and independent component pins preserved. No operation
  replays or LCD commands issued by the rollout. Next: observe normal Monitor
  use and compare a fresh export; production 409 improvement not yet measured.

- **Crypto Monitor reinstall: separate missing device selection from activation.**
  Read-only Raspberry diagnostics confirmed the 0.7.0 first-registration seal
  and configuration match, but the sealed configuration lacks the required
  DISPLAY_DEVICE_ID. Consent preview stops at required-field validation; this
  is separate from the historical LCD-operation 409. Implemented local Core/UI
  changes: Extensions saves only missing required device choices for the exact
  disabled, not-yet-active package through the staging API, which authenticates
  the original connector registration, validates approved devices, and leaves
  the app stopped and in review_required. Access review and activation remain
  separate. Owner checks: 23 Linux backend and 49 frontend tests passed.
  Frontend type-check and production build passed. Deployed the two scoped
  Core files and rebuilt UI from the last deployed baseline to rasp-3mm:
  local-b0582a77f169372c65d2b3a1, installer succeeded, Core active, /ready ready.
  Independent component pins and bundled BG preserved. Next: owner saves
  the device, reviews access and explicitly activates; no approval, activation
  or LCD commands were issued during this rollout.

- **Owner requests direct diagnosis after Crypto Monitor reinstall, 2026-11-02.**
  Owner accepts spontaneous Core409 improvement; remaining issue is display
  start/locked one-frame test, and now an unsuccessful app reinstall. Basic
  read-only SSH confirms rasp-3mm, Core local-b4a50dca..., Core PID686634 and
  update-helper active with NRestarts0. Newer SSH host key matches the owner's
  earlier device-console confirmation; no SSH trust settings changed. A proposed
  broad privileged diagnostic export was
  rejected by review; it did NOT run. Owner was asked separately to authorize
  ONLY selected app installation/version/error categories, migration revision
  and outstanding LCD command statuses returned to this chat, excluding process
  environment, settings, prices, screen text, secrets and general logs. Owner
  explicitly approved that limited read/export. Executed ignored
  inspect-monitor-status.py with fixed DB path, SQLite mode=ro/query_only and
  selected columns only; no product imports or actions. Two bounded observations
  confirm installation11/instance46e92c9bdffd26e204800468: selected package0.7.0,
  active_version NULL, disabled/enabled0, error NULL, mode review_required.
  Uploaded packages0.6.0 and0.7.0 exist. No retained-data registration, instance
  directory, active.json or own state.sqlite3 found; no associated LCD command
  records remain in the scoped join. Thus the current block is an inert candidate
  requiring fresh exact-package consent before activation: native_activation()
  with active_version None requires a current grant, whose mode must be enforced.
  Not evidence of a failing migration/host startup or an outstanding physical
  command in this current installation. Historical checkbox409 host ValueError
  remains undiagnosed; prior app DB/receipt state is unavailable, so do not claim
  that an old guard is proven or fixed. Next: owner authorizes reinstall/activation
  of0.7.0 and explicitly reviews rights, without Start/Send, then inspect/reproduce
  the LCD control path in a bounded way. No install, grant, service, data, LCD or
  tracked product-code changes; no tests/builds were run.

- **Latest409 after enabling persistent LCD, read-only diagnosis 2026-11-02.**
  Owner reports no spontaneous409s in this observation, but a failure on checking
  persistent enable. Export(5) contains one POST409, no drops: trace
  invoke_4993cfb5d87141a698ba9bcde9a5d6a4,1696.588ms,
  application.host_handler/host_value_error then response_check/ui_policy/
  completion operation_failed, execution_unconfirmed, retryable false. New host
  detail is observed working; this is a caught ValueError within handler execution,
  not an initial Core key/trust denial. Underlying SDK denial is not excluded:
  Crypto's observe() catches SDK errors and start converts unavailable observation
  to ValueError. Inspected current sibling source read-only: actor/request-key,
  payload/geometry/access, settings-revision, live-run/mode/pending and unresolved
  manual-receipt guards can all raise ValueError along this start path. Cannot
  identify the actual guard from the coarse exception family alone. Need failed
  display_live_start payload and only revision/display_geometry/live_display
  from current get_state response; no headers, tokens, full settings or business
  data. Do not retry Start, erase journals or weaken guards. No code/device changes,
  tests or further deployment performed; app fix is not yet identified.

- **Safe host-failure detail, owner authorized 2026-11-02; owner checks passed.**
  Bounded follow-up to exports(4)/(5), NOT a claim that the underlying application
  failure is fixed. Native host negative replies carry only version, fixed
  host_request/context/storage/handler/result stage, closed built-in/SQLite/SDK
  category and host elapsed milliseconds; generic error replaces raw exception
  text. No arbitrary class names, traceback, path, payload, actor or SDK phase
  is exported. SDK's nested refusal/not_dispatched never proves the outer call
  had no effects. Core accepts detail only after current completion policy and
  signed request/response checks; adds one failure-only observation to existing
  Core diagnostic records and recent-HTTP ring, using the SAME trace/instance.
  Missing/malformed/unknown details and collector errors do not change success,
  the generic409, phase, policy, rights or no-replay behavior. No healthy-call
  host record, new recorder, frontend, app-specific Core branch or dependency.
  Prepared real Unix-host socket tests (including handler effect before failure,
  unprintable exceptions and subsequent healthy call), strict metadata/export
  validation, real UI/key/HTTP tests for correlation, inactive/broken recorder,
  forged signature/request, revoked rights and positive/malformed responses.
  Native packaged-host check exercises SDK classifier without checkout/Core.
  Owner runner groups: host-failure then host-failure-consumers; permanent reports
  and existing300s limit retained. Owner completed both groups on SAME source
  c7e7eaf68d166fd1cb686bb148f1e210d30ac4231f9502ee7afe6ec27bb60cd8:
  host-failure169 passed in40.07s (run3af79f679cce4edc9ed876f6c8a51c68),
  consumers134 passed in19.42s (run387ca143999643d58ad7afc075894882).
  Total303 passed,0 skipped/failed; Python3.14.4, unchanged dependency fingerprint
  f91ccaad806c25f0057f8f802db6ed3ad6733a89fd44d3bd934d14d1b8c8c5f7.
  Agent verified both saved evidence/JUnit sets,303 distinct case identities,
  and all1295 frozen source hashes still match current files. No checks rerun.
  Static Python AST for8 files, runner PowerShell syntax and scoped whitespace
  passed; no product imports, tests, build, device changes, commit or publication.
  Prepared ignored prepare-host-failure-deploy.py, deploy-host-failure.ps1 and
  update-host-failure.py. Prepare defaults to local-only; reuses both pinned
  reports and the existing immutable Core builder with exactly3 delivered source
  changes, existing frontend and deferred BG preserved. Expected baseline
  key6694a92de7c2d6185f0cbd8cef32731035115a0c9d2234cf0e9c53302d0152a9
  is a local candidate, NOT independent device attestation; remote preflight
  must confirm it, app0.7.0/package6c919b56..., instance46e92c9bdffd26e204800468
  and previous host666ec3da... before Core deployment. Deploy requires current
  backup confirmation DEPLOY CORE AND CRYPTO HOST. First standard guarded Core
  update preserves all component pins; only after success, verify delivered source
  hashes and build native host from installed Core/existing locked dependencies
  without pip/download, under the shared release lock. Existing exact-instance
  host controller owns health/journal/rollback. No default-host publication,
  Agent/Runtime/other-host update, app upgrade, grants or Start/Send invocation.
  Existing persistent LCD consent may resume output on restart. Two phases have
  independent rollback; if the host phase stops, inspect rather than repeat Core.
  CoreStatus/CoreLogs/HostInspect are observations; HostUpdate is separately
  confirmed continuation after inspection, with exact new-Core/old-host guards.
  Private transfer directory, explicit SSH host-key checks, hash-verified root
  loader/plan, all delivered source/closure hashes and unchanged-other-pins checks
  are retained. Helper Python/embedded-loader AST, PowerShell parser and static
  baseline/delta review only; operator scripts not executed by agent. No new kit
  built, native compilation, test repeat, SSH/device action or deployment here.
  Latest next owner action: observe /monitor and export a fresh failure if409
  recurs; do NOT repeat Deploy/HostUpdate. See completed owner update below.
  Owner attempted Deploy: prepared key
  b4a50dcad60a99164e468a1f30faef721ecaed49488191cea329335e5e39c0bd.
  Remote read-only preflight CONFIRMED baseline6694a92d..., exact app/package,
  old host666ec3da..., active service and no pending host journal. Subsequent
  Core-kit SCP failed at hostname resolution for rasp-3mm.local (exit255).
  Inspected deploy.ps1 throws immediately after that SCP, BEFORE its SSH
  controller-start command; this attempt did not launch installer or host update.
  Local attempted receipt exists; it is NOT proof that a remote job started.
  Only diagnostic helper/plan transfer preceded the failure. Reuse exact prepared
  bundle/checks, restore hostname reachability then retry this guarded Deploy;
  this is a confirmed pre-dispatch transport failure, not an uncertain installer
  acknowledgement or permission to replay any application operation. No product
  code, network/SSH configuration, device or tests changed by agent for diagnosis.
  NEWER owner retry inspection now reports Core b4a50dca... already selected,
  exact Crypto0.7.0/package unchanged, old host666ec3da... active, no host journal.
  This supersedes the earlier device-state conclusion; provided logs do not show
  which intervening attempt selected Core. Preflight correctly refuses the old
  baseline rather than reinstall Core. Saved local plan/helper hashes verified;
  HostUpdate explicitly expects this exact new Core and previous host, verifies
  all delivered bytes, then uses normal native-host health/rollback. No guard
  bypass or source edit needed; no agent test/build/device action performed.
  Owner subsequently completed HostUpdate: status ready, Core keyb4a50dca...,
  selected native host5319e9936cece808c1b1827e6b1962562aaa08bce15922b078b963904e3ab524,
  artifact SHA201e56e46f73de8ede0bde20386083eecc76235cc4d54cd5f8bdacb09eb883ba.
  Core PID686634 retained during the host phase; application_metadata_unchanged
  and other_component_pins_unchanged both true, automatic_retry false. Device now
  has both diagnostic halves. This confirms rollout, NOT resolution of the
  original409 or physical LCD acceptance. Next: hard-refresh /monitor, observe
  the prior spontaneous-failure window, export fresh recent HTTP failures if
  needed; do not blindly repeat an unconfirmed Start. No agent runtime checks,
  device actions or further deploy requested. Crypto0.7.0 package/rights unchanged.

- **Post-fix Core409 exports(4)/(5), read-only diagnosis 2026-11-02.**
  Recent HTTP failures(4): two409s at10:56:04/10:56:46UTC, both
  response_check -> ui_policy -> completion retain operation_failed rather than
  being masked as authority_unavailable. This confirms the observed error-path
  correction, not an independent attestation of the device's deployment key.
  Operation records(5) cover10:57:31-10:58:03UTC:27 invocations,26 completions OK,
  one operation_failed, no diagnostic drops. Failing trace
  invoke_2ea0f7b3c07b4d6cb3e0125896ae24a7 identifies Crypto Monitor instance
  46e92c9bdffd26e204800468. The two exports have NO common trace ID/time window;
  do not attribute the earlier generic HTTP rows to this instance by proximity.
  Inspected relay identifies a verified signed response with ok!=true, not
  response timeout/signature failure or a refusal at the initial Core policy
  checks. Final policy recheck/commit are not reached. Native host catches both
  pre-handler validation and handler/SDK exceptions into that negative response;
  it does not itself log the caught exception. The actual operation ID and safe
  host-side failure category are still missing, so exact root cause is unproven.
  Nearby command.discover/core.request OK is not proof of granted access or a
  causal link to this invocation. Do not change rights, replay Start/Send, erase
  receipts, or claim physical non-execution from these records. Next bounded
  diagnosis needs the host-side failure stage/category correlated to invocation,
  without exposing raw exception text/payloads. Only exports and relevant source
  read this turn; no tests, imports, application/device actions or code changes.

- **Core409 key-error masking fix, owner authorized 2026-11-02; prepared.**
  Scope: preserve errors from code running under a key lease rather than turn
  RuntimeError-derived gateway/transport failures into AuthorityReviewKeyError.
  Only production edit is application_authority_keys.py. Acquisition and cleanup
  own an ExitStack; only their actual adapter operations are normalized. The
  yielded caller is outside that error adapter. Identity/fingerprint/rotation,
  record reads and locked-key checks/signatures retain private fail-closed key
  errors; no file mode/path checks, lock mode/timeouts, trust/grant decisions or
  key provisioning/recovery semantics are weakened. Caller cleanup still ends
  DB transactions before releasing the key. Actual cleanup failure remains a
  denial and adapter.active becomes false on every yielded-key exit.
  Prepared new real-POSIX tests for caller error identity (including gateway,
  transport, SQL, OS, runtime and cancellation), missing keys, partial acquisition
  and cleanup failures. Real HTTP/UI negative signed response, bad signature and
  malformed result retain operation_failed/response_invalid through completion,
  with one dispatch and no key/trust misclassification or private text export.
  These tests work with active/inactive opt-in diagnostics. Existing deliberately
  unexpected RuntimeError fixtures now expect original error/HTTP500 rather than
  the incorrect key-trust409; declared policy refusals stay redacted at their
  actual resource boundary. Existing rollback-failure tests still assert physical
  key/DB cleanup and rolled-back own data. No other failure was relabelled a pass.
  Owner runner adds key-errors then deduplicated key-errors-consumers, covering
  the shared key's read/write authority, session/UI, SDK effects and RPC consumers.
  No frontend build or entire Python suite requested. Previous166 passes precede
  this production edit and are NOT claimed to test it. Agent static review passed:
  Python AST/whitespace for five Python files, PowerShell runner parsing and
  tracked diff whitespace; no product imports/tests/builds. Crypto0.7.0 source, Agent,
  Runtime/host code, VERSION and grants unchanged; no commit or device actions.
  Owner key-errors run passed130, skipped2, no failures in42.23s. Source
  6ae482f42cb6f47ed6d8d8ffeb30929216a35a000ddcfdd80d4bc2e118fb682b;
  permanent run key-errors-41ac7ab6af794261bbb21253572f0f25. Python3.14.4,
  unchanged dependency fingerprintf91ccaad... . Skips are root/foreign-UID
  acceptance and the non-POSIX-only refusal, NOT passes. Agent verified saved
  JUnit132 cases/2 skips/0 failures and all1293 frozen source hashes still match
  current source. These130 successful checks are reused without repetition.
  Combined key-errors-consumers run da7c298c6a99447b9a8e8e7a77a09cc9 stopped
  at run_lab's300s subprocess timeout (exit2), not a recorded test assertion.
  It retained only tests.log through66% progress, no JUnit/evidence.json; no
  individual completed module identities, so none of those dots certify a pass.
  This does not distinguish a slow full selection from a waiting specific test.
  Fixed only ignored runner selection/reporting: six disjoint consumer groups
  (policy/effects/callbacks/public/events/ui), exact same28 modules, none from
  successful key-errors. Per-run300s bound unchanged, verbose node IDs/slowest8
  durations retained and missing-JUnit failures include the bounded log tail.
  Static AST selection review confirmed exact coverage/no duplicates. No product
  source, test behavior, dependencies or application installation changed after
  the successful130-case run. Owner subsequently completed all six groups on
  SAME source6ae482f4... /Python3.14.4 /dependency fingerprintf91ccaad...:
  policy210, effects97, callbacks127, public29+1skip, events63, UI108+13skips.
  Together with key-errors130+2skips:764 passed,16 skipped,0 failed; seven saved
  JUnit/evidence/log sets verified, no duplicate case identities, all1293 frozen
  source hashes still match current source. The timed-out combined run is NOT
  reused. Skips remain unproven root-boundary/non-POSIX cases, not passes.
  Evidence pinned in ignored prepare-key-errors-deploy.py; no checks repeated.
  Prepared deploy-key-errors.ps1 (default Prepare; explicit Deploy plus backup
  confirmation DEPLOY CORE KEY FIX), reusing existing generic guarded builder.
  Expected baseline key4e9f2bc0cba1690ee1a0a76dd362bc6a778125cd5ca7f7c55b70f9fe907f8d52
  under completion-detail-deploy. A local baseline candidate exists; this is not
  independent confirmation of the device's selected key, so remote guard must
  verify it before installation. Exactly one delivered source file changes:
  application_authority_keys.py; archive comparison confirmed it plus deferred BG
  source drift, which stays out. Existing prebuilt frontend is unchanged, as are
  independent Agent/Runtime/host pins and grants. Standard immutable installer,
  backups/rollback and no-replay guards retained; Core/related services restart,
  no reboot. Existing saved application consent may resume output; launcher never
  invokes Start/Send or approves rights. Static Python AST/report-hash/unchanged
  frontend/runner-guard review and PowerShell parser passed. Agent did not build
  a kit, import product code, run tests, deploy, restart or invoke app/hardware.
  Next owner action: deploy-key-errors.ps1 -Action Deploy; then observe /monitor
  and send the actual Response/new recent-failure export if409 recurs. Do not
  repeat an unconfirmed Start. Host-side ok:false remains a
  separate unresolved failure; fixing its misleading label does not make that
  negative response a successful command or permit automatic replay.

- **Core409 export(3), read-only diagnosis 2026-11-02.** Owner supplied
  Downloads/3mm-recent-http-failures (3).json. Two retained failures; all drop
  counters zero. New fine stages are present, but export alone does not attest
  the exact installed deployment key. Trace invoke_a97e35c90d6c48d0a59e652209fb2c59
  at06:13:47.384UTC /08:13:47 Sofia: application.response_check/operation_failed,
  execution_unconfirmed,1617.740ms; then ui_policy/operation_failed, outer
  completion/authority_unavailable. In inspected relay this identifies the
  verified response's ok!=true branch: signature/request validation passed,
  initial completion policy/binding passed; final policy recheck/commit were
  not reached. NOT proof of physical non-execution or missing Core rights.
  Generic native host catches both pre-handler validation and handler/SDK
  exceptions into signed ok:false plus bounded raw error text; exact exception
  and operation/module identity are intentionally absent from this HTTP export.
  Cannot assign this trace to Crypto solely from route template; correlate the
  browser x-3mm-trace-id before attributing it. Native host catch does not itself
  log this exception, so ordinary journal output cannot be assumed to retain it.
  Confirmed Core masking defect: ApplicationGatewayError subclasses RuntimeError;
  CoreReviewKeyStore._access catches RuntimeError across its yielded caller body,
  converts response failure into AuthorityReviewKeyError, route boundary converts
  that to generic UI-trust409, then completion labels authority_unavailable.
  This explains the misleading outer diagnosis, NOT the host's negative result.
  Separate trace invoke_e551e874cddf4026a50e2ad7ac2a0cc3 at06:08:33.429UTC /
  08:08:33 Sofia: application.dispatch/transport_unavailable,not_dispatched,
  1155.865ms. Failure before first send; no evidence of an LCD write, key busy
  or M20 refusal in this record. Transport reason alone does not identify whether
  socket connect/peer I/O failed. Both retryable=false; no automatic replay.
  Next bounded proposed work: preserve caller exceptions through the key lease,
  with actual-key failures still denied and DB-before-key cleanup preserved;
  obtain a safe classified host-side negative cause, not another broad timeout/
  rights change. This turn is diagnosis only: no executable changes, tests,
  deployment, restart, grants or app/LCD invocation. Root host failure unresolved.

- **Active Core409 investigation: owner explicitly requested the permissions
  path, 2026-11-02.** Read-only audit: the observed administrator operations
  endpoint requires a current admin principal; ordinary user/route denials are
  classified401/403, whereas UI trust/current-authority errors can become409.
  Missing a named application permission alone is not proof of this admin-path
  failure; service M20 authority and human access remain separate. No root cause
  claimed from the supplied generic completion response. Extended the existing
  ignored .runtime/cap14-crypto/inspect-ui-trust.{py,ps1} with optional -Access
  and -UserId. It runs only in a short-lived process as the actual non-root Core
  UID/environment, using installed code and SQLite mode=ro/query_only. A local
  SQLite audit hook refuses any unexpected writable/default connection. Reads
  bounded administrator-role/operation/route permissions and active-unexpired
  login counts without fetching tokens, tests current same-Session UI proof
  across expire_all, and validates current M20/declared command grants through
  their real read-only evaluators. It does not validate the browser JWT, execute
  the HTTP write fence, call application handlers/SDK effects, grant/recover
  authority, restart services or touch I2C. Thus a clean sample cannot exclude
  an intermittent completion failure. Python AST / PowerShell parsing passed;
  probe not executed by agent. Owner then ran -Access: exact installed0.7.0
  package SHA6c919b56f1e1e4316c5865fa0d0d04625594625ea914fc686da7013d2a082891
  matches the local built ZIP; UI digestc4bc8a153cc40bcf5b3d95ff78b947727e1f2e14e1753b3a5152a228309f09c3.
  Core PID407716. All code/build/key/trust/same-Session proof stages passed.
  Candidate admin1 is present, unblocked, with subject identity and current
  monitor_configure/display/privacy access; monitor route and live operations
  allowed. Internal health is not administrator-callable by design. Twelve
  active-unexpired login records do NOT identify or validate the browser JWT.
  Current M20 scopes connector:coinbase/coingecko and command:display_frame
  passed both current-grant and exact command-grant evaluators. No missing
  permission demonstrated; this sample does not exercise the HTTP write fence,
  concurrent completion or the browser token. Do not change/reapprove rights.
  Next bounded result: Core-only diagnostic deployment below, executed by owner.

- **Core409 completion diagnostic gap, prepared 2026-11-02.** Existing exports
  cannot locate four broad ui_policy/authority_unavailable completion failures.
  Added failure-only fixed stages for initial/final completion policy checks,
  binding/preparation, response validation and commit; UI preflight/client
  binding/artifact/Session-proof failures are retained BEFORE existing redaction.
  Gateway allowlisted reasons and invalid response signatures retain their safe
  category. Public HTTP errors, auth/grant evaluations, check order, lock mode/
  timeout, transaction lifetime and no-replay behavior are unchanged. Ring stays
  memory-only100/15min with six fixed metadata details and existing caps. Healthy
  calls produce no additional events. No bodies/exception messages/tokens,
  concrete module/operation identifiers or filesystem paths are added.
  Prepared regression coverage for current permission/session revocation after
  dispatch, stale browser bindings, expired/switched Session proof, transport-key
  changes, response failures and commit SQLITE_BUSY, with and without opt-in.
  Each already-dispatched failure remains execution_unconfirmed and sends once;
  this is diagnostic preparation, NOT a confirmed fix of the installed cause.
  Owner command: .runtime/core-ui-concurrency/test.ps1 -Group completion-detail
  -StopOnFirstFailure. Uses existing isolated runner/environment and permanent
  evidence; no installed Core, app invocation, grants or LCD writes. Agent runs
  only syntax/whitespace review: Python AST passed for all eight changed Python
  files, PowerShell runner parsed, tracked diff whitespace passed. This is NOT
  runtime evidence; no product imports/tests/builds. No app0.7.0
  source, VERSION, deployment, service action or commit. Device acceptance pending.
  Owner completion-detail run passed166, no skips/failures, 55.70s, source
  30e164f82ed9e7070a8620a96ed729f0fda4796418bd3afdd92616c82553ae79,
  Python3.14.4 with unchanged dependency fingerprintf91ccaad... . Permanent
  evidence: .runtime/core-ui-concurrency/runs/completion-detail-6f3c156469904fc288c285888b382174.
  Agent read-only verification: all1292 frozen source files/hash values still
  match current source; JUnit/evidence/log hashes pinned in the owner preparer.
  No checks repeated. Prepared deploy-completion.ps1 (default Prepare, explicit
  Deploy plus backup confirmation) and prepare-completion-deploy.py, reusing
  the existing guarded Core-only builder with explicit evidence/baseline inputs.
  Expected installed deployment91c92deb18eb043de2249fac3772837f518ac4d775aec64de93392532ab5bc04.
  Exactly five delivered source changes: application_extensions route,
  application_invocation_relay, compiled_ui, operation_diagnostics and protocol
  diagnostics. Frozen payload comparison confirms that delta; unrelated changed
  bundled BG remains deferred/preserved. Frontend is reused byte-for-byte;
  independent Agent/Runtime/application-host pins and grants stay unchanged.
  Standard immutable installer/backups/rollback and no-replay guards retained.
  Normal Core/related-service restarts may pause/resume app output according to
  existing saved app consent, but launcher never calls Start/Send/reviews rights.
  No kit builder, tests, imports of product code, deployment or device actions
  executed by agent. Next owner action: deploy-completion.ps1 -Action Deploy;
  after readiness use status reads / monitor opening and export a fresh409
  within15min. Do not repeat an unconfirmed Start, reapprove rights or clear IDs.

- **Active app-only follow-up: Crypto Monitor 0.7.0, owner approved 2026-11-01.**
  Owner requested visible original-frame recovery plus a durable enable checkbox
  that works without the browser and across service/device restart; Core VERSION
  remains unchanged. Source prepared in sibling 3mm-crypto-monitor: migration
  0007 conservatively requires new persistence consent after 0.6.0, preserving
  pending intent, sequence, settings, cached prices and all existing journals.
  Enabled healthy output resumes with fresh M20/target/profile checks and new
  sequence IDs; delayed startup readiness is observed without submission.
  Normal revocation/profile drift, failed/retired authority and unknown outcomes
  remain fenced. Disable persists even while blocked/pending/dirty; an admitted
  in-flight frame may finish. Original-ID Check now returns bounded last-check
  status/time and the UI displays its response immediately, including busy,
  not_found, denied/unavailable, identity mismatch and confirmed completion.
  Separate explicit recover command can continue a missing original admission
  ONCE, only after fresh exact Core not_found, no known command ID and same
  current reviewed target/geometry. It retains original args/SDK ID, commits
  its attempt and control receipt before SDK work, and checks Stop generation;
  no SQL transaction spans lookup/submission. Late original replies are observed,
  never assigned a replacement effect ID. Lost recovery acknowledgement stays
  pending/read-only. New backend/UI checks prepared for these cases, migration,
  restart persistence, stop races and denial; no agent-run tests/build/imports,
  no new package built, no deployment/service action, rights approval or LCD write.
  Owner checks supplied 2026-11-02: backend 99 passed / 25.368s, snapshot
  54cf4b286114463eadef05fee3afa046; frontend Vite build, Vue type-check and
  46 UI tests / 3 files passed, snapshot da10d25d96b343c6aabfa3044110fd56.
  Both existing Windows snapshots under AppData/Local/Temp/3mm-crypto-display-<id>
  have inputs.json: all 21 source SHA-256 values in EACH match current app source,
  with no missing or unrepresented source inputs (read-only comparison by agent).
  No checks repeated. Package build was pending at that verification handoff;
  the subsequently observed owner artifact is recorded below.
  Next: owner builds the 0.7.0 ZIP, then separately reviews/activates that exact
  package and tests original-frame recovery plus enabled/browser-closed/restart/
  disable behavior. Physical acceptance remains outstanding. These app results
  do not certify the independent dirty Core changes or authorize a commit yet.
  Static preparation passed: Python AST syntax for 12 files, Vue script/template
  syntax for 4 components and TS syntax for 3 UI test files; this is not type-check,
  build or runtime evidence. Owner runner itself is unchanged and installs nothing.
  This app work does not resolve or reopen the remaining Core409 lock-holder
  diagnosis recorded below. Preserve independent dirty Core/Agent/M21 work.
  Owner browser screenshot 2026-11-02 ~06:09 shows new persistent checkbox
  visually checked BUT mode stopped/original_outcome_read (output disabled),
  no pending frame, old confirmed text20:22:48 and last check05:48:51. A control
  request07c42680bd9a819f7e73eab8f70855db is retained with generic unconfirmed
  control error. Network filter shows get_state200 only; it hides the actual
  start operation, so these reads do not prove successful activation or closure
  of409s. Possible rejected async checkbox DOM/model drift is a UI candidate,
  NOT a confirmed installed cause. Next read-only evidence: existing last
  display_live_start HTTP status/Response and latest get_state.live_display;
  do not toggle/replay/reset or blame LCD/I2C from this screenshot. Local owner
  ZIP now exists at sibling dist/3mm-crypto-monitor-0.7.0.zip,43884bytes, built
  2026-11-02 05:46:28 local. Exact installed bytes not independently checked.
  No executable source changes, test/build repetition or device action by agent.
  Owner then supplied start-response detail: "Application result is unconfirmed;
  do not replay". This does not establish whether Start committed its enabled
  flag. The relay can redact completion policy failures AFTER app dispatch to
  this message; never infer non-execution or resend from it. Still need latest
  successful get_state.live_display (enabled/mode/reason/pending/run_id), not
  another Start attempt. UI catch preserves control ID and emits a status read;
  checked DOM alone is not durable service-state evidence. No fix implemented
  from this incomplete observation.
  Owner confirms the checkbox disappears after page reload and Start still
  returns409: latest observed service state is disabled, not successful enabled
  acceptance. This does not prove the original call never executed or authorize
  replay. Static audit traced remaining redaction: _ui_route masks build/proof
  errors; invocation_transaction labels its entire yielded body ui_policy;
  finish_invocation also maps current-policy HTTP refusals to the generic
  unconfirmed response. No finer final sub-check exists in the supplied ring.
  Checked principal/permission readers are read-only; no evidence of a login
  validator commit invalidating the snapshot was found. Do not assert a root
  cause. Proposed next Core-only diagnostic slice separates final policy read,
  immutable binding/preparation, UI proof, response validation and commit,
  preserving all checks/locks/no-replay. That slice is now prepared above;
  Crypto0.7.0 tested files remain unchanged, and owner checks are pending.

- **Core409 evidence update, read-only audit 2026-11-02.** Owner supplied
  Downloads/3mm-recent-http-failures (2).json (2753 bytes). Five retained POST
  operations-route409s at 05:48:53.967-05:50:45.936 Europe/Sofia: ONE
  authority.key_acquire/review_key_busy at admission, not_dispatched; FOUR
  authority.ui_policy/authority_unavailable with application.completion,
  execution_unconfirmed. All retryable=false. The latter four reached the
  acquired invocation lease's caller body, NOT the key-acquisition failure
  boundary; its broad span can cover admit/UI-policy validation, preparation,
  completion identity checks and commit. No exact failing sub-check or lock
  holder is identified. Do not claim SQLite busy, missing trust, LCD/host crash,
  actual non-execution, or that all records belong to Crypto Monitor: module and
  operation IDs are intentionally absent. HTTP totals970.186-1701.179ms are not
  lock-hold durations. Ring expired151 older records, with rate/busy/invalid/
  evicted all zero; these five are NOT a complete failure history or comparable
  error-rate window against export(1)'s single retained key-busy completion.
  Next proposed bounded investigation: distinguish completion sub-boundaries
  before redaction using fixed safe metadata, separately from remaining EX
  writer contention; preserve current revalidation and no automatic replay.
  No production/test changes, reruns, login, deployment, grants or LCD writes.

- **CAP14 live LCD output: 0.6.0 software checks green; physical live-mode incident under diagnosis, 2026-11-01.**
  Owner explicitly approved version 0.6.0 and application-owned Start/Stop for
  saved clock/currency layouts and rotation without an open browser. Existing
  CAP08 task restrictions/intervals were inspected: do not expand Core tasks for
  this app. The original app-only slice uses the existing reviewed-native
  service, native ApplicationStorage and public M20 display_frame commands.
  The owner subsequently approved a separate generic Core UI concurrency fix
  below; no SDK/Agent/runtime dependency, direct I2C access or VERSION change.
  New sibling service live_display.py keeps one durable singleton, unique run
  IDs, monotonic per-run effect IDs, one committed-before-submit pending intent
  and last confirmed frame. Migration 0006 is additive and leaves settings,
  samples, manual journals and receipts unchanged. The bounded worker renders
  every 0.5s, coalesces unchanged frames and waits for original native execution
  evidence before a later frame; no backlog or submit retry. Existing separate
  quote polling keeps its >=30s bound. Settings saves affect future frames only
  after explicit Start. Preview/mount/install do not start output. Stop prevents
  later intents; an already-journalled in-flight effect may finish. Unknown/lost
  receipts pause, original-ID Check only observes; restart leaves output stopped
  or pending for inspection. Revocation/profile drift pauses without automatic
  resume; retired-grant completion cannot revive the run. Start uses revision,
  exact geometry, prior-run CAS and explicit acknowledgement; controls require
  the current administrator/monitor_display. Background effects use current app
  M20 authority, not continuing human delegation. Pending manual frames must be
  reconciled before Start; new manual frames are blocked while live/pending.
  LiveDisplay.vue separates live controls from the preserved one-frame recovery
  UI, displays pending identity and allows Stop even with a dirty draft. New
  backend and UI checks cover lifecycle, lost acknowledgement, no-replay,
  stop/admission interleaving, migration, clock/cache/rotation and revocation.
  Owner backend ran 83 checks in 17.616s: 81 passed, two package consumer errors
  from the SAME overlong monitor_display description (>160 characters). All
  live/migration/legacy behavior checks passed. Owner snapshot
  C:/Users/LAZ-DELL/AppData/Local/Temp/3mm-crypto-display-1600a158c8074cdf923557080396a489:
  all 21 captured inputs matched current source before the metadata-only fix.
  Shortened the permission description without changing authority or runtime
  behavior. Owner package group passed both failed real Core package consumers,
  exit_code=0, snapshot 656b7028ca614ff294efaaeae834ca81. Owner frontend group
  passed Vite build, Vue type-check and 37 UI tests / 3 files, exit_code=0,
  snapshot f9ad165f81fa421f9671d547ec0519aa. Both snapshots live under
  C:/Users/LAZ-DELL/AppData/Local/Temp/3mm-crypto-display-<id>; all 21 captured
  inputs in EACH match current sources (read-only SHA-256 comparison).
  Reuse the 81 unchanged passed behavior checks plus the two corrected package
  consumer passes; do not describe this as a new full-backend run.
  No tests repeated/executed by the agent; old 0.5.2 results below are not evidence
  for later source. Owner subsequently built/activated and started live output;
  local dist/3mm-crypto-monitor-0.6.0.zip is 39853 bytes, SHA-256
  6193e380c9f00feec354d2b41ed70e04dfeb346dfd867cf1195cdd3179806b6c.
  Exact installed bytes have not been separately captured. No installation,
  deployment, approval, service/device action or physical write by the agent.
  Static preparation passed: AST for seven Python files, Vue script/template and
  TS syntax for three components/three UI test files, working-state whitespace.
  This is not type-check/build or test execution. SHA-256 of the accepted 0.5.2
  ZIP remains 2834a84f925bfa9f8840049be11a602045221e9eab0c5f096c56d0dd441152e7.
  Service restart auto-resume is deliberately outside this bounded acceptance.
  Do not close live operation until owner tests and browser-independent physical
  clock/price/rotation/Stop acceptance succeed. Preserve accepted transport.
  NEW owner incident: after Start, extension features/menus temporarily vanish,
  others return but Crypto remains unavailable. Screenshot first shows Running /
  Agent confirmed last frame plus repeated get_state HTTP 409; a fresh page
  stays Loading / operation failed. This does NOT yet prove a Core crash,
  extension deletion, SQLite failure or OOM. No physical reproduction/restart,
  grant changes, speculative code patch, new version or tests performed.
  Owner read-only unit evidence: Core PID90155 active since 2026-10-31 22:04:47
  EET, Runtime PID90172 since 22:04:48; Crypto PID244724 active since 2026-11-01
  08:55:32. All three Result=success, NRestarts=0, ExecMainStatus=0. No process
  restart is evidenced; active alone does not prove request responsiveness.
  Journal command failed before reading logs: Windows SSH split the quoted
  "1 hour ago" argument (timestamp parsed as 1). Owner then supplied the last
  200 boot journal entries, attachment 3a277d72-1b0c-4c17-9c0c-b12622d669a2.
  They cover 09:08:04-09:08:52 EET, not the original ~08:57 event, and show two
  DISTINCT cases: client 192.168.1.62 repeatedly GETs ui-host with obsolete
  0.5.2 SHA2834a84f... and gets409; client 192.168.1.59 GETs current 0.6.0
  SHA6193e380... / built UI1ac6f631... at09:08:30 and gets200, then POSTs
  operations/get_state at09:08:31 and gets409. Do NOT dismiss the latter as
  stale-cache-only. Agent state/authority calls continue200/202; a device
  command result is accepted200 at09:08:41 (not proof of its execution status).
  This excerpt contains no traceback or process exit. Owner then supplied CURRENT
  get_state409 detail: "Application UI build is unavailable; reload the interface"
  and confirms the physical clock keeps changing. The refusal maps to Core
  application_extensions._ui_route (before app get_state dispatch), covering
  package/build verification OR current native UI code-trust failure. It is not
  evidence that the LCD worker stopped. Do not infer a missing build, lost grant
  or key-lock contention from this deliberately generic error alone.
  Owner ran .runtime/cap14-crypto/inspect-ui-trust.ps1. Its stdin-only probe
  inherits the existing Core environment, drops to its existing UID/groups and
  reads installed package/build/key read-lease/code-trust stages. SQLite mode=ro
  AND query_only prevent writes. No native app invocation, resource approval,
  frame, service restart, remote file, key recovery or diagnostic hook in the
  running Core. It reports only identifiers, bounded reason codes/error types
  and durations, not environment/keys/tokens or exception text. Python/PowerShell
  syntax checked only; no probe/test/device execution by the agent. No product
  source or version changed. No more broad logs or physical replays. Preserve the
  original live intent; do not repeatedly Start or resubmit its physical command.
  First owner probe stopped with InvalidRequestError before emitting installed
  metadata: no UI trust result was obtained. Probe imported backend.db.User but
  omitted its UserSession/AuditLog/Permission/Role/Group relationship registration.
  Added those four existing model modules and explicit configure_mappers before
  the first query, without importing backend.database or creating a writable
  engine. Added safe stage codes to unexpected probe failures. This repairs
  diagnostic setup only, NOT the underlying UI incident.
  Corrected owner probe PASSED: CorePID90155; installation11 active/enabled,
  authority_mode=enforced, active/package_version0.6.0, exact artifactSHA6193e380...
  installed_code_prepare147ms; compiled_ui_files13ms; exact UI1ac6f631...;
  review_key_read_lease2ms; current_ui_code_trust133ms. changed=false,
  application_invoked=false, physical_write=false. This rules out a persistent
  missing/mismatched local build or invalid current UI review at probe time;
  it does NOT reproduce the failing HTTP request or prove concurrent-key/SQLite
  contention. No trust recovery/reapproval/reinstall is indicated by this evidence.
  Source comparison shows normal HTTP UI operations call separate trust snapshot
  readers during admission/completion, whereas M21's existing snapshot path
  carries one exact shared-session proof. Owner explicitly approved reviewing
  and fixing this general Core authorization-flow discrepancy before release.
  Prepared change: ordinary HTTP operation admission and completion now acquire
  the code-review SH key lease before one caller-owned DB transaction, carry
  only an exact Session/transaction/installation/package/build code proof and
  expire it before releasing the lease. SQLite initial reads explicitly BEGIN;
  final admission/completion obtain the existing lifecycle write fence BEFORE
  policy reads, rather than upgrading a reader behind a pending SDK writer.
  Native UI review, human/session/route access and lifecycle remain fresh at
  each boundary. No stored grant cache, global serialization, journal-mode
  change, module-specific rule, permission weakening or effect retry was added.
  Relational metadata preparation is separated from code preparation so all
  metadata IPC, reservation, dispatch and response waits remain outside the
  caller DB/key leases. Tickets retain their independent current resource
  checks. Completion failures still mean unconfirmed, never not-dispatched.
  Existing M21 snapshot/session-worker source is unchanged.
  New test_application_ui_concurrency.py exercises ordinary HTTP with real
  protected native review and actor policy, actual pending SQLite DELETE/WAL
  writers, proof expiry/foreign Session/transaction/build/source rejection, and
  human/native/recovery/lifecycle/build/package drift across metadata/response
  boundaries. Only the response transport is doubled: no physical device I/O.
  Relay tests additionally cover metadata ticket handoff and honest completion
  phases. Owner's isolated repro group PASSED (exit_code=0), 29.37s test
  process, 2.16s preparation; snapshot c6fc6af9d3311dc98d7b8168eb252ac94067ae4e842dbdb0452bd709896e2940,
  HEAD061e7ebe76c325c5203708b03550dba2e1b611f1 plus dirty source, Ubuntu/WSL
  Python3.14.4, reused dependency environment f91ccaad806c25f0057f8f802db6ed3ad6733a89fd44d3bd934d14d1b8c8c5f7.
  Evidence: /tmp/3mm-lab-17f427yf/{evidence.json,results.xml,tests.log}; selected
  test_application_ui_concurrency.py and test_application_invocation_relay.py.
  Owner supplied exit status/provenance, not test/skip totals. This validates
  the prepared synthetic interleavings, not a failing pre-fix baseline or the
  installed Raspberry incident. No implementation/test edits or agent reruns
  followed this result; only the handoff was updated.
  Owner then completed both remaining groups on the SAME source/dependency
  digests above: ui 127 passed / 13 skipped, 72.05s pytest (77.92s process),
  evidence /tmp/3mm-lab-s68f2s42; consumers 211 passed / 1 skipped, 222.49s
  pytest (228.94s process), evidence /tmp/3mm-lab-3tttrp6j. Both exit_code=0.
  The 13 relational-runtime skips require the real root helper boundary;
  the public-web skip requires distinct OS principals under a root driver.
  These 14 cases are NOT passes; their privileged isolated acceptance remains
  separate. Reuse these successful unchanged-source groups, not another full
  run. Agent read the owner log and updated this handoff only.
  Owner runner: .runtime/core-ui-concurrency/test.ps1, groups repro / ui /
  consumers, using isolated verified dev-lab snapshots with optional libraries.
  Static preparation passed: AST parsing of eight Python files, PowerShell
  parser, selected test-path existence and scoped git diff --check. These are
  syntax/input checks only, not an executed concurrency/security regression.
  Owner runs tests; no tests/build/dependency installation, SSH/device changes,
  grants/recovery, frame replay, commit/push/release or version change by agent.
  Owner requested comparison with a 30-Oct audit (two supplied points, despite
  its introduction saying three). READ-ONLY product review confirms the HTTP
  boundary fix is narrower than a universal lock-order repair: relay callers
  without boundary (delegations / installation-peer callbacks) still take the
  DB write fence before callbacks/preparation that may acquire a review key.
  effect_admission takes key -> guard on admission, but its ExitStack releases
  the key before the outer except rolls back a failed DB transaction. Neither
  uncovered interleaving is proved safe by the existing green consumer tests.
  Diagnostics gap also confirmed: Runtime responses.py sends failure codes
  deadline_exceeded / response_unconfirmed; Core ResponseWaiter.receive accepts
  only the success response envelope and reduces both failures to ValueError.
  The application.response span also includes completion authorization and uses
  the default operation_failed reason, so wait failure and final policy denial
  cannot be reliably separated. Existing bounded opt-in recorder already has
  duration/trace IDs; a fixed reason mapping and separate completion stage would
  suffice, retaining generic public errors and honest no-replay dispatch phases.
  Owner subsequently explicitly approved fixing both supplied audit points;
  the omitted third point is out of scope. Prepared follow-up: generalized the
  short code lease to invocation_transaction, retaining exact UI proof when a
  package has compiled UI. Delegations use its live read-only key for their
  existing current-grant/actor checks, without nested EX acquisition. Peer
  callbacks enter an explicit boundary too; existing unsupported scoped peer
  declarations remain denied (no peer feature/rights expansion). Enforced
  relay calls without a boundary now fail before preparation/dispatch.
  SDK effect_admission closes the clean routing reader before code/key work;
  its ExitStack now closes the DB before the key on every exit, including
  explicit release and unexpected caller errors. Failed rollback invalidates
  the connection while the key is still held. No timeout increase or effect retry.
  Core now decodes exact Runtime failure envelopes to a closed safe reason,
  rejecting unknown/extra/foreign-nonce frames. Opt-in bounded diagnostics have
  separate admission / dispatch / response / completion spans, one trace ID,
  durations and fixed reason categories. Public unknown outcomes stay generic;
  known not-dispatched versus execution-unconfirmed and retryable=false remain.
  No bodies, tokens, keys, exception text, new spool or diagnostic auto-start.
  New targeted tests cover actual delegation/peer fence ordering, SDK rollback/
  release/failure cleanup (including failed driver rollback), real Runtime
  deadline/invalid-frame replies, safe diagnostics and no-resend phases.
  Static preparation PASSED: AST for 14 Python files, PowerShell parser, all
  selected test paths and scoped diff whitespace. No tests/imports/build were
  executed by the agent. No installed services, grants, device/LCD actions,
  version, commit or publication changed. Previous green c6fc6af9... groups
  describe the PRIOR candidate, not these later code changes.
  Owner audit run FAILED (exit_code=1), source
  f165cbe4f9af88348218a063cd9751c06524df1cebf42f17e13966b2dd593144,
  same HEAD061e7ebe... and dependency digest f91ccaad...; Python3.14.4,
  2.64s preparation / 40.97s test process. Evidence path supplied:
  /tmp/3mm-lab-21tmr2ru. The owner pasted provenance only, with no failing test,
  traceback or pass/skip counts. Owner confirmed tests.log is absent; agent's
  read-only check also found the whole named lab directory, results.xml and
  evidence.json absent. The original source-f165cbe4...tar remains on Windows,
  but no saved failure report was found. No runtime cause is inferred from
  exit_code alone. Prepared only the ignored owner runner to retain console,
  tests.log, JUnit, evidence and extracted failure text under
  .runtime/core-ui-concurrency/runs/<group>-<unique-id> on Windows. Fixtures and
  permission/locking checks remain in Linux /tmp. Runner receipts include its
  own hash; successful exit now requires retained test reports. Optional
  StopOnFirstFailure requests --maxfail=1 and a long traceback. Product source
  was not changed for this evidence-recovery step. Static Python AST, selected
  path existence, PowerShell syntax and handoff whitespace checked only;
  no tests were executed by the agent.
  Owner repeated audit with stop-first on the SAME f165cbe4... source/dependencies:
  1 failed / 2 passed, 7.57s pytest, 9.4s process. Reports are now retained in
  .runtime/core-ui-concurrency/runs/audit-e2e5c246fee348e280812b5bbf882bd1.
  Exact failure: test_sdk_transaction_ends_before_key_even_on_failure[unexpected]
  expected RuntimeError, but the EXISTING CoreReviewKeyStore._access redacts
  caller RuntimeError to AuthorityReviewKeyError; effect_admission then emits
  its generic ValueError. This is a wrong new-test expectation, not evidence
  to change the key/error contract. Corrected only that test: expect the exact
  generic denial for injected caller/driver failures, and observe the ORIGINAL
  injected exception reaching the real key context before redaction. Existing
  key-first, DB-ended-before-key-release, independent writer commit, rollback/
  invalidation and committed-state assertions remain. No production change.
  Owner rerun on source4a94ab9f78c56d9c7b464fdbea327a13058e8cc584be88ac5f30e47b92df2e2b,
  same HEAD/dependencies, passed ALL nine lock-order cases (seven SDK exits,
  delegation and peer callback), then failed first diagnostic actor case:
  9 passed / 1 failed, 14.22s pytest, 16.27s process. Retained reports:
  .runtime/core-ui-concurrency/runs/audit-14abfee9d7e4442591fbc4b8ee23f41a.
  Diagnostic fixture inherited single-thread-only sqlite://; real worker
  rollback raised sqlite3.ProgrammingError before the actor callback, so its
  safe category was authority_unavailable rather than authentication_failed.
  Prepared a LOCAL file-backed diagnostic DB with check_same_thread=False,
  matching Core configuration and retaining real async/worker execution;
  the Session is used sequentially. No inline-worker double, shared-fixture
  change, weakened category assertion or production code change. Actor case
  now also requires the denial callback actually to have run. Read-only source
  manifest comparison confirms only this diagnostic test file differs from
  the retained 4a94ab9f... snapshot; reuse the nine unchanged passing cases.
  Added explicit owner group audit-remaining (all seven remaining audit files),
  keeping full audit unchanged. Static Python AST, PowerShell syntax and
  handoff whitespace checked only; no tests executed by agent.
  Owner audit-remaining PASSED: 124 passed, no skips, 337 warnings, 28.87s
  pytest / 31.98s process, 2.37s preparation, source
  627ca004cfb23b20d33a9687d889730cce9bd325f0a1e8b671fb99ce1413602d,
  same HEAD/Python/dependencies. Reports retained in
  .runtime/core-ui-concurrency/runs/audit-remaining-92e00567be3b435bb9a34cd9015ba6b8.
  Agent read the retained JUnit/evidence and compared current captured source
  hashes: all match. Reuse the nine unchanged passing lock-order cases above;
  the complete targeted audit now has 133 distinct passes across TWO runs,
  not a new single full audit/CI run. No implementation edits or agent test
  execution followed this pass. The live Raspberry incident is not yet
  rechecked with the prepared Core; no device action is authorized by a pass.
  Owner effects group PASSED: 132 passed, no skips, 1208 warnings, 53.63s
  pytest / 57.43s process, 5.84s preparation; SAME source627ca004..., HEAD,
  Python3.14.4 and dependency digest f91ccaad.... Retained evidence:
  .runtime/core-ui-concurrency/runs/effects-eb09cb2c37794a22ae7b5bb2bf9af1d9.
  Agent read the saved provenance only and updated this handoff; no code edits,
  tests or device actions. Reuse this SDK effect-admission coverage.
  Owner ui group PASSED: 127 passed / 13 skipped, 1384 warnings, 77.41s
  pytest / 83.17s process, 1.99s preparation; SAME source627ca004..., HEAD,
  Python3.14.4 and dependency digest f91ccaad.... Retained evidence:
  .runtime/core-ui-concurrency/runs/ui-cd88404f98a44d8085bd95c3289645c7.
  All 13 relational-runtime skips require the actual root helper boundary;
  they are NOT passes and remain separate privileged isolated acceptance.
  Agent read the saved provenance and updated this handoff only.
  Owner consumers group PASSED: 219 passed / 1 skipped, 1092 warnings,
  231.47s pytest / 238.21s process, 2.53s preparation; SAME source627ca004...,
  HEAD, Python and dependencies. Retained evidence:
  .runtime/core-ui-concurrency/runs/consumers-ba00d7dd177847a69edacd6dc2340d28.
  The public-web skip needs the root driver and distinct actual OS principals;
  combined with ui's 13 skips, 14 privileged cases remain NOT passed.
  All agreed unprivileged groups are now green; reuse their evidence. No code
  edits/tests/service or device actions by agent followed these results.
  Owner approved preparation of the Core-only Raspberry deployment command.
  Prepared ignored .runtime/core-ui-concurrency/deploy.ps1 and prepare-deploy.py:
  reuse the last accepted 3abf44a5... kit (SHAa838903e...) and its exact prebuilt
  frontend, replace ONLY the nine reviewed Core/protocol implementation files,
  and retain owner XML/log/provenance hashes without rerunning tests/builds.
  Read-only baseline comparison found exactly those nine production changes;
  other differences are tests/handoff. Builder requires current source627ca004...
  and the five retained owner runs; the nine lock-order passes are separately
  reused from4a94ab9f..., not the later failing actor-fixture case in that run.
  Normal deploy.ps1 immutable installer/backup/rollback remains in use. This
  kit's controller adds preflight guards for the inspected base/host and existing
  independent pins, refuses any host build/publication, sets agent=null and
  checks unchanged component/instance-host pins after install. No version bump,
  app replacement, permission approval or automatic Start/frame replay. Default
  action only prepares; -Action Deploy requires explicit DEPLOY CORE ONLY plus
  the owner's current-backup acknowledgement. The normal installer WILL restart
  Core/related services; pin preservation is NOT process continuity. Live output
  may pause and must be inspected before any later explicit Start.
  Static Python AST, guarded-controller splice/AST and PowerShell syntax passed;
  agent did not build the kit, run tests, connect to Raspberry or deploy.
  Owner deployed successfully on rasp-3mm, 2026-11-01 14:18:20 host log:
  key40240df179fa2e00bafeff031730b8e0c96eb13d82b22bb34689f780a0eb570b,
  release local-40240df179fa2e00bafeff03, state=succeeded / phase=ready,
  install Core190.926s, validate/extract0.96s. No native-host/Agent update phases.
  Local kit evidence confirms base3abf44a5... and checked source627ca004....
  The controller's success includes its unchanged independent/instance-host pin
  checks and Core readiness; it does NOT prove browser/LCD concurrency acceptance.
  New Core PID was not supplied (installer/helper PIDs are not Core identity).
  Agent did not connect to or mutate the device; owner executed deployment.
  Owner screenshot after deployment shows /monitor loaded (preview14:24:27,
  live frame14:24:21), menus present, status Running / Waiting for the original
  command, with existing command cmd_cd34fb3efec8483697eeccda349e2ca2 and seven
  409 entries (GET and POST) in the browser console. It does not show their
  complete URLs/responses or prove when each console entry occurred, physical
  execution, a permanent stuck frame or an owner Start action. Browser loading
  is an improvement, NOT successful concurrency acceptance. Do not declare the
  original incident fixed or infer a new lock failure from this image alone.
  Owner supplied fresh detail "Application UI code trust is temporarily
  unavailable" and clarified that merely leaving /monitor (and other extensions)
  open produces errors after 10-20s, before Start. A later Start can start output
  while a page update fails. Treat this as a general Core UI incident, not proof
  of a physical-display failure or of a full browser navigation/reload.
  Read-only source review maps this exact detail to the ordinary HTTP operation
  authority boundary. Completion converts such refusals to the separate generic
  unconfirmed result; the supplied detail is therefore an admission refusal.
  It does NOT distinguish key acquisition, current-code policy or a DB failure:
  CoreReviewKeyStore._access also redacts exceptions thrown INSIDE its lease.
  Monitor's mounted timer reads get_state every second; each host.invoke first
  performs fresh ui-host discovery, even when live output is stopped. GET
  ui-host still uses independent trust validation, unlike the operation proof.
  This identifies remaining paths/load, not a demonstrated lock-contention cause.
  No speculative SH/EX change, timeout increase, trust cache, polling suppression,
  frontend/library update or retry was made. Existing passed tests remain prior
  evidence; no tests/builds/imports, SSH or device actions by the agent.
  NEXT: use the ALREADY deployed Settings / Diagnostics operation recorder for
  60s, all supported operations, no instance filter. In a separate tab leave
  /monitor open without Start/Send; after the first fresh failure stop recording
  and export safe records BEFORE expiry clears them. Supply the failed Network
  entry's pathname/operation and Response too, without headers/tokens/HAR or
  resending it. This separates admission/response/completion timing and observes
  concurrent SDK stages without another deployment. Preserve the existing pending
  identity; do not repeat Start, reapprove rights or replay a physical command.
  No further product patch is justified solely by the generic detail.
  Owner supplied Downloads/3mm-operation-records (2).ndjson: session61b2197b...
  contains only its header, accepted151 / records0 / buffer_bytes0, inactive
  with remaining_seconds0 and no dropped events. The recording expired before
  export; existing _expire clears records even after Stop. No failure span or
  cause can be inferred from this empty export. Revised capture: choose 5min,
  reproduce by leaving the page open 20-30s WITHOUT Start/Send, export while the
  recorder is still active, then Stop. No code/tests/device changes for this step.
  Owner objects to repeating the manual capture after two unsuccessful attempts.
  Confirmed diagnostic COVERAGE gap separately from the expired export: GET
  ui-host runs outside invocation recording, and key _access redacts original
  DB/caller exceptions before the relay sees them. Prepared a bounded diagnostic
  correction, NOT a claimed fix of the installed 409: discovery has its own
  application.ui.discover trace; request-local ContextVar metadata joins failure
  detail to the existing invocation trace. Failure-only code preparation / key
  acquisition / DB snapshot / UI trust / policy records are emitted BEFORE
  redaction. Fixed closed reasons distinguish key contention, unavailable key,
  SQLite BUSY/LOCKED (numeric driver code only), other DB failure and unavailable
  code. The acquired callback prevents caller errors being mislabelled as failed
  key acquisition. Existing public errors, key/DB ordering, timeouts, permissions,
  recorder TTL/budgets, dispatch phases and no-replay behavior remain unchanged.
  No logging of SQL, exceptions, tokens, bodies or new persistent spool. GET
  catalogue snapshot behavior itself is unchanged; no contention cause is proved.
  Added real protected-key GET/POST denial and original DB-cause regressions,
  caller-versus-acquisition distinction and inactive/broken recorder checks.
  Owner runner adds diagnostic-gaps with direct key/UI/recorder consumers.
  Ignored capture.py logs in only to diagnostics, starts one 300s session and
  automatically saves exports at15/30/45s before stopping its inspected session;
  no app invocation, Start/frame, trust/grant or service operation. Existing
  active recording is not replaced. Credentials are prompted, kept in memory,
  not saved; redirects/proxies and mutation retries are disabled. Saved files
  remain under .runtime/core-ui-concurrency/captures/<unique-id>.
  Static AST for10 files, PowerShell parser and scoped diff whitespace passed.
  No imports/test/build, API login, SSH, deployment or device operation by agent.
  Owner must run diagnostic-gaps before any deployment of these NEW changes;
  source627ca004... results do not test this diagnostic correction. The timed
  capture can run against the current installed Core, but that Core will still
  lack the newly prepared GET/detail records until explicitly deployed later.
  Owner now requests a review/design for more useful general 409 diagnostics.
  Read-only audit: backend.main has no common 409-to-record boundary or returned
  trace ID; handled HTTPException responses do not reach its generic exception
  catch. Application host intentionally reduces failed POSTs to unconfirmed,
  while the diagnostics UI shows opt-in spans without an HTTP-request link.
  The same 409 also represents expected revision/lifecycle/idempotency conflicts;
  do not classify every conflict as a crash, a lost grant or a retry instruction.
  PROPOSED next bounded slice (not implemented): server-generated HTTP trace
  header, shared with policy/relay diagnostics; a small administrator-only
  recent-failure view with route TEMPLATE, method/status, fixed reason/stage,
  elapsed time and honest dispatch phase, no URL query/body/actor credentials;
  retain the existing detail/public access boundary. Catch final response status
  at the common HTTP boundary, while retaining original typed causes at their
  source. Detailed tracing remains explicit and bounded; Stop/expiry UX must
  distinguish recording lifetime from short export retention or export before
  expiry. No automatic retry, rights change or effect replay from error UI.
  Asked owner whether minimal recent failures may be always-on in memory,
  proposed <=100 records / <=15min, coalescing/rate/byte bounds, no disk or remote
  collector. This changes the previously opt-in-only diagnostic posture and
  remains a design choice, not authorization to deploy or silently enable it.
  Reuse existing diagnostics/settings/admin controls, not a new diagnostics
  service. First scope should be HTTP409 and server failures plus UI/authority
  cause correlation; extending all SDK/Agent/session errors is separate work.
  No new implementation, tests/build or device action during this design audit.
  Owner explicitly APPROVED the limited always-on in-memory register. Prepared
  implementation (not deployed): HttpFailureMiddleware observes handled HTTP409
  and 5xx responses and generates X-3mm-Trace-Id, ignoring incoming IDs. Core
  CORS exposes this opaque reference. Relay and pre-relay UI discovery now share
  that HTTP trace; wire request/idempotency identities remain independent.
  Original closed authority causes feed request-local metadata before masking,
  even with detailed recording disabled. Dispatch observation advances only:
  unknown -> not_dispatched -> execution_unconfirmed -> completed. The real
  send marks uncertainty BEFORE its first write; a later refusal cannot undo it.
  Generic endpoints remain unknown, not falsely unsent. No resend/permission
  decision comes from metadata. Existing public error bodies are unchanged.
  RecentHttpFailures stores <=100 entries / <=128KiB serialized metadata / <=900s
  logical retention, max10 writes/s, max6 closed cause details/request. Locks are
  nonblocking; overload/expiry/eviction are explicit counters. No disk, DB writes,
  worker/helper probe, background service, bodies, query strings, raw URLs,
  exception/SQL text, credentials or actor identity. Only router-owned templates
  are accepted; unmatched routes use a fixed placeholder. Memory clears on Core
  restart. This is bounded process-local history, not a complete audit/uptime claim.
  Existing admin dependency protects GET diagnostics/failures and failures/export;
  stale/revoked/non-admin access stays denied. Busy export returns503 instead of
  a misleading empty success. New Settings component loads this view without
  starting debug, groups repeats while preserving every retained trace, displays
  unknown/unconfirmed phases and exports the bounded snapshot. It does not poll
  continuously or offer a business retry. Expired opt-in sessions cannot erase
  the separate recent ring. EN/BG15 new keys match; no language-package/version
  bump/build/activation was requested or performed (new BG source keys only).
  Prepared tests cover bounds/expiry/pressure/privacy, real handled status and
  server-generated header, cross-thread original cause, actual relay first-write
  uncertainty, admin denial/revocation, inactive diagnostic capture and UI
  grouping/filter/export/stale/unmount behavior. diagnostic-gaps now selects10
  files including Core startup; new frontend unit checks are separate. Static
  Python AST10 files, SFC/TS syntax4 files, JSON/key parity and PowerShell parser
  passed. These are NOT test/type-check/build or browser visual evidence.
  Agent did not execute tests, import product modules, log in, deploy or touch
  device state; no commit/push/version/publication. Owner next runs the updated
  backend group and the two frontend component tests, type-check and build.
  No claim that the underlying installed409 is fixed. The previous Core-only
  deploy wrapper pins source627ca004... and must NOT be reused for this new
  backend/frontend candidate. A new reviewed deployment follows fresh evidence
  and separate owner instruction, preserving independent work/component pins.
  Owner checks PASSED, 2026-11-01: diagnostic-gaps205 passed /2 skipped,
  821 warnings, 53.17s pytest /58.98s process, preparation2.37s. Source
  8f5703619460dd05cfb5b3a923ef6747c0d237c0ab9e9f7cce2652ca71b7572e,
  HEAD061e7ebe..., LinuxPython3.14.4, dependency f91ccaad... reused.
  Retained run: .runtime/core-ui-concurrency/runs/
  diagnostic-gaps-0e0117bd20784e89ad802d5fc2d4752f. Agent read JUnit:
  207 cases,205 passes,2 skips, no failures. Read-only archive manifest/hash
  comparison: all1291 captured inputs still match current files (0 mismatches)
  before this handoff-only update. Reuse this result; no repeated test run.
  Skips are NOT passes: foreign-UID check needs disposable root POSIX acceptance;
  non-POSIX-refusal case is inapplicable in this Linux run. Earlier privileged
  release obligations are not closed by this targeted group.
  Owner frontend:12 tests /2 files passed (Workspace6 +RecentHttpFailures6),
  12.51s, Vitest3.2.4; Vue type-check and Vite6.4.1 build passed. Supplied local
  log starts19:28:42. Existing dist index/assets match reported main-CUqh5PR2.js
  and Settings-DCNZ8AdH.js. Python snapshot intentionally contains no main
  frontend sources; do not claim it fingerprints the frontend run. No agent
  implementation edits followed the owner checks, only this handoff.
  Owner subsequently explicitly requested deployment. Prepared ignored owner
  launcher .runtime/core-ui-concurrency/deploy-failures.ps1 (Prepare default;
  Deploy / Status / Logs explicit) and prepare-failures-deploy.py. No rollout
  was executed by the agent. The builder reuses the exact205/2 backend evidence,
  checks all1291 frozen inputs, and binds249 current frontend inputs plus35
  owner-built outputs. Frontend evidence is honestly owner-reported plus a
  POST-success capture, not a fabricated pre-run/machine test receipt. Source
  identity2b12f596... and output identity7d3f2b0d... are pinned; any drift stops.
  Incremental payload: eight existing Core/protocol diagnostic files, the new
  http_failures module and prebuilt frontend. Other payload bytes are retained
  from the accepted local40240df1... kit. Its existing immutable installer,
  backup/rollback and component-pin guards are reused; only the required baseline
  deployment key changes. Agent/Runtime/native/application hosts are not updated.
  Bundled BG1.0.2 bytes stay unchanged: new BG translations await a separately
  versioned language package; EN fallback remains available. No version bump,
  grant change, application Start/frame, device reboot or publication. Deployment
  DOES restart Core/related services and may pause the live LCD. The launcher
  asks for a current backup and DEPLOY DIAGNOSTICS before transfer; an uncertain
  rollout must be observed through Status/Logs, not replayed. Static Python AST,
  guarded-controller AST, PowerShell parser, frozen source/frontend/base hash
  comparisons passed. No tests/builds/product imports or device actions by agent.
  Owner supplied Downloads/3mm-operation-records (4).ndjson (401 bytes): only
  session5c952bcb... header, active=false, remaining_seconds=0, records=0,
  accepted184, no drops. No failure span/cause is present. This is the OLD opt-in
  session export, not the independent recent-HTTP-failures snapshot. Its empty
  expired buffer does not prove whether the new ring contains409s or whether
  deployment completed. Request Settings/Diagnostics/Recent HTTP failures ->
  Refresh failures -> Export recent failures (3mm-recent-http-failures.json);
  no new debug session, application Start or frame replay. No tests/device action.
  Owner then supplied Downloads/3mm-recent-http-failures.json (5691 bytes).
  The new ring is ready with11 HTTP409 records and zero drops/expiry/evictions:
  TEN review_key_busy at authority.key_acquire (eight operation admissions,
  one ui-host discovery, one operation completion), plus one earlier
  application.dispatch/transport_unavailable. Key-contention burst spans
  17:58:54-17:59:21 UTC; total HTTP durations464.715-1081.483ms are NOT measured
  lock-hold times. Ten records are not_dispatched; the completion record
  invoke_294fb268267545aaa03aa6be47534db1 is execution_unconfirmed and MUST NOT
  be replayed. Earlier transport refusal is17:51:33 UTC and is a distinct cause.
  This proves the observed refusal boundary is review-key contention, not a
  missing-review inference. It does not identify which owner/process holds the
  lock or exclude a slow DB inside that owner's lease. Read-only source audit:
  ordinary HTTP UI boundaries already use SH; several DB-enforced read-only
  consumers still use EX (manager._inspect_reviewable, command discovery and
  resource discovery). SDK effect admission also uses EX for durable writes.
  Those are concrete contention candidates, NOT proof of the captured holder.
  Next proposed scoped fix: review shared verification versus exclusive key
  replacement and lease duration/transaction ownership, with deterministic
  real-lock concurrent reader/writer/revocation regressions. Do not merely
  raise250ms, cache authority, weaken checks or add effect retries. No code,
  tests, installed services/grants or physical output changed by this audit.
  Owner explicitly approved the next lock correction ("хайде"). Prepared a
  bounded read-only slice: manager._inspect_reviewable, selected-command
  discovery and BOTH pre-/post-provider resource snapshots now use the existing
  read_locked SH adapter instead of locked EX. The adapter forbids new seals/
  encrypted receipts and the DB remains query_only. No key-store primitive,
  timeout, SDK effect admission, mutation/rotation/recovery/revocation lock,
  policy, transport or frontend behavior was changed. Provider IPC remains
  outside key/DB leases; completion uses a NEW current snapshot, not cached rights.
  Added test_application_authority_read_leases.py:22 prepared parameter cases,
  actual POSIX locks and file-backed SQLite, one current compiled-UI/native
  snapshot held while another thread completes each read view, no DB/key/command
  writes, EX exclusion, fresh grant/native/key/recovery refusal, and independent
  EX/SQL availability plus revocation during provider observation. Only provider
  readiness is doubled; no Runtime/device/physical effect. These checks have
  NOT been executed or claimed as a pre-fix failure/post-fix pass by the agent.
  Owner runner adds key-readers (new file) and key-readers-consumers (10 direct
  key/status/discovery/optional/composition/session/UI/ordering consumers), with
  durable console/JUnit/evidence and stop-first support. First run key-readers;
  only on success run key-readers-consumers. No frontend test/build is needed
  for this Python-only slice. AST5files, PowerShell parser, selected paths and
  scoped whitespace passed; exact diff against owner-tested8f570361... shows
  ONLY four EX->SH substitutions plus comments in three production files.
  Previous green reports are baseline evidence, not tests of these later edits.
  No agent test/build/import, SSH, service/device/grant/frame, deployment,
  commit, version or publication action. The old deployment builders pin prior
  content and must not be reused for this candidate. This removes demonstrated
  unnecessary reader exclusion, NOT proof of the installed lock holder or a fix
  of the separate transport_unavailable. Genuine writes still require EX and
  can deny concurrent reads; physical acceptance of the409 incident remains
  pending after owner checks and a separately requested reviewed deployment.
  Owner key-readers stopped at its FIRST case (status):1 failed,19warnings,
  7.96s pytest /10.5s process, prep6.08s; source12d805cdc62bf8c511c8d48cd547bca14d64396910e08f0c01b22c7637d00e7a,
  same HEAD/dependencies/LinuxPython3.14.4. Saved run key-readers-
  05f25cb48b9a4623ad6ab4b65e1b2b06. Consumers did NOT run. Exact assertion
  error is in the NEW test, not proof of an absent real snapshot: the DB-enforced
  _read_snapshot starts BEGIN on its Connection before yielding a lazily joined
  ORM Session; Session.in_transaction() is still false before its first query.
  Corrected only that test to assert the bound SQLAlchemy Connection AND native
  sqlite3 transaction plus query_only=ON before composition, and the ORM
  transaction after actual composition. Existing SH overlap, EX refusal,
  no-writes, key-byte and current-authority checks stay intact. Three production
  files are unchanged. Agent AST/whitespace only; owner repeats key-readers then
  consumers on success. No test execution or device/deployment action by agent.
  Owner rerun: key-readers22 PASSED (300warnings,21.74s pytest /23.7s process,
  prep1.82s), retained key-readers-69eccfca0f6b4e62979852e9ff184d9b. Consumers
  then stopped:102 passed /2 skipped /1 failed (540warnings,28.98s pytest /
  31.99s process,prep0.92s), retained key-readers-consumers-
  b59683688b7d40dfa1a08df9a62b2ae2. SAME source7a98a6f754e490e746583a5d515ee6706f64e0ceb6fbc78f438603d20c969e2f,
  HEAD/dependencies/LinuxPython unchanged. Agent read JUnit: keys52pass/2skip,
  management35pass, command discovery15pass. Skips remain the real foreign-UID
  root boundary and inapplicable non-POSIX refusal; neither is a pass.
  Failure is the EXISTING resource-discovery test assuming unknown connector
  readiness while probing host-default /run/3mm-connectors/worker.sock and
  account3mm-connectors. A missing account maps to unknown; an existing account
  with a missing worker maps correctly to unavailable. Its actual result was
  unavailable; changing read leases must not force unknown or accept either.
  Fixed ONLY that test: explicit absent socket in its disposable fixture dir,
  actual current UID account, exact unavailable/provider_unavailable assertion.
  Other access/read-only/revocation assertions and signed SDK/Runtime are intact.
  Full consumer group now also includes existing real provider-probe tests
  (trusted/mismatched connector principal, event/task metadata without work).
  Added owner key-readers-remaining: corrected resource test/module + those
  provider checks + untouched later consumers,8 files. Reuse22 +102 earlier
  passes; no repeated first three modules. Read-only SHA comparison against all
  captured7a98a6f7... files shows ONLY test_application_resource_discovery.py
  changed; production/new22case test and earlier fixtures are unchanged.
  Static AST2files, selected paths, PowerShell parser and whitespace passed;
  no agent tests/imports/deployment. Owner next runs key-readers-remaining.
  Owner key-readers-remaining PASSED:147passed /0skipped,1761warnings,
  96.31s pytest /102.88s process,prep4.4s; retained key-readers-remaining-
  a642d772d1854362a52620c196c84113. Source
  c9f42527e812428fbf217c8ec9fae2fcbeeb9d9492eb46f59e19a52bbe88a814,
  same HEAD061e7ebe..., LinuxPython3.14.4 and dependencyf91ccaad.... Agent
  verified all three saved JUnit/provenance files and1292 snapshot file hashes:
  current source matches exactly. Comparing7a98a6f7... to c9f42527... changes
  ONLY the corrected resource-discovery test; production, new22case test and
  earlier successful fixtures are unchanged. Composite targeted evidence is
  22 +102 +147 passed, with2 prior skips NOT passed; the old fixture failure
  is superseded by its fresh147-case group, not counted as a success itself.
  No tests repeated, product imports, source implementation edits or device
  actions by agent after these owner results; only this handoff changed.
  Next, if owner requests deployment: prepare a NEW evidence-bound Core-only
  candidate for the three production files/four EX->SH sites, preserving the
  already deployed diagnostic frontend and independent Agent/Runtime/hosts/
  grants. Do not reuse source-pinned older deploy wrappers. No authorization
  for another rollout was given with this test result; no deployment/commit/
  publication performed. Then observe the409 incident without Start/frame replay;
  green local checks are not installed Raspberry acceptance or full release CI.
  Owner then explicitly requested the next step ("хайде"). Prepared ignored
  prepare-key-readers-deploy.py and deploy-key-readers.ps1, Prepare default /
  Deploy explicit / Status / Logs, for owner-run Raspberry rollout. The target
  receipt points to diagnostic kit3960d7d00ad42a3d726485381379c9e79deb243c258eb9897e480945c7d675ef;
  a receipt is an ATTEMPT, not proof of installed success. The reused guarded
  controller requires that actual installed base (or this exact candidate)
  before dispatch and before installation, preserving independent component pins.
  Builder pins c9f42527... all1292 files and the three hashed owner reports;
  reuses only completed102 cases/2skips from the earlier stopped run, verifies
  the sole snapshot difference is the corrected resource test and records the
  superseded failure honestly. No tests/builds are run. Only the three reviewed
  Core files replace baseline payload bytes; diagnostic frontend, Agent,
  Runtime, connector/public/session/instance hosts, dependencies and bundled
  BG1.0.2 remain baseline bytes/pins. Unversioned BG source is still deferred.
  Normal immutable installer/backups/rollback are reused. Core/related services
  restart and live LCD may pause; no device reboot, rights approval or frame
  replay. Wrapper asks for current backup and DEPLOY CORE READERS before transfer;
  inspect Status/Logs instead of repeating an uncertain rollout. Static builder
  and guarded-controller AST, PowerShell parser, baseline file/kit hashes and
  checked-source/three-file delta passed. Agent did NOT run the builder/tests,
  import product modules, transfer, log in or act on the device. No commit,
  version or publication change. Owner receives the new explicit Deploy command.
  Owner reports409s now occur much less often and supplied Downloads/
  3mm-recent-http-failures (1).json (744bytes). New snapshot has ONE HTTP409,
  zero drops/eviction/expiry: invoke_50a5c1977b7341e7b62753d5428edd1d,
  2026-11-01T19:33:15.042927Z, POST operations route template,
  authority.key_acquire/review_key_busy with application.completion/
  authority_unavailable, phase execution_unconfirmed, retryable=false.
  Total HTTP878.46ms is not measured lock-hold time. No admission or ui-host
  refusal is retained in this snapshot; no equal observation window/request
  denominator exists to calculate a reduction rate versus the previous11.
  This supports owner-reported improvement, NOT closure: application execution
  may have occurred before final authority validation failed, so do not replay.
  Remaining known EX users include durable SDK effect admission; the record
  does NOT identify the holder or prove that a particular SDK write caused it.
  Next proposed bounded audit is writer lease duration / SQL ownership versus
  HTTP completion, preserving revocation and unknown-outcome safety. No timeout
  increase, write-lock weakening, auto-retry, production/test change or device
  action performed in response to this result. Final rollout JSON was not
  supplied here; do not claim its exact installed key from the HTTP export alone.
  Owner asks why live Start is disabled; screenshot shows blocked/
  outcome_unconfirmed with an original pending frame (20:22:45), and reviewed
  display ready. Read-only sibling-source check: LiveDisplay.canStart requires
  !state.pending, so this old durable intent disables BOTH acknowledgement and
  Start even with no console errors. Core deployment does not clear app journals.
  LiveDisplay.check invokes display_live_check without a new effect identity;
  service LiveDisplay.check/_check_pending performs ONLY original command_lookup,
  never submit. Proven succeeded/failed/never-claimed-expired completion clears
  pending; blocked mode becomes stopped (failed stays blocked). Unknown/not_found
  remains fenced; no replay or blind journal reset is authorized. Next owner
  clicks Read current frame outcome; if still blocked, inspect that operation's
  response. No claim this old pending frame caused the later19:33 HTTP409.
  No sibling edits, tests, installed/device/physical actions by agent.
  Owner clicked Read current frame outcome and reports no visible change.
  Further sibling READ-ONLY audit confirms a recovery/feedback gap, not a new
  proven Core error: check() returns unchanged status when step_lock is busy;
  not_found/nonterminal/mismatched lookup and ANY caught exception collapse to
  the same blocked/outcome_unconfirmed. LiveDisplay.vue awaits host.invoke but
  discards its result and only requests a state refresh. Thus a successful
  check can look like a no-op; the supplied symptom alone does not distinguish
  not_found, denied/failed lookup, a busy check, or another HTTP refusal.
  Do not claim a specific actual response or clear the old pending intent on
  this evidence. Proposed next app scope is visible safe lookup/check feedback
  and a verified original-outcome recovery path, no blind Start/replay/delete.
  No sibling write/version/package change is authorized by this symptom report
  and none performed; no installed/API login/device action or tests.
  Actual browser visual and installed409 root-cause acceptance remain pending.
  No full CI or release claim.
  Privileged isolated checks plus normal integration/
  release gates remain before publication; targeted passes are not full CI.
  No claim that the separate UI catalog/menu read path is fully resolved.

- **Accepted transport/orphan recovery baseline: 0.5.2, not live-mode proof.**
  Owner corrected premature stage closure: one static frame is not the desired
  continuously configured display. The following notes describe 0.5.2 only.
  Owner approved that app-only fix and version 0.5.2. Six sibling application
  files changed: display service, DisplayOutput.vue, builder, backend/frontend
  display tests and README. No Core/SDK/runtime/Agent change or new migration;
  schema remains 0005 and Core VERSION remains 0.3.3. On an absent local row,
  display_lookup now checks Core with the original actor-scoped SDK request ID.
  Only an exact Core not_found sets optional recovery_allowed=true. Denial,
  malformed/unknown/lost lookup and found-without-local-frame evidence keep
  recovery blocked; a found command's identity is retained without claiming
  physical execution. Existing local uncertain rows remain lookup-only.
  UI recovery is two explicit steps: Prepare original request (same ID), then
  re-acknowledge and Continue original request once. It retains browser storage
  and the ORIGINAL idempotency key, never unlocks/generates a replacement ID.
  Existing send() rechecks Core/journal before submit; late original invocations
  therefore meet the same durable deduplication identity. No cancel tombstone,
  global privacy fence or erasure change was added. Optional result flag allows
  old receipts to remain unchanged. Same-valued geometry object refresh no
  longer clears the checkbox; real revision/screen/profile changes still do.
  New checks cover negative/unknown/revoked Core lookup, actor scoping, no SQL
  transaction over lookup, original local/Core arrival races, no auto resend,
  same-ID recovery, fresh acknowledgement, stale lookup evidence and geometry/
  permission changes. Owner retest exit_code=0, snapshot
  C:/Users/LAZ-DELL/AppData/Local/Temp/3mm-crypto-display-524a38160b964476b336b25789e9eae3;
  no backend test total supplied. The existing runner also checks the actual
  Core package consumer. Owner frontend exit_code=0, 29 tests / 2 files,
  snapshot C:/Users/LAZ-DELL/AppData/Local/Temp/3mm-crypto-display-8e1a4c3bdcce471cb75411aba4a42080;
  existing frontend runner completed Vite build, Vue type-check and UI tests.
  Agent read-only SHA-256 comparison confirms all 17 captured source inputs in
  EACH owner snapshot match current application files, with zero mismatches.
  No tests were repeated. Owner then reports succeeded/executed=true for the
  ORIGINAL request 1aa7e8408c754c6fc3c0fb77783eed9f, command
  cmd_fbbd1a726661435180b19cf09f25d5fe, exact device
  dev_65dba727720a40539c7d68cb70fef671, backlight=true, lines
  "01.11.2026 07:50" and "BTC 69,692.04   " (both 16 characters).
  Owner explicitly confirms both rows are visible on the real LCD ("виждат се").
  This closes the bounded 16x2 delivery/orphan-request recovery acceptance:
  software checks green, Agent execution confirmed and human visual confirmation.
  It does not claim automated optical readback, physical acceptance of other
  geometries/controllers or an automatic refresh/rotation loop on the LCD.
  Transport acceptance is retained, not reopened. Owner explicitly says the
  overall stage is not complete because the configured clock/currency is not
  being continuously presented; next scope is recorded above. Do not repeat
  the accepted one-frame test or unchanged checks as proof of live operation.
  Read-only local inspection now finds owner-built dist/3mm-crypto-monitor-0.5.2.zip,
  32157 bytes, SHA-256 2834a84f925bfa9f8840049be11a602045221e9eab0c5f096c56d0dd441152e7.
  Exact installed package/UI/grant has not been separately supplied; do not infer
  it solely from command success. Do not replay frame, repeat unchanged Core
  checks/deployment, reinstall or overwrite the old 0.5.1 ZIP.
  Agent performed only AST, Vue/script/template and TS syntax preparation; no
  tests, type-check, package/frontend build, login, deployment, grants, physical
  writes, commit or push. Original notes/evidence follow.

  Owner approved replacing the undeployed fixed 16/20 variant with a common
  contract, not another per-size Core/app patch. `display.character` 2.0 has ONE
  scalar frame schema: display_id, profile_sha256, newline-delimited text,
  backlight. All profiles share it. Exact geometry is singleton provider data in
  state_schema; complete contract/package/profile identities still change and
  M20 still requires fresh approval. No schema-containment shortcut was added.
  Existing generic command discovery now projects the bounded selected contract
  through SDK; denied/revoked observations still expose no resource candidates.
  This is declaration data, not device state/I2C probing or an execution permit.
  Generic profile helper has wire budgets 80 columns / 4 rows, no 16/20 list.
  Native topology checks live in the HD44780 driver: standard two-row banks up
  to 40 columns, or split-bank four-row panels up to 20; unknown drivers/mappings
  fail before I/O. Native/frame service handles variable row lists. New profile
  schema 2 and contract 2.0 require new packages; old reviewed ZIPs remain inert.
  Crypto Monitor stays 0.5.1 (Core VERSION unchanged), ONE display_frame binding,
  no controller/address/profile-hash/size catalog in the application frame path. SDK
  discovery supplies physical geometry; send compares a fresh observation to the
  user's expected_geometry after committing its original-request journal. Old
  outcomes remain historical, never reformatted/resubmitted. Migration 0005 adds
  preview_columns/preview_rows only and preserves settings/quotes/receipts.
  Physical sizing is NOT changed by preview fields. The old inert address field
  is hidden (stored configuration remains untouched). Saved physical preview
  adapts after access refresh; two-currency cells handle odd widths too. Current
  saved screens retain two templates; additional physical rows are blank and a
  one-row preview warns about omitted content (future layout work is app-only).
  No tests/build/install/deploy/SSH/I2C/consent/Git mutation was run by the agent.
  Earlier 142-pass and owner-reported app/frontend passes tested the SUPERSEDED
  fixed-size candidate, not these changes. Updated .runtime/cap14-geometry/test.ps1
  core selection covers protocol, Agent, sealed M20 profile-change denial,
  SDK/wire discovery/revocation/rebinding/recovery and Agent/native-host artifact
  consumers. Owner core run passed: 276 tests, 614 warnings in 55.39s, isolated
  Linux Python 3.14.4, /tmp/3mm-lab-eg52mln4/results.xml, source SHA-256
  e3248cc957db9c9ce415100e883ccb215fc0b238ca61e786b066bd8263bf395f,
  dependency SHA-256 f91ccaad806c25f0057f8f802db6ed3ad6733a89fd44d3bd934d14d1b8c8c5f7.
  Owner frontend result exit_code=0, snapshot
  C:/Users/LAZ-DELL/AppData/Local/Temp/3mm-crypto-display-1f95db8459944552bac10de905c6f1d4;
  no test totals supplied. Deployment/physical_write not_requested. Owner then
  explicitly confirms ALL groups passed, including application; application totals
  and snapshot ID were not supplied. No source change since that confirmation.
  Owner built two inert packages with existing builders: native PCF8574T
  16x2 / I2C-1 / 0x27 profile schema 2 / command contract 2.0 at
  .runtime/cap14-geometry/character-display-pcf8574-v2-16x2.zip and Crypto Monitor
  .runtime/cap14-geometry/3mm-crypto-monitor-0.5.1.zip. Both builders refuse to
  replace different existing bytes. Read-only inspection confirmed owner hashes,
  16x2 / bus1 / address39 / profile schema2 and both command contracts=2.0:
  provider ZIP 6637 bytes, SHA-256
  edaaef545e5efeca9ff9a841f9f3c4f9b0140362704055d16b126cad0849b28d;
  profile SHA-256 ac1937994d21ac34d749794d2b2e05e72e3f7ab6b2143d1b76a58906e13504ac;
  provider module org.3mm.character-display.ac1937994d21ac34d749794d2b2e05e72e3f7ab6b2143d1b76a58906e13504ac.
  Crypto ZIP 31222 bytes, SHA-256
  6dfe8552241da559c44d0450844159f7b48c187b26dfe84661b113107c4d7e1c,
  one display_frame binding / 2.0. No package activated or device accessed.
  Owner platform deployment succeeded on rasp-3mm:
  key 3abf44a55c12c52b777c5af213bc33b3d5088b40b2b52535a957149bcc678a40,
  release local-3abf44a55c12c52b777c5af2; state=succeeded, phase=ready;
  Agent build 6b63b8272aac54be0b01ad106acd9f2a6991eeb6aeb399fdbfef4b6ddc0499b7,
  ready response core_pid=90155. Log includes native-host preparation/default
  publication and explicit Agent update. This does not prove existing Crypto
  host pin moved or new display/app ZIPs were installed. Owner read-only inspection
  confirms Crypto instance 46e92c9bdffd26e204800468, app version 0.5.0,
  current host 584e849cf07e7087c5794db46de95b32b761a09b0949b5da4ab19d167176fd9e,
  new default 666ec3dacc28a56161a469a14d0190a27fdd22dd77c43739f1bb6c1ca2b01ef9.
  Owner operates from Windows PowerShell/phone: use a single PowerShell wrapper,
  not Bash heredocs requiring manual SSH-shell switching. Prepared
  .runtime/cap14-geometry/update-crypto-host.ps1 (default Inspect, explicit Update
  with typed confirmation). Before existing component CLI update it checks exact
  Core release, module/instance/version, old/new/default host pins, immutable
  artifact/build and absence of pending host journal. Computes SHA-256 and lets
  the existing artifact validator/transactional updater check it. Only selected
  host restarts; Core/platform continuity and host health use existing updater.
  Already-selected candidate only probes, never repeats update. Unknown result:
  Inspect, not blind retry. PS/embedded-Python syntax checked, not executed; no
  runtime test/device mutation performed by agent. Owner then ran -Action Update:
  status=ready, instance 46e92c9bdffd26e204800468 now selects host
  666ec3dacc28a56161a469a14d0190a27fdd22dd77c43739f1bb6c1ca2b01ef9;
  application_metadata_unchanged=true, new_host_selected=true, core_pid=90155.
  Application remains 0.5.0. Owner screenshot 2026-11-01 confirms new provider
  profile ac193799... and package edaaef54... with 16 columns / 2 rows,
  schema_version=2, bus1/address39 and reported installation=succeeded/Enabled.
  This confirms installation, not a physical frame or capability availability.
  Keep old declared-20x2 provider disabled. Owner reports app activation and a
  frame attempt ending with HTTP 409. Screenshot shows new provider/16x2
  discovery, retained browser request ID, no outcome, and a generic error in
  the settings editor. Exact activated version/authority and failing operation
  response have not been supplied. Do not assume 409 means missing rights:
  Core maps application gateway failures to 409 too, and the editor error is
  separate from the display panel's error. NEXT: inspect the existing failing
  request URL/operation and Response JSON; if absent, use display_lookup only
  for the retained ID. Never clear pending identity, resend, replay a command,
  reapprove rights or change device state merely to diagnose this response.
  Owner identifies failing operation as display_observe, response HTTP 409:
  {"detail":"Application result is unconfirmed; do not replay"}. Local source
  maps several relay/handoff/response/completion-fence failures to this same
  message; it does NOT establish an M20 refusal, a timeout or LCD execution.
  Owner exported diagnostics. First file has zero events; second Downloads/
  3mm-operation-records (1).ndjson (10738 bytes), session e44eaa48... has 31 events,
  dropped counters all zero: ten complete ok admission/dispatch/response traces
  and one admission-only failure, trace invoke_968ee2e60b424e2ea4d2a3185dfb8162,
  duration 487.152 ms, timestamp 1793508950.505101 = 2026-11-01 04:55:50.505 UTC
  (06:55:50.505 Sofia). It records generic reason operation_failed, not an
  exception type or concrete operation ID, so cannot yet correlate this failure
  conclusively with display_observe/its earlier HTTP text. Successful responses
  take 251-1289 ms; this recording contains no failed response span. Read-only
  inspection of the exact deployed local-3abf44... core.tar.gz confirms relay
  source matches the inspected stage structure. Owner journal for that window
  now correlates the admission failure with get_state HTTP 409 at 04:55:50;
  display_observe from the same current client returns HTTP 200 at 04:55:51.
  Current client 192.168.1.59 uses exact 0.5.1 artifact 6dfe8552... / built UI
  64b72a2b... and receives ui-host/access 200. A different client 192.168.1.62
  repeatedly polls ui-host for old 0.5.0 artifact 8fb6acc7... / built UI ae66620f...;
  those stale-UI 409s are separate, expected package fences, not display denial.
  No underlying exception appears in journal. Read-only inspection of the exact
  0.5.1 ZIP confirms Monitor.vue polls get_state every 1000 ms; its reading flag
  only guards other read() calls. DisplayOutput.vue independently dispatches
  observe/send/lookup under its own busy flag, so they can overlap polling.
  Host metadata exposes one active relational invocation and Core explicitly
  refuses preparing another while it is active (application_relational.py).
  Potential UI admission contention was identified statically, but the underlying
  exception and causal link were not proved. Owner then reports Ctrl+F5 on
  /monitor resolves the problem. Treat this incident as resolved by page refresh;
  do NOT implement the proposed invocation gate, bump versions, redeploy or
  reopen the incident without recurrence/new evidence. Hard refresh resolving
  it does not prove which cache/state mechanism caused every observed 409.
  NEXT: confirm original frame outcome and visible physical 16x2 output before
  accepting new-profile/app physical delivery. Preserve any pending display
  request and resolve its original lookup; do not create a replacement send.
  Owner clarifies nothing new appears physically and checkbox/Send are disabled.
  Screenshot shows Reviewed display is ready, native profile ac193799..., 16x2,
  and retained request ID 1aa7e8408c754c6fc3c0fb77783eed9f without an outcome.
  DisplayOutput.vue explicitly disables checkbox/send while requestId exists;
  this is the known duplicate-prevention gate, not evidence of hardware failure.
  Owner Read existing outcome returns not_found, command_id/target_device_id=null,
  lines=[], backlight=false, executed=false for that exact retained request ID.
  Source confirms DisplayOutput.lookup returns this immediately when the current
  actor's display_requests row is absent; NO SDK command_lookup occurs on that
  branch. Therefore this is missing app-local evidence, NOT verified Core absence
  or permission to replay. UI canStartAnother excludes not_found, so the browser
  request ID locks checkbox/send indefinitely: a diagnosed app recovery UX gap.
  Owner approved preparing 0.5.2. The implemented plan above keeps the ORIGINAL
  request ID rather than cancelling/clearing it and releasing a replacement ID;
  a negative lookup alone never permits two independent physical requests.
  No device/grant change, restart, frame or cleared request identity occurred.
  Do not repeat the host update/Core rollout, approve grants or send a frame.
  No physical acceptance follows from these checks. Do not repeat unchanged green
  core/frontend groups, build/deploy or write a frame on the owner's behalf.
  Static preparation passed: Python AST (25 files), Vue/TS syntax (2 components
  and 2 test sources), PowerShell parser, scoped git diff --check. This is NOT
  runtime/type-check/build evidence. Packages were built by owner, not approved.
  Before device delivery, account for independently pinned Runtime/application
  host/Agent artifacts; a Core-only update does not update those consumers.
  Standard local deploy publishes the native host DEFAULT for new instances and
  updates Agent only with explicit WithAgent. The separately inspected Crypto
  instance has now been explicitly updated; other application pins are unchanged
  by this operation. Provider/profile consent,
  app package trust and M20 resource review remain separate owner actions. No
  enablement/reboot/scan or physical write is needed for these inert builds.

- **CAP14 geometry architecture review; do not deploy the fixed-size candidate,
  2026-10-31.** Owner reports application and frontend groups also passed (no
  detailed totals/source evidence supplied). Then questions requiring another
  Core update for future LCD sizes: wants profile-driven selection usable from
  the application, not an expanding list of sizes in Core. Read-only review
  confirms the current candidate still enumerates 16/20 in shared profile and
  native worker, and duplicates exact bindings/profile hashes in Crypto.
  Proposed next design: generic bounded display capability, provider-owned
  geometry/controller limits, application discovery/layout and explicit hardware
  configuration approval. Supported geometry changes should need no Core or
  application source edits; a new controller may need a provider/driver update.
  Preserve exact device/profile M20 binding, explicit reapproval after hardware
  changes and original-request lookup/no replay. This generalization is NOT
  implemented or accepted by existing fixed-size software checks. No deployment
  wrapper, device mutation or additional runtime test was performed in review.

  Previous fixed-size candidate/evidence (retained, not the deployment plan):
  Owner confirms Crypto Monitor 0.5.0 displays real values, then corrects the
  actual LCD to 16x2. The earlier successful short two-line frame did NOT prove
  20 physical columns. Owner explicitly approved general Core/Agent geometry
  support and Crypto Monitor 0.5.1; Core VERSION remains unchanged.
  General CharacterDisplayProfileV1 accepts only strict integer columns 16/20,
  keeps rows=2, and binds each width into profile/package/contract identities.
  Per-profile argument limits/padding, blank state and native child/encoder
  geometry are exact; no truncation in Agent, new drivers or bus probing.
  Builder gains --columns; existing 20-column profile data remains unchanged.
  Crypto 0.5.1 adds explicit display_columns selection and migration 0005:
  old settings adopt 20 until owner chooses 16, revision advances, screens,
  quotes and receipts are preserved. Render uses 8+8 columns on 16x2, 10+10 on
  20x2, retaining dual-asset layout, independent overflow/OLD markers and clock.
  No new M20 authorization DSL: existing optional_resources handles TWO exact
  bindings, command:display16_frame and the prior command:display_frame (20x2).
  Same configured device, independently selected/reviewed matching resource;
  neither grant covers the other profile. Discovery takes selected columns,
  changed size clears UI acknowledgement/readiness, and stored request arguments
  choose their ORIGINAL binding during lookup/replay, not new settings.
  Added protocol/Agent transport/approval and real sealed optional-resource
  geometry-switch checks; application geometry/render/migration/binding/UI cases.
  Static preparation checks: Python AST parsed (20 files), Vue/TypeScript syntax
  parsed (2 components + 2 test sources), PowerShell runner parsed and scoped
  git diff --check passed. These are NOT runtime tests or type-check/build.
  Tests/builds are owner-run only. Prior 0.5.0 green evidence is a baseline, not
  verification of the changed geometry code. Native/provider replacement,
  frame writes, Core/Agent deployment, release and Git mutations NOT performed.
  Owner core geometry run passed: 142 tests, 79 warnings in 14.51s; isolated
  Linux Python 3.14.4, /tmp/3mm-lab-ke2ybky0/results.xml, profile
  cap14-display-geometry, source SHA-256
  8c83e93c60459fa5d11dc15612488306b2d20e14fc560870d04f38248017029d.
  Includes native Agent artifact and sealed M20 denial/profile-change checks;
  no physical 16x2 acceptance or deployment follows from this software evidence.
  Superseded delivery plan after checks: Core+Agent delivery, a NEW 16x2 provider
  ZIP and Crypto 0.5.1 ZIP. Hold delivery pending architecture decision; do
  not overwrite published 0.5.0 or relabel the current approved 20x2 provider.
  Installation later requires explicit old-provider disable/new-profile review
  and new M20 grant. No automatic physical rotation/refresh or GPIO/AP/reset work.

- **CAP14 Crypto Monitor 0.5.0 ZIP built; owner upload/approval next,
  2026-10-31.** Owner requested integration after the accepted native LCD frame
  and explicitly approved Crypto Monitor 0.5.0 (no Core version change). Work is
  in the separate C:/Users/LAZ-DELL/Desktop/3mm-crypto-monitor source directory,
  which has no .git directory; preserve the existing independently developed
  0.4.0 editor/clock/connector logic. No extension-specific Core mechanism added.
  First bounded slice is an explicit single saved frame, not automatic physical
  polling/rotation. Added public SDK discovery/submit/lookup against command
  binding display_frame, display.character / 1.0 / write_frame, max TTL 10s.
  DISPLAY_DEVICE_ID is selected through ordinary configuration; argument schema
  exactly matches the accepted PCF8574T profile (digest f7960ad8...4bd5b7f),
  with no application-selected bus/address/provider fallback or admin token.
  New administrator operations require monitor_display separately from the
  existing monitor_configure and service M20 command:display_frame grant.
  Server prepares the saved revision/screen only, commits an actor-scoped
  request journal before SDK I/O and never resubmits the same request after a
  lost reply/restart. Migration 0004 only adds display_requests; preserves
  settings/samples/old receipts. Bounded 500-record journal stores user IDs, so
  storage metadata now declares personal data. UI persists request identity
  before its one invocation; unchecked acknowledgement, dirty-preview guards,
  explicit read-only recovery, and native matching receipt required for executed.
  Existing preview/settings/connector refresh/rotation never send a frame.
  Added backend exact-provider/Core-package validation, migration, denial,
  lost-ack, restart and actor separation checks plus frontend no-auto-send,
  storage failure, lost-reply/remount and permission checks. Agent performed only
  Python AST, Vue/TS syntax parsing and PowerShell parsing, not runtime tests,
  type-check, build, dependency install, API login or hardware access.
  Owner ran backend: 41 tests, errors=11, 5.206s; retained snapshot
  3mm-crypto-display-6275afba73aa45f5a20254c0eb90c04f. Identified a raw sqlite3
  context manager in the NEW test fixture (commits but never closes), causing
  Windows cleanup failures/resource warnings; fixture's second-actor write also
  inspected the first journal row rather than its own current request, raising
  an assertion swallowed by the deliberate unconfirmed-effect boundary. Fixed
  explicit connection closing and exact actor/request-row inspection, without
  weakening that boundary. Actual Core package validation correctly rejected
  contains_personal_data=true with no retention/export/erasure contract.
  Added real bounded actor-own display_export/display_erase administrator
  commands with separate monitor_privacy permission and explicit-erasure
  retention. Exports paginate at 20; erasure requires typed acknowledgement,
  refuses pending/unconfirmed work and never deletes another actor's journal,
  settings or Core/Agent receipts. A proposed GLOBAL output fence on erasure
  was rejected by automated review and was NOT applied; no safety table/global
  output block exists. Safer implementation consults the original SDK/Core key
  before any new submit when a local record is absent, including after explicit
  erasure; failed/unknown lookup cannot fall through to submit. Added scope,
  pagination, erasure/unknown refusal and original-receipt replay checks.
  No tests/build run by agent for the repairs; only static parsing/diff checks.
  Owner retest passed: all 18 affected display tests in 4.028s, plus the formerly
  failing existing package reproducibility/actual-Core validation consumer in
  0.186s; exit_code 0, retained snapshot
  3mm-crypto-display-486eece5d6e84f3294248d7bae0c6370. No cleanup errors reported.
  Reuse this evidence and unrelated successful original domain/monitor cases;
  do not rerun backend or claim an additional full-suite run.
  Owner frontend group passed: 2 files / 22 tests (13 existing monitor, 9 display),
  18.30s, Vite 6.4.1 build 10 modules in 847ms, vue-tsc type-check succeeded
  before Vitest; exit_code 0, retained snapshot
  3mm-crypto-display-007a9a6b0044496d9f6beda389aeeb74. Read-only hash comparison
  of all 16 allowlisted current application inputs with BOTH successful backend
  and frontend inputs.json manifests finds zero mismatches. Reuse these checks;
  no new tests/build run by agent. Owner built the distinct package with the
  existing build_package.py and Core Windows .venv Python:
  C:/Users/LAZ-DELL/Desktop/3mm-crypto-monitor/dist/3mm-crypto-monitor-0.5.0.zip,
  SHA-256 8fb6acc71cba89cd8711fcdd3b2dd9c71330a95fb84f318b1d6622ab5b27e48e.
  Agent's read-only Get-FileHash agrees. NEXT: owner uploads 0.5.0 on rasp-3mm
  via ordinary Extensions upgrade, preserves existing data, sets DISPLAY_DEVICE_ID
  to dev_65dba727720a40539c7d68cb70fef671, retains the two declared HTTPS
  connector URLs and separately reviews/approves exact new code/resource grants
  including command:display_frame plus user monitor_configure/monitor_display.
  Do not send a frame or invoke journal erasure/export as part of installation.
  No Core redeploy/rebuild or repeated software checks for this packaging step;
  runner copies allowlisted application source to a retained isolated temp folder
  and reuses the existing Windows Core dependencies. Source descriptors remain
  generated by the owner-run builder, not hand-edited with an invalid wheel hash.
  After software checks, owner builds the distinct 0.5.0 ZIP, then separately
  reviews/approves its exact native code, resources and user permissions before
  live application acceptance. No commit, publication, deployment, grant approval
  or physical Crypto Monitor frame has been performed or claimed.

- **CAP14 native 20x2 display: first-frame physical acceptance passed,
  2026-10-31.** Owner
  requests the next bounded step after I2C-ready acceptance. Read the existing
  character-display builder/profile, Agent activation guard and driver, Devices
  capability panel and the hardware-interface scope. The provider is an Agent
  module, not a Core-hosted application. Existing immutable native package
  builder supports bus 1 / address 0x27 / 20x2 / PCF8574T + HD44780, explicit
  profile digest and fixed rs0_rw1_e2_bl3_d4_7 mapping. Construction/install/probe
  must not send a frame; M20 consumer rights remain separate. Before this slice
  Agent activation required a local environment opt-in. This slice replaces it
  with explicit exact-installation consent, not a bypass or manual environment
  edits. Owner built the inert native ZIP (6299 bytes),
  .runtime/cap14-display/character-display-pcf8574-1.0.0.zip; package SHA-256
  66a0a140a9f92f5a38a81c534126fc9d50662307e3ac8782f0bb62624c4d9468,
  profile SHA-256 f7960ad8593131012af227d4f55ea14706ddce5f9c30e803f6ea13f4a4bd5b7f,
  module_id org.3mm.character-display.f7960ad8593131012af227d4f55ea14706ddce5f9c30e803f6ea13f4a4bd5b7f,
  driver pcf8574, activation not_requested. Local read-only archive hash agrees
  with owner evidence. Owner asks to stop handing back blocked installation
  steps and prepare the missing software. Prepared a general protocol descriptor
  and explicit approval body bound to exact device/package/profile; Core and
  Agent both validate before queueing/extraction/activation. No concrete module
  names in the Core mechanism. Native install requires the independent Agent's
  advertised module_hardware_profiles.v1 feature, not a guessed Core version.
  Devices gains Hardware providers: inert ZIP upload/catalog, exact configuration
  review, unchecked acknowledgment and explicit normal module installation.
  Approval is submitted with that install request, not a free-standing global
  grant. Existing Disable has a separate confirmation; disabled state cannot
  silently reapprove a later install. Preserve request ID across reload/lost
  acknowledgment and reconcile through a read-only installation receipt; no
  automatic retry. Reported installation status is not optical/live readiness.
  Agent persists device/package/manifest/profile consent with module state and
  rechecks it at startup. Native provider still requires native hardware mode;
  metadata deletion/simulation spoof must not bypass its trusted handler.
  Removed obsolete display environment flags from settings/CLI/installer; they
  cannot create consent. Profile/package bytes remain unchanged. Added EN/BG
  source labels (no language version bump or republishing modified BG 1.0.2).
  Added protocol/Agent/Core/UI denial, mismatch, restore/disable, idempotency,
  unadvertised support and lost-ack checks; updated prior display/CLI/environment
  tests to the current consent contract. Existing broad Agent/lifecycle/registry/
  startup/packaging consumers are in cap14-profile-approval owner profile.
  Static Python AST, JSON/key parity, profile paths, sorted deployment contract,
  Vue/TS syntax, PowerShell parser and diff checks only; no test/type-check/build
  run by agent. Owner then ran the backend profile: 367 passed, 2 failed,
  58 warnings in 27.45s, /tmp/3mm-lab-6eiqctz5; source SHA-256
  846218d8093975fb6837d5535de541fc8581a48e6d9ce0b73245d060d65f3d1e,
  unchanged a12c96a1 Python 3.14.4 dependency environment reused. Failures:
  old provider-specific error regex versus the new earlier generic digest gate;
  Contacts package consumer lacks optional three_mm_crud source in its snapshot.
  Corrected the exact expected denial and asserted rejection before extraction.
  Added explicit dev-lab pack --with-libraries opt-in (private/generated/path,
  symlink, digest/budget guards remain; no optional dependency installed in Core).
  Added source-roundtrip and exclusion regressions. Owner profile helper now
  supplies library sources and has -Group retest for the two failures plus
  tools/tests/test_dev_lab.py, independent of temporary prior-run files.
  Read-only comparison with the owner's original Windows archive confirms the
  only changed existing snapshot inputs are agent/tests/test_character_display.py,
  tools/dev_lab.py and tools/tests/test_dev_lab.py; no production-code change for
  these repairs. Reuse the 367 unchanged successes, not as a fresh full run or
  coverage of the newly included optional library. Owner instead reran the full
  selected backend profile: 369 passed, 58 warnings in 32.94s, exit 0,
  /tmp/3mm-lab-lhqs1_vc; source SHA-256
  e8aad2718ef727af79cb945e0162f6292aa56cea2213cd86182e7f05dd7d9986,
  same a12c96a1 environment/dependency hash reused. Both failures are resolved;
  no further backend or two-case retest is needed. New dev-lab self-tests were
  not part of that 369-case selection: included tools/tests/test_dev_lab.py in
  the existing deploy helper's complementary pre-transfer delivery checks.
  They must pass before delivery; do not claim they already ran. Owner then
  reports frontend group green: 4 files / 30 tests, 28.13s; vue-tsc type-check
  passed; Vite 6.4.1 build passed, 948 modules, 8.31s (main-p9CKmSE0.js).
  Reuse these unchanged backend/UI results; no repetition or new implementation
  at this handoff. Owner then reports successful Core + Agent deployment at
  2026-10-31 15:05:44, phase ready/state succeeded; key
  f1f5647955865f520a1285d41399a3dfdaf73108e90d28fb12127b616e2dcd76,
  release local-f1f5647955865f520a1285d4. Local prepared.json matches that key;
  preparation was not reused (266.422s). Reported stages: Core install 185.999s,
  Agent prepare 4.253s, native host prepare/publish 32.04/38.529s, Agent update
  39.879s, validate/extract 1.004s. This is owner deployment evidence, not a
  provider installation or physical frame result. Owner subsequently supplied
  /devices Hardware providers screenshots: exact native package/profile on
  dev_65dba727720a40539c7d68cb70fef671 changed queued/Enabled -> succeeded/Enabled;
  installation request 23d91d88cb9e12daf3af64b01f99c7b6. Treat installation as
  passed, not evidence of capability health or a visible physical frame.
  Existing helper updates Core AND independent Agent (full/aarch64/Python3.13),
  with normal pre-transfer delivery/rollback checks. Services may restart;
  provider approval/install, I2C activation/reboot, bus scans, frames and M20
  grants are not requested. Prepared ignored owner helper
  .runtime/cap14-display/probe.py: status reads exact package installation and
  discovery v3; send-one requires separate SEND ONE FRAME confirmation and
  first-frame-request.json exclusive durable identity before its only POST;
  outcome reads that idempotency key in recent command history and reported
  state, never resubmits. Existing admin command queue performs the shared
  invocation checks; the helper pins native profile/contract and uses a 30s TTL.
  This is administrator acceptance, not an M20 consumer grant or Crypto Monitor
  integration. Owner status now confirms standalone/online, exact native
  installation cmd_e2aa241e23404862a88c00e6cdd08801 succeeded/Enabled, installed_exact,
  display.character registered/available with no unavailable reason and
  ready_for_one_frame true. This is not optical verification. Helper reported
  logout unconfirmed; its cause is not diagnosed and does not negate the
  completed read-only status response. That status command submitted no frame.
  Owner then explicitly sent and read one physical frame: request
  c6f815570621d5feba62c28d5b27b424, command cmd_99b046ef24c04593b4c4a04fa3bb96c9,
  succeeded, delivery_attempts 1, execution_state executed, simulated false,
  error null; completed 2026-10-31T13:57:14.868102. Receipt and later reported
  state agree on the exact profile and space-padded 20-column lines
  "3mm CAP14" / "Display test OK", backlight true, has_frame true. Owner confirms
  both lines are visibly correct. Accept this bounded real PCF8574T/HD44780
  bus 1 / 0x27 / 20x2 test through Core -> Agent -> display, not just queueing
  or simulated state. Keep its local record; no repeat frame is needed.
  NEXT proposed integration: Crypto Monitor consumes the existing display
  capability through SDK with an exact M20 command binding; separate application
  permission review remains required. This does not authorize implementation,
  an automatic refresh loop, commit or release in this handoff.
  No new tests/build or live API access by agent; static syntax/diff checks only.
  Reuse unchanged owner 369 backend / 30 frontend checks and deployment evidence.
  Capability readiness and first-frame acceptance are now owner-confirmed.
  Broader lifecycle/failure/recovery or Crypto Monitor acceptance is not claimed.
  No photo request, new bus
  activation/reboot, raw bus tool, automatic frame or M20 grant.
  On dispatch/connection uncertainty use Status/Logs, not another Deploy.
  No deployment or live UI/physical acceptance by agent; no release claim.
  Owner explicitly declines a board photo; do not ask for it again or make an
  image a prerequisite for software work. Continue with the declared fixed
  PCF8574T/HD44780 profile; owner visual confirmation validates this frame on
  this mapping, not an independent electrical/voltage certification. Any further physical
  frame remains separately explicit and limited to that supported profile,
  without scans, arbitrary mapping guesses or automatic retries. No tests/build,
  dependency install, deployment, service/host change, activation, hardware I/O,
  version change or Git mutation by agent. No standalone test application or
  frame submitted by agent; the ignored helper was executed by the owner.
  Keep the accepted host-interface stage closed; no repeated bus enablement/reboot.

- **CAP14 local web I2C enable/reboot/readiness stage passed on device,
  2026-10-31.** Owner's read-only Raspberry evidence: class/i2c-adapter/i2c-1
  absent, bus/i2c/devices/i2c-1 present as a kernel symlink to
  devices/platform/soc/3f804000.i2c/i2c-1; name bcm2835 (i2c@7e804000), of_node
  resolves to firmware/devicetree/base/soc/i2c@7e804000. Clock bytes 00 01 86 a0
  decode to 100000 Hz. Together with the prior device-node/Agent-access UI,
  this confirms a wrong sysfs lookup in our verifier, not a need to enable or
  reboot again. Changed live() to the documented /sys/bus/i2c/devices/i2c-1;
  no legacy-class fallback, API/auth/permissions, activation or reboot changes.
  Reworked metadata doubles to match kernel adapter/of_node symlinks without
  any i2c-adapter class. Added post-reboot verification preserving original
  enable/restart IDs, journal and all three config files, plus missing/malformed/
  conflicting clock denial. Static AST and whitespace review only by agent.
  Owner then ran -Group boot: 72 passed, 8 warnings, exit 0 (5.47s pytest),
  /tmp/3mm-lab-jcm7afkn, source SHA-256
  e455b4702797565fcebd66ca9af6fe035f368fe7274b088113e7e9701f151a4b;
  existing a12c96a1 Python 3.14.4 dependency environment reused. The repeated
  deployment result 8f90fab3... is the prior release, not delivery of this fix.
  Owner's subsequent screenshot (12:52) now reports I2C ready, Live adapter
  Present, Device node Present, Running Agent access Verified for the same local
  device, retaining both enable/restart request IDs. This meets the current
  local host-interface web enablement, separate reboot and post-boot readiness
  acceptance point. No fresh deployment key was supplied; do not reuse the old
  8f90... receipt as evidence of the latest delivery. No further activation or
  Raspberry reboot is needed. Unchanged frontend evidence remains reusable;
  no additional tests/build/remote actions/Git mutation at this handoff.
  NEXT bounded stage: inspect/configure the existing 20x2 PCF8574T display
  provider and arrange an explicitly approved one-frame acceptance through the
  platform, then integrate Crypto Monitor through its approved binding. Do not
  scan/open/write the bus merely to inspect status; physical display mapping,
  visible frame and complete CAP14 acceptance are still pending.

- **CAP14 web enablement and separate reboot exercised; live adapter check not
  accepted yet, 2026-10-31.** Owner reports Core-only deployment succeeded at
  12:02:06, key 8f90fab3ecc343e202f03a9765a92d946d81ce5239db51251ad68854aaac5599,
  release local-8f90fab3ecc343e202f03a97. Screenshots for the same local device
  show not_configured -> configured/pending_reboot -> reboot detected, with
  device node Present and running Agent access Verified, but adapter Absent.
  Enable request a818e7a4694cf388d707dc7b5e016b5b; separate restart request
  0d554b19e6581874d1eaf07408686996. Owner confirms both actions already performed;
  do not repeat either or clear/replay their journal. This proves the reported
  web workflow reached post-reboot inspection, not full I2C/display acceptance.
  Source live() only checks /sys/class/i2c-adapter/i2c-1; kernel documentation
  describes /sys/bus/i2c/devices/i2c-1. Suspect a verification-path defect, not
  missing activation, but target metadata is still needed to confirm it.
  NEXT: owner supplies read-only sysfs adapter name/link and clock property.
  No bus scan/open/write, further reboot, hardware change or new deployment;
  no production-code change or repeated tests/build in this diagnostic handoff.

- **CAP14 stock model-filter false positive repaired in source, 2026-10-31.**
  Owner supplied active boot directives: ordinary common graphics/audio setup,
  [cm4] otg_mode, [cm5] dwc2, [pi5] dtoverlay=nospi10, then [all] enable_uart.
  The actual device is Raspberry Pi 3B+ Rev 1.4. Confirmed cause in our parser:
  overlay validation ignored firmware model-filter applicability, so a Pi5-only
  line blocked the Pi3 web workflow. No evidence of a real local I²C pin conflict
  in those supplied directives. Primary reference:
  https://www.raspberrypi.com/documentation/computers/config_txt.html#conditional-filters
  Prepared bounded correction in hardware_interfaces.py: exact supported-board
  model-filter membership (3B+ reads pi3 and pi3+; Zero W reads pi0 and pi0w),
  known foreign model sections skipped, model filters replace only the model
  condition, [all] resets uncertainty. Unknown/malformed/case-unverified headers
  remain fenced for hardware directives until [all]; unknown other filter
  classes are not assumed active/false or cleared by a model switch. Includes
  remain refused even under foreign model sections. Did NOT whitelist nospi10
  globally: it still blocks in an applicable section, including a real Pi5.
  Existing active unknown overlays, explicit I²C disable/speed and GPIO conflicts
  stay denied. A known matching model's I²C declarations are now interpreted
  rather than blanket-refused as conditional. Added exact owner-config regression
  through prepare/pending-reboot with full byte/preimage preservation, model
  aliases/foreign CM filters, unknown-condition/reset and active-denial coverage.
  One old negative case (foreign pi4 I²C on a Pi3) is now correctly a positive
  case; matching-pi3 disable remains a negative. No RPC/schema/auth/UI/permission/
  reboot behavior changed, and no device config was edited. Owner helper gains
  -Group boot (fresh isolated cap14-i2c-boot profile: hardware workflow + admin
  route cases, no old temporary JUnit dependency). Agent runs static AST/profile
  paths/PowerShell/diff checks only, no tests/build/install/SSH/deploy/hardware or
  Git changes. Prior 30 UI/type/build and unrelated successful backend evidence
  remain reusable, but do not claim they cover this new parser. Owner completed
  -Group boot: 68 passed, 8 warnings, exit 0 (5.45s pytest), isolated run
  /tmp/3mm-lab-n6tdfl2f; source SHA-256
  bc49e092cd0d994986d8f7cce7f84859bbeb95141368cdbbc13a4543143d19fa.
  Existing a12c96a1 Python 3.14.4 dependency environment reused; this is source
  test evidence, not installed-device or physical acceptance. NEXT: owner deploys
  via the existing .runtime/cap14-i2c/deploy.ps1 Core-only helper, then repeats
  read-only web inspection. No activation/reboot/frame or full CAP14 acceptance
  yet; do not repeat unchanged frontend checks solely for this parser fix.

- **CAP14 first live web inspection is fenced by an unidentified overlay,
  2026-10-31.** Owner screenshot shows the deployed Devices/Hardware interfaces
  panel for online standalone rasp-3mm, device dev_65dba727720a40539c7d68cb70fef671,
  inventory Raspberry Pi 3 Model B Plus Rev 1.4. The API/UI reports
  unverified_overlay_conflict and offers no enablement. This confirms the panel
  loads and the host-config guard refuses an overlay outside its initial allowlist;
  it does not identify which overlay, prove a real pin conflict or establish a
  defect in the board itself. No confirmation, bus activation or reboot reported.
  Current config() admits only empty scope reset, vc4-kms-v3d and dwc2 overlays;
  do not broaden this blindly or tell the owner to delete an OS overlay. NEXT:
  owner supplies a read-only view of active /boot/firmware/config.txt directives
  (comments/blank lines omitted, section context retained). Inspect the exact
  overlay/parameters and supported-board effects before deciding whether to
  extend the profile or report a genuine conflict. Diagnostics are not a return
  to manual raspi-config activation; the product workflow remains web-managed.
  Prior 244 backend + 30 UI/type/build evidence remains unchanged; no code edits,
  new tests/build, remote/device action or Git mutation in this handoff.

- **CAP14 Core-only device deployment succeeded; begin read-only web acceptance,
  2026-10-31.** Owner reports rasp-3mm deployment key
  894bbe6f99a251d71a8118da8610fd32b7db8f1a87833bc2ece7b905a826d4f5,
  release local-894bbe6f99a251d71a8118da, state=succeeded, phase=ready,
  unit 3mm-deploy-894bbe6f99a251d71a8118da.service. Installer completed
  2026-10-31 10:46:26; install Core 190.773s, validate/extract 1.029s.
  This is owner-reported deployment evidence, not an agent remote inspection,
  physical interface enablement or reboot acceptance. No replay/update is needed.
  Reuse the accepted 244 backend + 30 frontend/type-check/build results; no source
  code changes or new tests/build were made for this handoff. NEXT: owner opens
  http://rasp-3mm.local/devices as admin, hard-refreshes, selects the local rasp-3mm
  device's Hardware interfaces panel (last known device identity
  dev_65dba727720a40539c7d68cb70fef671), and sends current status/screenshot before
  any confirmation. Last observed bus was disabled/absent; do not assume that
  deployment activated it. Unsupported/conflict/unavailable results must be
  inspected, not bypassed with manual raspi-config. Only after a valid review,
  proceed with explicit web enablement, pending reboot, separate device restart
  confirmation, then live readiness verification. No display frame/provider/app
  approval, release/commit or physical acceptance inferred from deployment.

- **CAP14 selected frontend gates passed; Core-only deployment handoff prepared,
  2026-10-31.** Owner restored Windows frontend dependencies with npm ci from
  the checked-in lock; no package/lock source change. All 4 selected files passed:
  Device capabilities 13, Hardware interfaces 5, hardware transport 7 and system
  control 5 = 30 tests in 19.80s. vue-tsc type-check and Vite 6.4.1 build (944
  modules, 10.99s) also passed under the restored npm environment (Vitest 3.2.4).
  Do not relabel the earlier pnpm-tree versions as this environment. npm reported
  deprecated packages and an esbuild allow-scripts notice; neither blocked these
  gates. No script approval policy or dependency version was changed by agent.
  Reuse the owner's 244 passing Linux backend checks (source 6edcec34..., run
  /tmp/3mm-lab-i1z7ovsi) for unchanged backend behavior; no backend/frontend source
  changes made after this evidence. This is not a full release gate or physical
  I²C/reboot/visual acceptance.
  Prepared ignored .runtime/cap14-i2c/deploy.ps1 for owner execution: normal
  immutable Core deployment to the existing full/aarch64/Python 3.13 target,
  requires explicit current BACKUP confirmation, uses Ubuntu only as a build
  environment, preserves independent Agent selection (no --with-agent), and
  validates a Core-only kit before invoking the standard deploy.ps1. Additional
  checks select the deployment controller and full-release-contract consumers;
  standard Linux frontend preparation retains its own checks rather than faking
  reuse of Windows build evidence. Observation actions do not prepare/dispatch.
  Deploying these files does NOT enable I²C, start a display provider, issue a
  frame, approve an app or reboot the machine. Service restarts are normal
  installer behavior. Existing BG 1.0.2 stays selected/immutable; new source
  labels may fall back to English until a separately versioned BG update is
  prepared/selected at the later release gate. No version bump or language
  activation inferred here. Agent ran only PowerShell syntax/diff checks, no
  tests/build/install/SSH/deploy/hardware/Git mutation. NEXT: owner confirms backup
  and deploys; after the successful result, walk through the real web interface
  preparation and separate reboot, checking readiness rather than assuming it.

- **CAP14 backend accepted; Windows frontend dependency installation missing,
  2026-10-31.** Owner reran the bounded backend profile successfully: 244 passed,
  10 warnings, 13.48s, /tmp/3mm-lab-i1z7ovsi, source
  6edcec34aaaa99c06701c7836cb45b891e3d6fea7e21b48ceffef506b8961776,
  Python 3.14.4, same reused a12c96a1 environment/dependency digest
  f91ccaad806c25f0057f8f802db6ed3ad6733a89fd44d3bd934d14d1b8c8c5f7,
  exit_code=0. This confirms the repaired contract and the selected backend
  behavior/consumers, not a full release or real reboot acceptance. Do not rerun
  backend for an unchanged frontend environment repair.
  Owner's frontend run: transport 7 + system-control 5 passed; Hardware interfaces
  and Device capabilities suites failed during import, before their assertions:
  reka-ui cannot be resolved from UiRecordPicker.vue through the public UI barrel.
  Read-only inspection confirms reka-ui 2.11.0 is declared in package.json and
  both lock files, while frontend/node_modules/reka-ui is absent and an older
  .pnpm tree exists. No dependency/version/source fix is required or made.
  NEXT: owner restores frontend dependencies with npm ci using the checked-in
  package-lock, then repeats only -Group frontend (4 selected files + type-check
  and build). A changed installed dependency environment needs that new UI
  evidence; do not relabel the earlier 12 passes as testing it. No tests, installs,
  builds, deployment, hardware action or Git mutations by the agent. Live UI
  light/dark/mobile, device setup and separate reboot remain gated and pending.

- **CAP14 previous temporary JUnit unavailable; use a fresh bounded backend run,
  2026-10-31.** Owner's -Group retest stopped before any tests because the prior
  /tmp/3mm-lab-mbblhywe evidence could not be read. This is not a new I²C failure
  and does not verify the contract-order repair. Do not depend on restoring an
  ephemeral /tmp report, invent per-case successes, or silently narrow the missing
  failed-case list. NEXT: owner runs the existing self-contained -Group backend
  profile against a fresh snapshot (previous selected run: 244 cases, about 20s;
  not the full project suite). It covers the unknown prior failures and repaired
  contract guard without relying on old JUnit. Then pending -Group frontend.
  Updated the ignored retest helper's missing-evidence message to give this
  actionable path instead of requesting an unavailable original log. No new
  production edits, tests/build, device/deploy/reboot or Git mutation. Static
  helper syntax and diff checks only; deployment remains gated on owner results.

- **CAP14 I²C backend owner run failed; contract ordering repaired, 2026-10-31.**
  Owner evidence: /tmp/3mm-lab-mbblhywe, profile cap14-i2c-web, source
  12893b6146d93872eceb4f528a57d028c4ffb29658d89bad87c52d8b5446b22a,
  Python 3.14.4, reused a12c96a1 environment, dependency digest
  f91ccaad806c25f0057f8f802db6ed3ad6733a89fd44d3bd934d14d1b8c8c5f7.
  Result: 71 failed, 173 passed, 10 warnings in 16.91s; no deployment.
  Visible tail contains packaging failures; it is not evidence that all other
  individual checks passed. Static inspection found a deterministic error in
  this change: hardware_interfaces.py was inserted after platform_runtime_updates
  in deployment-contract.json, violating validate_deployment_contract's mandatory
  sorted/unique required_files rule. Moved it to its proper position. No helper,
  I²C transaction, API or UI production behavior changed in this repair. Strengthened
  the new release guard to validate the complete baseline first and require the
  expected incomplete-archive error for each removed file; malformed baselines
  must not satisfy its denial assertions for the wrong reason.
  Ignored owner helper now supports -Group retest: reads the previous JUnit,
  maps EVERY failed/error case to the fresh snapshot without silently dropping
  unknown cases, then adds the strengthened guard and direct deployment-contract
  consumer checks. Old logs are retained; unchanged successful cases need no
  repeat. Missing/mismatched prior evidence stops before tests. The full old
  log was not available through local read-only WSL inspection; do not claim its
  unshown failures were individually diagnosed. Static JSON order/uniqueness,
  Python AST, PowerShell parsing and diff checks passed; agent ran no tests or
  build, no device changes, deploy or Git mutations. NEXT: owner runs -Group retest;
  if green, run the pending frontend group. Real reboot/visual acceptance remains
  pending; no release/deploy authorization is inferred from this test result.

- **CAP14 local I²C web + separately confirmed reboot prepared, 2026-10-31.**
  Owner authorized the next implementation slice. Added a device-selected
  Hardware interfaces panel, administrator-only API and a fixed privileged
  worker through the existing update-helper boundary. No remote Node fallback:
  the selected identity must match the real local Agent identity. Initial
  supported profile is modern Raspberry Pi OS bookworm/trixie, canonical mounted
  /boot/firmware, named 40-pin Pi profiles, I²C-1 GPIO2/3 at explicit 100 kHz.
  Unknown includes/overlays/HATs, conflicting pins, explicit host disable or other
  speeds are refused, not overwritten. Inspection performs no bus scan/open/write.
  The worker journals pre/postimages of exactly boot config, a modules-load file
  and an Agent-only supplementary-i2c systemd drop-in. It does not change the
  shared 3mm account, load modules live, start providers, grant M20 rights or
  reboot on apply. Pending state survives Core/browser restart; only a changed
  kernel boot ID plus adapter/node/clock/running-Agent permissions can verify
  activation. Extended ACLs remain unverified rather than guessed. Reboot has a
  second device/revision/operation-bound confirmation and reuses the existing
  system-action scheduler, never factory reset. Request IDs reconcile without
  rescheduling; partial/lost workers are fenced, not automatically resumed.
  Common release-mutation locking is released before starting the worker to
  avoid racing its non-blocking admission. Failures restore only unchanged
  owned postimages; foreign edits and uncertain restoration remain fenced with
  durable evidence. API audit plus root journal retain the operation identity.
  Added isolated runtime/auth/rollback/socket/packaging and UI/transport/i18n
  tests; owner runner .runtime/cap14-i2c/test.ps1 exposes backend/frontend groups.
  tools/dev_lab.py profile cap14-i2c-web runs a fresh isolated snapshot; frontend
  group uses existing npm environment and includes affected Device capabilities
  and system-control consumers, type-check/build. No new dependencies or schema.
  English and BG message source updated; no version changed. Before publishing
  another BG archive, allocate a fresh language-package version; published BG
  1.0.2 must not be replaced. This is prepared source, NOT passing-test or physical
  acceptance evidence. Static Python AST/JSON/PowerShell and TypeScript/Vue syntax
  parsing plus diff checks
  only; no pytest/Vitest/type-check/build/install, SSH/deploy, service changes,
  reboot, Git mutation or display operation by the agent. Prior display 374+1
  evidence applies only to that unchanged display behavior, not these new paths.
  NEXT: owner runs backend then frontend commands; inspect any failure before
  deployment. Visual light/dark/mobile and real reboot acceptance remain pending.
  Do not reopen accepted CAP03/CAP09/M20 WP4 or independent M21 work.

- **CAP14 interface catalogue and I²C-only execution scope recorded,
  2026-10-31.** Owner asks to examine other useful hardware settings and save
  them in the plan before implementation, then implement only I²C + reboot.
  Extended the existing CAP14 section of docs/CORE_SIMPLIFICATION_PLAN.md, not
  another report: separates OS interfaces, provider profiles and M20 app rights;
  future catalogue covers SPI, UART/serial, 1-Wire, GPIO reservations, PWM,
  USB/serial/HID, camera/audio and approved HAT profiles. Future rows are not
  blanket implementation approval or claims of support. Network/AP/roles/reset,
  bootloader/overclock and business display content stay outside this editor.
  Shared admin/helper, revision/identity/audit, pin conflicts, truthful readiness
  and pending/reboot behavior are specified. The next bounded implementation is
  only local supported Raspberry I²C-1 web inspection/enablement, Agent-specific
  access, persisted pending-reboot state, a separately confirmed existing restart
  operation and real post-boot verification. No disable/other buses, driver wizard,
  native profile/app grant, frame or Crypto Monitor integration in that slice.
  Device hostname is an acceptance target, not a Core branch. Current handoff is
  documentation-only: no production/UI edits, tests/build/deploy/commit or device
  action; prior accepted behavior evidence is not rerun or relabelled. NEXT:
  implement only the I²C + reboot slice described in that canonical CAP14 plan;
  owner runs the new affected checks. The manual raspi-config handoff stays retired.

- **CAP14 direction corrected: hardware setup belongs in the platform UI,
  2026-10-31.** Owner rejects manual raspi-config/SSH as the product workflow and
  requires Core-managed device interface settings, shown for supported Raspberry
  hardware. Owner also specifies reboot is needed for I2C activation on this
  target. Stop the earlier manual-enable handoff; it was not accepted/executed
  as a platform solution. Last observed I2C state remains disabled/unavailable.
  Proposed bounded next slice: device interface inspection + explicit admin
  preparation of I2C/Agent-only access through a narrow privileged helper;
  distinguish configured/pending reboot from live ready. Reuse the existing
  admin-confirmed/audited system-control restart path for this local target;
  no automatic reboot, reset, arbitrary root shell or raw I2C application API.
  After reboot verify live adapter, device node and effective Agent access,
  rather than treating a saved setting as successful activation. Device/provider
  profile setup must also be web-managed; app M20 grants remain a separate step
  and are never approved by OS configuration. No Crypto Monitor special case,
  new framework or reopening accepted M20/WP4/CAP09 work. Current investigation
  confirms generic Agent/device command infrastructure and Core admin/helper
  restart already exist; exact new helper/API/UI implementation is the next
  task, not already delivered. Owner still runs tests/deploy; agent prepares
  source/commands only. This turn records the corrected direction, with no
  production/UI edits, tests/builds, reboot, OS enablement or remote action.

- **CAP14 Core + Agent deployment succeeded (owner evidence), 2026-10-31.**
  Owner confirms the physical display is on rasp-3mm.local, the same full/aarch64
  target as this deployment, not the separate Pi Zero/rasp-3mmw Node. Owner's
  final record: key 82d67dc1f6c703ffa8bd037ec8cadc711a98f0de324dc0c49642dbe0bbf44de9,
  release local-82d67dc1f6c703ffa8bd037e, state=succeeded/phase=ready.
  Core install, native-host preparation/publication and independent Agent
  preparation/update all completed. Reported ready build
  c9884507e69613fb03a2b70bdf7ea5c929f046930f94ede8002b90f5ce04b68b,
  Core PID 1369057. This is owner-reported deployment evidence, not an agent SSH
  inspection or a display write/physical acceptance. No provider ZIP/local
  native approval/application grant or Crypto Monitor binding was requested by
  the deployment. Owner's read-only preflight confirms Core ready, Agent role
  standalone, device_id dev_65dba727720a40539c7d68cb70fef671. /dev/i2c-1 is absent;
  user 3mm is not in i2c and service supplementary group is gpio; the user write
  check is no. Further owner output: /sys/class/i2c-adapter and
  /sys/module/i2c_dev absent, /usr/bin/raspi-config available, i2c group gid988
  contains raspberry only. Owner explicitly confirms I2C was never enabled in
  raspi-config; only the hardware was connected. This establishes an OS setup
  prerequisite, not an observed LCD failure. Historical manual raspi-config
  enable instruction is superseded by the owner's web-management requirement
  above; do not continue it as the accepted product workflow.
  Later device access should be Agent-service-specific, not blanket membership
  for the shared 3mm account. No bus scan, device open/write, group/service/
  environment change or frame yet. Actual
  LCD/backpack mapping and electrical compatibility still need confirmation.
  Agent only records evidence and provides commands; no repeated test/build or
  remote action. Previous 374+1 selected checks remain the behavior evidence.

- **CAP14 selected owner checks accepted: 374 + 1 passed, 2026-10-31.**
  Owner ran cap14-display on Linux/Python 3.14.4, source
  9640c711829a1e3736e611c66defed931ab90d8207e7767018d5b48bf5dde944;
  logs/JUnit/evidence retained in /tmp/3mm-lab-ekg4kv4l. One lifecycle test
  expected CapabilityContractError after disabling the provider, but invoke()
  correctly raises ModuleLifecycleError("capability is unavailable") before any
  driver call. Changed only that test's exact exception/message expectation;
  production code, dependencies, contracts and safeguards are unchanged. Reuse
  the 374 passing cases only for those unchanged inputs. Owner's single-case
  retest now passed, including the previously unreached restart assertions:
  source e2c37cc8ddf180c507912f8a11358826e59dfcbce5cf282d23ce842d9892015c,
  /tmp/3mm-lab-3fwspbo8, 1 passed in 1.25s, exit_code=0. Same Python 3.14.4
  environment was reused; dependency digest remained
  f91ccaad806c25f0057f8f802db6ed3ad6733a89fd44d3bd934d14d1b8c8c5f7.
  This is 375 distinct selected checks across two runs, not a new full-suite
  run or a replacement for release gates. No production change since that run.
  Ignored owner helper now supports -OnlyFailed: fresh source snapshot, same
  tested a12c96a1 Linux environment, single affected case, separate evidence;
  original failed evidence is preserved. Agent runs static syntax/diff checks
  only, no tests/build/install/deploy/Git/hardware action. NEXT: prepare an
  explicitly requested Core + independent Agent deployment for owner execution,
  preserving the disabled display default. Then separately verify board mapping,
  electrical/device access and accept an explicit physical frame. Crypto Monitor
  binding, sustained update cadence/retention and full CAP14 remain unaccepted.
  Owner now requests this deployment step. Prepared ignored
  .runtime/cap14-display/deploy.ps1: defaults to full/aarch64/Python3.13 target
  raspberry@rasp-3mm.local, Ubuntu only as a build/check lab, existing a12c96a1
  Python environment. It requires owner BACKUP confirmation, prepares an exact
  --with-agent/--without-images kit via tools/deploy.py, then calls the standard
  deploy.ps1 with -Bundle/-WithAgent. Reuses 374+1 behavior evidence; only the
  complementary deployment-controller and Agent delivery/rollback/locking gates
  are selected during preparation. Existing content-bound frontend/check caches
  remain authoritative; no gate/hook bypass or fabricated cache evidence. No
  display ZIP installation, driver/approval/grant changes, bus/GPIO/network setup
  or I2C frame is requested. Status/Logs are observation-only. This is the Core
  target, not an implicit ARMv6 Node/Pi Zero rollout; physical display host asked
  separately. Agent only prepared/parses the helper, no tests/build/SSH/deploy.
  NEXT: owner run helper with current target backup and send final status JSON;
  after uncertainty inspect Status/Logs rather than blind replay.

- **CAP14 character-display slice prepared; owner checks pending, 2026-10-31.**
  Owner resumes the 20x2 I2C display after 0.3.3 publication. Confirmed PCF8574T,
  address 0x27, I2C-1, SDA GPIO2/pin3 and SCL GPIO3/pin5. Owner says appropriate
  voltage; actual pull-up/level-shifting arrangement and LCD/backpack mapping
  are not yet physically verified. Supplied marketplace page was inaccessible.
  Prepared a general display.character/1.0 write_frame provider on the existing
  Agent module, command, M20 and SDK path, with two bounded printable-ASCII rows,
  explicit backlight and exact immutable profile/contract digests. Profile-bound
  module IDs avoid reusing one immutable module/version for different hardware.
  Local driver defaults disabled; mock and PCF8574 profiles are distinct. Native
  additionally requires the native hardware profile and exact local approval
  digest, separate from application resource consent. CLI and filtered Agent
  environment preserve only these two non-secret settings. Generic Agent service
  invocation now carries the authoritative command deadline; both current trusted
  services were updated together. Provider-side preflight validation occurs before
  I/O. Native HD44780/PCF8574 driver uses one fixed pin map and an isolated stdlib
  child, no bus scan/FORCE/raw application I2C, a <=3s deadline with per-byte checks
  and a resource lock, bounded kill/reap, no fallback or unknown-outcome replay.
  Activation/restart/readiness never write a frame; availability is only local
  path/permission readiness, not LCD detection. State distinguishes mock/native,
  has_frame and last_write_at; heartbeat does not refresh frame age. LCD content
  may remain after link/service loss; physical updates are not atomic/readback.
  Prepared contract/Agent/transport/CLI/filter tests and owner-run dev-lab profile
  cap14-display (whole Agent suite, generic M20 command regressions and Agent
  artifact). Agent performs only static syntax/diff review, no tests, dependency
  installs, frontend build, deployment, Git mutation, bus or hardware action.
  NEXT: owner run that profile from a fresh source snapshot; then separately
  deploy Core + independent Agent, confirm wiring/3.3V-safe signal levels and OS
  device permissions, and accept one explicit native frame. No extra mock device
  deployment is required. Crypto Monitor SDK consumption remains a separate
  sibling-app change; no sibling source was edited. Button, AP/Wi-Fi/app reset,
  other controllers and full CAP14 completion are outside this bounded result.
  Static evidence: all 18 affected Python files parsed without project imports;
  the ignored owner helper's PowerShell syntax parsed and git diff --check passed.
  No runtime pass is claimed. Owner command:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .runtime/cap14-display/test.ps1.
  API/build/hardware limits live in modules/character-display/README.md. Preserve
  this already mixed dirty diary outside any later exact implementation commit.

- **Core 0.3.3 published and publication metadata verified, 2026-10-30.**
  Owner screenshot shows Latest 0.3.3 and green preparation commit. Read-only
  public GitHub API confirms stable v0.3.3 is visible (draft=false,
  prerelease=false), annotated tag and both manifests resolve to
  061e7ebe76c325c5203708b03550dba2e1b611f1. Same-commit CI run 41038223241
  and Release run 41042773754 completed successfully. All seven required
  assets are present: three full architecture archives, ARMv6 Node archive,
  Core/Node manifests and SHA256SUMS. Manifest sizes/hashes and all six checksum
  entries agree with GitHub asset digest metadata; no large archives downloaded
  or independent local archive-byte verification claimed. Local HEAD/tag match;
  only this preserved mixed diary remains dirty. No agent tests/build, Git
  mutation, publication or device action. Do not recreate/move the published
  tag. NEXT: owner update the Raspberry through the Stable channel to the
  published 0.3.3 artifact, explicitly enable BG 1.0.2 and verify readiness,
  identity and the accepted UI. Published-artifact device acceptance is separate
  from the earlier local d33f409c deployment. Resume the agreed CAP14/I2C display
  direction afterward; existing CAP09/theme and M20/WP4 acceptance stay closed.

- **Core 0.3.3 + BG 1.0.2 release preparation authorized, 2026-10-30.** Owner
  confirms these independent versions after the green main screenshot. Public
  API and job summaries confirm CI run 41031237540 for full commit
  e615d727840e17e9c7bdb54e8ec8476b67d5d2f4 succeeded: Linux Python selected
  suites and compiled-UI integration, frontend 81 files / 812 tests plus types/
  build, tooling and selection. No repeated checks by agent. Published latest
  stable remains v0.3.2; the new preparation is not a publication or deployment.
  Updated VERSION, README, CHANGELOG and 0.3.3 release notes; BG changes only the
  matching manifest/definition version to 1.0.2. Translations/code/dependencies
  from the green commit are unchanged. The earlier generated BG 1.0.1 ZIP is
  preserved, not overwritten. Bundled-language lifecycle stages a new version
  without changing an existing selected/disabled package; enable BG 1.0.2
  explicitly after an upgrade. No resource/key/schema/SDK/Agent/Terminal change.
  Owner's final metadata/package run succeeded: 98 passed, 12 warnings, 17.34 s
  on Ubuntu/Python 3.14.4, source
  d0961c44b79c98620b1a4a143f8693899dade447ec46a77717c5215f8f0e0e9f;
  log/JUnit at /tmp/3mm-release-033-pz6hn0cs. BG 1.0.2 standalone ZIP validated:
  .runtime/release-033/packages/language-bg-1.0.2.zip, 126234 bytes, SHA-256
  77804ed3b31a6a3b2948607a1a26a4ba04d8104e3892341b24d09ccece134218,
  activation=not_requested. Agent verified the ZIP hash matches. Final static
  packaging review found 1571 CRLF line endings in the Windows dictionary while
  the Git/Linux bundled release uses LF. Corrected ONLY the ignored package
  helper to normalize CRLF -> LF and write packages/canonical/language-bg-1.0.2.zip;
  preserve the raw unactivated ZIP above. Dictionary meanings and tracked source
  are unchanged; no need to repeat the 98 checks. Owner must rerun only the
  inert validated ZIP builder before using the portable artifact. Only release
  prose records this result afterward. This mixed diary remains excluded from
  the six-file release commit.
  NEXT: owner review/commit/push the six files and use a clean exact-commit
  publication checkout for the new annotated tag after required gates.
  Preserve this dirty diary; do not stash/reset it implicitly.
  Ignored release-033/release.ps1 supplies Verify, CommitPush and Tag actions
  against six frozen Git blob IDs and base e615d72. CommitPush rebuilds/validates
  only the canonical BG ZIP, reviews exact staging, asks COMMIT and pushes only
  that exact preparation commit. Tag requires green CI for the same six-file
  commit, remote-main containment, an unused tag and explicit RELEASE 0.3.3;
  it publishes from a new clean detached worktree, preserving original notes
  and retaining the clean temporary checkout. No branches/history rewrites,
  test reruns, hook bypass, forced tags or automatic publication retries.
  Release retains all full canonical/reproducible-build gates. No agent tests,
  install, build, commit, push, tag or publication is performed.

- **Fork isolation comparison passed locally; CI confirmation pending,
  2026-10-30.** Owner committed/pushed diagnostic test as 78eaf1e.
  New same-case first_dispatch failure shows all three processes alive, empty
  child logs, seen_count=0 and one pending delivery with attempts=0/error=null.
  Handler response timeout/signature processing has not started. A concrete
  test-harness defect is possible at the multiprocessing fork boundary:
  application_events._claim_lock is a process-local threading.Lock, but the
  test Core inherits the multithreaded pytest parent's copy. A held inherited
  lock makes claim_event_delivery return idle forever, without claiming a row;
  metadata/HTTP can remain healthy. Installed Core starts a fresh interpreter.
  Test-only _serve_core now initializes its own claim lock before its threads
  start. New real-process regression deliberately keeps the parent's lock held
  across the whole test, then requires exactly one acknowledged delivery and
  unchanged Core fingerprint/admin HTTP, with the parent lock still held.
  No production/admission/lease/handler budget, retry or skip change. The CI
  snapshot did not measure the inherited lock, so this is a concrete mechanism
  to validate, not yet proof of the original CI root cause. Agent syntax/diff
  checks only. Owner ran the fresh dev-lab pack and ignored event-runtime-ci/check.py
  --compare-fork on Ubuntu/Python 3.14.4, snapshot
  7ff4900d2c05a5944c60eb46d6076636fd818349160e09d90c01a56ca3e85ac9.
  Pre-fix copy: one expected regression failure, 19 warnings, 15.03 s; exact
  three-live/pending/zero-attempt/no-receive state confirmed. Fixed copy:
  **5 passed**, 71 warnings, 58.02 s, exit_code=0/baseline_reproduced=true.
  Log/JUnit retained at /tmp/3mm-event-ci-vt4fat0z. This proves the controlled
  inherited-lock defect and its test-fixture fix, not a measured parent-lock
  snapshot from the original CI or a canonical Python 3.13 full-suite pass.
  No relevant edits followed this run; reuse it without repeating local checks.
  NEXT: owner-only two-file test commit (test_platform_runtime_process.py and
  test_event_runtime_process.py), then push and normal CI. Keep this mixed diary
  out of the commit; no production/frontend/device/version/release change.

- **CI event-process failure: first-dispatch diagnosis prepared, 2026-10-30.**
  Main de5f6ce7e9f96f5a632106fd41e8213715fd146b CI run 41021773133 failed
  in Python job 123950562514: 3249 passed, 598 skipped, one failure after
  1233.75 s. Frontend/tooling/selection succeeded. Owner traceback and fetched
  job log agree: event_runtime_process.py:108 timed out waiting for the FIRST
  handler receive, before the hang-response/admission assertions. This does not
  establish a Runtime timeout defect or a harmless scheduler flake. The fixture
  discarded peer stderr and removed runtime.log on teardown, hiding causal
  evidence. Added test-only phase/process/durable-delivery diagnostics and owned
  peer log capture. Existing five-second waits, delivery/attempt assertions and
  production code are unchanged; no retry/skip/deadline relaxation. Agent source
  review/static syntax/whitespace only, no tests or environment install.
  Owner completed the fresh minimal pack and .runtime/event-runtime-ci/check.py
  on cached unprivileged Ubuntu/Python 3.14.4: all four signature/request_id/
  trickle/hang cases passed, 58 warnings, 36.36 s, exit_code=0. Snapshot
  77f2bd2697700f0e245811d06389391b8ad215fe1cda5789f250562e14162a47;
  log/JUnit retained at /tmp/3mm-event-ci-pefsonws. No relevant source changes
  followed. This is non-reproduction, NOT a root-cause/fix claim, full-suite
  result or canonical Python 3.13.17 CI pass. NEXT: owner-only one-file test
  diagnostics commit, then push and normal CI; retain the same five-second
  assertion and all delivery/attempt checks. If CI fails again, inspect the new
  Event process wait failed state before choosing a fix. Keep this mixed working
  diary out of that commit. No agent commit/push/rerun/release/device mutation.
  Theme acceptance remains closed and is not reopened by this independent gate.

- **Two reviewed source commits completed by owner, 2026-10-30.** Owner asks
  to commit after successful checks; no agent test/build or Git mutation.
  Reviewed base is 65e27112fbcb6797fbedf2b04c89ef032ee8a3f8. Connector proof
  priority and its regressions form an independent four-file fix. Unified theme,
  menu placement/sticky and Header/Menu editors share Settings/labels and form
  one coherent 38-path UI commit, including two retired component deletions.
  Ignored .runtime/theme-workspace/commit.ps1 supplies Connector/Theme scopes,
  frozen content digests, exact staging review and explicit COMMIT prompts;
  it preserves hooks and refuses changed content, foreign staging or index.lock.
  This working diary remains outside both commits because its dirty content
  also includes independent notes. No generated/private artifacts, app/language
  ZIP, version, branch, push, tag or release is included. BG changes are source
  labels, not a newly published language package. Existing successful owner
  checks are reused. Latest preparation now records key
  d33f409c6c3daeb4579383557d63e31b2036aa7ac6f2152688c88b6d29efc0a9,
  release local-d33f409c6c3daeb457938355, 308.21 s. Its checks.json matches the
  ready receipt hash: all 40 existing intended files match source_inputs and
  both intended deleted paths are absent. Standard preparation records the
  targeted 13-file Python group (72.719 s), full frontend test command
  (131.96 s) and build command (30.254 s); no new case totals are inferred.
  Owner now supplies final same-key Raspberry result at 09:21:32:
  phase=ready/state=succeeded, unit 3mm-deploy-d33f409c6c3daeb457938355.service,
  install Core 191.74 s and validate/extract 0.984 s. Owner also reports device
  checks completed and explicitly closes the theme work. This is owner-supplied
  live acceptance, not additional agent browser inspection. Do not reopen the
  earlier pending theme gates below. Commit helpers passed read-only scope/hash
  verification (4 and 38 paths); index remains empty, HEAD remains 65e2711.
  Owner executed both scopes with explicit COMMIT confirmation: 4e5007f
  (connector, 4 files, +165/-9) and de5f6ce (theme/Header/Menu, 38 paths,
  +1766/-2185). Local log matches; index is empty and only this working diary
  remains dirty. LF/CRLF notices did not prevent either commit. No source edits
  or repeated tests followed. NEXT: owner push of main, then hosted CI results
  and separate release preparation; do not create a tag before release review.
  No agent push/tag/release is performed here. Theme work remains accepted.

- **Header Customization + Menu Configuration selected checks passed, 2026-10-30; live acceptance pending.**
  Owner explicitly starts this slice while testing the menu/sticky deployment.
  Agent waited with read-only inspection while that kit was preparing. Owner
  then reports Raspberry success at 08:22:17, key
  0a5021372e6318fe619c1b9fc3c921375563a6fa4ca3470c77b7de1291c58ff1,
  release local-0a5021372e6318fe619c1b9f, phase=ready/state=succeeded;
  validate/extract 0.989 s, install Core 182.378 s. Prepared/attempt metadata
  locally matches the key. This is owner deployment evidence, not agent device
  inspection or visual acceptance. Only after freeze/dispatch did source edits
  begin; the following Header/Menu work is NOT in that deployed kit.
  Header now uses shared form/fields/buttons and an isolated branding preview.
  Text drafts remain per language; the shared logo is now a local copy, not a
  live-store mutation. Save writes only site_name/header_message for the chosen
  language and global logo_url; colors remain Theme-owned. Existing settings
  API is NOT transactional; any uncertain/partial save requires explicit reads
  before another save. Failed reads preserve drafts. The current asset upload
  endpoint already generates unique file names, so cropping need not modify the
  common ImageEditorModal or overwrite the saved asset; uploaded-but-discarded
  assets are preserved, not deleted. Header errors/locale changes are guarded.
  Menu contents use shared UiEditorForm/UiField/UiCollectionEditor; keyboard
  reorder, duplicate and reversible draft removal replace drag-only controls.
  Stable row keys are client-only; existing localized labels, audiences, custom
  internal routes and API payloads remain. Separate menu drafts survive menu/
  locale/section switches. Create/rename/delete use shared dialogs, not browser
  prompt/confirm; deletion keeps an explicit confirmation. Existing activation
  stays the automatic default, distinct from Theme placements/sticky. Lost CRUD
  or save replies fence further writes until explicit read; no replay/CAS claim.
  No backend/auth/schema/dependency/SDK/version change, Git action or new deploy.
  New source EN/BG labels only, no new language ZIP/version. Prior passing tests
  do not test these new inputs. Agent source/consumer review and static syntax/
  JSON/whitespace only; no tests, type-check/build, install or browser/device work.
  NEXT: owner --with-frontend pack, then .runtime/theme-workspace/check.py
  --group header-menu: Node 22/pnpm 10.13.1 frozen install, type-check, eight
  targeted Header/Menu/Settings/helper/asset/navigation files, build. Backend and
  unchanged shared primitive checks are reused, not rerun. Real light/dark,
  narrow/keyboard, logo cancel/save, locales and uncertain-result recovery remain
  a separately authorized rollout/visual gate. User is testing the previous kit.
  Owner's first header-menu run /tmp/3mm-theme-workspace-v_vqgsfe completes
  locked dependency installation, then type-check stops before tests/build on
  two NEW MenuEditor.test.ts typing errors. Mixed fixture objects inferred an
  optional undefined bg value incompatible with Record<string, string>; the
  generic collection component lookup selected VTU's DOMWrapper overload, which
  has no vm. Corrected ONLY the test: explicit string-map fixture annotation,
  and disabled Add checked/clicked through its actual DOM button rather than
  manually emitting a component event. No cast, compiler weakening or production
  edit. Source syntax/diff checked only by agent; tests/type-check/build remain
  owner-run. NEXT: fresh --with-frontend pack and the same --group header-menu;
  there are no completed tests/build from this failed run to reuse or omit.
  Owner's corrected header-menu run /tmp/3mm-theme-workspace-9h1rbyro now
  returns exit_code=0, deployment=not_requested. Vite 6.4.3 production build
  passed, 943 modules, 7.90 s. The runner's preceding fail-fast type-check and
  eight selected test files therefore passed. Supplied excerpt has no test
  total/source SHA, so none is invented. No production edits followed the
  test-only correction. This is targeted verification, not full frontend/CI
  or device acceptance. NEXT: separately authorized owner-run Raspberry
  deployment, then light/dark/narrow/keyboard and draft/save/discard/reload
  checks for both screens. No tests/build/deployment/Git action by agent.
  Owner now authorizes the Header/Menu Raspberry rollout. Reuse the existing
  ignored .runtime/theme-workspace/deploy.ps1 wrapper: it prepares CURRENT
  source before dispatch, not the older 0a502137 kit, using the standard own
  npm/check cache and explicit thirteen-file Python selection. Same target
  raspberry@rasp-3mm.local, full/aarch64/Python 3.13/without-images; no Agent,
  app ZIP, language ZIP, Ubuntu installation, version or Git/publication action.
  Owner runs it via process-only powershell.exe ExecutionPolicy Bypass with a
  current backup; uncertain dispatch requires saved-key Status/Logs, not replay.
  No helper/runtime changes or agent preparation/check/deployment in this
  handoff. New prepared identity and final device result remain pending owner.

- **Theme menu positions + sticky zones frontend gates completed, 2026-10-30; live acceptance pending.**
  Owner requests multiple configured menus in distinct locations and sticky
  controls in Theme settings. Added bounded optional menu_layout preferences:
  up to 16 unique existing IDs in primary/header/sidebar/footer; omitted
  placements follow the active menu, explicit [] hides all. Separate sticky
  flags for header/sidebar/footer; no DB migration, menu-content/activation
  write, package edit or new dependency. Existing admin/exact-theme save and
  2048-character read/write budget remain; missing current IDs return 409.
  The appearance editor uses shared selects/checkboxes, an isolated position
  diagram and the existing Save/discard/unconfirmed/conflict flow. Failed menu
  reads never clear saved placements; deleted IDs remain visible for cleanup.
  Menu.vue filters every region through the existing live route/audience/kiosk
  rules. Shared MenuGroups renders the groups; the shell's main slot stays at
  one stable parent across placement, navigation and recovery changes. Mobile
  merges header/sidebar into one drawer; footer remains separate. Public/auth
  has no sidebar; kiosk/display get no configured groups. Sticky zones are
  height-bounded/scrollable; existing auth/language/Command Palette actions stay.
  Source EN/BG labels included, no language version/ZIP. Prior owner theme and
  connector results do NOT prove these new inputs. Agent performed source review
  plus Vue/TypeScript/Python syntax, JSON and whitespace checks only; no tests,
  type-check/build, dependency install, browser/device action, Git or release.
  NEXT: owner repacks --with-frontend and uses .runtime/theme-workspace/check.py
  backend (five theme modules plus test_menu_items) then frontend (Node 22,
  pnpm 10.13.1 frozen install, type-check, full frontend tests, production build).
  After success: separately authorized rollout and light/dark/390px/keyboard/
  long-page sticky and role-filtered region review. Independent connector fix
  and all prior theme source changes preserved; no new deployment is performed.
  Owner frontend run /tmp/3mm-theme-workspace-qwbcboti now reports **799 passed /
  1 failed** in 79 files, 153.94 s, start 07:51:15. The preceding fail-fast
  type-check step succeeded; production build did not run. Sole failure is
  extension-ui/v1.test.ts: its historical Menu mock renders only <div /> and
  swallows the newly named content slot, so the draft input is absent. Updated
  ONLY that mock to forward the content slot; kept every draft identity/value/
  mount-count assertion and all production inputs unchanged. Real Menu/shell
  integration tests are among the passing files, not replaced by this mock.
  Owner's UiPreview RouterLink warning is separate; that file passed and is
  untouched. Agent runs no tests/type-check/build. Reuse the other 799 passes
  and unchanged backend evidence; the supplied frontend excerpt has no archive
  SHA or backend count, so neither is invented. NEXT: fresh --with-frontend pack
  and --group frontend-finish in the existing owner runner: clean locked install,
  type-check, only extension-ui/v1.test.ts, then the still-pending build. This is
  supplemental evidence, not a new full-800-test claim or a device rollout.
  Owner now supplies completed frontend-finish result from
  /tmp/3mm-theme-workspace-d1huc1o2: exit_code=0, deployment=not_requested.
  Vite 6.4.3 build passed, 947 modules, 7.79 s. Type-check and the corrected
  public-UI test file are earlier fail-fast steps, so both completed before
  this final result. The excerpt contains no test count or source SHA; neither
  is invented. Reuse the other 799 passing tests above; production inputs have
  not changed in the test-mock correction. Missing isolated-copy config.json
  is expected: default build config succeeded, no private device config is
  needed. This closes the supplemental frontend gate, not device/visual
  acceptance, canonical release CI or publication. NEXT: separately authorized
  owner-run Raspberry deployment of the new menu/sticky slice, followed by
  actual positions, sticky scrolling, mobile and role-filtered navigation checks.
  No code changes or agent tests/build/deployment/commit in this handoff.
  Owner explicitly authorizes Raspberry deployment, 2026-10-30. Prepared the
  ignored .runtime/theme-workspace/deploy.ps1 owner wrapper: cached unprivileged
  Ubuntu Python, standard tools/deploy.py preparation, explicit six theme/menu
  plus seven connector checks, full/aarch64/Python 3.13/without-images, then the
  unchanged root deploy.ps1 with the returned Bundle. Run the wrapper using a
  child powershell.exe with process-only ExecutionPolicy Bypass, matching the
  prior policy workaround. Require a current backup; no Agent/app/language ZIP,
  Ubuntu installation, version/Git/publication change. Standard npm preparation
  owns its own exact-input cache; no invented reuse of pnpm results. On dispatch
  failure or lost SSH, use root deploy.ps1 Status/Logs for the saved key instead
  of rerunning preparation/installation. Helper syntax only checked by agent;
  no preparation, test/build, transfer or device job run. Prepared key and live
  result remain pending owner output; do not reuse the older 902300d6 kit.

- **Joint theme + connector rollout succeeded; browser acceptance pending, 2026-10-30.** Owner explicitly
  includes both scopes in one local Raspberry deployment. Agent prepares the
  command; owner runs the standard preparation/checks and authenticated dispatch.
  Target raspberry@rasp-3mm.local, full/aarch64/Python 3.13, without-images as in
  the last accepted kit; no independent Agent rollout, app ZIP, version, Git or
  publication change. Ubuntu is build/test-only, never an installation target.
  Use the existing cached unprivileged Ubuntu Python for tools/deploy.py prepare,
  explicit union of five theme and seven connector registration/consent/staging
  files, then deploy.ps1 -Action Deploy -Bundle with the returned checked folder.
  The standard npm deployment build/cache has its own proof; do not fabricate
  cache reuse from the separately passed pnpm run. No --skip checks or profile
  override. Owner must have a current backup; on lost/failing dispatch retain
  the exact key and use Status/Logs rather than replay. This handoff creates no
  kit or remote job. Owner's preparation now succeeded, reusing exact checked
  inputs 700ba58852ed and frontend build ec4d4e804fcc, 150.473 s:
  key 902300d6231fa079c360351850017bf8f88cd10149218c4a0ca81ae77815aded,
  release local-902300d6231fa079c3603518. Local prepared/ready metadata matches
  that identity. PowerShell execution policy initially blocked deploy.ps1 before
  dispatch. Owner then ran the existing Bundle in a child powershell.exe process
  with process-only ExecutionPolicy Bypass; no persistent policy change or
  preparation/check rerun. Owner returned the final same-key result at Raspberry
  log time 2026-10-30 07:17:23: state=succeeded, phase=ready, release_id as above,
  unit=3mm-deploy-902300d6231fa079c3603518.service. Installer reports update
  succeeded; validate/extract 1.054 s, install Core 195.996 s. This is owner-supplied
  deployment evidence, not an independent agent device inspection. NEXT: hard
  refresh Settings, inspect saved theme and the new editor, then real light/dark,
  draft/discard/save/reload, narrow/keyboard and preserved connector consent/
  settings acceptance. Installed theme packages and app configuration remain in
  scope to preserve, not erase/reinstall. No new agent tests/build/deployment,
  version, Git mutation or publication.

- **Theme workspace selected checks passed; visual acceptance pending, 2026-10-30.**
  Owner switches scope from the accepted CAP09 slice to one built-in default
  theme (always light/dark) and a single Settings editor using current controls.
  Local CAP09 commits are 824e2ea and 65e2711; no new commit/push is authorized.
  Canonical built-in/fallback/recovery palette is theme_design_defaults.json,
  with theme-owned header by default. Retired light_*/dark_* DB color records
  remain untouched but no longer form a second live default. Removed their
  duplicate Settings editor/read/save paths; explicit installed theme packages,
  branding, personal mode, role-filtered navigation and recovery are retained.
  Built-in palette overrides now use the same bounded v2 color/contrast checks
  and existing admin/exact-selection customization endpoint as theme packages;
  no schema change, DB reset, automatic migration or device/settings write.
  Settings uses UiEditorForm/UiField/UiButton; sample preview also exercises the
  public record/collection editors. Draft palette/variants are preview-pane-only,
  not global shell changes. Editing light/dark is separate from personal mode;
  defaults/discard are local intents until explicit Save. Lost save/read replies
  preserve the draft and block replay until explicit reload; fresh conflicting
  saved values fence a dirty draft. Existing route, auth and theme asset limits
  are unchanged. EN fallback and BG source labels added, no language version/ZIP.
  Agent performed source/consumer review and syntax/JSON/diff checks only;
  no test/type-check/build, dependency install, browser/device deployment or Git
  mutation. Prior CAP09 tests do NOT cover these changed inputs. Owner runner:
  .runtime/theme-workspace/check.py with --group backend/frontend, verified
  --with-frontend dev-lab source copy, existing unprivileged Ubuntu Python and
  Node 22. Shared store/shell require full frontend tests + type-check/build;
  theme customization/options/preview/selection/v2 are the selected Python group.
  NEXT: owner checks, then separately authorized deployment + Settings real
  light/dark/390px/keyboard review before visual acceptance. Single-picker UX,
  business app migration, CAP14, publication and unrelated independent authority
  source/configuration-provenance edits remain outside this slice.
  Owner returned 2026-10-30 evidence on verified source
  3669f7dc7ff17ca3a53bd247346b2cd42170436093845856f2a0296e6e093f46:
  selected backend **75 passed**, 85 warnings, 12.97 s, cached unprivileged
  Ubuntu/Python 3.14.4, /tmp/3mm-theme-workspace-x8364ooi/results.xml.
  Frontend /tmp/3mm-theme-workspace-ky6a8sen completed pnpm 10.13.1 frozen
  install, then type-check failed on five new TEST-source typing errors:
  get() omits exists(), and optional preview props were dereferenced directly.
  Changed only the affected assertions (declared option count and structural
  prop matches), without non-null casts, weaker compiler flags or production
  edits. Reuse the unchanged backend result; owner must repack and run only
  --group frontend. Frontend tests/build have NOT run yet. Agent runs no tests,
  type-check/build, install, Git mutation or deployment in this correction.
  Owner's subsequent frontend run /tmp/3mm-theme-workspace-vcgvmviv returns
  exit_code 0: full frontend **77 files / 778 tests passed**, 197.32 s,
  start 06:26:39; production Vite build passed, 940 modules, 10.10 s.
  Type-check is the preceding fail-fast runner step and therefore passed before
  this completed run. Evidence is the supplied final output; the excerpt omits
  the new snapshot hash. Direct read of WSL logs was denied by this agent's
  environment; do not claim an independent full source/hash comparison.
  Missing config.json in the isolated source is expected (live configuration
  excluded); normal build defaults succeeded, no config/secret copy is needed.
  Reuse the unchanged 75-case backend result above. No runtime/source changes
  or repeated checks in this handoff. NEXT: separately authorized Raspberry
  rollout and actual Settings light/dark/keyboard/narrow visual acceptance,
  including draft-only preview vs saved shell, discard/save/reload and one
  built-in default. No deployment, commit or publication has been performed.

- **Crypto Monitor connector upgrade blocker, 2026-10-29: local Core fix prepared.**
  Owner reports 409 unavailable in connector settings and consent after app upgrade;
  clean installation works. Found and reproduced a shared Core selection bug:
  historical connector-first registration (installation/incarnation key) shadows
  the exact staged-package proof. `_resolve_code_identity` and
  `current_registration` now select the current package-specific staging proof
  first and still require its original sealed verification; invalid current proof
  never falls back to historical consent. No data, grants, keys, app package,
  Core version, commit or device change. Preserve unrelated theme work.
  Six pure routing regressions: before fix 2 passed / 2 failed / 2 errors;
  after fix 6 passed. Python syntax and scoped whitespace checks passed.
  Added a POSIX integration regression with real first registration, immutable
  staging, connector reconfiguration overlay and fresh consent. User continued
  the work; selected Linux verification is now complete. The first run stopped
  in the NEW test's setup: the shared helper defaulted to creating credentials
  although this case declares authentication=none. Fixed that fixture input only
  (create_credential=False, credential=None). On verified source archive
  ccef0ecf43f81992a517922da85d52cb0267d9daa3313b7c661f60487f602e92,
  existing unprivileged Ubuntu cached Python 3.14.4: new integration 1 passed,
  4.23 s, /tmp/3mm-connector-upgrade-w0burby3; regression group 153 passed,
  75.97 s, /tmp/3mm-connector-upgrade-03sws9gw. Real seals/SQLite, no skips;
  logs/JUnit remain in those private runs. Reuse the 6 passing pure routing
  regressions above. No single-run 160-test claim. No dependency installation,
  Core build/version/commit, production DB access or deployment was performed.
  Owner-run `.runtime/crypto-connector-upgrade/check.py` uses a verified dev-lab
  source archive and existing unprivileged Linux Python, private /tmp state,
  --group new then --group regression. No dependency install or deployment.
  Live Raspberry failure is not independently inspected: user supplied generic
  connector response {detail:{code:unavailable}}. Treat the local reproduction as
  a concrete matching code defect, not completed device acceptance. Next:
  standard reviewed Core rollout; retry existing
  app consent/settings without uninstall or deleting preserved data.
  Follow-up, 2026-10-30: owner supplied current Crypto Monitor catalog row:
  disabled, enabled=false, active_version=null, error=null, candidate SHA
  62736c2021d0ea601ed1ac881870614d808c21a239c68cfd3686a261ef86e1c8 (0.4.0).
  Owner challenges attributing this to Core; direct real-artifact comparison now
  reproduces both consent preview and connector-save failure, using unchanged
  app ZIPs 0.2.0 -> 0.4.0 in disposable Linux state. Both connector origins,
  enabled flags, binding revisions and complete saved configuration remain
  identical after staging: transfer succeeds. Original HEAD source for the two
  changed services fails BOTH paths with registration_unavailable; the same test
  with the local fix passes BOTH. Exact case SHA:
  6a4e70069a09f743116079c5b1995a3c33d00cdb0740896ac1c346f709c87398.
  Source archive remains ccef0ecf43f81992a517922da85d52cb0267d9daa3313b7c661f60487f602e92.
  Baseline 2 expected failures, 5.28 s, /tmp/3mm-real-crypto-upgrade-orbw4qat;
  fixed 2 passed, 6.26 s, /tmp/3mm-real-crypto-upgrade-t9ecl13g. Real DB/seals/login,
  mocked UI compiler output only (no UI rendering/native service/device claim).
  First test-helper attempts stopped at hardcoded reference entrypoint IDs and
  then at a reused settings snapshot after a successful save; those fixtures
  were corrected before the final identical-case comparison. No production
  changes followed the previously checked two-service fix. Current app archive
  is not modified for this diagnosis; no direct Core-private data workaround,
  package-specific Core branch, rights bypass or Raspberry deployment.

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

- **Approved direction, 2026-10-29: CAP09 editing, then CAP14 display.**
  Read-only review of the Barsy/Crypto screenshots, current sibling UI sources,
  public @3mm/ui/v1 components and the explicitly referenced `3mm-crypto-monitor`
  chat. Existing fields/forms/tables are accepted; do not reopen that result.
  Recommend a shared editor shell (draft/save/cancel/conflict states), searchable
  record selection and repeatable/reorderable collections, retaining custom
  app-owned previews and business operations. First acceptance should use the
  two real editing scenarios, not a generic Core CMS/business CRUD engine.
  Owner now explicitly approves Reka UI as the internal accessible Vue primitive
  foundation behind the public 3mm UI contract. TanStack Table remains only a
  later candidate, not an approved dependency. First provide owner-run CAP03,
  deploy-fix and BG 1.0.1 commit commands; start CAP09 only after that checkpoint.
  Agent prepares files, owner runs checks. No dependency installation, framework
  replacement or sibling edits performed in this commit-command handoff.
  Barsy's current local source differs from the deployed screenshot, so agree
  the exact app versions before adapting either independently developed app.
  Crypto hardware is explicitly pending: Pi Zero W, 20x2 character display,
  owner-specified I2C address 0x27, selectable button GPIO. Follow-up belongs to
  CAP14 device/provider contracts, with bounded display frames and exact hardware
  binding, mock first; no raw application I2C/device access. Confirm controller,
  bus and electrical compatibility before real execution. Short press changes
  screen; 8..15 s selects AP and >=15 s app+Wi-Fi reset on release, not a Core
  factory reset. AP/reset need separate explicit recovery authority and acceptance;
  a display grant must not confer them. No hardware/network/reset action performed.
  Reka-based CAP09 direction is approved; exact implementation slice follows the
  commit checkpoint. Hardware/reset follow-ups remain separate. This note stays
  outside the existing CAP03 commit fragment. Agent ran no tests, builds,
  deployment or Git mutations.

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

- **0.3.2 owner-run CAP13 device smoke PASS, 2026-10-29.** The agreed manual
  local/read-only/one-hop profile has completed successfully on `rasp-3mm`.
  This is owner-returned installed-device smoke evidence, not whole CAP13,
  WP5/native-code isolation, remote composition or independent Ubuntu acceptance.
  Owner reports green
  Release and is testing `rasp-3mm`, not the still-older Ubuntu VM. Current Core
  0.3.2 and all five checked services are active/ready. Initial independent
  Runtime `3400e4bd...` did not advertise queries. With owner-confirmed backup,
  owner built from the installed release and independently activated Runtime
  `3af4df434255fa2700f21ffc9b4510382bb5f55d28bc4b248ffc271fd3429e80`.
  Returned probe confirms `query_execution_contract: 1`, readiness and unchanged
  Core PID. Native aarch64/CPython 3.13 application host
  `584e849cf07e7087c5794db46de95b32b761a09b0949b5da4ab19d167176fd9e`
  was built and published for NEW instances only; existing application pins stay
  unchanged. These are owner-returned command outputs, not agent-run remote checks.

  Prepared ignored `.runtime/cap13-acceptance/{prepare,probe,check_pair}.py` and
  two pure-Python manifest-v2 fixture ZIPs under its `packages/` directory.
  Provider SHA-256 `7f4b1ed406988bd4a4e69b962a4c66dde4afae2ce07d606669852d35f6b81f5e`;
  consumer SHA-256 `86f069b586b5a245aec991fb52b7a64cdb8904bf46521bcd82f7080df009ed18`.
  They use synthetic data only, no hardware/external network, no UI compiler;
  host-owned bootstrap storage has no business tables. Consumer has one admin
  test query and one exact `directory` dependency. Health does not execute it.
  Windows project Python 3.13.15: actual Core ZIP validation/determinism, matching
  contract, packaged wheel import, Unicode/application caller, unattributed-caller
  refusal, deliberately invalid output and one-call/no-retry refusal checks pass.
  These bounded fixture checks are NOT actual device timeout/transport/isolation
  acceptance; prior unchanged release evidence is reused, not rerun.
  Owner uploaded, approved and activated provider installation 7, instance
  `2aa790360ad8655de00819d0`. Returned status verifies the exact provider ZIP,
  active/enabled/enforced, active effective grant revision 1, no review blockers;
  empty scopes are expected. Signed host/health check confirms the exact new
  host build above and ready Core with unchanged PID/process generation.
  SSH transfer initially detected a changed key. Owner independently confirmed
  hostname/IP and the new device-console ED25519 fingerprint before updating the
  one hostname's known-host record; no SSH verification bypass was requested.
  Consumer installation 8, instance `13642b0f10fe9217fccb93fa`, is now owner-
  confirmed active/enabled/enforced on the exact consumer ZIP and expected host.
  Initial consent intentionally leaves query unselected. One owner-run alpha
  request returned `refused_or_unconfirmed`, `operation_failed`,
  `execution_unconfirmed`, retryable false, no provider output. This alone does
  NOT prove the permission-specific cause: status lists declared scopes, and a
  general admission exception is redacted. After explicitly approving consumer's
  `query:directory:read` for the same provider, owner-run alpha returned query v1,
  binding directory, exact provider instance, contract digest
  `187075c507c734a026dc0d2880a3d0cbb01b0fb6e724faa3fe207a4b432aee2f`,
  expected Unicode label and application caller instance/module matching consumer,
  with human_delegated false. This is the first successful installed-device CAP13
  vertical, not whole CAP13/isolation acceptance. Owner-run `bad-output` and
  `slow` (six-second handler/five-second contract) each returned operation_denied,
  execution_unconfirmed, retryable false, no output; Core /ready stayed ready.
  No precise wall-time or live provider dispatch-count measurement is claimed.
  Owner then revoked ONLY consumer rights: still active/enabled, review_required,
  grant revision 2, record `933729675b55002392b6d3b08b9239b0`, state revoked,
  effective/access_saved false. One alpha query was refused without output.
  `query_runtime_not_connected` in this revoked status is not proof of a Runtime
  process outage; the reader also emits it when the selected grant is ineffective.
  Fresh explicit consumer approval now verified: enforced/active/effective,
  grant revision 3, record `dec917487367a090a57b2c2316e71390`; one alpha returned
  the same provider/contract/caller and expected Unicode output. No restart,
  key recovery or provider approval renewal was needed. Owner stopped only the
  exact provider test unit and confirmed inactive before one alpha call. That
  call was refused without output; Core /ready stayed ready. The same unit was
  restored, and its signed health probe confirmed unchanged Core PID/process
  generation. One final separately requested alpha returned the same exact
  provider/contract/caller and expected Unicode output, without any new approval.

  Acceptance point reached: selected explicit binding, initial no-right refusal,
  successful query/application attribution, malformed output refusal, timeout
  profile refusal, effective consumer revocation, fresh-consent recovery and
  stopped-provider refusal/recovery. No new broad suite/build was run; unchanged
  release evidence is reused. Live dispatch-count/precise timing, in-flight
  revocation/drift, upgrades and reboot/fleet acceptance are not newly claimed.
  Test applications remain active with provider grant 1 and consumer grant 3;
  no cleanup, grant revocation or extra device operation has been requested.
  Runtime/default host now use the independently selected builds above; existing
  unrelated application pins and Terminal are untouched. Only this working-state
  handoff is tracked; fixture ZIPs/helpers remain ignored under `.runtime`.
  No commit or push. NEXT: owner chooses the next bounded development task or
  explicit test-fixture cleanup; do not extend this completed smoke on our own.

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
