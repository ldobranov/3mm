# M20 — Core-reconstructed installed policy subjects

Date: 2026-10-09. Status: **implemented locally, internal read-only prerequisite**.
This follows the [installed sources](EXTENSION_PLATFORM_V2_SOURCE_RESOLVER.md),
[private review keys](EXTENSION_PLATFORM_V2_REVIEW_KEYS.md) and
[pure policy evaluator](EXTENSION_PLATFORM_V2_POLICY_EVALUATOR.md).
It does **not** deliver an authentic positive policy/native-provenance source,
approval or runtime enforcement. Scope is the common Core, not Fleet-only.

## Supported boundary

[resolve_installed_policy_subject](../backend/services/application_authority_subjects.py)
accepts only the trusted Core Engine, installation ID and host-controlled package
storage/version/private-key settings. No caller manifest, configuration, principal,
resource revisions, policy or authoritative subject snapshot is accepted.

1. Pin the actual installed package, read and validate its digest-named ZIP outside
   the final database transaction, then recheck the pin in that transaction.
   The candidate is **the installed artifact only**, not a proposed update or a
   new-install reservation. The catalog's arbitrary path/manifest is not authority.
2. Read guard, Core/application identity, epoch/mode, full saved configuration and
   actual command/connector sources through the existing dedicated read snapshot.
   Never use a caller Session/cache, configuration defaults or missing metadata
   repair. Do not select/decrypt credential values.
3. Require the real selected provider/module action contract. Compare its validated
   argument schema with the binding using typed canonical exact equality. Normalize
   only known set order (`required`/property `enum`); reject duplicate enum values.
   Both wider **and narrower** schemas remain unsupported: this is not general
   schema containment. Sensor identity is not a resolved passage/sensor contract.
4. Hash the actual command control evidence: target/control generation, active
   credential IDs, runtime/features/revision, selected provider or module digest,
   contract digest and selected action schema. Connector evidence keeps the real
   owned binding revision/origin and credential reference/kind/version.
5. Read the existing protected Core/recovery-bound key under its real POSIX file
   checks and nonblocking lock. Bind its Core identity/recovery generation to the
   **same database snapshot**, not an independent key-store database read. HMAC
   the entire validated private configuration, never a selected/public projection.
   This read does not create, rotate or recover keys. Non-POSIX hosts fail closed;
   no simulated ACL claim or fallback hash is used.
6. Revalidate the strict bounded policy subject and preserve unsupported scope,
   peer, dependency, executable-frontend and isolation blockers. Any missing,
   foreign, stale, corrupt or unsafe source/key returns **no partial subject** and
   only bounded reason codes, never raw private input/errors.

The output always has `subject_scope: installed_artifact_only`, `reviewable: false`
and `permission_approval: not_evaluated`. Even when all supported subject sources
resolve and no source blocker remains, `policy_evidence_unavailable` remains.
It cannot mint grants, native trust, approval or a reviewable context fingerprint.

## Snapshot is not authorization

The source reader's SQLite/PostgreSQL boundaries remain unchanged. Artifact I/O
precedes the final read snapshot. The key is locked only while fingerprinting;
the database and file lock are released before returning historical evidence.

A key rotation or authority writer after that point can invalidate this evidence.
Approval/apply must coordinate guard/key changes, re-resolve current sources,
recheck the current actor and record audited decisions atomically. None of those
mutation coordinators is implemented here. Live PostgreSQL/recovery/file-replacement
acceptance remains open; SQLite snapshot consistency is not effect admission.

A parsed `PolicySubjectV1`, including one received from a caller or stored as
negative-only [review history](EXTENSION_PLATFORM_V2_POLICY_REVIEW_STORE.md), is
**not authenticated provenance**. This composer is not yet a production caller
of that store, a trusted evidence producer, or a positive-policy verifier. Current
SDK 1.3, API routes, runtime dispatch and compatibility mode are unchanged.

## Verification

[Focused tests](../backend/tests/test_application_authority_subjects.py) use real
validated ZIP bytes, file-backed SQLite WAL and actual protected Linux key files.
They cover saved/full private configuration, key rotation, exact schema comparison,
provider/runtime/credential/binding drift, unsafe/foreign/stale/corrupt keys and
resources, sensor non-inference, package-pin drift, non-POSIX refusal and a headless
command/connector subject that still cannot authorize without authentic policy.

An independent SQLite writer commits configuration, secret version, application
epoch and connector revision between snapshot reads. The reader returns the whole
old subject/HMAC/guard; a fresh call returns the whole new state. Key contention
is tested during actual fingerprinting. SQL tracing excludes private credential
columns; pending caller work, protected key bytes and filesystem state stay intact.
No network call, package execution or data mutation is allowed by the reader.

Local targeted runs (overlapping, **not a full release suite**):

- Linux subject/key/source suites: **123 passed, 3 skipped**, 7 warnings, 26.57s.
  Skips: two non-POSIX cases and the foreign-UID key case requiring disposable root.
- Windows subject/key/source/policy/review-store suites: **197 passed, 42 skipped**,
  276 warnings, 29.34s. POSIX key checks run on Linux, not emulated on Windows.

Python compilation, scoped whitespace and local Markdown target checks passed.

No schema migration, auth change, public endpoint, frontend/build, commit/push,
release, live mutation or deployment is included. Next is protected authentic
Core-owned positive-policy/native-provenance evidence with guarded invalidation
and key/actor coordination; staged candidates, approval/apply, other scope adapters
and OS/browser/effect enforcement remain separate gates. WP4/WP5 are not complete.
