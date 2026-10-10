# 3mm — Extension Platform v2 Core Plan

Milestone: **20 — Extension Platform v2**.
Status: approved as the next Core milestone on **2026-10-07**. A limited WP0
source audit and 35 focused baseline tests were completed on **2026-10-08**.
The owner approved the first read-only Package Inspection slice; it is implemented
locally with focused tests and fixture-based visual review. Internal authority
metadata, connector/credential management writers and guarded API lifecycle
phases, explicit stopped/disabled lifecycle reconciliation and device pairing/
credential/lifecycle, provider/runtime and Agent-module authority writers are now local;
offline restore/rollback/reset fences and shared helper/recovery coordination are
also local. Actual installed command/connector source and subject reconstruction,
protected configuration identities and pure policy/context comparison are local.
As of **2026-10-09**, an installed-only headless reviewed-native backend cycle is
also local: authenticated manual native-review records, exact resource review,
separate approve/apply, sealed durable grants, broker admission and revocation.
It requires explicit local key administration and never infers OS/browser isolation
or publisher ownership. Existing installations stay compatible unless individually
adopted while disabled. See [implemented cycle and remaining gates](docs/EXTENSION_PLATFORM_V2_AUTHORITY_APPLY.md).
The Extensions management UI is also implemented/tested locally; the owner accepted
its command/connector visual delivery on **2026-10-09**. Scoped event consumption
is now implemented/tested locally; the owner also accepted its additive resource
view on **2026-10-09**. Scoped application publication now also has local package,
grant, shared journal/migration and signed SDK/runtime integration, with an additive
resource view. **WP4 is not yet closed**: remaining scoped contracts and
neutral Standalone/Hub/SDK acceptance remain open. Staged/new-artifact lifecycle and WP5
isolation are separate unfinished gates; there has been no live rollout.
See [limited WP0 report](docs/EXTENSION_PLATFORM_V2_WP0_REPORT.md)
and [inspection contract and evidence](docs/EXTENSION_PLATFORM_V2_PACKAGE_INSPECTION.md).
The local schema-export slice exports existing public JSON Schemas and documents the
compatibility matrix; see [public contracts](docs/EXTENSION_PLATFORM_V2_PUBLIC_CONTRACTS.md).
The authority/isolation design and additional current-broker baseline are local;
see [WP4/WP5 design](docs/EXTENSION_PLATFORM_V2_AUTHORITY_ISOLATION.md).
The read-only application authority diff and its Package Inspection UI are local,
comparing validated declarations with the installed baseline and saved configuration,
not approved grants;
see [authority review](docs/EXTENSION_PLATFORM_V2_AUTHORITY_REVIEW.md).
Owner visual review of this read-only UI was accepted on **2026-10-08**.
This does not approve package grants, production isolation or release/deployment.
Owner: Core / SDK chat. Marketplace, concrete extensions and AI Generator
implementation remain separate consumers/projects.

## Purpose and scope

Evolve the existing extension system into a stable, secure and distributable
platform. Reuse accepted Core, Agent, SDK, lifecycle and device contracts;
introduce only demonstrated generic gaps. Do not build a second extension or
device subsystem or reopen completed milestones as new implementation.

This is the common platform for **Standalone, Hub/Fleet, local Agent and
application extensions**, not Fleet-only or cloud-only work. Device capabilities
remain provider-neutral: Linux, embedded firmware and future providers use the
same registry/command/event contracts. Optional cloud/registry access must not
become a local availability gate.

Human developers and AI use the same public schemas, SDK, validator, packaging
and runtime. A generator may propose a missing generic contract; it cannot
patch Core, bypass review or execute generated code inside Core.

The six original work-package numbers remain stable. WP0 precedes them, and
delivery follows dependencies rather than numerical order. New field names,
schema/API numbers and signature formats are fixed through WP0/WP1 before
implementation. This plan is not an already supported wire specification.

## Architectural rules

1. Core knows identities, types, contracts, sources, lifecycle, grants and health,
   never concrete extension names or business entities.
2. Preserve installed IDs, data, configuration, permissions, device bindings,
   routes and version identity. Adapters do not authorize renaming existing
   `org.*` IDs into `com.*` IDs.
3. Shared identity/distribution does not mean one runtime. Applications, Agent
   modules, runtime pages, compiled UI/widgets, themes and language packages
   retain their existing type-specific validators and contracts.
4. Device capability, platform API feature and authorization grant are distinct.
   A capability declaration is not permission to use it.
5. Signature validity, publisher trust, runtime policy and approved permissions
   are independent. A signature proves provenance, not safe code.
6. One logical install/lifecycle contract delegates to existing type adapters;
   source, publisher or AI origin cannot select a weaker verification path.
7. Marketplace discovery, prices, checkout, invoices and payouts stay outside
   Core. Registry and licensing are optional generic boundaries.
8. Preserve offline operation and recovery. Expired AI credit or loss of cloud
   connectivity does not disable existing local workloads.
9. Code/package rollback does not reverse a payment or physical action. Preserve
   idempotency, expiry, durable evidence and uncertain-outcome review.
10. Database changes require Alembic migrations and migration tests. No
    destructive conversion, re-pairing or silent permission escalation.

## Independent version axes

| Axis | Baseline / rule |
| --- | --- |
| Core release | Normal immutable release version; no release number promised here |
| Module manifest | Existing `manifest_version: 2` remains valid |
| Type descriptors | Existing application, compiled UI, runtime, theme and language contracts remain supported |
| Application SDK | Keep SDK 1.3 and supported earlier versions; no automatic SDK 2 bump |
| Device protocol | Reuse accepted C0–C14 contracts and provider-neutral registry |
| Distribution envelope / registry | Independently versioned; exact new schema selected in WP1/WP2 |
| Developer Kit | Independently versioned, reproducible bundle with exact compatible Core/SDK/contract references; not an SDK-major bump |

