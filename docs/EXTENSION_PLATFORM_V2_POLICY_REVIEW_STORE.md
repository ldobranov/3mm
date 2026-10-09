# M20 — Core-private policy review history / WP4

Date: 2026-10-08. Status: **implemented locally, negative decisions only**.
This is a durable review-history foundation, **not a trusted policy/native-
provenance source**, approval issuer, active grant store or runtime enforcement.
No route, UI, CLI or production caller is wired to it. SDK 1.3 and existing
compatibility workloads remain unchanged.

Scope: the common Standalone/Hub Core, not Fleet-only. Packages, devices and cloud
services cannot supply authorization policy through this internal service.

## Persistence and boundaries

[The store](../backend/services/application_policy_reviews.py) records a bounded
`PolicySubjectV1` snapshot with Core/application/incarnation, installed artifact,
baseline, keyed configuration identity, resource references and recovery binding.
It rechecks actual installed ownership, artifact metadata and authority under the
database guard. Only the currently installed candidate is supported here.

**Recording does not authenticate the subject's configuration HMAC, complete
resource claims, artifact bytes, publisher or native-review provenance.** It
cannot turn caller-supplied data into `CorePolicyEvidenceV1`. Its domain-separated
canonical digest detects a changed snapshot; it is not a signature or proof of
trust. The trusted composer, key coordination, staged candidates and authentic
positive evidence source remain separate work.

The [two Core-private tables](../backend/db/application_policy_review.py) contain
the historical subject/head and append-only-through-service decision records.
No raw login token or private configuration values are put in review receipts or
audit rows. Session attribution uses historical numeric IDs and a domain-separated
token digest. The private subject contains resource metadata; it is not a public
history/export response. No root/DB-administrator tamper-proof claim is made.

Permitted transitions are deliberately small:

- Record → `review_required`.
- `review_required` → `denied` or `revoked`.
- `denied` → `revoked`; `revoked` is terminal.

There is no approve, reopen, grant or activate operation. Database checks also
reject positive states/decision kinds. Here **revoke means withdrawing a pending
review**, not revoking a running application's existing permissions or stopping
its process. The installed application's epoch, mode and physical command fence
are not changed. Only the singleton guard revision advances for a new review
mutation; exact retries advance nothing.

## Authenticated, atomic mutations

Every write and exact retry requires a real signed, unexpired human login token
with an explicit session and token version. Under the guard the service locks and
rechecks the actual account's current administrator role, blocked state and token
version, then its active matching session, ownership, token and expiry. Claimed
roles, caller user IDs, sessionless compatibility tokens and device/kiosk tokens
are not review-write authority. Existing global authentication APIs are unchanged.

The lock order is guard → user → session → application → review. The service
requires its own clean caller Session. Live checks, head compare-and-swap, audit
append and guard revision commit together; an audit failure rolls everything back.
No package code, network access, helper call or external action runs inside this
transaction. Subject resource/configuration claims are still unverified even when
the administrator is authentic.

A unique request ID binds the operation/content and actual actor/session. A retry
by that same still-authorized session returns the original decision and **current
review head**, so a later denial/revocation is not hidden. Different content,
operation or actor conflicts. Concurrent duplicate records commit one review/audit;
competing transitions have one winner. No uncertain external action is replayed.

The internal status reader uses a dedicated consistent read-only snapshot. Missing
metadata, malformed subject, digest mismatch or broken bounded audit lineage fails
closed; reads never create/repair keys or authority. Status contains IDs/revision,
state and `recovery_binding_current` only. That flag checks **Core identity and
recovery generation**, not current configuration/resource/artifact freshness.
`reviewable` stays false and `permission_approval` stays `not_evaluated`.

## Migration, retention and recovery

Migration `c9d128d9e0f1`, after `b8c017c8d9e0`, creates empty review/audit tables.
It does not backfill approvals, grants or native trust and does not change existing
application/device/credential data or the guard. Runtime model imports are not
used for migration discovery or frozen DDL. Legacy precreated tables must match
the frozen column types/nullability/defaults/primary keys, checks, uniqueness and
foreign keys. Partial or weakened schemas stop without repair or erasure.

Historical user/session/application IDs deliberately have no live cascading
foreign keys. Deleting those live objects retains attribution and review history;
the only history FK links a decision to its review, without cascading deletion.
Empty-table downgrade is supported. Once history exists, destructive downgrade is
refused: use the verified pre-upgrade backup/recovery procedure instead of silently
discarding records.

Existing offline recovery rotates authority generations and retains these rows.
Old reviews become recovery-stale; retries do not renew/rebind them. Explicit
negative cleanup of same-Core history is allowed but leaves its original binding
stale. A different Core identity cannot mutate/replay that history as its own.

The stdlib [offline recovery helper](../deployment/authority_recovery.py) now
recognizes legacy missing metadata using a frozen set of pre-authority migration
ancestors, not equality with one historical head. New/unknown revisions or partial
review metadata cannot silently enter legacy fallback. No SQL deletion or uncertain
command/job replay is introduced.

## Verification and remaining gate

Targeted Windows checks: **113 passed** (45 store/auth/atomicity tests plus 68
pure-policy regressions); migration/authority/recovery checks: **59 passed**.
After strict precreated-schema validation was added, the complete migration suite
was rerun: **10 passed**, including four additional weakened-schema cases.
This gives **176 distinct passing targeted Windows tests** across these checks.
The 45 store tests also pass under WSL/Linux with disposable test dependencies.
Actual two-connection SQLite races, populated upgrade, current model parity,
history retention, rollback, stale recovery and fail-closed reads are covered.
Python compilation, local Markdown links and whitespace checks pass.

No live PostgreSQL, Raspberry recovery, positive policy/approval, isolation or
external effects are accepted by these tests. No full release suite, frontend
build, deploy, commit/push or release is included in this backend-only step.

Next: a protected, authentic Core-owned policy/native-provenance producer and
coordinator, with exact subject/key/resource re-resolution and guarded invalidation.
Then staged-candidate/approval/apply integration. Merely persisting a review or
adding an administrator checkbox must never clear
`policy_evidence_unavailable` in the
[installed-source resolver](EXTENSION_PLATFORM_V2_SOURCE_RESOLVER.md) or bypass
the [pure evaluator's remaining gates](EXTENSION_PLATFORM_V2_POLICY_EVALUATOR.md).
