# M20 WP4 Block 1 — public peer listing preparation

Date: **2026-10-16**. This bounded local preparation follows the
[scoped local status read](EXTENSION_PLATFORM_V2_STATUS_READ.md). It does **not**
enable scoped peer listing, enrollment, approval, signing, rotation, revocation or
reporting, and does not close Block 1 or WP4.

## Implemented source boundary

Compatibility/admin `list_peers` now reads explicit presentation columns rather
than materializing whole inbound/outbound ORM entities. The only credential field
returned from SQL is `claims.expires_at`; no whole certificate, report snapshot,
report receipt/cache, rotation request or separate inbound `sender_challenge`
column enters the Python listing result. The existing public serializers retain
their peer v1/v2 behavior.

Public signed `start_request` wire JSON **is** read to validate the existing
version/enrollment metadata. It contains public challenges/signatures and the
opaque application intent; it is not a private signing key. The raw start request
is never returned by the listing. V2 `verified_metadata` still appears only when
the existing completed-digest and pending/active-state checks allow it; a pending
state alone cannot invent completed proof. Outbound local metadata is not remote
approval or proof of receiver possession.

The module-only filter, newest-first order, 100-entry limit per direction,
historical/revoked entries, response fields and null expiry behavior remain
compatible. Disabled/admin history remains available under its existing caller
authentication; no new active-instance filter silently hides recovery evidence.
Non-null certificate expiry must be a bounded, valid timestamp with a timezone.
Malformed strings, booleans, numbers, nested objects/arrays and naive dates are
refused with a fixed redacted error, not returned as arbitrary public payload.
This deliberately tightens corrupt-data handling, without changing valid expiry
or null response values. Expired historical dates are not hidden or renewed.

The reader prevents autoflush, including expired caller-application attributes,
and never commits, rolls back, locks peers, initializes identities, decrypts/signs,
contacts another Core or writes audit/grants. The caller owns authentication and
transaction lifetime. These historical presentation rows are **not** current
authority resources and cannot be passed off as an admission check.

## Verification

- **27 focused Windows/Python 3.13.15 cases** passed, covering exact v1/v2
  response parity, missing/null/valid public expiry, secret-bearing certificates,
  all existing inbound metadata-visibility states, module filtering, newest-first
  100-entry bounds, retained tombstones, expired-caller autoflush prevention and
  malformed metadata refusal and eight malformed-expiry cases.
- Minimal SQLite fixtures deliberately omit private inbound credential/challenge
  and report/cache columns and all Core identity/key tables. Tests assert only
  SELECTs, no peer ORM entities, no raw credential result column and no signing,
  initialization, network or audit calls. Only the explicit public expiry is
  extracted from the outgoing certificate JSON.
- Final native Linux/Python 3.14.4 regression: **273 passed, no skips**. It includes
  those 27 cases, established v1/v2 workflow/approval fixtures, the existing real
  two-Core verified HTTPS/Unix-socket **v1** acceptance, status binding/admission
  and identity/peer-denial regressions. V2 remains covered by local fixtures, not
  a new real-v2/public-ingress proof. Logs/JUnit: `.runtime/m20-peer-listing-*`.
  The two production files and final test file match the disposable Linux snapshot
  byte-for-byte. Existing deprecation/fixture-key warnings remain visible.
- A previous 265-case run preceded expiry hardening. The additional negative test
  first reproduced unrestricted malformed expiry output; all eight new cases and
  the full 273-case selection were then rerun on the corrected source. Earlier
  runs, Windows/Linux and prior status checks overlap and are not added together.
- Production frontend build passed after the status visual review. No production
  frontend source is changed by this peer-listing preparation.

All checks use disposable state, not the VM, live Core or parallel development
checkout. No schema migration, public SDK/manifest version, grant/key/service
mutation, commit, push or release is included. No live PostgreSQL acceptance is
claimed.

## Source-backed next boundary, not enabled authority

The following constraints were checked in `application_platform.py`,
`installation_peers.py`, SDK 1.3 and the existing peer v1/v2 contracts:

| Existing operation | Constraint for the scoped adapter |
| --- | --- |
| `installation.peers.list` | Current SDK call has no direction/peer selector and accepts enroll **or** receive permission. It returns module history, not just current live links. It must not inherit authority from status read or silently expose an unreviewed inbox. |
| Receiver approval | Issues a credential and commits. Preserve the extension's independent intent/Owner/ACL decision and v2 generation + metadata revision/hash CAS; a Core service grant cannot replace receiver consent. |
| Outbound enrollment/rotation | Uses private signing, persists resumable state and crosses several commit/network phases. A public-only status lease is not a signer or a lease across remote I/O. |
| Reporting | Stores a particular projection/report ID, signs and sends it, then saves a fenced response. Preserve exact outstanding-sample recovery and no automatic replay; recheck fresh authority at separate dispatch/completion boundaries. |
| Peer revocation | Commits and preserves tombstones while advancing local revision/generation. Its scoped mutation needs the shared authority transaction/audit boundary; do not call an inner commit under an outer lease. |
| Generic identity proof | Existing permission alone declares no approved audience/receiver/resource selection. Do not turn it into an unrestricted signer to make peer methods work. |

The subsequent [exact peer-action request delivery](EXTENSION_PLATFORM_V2_PEER_BINDING_REQUESTS.md)
now adds bounded declarations, per-action advisory comparison and negative
runtime/adoption gates, reusing SDK 1.3 and existing wire v1/v2. It separates requested
operations from coarse manifest permission groups. Actual saved peer targets
and local consent must be bound by the next current-source executor; inbound
discovery is not part of the exact existing-link request. That executor must
distinguish permission identity from the credential
generation/deadline checked for a single attempt: ordinary rotation must neither
silently widen a grant nor require pretending an expired generation is current.

Only after those rules have tests should the source blocker/dispatch allowlist be
opened for the corresponding operation. Unsupported declarations remain blocked
even when another selected scope is supported. Pairing and receiver business
policy, pure status read and generic proof signing stay separate. This report is
not a new public permission name, fixed internal version or an implementation of
the remaining write/network flows.