“Extension Platform v2” is the milestone name. A new object containing
`schema_version: 2` is not automatically compatible with Module Manifest v2.
A new envelope must be unambiguous and adapt existing type descriptors.
Export machine-readable public schemas from authoritative models rather than
duplicating competing definitions inside the generator.

Older packages do not automatically become privileged. Preserve actual
provenance/runtime; a supervised application must not be downgraded to in-process
`legacy-trusted`. Deprecation requires a documented compatibility/migration window.

## WP0 — Current architecture → target architecture

Goal: fix a reproducible baseline and the smallest gap list before implementation.

Initial reuse map; these mechanisms are not a blanket production-security claim:

| Concern | Foundation to inspect and reuse |
| --- | --- |
| Identity / compatibility | `three_mm_protocol/module_manifest.py`, validators and catalog |
| Application / audiences | `three_mm_protocol/application_extension.py`, gateways and Public Web |
| SDK / scoped data | `three_mm_application_sdk` 1.3, private application DB and migrations |
| Application lifecycle | `three_mm_runtime/application_activation.py`, installed package lifecycle |
| Agent lifecycle | `agent/module_runtime.py`, desired/reported state and installations |
| Device capabilities | `backend/services/device_capability_registry.py`, C0–C14 contracts |
| Supervised process | `3mm-application-extension@.service`, signed platform socket, connector broker |
| Events / commands / jobs | Brokers, scheduler, startup recovery and external-outcome resolution |
| Frontend types | Compiled UI/runtime host, theme v1/v2, language and dynamic registrations |
| Recovery | Immutable releases, persistent namespaces, mutation locks and portable backups |

Deliverables:

- Source/test-backed `reuse / extend / missing / deferred` matrix, contract
  versions, compatibility risks and an owner for each gap.
- Representative application, Agent module, runtime page, compiled widget/UI,
  theme and language fixtures; no concrete product names in Core.
- Baseline install/update-failure, disable/uninstall, configuration, storage,
  backup/restore, routing, authorization and device invocation checks.
- Threat model for inspection/build, backend execution, cross-extension access,
  frontend integration and registry transport.
- Decisions on version negotiation, publisher namespace ownership, grant scopes,
  runtime classes and migration policy; one small first vertical slice.

Acceptance: distinguish implemented mechanisms, verified guarantees and remaining
live acceptance. No package is renamed/repackaged or device re-paired.
Cross-extension isolation is tested, not inferred from separate processes or
`ProtectSystem`. WP1 starts from the accepted gap list.

Limited WP0 delivery (2026-10-08): source/test-backed reuse map, concrete trust/
isolation/inspection gaps and a proposed read-only manifest-v2 Package Inspection
slice. This is not full WP0 security/live acceptance. It does not authorize WP1,
remote distribution, legacy backend execution or runtime changes automatically.
The subsequent owner approval covers only the read-only inspection slice below,
not full WP1 or WP5 acceptance.

## WP1 — Extension Domain and public contracts

Goal: normalize identity/metadata/compatibility through adapters around existing
models, not replace Module Manifest v2.

Scope:

- Stable ID, display name, publisher and immutable version plus artifact digest.
  The same ID/version cannot silently acquire new bytes.
- Publisher namespace ownership and authorized signing-key binding. Reverse-DNS
  syntax or an AI-generated name alone does not prove ownership.
- Normalized domain view with explicit type/runtime and existing descriptor
  adapters. New envelope fields have a closed schema.
- Core, SDK/API, Device Protocol where applicable, architecture, provisioning role,
  runtime-feature and dependency compatibility. Use Standalone/Hub/Node and
  advertised features, not a new ambiguous `server` role or fake Linux inventory.
- Separate install compatibility from availability. Optional/deferred device
  binding may allow install-inactive; activation/invocation stays blocked until
  required configuration and grants exist.
- Public schema exports and a compatibility matrix.

Acceptance: existing types inspect/load through existing validators; inspection
executes no package code. Invalid IDs/unsupported versions fail clearly.
Migrations preserve IDs, data, grants, configuration and bindings. Human and AI
manifests use the same schema/validator.

First scoped delivery (2026-10-08, local): admin-only manifest-v2 ZIP inspection
in Extensions, using existing validators without storage/build/activation. Exact
artifact comparison, declarations and explicit unverified/not-checked states are
covered by focused tests. No new manifest, SDK version or database model. Publisher
ownership and general compatibility planning remain open;
this is not completion of WP1. See the [inspection report](docs/EXTENSION_PLATFORM_V2_PACKAGE_INSPECTION.md).

Second scoped delivery (2026-10-08, local): deterministic structural JSON Schema
catalog/CLI over six authoritative manifest/descriptor models, with a compatibility
matrix and explicit semantic-validation limits. No new manifest, API route, SDK
version or install path. See [public contracts](docs/EXTENSION_PLATFORM_V2_PUBLIC_CONTRACTS.md).

## WP4 — Public Platform API, SDK and authorization

Goal: stabilize public contracts before lifecycle/generator work depends on them.
Extend SDK 1.3 compatibly. A new SDK major needs explicit approval of an unavoidable
break with a documented adapter/migration path.

Scope:

- Reuse the signed platform gateway, private storage/DB, events, connector broker
  and device command APIs. Native code imports public SDK/protocol packages,
  not Core database/services.
- One provider-neutral device registry. `gpio.digital.control` is a device
  function; permission to invoke it is a grant scoped to devices, operations/
  channels and actor context. No parallel `ctx.gpio` bypass.
- Keep provides/consumes capabilities, runtime/protocol features, platform grants
  and human role/application access separate and machine-readable.
- Deny-by-default server/runtime enforcement, bounds, revocation, audit,
  idempotency, expiry and target/connector scopes.
