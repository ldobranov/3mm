# M20 WP4 Block 1 — exact peer-read source foundation

Date: **2026-10-16**. Implemented locally: an internal, bounded, current-source
reader for exact configured inbound/outbound peer reads. This is the first part
of the planned scoped reader, **not an approved grant, SDK endpoint or completed
peer-read executor**. Block 1 and WP4 stay open. The
[request/inspection contract](EXTENSION_PLATFORM_V2_PEER_BINDING_REQUESTS.md)
and its negative runtime/adoption gates remain in force.

Follow-up: the [internal v9 pure context/policy contract](EXTENSION_PLATFORM_V2_PEER_READ_CONTEXT.md)
now shares the strict binding type. Sealed review/apply and positive SDK runtime
support remain disabled; the source result still grants no access.

## Implemented boundary

`read_configured_peer_sources` consumes a Core-prepared, validated, digest-pinned
package and the actual installation ID. The caller owns a consistent Core read
transaction, such as the existing read-only `_read_snapshot`. It must prepare the
actual artifact outside that transaction; an arbitrary caller-constructed object
is not provenance or authorization. No SDK/browser configuration, identity,
peer selector, origin, credential or already-approved snapshot is accepted.

The reader checks the persisted package/module/version/digest pin and current
installation instance/incarnation. Configuration comes from the stored Core row
and is validated against the package schema, without assuming manifest defaults.
That private configuration is an internal input; **it is not returned**. Public
peer fields and the already-existing public Core identity are explicit SQL
projections, never whole peer/key/package ORM entities. JSON/text size predicates
bound selected fields before decoding; strict schema/canonical-byte bounds apply
afterward as well.

Only complete `read`-only declaration sets are accepted. Logical bindings resolve
to saved `peer_<32 hex>` IDs for the same module and current instance; duplicate
resolved aliases, missing/foreign/revoked peers and unsupported mixed actions
refuse the whole family, without partial output or fallback to listing history.
Legacy packages without bindings return an empty requested family, **not** a
permission to use their coarse legacy peer groups.

Both peer wire versions are supported. The public enrollment-start signature,
sender/receiver pins, request/target, HTTPS origin and challenge resource are
checked against the actual saved row. This verifies the saved signed metadata;
it does not renew a challenge, prove fresh possession, validate a credential or
contact another Core.

- Outbound reads require the current Core as sender, exact locally selected
  consent/revision and matching v2 metadata where declared. New links may have
  no remote binding yet; pending/active links require a valid remote binding ID.
- Inbound reads require the current Core as receiver, the configured receiving
  origin, exact sender/request and declared receiver wire version. Only
  proof-completed pending/active records are accepted. Challenged, renewable and
  revoked entries are refused, even if their IDs are configured; no inbox
  discovery is inferred. The stored completion digest is a Core proof-state
  marker, not an independently reconstructed or fresh possession proof.
- V1 inbound data does not invent consent or application-intent metadata absent
  from its protocol. V2 retains the exact verified enrollment metadata and hash.
- Stopped metadata reads require explicit `allow_stopped=True` and actual
  disabled/stopped state. They never enable the application. Ordinary calls
  require an active installation with the exact installed version; inert/new
  registration lifecycle is not supported by this source profile.

The source separates stable binding inputs from changing observations. Credential
generation, remote binding and approval deadline observations do not masquerade
as permission identity or a usable credential. No certificate, private signing
key, report payload/cache, rotation request, raw enrollment start or challenge is
returned. The opaque v2 intent remains protected, selected-peer protocol metadata,
not anonymous/public-internet data or Core interpretation of business ownership.

Sources are sorted by logical binding ID, at most 32, with the existing 128 KiB
authority-context byte ceiling for the whole source result. Excess size refuses
the whole set; nothing is silently clamped or truncated. Results explicitly say
`reviewable: false` and `permission_approval: not_evaluated`.

The reader has no commit, rollback, lock, signing/decryption, identity/key
initialization, audit/grant writer, network request or extension invocation. It
does not flush pending caller work. Failures use a fixed redacted error, not raw
configuration, opaque intent, SQL errors or partial resources.

## Verification

- **78 Windows cases passed without skips** in 112.17 seconds: both directions
  and wire versions, persisted pins/configuration, signature/proof-state drift,
  private-field absence, complete-set rejection, alias/mutation refusal, stopped
  inspection, pending-work protection, observation separation and 32-binding/
  aggregate-size bounds. The final expanded set was rerun after the focused
  incarnation, snapshot and total-budget cases.
- **460 native Linux/Python 3.14.4 cases passed without skips** in 505.28 seconds.
  The selection includes those 78 cases, current/historical public listing,
  status bindings, established v1/v2 workflows and receiver approval, exact peer
  request/adoption/SDK denial, identity/status grants and relevant protocol tests.
  Existing real two-Core verified HTTPS **v1** acceptance also passes. V2 remains
  fixture-based, not new live-v2 or public-ingress acceptance. This is not the
  complete release suite; platform and previous-slice counts overlap.
- Minimal-schema tests physically omit Core private-key, whole credential,
  challenge, report/cache and rotation columns. Core configuration remains an
  internal input, not output. There are no ORM entity loads or non-SELECT
  statements, and the reader works without the encryption key. Private-key,
  signing, network, audit and invocation helpers are forbidden by test doubles.
- A real two-connection WAL/read-only Core snapshot interleaves revocation during
  resource reading. The open snapshot remains coherent; after it closes, fresh
  reading refuses the revoked link. Retained evidence never becomes admission.
- An initial negative test exposed that the reusable pure principal model accepts
  broader identifiers than durable installation incarnation metadata. The reader
  now explicitly enforces the existing 32-hex incarnation format. No shared
  principal grammar or runtime permission was weakened.
- Frontend production build passed in 6.73 seconds; no frontend source or new
  visual delivery is included. Both new source/test files match native checkout
  `/var/tmp/3mm-peer-read-sources.J2fGd8` byte-for-byte. Existing deprecation and
  fixture-key warnings remain visible.

Evidence lives under `.runtime/m20-peer-read-sources-*`. Tests use disposable,
unprivileged databases/checkouts, never the VM installation or parallel
`/opt/3mm-dev` project. Earlier incomplete runs are not counted as extra passes.

## Next integration, deliberately not enabled here

1. The exact resource is now available in internal v9 pure context/policy/
   selection models. Integrate the installed resolver and sealed review/apply
   cycle next, preserving old v1–v8 canonical forms and all unsupported families.
   A valid source alone cannot clear the peer source blocker.
2. Reconstruct all requested bindings from current sources under authenticated
   key/guard/peer serialization. Recheck actor/instance, package, configuration,
   grants, recovery, revocation and complete bindings before returning data;
   never reuse a stale read-only snapshot as admission.
3. Add an SDK request by logical binding, with a bounded public result. Do not
   open the unfiltered legacy list, generic signer, enrollment, receiver approval,
   reporting or mutation paths. Preserve independent receiver business consent.
4. Verify current-grant refusal, drift/revocation races and exact management/UI
   presentation before advertising positive scoped runtime support.

The original source-only slice introduced no internal authority version. The
separate pure-contract follow-up introduces internal v9, not a public SDK/
manifest/schema version, route, database migration, live grant/key/service
mutation, release, commit or push. Existing beta.51 relational acceptance is not reopened. WP5 isolation,
neutral Standalone/Hub acceptance and the rest of WP4 remain separate gates.
