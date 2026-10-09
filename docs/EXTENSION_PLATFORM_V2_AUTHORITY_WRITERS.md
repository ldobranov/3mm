# M20 — connector and credential authority writers

Date: 2026-10-08. Status: **implemented locally; first bounded writer integration**.
Builds on the [metadata foundation](EXTENSION_PLATFORM_V2_AUTHORITY_METADATA.md)
and [writer ledger](EXTENSION_PLATFORM_V2_RESOLVER_DESIGN.md#4-writer-and-invalidation-ledger).
This does not complete WP4, add approved grants or enable effect enforcement.

## Integrated entry points

The existing admin-only [management endpoints](../backend/routes/application_operations.py)
retain their URLs, request/response fields, credential encryption and ownership
rules. Internal helpers require the owning `AuthorityMutation` and no longer
commit independently. All repository callers were adapted.

| Mutation | Authority change in the same transaction |
| --- | --- |
| Create unused credential | Check/lock actual owner incarnation; no epoch or guard revision advance |
| Create connector binding | Fresh binding generation, owner epoch and guard revision advance |
| Change origin, credential FK or re-enable binding | Fresh binding generation, owner epoch and guard revision advance |
| Repeat identical normalized binding | No authority generation, binding telemetry or guard revision change |
| Rotate credential | Secret version increments; owner epoch and guard revision advance |
| First credential revocation | Revocation timestamp, owner epoch and guard revision advance |
| Repeat credential revocation | Revocation timestamp/version and authority generations retained |

Each successful HTTP mutation still writes the existing redacted admin audit.
An audit failure rolls back resource changes and all revisions: there is no
intermediate helper commit. Explicit rotation retains the previous API behavior
of reactivating a revoked secret with a new version/epoch. It does not compare
plaintext values to decide whether rotation is a no-op.

## Transaction boundary

1. Authenticate through the existing admin dependency and capture actor ID.
   Read actual owner/secret identity; missing/foreign references keep 404/422.
2. Validate connector ZIP/descriptor and normalize origin outside the write lock.
   An internal immutable plan binds actual application incarnation/epoch/mode and
   package pointer/version/digest/status/enable state, not client-authored proof.
3. End this endpoint's read-only auth/preflight transaction. Reject pending ORM
   work instead of discarding it. The private route scope is not an adapter for
   arbitrary transactions or previously flushed SQL writes.
4. Acquire guard first, then conditional owner lock, then actual binding/secret.
   Re-read state; stale incarnation, epoch, credential identity/version/kind or
   package state fails with a redacted conflict. No cached object is authority.
5. Apply effective resource/revision changes, flush, add audit and commit together.
   Return only existing selected public fields, never ciphertext or new metadata.

Missing guard is a conflict, never lazy initialization. No package/file/network
work occurs under the management guard. Credential encryption uses the existing
bounded validator and key; identity checking does not decrypt secrets.
The owner lock preserves `updated_at` on a no-op and prevents deletion during the
transaction. Helpers reject another Session's mutation and poison the scope on
stale identity even if a caller catches the error inside it.

## Compatibility and limits

- SDK 1.3, manifests, configuration and human/application access are unchanged.
  No new schema beyond metadata migration `b8c017c8d9e0`.
- Connector HTTP execution/admission is not refactored. Attempts, ambiguous
  outcomes and duplicate handling remain unchanged; telemetry is not authority.
- Physical command generation, queue/claims, unknown jobs, event cursors and
  runtime helpers are untouched. No automatic external replay or network request
  is introduced by a management mutation.
- Lifecycle, device/provider/runtime and raw-SQL restore/rollback writers still
  need integration. Nonparticipating writers/effect admissions are not claimed
  to share a completed lock/fence model.
- No grant store, private HMAC review key, full resolver, publisher/isolation
  proof, new effect enforcement or live acceptance.
- Effective writes activate the existing guarded-downgrade refusal; recovery must
  use a verified pre-upgrade backup rather than erase used authority metadata.

## Evidence

The 23 new writer cases cover real FastAPI authentication, foreign/wrong-kind/
revoked credentials, no-op/A-B-A binding, secret versioning, missing guard,
pending-write rejection, stale package/owner/secret identity, cross-Session use,
response/audit redaction and audit-failure rollback for all four endpoints.
Two real SQLite connections test a rotation waiter rejecting stale identity.
Package preparation finishes before the first guard write; ambiguous connector
execution and duplicate lookup retain authority metadata.

Focused run: **78 passed, 6 skipped**, 164 warnings. Existing commands, scheduler,
metadata and populated migration checks passed. Six signed-platform transport
cases were skipped on Windows because they require Unix sockets; this is not
Linux transport/isolation acceptance. No full release suite or live PostgreSQL race.
No live database/device changes, frontend edits, deployment or release.

## Subsequent lifecycle slice

The [lifecycle integration](EXTENSION_PLATFORM_V2_LIFECYCLE_AUTHORITY.md) now adds
guarded activate/disable/uninstall phases and physical-command invalidation.
Ordinary owner locks reject pending/unconfirmed lifecycle states, including
connector/credential mutations. The scope and evidence above describe the original
writer delivery; they are not a claim that subsequent lifecycle work is pending.
Subsequent [explicit lifecycle recovery](EXTENSION_PLATFORM_V2_LIFECYCLE_RECOVERY.md)
and [device pairing/credential writers](EXTENSION_PLATFORM_V2_DEVICE_AUTHORITY_WRITERS.md)
are now local. Remaining device lifecycle/provider/runtime, restore/reset and effect
admission work still precedes resolver/approval enforcement.