- Private relational data through public storage, not raw Core/other-extension
  sessions. Existing application-owned databases remain supported.
- Scoped events and lifecycle events, cursors, acknowledgements, quotas and
  redaction reuse existing brokers.
- Public frontend host/bridge contract without private stores or Core tokens.
  Declarative themes keep the safe Theme API.
- Authoritative catalogs, schemas, reference code and a bounded developer harness
  serve human developers and AI alike.

Acceptance: a neutral application uses only public SDK contracts and consumes
Linux or mock embedded capabilities in Standalone and Hub layouts. Undeclared
devices, foreign data/events and unauthorized operations fail. SDK 1.3 and
public/kiosk/operator/admin behavior remain compatible; missing features are
reported, not bypassed.

The dated slices below are delivery history, not the current feature matrix.
Their statements of "not implemented" describe that slice's date; the current
installed-only backend cycle and explicit closure checklist appear at the end
of this section.

Design slice (2026-10-08): distinct package/publisher/service/human/grant authority,
resource-scoped review, exact artifact/plan binding, race-safe invalidation and
recovery exceptions are specified in the [authority/isolation contract](docs/EXTENSION_PLATFORM_V2_AUTHORITY_ISOLATION.md).
No new grant schema/persistence, SDK call or live authorization behavior is enabled.

Read-only implementation slice (2026-10-08): application declarations are compared
by stable scope IDs, including effective command/event device bindings, connector
origins/references and human access. Unknown configuration/authority stays explicit;
new artifacts remain reviewable even without a scope diff. The additive opt-in
inspection field and read-only Extensions view select the actual installed artifact
and saved configuration through Core; unavailable baselines never imply a new install.
No approval, grant persistence or lifecycle enforcement is enabled. Grant baseline comparison
and other package-type adapters remain open. See the [authority review](docs/EXTENSION_PLATFORM_V2_AUTHORITY_REVIEW.md).

Approval-contract design slice (2026-10-08, local draft for owner review): explicit
resource subsets, exact artifact/configuration/credential-version binding, decision
versus active authority, race-safe invalidation and non-destructive existing-install
transition are defined in the [approval contract](docs/EXTENSION_PLATFORM_V2_APPROVAL_CONTRACT.md).
No grant store, approval endpoint or enforcement is implemented.

Internal validator slice (2026-10-08, local): a pure, closed/versioned resolved
context and whole-binding selection validator for commands/connectors, with
bounded/redacted failures and canonical test vectors. It is not wired to a route,
live resolver, approval issuer or runtime. See the [scope and evidence](docs/EXTENSION_PLATFORM_V2_CONTEXT_VALIDATOR.md).
Resolver design slice (2026-10-08, local): actual Core sources, production writer/
invalidation ledger and durable incarnation/epoch/resource-revision/private-key
ownership decisions are documented in the [resolver design](docs/EXTENSION_PLATFORM_V2_RESOLVER_DESIGN.md).
This is source-backed design, not a wired live resolver or installed invalidation
hooks.

