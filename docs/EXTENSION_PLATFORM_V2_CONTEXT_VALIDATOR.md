# M20 — internal authority context validator

Date: 2026-10-08. Status: **implemented locally, pure/internal only** following
owner approval of the bounded validator slice. This is not completed WP4/WP5,
a grant store, approval API, supported public wire schema or live authorization.
The [approval design](EXTENSION_PLATFORM_V2_APPROVAL_CONTRACT.md) remains the
larger intended contract, not a claim that its acceptance matrix already passes.

## Scope and trust boundary

[review_authority_context](../backend/services/application_authority_context.py)
accepts a resolved context, an explicit selection and an explicit `now_ms`.
It returns reviewability, sorted bounded reason codes and, only when reviewable,
an internal domain-separated `context_fingerprint`. `permission_approval` is
always `not_evaluated`; there is no token, signature, decision or executable grant.

There is **no production caller or route**. Inputs must eventually be constructed
by a trusted Core resolver from the validated exact artifact, real installation,
effective configuration and current broker/resource/policy records. The helper
does not resolve those records itself. A fabricated internally consistent input
can fabricate reviewability, never live permission. Do not expose it as an API
accepting client-authored authoritative snapshots.

Its closed, independently versioned internal models bind:

- Local Core/application identity, module ID and application incarnation.
- Candidate version/digest and optional separately built executable UI digest.
- Actual baseline artifact or explicit absence, authority epoch, grant revision
  or explicit absence and Core-owned enforcement mode.
- An installation-keyed configuration fingerprint and key identity, **not** raw
  configuration, defaults, secret values or unkeyed password hashes.
- Core policy/adapter/trust/profile identities, exact scope-key allow/required
  sets and explicit unresolved proof/dependency/peer/frontend blockers.
- Command declarations using the existing `ApplicationCommandBindingV1`, exact
  target/sensor identity and resolved control revisions.
- Connector declarations using the existing `ApplicationConnectorV1`, configured
  values separately from stored origin/binding ownership/revision/enabled state,
  and actual credential reference/kind/owner/version/revocation state.
- Issued/expiry timestamps and the explicit selection.

Identity/revision/key/proof fields are **resolver evidence slots**, not new DB
columns, package fields or claims accepted from an extension. No new IDs are
allocated, no local configuration key is generated, and no proof is verified
against a persistent evidence store in this step. SDK 1.3 stays unchanged.

## Supported selection and failures

Selection contains only complete `command:<binding_id>` and
`connector:<connector_id>` keys. It cannot replace a target, contract, arguments,
TTL, channel set, path or credential. Selected keys must be declared and belong
to the supplied Core policy's exact resolved-context allow set. Required omitted
keys fail. Empty selection is explicit, never a wildcard. Narrower schemas/path
policies and other resource families are not inferred or implemented.

The future resolver must decide `allowed_scopes` against **these exact resolved
resources**, not only a manifest ID; the helper does not independently prove
Core-policy/schema containment. Unsupported families remain explicit blockers.
All supplied resource scopes must resolve even when omitted from selection;
optional-feature degraded activation needs a separately accepted adapter.

Connector origins must be canonical plain origins according to the existing
broker validator and must match configured versus stored values. Disabled or
foreign bindings, foreign/revoked/missing/wrong-kind credentials and mismatched
references fail. A rotation version enters fingerprint identity. Authentication
`none` requires both references and stored credential to be absent. Conservative
path syntax excludes traversal, encoded/wildcard/query/fragment/backslash forms;
it is not a new path-containment or network-isolation proof. Current connector
method semantics derive from the unchanged broker/descriptor adapter revision,
not a newly invented per-package method list.

An exact command contract version must be supplied; legacy omitted contracts
remain unsupported here without changing current runtime compatibility. Contract
compatibility, device ownership/availability and live control revisions still
need trusted resolution and dispatch checks. No Linux/firmware/provider branches.

