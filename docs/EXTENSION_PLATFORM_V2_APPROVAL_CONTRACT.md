# M20 — explicit application authority approval contract

Date: 2026-10-08. Status: **design draft for owner review**, following the accepted
read-only authority UI. This document defines intended semantics, not a supported
wire schema, implemented grant store, new API or production security guarantee.
No DB, SDK 1.3, runtime, installer or live policy changes belong to this step.
The subsequent owner-approved [pure internal validator slice](EXTENSION_PLATFORM_V2_CONTEXT_VALIDATOR.md)
is implemented locally; it does not implement this document's approval lifecycle.

Implementation update, 2026-10-09: the bounded installed-only reviewed-native
command/connector cycle is now local. This document remains the wider design;
use the [delivery report](EXTENSION_PLATFORM_V2_AUTHORITY_APPLY.md) for actual API,
operator sequence, tested guarantees and remaining adoption/isolation gates.

Scope: the common Standalone/Hub application platform. Fleet, cloud, a registry,
publisher or generator cannot approve local authority on behalf of Core. The
first adapter is for supervised applications; other package types retain their
existing adapters and cannot be forced through a fake application installation.

## 1. Reuse and distinctions

- Existing [human grants](../backend/db/module.py) (`ApplicationPermissionGrant`)
  assign application permissions to users. They are **not** service resource grants
  and must not be renamed or repurposed. Human/terminal access remains independent.
- The [command epoch and one-use permit](../backend/services/application_commands.py)
  already fence physical commands. A future application authority generation must
  integrate with them, not introduce a competing command queue or bypass permits.
  The current command epoch does not already cover connectors, events or storage.
- [Connector bindings](../backend/services/application_connectors.py) and
  [secret references](../backend/services/application_secrets.py) already belong to
  an installation. Rotation increments `ApplicationSecretReference.version`;
  reuse that actual version, ownership and revocation state, not a secret hash
  or an invented client-supplied credential generation.
- [Read-only inspection](EXTENSION_PLATFORM_V2_AUTHORITY_REVIEW.md) compares
  declarations. Its fingerprints, `previous_declarations` and
  `declaration_review_required` are **not** approval identity or approved policy.
  It does not resolve actual stored connector bindings or credential versions.

Separate three concepts: validated package requests, locally selected grants,
and current authority to perform one effect. An approval is necessary in the new
enforced mode, but not sufficient: current device, actor, broker and runtime
checks may still deny an action. No package field can self-assert approval.

## 2. Core-owned review context

The future review context must be reconstructed by Core from authoritative data,
not accepted as a client-authored manifest/configuration/grant snapshot. Its
semantic components are:

| Component | Bound information |
| --- | --- |
| Principal | Local Core installation identity, logical application installation identity and incarnation, module ID; a reusable DB integer alone is insufficient |
| Candidate | Exact version and ZIP digest, validated descriptor contracts, SDK/runtime entrypoints; built executable/UI artifact identity when relevant |
| Baseline | Actual active artifact, approved-grant revision or explicit absence, current authority epoch and enforcement mode; never latest catalog version |
| Configuration | Exact validated effective configuration identity plus resolved authority projections; supplied defaults alone are not effective bindings |
| Resources | Selected device identities/contracts/control authority; actual stored connector origins and credentials with ownership/version/revocation; other resolved scopes |
| Policy | Core-selected execution profile and policy/adapter revisions, required proof status and relevant trust revision; resolved dependency artifact pins when supported |
| Selection/lifetime | Exact proposed grant subset and bounded review-plan lifetime |

The approving actor and local decision/audit identity are separate immutable
evidence over this plan, not self-referential inputs to its digest. They do not
change the reviewed resource context or turn a client identity into authority.

Use existing logical IDs; a package-dependent runtime instance is not the stable
logical principal. A fresh incarnation/epoch prevents deleted/recreated rows or
restored revisions from reusing an old decision. Concrete DB representation is
selected in the persistence slice with a non-destructive migration.

Package requests and effective bindings must agree with stored broker records.
For example, a configured connector origin/reference does not supersede its
stored binding. Missing, foreign, revoked, inconsistent or unsupported inputs
stay unresolved and cannot become active grants. They may permit staging a
package without activation; they never imply any-device/any-origin access.

