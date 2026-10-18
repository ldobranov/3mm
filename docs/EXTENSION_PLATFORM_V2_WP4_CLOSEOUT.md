# WP4 closeout — current execution checklist

Updated: 2026-10-18. This short checklist is the current work queue; dated delivery
reports remain evidence, not an ever-growing list of new work packages. It does
not replace or reduce the acceptance criteria in the Core plan.

## Preserve, do not reopen

- Existing command/connector/event/private-file authority and compatibility.
- The owner's accepted beta.47 private-file and beta.51 bounded SQL
  upgrade/recovery scenarios. Broader live acceptance is not inferred.
- Local checkpoint, public identity and consent-bound local-status execution.
- Exact outbound peer-read declarations, sealed optional approvals and EN/BG UI.

## Remaining outcomes, in order

| Outcome | Completion evidence | State |
| --- | --- | --- |
| Exact outbound peer read | Public SDK → signed gateway → current applied grant → one configured peer; refusal after revoke/drift, no unfiltered-list/signing/network fallback; current UI/catalog truth | Implemented/tested locally; common owner acceptance remains below |
| Remaining scoped platform coverage | Reconcile proof/peer mutations, jobs/public routes/provides with the original accepted contract; implement required paths or explicitly record unsupported features, never silently call them supported | Current matrix reconciled; runtime refusal checks implemented; unsupported combinations below remain open |
| Public frontend host contract | Module-bound operation bridge and feature/access information; server enforces actor/audience/resource grants; no token/private-store/general-HTTP exposure | Implemented/tested locally; common acceptance remains below |
| Reviewed UI + scoped service resources | Exact source/build/native review; human access independent of service grants; real signed UI-operation/SDK path and negative cases | Implemented/tested locally; common acceptance remains below |
| Neutral end-to-end acceptance | Same public reference in Standalone/local Agent and Hub with Linux/mock embedded providers; human/kiosk/admin boundaries, revoke/disable/restart/uncertain outcomes | Open |
| Final integration and owner acceptance | One consolidated regression/release candidate plus authorized disposable VM recovery/layout tests; exact versions and remaining limitations recorded | Open |

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