Proof blockers cannot be cleared by scope selection. `proven_isolated` additionally
requires an evidence revision slot; a nonempty revision does **not** prove OS or
browser isolation. `reviewed_native` is only a Core policy input, never a package
opt-in or automatic fallback. Human roles, kiosk and service authorization remain
independent and unchanged.

Malformed inputs return generic `invalid_context`/`invalid_selection`, not raw
exceptions, configuration, credentials or origins. Other reasons are closed
codes with bounded scope IDs only. The result explicitly lists unverified
resolver/artifact completeness, current actor permission, live resource revisions,
proof/configuration-key authenticity, durable clock/concurrency and enforcement.

## Internal canonical vectors and bounds

This is a deliberately internal v1 encoding, **not RFC 8785, a public signing
format or the final persisted approval-plan identity**:

1. Reject unknown fields, unsupported versions, duplicate raw JSON keys and IDs,
   duplicate set members, non-finite numbers, unsupported Python values, cycles,
   invalid Unicode and out-of-bounds payloads. Parse with strict scalar types;
   `true`, `1.0` and `"1"` cannot stand in for an integer model version/revision.
2. Revalidate model instances as well as plain mappings/JSON strings. Never trust
   a preconstructed model or mutate nested caller input.
3. Normalize declared set-valued scope collections, selection, policy sets,
   connector schemes and command `required`/`enum`. Preserve other array order.
4. Expand existing model defaults. Optional absence equals explicit null **only
   where a default is declared**; required nullable fields require explicit null.
5. Sort object keys by Unicode code point; encode typed JSON nodes. Integers use
   decimal strings, binary64 floats use Python hexadecimal strings, including
   signed zero. Numeric types remain distinct conservatively. Unicode is not
   normalized. Serialize with compact ASCII-escaped JSON.
6. Hash `3mm:m20:authority-context:v1\0` followed by those bytes using SHA-256.
   Do not reuse declaration-diff fingerprints, serialize this as a bearer grant,
   or persist it as a final public approval contract without a separate decision.

Input bounds: 128 KiB compact ASCII-escaped JSON with an early cumulative byte
budget, 16 levels, 16,384 visited values/keys, 4,096 characters per string, finite
numbers of magnitude at most `2**53-1`, at most 64 command/32 connector scopes.
Canonical typed bytes are additionally capped at 512 KiB. Declared field limits
may be stricter. The normalized context must also fit these bounds.

Review lifetime is positive and at most one hour; supplied time must satisfy
`issued_at_ms <= now_ms < expires_at_ms`. This helper has no clock I/O or durable
restart/rollback detection. The persistence slice still needs its tested clock
and epoch policy. A fingerprint changing after a revision change is **not** race
prevention, a CAS, revocation or evidence that all actual writers advance it.

## Verification and next gate

[Focused tests](../backend/tests/test_application_authority_context.py) cover
closed/strict types, whole binding selection/omission, policy restrictions,
foreign/revoked credentials, canonical/stored origin mismatches, sensor identity,
proof blockers, explicit expiry, malformed/large/deep/duplicate/redacted inputs,
canonical bytes/full-context golden digest, key/set versus ordered sequence
semantics, null/absence, same-ID resource/version changes and absence of I/O/input
mutation. The isolation revision in fixtures is synthetic, not live acceptance.

Local Windows/Python 3.13.15 verification: **107 tests passed** (85 new context
cases + 22 existing authority-declaration comparison cases), 4 warnings, 3.08 s.
No new dependency, frontend change/build, full release suite, live resource probe,
database migration, commit/push, deploy or release.

The subsequent [resolver design](EXTENSION_PLATFORM_V2_RESOLVER_DESIGN.md) maps
actual storage/command/connector/lifecycle writers and specifies durable identity,
epoch, resource-revision and configuration-key ownership. It is source-backed
design, not runtime resolution or installed invalidation hooks.

Next: durable metadata and transaction helpers with Alembic/migration tests before
wiring trusted resolution. Audit/idempotent decisions, API/UI and effect-boundary
enforcement remain separate slices. No existing-install policy or runtime switch
is enabled by this validator or its resolver design.
