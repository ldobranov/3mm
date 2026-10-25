# Current working state

Updated: 2026-10-25. Start here; follow linked details only as needed.

## Active task and next result

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
  Next proposed bounded design is CAP08 task/schedule admission and execution,
  with claim/lease, durable identity, retry/unknown and lifecycle semantics;
  no old scheduler revival or mass rename. Preserve Terminal and the accepted
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
