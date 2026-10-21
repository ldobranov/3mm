# WP4 closeout — current execution checklist

Updated: 2026-10-21. This short checklist is the current work queue; dated delivery
reports remain evidence, not an ever-growing list of new work packages. It does
not replace or reduce the acceptance criteria in the Core plan.

## Current decision

The functional implementation, bounded live scenarios, consolidated regression
and publication evidence have been reconciled in the
[final acceptance record](EXTENSION_PLATFORM_V2_WP4_FINAL_ACCEPTANCE.md).
The backup/first-install/rollback corrections that were unpublished during the
beta.54 trials are included in published **beta.55**, commit
`2e634e22f7498f798867a6de4e23ace6024ac8a4`; exact-tag CI and Release both succeeded.

**M20/WP4 is functionally completed by explicit owner acceptance on 2026-10-21**
in the documented reviewed-native scope and with the final record's limits.
No WP4 closeout decision, additional declaration layer, repeat of accepted tests
or new Core release is required. This does not assert that every optional
combination, privileged skip or layout-specific negative case was exercised live.

The M21 Terminal disconnect repair remains a separate, unpublished worktree
change. It does not invalidate the accepted non-session WP4 scenarios. WP5
malicious-code/OS/browser isolation and the other M20 work packages are separate;
WP4 acceptance does not close M20 as a whole.

## Preserve, do not reopen

- Existing command/connector/event/private-file authority and compatibility.
- The owner's accepted beta.47 private-file and beta.51 bounded SQL
  upgrade/recovery scenarios, plus the beta.53 effective-status/UI correction.
  Broader live acceptance is not inferred.
- Local checkpoint, public identity and consent-bound local-status execution.
- Exact outbound peer-read declarations, sealed optional approvals and EN/BG UI.
- The owner's beta.54 Hub/mock functional stage, Standalone command and disposable
  portable-restore/backup-resume/corrected-rollback cases, within the exact limits
  of the final acceptance record. Styling was excluded from functional acceptance.

## Reconciled outcomes

| Outcome | Completion evidence | State |
| --- | --- | --- |
| Exact outbound peer read | Public SDK → signed gateway → current applied grant → one configured peer; refusal after revoke/drift, no unfiltered-list/signing/network fallback; current UI/catalog truth | Delivered with local integration/negative coverage; no separate live peer-mutation claim |
| Remaining scoped platform coverage | Reconcile proof/peer mutations, jobs/public routes/provides with the original accepted contract; implement required paths or explicitly record unsupported features, never silently call them supported | Reconciled; unsupported operations remain explicitly refused, not silently granted |
| Public frontend host contract | Module-bound operation bridge and feature/access information; server enforces actor/audience/resource grants; no token/private-store/general-HTTP exposure | Delivered; real neutral UI/SDK path exercised on Hub and Standalone |
| Reviewed UI + scoped service resources | Exact source/build/native review; human access independent of service grants; real signed UI-operation/SDK path and negative cases | Delivered; Hub human/kiosk/service separation and Standalone execution recorded |
| Neutral end-to-end acceptance | Same public reference in Standalone/local Agent and Hub with Linux/mock embedded providers; human/kiosk/admin boundaries, revoke/disable/restart/uncertain outcomes | Bounded live results recorded; owner accepted Hub stage and excluded styling; not every negative case repeated on each layout |
| Final integration and owner acceptance | One consolidated regression/release candidate plus authorized disposable VM recovery/layout tests; exact versions and remaining limitations recorded | Complete in the recorded scope; whole-WP4 owner acceptance confirmed 2026-10-21 |

## Execution rules

- Deliver a usable vertical path, not another declaration-only intermediate layer.
- Reuse existing contracts, fixtures and transport. No new authority subsystem,
  pairing rewrite, database engine, UI framework, sandbox claim or Developer Kit
  packaging in this closeout.
- Run the new scenario and directly affected regressions while implementing;
  broad checks at integration boundaries, the full release suite at the end.
- New blockers must identify the exact failed criterion and smallest necessary
  repair. Do not expand scope or defer an agreed acceptance criterion silently.
- Record results here concisely; do not count overlapping test runs as new progress.
- No branch, commit/push/release or live VM mutation without the user's request.

## Dated delivery history

The sections below describe what was true at each delivery date. Their then-open
gates and unpublished-candidate statements are not the current queue; use the
current decision and final acceptance record above. The original failures and
limitations remain evidence and are not rewritten as successful trials.

