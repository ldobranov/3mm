# M20 WP4 — bounded existing public installation identity read

Date: **2026-10-16**. Local implementation and targeted integrated verification
are complete; owner visual/live acceptance is **pending**. This is not a release,
deployment, VM acceptance or closure of WP4. Existing checkpoint and accepted
beta.51 SQL evidence remain separate and unchanged.

## Scope and compatibility

This slice supports only reading the **already initialized whole-Core public
identity**. It is not an Agent/device identity, an application-generated identity,
private-key availability check, possession proof, peer/cloud ownership or human
administrator permission. Core does not know a concrete application by name.

The existing application descriptor and public SDK method are reused:

| Layer | Exact declaration / operation |
| --- | --- |
| Application descriptor v1 | `service.sdk_version: "1.3"`; `platform_permissions` includes `installation.identity.read` |
| Module Manifest v2 | Matching `installation.identity.read` permission; normal exact permission validation still applies |
| Reviewed service resource | `platform:installation.identity.read` |
| Existing signed SDK call | `ApplicationPlatformClient.get_installation_identity()` → `installation.identity.get`, no identity/owner/path input |

The declaration is only a request. An exact local native review and separate
review → approve → apply are still required. Read permission does not authorize
`installation.identity.prove`, peer enrollment/approval/rotation/revocation/reporting,
status projection, jobs, public routes, compiled UI or a frontend host bridge.
Packages containing unsupported families still fail closed, including when the
caller selects only an otherwise supported scope.

No SDK-major, application/manifest version, new database model or migration is
introduced. Legacy SDK 1.1–1.3 identity/proof APIs in **compatibility mode** keep
their existing initialization, encrypted-key and error behavior. This slice does
not silently adopt old installations or enable scoped identity access for old
SDK declarations.

## Exact internal binding

Internal context/selection/subject/policy version **7** adds at most one
Core-resolved identity resource. Earlier versions retain their original shape
and canonical identity; an absent identity declaration contributes no synthetic
identity scope. Version 7 may carry supported checkpoint/file/relational resources
alongside identity without granting one family from another.

The resource contains only:

- `owner`: Core installation, application installation/incarnation and module ID;
- `package_artifact_sha256` and exact operation `installation.identity.read`;
- `identity`: `identity_version`, `installation_id`, `algorithm`, `key_id`,
  `public_key`, `key_generation`, `created_at` — all seven public fields, validated
  together, not a key ID supplied by the application.

The public key's digest must match `key_id`; identity belongs to the same Core as
the application principal. The current native/artifact/configuration/recovery
binding and separate applied grant remain authoritative. Core review-key drift,
public identity/key drift, package/configuration changes, foreign incarnation,
recovery generation, revoke or inactive installation must refuse new scoped reads.
An old apply receipt cannot restore access. The returned actual Core/runtime
version is response metadata, not a new key identity or an application-selected
authority target.

## Existing-public-only read boundary

`backend/services/installation_identity.py` adds
`read_existing_installation_identity(db)`. It projects **explicit public SQL
columns**, not the ORM entity or `encrypted_private_key`; normalizes SQLite's
stored UTC timestamp; and validates the public binding. Missing or corrupt
identity is a bounded refusal, never a request to create, rotate or repair it.

The helper uses no `_cipher`, private-key decrypt/sign/generation,
`_load_or_create`, autoflush, commit or rollback. Its caller owns authorization and
transaction lifetime. A public-only result does not claim that an encrypted
private key exists, decrypts or can sign. Compatibility identity/proof behavior
is deliberately not rewritten to this public-only interpretation.

The scoped adapter rechecks the exact current grant and authenticated instance
under the existing Core key/authority/application admission boundary. It returns
the typed public resource from that revalidated grant, without another identity
lookup or private-key read; its guard transaction ends before key release.
Conditional DB locking used to serialize authority is not identity initialization
or a new grant. No network request, helper/process start, cloud consent, identity
setup, proof generation or automatic permission retry belongs in this operation.

Existing SQL start consent explicitly accepts exact internal versions 5/6/7, so
a supported mixed SQL/identity request can retain its separately authorized
prepared lifecycle. This does not add a lifecycle entry point: start still
requires its independent one-use consent, begin fences old runtime authority,
and successful start remains `active_review_required` until fresh permission
review/apply. Unknown or coerced versions remain refused.

