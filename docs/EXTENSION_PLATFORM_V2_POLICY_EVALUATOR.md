# M20 — bounded internal Core-policy evaluation / WP4

Date: 2026-10-08. Status: **pure evaluator implemented locally**, not a trusted
policy store, evidence verifier, approval API or runtime authorization change.
The [installed-source resolver](EXTENSION_PLATFORM_V2_SOURCE_RESOLVER.md) still
reports `policy_evidence_unavailable`; this step deliberately does not clear it.
SDK 1.3, current compatibility workloads and production callers are unchanged.

Scope: common Standalone/Hub Core. Fleet, packages, devices, generators and cloud
services cannot supply local authorization policy. No concrete extension names,
hardware branches, frontend changes, database changes or network dependencies.

## 1. Why this is separate from context validation

The [context validator](EXTENSION_PLATFORM_V2_CONTEXT_VALIDATOR.md) consumes an
already resolved `AuthorityPolicy`. It cannot establish that an allow set really
came from Core or that an arbitrary proof revision is authentic. The new internal
[policy evaluator](../backend/services/application_authority_policy.py) fixes the
bounded comparison semantics for the **future** trusted policy/evidence adapter.
It is not that adapter or a replacement for its source verification.

Its inputs are explicitly trusted internal snapshots, not a public/wire schema:

- `PolicySubjectV1`: resolved principal, exact candidate and active baseline,
  keyed full-configuration identity, recovery generation, command/connector
  resources, executable-frontend presence and existing source blockers.
- `CorePolicyEvidenceV1`: a separately Core-owned exact binding, durable policy/
  trust/profile/native-review revisions, execution classification and concrete
  whole-resource rules. These revisions have no automatic defaults.

**Parsing or constructing either model does not authenticate it.** A caller
which fabricates evidence can fabricate a successful pure comparison, not actual
authority. No route, UI checkbox, manifest field, production resolver hook,
evidence writer, automatic compatibility conversion or approval issuer is added.
The synthetic positive fixtures do not claim any real package has been reviewed.

## 2. Implemented comparison

| Input/change | Evaluator behavior |
| --- | --- |
| Missing policy, unknown/revoked artifact trust or absent native review | No resolved policy; bounded reason, no allow set |
| Different Core/application/incarnation/module, artifact, active baseline, configuration key/HMAC or recovery generation | Exact binding mismatch; no partial policy |
| Changed device/control/sensor, contract/action/schema/TTL | Exact command rule mismatch |
| Changed connector owner/origin/binding, path/mutation/limits, credential reference/version/revocation | Exact connector rule mismatch |
| Policy rule refers to a disappeared resource | Stale rule; no partial policy |
| Declared resource has no policy rule | Not allowed; never derive permission from the declaration |
| Explicit empty rule set | Empty allow set, not a wildcard |
| Required rule omitted from later selection | Existing context validator rejects it |
| Existing configuration/peer/dependency/unsupported-family/proof blocker | Preserved; matching policy cannot clear it |
| Executable frontend flag or built-UI identity | Frontend remains unresolved even for native evidence |
| `proven_isolated`, with or without a nonempty proof revision | Denied: no accepted isolation verifier exists here |

The only comparison profile supported in this slice is
`supervised_reviewed_native_v1`, with explicit `reviewed_local_artifact` trust and
an exact native-review revision. It names the evaluator's proposed native policy
classification, **not** a newly installed/verified OS profile. It is not proof of
cross-instance isolation, resource limits or publisher identity/signatures. It
cannot lower an isolated-runtime requirement to native: source blockers remain
binding. Production acceptance of native provenance still requires the missing
Core-owned source/decision adapter, not an administrator checkbox or package label.

Selection remains whole supported bindings or omission; this does not implement
JSON-Schema containment, narrower path/range/TTL grants or optional-feature runtime
semantics. Unknown fields, wildcard IDs, duplicate rules/enums, malformed versions,
coerced values, oversized inputs and constructed-model validation bypasses fail
closed. Reasons do not echo configuration, origin values or credential references.

## 3. Identity and result limits

Successful output supplies only an internal `AuthorityPolicy` for subsequent
context/selection validation. `reviewable` remains **false** and
`permission_approval` remains `not_evaluated`; there is no plan fingerprint,
approval, signing token, active grant or execution permit.

Effective policy identity is a domain-separated digest over the bounded typed
evidence and the actual evaluator semantics version. It includes every supplied
policy/trust/profile/native-review revision and exact binding/rule, so keeping an
outer revision string unchanged cannot hide a changed evidence record. Known
sets are canonicalized consistently with the context model; typed numeric values
are not compared using Python's `1 == 1.0` equality. The fixed synthetic vector is
tested. This internal digest is **not** proof that a store was authentic or fresh.

Private configuration enters only via its separately keyed identity, not raw
values or an unkeyed password hash. No file/DB/process/network I/O or implicit
clock occurs here. Source completeness, resource validation, actor verification,
durable approval, apply races and effect admission remain independent checks.
The evaluator does not establish ownership merely because two snapshots agree;
the existing context validator and actual source adapter must still verify it.

## 4. Remaining integration gate

Before any positive policy can be used in production, implement/accept:

1. A protected Core-owned durable policy/native-provenance source with authenticated
   decision/audit, exact artifact ownership, non-reused revisions and guarded
   invalidation/revocation. Never backfill grants or native reviews from manifests.
2. Re-resolution of that source in the same authoritative subject snapshot, plus
   the private key, staged-candidate and complete declaration adapters. Missing
   producer/verification remains a blocker, not a synthetic default.
3. Freshness/recovery/apply coordination and the separate approval/actor contract.
4. Actual supported-host OS/browser/resource evidence before any isolated or
   remote/untrusted executable path; no nonempty-string proof substitute.

Subsequent local foundation: [Core-private review history](EXTENSION_PLATFORM_V2_POLICY_REVIEW_STORE.md)
persists pending snapshots and authenticated negative decisions only. It is not
the positive policy/native-provenance producer in gate 1 and cannot clear missing
evidence, return `CorePolicyEvidenceV1`, approve grants or reopen revoked reviews.

This slice does not wire a positive policy into existing workloads, change grants,
advance DB authority, start code or submit connector/device actions. It does not
make M20/WP4/WP5 complete or ready for untrusted distribution.

## Verification

Targeted Windows regression: **250 passed, 23 POSIX-only skips, 9 warnings**
(20.40s), covering policy/context/source/key/recovery primitives. The new policy
suite also passed under WSL/Linux: **68 passed, 5 warnings** (6.05s), using the
existing Python with disposable test dependencies; no live dependency changes.
Python compilation, local Markdown targets and whitespace checks passed.

Fixtures are synthetic; no live policy, isolation, PostgreSQL, device or connector
acceptance is claimed. No full release suite, frontend build, deploy, commit/push
or release is part of this backend-only step.