## Current vertical delivery: exact outbound peer read

`context.platform.read_installation_peer("logical_binding_id")` is an additive
SDK 1.3 call over the existing signed local platform socket. Its closed public
`ApplicationPeerReadV1` response carries the existing v1/v2 outbound status model
and the matching logical binding. It never falls back to the old list/enroll
methods. Credential expiry is explicitly unknown (`null`); credentials and
private signing keys are never read. Remote status/approval is not inferred.

The Core executor validates the installed ZIP outside locks, acquires the existing
review key and Core guard, locks all approved outbound peer rows in stable order,
then checks the full current subject and exact applied scope. Only after that
does it serialize the selected public peer snapshot and commit/release. Revoked,
stale, stopped, unselected, foreign or malformed requests receive no partial data.
This is local read-only metadata, not a network request or a sandbox.

Current Core status and the authoring catalog identify this bounded executor as
available; older unavailable-runtime responses remain understood by the dialog.
Pending approval is still not apply, and a declaration is not a grant.

Verification completed:

- **83 Linux cases** (117.62 s): new 28-case executor suite and existing 55-case
  sealed-authority suite. Actual signed SDK round trip, v1/v2, approve/apply/
  revoke/reapprove, complete-family subset checks, drift and real two-connection
  peer-revocation races pass. No credential/private-key SELECTs in the read path.
- **76 Linux compatibility cases** (101.52 s): existing peer-denial/cleanup,
  local-status and SDK compatibility suites. Together these two runs contain
  **159 distinct passing cases**; no skips. Existing warnings are not suppressed.
- **90 Windows SDK/protocol/catalog cases** pass; **111 targeted frontend cases**,
  type check and production build (5.89 s) pass. The first parallel frontend
  process ran out of memory; its complete one-worker rerun passed unchanged.
  These are targeted checks, not a newly claimed full release suite.
- Eight production/test files match the tested native source snapshot by SHA-256.
  Evidence: `.runtime/m20-peer-grants-read-{sdk,compat}.{log,xml}`. Disposable
  native sources use `/var/tmp/3mm-peer-grants.*`, not the live installation.

No VM, root service, live grant, M21, release version, commit or push changes.
The public frontend host outcome is now implemented below. Remaining platform
coverage must still be reconciled against the original accepted criteria. The
common neutral/owner acceptance gates remain open.

## Current vertical delivery: public frontend host

`@3mm/application-ui/v1` provides only `getInfo()` / `invoke()` through the actual
dynamic application route boundary. The existing public/kiosk/operator/admin
gateways recheck exact installed-artifact/entrypoint/audience bindings; current
human or kiosk access stays separate from native resource grants. No private
store, token or general HTTP API is exposed. Same-origin code is not sandboxed,
and that original delivery did not admit compiled UI into scoped grants. The
separate reviewed UI profile added below now closes that integration gap.