Authority-metadata implementation slice (2026-10-08, local): durable application
incarnation/epoch, connector/device generations and a database transaction guard
with compare-and-swap helpers, Alembic migration and populated-data/concurrency
tests. Existing installs remain in compatibility mode; no approved grants or live
writer hooks are enabled. See [scope and evidence](docs/EXTENSION_PLATFORM_V2_AUTHORITY_METADATA.md).
Connector/credential writer slice (2026-10-08, local): existing admin mutations
now commit resource changes, authority generations and redacted audit together.
Connector ZIP preparation is outside locks; exact retries preserve revisions and
stale owner/package/secret snapshots fail. Public API/SDK and effect execution stay
compatible. See [writer integration and limits](docs/EXTENSION_PLATFORM_V2_AUTHORITY_WRITERS.md).
Lifecycle writer slice (2026-10-08, local): activate/disable/uninstall now use
guarded pre-helper and conditional completion transactions, general/physical
command fencing and atomic phase audits. Unconfirmed helper outcomes remain
disabled without replay or old authority restoration. See
[lifecycle integration and recovery gate](docs/EXTENSION_PLATFORM_V2_LIFECYCLE_AUTHORITY.md).
Recovery slice (2026-10-08, local): explicit admin reconciliation to verified
stopped/disabled state, helper-side current-ticket checks, Linux serialization and
durable one-use admission receipts. Unknown jobs/data/peer tombstones are retained;
no activation, rollback or replay is inferred. See
[recovery contract and limits](docs/EXTENSION_PLATFORM_V2_LIFECYCLE_RECOVERY.md).
Device pairing/credential slice (2026-10-08, local): approval/completion, credential
issuance/revocation and trusted local bootstrap repair now commit the resource,
device control generation, guard revision and redacted audit together. Same-ID
re-enrollment retains history but not old control identity. The unreleased metadata
migration materializes missing legacy-default platform rows; metadata readers and
participating writers never silently recreate missing existing authority. See
[device writer scope and evidence](docs/EXTENSION_PLATFORM_V2_DEVICE_AUTHORITY_WRITERS.md).
Device lifecycle follow-up (2026-10-08, local): reporting, authority release and
explicit re-enrollment preparation now commit control generations, existing state/
credential changes and lifecycle events under the guard. Presented credentials
are rechecked after authentication; exact lifecycle/release retries and reason-only
diagnostics do not advance control identity. Public revisions and uncertain
command evidence are preserved, with focused rollback and actual SQLite race tests.
Provider/runtime follow-up (2026-10-08, local): declarations, Core-owned capability
selection/enable and runtime support now commit their existing resource revisions,
fresh device control generation, guard revision and audit atomically. Presented
credentials are rechecked under the guard; exact retries do not invalidate reviews.
Health reports remain telemetry and cannot select offers or advance authority.
Focused tests cover audit rollback, missing metadata, key revocation and a real
two-connection provider-report versus administrator-control race. No new public
protocol, grant, capability registry or SDK is introduced.
Agent-module follow-up (2026-10-08, local): install/disable requests, matching Agent
receipts and proven pre-dispatch failures now commit installation/command changes,
fresh control generation, guard revision and redacted audit together. Exact retries
and superseded receipts cannot restore old module authority. ZIP validation and
Agent notification stay outside the short DB transaction; SDK/protocol and the
existing lease/uncertain-outcome behavior are retained. Focused rollback, missing
metadata, key-revocation and two-connection duplicate-request checks are local.
Offline recovery follow-up (2026-10-08, local): restore, failed-restore/installer
rollback and reset allocate fresh authority fences before services start; private
lifecycle helpers share the release lock. Identity/configuration and existing
uncertain evidence are retained; missing metadata blocks activation. See
[recovery scope, tests and limits](docs/EXTENSION_PLATFORM_V2_RECOVERY_FENCES.md).
Read-only installed-source follow-up (2026-10-08, local): validated digest-pinned
installed artifacts, saved configuration, Core/application identity, device/
credential/provider/runtime/contract and connector/credential metadata are read
from an explicitly consistent snapshot. No caller Session/cache is reused, no
missing authority is initialized, no secrets are decrypted and no authority is
minted. Real SQLite writer/read interleaving is tested; live PostgreSQL is not.
See [source scope and remaining gates](docs/EXTENSION_PLATFORM_V2_SOURCE_RESOLVER.md).
Private review-key follow-up (2026-10-08, local): explicit Core-owned POSIX key
creation/CAS rotation/recovery, full private configuration HMAC and current Core/
recovery-generation binding are tested, including real Linux process contention
and foreign-UID file denial. Reads never provision or repair keys. This was a
primitive without a production caller, not a management API or approved authority;
coordinator/audit and approval/apply serialization remain open. Read-only subject
composition is delivered separately below. See
[key scope, evidence and limits](docs/EXTENSION_PLATFORM_V2_REVIEW_KEYS.md).
Policy-evaluator follow-up (2026-10-08, local): strict internal whole-resource
policy comparison binds the exact principal/artifact/baseline/configuration and
recovery generation, preserves unsupported/source blockers and refuses fabricated
isolation or executable-frontend proof. Missing policy never inherits declarations;
changed evidence/rules change effective policy identity. This is a pure primitive,
not a protected evidence store/verifier, approval or production resolver hook. See
[policy comparison, tests and remaining gate](docs/EXTENSION_PLATFORM_V2_POLICY_EVALUATOR.md).
Review-history follow-up (2026-10-08, local): Core-private pending subject snapshots
and atomic recorded/denied/revoked history require a current signed administrator
session, exact request/actor idempotency and guarded head revisions. They preserve
the running application's epoch/authority and cannot represent approval or native
trust. Populated migration, retention, fail-closed recovery and actual SQLite races
are tested; no route, positive evidence producer or production caller is wired.
See [review-store scope and remaining gate](docs/EXTENSION_PLATFORM_V2_POLICY_REVIEW_STORE.md).
Installed-subject follow-up (2026-10-09, local): Core reconstructs the actual
installed artifact, full private configuration HMAC and command/connector
resources from one real database read snapshot, using the existing protected
Core/recovery-bound key. Only exact command-argument schema equality is supported;
sensor contracts and other unresolved scope families remain blocked. Missing,
foreign, corrupt or stale resources/keys yield no partial subject. Real SQLite
writer interleaving, key-lock contention and resource drift are tested on Linux.
This accepts no caller snapshot, provisions no key and issues no native trust,
positive policy, approval, grants or effects; even a supported headless subject
remains blocked without authentic policy. No production caller is wired. See
[subject scope, evidence and limits](docs/EXTENSION_PLATFORM_V2_POLICY_SUBJECTS.md).
Installed authority cycle (2026-10-09, local): a protected Core key now authenticates
manual exact-artifact native-review attestations, review plans, current grants and
idempotent action receipts. Local administration authenticates the real current
Core administrator; there is no HTTP native-proof checkbox. A bounded admin API
reconstructs actual resources, approves without changing authority, applies through
the guard with a fresh epoch, and revokes without replay. Existing command queue,
one-use physical permit and connector-attempt admission now enforce opted-in
whole-resource grants. Real POSIX keys, actual SQLite concurrency, real signed
sessions, broker/lifecycle routes, offline recovery fences and migration tests
cover this backend cycle. SDK 1.3 and compatibility installations remain supported.
This is reviewed native execution only, not untrusted executable isolation, a
staged/new-version installer or public SDK schema change. See the
[delivery report and operator sequence](docs/EXTENSION_PLATFORM_V2_AUTHORITY_APPLY.md).

Management UI follow-up (2026-10-09, local): installed application cards now offer
admin-only exact-resource review, explicit approve followed by apply, and separately
confirmed revocation. Core lists only current authenticated local native reviews;
HTTP/browser controls cannot create code trust. Expiry, stale/historical receipts,
actor errors and uncertain network outcomes cannot silently apply/replay rights.
Actual disabled state gates first adoption. Focused backend/frontend tests, type
checking, production build and isolated desktop/mobile light/dark browser inspection
pass. The owner accepted the local visual delivery on **2026-10-09**. Real
Core/browser recovery acceptance remains open; there is no live rollout.
Visual acceptance does not grant native trust or live application rights.
See the same delivery report above.