Full configuration and credentials are not returned in a plan or audit. Use an
installation-local keyed fingerprint for private effective configuration, with
versioned key identity and explicit invalidation on key rotation. Never publish
raw secret values or unkeyed hashes of passwords/low-entropy private settings.
The grant stores opaque secret references and their actual versions only.
Default to invalidating on any effective configuration change; excluding a field
requires a proven, versioned cosmetic-only contract, not a guessed key name.

No unresolved peer authority, same-origin executable UI or missing isolation
proof can be cleared by an administrator clicking a generic checkbox. Existing
reviewed-native execution is a separate Core-owned compatibility policy, not a
sandboxed grant or a means of enabling arbitrary untrusted code.

## 3. Grant scopes and safe subset rules

The conceptual scope key is installation + resource kind + existing declaration
ID. IDs resolve through existing brokers; they are not paths or new hardware APIs.
The initial typed model should support exact declared device-command and connector
scopes or their omission. Wider scope families below require their own accepted
adapter; unsupported families are not silently treated as implemented.

| Scope family | Authority that must be explicit |
| --- | --- |
| Device command | Binding ID, concrete device ID, capability/contract/action, validated argument/channel bounds, TTL and any sensor identity/direction |
| Connector | Connector ID, actual bound plain origin, allowed methods/path policy/mutation flag, authentication kind, owned secret reference/version, request/response/deadline limits |
| Events | Subscription/publication ID, event/capability, concrete device/producer ownership scope, handler/cursor/backlog limits; no global stream inferred |
| Private storage | Own logical installation namespace, access mode, quota/schema/lifecycle requirements; never raw host paths or foreign/Core DB |
| Jobs/platform/peers | Exact declared operation and service scope; exact approved peer binding/generation when supported, never cloud/fleet-wide authority |
| Runtime/UI | Core-owned approved execution/build profile and limits; explicit native/isolation classification, never arbitrary spawn/root or inferred browser safety |

Human route/operation audiences and public HTTP exposure are authority-relevant
review inputs, but resource grants cannot assign user roles, elevate a session,
invent a human actor or bypass application access. Background jobs need an
explicit service context, not an administrator impersonation.

Selected grants must be a subset of both the validated requests and Core policy.
Initially, select whole supported resolved bindings or omit them. Narrower
channel sets, ranges, TTLs, paths or schemas require a typed subset validator and
tests; there is no general JSON-Schema containment or path-prefix proof. Unknown
keys, duplicate IDs, unsupported contracts, invalid values and omission-as-wildcard
are rejected. An omitted required grant blocks the dependent effect/activation;
an optional feature may remain unavailable only if its adapter defines that mode.
Removing a declaration cannot leave an active orphaned grant.

Device scopes depend on provider-neutral identity and invocation contracts, not
Linux/firmware/provider names. Offline/unavailable is an operational denial, not
a broader grant. Re-evaluate live control authority and compatible contracts at
dispatch. Origin approval alone is not TLS service identity, DNS/redirect safety
or OS network isolation; current broker and future destination-policy checks
remain independent and may deny the request.

## 4. Plan identity and approval lifecycle

A plan is an expiring review snapshot, **not a bearer execution token**. The
future bounded, closed, independently versioned model must define canonical
encoding and a domain-separated digest before persistence/API export. Sort
object keys and explicitly set-valued fields; preserve ordered sequences. Fix
number/string/null/absent semantics, reject non-finite numbers, duplicate raw
keys, unsupported versions and oversize inputs. A JSON dump or inspection
fingerprint alone is not the canonicalization contract. Cosmetic labels and
heartbeat/last-seen/status telemetry do not enter authority identity.

Approval evidence is an immutable decision over the exact plan, selected subset,
actor and observed baseline/epoch. Core verifies the actor's current approval
permission again at decision time; an application service, device token or client
user ID is not an approving actor. Repeating the same decision is idempotent;
the same request identity with changed content is a conflict. Approving a plan
does not itself run code, migrations, connector calls or physical commands.
Expiry or a clock rollback/restart cannot renew the original review lifetime;
the persistence slice must define a tested clock policy alongside epoch checks.
Cancellation/denial of a candidate leaves the valid running policy unchanged.