The neutral reference's operator and kiosk components now use only this public
host, not direct fetch/token access. The kiosk preserves an uncertain request ID
and blocks resubmission. The real install-time compiler built both components
successfully (807 ms); the existing presentation API and service SDK versions
are unchanged. See the [public usage contract](EXTENSION_PLATFORM_V2_PUBLIC_CONTRACTS.md#public-application-frontend-host-v1-2026-10-17).

Verification: **147 Linux tests** pass (14.39 s; native Python 3.14.4), including
new actor/audience binding, stale/forged context, disable and grant/terminal
revocation checks plus existing gateway, access, compiler, neutral reference and
authority-context regressions. The earlier Windows run passed its 59-test subset;
these are overlapping suites, not 206 distinct tests. Native evidence:
`.runtime/m20-peer-grants-ui-host.{log,xml}`. No live VM/services/grants were
changed. This is not the full release or cross-layout acceptance run.

Frontend: **61 targeted tests** pass (including actual route-host provisioning,
credential selection, fresh access, cancellation, stale/foreign bindings, JSON
bounds and no replay), type-check passes, production build passes (6.38 s).
The emitted import map resolves the public host artifact. There is no screen
redesign in this delivery and no new visual acceptance is claimed.

## Coverage reconciliation and execution refusals (2026-10-17)

The public schema catalog now reports separate execution profiles and explicit
unsupported features. The SQL metadata no longer incorrectly says the prepared
runtime is unimplemented. These are authoring facts, never live grants.

| Family / combination | Actual scoped behavior | Acceptance meaning |
| --- | --- | --- |
| Checkpoints, identity/status and exact outbound peer read | Dedicated current-grant adapters exist | Preserve current local evidence; common acceptance remains |
| Identity proof; peer mutation/receiver/unfiltered list | Refused before legacy private/network paths | Unsupported, not supplied by read authority |
| Jobs / public HTTP handlers | No scoped adapter; explicit execution refusal | Not silently enabled by valid declarations; compatibility retained |
| Capability `provides` | Exact explicit event publications only | No arbitrary provider-registration authority inferred |
| SQL + peer bindings | Unsupported combination | No mixed-profile claim |
| Compiled UI + scoped resource grants | Separate exact-build reviewed-native profile added 2026-10-18 below | Local integration repaired; broader layout/owner acceptance remains |

Reconciliation exposed a real missing execution fence: scheduler and public HTTP
could reach legacy invocation for a non-compatibility installation despite their
unsupported review status. Nine initial regression cases failed before repair.
The scheduler now checks mode at discovery, claim, execution and the existing
post-readiness callback. The shared service gateway refuses job/public HTTP
handler bypasses; public HTTP rechecks current mode after route resolution and
does not hide another compatibility app. Previously unknown/expired job claims
retain their tokens/evidence rather than becoming a new safe-to-retry claim.

The unchanged signed gateway's proof/peer refusal is also exercised through real
authenticated Unix IPC, not just SDK validation. No policy, pairing flow, schema,
new resource grant or browser/OS sandbox is introduced.

The original acceptance scope is not reduced by calling a combination unsupported.
In particular, a single neutral app combining the public UI host with resource
authority remains an explicit next integration gate. Broad Standalone/Hub owner
acceptance and final release regression are still open.

Verification: **188 distinct native Linux cases pass**, without skips. The
186-case integration run (158.48 s) covers scheduler/startup/quarantine,
public HTTP and signed public-web transport, actual signed peer/proof refusal,
native review/grants, UI host/gateway compatibility, catalog and relational
structural contracts. The final 7-case quarantine/lifecycle run (36.24 s) adds
two new cases; its other five overlap the first run. Evidence:
`.runtime/m20-peer-grants-scoped-{gates,quarantine}.{log,xml}`. Six production/test
source hashes match the final disposable native snapshot. Windows targeted
checks also pass; their overlapping counts are not added to the Linux total.
Production frontend build passes (6.59 s); no frontend source or visuals changed
in this reconciliation. Existing warnings remain visible. No full release-suite,
live VM, branch, commit/push or release claim.

That delivery's next implementation target was an exact reviewed-native **UI + scoped service
resource** profile through the existing manager and public host, preserving
separate human and machine access. Do not remove the frontend blocker without
binding the executable UI/source/build provenance and proving negative cases.
This is a required integration repair, not a new work package or a sandbox.

## UI + scoped resources integration (2026-10-18)

The existing `built_ui_sha256` artifact field now binds an entire Core-owned
compiled build, source ZIP and toolchain record. Local native review requires
the exact build hash and separate explicit same-origin UI risk acceptance.
The new reviewed UI profile reuses existing resource policies/approve/apply and
SDK enforcement; headless and old compatibility behavior remain unchanged.
No database/descriptor/SDK version or sandbox/publisher claim is added.

Catalog assets and the public host pin source AND build; native trust is checked
before UI/catalog/service admission. Resource revocation still denies the effect,
not human UI access; human access cannot substitute for service grants. Native
review revocation blocks new UI/service admission. Cached browser code is not
recalled. Legacy output without provenance is never silently rebuilt/promoted.
See [local review and host details](EXTENSION_PLATFORM_V2_PUBLIC_CONTRACTS.md#reviewed-ui-with-scoped-service-resources-2026-10-18).

The new integration fixture follows HTTP operator access → real signed service
IPC → public SDK → real signed Core platform IPC → scoped command queue. It
checks separate grants, stale build/context, revoke/reapprove and native revoke.
Additional cases cover modified/coherently rebuilt output, disabled lifecycle,
missing UI-risk acceptance and protected output paths. This is a disposable
test service, not a claim that a complete deployed Standalone/Hub reference has
passed owner acceptance. No live VM, service, grant, branch, commit or release
was changed.

Verification: **274 distinct native Linux cases** have successful results across
the integration and final focused rerun; no skips. The first integration run
passed 254 cases before exposing the gateway's refusal-order regression. That
order is corrected, and the final 78-case run passes (65.84 s), including the
full new vertical path, gateway/access/host regressions and public catalog.
Overlaps are not counted twice. Evidence:
`.runtime/m20-peer-grants-ui-grants-{integrated,fence}.{log,xml}`. The earlier
CLI test also now explicitly injects its own manager instead of relying on test
import order. Existing deprecation/test-key warnings remain visible.

**39 frontend tests**, type-check and production build (6.46 s) pass. The real
compiler built the neutral reference's two routes and emitted verified build
provenance. This is targeted integration, not the full release suite. No visual
redesign or new visual acceptance is claimed. Next: the common neutral
Standalone/Hub acceptance, then consolidated release/owner acceptance; do not
reopen this profile as another declaration-only work package.

## Consolidated beta.52 release verification (2026-10-18)

The complete local default Python collection ran all 5,076 cases. The initial
snapshot passed 4,460, skipped 602 platform-gated cases and exposed 14 outdated
test fixtures/expectations. Corrective whole-file runs confirm every failed case:
121 event/gateway/release cases, 31 registration cases (one Root-gated skip), and
eight final dispatch/gateway cases plus five transport subtests. Their overlap
is not new coverage: 4,474 distinct default cases now have successful results.

Deployment/Application SDK: 372 passed. A separate actual Root/helper run passes
15 start-consent cases without skips; it does not cover every privileged skip.
Frontend: 453 tests across 52 files, type check and production build pass.
Native tests use disposable source/mount namespaces, not the installed VM.

The immutable release workflow must independently repeat the exact tagged tree
on Python 3.13 and verify reproducible full/Node artifacts before publication.
This consolidated test Beta does not close WP4, broad Standalone/Hub acceptance,
disposable-VM recovery or owner acceptance. Update does not adopt applications,
grant permissions or start services on the owner's behalf.

## Relational status correction after beta.52 (2026-10-18)

The owner accepted the beta.52 bounded SQL preservation/replay/conflict/ATTACH
regression; its exact limits are recorded in the
[beta acceptance report](EXTENSION_PLATFORM_V2_BETA_ACCEPTANCE.md#owner-reported-beta52-sql-regression--2026-10-18).
The published release's authority status nevertheless unconditionally labels SQL
runtime unavailable. That is a status defect, not failed SQL execution or permission
to weaken admission. The local correction removes that unconditional claim.

After checking current native trust and all selected grants, status reads one
bounded signed host-metadata response outside Core snapshots/review-key leases.
It then revalidates the artifact, guard generation/revision, application epoch,
configuration, sealed grant and prepared lifecycle in a fresh snapshot. A stopped,
revoked, changed, stale or unverifiable runtime remains ineffective. Status issues
no invocation tickets/SQL permits and writes no journal, grant or business data.
The existing DTO/UI accepts a verified effective result without a schema or screen
change. This is a point-in-time observation, not authority for the next operation.

Verification: 34 new native Linux status cases pass, including real signed Unix
IPC, read-only refresh, admin-only/no-store HTTP and revocation/drift during IPC.
The affected integration run passes its 109 existing host/admission/review/UI
authority cases. Its one new-test expectation failure (missing sealed grant uses
the existing stricter status-only refusal) is corrected in the full 34-case rerun;
these runs cover 143 distinct successful cases, not additive repeated counts.
Two further actual Root/helper tests pass (146.61 s): the exact delivered ZIP,
protected preparation, separate non-root Core/application identities and real
signed SDK SQL path report effective status only while current rights hold,
then ineffective after revocation. No skipped cases are counted as evidence.
That is 145 distinct successful backend cases across these targeted runs.
Frontend: 13 relational DTO cases, type check and production build pass.
Evidence: `.runtime/wp4-status-{integration,focused,root}.{log,xml}`. The initial
privileged harness failed before reaching assertions because its temporary source
root was not traversable by the test UIDs; only that disposable directory's mode
was corrected for the complete successful rerun. Production permissions unchanged.

This correction is local, not part of published beta.52. No VM code, services,
grants, version, branch, commit or push were changed. WP4 remains open for the
common neutral UI + SDK Standalone/Hub and final owner/recovery acceptance gates;
the accepted SQL probes need not be repeated merely to restate their result.

## Consolidated beta.53 release verification (2026-10-18)

The status correction above is included in the beta.53 candidate together with
the gated M21 foundation. The complete default Python collection passes 4,625
cases, skips 602 platform-gated cases and passes five subtests (53m14s), with no
failures. Deployment/Application SDK passes 382 cases. The separate actual
Root/helper run passes both delivered-ZIP/Core-UID/signed SQL status/revocation
cases; it does not cover all privileged skips. Frontend passes 455 tests across
52 files, type check and production build. Existing warnings remain visible.

Evidence: `.runtime/release-beta53-{full,extra,root}.{log,xml}`. Local tests use
disposable Linux sources/mount namespaces, not live services. Exact tagged
Python 3.13 CI and reproducible full/Node builds must also pass before publication.
M21 routes stay unmounted. This release does not update the owner's VM, adopt or
start applications, grant rights, or close the outstanding WP4 acceptance gates.

## Neutral scoped reference delivery (2026-10-18)

The same public [application reference](../modules/application-reference/README.md)
now has a deterministic 1.1.0 scoped command profile; its default 1.0.1
compatibility workflow remains unchanged. The new profile binds one explicit
versioned mock capability/action/schema and uses only the public frontend host
and Python SDK. No new Core authority adapter, jobs, connector or scoped SQL
combination is introduced. Invalid scoped specification files cannot silently
produce the compatibility profile.

The real delivered wheel runs in a separate host process, with HTTP human/kiosk
authorization and both signed Unix boundaries. Acceptance exposed an actual
kiosk deadlock: updating `last_seen_at` before UI checks let autoflush hold a Core
write lock while the service needed the same DB for resource admission. That
timestamp is now written only after service IPC; access/grant checks are intact.

Verification: 91 Linux integration cases pass, then the final complete reference
suite passes 10 cases (three new CLI refusal cases; seven overlap). Together
these are **94 distinct passing cases**, not 101. The checks cover exact build,
separate human/kiosk/resource revocation, undeclared resources, replay/conflict,
lost ACK with original-ID lookup, and actual host restart without new work.
Evidence: `.runtime/m20-neutral-{final,package-final}.{log,xml}`. Existing warnings
remain visible. Provider-role fixtures are not live Hub/Node/Agent execution or
Root isolation evidence; the existing fake compiler is used only for trust
metadata in these backend fixtures.

The actual install-time UI compiler succeeds, **44 frontend tests** pass,
type-check passes and production build passes (6.28 s). The emitted component
was visually checked in desktop/light and 390px mobile/dark mock-host previews,
including an unconfirmed request that blocks resend while allowing lookup.
Request IDs use `getRandomValues` so LAN HTTP does not require `randomUUID`.
This UI preview is not a live Core acceptance claim.

The owner's beta.53 SQL/status/UI result is recorded in the beta acceptance
report. Live Standalone/Hub/Node and disposable recovery acceptance remain open.
That local delivery made no live changes. The subsequently authorized Hub/mock
preparation is recorded below; do not confuse it with complete UI/SDK acceptance.

## Live Hub / isolated ARMv6 mock preparation (2026-10-19)

The owner approved VM Hub plus a separate mock Agent on the physical Node.
The VM remains immutable beta.53. Its canonical role is Hub; Node enrollment,
heartbeat and inventory cross the real LAN connection. The isolated Agent has a
fresh identity, separate state, DynamicUser, private devices and no GPIO device
nodes or access to the original credentials. The original physical Agent's PID,
identity, connection and all 25 baseline file hashes remain unchanged.

The owner's managed mock configuration accepts one output and no input rules.
An initial development Mock GPIO package was explicitly refused for its input
declaration (`cmd_08924474be854debb689bf533ae58bdb`); no capability call was sent.
Its failed package/history is retained, not silently retried or rewritten.
The accepted candidate instead uses the existing **Digital GPIO Output** handler:

- Opt-in deterministic **1.1.0** build publishes the exact output-only command
  contract **1.0**. Default **1.0.0**, legacy packages and automation stay unchanged;
  unversioned calls are not accepted by the new profile. No Core/Agent code or
  GPIO configuration was changed for this contract.
- Package SHA-256 `e7ab19b266db360fc76b87204080c3ac863d13ad8c2a8c3657525e697da6991a`;
  target `dev_1d54a2398b9346aeb557523d09192d49` / `WP4 isolated mock Zero`.
  Install command `cmd_e41e974a1ee942b7a7ac23b449ecd4df` completed `succeeded`,
  one delivery. Registry reports registered/available true and output false.
- The neutral 1.1.0 app was built from the actual registry contract, not the
  synthetic example: `pulse_output`, `gpio.output.1`, 50 ms; contract digest
  `9a6b195d0dcb5f7183580157f2fd0fd68eabb402469683fb6afaf3220f97ae88`.
  ZIP SHA-256 `5167b7013478da40ad98afc8fc028016efa1fcf7af997bcdc62155214aa941af`.
  It is not installed/started/reviewed/granted by this preparation.

**47 targeted tests pass**: the delivered output-only package's managed-mock
path, deterministic builds, legacy profile, exact-version/digest/schema refusals,
pulse result/state and inactive shutdown, plus existing GPIO configuration,
module runtime and capability contracts. They are not a full release suite.
The live install additionally proves ARMv6 admission and real Hub/Node transport;
it does not prove a WP4 UI operation, application SDK command or GPIO pulse.

Next: consolidate the pending kiosk IPC fix in the candidate and perform the
reviewed neutral UI/SDK acceptance, then final integration/owner/recovery gates.
No commit, push, release, physical GPIO action or destructive recovery ran.

## Common candidate preparation (2026-10-19)

The unpublished local candidate includes the kiosk IPC fix, neutral scoped
reference and opt-in output-only provider. Its [installation/access runbook](../modules/application-reference/ACCEPTANCE.md)
keeps native/build trust, service `command:acceptance`, operator `probe_use` and
kiosk enrollment separate. No live grants are applied by packaging or release.

Preparation caught and fixed scoped ZIP differences from CRLF and OS-specific
ZIP creator metadata. The actual Hub-targeted ZIP now independently matches
between Windows and native Linux; compatibility packaging is unchanged. Final
app SHA-256: `1cafba392068fa843588220890f0535bbc5f9c7465d6b5d3d239013134646b75`.
The earlier 5167... local artifact is superseded, not a deployment input.

Verification: **142 affected Linux cases pass**, then the full **11-case**
reference/compatibility rerun passes after the final ZIP-metadata correction;
those 11 overlap, not 153 distinct cases. Human grant/revoke now uses normal
HTTP administration in the integration scenario, with independent SDK authority
and refusal of self-grant by an ordinary operator. **All 464 frontend tests**,
type-check and production build (6.27s) pass. The real compiler builds both
final ZIP routes. Existing warnings remain visible; the complete Python release
collection and exact tagged CI are not claimed for this candidate.

Evidence: `.runtime/m20-neutral-candidate{,-final}.{log,xml}` and
`.runtime/m20-wp4-candidate-final/VERIFICATION.md`. The local kit's source.tar is
a working-tree test snapshot, explicitly NOT an update-installer archive.
No live app upload/start/review/grants, GPIO command, VM update, commit/push/tag
or release occurred in this step. Post-update target review/access setup and
live UI/SDK/recovery/owner acceptance remain open; WP4 is not closed.

## Consolidated beta.54 release verification (2026-10-19)

The complete local default Python collection passes 4,636 cases, skips 602
platform-gated cases and passes five subtests (64m20s), with zero failures/errors.
Deployment/Application SDK passes all 382 cases. Both separate actual Root/helper
cases pass without skips; they are not evidence for all privileged skips.
All 464 frontend tests across 53 files, type check and production build pass.
Existing warnings remain visible.

The final test-only scheduler synchronization correction passes the complete
11-case file. These cases overlap the default collection, not 11 extra distinct
tests; runtime behavior, timing bounds and slow-application isolation are intact.
Only that test and documentation differ from the full-suite source snapshot.

Evidence: `.runtime/release-beta54-{full,extra,root,scheduler}.xml`. The local
sources run under Python 3.14.4 in disposable Linux mount namespaces, not live
services. Editing the task-local collector during its wait broke its post-test
shell offset and overwrote two logs; the complete native JUnit reports were
recovered directly and verified against the 5,238-case default collection.
This collector error is not a test failure or a production change. Exact tagged
Python 3.13 CI and reproducible full/Node builds must pass before publication.

The new reference ZIP remains a separate upload after the owner's Hub update.
Publication performs no application adoption/start/grant, VM update or GPIO
action. Live neutral Standalone/Hub UI/SDK, disposable recovery and final owner
acceptance remain open; beta.54 does not close M20/WP4.
