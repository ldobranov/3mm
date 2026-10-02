# Installation peers v2 — verified application intent and consent

Implemented locally on 2026-10-02, after `b119060` / published beta.31.
Release target: **v0.3.0-beta.32**; publication requires its annotated tag
workflow to succeed. Beta.31 contains peer v1 / SDK 1.2, not this addition.
No deployment, OTA, public ingress or live application enrollment is implied.

This generic G2 addition addresses `CM3_CORE_APPROVAL_BINDING.md`. Core verifies
the exact intent reference and consent that were proved and reviewed. It does
not implement organization, invitation, Owner or customer rules. Those remain
in the receiving extension. Node pairing, Hub addresses, GPIO/Agent authority,
human sessions and reverse command transport are unchanged.

## Compatibility and capability

Application SDK runtime becomes **1.3**, supporting manifest SDK versions
1.0–1.3. Peer v1 wire schemas, signature domains, endpoints, bootstrap payload
and approval behavior remain available to SDK 1.2 applications. V1 consent
changes remain local exporter changes; v1 does **not** guarantee the exact
receiving-application intent/consent binding described here.

V2 requires `service.sdk_version: "1.3"` on both applications. The receiver
must additionally declare `peer_receiver.peer_version: 2`; omission means v1.
There is no silent downgrade or automatic conversion of an existing binding.
Changing a receiver's peer version fences its old bindings. To upgrade trust,
explicitly revoke and reopen the receiver binding, create a new administrator-
approved outgoing link, prove possession again, and review its metadata.

The SDK still uses signed local platform envelope v1 and G1 identity/proof v1.
G1's `sdk_version` reports the actual runtime (`1.3`), not the application's
declared minimum. Applications embedding old SDK/protocol copies must update
their parser to accept that runtime value; v1 peer wire behavior is unchanged.

Require capability instead of assuming a Core version number:

```python
capabilities = platform.get_installation_peer_capabilities()
assert capabilities["approval_binding_version"] == 2
```

The permission is enroll or receive. SDK 1.2 declarations cannot use this new
action. Public `GET /api/v1/installation-peers/v2/capabilities` requires the
configured HTTPS origin and returns `peer_versions: [1, 2]`,
`approval_binding_version: 2`, `minimum_sdk_version: "1.3"`, with no-store.
Capability discovery is not identity pinning or authorization.

## Exact shared schemas and local API

Schemas live in `three_mm_protocol/installation_peer_v2.py`. Models forbid
unknown fields; versions, generations and revisions reject boolean/coerced
numbers. Existing consent, projection, identity and proof models remain v1.

An authenticated local Core administrator creates a v2 link with:

`POST /api/v1/installation-peers/applications/{module_id}/outbound/v2`

Request `PeerOutboundConsentRequestV2` is exactly:
`origin`, `receiver_identity`, `target_module_id`, `consent`,
`application_intent`. Origin is canonical HTTPS; the receiver's full G1
identity must be independently pinned. Core checks selected Node IDs against
its non-revoked registry. The caller cannot supply a verified receipt/hash.

`application_intent` is a bounded opaque reference: 1–256 ASCII characters,
`[A-Za-z0-9_-]`. It is not arbitrary JSON, a URL, a user ID or a Core grant.
The application must issue and check its intent's ownership, expiry, reuse
and intended installation/organization. Core never interprets its content.
Do not put credentials or business records inside the reference.

Core stores `PeerEnrollmentMetadataV2` durably in the existing start JSON:

```json
{
  "metadata_version": 2,
  "application_intent": "opaque_reference_from_receiving_application",
  "consent_revision": 1,
  "consent": {
    "consent_version": 1,
    "summary_fields": ["core_version"],
    "node_ids": [],
    "node_fields": []
  },
  "metadata_hash": "<64 lowercase hexadecimal characters>"
}
```

The three consent selection lists are sorted, unique and explicitly bounded
by `ProjectionConsentV1`. Hash = SHA256 of canonical JSON of metadata excluding
`metadata_hash`. Use `enrollment_metadata(intent, consent, revision)` to derive
this shared representation. Equal selections with different ordering are equal.

## Proof, receipt and pre-approval review

Wire base is `/api/v1/installation-peers/v2`:

- `POST /enrollments/start`: `PeerEnrollmentStartV2` adds
  `enrollment_metadata`; challenge returns the same metadata.
- `POST /enrollments/complete`: `PeerEnrollmentCompleteV2` includes
  `metadata_hash`; pending/active receipt includes the full metadata.
- `POST /report`, `/rotate`: signed `PeerRequestV2`, credential claims v2.
- `GET /identity`: public G1 identity/runtime result.