Conceptual states distinguish review-required, approved-pending-apply, current,
stale, denied and revoked. These are semantics, not finalized API enum names.
Approving a staged update does not replace the running version's grants. Apply
must revalidate the exact snapshot and compare-and-swap the observed baseline.
Only successful apply promotes the artifact/grants and allocates a fresh active
authority epoch. Record both the observed and resulting epoch; do not mutate
the approved plan/hash to make it appear to have been reviewed against new state.
The future lifecycle journal must fence file/DB/runtime transitions and recovery.
Re-enable/resume cannot mark a stale decision current by flipping a flag. Prior
selected scopes may seed a fresh local resume review, never replace current
actor/context verification or revive revoked authority.

At effect admission, require current installation/artifact, current grant and
epoch, exact matching resolved scope, Core-verified actor/service context and
existing broker checks. No authority is cached solely because the process started
successfully. Queueing records authorization context; dispatch/physical permit
consumption rechecks it. An old request ID cannot be recycled into a new effect
after a reapproval or target change; historical lookup retains original identity.

Audit records approval/denial, apply, invalidation, revoke and recovery outcomes
with authenticated actor, logical subject, exact plan/artifact, observed/resulting
epochs, correlation identity and bounded reason codes. Never log configuration,
credential plaintext or unsanitized package errors. Retain decision history and
tombstones under Core audit/retention policy, independently of application data;
uninstall or deleting a user cannot silently turn evidence into current authority.

## 5. Invalidation and concurrency

| Change | Required treatment in enforced mode |
| --- | --- |
| New artifact, including fewer rights or cosmetic-only code change | Fresh exact-artifact review/apply; never reuse old approval because diff is empty |
| Effective configuration, target/sensor identity, connector origin/reference/version or scope/limits change | Stale related plans/authority; fresh review, no same-key exception |
| Grant revocation/reduction, disable/uninstall, changed execution/trust policy | Fence new affected effects and invalidate old queued authority/plan baseline |
| Device/peer trust or control ownership revoked; incompatible capability contract | Deny affected dispatch immediately; invalidate dependent context as required by the adapter |
| Heartbeat, last-seen, connector last outcome, health telemetry, UI language/labels | No approval churn from telemetry; current operational checks still apply |
| Restart without authoritative-state change | Preserve valid durable authority, not stale in-memory approval |
| Restore, reinstall incarnation or policy rollback | Fresh epoch/context verification; never resurrect superseded/revoked authority |

Authority writers and effect admission need one documented per-installation
fence/lock order plus resource revisions/CAS where resources can change
independently. Configuration, lifecycle, grants, connector rebind, credential
rotation/revocation, trust and device/peer authority paths all participate. An
`updated_at` check or UI warning is not a concurrency boundary. Existing command
epoch/permit checks remain mandatory and must be invalidated in the same coherent
transition; do not replace them with a snapshot-only approval lookup.

Revocation wins if committed before the effect's durable admission point. If a
connector dispatch or one-use physical permit was already admitted, its effect
may still occur; do not promise revocation can recall it. Do not hold a DB lock
through network I/O. Persist admission/evidence before dispatch, preserve the
existing command TTL/idempotency/one-use rules and treat lost responses as
uncertain. Revoke/restart/rollback/reapproval must never auto-replay them. ABA
changes (A → B → A) need a new epoch even if final fields/digests match again.

## 6. Existing installations and recovery

This design changes no running installation. The later rollout must preserve
IDs, SDK 1.3, data, configuration, versions, human access, module installations,
event cursors, command identities and job quarantine. Do not bulk-create grants
from old manifests or human permission rows, and do not stop existing services
merely because a new approval record is absent.

A non-destructive migration records an explicit Core-owned compatibility mode
and actual provenance/current artifact for existing reviewed installations. It
is not a wildcard grant, a sandbox claim or a package-selectable fallback. New
code cannot opt into it; any later trusted-native compatibility activation needs
an explicit local policy decision for the exact artifact. New enforced-mode
applications stay staged/denied without supported complete scopes and approval.
Compatibility retirement requires an accepted migration/recovery window, not a
silent Core update. Remote/untrusted execution remains blocked by WP5 proof gates.

