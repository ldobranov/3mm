# M20 WP4 Block 1 — exact peer-read context and policy contract

Date: **2026-10-16**. Implemented locally: **internal authority v9** for exact
existing-peer `read` requests. This is a pure context/policy/selection contract,
**not a persisted approval, effective grant, SDK endpoint or completed Block 1**.
WP4 remains open. It follows the
[current-source reader](EXTENSION_PLATFORM_V2_PEER_READ_SOURCES.md).

Follow-up: the [installed-only outbound approval cycle](EXTENSION_PLATFORM_V2_PEER_READ_AUTHORITY.md)
now explicitly opts into v9 for its limited profile. The pure functions themselves
still authenticate/approve nothing. Inbound/receiver, relational lifecycle, UI
and positive peer SDK execution remain outside that integration.

## Boundary implemented

`ResolvedPeerReadScope` is shared by the current-source reader and the new pure
authority models; the reader's `PeerReadBinding` name is an internal alias, not a
second drifting schema. Its public binding pins:

- the logical declaration, direction and saved-configuration reference;
- exact Core/application owner, incarnation and current instance;
- installed package and service artifact SHA-256;
- resolved existing peer ID, wire version, both complete public identities;
- canonical HTTPS origin and target module;
- exact local consent/revision and verified v2 enrollment metadata where present.

The only new selection key is `peer:<logical_binding_id>:read`. It is neither a
raw peer selector nor an implicit right to list an inbox/history. Generic peer
groups, signing, enrollment, rotation, reporting, approval, revocation and
wildcards are not admitted by this vocabulary. The declaration must contain
exactly `read`; supported selections cannot hide a wider declaration.

Inbound resources require the local Core as receiver and this application's
module as target; outbound resources require the local Core as sender. Self
peers are rejected. V1 inbound records do not invent consent or intent absent
from their protocol. V2 metadata retains canonical ordering, strict bounded
revisions and its exact hash; it must agree with the resource's consent. The
pure parser does **not** verify an enrollment signature or prove freshness:
those inputs must come from the trusted current-source reader. A valid metadata
hash or a well-formed caller object cannot authenticate evidence.

The complete family has 1–32 exact resources, unique logical IDs, unique
direction/configuration references and no resolved aliases within a direction.
One instance, service artifact and local public identity must own the family.
Mixed public-identity and status resources must agree with that same identity
and instance. If status and peer resources refer to the same outbound link,
their public pins, target, origin and consent must agree too.

Changing state, credential generation, remote binding IDs and approval deadlines
remain separate source observations. They cannot be inserted into permission
identity. This does **not** waive future fresh-state/revocation checks: a retained
binding or read-only snapshot is never live admission.

## Versioning and pure comparison

Internal `AuthorityReviewContextV9`, `AuthoritySelectionV9`, `AuthorityPolicyV9`,
`PolicySubjectV9` and `CorePolicyEvidenceV9` carry `peer_reads`. The pure policy
adapter revision is 9. Earlier resource families remain available with their
existing validation and whole-relational-profile selection semantics. Internal
version numbers are not new manifest, SDK or peer-wire versions.

Exact rules compare the complete typed resource, not just logical/peer IDs.
Changed package/service, owner, instance, direction, reference, public key,
origin, target, consent or v2 intent requires different matching evidence and a
different context fingerprint. Absent rules authorize nothing; an explicit
subset does not grant other peers. Source blockers, revoked/missing native trust,
unsupported execution profiles, configuration/recovery drift and review expiry
remain refusals. The pure functions perform no I/O or implicit clock lookup and
return `permission_approval: not_evaluated`.

Versions 1–8 keep their existing models, selection vocabularies and canonical
policy/context bytes. Fixed vectors were captured from the previous native
source checkout and compared against this implementation. New resources are
sorted only in v9. Typed inputs are fully revalidated, including public datetime
fields, rather than trusting constructed/copied Pydantic instances. Existing
128 KiB JSON/context limits still refuse oversized complete requests without
truncation. Consumers of `_parse_versioned` must explicitly opt into v9.

## Original pure-contract boundary

At the pure-contract slice's checkpoint, the installed authority resolver/subject
builder, sealed manager, public API/UI, SQL lifecycle consent and scoped SDK
dispatch had not opted into v9. The separate follow-up linked above now implements
only the bounded outbound installed/backend/API cycle. Its unsupported profiles
and positive SDK dispatch remain blocked; a pure context still cannot create a
grant or hide unresolved peer authority by selecting a supported subset. Existing
compatibility peer workflows are not rewritten.

The original integration sequence is below; the follow-up report tracks which
steps are now implemented and the narrower supported installed profile:

1. Resolve the complete supported request in the installed authority flow and
   explicitly version its sealed review/approve/apply/current-grant handling.
   Preserve independent receiver business consent and all unsupported families;
   a declared receiver is not only read metadata and must not be silently cleared.
2. Present exact resources and selections in management/API/UI, including empty
   selection, partial selection, stale plans and EN/BG review text.
3. Add bounded SDK reading by logical binding under current key/guard/peer
   serialization. Reconstruct current sources; recheck caller, package, instance,
   configuration, native review, grants, recovery and revocation before output.
   Do not reopen the legacy unfiltered list, signer or mutation helpers.
4. Verify real sealed authorization, current-grant refusal, drift/revocation
   races and UI behavior before advertising positive scoped peer-read support.

## Verification

- **132 Windows cases passed** in the new suite, including both directions and
  wire versions, mixed storage/checkpoint/identity/status resources, strict
  metadata, alias rejection, subset/empty rules, aggregate byte limits,
  constructed-input rejection, source-blocker/trust/clock refusal and old
  canonical vectors. Real signed source bindings are accepted by the shared
  strict model but still explicitly carry no approval.
- **405 additional Windows regression cases passed**, including the existing
  78 current-source cases and authority context/policy families 1–8. These are
  scoped checks, not the full release suite.
- **1044 native Linux/Python 3.14.4 cases passed** in 1085.86 seconds. The one
  skipped non-POSIX refusal was executed separately on Windows and passed
  (**538 distinct Windows cases total**, including that check). Platform and
  earlier-slice selections overlap and must not be added as unique coverage.
  The native selection covers all new vectors, real signed source bindings,
  established v1/v2 workflows, current/historical peer readers, request/adoption/
  SDK denial, real POSIX keys and sealed management, current identity/status/
  checkpoint authority, subjects and read-only sources. Real two-Core verified
  HTTPS v1 acceptance passes; v2 coverage is fixture-based, not new live/public
  ingress acceptance. This is not the full release suite or actual Root/helper
  acceptance; no helper implementation changed in this slice.
- Both changed service modules, the shared source reader and the new test suite
  match `/var/tmp/3mm-peer-context.Td3f6o` byte-for-byte. Version 1–8 fixed
  vectors match the previous `/var/tmp/3mm-peer-read-sources.J2fGd8` checkout.
- Frontend production build passed in **10.40 seconds**. No frontend source or
  visual change is included; this is not a new browser visual acceptance.

Evidence: `.runtime/m20-peer-context-*`. Existing deprecation and intentionally
invalid constructed-model serializer warnings remain visible. Checks use local
disposable databases and an unprivileged isolated native checkout, not the VM or
the parallel `/opt/3mm-dev` project. No database schema, runtime/public version,
installed service, key, grant, release, branch, commit or push was changed.