Event-delivery follow-up (2026-10-09, local): opted-in installations cannot consume
events through legacy manifest subscriptions. Compatibility backlog retries now
recheck current source/configuration/permission/artifact and device revocation;
denied deliveries retain terminal cursor/evidence without a new dispatch. The
gateway admits under a short conditional application/device transaction after
preflight and commits before service IPC, with a pinned transport target. Shared
package defaults are no longer mutated during event configuration resolution.
That first slice closed an unsupported-authority bypass without positive grants.
The subsequent scoped-consumption delivery below builds on its denial boundary.
See the event boundary in the delivery report.

Scoped event-consumption follow-up (2026-10-09, local): the existing exact-resource
review/approve/apply/revoke cycle now grants explicit subscription/device/event/
capability/handler bindings from the common provider-neutral registry. Current
source/artifact/configuration/authority is rechecked before durable dispatch;
approval-epoch-pinned backlog cannot acquire new rights by adoption or reapproval.
Version 1 command/connector records remain compatible; event subjects use internal
version 2 snapshots, with no public manifest/SDK version bump. Linux tests cover
native, firmware and Agent-module providers, source drift, revocation races and
legacy queue migration. The additive event-resource dialog is implemented/tested
and visually accepted by the owner on **2026-10-09**. Event publication and other unsupported families
remain denied. This is common Standalone/Hub/extension work, not Fleet-only support,
and neither fixture success nor reviewed-native execution proves WP5 isolation.

WP4 closure checklist (remaining work, not additional numbered work packages):

Source audit (2026-10-09): the own SQLite SDK and public UI presentation primitives
already exist; their presence is not scoped relational/platform/frontend authority.
The exact residual contracts, current denial boundaries and acceptance sequence
are recorded in the [WP4 closure audit](docs/EXTENSION_PLATFORM_V2_WP4_CLOSURE_AUDIT.md).
This audit changes no runtime permissions and does not close WP4.

1. Admin management UI: exact-resource review, approve/apply/revoke and actionable
   stale/recovery states: implemented/tested locally for the bounded headless
   command/connector profile, visually accepted by the owner on **2026-10-09**.
   The new event-consumption resource view is also visually accepted. It supplies no
   grants for unsupported scope families or untrusted frontend code.
2. Scoped event consumption and application publication are implemented/tested
   locally. Complete the accepted scoped storage/platform/frontend host contracts
   and their negative tests. Application-producer subscription access is not inferred.
   Unsupported authority cannot fall through to legacy execution on an opted-in
   installation.
3. Neutral public-SDK acceptance in Standalone/local Agent and Hub with Linux and
   mock embedded providers, including human/kiosk access and explicit local live
   recovery. Backend fixtures alone do not close this gate.

Scoped publication delivery (2026-10-09, owner-approved, local): the initial audit
proved a missing SDK method and typed application producer/payload contract. The
additive declaration is now validated in installed packages and exact-resource
reviews; internal context version 3 retains prior version 1/2 compatibility.
Publication grants use the existing native-review/approve/apply/revoke cycle and
short guarded admission, not manifest-inferred permission. Alembic
`fcd45b0213c4` extends the existing event journal non-destructively, preserving device
IDs, delivery FKs, cursors and original owned receipts. The additive signed SDK 1.3
call acknowledges only committed events, rejects foreign/changed content, preserves
exact historical receipts after revocation/recovery and never auto-drains the local
outbox or falls back to device ingestion. The catalog now marks this bounded runtime
`reviewed_native_scoped`. Tests exercise real local keys/sessions/SQLite/socket,
lost ACK, drift, revocation races, migration and offline fences. The existing dialog
also displays exact publication resources, with frontend checks and fixture-based
browser review. Cross-application consumer grants and WP5 isolation are not inferred.
See [approved scope, runtime evidence and remaining gates](docs/EXTENSION_PLATFORM_V2_EVENT_PUBLICATION.md).
WP4 remains open for the explicit checklist above; no live rollout is claimed.

Private-file SDK follow-up (2026-10-09, local): the existing host-owned data root
now has an additive `context.files` helper with logical IDs, read/read-write modes,
bounded content/count, digest CAS, pinned POSIX directory access, nonblocking
process locks and synced atomic replacement. SDK 1.3, SQLite/outbox and broker
denial of unsupported authority families remain unchanged. This is a cooperative
reviewed-native adapter, not authenticated storage approval, OS disk quota or WP5
isolation. A subsequent bounded activation slice now snapshots SQLite plus SDK
files, restores both before restarting on ordinary failure and retains stopped/
review-required evidence when rollback is uncertain. A further local slice verifies
SDK files through existing encrypted Standalone backup and downloaded portable
recovery with a fresh key, preserves private modes, rejects unsafe imported/source
namespaces and blocks backup/restore from discarding pending activation evidence.
Service/health/migration boundaries in these fixtures are doubles; no Hub/Fleet
full-state recovery is added. Explicit interrupted recovery, live acceptance and
approved storage policy remain gates; arbitrary native files and external effects
are not part of activation rollback. WP4 is still open.
See [private-file scope and limits](docs/EXTENSION_PLATFORM_V2_PRIVATE_FILES.md).

Private-file declaration slice (2026-10-09, local): optional descriptor-v1
`storage.private_files` now declares one own logical namespace, explicit mode and
strict SDK-compatible file/count bounds with its own contract version. SDK remains
1.3; existing undeclared packages are unchanged. The existing inspection diff
shows exact requests, and the source/authority manager refuses storage adoption
even through another selected scope or old native review. Catalog metadata says
runtime authority is not implemented. This is contract/negative-authority work,
not an effective storage grant or runtime quota. Guarded signed runtime admission
and per-operation checks must precede removal of this blocker. No WP4 closure,
live rollout or new database migration is claimed.