Per-installation adoption uses the existing mutation lock, quiescing and verified
backup, then resolves/reviews/apply-fences all required effects for that adapter.
No halfway mode in which missing new grants fall through to the old policy. On
failure, recover the coherent prior policy/code/data or a clear review-required
disabled state; never silently widen rights or lower an execution classification.

Backup/portable restore retains decisions and audit as evidence, not automatic
live authorization. Restore verifies local identity, artifact, resources and
credential ownership/versions and allocates a fresh epoch after restoring state.
A foreign installation's approval or backed-up integer/OS UID cannot authorize
local effects. Historical revoked decisions cannot become current after restore.
Restore/reapproval does not release uncertain command/job claims or move event
cursors to replay external work.

Authenticated Core admin audit/export/backup/recovery/uninstall remains available
under its own policy. Preserve narrowly scoped owned historical lookup such as
`command.lookup` after disable; this is not permission to submit new commands.
Recovery exceptions are named operations, never a blanket extension bypass.

## 7. Acceptance matrix for later implementation

These are required future tests, **not tests run or passing in this design step**:

1. Two applications cannot reuse each other's approval, credential, device scope
   or local/foreign installation identity; a service cannot approve itself.
2. Candidate/default/configured origin differs from stored binding: unresolved,
   no grant. Same reference with rotated version/revocation requires fresh context.
3. Exact binding selection succeeds; unknown/wider arguments, channels, TTL,
   origin/path/method, storage namespace or peer scope fail before effects.
4. Human and kiosk audiences still apply with a valid service grant; background
   work cannot forge a human principal or acquire Core administrator access.
5. Deterministic bounded canonical vectors cover key/set ordering, ordered
   sequences, numbers, duplicate keys, null/absent, private-config redaction and
   unsupported versions; inspection markers cannot be submitted as approvals.
6. New digest with no scope changes, removals, expired/stale plans and A → B → A
   cannot reuse a decision. Duplicate decision requests cannot create two applies.
7. Change/disable/revoke/rotation between review, approve, queue and dispatch
   denies the stale operation under concurrent processes, not just mock snapshots.
8. Approval of a staged version leaves active grants unchanged. Apply crash or
   restart reconciles a coherent journaled artifact/grant/epoch state.
9. Already-admitted POST/physical permit with a lost response remains uncertain;
   fresh approval does not replay it or release scheduler quarantine.
10. Non-destructive migration and adoption failure retain current compatibility
    behavior/data; an enforced installation cannot fall back when a grant is missing.
11. Same-install and foreign portable restore cannot resurrect authority; fresh
    local review/epoch and historical audit/lookup remain possible offline.
12. SDK 1.3, Standalone/local Agent and Hub/Linux/embedded consumers retain their
    existing contracts; no concrete extension/provider branches are introduced.

## 8. Next bounded implementation decision

The owner-approved internal pure, versioned typed context/selection validator and
canonical test vectors for device commands/connectors are now implemented locally;
see [exact scope and limitations](EXTENSION_PLATFORM_V2_CONTEXT_VALIDATOR.md).
It accepts only trusted resolved snapshots, returns reviewability/reasons and
cannot mint executable approval or substitute for WP5 isolation. The next bounded
decision is the actual Core resolver/writer-invalidation map and durable
identity/revision/configuration-key ownership, not a client-authored snapshot API.

Only after that separate approval: persistence + Alembic migration/migration
tests, generation integration/audit and migration classification. The approval
API/UI and lifecycle/effect enforcement follow as separate scoped slices. Before
enforcement, accept the full writer/invalidation map, dispatch linearization,
supported-host two-instance isolation and existing-install recovery proof. Do
not export a public signing/wire schema or change SDK versions prematurely.

Verification for this step: source/design consistency review and local Markdown
link/whitespace checks only. No new security guarantee, automated-suite claim,
frontend change/build, live device/connector operation, commit/push or release.
