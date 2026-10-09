# M20 — application lifecycle authority fences

Date: 2026-10-08. Status: **implemented locally; bounded lifecycle writer slice**.
Builds on [metadata](EXTENSION_PLATFORM_V2_AUTHORITY_METADATA.md) and
[connector/credential writers](EXTENSION_PLATFORM_V2_AUTHORITY_WRITERS.md).
This is not WP4 completion, a grant issuer or end-to-end effect enforcement.

## Integrated behavior

The existing administrator activate, disable and uninstall endpoints now use
two short guarded transactions around the existing privileged helper call:

1. Read-only preflight captures actor ID, guard revision and actual installation
   incarnation/epoch/resource state. Activation validates the ZIP, public routes
   and resolved configuration outside the write lock.
2. Acquire the singleton guard first, recheck preflight state and lock the owner.
   For new installs, reserve a fresh incarnation using the existing model default.
   Advance the general epoch and guard revision, mark the pending operation with
   `enabled=false`, invalidate the existing physical-command generation/queued
   authorizations and add the start audit. Commit all of this before helper I/O.
3. Call the helper once, without an open route database transaction or write lock.
   No ORM access is needed to discover helper arguments after the first commit.
4. Reacquire the guard and compare the pending ticket's incarnation, epoch,
   operation, package pointers, runtime locator and resolved configuration.
   A stale completion cannot overwrite a different operation or installation.
   Success advances the general epoch/guard again and commits the final resource
   state, existing terminal audit and uninstall cleanup together.

Uninstall retains package catalog entries and application data, as before.
Peer revocation/tombstones share the first transaction and are not reversed on
failure. A completed uninstall/reinstall gets a fresh incarnation even if the
database row ID or deterministic runtime locator is reused. Disable/activation
preserve incarnation, event cursors and outstanding job evidence.

Pending activations reserve their public HTTP paths when another candidate is
validated; they are never dispatched as active public routes. The preflight guard
comparison prevents concurrent integrated lifecycle writers from invalidating
that conflict check before reservation commits.

Ordinary connector/credential management locks now reject pending lifecycle and
`recovery_required` owners. Only lifecycle completion supplies the exact expected
pending status, in addition to the incarnation/epoch CAS. No new grants or mode
changes are synthesized. SDK 1.3, request/response shapes and admin access remain.
No new database migration is needed beyond the existing metadata migration.

## Failure and recovery boundary

Helper errors, invalid identities and lost responses **do not prove runtime or
filesystem rollback**. The current helper has no durable, queryable operation
outcome contract and its activation rollback can itself fail.

Therefore this slice deliberately tightens failure behavior: it never restores
the old `active` status/package as though rollback were confirmed. A matching
failure ticket advances the epoch/guard, sets `recovery_required`, keeps the app
disabled for Core and commits a redacted `execution_unconfirmed` audit. Old
physical commands remain invalidated. Repeating activate/disable/uninstall does
not automatically replay the helper action.

If Core stops between phases, or the completion/failure audit/commit fails, the
already committed pending state remains disabled. Stale completion is a conflict,
not permission to rewrite newer state. The route does not forcibly stop an
externally running service or promise to recall an admitted physical action/POST.

Subsequent local slice: [explicit administrator reconciliation](EXTENSION_PLATFORM_V2_LIFECYCLE_RECOVERY.md)
now provides recovery to verified stopped/disabled state, with fresh helper ticket
checks, serialized effects and durable one-use admission receipts. It never asserts
activation or data rollback. Live Linux recovery, UI and integration with raw-SQL
restore/reset writers remain release gates. Do not reset status/epoch through SQL,
blindly retry helpers or claim that restart/restore automatically repairs these cases.

Uninstall refuses any outstanding scheduler lease before calling the helper or
deleting evidence. Disable remains available so the existing reviewed job
resolution flow can be used. This code never releases a lease, resets a cursor or
replays a payment/command to repair authority. Existing connector attempt cleanup
on a confirmed uninstall is unchanged; complete effect-admission/evidence retention
and connector outcome review remain separate gates.

## Evidence

The new focused cases exercise real FastAPI authentication and SQLite with
foreign keys enabled: all three operations, committed pre-I/O fences, start/final
audit rollback, unconfirmed helper outcomes, invalid helper responses, stale
epoch/incarnation/package/configuration, blocked overlapping writers, preserved
job claims, fresh reinstall identity, missing guard and pending-work rejection.
Public-route reservation is tested separately from public dispatch. A real second
SQLite connection waits on the guard and rejects a stale lifecycle preflight.

New lifecycle cases: **28 passed**. Combined focused run: **139 passed, 6 skipped**,
315 warnings, 177.61 seconds. This includes existing connector/credential writers,
human/application access, commands and command recovery, scheduler/startup recovery,
public routes, metadata primitives and populated migration tests. The six skipped
cases require Unix sockets and are Windows skips, not passing transport evidence.

Windows helper calls are mocked; this does not prove Linux systemd/helper rollback, PostgreSQL concurrency,
OS isolation or live recovery. No full release suite, deployment or live data
changes. Device/provider/runtime writers, restore/reset fencing, trusted resolver,
private review key, grants and effect-admission enforcement remain pending.