Host file-policy follow-up (2026-10-09, local): activation retains the validated
file request in protected runtime metadata; the host validates it before package
migration/import and binds an own-root SDK adapter. Declared get/list/put/delete
all refuse unsupported authority before file I/O, instead of silently acquiring
the legacy helper. Old undeclared SDK 1.0–1.3 applications remain compatible;
failed activation restores the exact previous metadata. No Core write permission,
new storage root, applied file grant or isolation is introduced. The remaining
positive executor must use the target-owned runtime boundary and serialize
current signed authority/revocation against file operations.

Exact file-policy inputs (2026-10-09, local): internal version 4 extends the same
pure policy/context evaluator with separate own-file read and write scopes. Whole
Core/application/incarnation identity, exact package digest, requested mode and
strict limits participate in policy identity and review fingerprint. Complete
requests cannot hide operations; policy subsets do not imply additional rights.
Old internal versions 1–3 retain their shape and behavior. This implements review
contracts only: synthetic evidence is not authenticated authority. Production
storage adoption, the host file denial and catalog's unsupported status remain
unchanged until sealed current-source approval/admission and target-owned execution
are wired and tested. No new Core file writer, writable mount, database model,
SDK version or live grant is introduced; WP4 remains open.

Bounded file execution (2026-10-09, local): real installed sources and the existing
sealed native-review/approve/apply cycle now bind internal version-4 own-file read/
write grants. The signed SDK gateway commits admission before target-owned IPC;
Core gains no application-data write access. A separate bounded worker in the same
application host avoids serial service-socket deadlock, pins its current nonce/
artifact/declaration and rejects expired/reused permits. Mutations reuse the sealed
authority action journal for metadata-only admissions/completions; uncertain or
historical requests never redispatch, including after worker restart or revocation.
Read-only requests never grant writes; requests above 1 MiB/file remain unsupported
rather than clamped. The catalog marks bounded local reviewed-native authority,
not sandbox support. Exact current-source, signed transport, real POSIX filesystem,
lost response, key/recovery drift and revocation ordering are tested locally.
The existing admin HTTP review/dialog now accepts the two exact private-file
scope IDs and presents separate read/write cards, owner/package bindings and exact
limits. It refuses incomplete, mixed, foreign or unsupported resources; local
native attestation and distinct approve/apply/adoption gates remain mandatory.
This is neither a file browser nor native-trust creation through the UI.
Focused HTTP/execution/authority/schema checks passed (138 Linux tests), as did
49 frontend tests, type checking and the production build. The isolated dialog
was reviewed in light/dark, EN/BG and mobile with no real permission mutations;
owner visual acceptance is still separate from automated/local verification.
Relational policy, remaining platform/frontend contracts and
neutral Standalone/Hub live acceptance still keep WP4 open. No SDK-major change,
new database model, live grant, deployment or release is included. See the same
[private-file delivery report](docs/EXTENSION_PLATFORM_V2_PRIVATE_FILES.md).

New-artifact staging/adoption recovery belongs to the agreed WP3 lifecycle work;
malicious-code/backend/frontend isolation belongs to WP5. Neither is claimed by
this installed-only backend cycle. Do not silently expand its runtime trust class
to finish the checklist.

## WP5 — Isolation and permission enforcement

Goal: prove executable third-party isolation before remote installation/untrusted
AI code. Design begins in WP0/WP4; enforcement gates the first executable slice.

Scope:

- Reuse the supervised application runtime and signed RPC, not a second host.
- Separate source (local/registry/development), publisher trust
  (official/trusted/unknown), runtime (declarative, supervised/sandboxed, reviewed
  native, legacy in-process) and approved rights. Packages cannot self-assert
  official trust or choose host privileges.
- Prove isolation between extensions: shared user/group access, private files,
  sockets, secrets and impersonation. Introduce per-instance identities or an
  equivalent tested boundary where needed.
- Restrict paths, networking, devices/processes, CPU, memory, deadlines, open
  files, disk usage and restart storms. No mandatory Docker-per-extension.
- Networking stays destination-scoped through connectors. No undeclared direct
  access or untrusted code imported into the Core API process.
- Existing compiled Vue UI is reviewed native integration, not a sandbox.
  Third-party executable UI needs a proven isolated origin/frame boundary and
  narrow bridge with message source/origin/schema checks, no Core token or
  unrestricted DOM/store access. An iframe alone is not proof.
- Review new rights, wider target/destination scopes and stronger runtime
  privileges. Bind approval to exact artifact/plan/grant diff; changes invalidate it.
- Unsigned development is explicit, opt-in and nonprivileged; no silent promotion
  to registry/public trust.

Acceptance: malicious reference packages cannot read foreign secrets/files,
write Core, impersonate an instance, escape frontend isolation or invoke undeclared
operations. Crash/exhaustion stays bounded and admin/recovery remains available.
Revocation/escalation review works. No sandbox label before proof.

The same design records private per-instance Linux identity/IPC/credential and
separate browser/resource proof gates, plus non-destructive migration/restore.
Existing broker credential/ownership tests are a baseline, not OS isolation
acceptance. The first internal read-only application declaration-diff slice is now
local with read-only inspection integration. The later installed-only cycle also
enforces command/connector grants for explicitly reviewed native headless apps;
it is not a remote executable installer or OS/browser boundary. Untrusted-code
isolation, broader permission families and WP5 acceptance remain unimplemented.

## WP2 — Distribution, packages and sources

Goal: one verified local/remote distribution boundary over existing type adapters.

Local first:

- `.cxp` is a proposed versioned ZIP envelope, not a new archive engine.
  Existing ZIP uploads/installations remain supported.
- WP1 fixes envelope version and typed-manifest references. Backend/frontend/
  migration payloads are optional by type. Themes/languages need no backend
  wheel, process, installer or RPC health check.
- Reuse archive validation with bounded entries, sizes, decompression, paths,
  links, duplicates and content before extraction/execution.
- Define canonical signed content covering publisher/identity/manifest/version
  and all payload digests; avoid self-referential signature/hash definitions.
  Fix signature/key format, rotation, revocation and audited downgrade policy.