## Verification and delivery status

Final local checks passed on the same production source:

- **403 distinct native Linux tests** on disposable WSL Ubuntu/Python **3.14.4**:
  main non-root run **296 passed / 15 Root-only skips**; a separate actual Root
  run executes exactly those **15 cases**, without skips; a disjoint compatibility
  run passes **92 cases**, including mixed v7 identity/checkpoint reads. JUnit
  confirms no duplicated passed cases or uncovered Linux skips. Logs/XML are
  retained under `.runtime/m20-identity-verified-{linux,root,compat}.*`.
- Windows/Python **3.13.15** protocol/SDK/context/identity compatibility matrix:
  **1119 passed / 45 POSIX-specific skips**. This overlaps Linux coverage and is
  not added to its unique count. Earlier focused runs are also overlapping.
- Full frontend suite: **357 tests / 47 files**, TypeScript check and production
  build passed. The focused 83-case run is included, not additional coverage.
- Isolated browser fixture: desktop Slate Copper/light/EN, Graphite Mint/dark/BG
  and **390 × 844** mobile dark/BG. Exact public fields, expanded owner/package
  bindings, long-key wrapping and disabled approval before acknowledgment were
  checked. The mobile card has equal client/scroll width (276px). Valid images
  are `.runtime/m20-relational-ui/identity-{light-en,dark-bg,mobile-dark-bg}.jpg`;
  this fixture has no live backend, credentials or permission effects.

The integrated run exposed typed public datetimes being rejected by the plain-JSON
context parser. Serialization now converts only this known identity field, with
a typed resource/subject/context round-trip regression; old v1–v6 strict parsing
and canonical vectors are retained. The forged SDK-secret test also verifies
that the client refuses an unauthenticated response signature rather than trusting
its error body. Diagnostic failures/subsets are not added to the final totals.
Existing deprecation and short fixture-key warnings are not suppressed.

Verified negative coverage includes missing/corrupt public metadata, no private
column/crypto/init/transaction side effects, exact SDK/manifest permission,
unknown/extra/caller-selected fields, cross-owner/key/configuration/recovery drift,
review/approve without apply, revoke/disable races, old sealed version compatibility,
signed SDK transport and explicit refusal of proof/peer/status operations.

No live VM keys, identities, grants, services or immutable release files are
changed by this development slice. Commit/push/release and live acceptance require
their normal explicit workflow. Reviewed-native remains **not a sandbox**.

## Remaining WP4 work

Possession proofs require a separate signing authorization contract, not this
public read. Peer mutations require exact local consent/peer/generation bindings;
their scoped support remains blocked and existing compatibility security contracts
are preserved. The subsequent bounded local status projection uses exact link,
consent revision and selected node/field bindings, not a blanket device-data or
reporting grant.

The next bounded adapter should reuse an exact existing Core-owned peer link and
its consent/status bindings. The [public-only status foundation](EXTENSION_PLATFORM_V2_STATUS_READ_FOUNDATION.md)
now separates that local read from private keys and peer credentials. The later
[scoped status adapter](EXTENSION_PLATFORM_V2_STATUS_READ.md) adds exact local
review/admission, with visual/live acceptance still pending. The current proof permission alone declares no
approved receiver, audience or resource; it cannot safely enable a general scoped
signer. Such support needs a separate additive binding contract and review.

Jobs/public routes/provides, the public frontend operation bridge and neutral
Standalone/Hub acceptance also remain open. General WP3 lifecycle/dependency and
WP5 OS/browser isolation gates are not completed by this read operation.

Related evidence:

- [WP4 scope and closure checklist](../EXTENSION_PLATFORM_V2_CORE_PLAN.md#wp4--public-platform-api-sdk-and-authorization)
- [Current closure audit](EXTENSION_PLATFORM_V2_WP4_CLOSURE_AUDIT.md)
- [Authority administration and admission](EXTENSION_PLATFORM_V2_AUTHORITY_APPLY.md)
- [Existing identity/proof compatibility contract](INSTALLATION_IDENTITY_V1.md)
- [Existing peer/consent contract](INSTALLATION_PEER_V1.md)
- [Checkpoint contract and verified local evidence](EXTENSION_PLATFORM_V2_CHECKPOINTS.md)
- [Public-only reader tests](../backend/tests/test_application_identity_existing.py)