Start, credential and request signatures have domain separators ending
`.v2\n`, distinct from v1. Both G1 proof resources hash canonical
`{"module_id": ..., "scopes": [...], "enrollment_metadata": ...}` within
`peer.enroll:<request_id>:<hash>`. This binds exact metadata to both proofs,
the signed start, durable pending receipt and signed active credential.
Full issuer/subject identities, module, origin, scope, generation, deadlines,
request path and nonce retain their v1 bindings. V2 data cannot go through v1.

Only completed, pending/active enrollments expose `verified_metadata` through
SDK/admin inbound list (`PeerInboundStatusV2`). Challenged/revoked/renewable
entries expose null, not unproved intent claims. Bootstrap payload is the v1
three fields plus `enrollment_metadata`. Its input schema must require these
four fields with string/object/array/object types. It is delivered under the
existing authenticated Core-to-host machine envelope, not a human context.

The bootstrap actor still has empty scopes. Its idempotency key now includes
binding ID, generation and metadata hash, so a new consent review episode is
not mistaken for an old application receipt. Callback dispatch is fenced by
current pending state/generation. A callback result cannot activate trust.

After its own intent/Owner/ACL checks, the receiver calls:

```python
peer = platform.list_installation_peers()["inbound"][0]  # choose intended peer
metadata = peer["verified_metadata"]
# Validate this opaque intent and Owner authorization in the application first.
platform.approve_installation_peer(
    peer["binding_id"],
    expected_generation=peer["generation"],
    expected_metadata_revision=metadata["consent_revision"],
    expected_metadata_hash=metadata["metadata_hash"],
)
```

Shared review schema is `PeerApprovalReviewV2`. The existing administrator
approval endpoint accepts these same three review fields. Generation-only
approval is still valid for v1, but fails for v2. Metadata CAS is checked even
for an already-active approval retry. Stale/partial reviews cannot approve
different data. Human/public payloads cannot invent verified metadata.

## Consent changes, delivery and recovery

The existing authenticated consent update API uses `expected_revision`.
For v2, every actual selection change (expansion **or reduction**) increments
consent revision, replaces the signed start and clears credential, completion,
rotation and report cache. Local state becomes `new`; no reports can be sent
until a fresh enrollment and receiver approval. The opaque intent stays fixed.
The receiver replaces the same link's older revision, advances generation,
and becomes challenged/pending again. Older completions, credentials, reviews
and callbacks are denied. Identical normalized selection is an idempotent no-op.

The receiver validates each projection's consent revision and exact summary
fields, Node IDs and per-Node fields against its signed approved metadata.
Even a correctly signed sender request cannot widen or change that selection.
Local consent revision CAS fences delayed enrollment/report/rotation replies.
Revocation, uninstall, nonce replay, lost-response receipts, expiry and restart
rules remain in force. Request/response limits remain 128 KiB; projection 64 KiB.

Local withdrawal immediately stops new export and cache reuse; it cannot
retract an already-sent snapshot or a dispatched action. The receiver's old
credential generation is invalidated when the new consent enrollment arrives,
or when the receiver revokes it. Retention/visibility leases for previously
received data remain receiving-application policy, not a Core guarantee.

No database model/schema changes are needed: v2 lives in existing peer JSON
columns created by Alembic `526ab1c2d3e4`. Legacy records remain v1. Full/portable
restore keeps metadata for audit but quarantines both trust directions, removes
credentials/caches, advances fences and clears nonces; no restored approval
automatically activates. Revoke/reopen and new proof/approval remain explicit.

## Verification and remaining extension work

Targeted tests cover v1 regressions and v2 signed metadata, completion/review
CAS, scope change/reapproval, projection restrictions, old callback/credential
denial, delayed replies, loss/retry across sessions, restore quarantine,
strict bounds, manifest compatibility, authenticated administrator creation,
SDK read/approval HMAC envelopes, and signed host bootstrap delivery.
Wrong/expired/reused intent tests use an opaque fixture application ledger;
they do not add organization/invitation tables or policy to Core.

Combined targeted/regression run: **154 passed** in 88.78 seconds. Five added
malformed-credential cases passed separately in 2.17 seconds. Existing
deprecation and duplicate-ZIP fixture warnings remain; no live data were used.

These are local Windows tests with in-process HTTPS handlers and in-memory
socket boundaries, **not** a new real TLS/Linux/public-ingress acceptance.
The separate v1 Linux acceptance documented in
[INSTALLATION_PEER_V1.md](INSTALLATION_PEER_V1.md) does not verify v2.

The consuming extension still needs intent issuance/expiry/reuse rules, exact
Owner review, organization mapping, durable report deduplication, retry/rotation
schedule and scope-limited visibility. This Core addition alone does not finish
CM3 activation or connect a live cloud installation.