- Checksums alone are not trust. Inspection/verification cannot execute package
  code, migrations or build/install scripts.
- Root/system-package installers from marketplace packages are forbidden.
  Extension-owned migrations run only inside the allowed lifecycle boundary.

Sources/registry:

- Generic metadata/version/immutable-resolution/bounded-download interface.
  Local Source precedes Registry Source.
- Registry Protocol v1 is independent of a marketplace/domain. Metadata covers
  compatibility, dependencies, digest/signature and artifacts; it grants no
  host/device rights.
- Remote executable installs remain disabled until WP5 isolation and WP3 recovery
  gates pass. Private/public registries share the verifier.
- Explicit destinations, TLS, redirect and opaque-credential policy prevent
  unreviewed endpoint changes and secret forwarding. Pin exact artifacts;
  mutable `latest` is not approval.
- Development directories remain explicit local sources, not trust shortcuts.
  Human and AI projects use one inspect/validate/pack/sign toolchain.

Acceptance: corrupt, changed, oversized, unsafe-path, wrong-publisher and invalid
signature packages fail before mutation. ZIP/new-envelope adapters use the same
typed validators. Local/remote paths share exact artifacts, permission review and
lifecycle. No AI bypass.

## WP3 — Dependency-aware lifecycle and recovery

Goal: extend existing application/Agent/type engines into a common planned,
observable lifecycle, not replace working engines wholesale.

Scope:

- Bounded deterministic resolver with documented SemVer/prerelease grammar,
  cycles/conflicts, role/runtime/architecture checks, pinned versions/digests
  and a reviewable plan.
- Extension/artifact dependencies are not uncontrolled APT/Python installation.
  Dependencies do not auto-grant rights or silently update applications.
  Removal checks reverse dependencies.
- Resolve metadata, download/verify, revalidate the whole graph, review permissions,
  stage, quiesce, snapshot/migrate, start, health-check and activate. Drift
  invalidates plan/approval.
- Durable operation/stage journal and recovery evidence. Serialize conflicting
  install/update/restore. Bundles do not imply atomic transactions across devices.
- Staged versions cannot consume live jobs/events or cause external effects.
  Define private health/preflight and activation fences; quiesce writers and
  snapshot data before migration.
- Restore code/configuration/data together on supported failures. Irreversible
  migration needs approved verified recovery before mutation; a version pointer
  is not data rollback.
- Preserve command/outbox/job identities, leases and startup recovery. Uncertain
  outcomes after dispatch remain quarantined; rollback/reboot never blindly
  replays physical/fiscal/external actions.
- Distinguish disable, runtime uninstall, package removal, retain/export data and
  explicit erasure. Preserve unrelated packages and recovery access.
- Extend protected bounded backup/portable recovery for new metadata, grants,
  trust references and journals, with compatibility checks.

Acceptance: stage failure/restart recovers to healthy or review-required state,
not a partial active version or replay. Migration retains a verified recovery
path; conflicts/escalation fail before mutation. Existing type fixtures, identity,
configuration, routes and recovery still work.

## WP6 — Optional commercial foundation

Goal: generic offline-verifiable entitlement after the free local platform passes.
Marketplace and billing remain separate extensions.

Scope:

- Provider interface with free/no-provider default; no mandatory account,
  registry service or cloud enrollment for local install.
- Signed grants use existing installation/device identity and generic feature/
  version references. Entitlement is not user permission, publisher trust or
  device command authority.
- Issuer trust, expiry/renewal/revocation, clock rollback/skew, replay, durable
  cache and restore-to-another-installation policy. Document offline revocation
  limits instead of promising immediate disconnected revocation.
- Grace is verified grant/policy, not an unsigned local override. Perpetual
  offline grants can remain valid without a live provider.
- Denied/expired/review-required transitions occur at safe boundaries. No Core/
  free-workload shutdown, unsafe actuator changes or interrupted begun transaction.
  Preserve admin/export/backup/restore/uninstall; gate new paid work according to
  agreed policy and reconcile in-flight work.
- Generic lifecycle events only; no prices, products, payments, subscriptions,
  invoices or payouts as Core business models.

Acceptance: free packages work without provider. Cached grants survive allowed
offline periods; foreign/tampered/expired grants fail predictably. Clock/recovery
cases pass; denial preserves management/data recovery and physical safety without
overriding authentication.

## Shared AI Generator constraints

- Accepted schemas/catalog/public SDK only; no Core internals or private Vue stores.
- Requirement analysis and capability/dependency resolution precede code.
  Classify gaps as available, optional/unavailable, unsupported or generic proposal;
  no raw database, subprocess or host-path workaround.
- Preserve project IDs. Registry/key verification establishes publisher ownership,
  not an AI naming convention.
- Derive requested rights, but local authorization review selects grants.
- Default executable output to a supported proven isolated runtime. Until accepted,
  use existing approved/declarative paths or inspect-only artifacts, not a
  claimed future sandbox.
- Same validation/tests/packaging/signing/lifecycle and exact source/artifact review,
  bounded repair and no generated Core patch.
- Generator UI/implementation remain separate (Milestone 16 where applicable).
  Reconcile its draft against accepted contracts before implementation; WP0 does
  not authorize a parallel generator rewrite.

## Delivery order and gates

### Final deliverable — Developer Kit v1

Owner-approved on **2026-10-09**; planned, not yet packaged or accepted. This is
the final developer-facing result of M20, not a seventh implementation work
package, new runtime, second capability registry or AI-specific execution path.
Build its contents incrementally from accepted WP1/WP4 contracts and WP2/WP3/WP5
evidence; assemble and verify the versioned bundle at final acceptance.

Required contents:

- Public SDK/API contracts, generated JSON schemas and a compatibility/support
  matrix derived from authoritative models. Pin Core, SDK, Device Protocol,
  descriptor and UI-host versions separately; retain SDK 1.3 compatibility.
- Provider-neutral capability contracts/catalog with arguments/results, events,
  required grants, feature requirements and bounds. Reuse the common registry;
  a known capability is not necessarily present or authorized on an installation.
- Public Vue UI components/design tokens and the accepted frontend host/bridge
  API, with light/dark, i18n and responsive examples. No private Core stores,
  administrator tokens or new frontend framework in developer-facing examples.
- Small neutral reference extensions and starter templates for supported
  applications, Agent modules, declarative UI and themes. Preserve type-specific
  packaging/runtime constraints; include executable examples only for proven,
  explicitly supported trust classes, not an invented future sandbox.
- A bounded offline/local test harness using disposable data, mock devices and
  connectors, the normal validators/packager and positive/negative rights tests.
  Cover lifecycle/recovery fixtures without real GPIO, payments or fiscal effects.
- A human-readable quickstart plus machine-readable contract index, examples and
  AI authoring instructions. Mark each contract supported, experimental,
  declaration-only or unsupported with required versions and remaining limits.
  Human developers and AI follow identical review, testing and installation rules.

The bundle has its own immutable version/digest and reproducible build/validation
instructions, with no secrets, local generated state or mandatory cloud service.
Do not copy schema definitions into templates as a competing source of truth.
Catalog/schema/template consistency is tested against the exact supported release.

Acceptance: from a clean checkout/environment, a developer or AI can author a
neutral extension using only the Kit, validate/test/package it, then install and
review it through the ordinary supported lifecycle without patching Core. Prove
this in Standalone and Hub with Linux or mock embedded capability providers;
public/kiosk/operator/admin and denied/foreign/revoked access remain covered.
Mock/harness success does not replace live recovery, isolation or release gates.
Kit v1 is not accepted merely because documents/templates exist.

| Delivery | Work packages | Result |
| --- | --- | --- |
| D0 | WP0 | Accepted reuse/gap map, baseline and threat model; no runtime changes |
| D1 | WP1 + WP4 contracts + WP5 design | Domain adapters, public exports and scoped permissions |
| D2 | WP2 local + WP5 enforcement + focused WP3 | Neutral local package in existing isolated runtime; approval, health, failed-update recovery |
| D3 | WP3 full lifecycle/recovery | Dependency plans, journal/restart/portable recovery and cross-type acceptance |
| D4 | WP2 registry | Same lifecycle from approved private/local test registry; no marketplace |
| D5 | WP6 | Optional signed offline entitlement with safe denial/recovery |
| D6 | Final acceptance + Developer Kit v1 | Clean install/upgrade plus reproducible developer/AI author-to-install proof without product-specific Core branches |

WP5 is a prerequisite throughout, not postponed until after untrusted distribution.
Each delivery has a small demonstration, focused checks, explicit gaps and separate
live acceptance. Planning edits need no deployment/full-suite run.
Release/deploy continues through the normal explicitly requested workflow.

## Definition of Done

- Existing SDK 1.3 applications, Agent modules, runtime pages, compiled UI,
  themes/languages retain IDs/data/configuration/permissions across upgrade,
  disable, uninstall-retain and protected portable restore.
- Standalone/local Agent, Hub/multiple nodes and applications consuming Linux
  or mock embedded capabilities share the accepted Device Platform.
- Neutral packages inspect/validate/install/start/health-check through normal
  adapters without extension-code execution in Core.
- Exact dependency/artifact/grant plans require approval; drift/escalation
  cannot reuse stale approval.
- Update/migration/interrupted activation recovers code plus data without
  replaying uncertain external work.
- Negative backend/frontend/cross-extension isolation and revocation checks pass;
  resource limits are measured on the supported low-resource baseline.
- Approved registry uses the local verifier/lifecycle with signed publisher
  ownership and immutable version/digest binding.
- Optional entitlement works offline within policy; denial preserves admin,
  export, recovery and physical safety.
- Human/generator reference artifacts share public contracts and acceptance,
  without product-specific Core branches or AI exemptions.
- Versioned Developer Kit v1 ships authoritative contracts/catalog, public UI
  components, supported reference packages/templates and bounded harness, with
  the clean author-to-install acceptance above and explicit unsupported features.

Automated/local success is not live recovery or production-security acceptance.
Record source/version, evidence, physical/VM scope and outstanding limits.

## Explicitly outside this milestone

- Marketplace storefront, registry hosting business UI or commercial pricing.
- Rewriting business extensions or migrating all packages at once.
- ESP firmware/board profiles, GPIO/serial/Modbus drivers or a second Device
  Platform; generic gaps require a separate scoped decision.
- Replacing Vue/theme UI, adding a framework or bundling concrete themes.
- Mandatory cloud, fleet-wide secrets or licensing kill switches.
- Root dependency installers, Docker/Kubernetes redesign, broad DB replacement
  or unsupported cross-host role promotion.
- Replacing SDK 1.3, renumbering accepted contracts or shipping an invented
  manifest before WP0/WP1 compatibility decisions.

## Related plans

- [Roadmap / Milestone 20](docs/ROADMAP.md#milestone-20--extension-platform-v2).
- [Master product plan](docs/MASTER_PLAN.md).
- [Application foundation](docs/APPLICATION_EXTENSION_V1_PLAN.md).
- [Common Device Platform](docs/PLATFORM_NEUTRAL_NODES_PLAN.md).
- [Theme Platform v2](docs/THEME_PLATFORM_V2_PLAN.md).
- [Public Web boundary](docs/PUBLIC_WEB_EXTENSION_PLAN.md).

Final rule: Core knows verified identity/source, contracts, approved rights,
lifecycle and health without knowing an extension's concrete business.
