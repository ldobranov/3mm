# Installation identity v1 — Core/SDK G1

Release target: `v0.3.0-beta.31`, prepared on `main` after isolated Raspberry
acceptance. Publication requires the tag release workflow to pass; this is not
a live deployment. G2 enrollment/machine principals and G3 consent-scoped projection have a separate contract
in [INSTALLATION_PEER_V1.md](INSTALLATION_PEER_V1.md).
No Node pairing, Hub address or command authority changes are part of G1.

## Supported contracts

- Core: `0.3.0-beta.31` introduces this contract. Released beta.30 alone does
  **not** implement it.
- Core-Agent protocol: `1.0`, unchanged; new installation identity/proof schemas: `1`.
- Application manifest: `application-extension v1`, G1 requires SDK `1.1` or
  `1.2`; SDK `1.0` services remain supported without new permissions.
- G1 Alembic: `4159a0b1c2d3`, following `3048f9a0b1c2`; the G2/G3 head
  is `526ab1c2d3e4`.

SDK 1.1 exposes `ApplicationPlatformClient.get_installation_identity()` and
`prove_installation_identity(request)` through the existing authenticated local
platform socket, actions `installation.identity.get` and
`installation.identity.prove`. G1 does not expose a generic HTTP proof/signing
endpoint; G2 adds its configured HTTPS public identity/enrollment endpoints.
The existing signed socket envelope stays version 1.

An administrator-installed application must declare `service.sdk_version: "1.1"`
or `"1.2"`
and `platform_permissions` containing `installation.identity.read` and/or
`installation.identity.prove`. The same permissions must appear in the Module
Manifest v2 `permissions`. Unlisted permissions, inactive services and tampered
packages fail closed. Proof permission does not grant enrollment, reporting,
ownership, commands or any access to another installation.

`InstallationIdentityV1` has exactly: `identity_version: 1`, opaque
`installation_id: inst_<32 lowercase hex digits>`, `algorithm: "ed25519"`,
`key_id` (SHA-256 of the 32-byte raw public key), padded standard-base64
`public_key` (32 bytes), `key_generation: 1`, and UTC `created_at`.
Generation 1 is the only key generation supported by G1; key rotation is not
silently implemented by changing it. It is distinct from G2 binding generations.
`InstallationIdentityResultV1` wraps `identity` and actual `core_version`,
`protocol_version: "1.0"`, actual `sdk_version: "1.2"` (also accepts legacy 1.1
responses). Runtime versions are not key
identity, extension versions or claims about Nodes.

## Bounded proof of possession

`InstallationProofRequestV1` has exactly: `proof_version: 1`,
`purpose: "identity.possession"`, `challenge` (canonical unpadded base64url of
32 receiver-generated random bytes), `receiver_installation_id`,
`receiver_key_id`, `receiver_key_generation: 1`, `audience` (canonical HTTPS
origin), `resource` (1–160 lowercase ASCII identifier characters, including
`._:/-`), UTC `created_at` and `expires_at`.
Origins exclude userinfo, paths, query, fragment, default `:443`, mixed-case
hostnames and noncanonical host/port spellings. Proof lifetime is at most 120
seconds; creation may be at most 30 seconds ahead of the verifier clock.

`InstallationProofV1` has exactly `proof_version: 1`, `identity`, `request`, and
standard-base64 `signature` of the 64-byte Ed25519 signature. Signed bytes are
ASCII `3mm.installation.identity.proof.v1\n` followed by UTF-8 JSON of
`{"identity": ..., "request": ...}` using the validated models' JSON-mode
serialization (UTC `Z`), recursively sorted keys, ASCII escaping and separators
`,`/`:` without whitespace. `canonical_installation_proof` is the shared encoder.
No arbitrary bytes or caller-selected signing domain are accepted.

The shared/SDK `verify_installation_proof` requires independently expected
identity and the **entire** expected challenge request, validates expiry and key
binding, then verifies the signature. It never trusts the proof's embedded key
as a substitute for receiver policy. Receivers must persist and consume
challenges once. G1 verification itself is stateless, so a valid proof can be
verified twice; replay protection/approval/idempotent completion belong to G2.
There is no enrollment HTTP path in G1. This proof is neither a credential nor
evidence of local consent, ownership, TLS transport or a trusted machine actor.

## Persistence, encryption and recovery

`core_installation_identity` is a singleton platform table in the existing Core
database, not an extension database. ID, public binding and Fernet-encrypted
private key are inserted atomically on first authorized SDK or configured G2
peer use. The existing
`AI_SETTINGS_MASTER_KEY` is the at-rest key, as for application secrets; missing,
wrong or malformed master keys fail closed, with no plaintext fallback. No key
or identity is rotated on read, restart, immutable update or extension update.
Corrupt rows/key mismatches are errors, not a trigger to generate a replacement.
Parallel creators converge on the one primary-key row. Never export the row or
master key in diagnostics, SDK responses, manifests or logs.

- Independent clean Core databases generate independent IDs and key pairs even
  when they install exactly the same extension. Node-only installations do not
  create this Core identity.
- Existing migrated databases acquire their first identity lazily; migrations
  do not require a master key and do not overwrite existing state.
- Full device and portable recovery preserve ID/key via the existing secret Core
  database entry and protected host-config entry containing the master key. Both
  are required to recover proofs. Restore is replacement, never merging the old
  destination identity. Backup preview refuses initialized identities without a
  matching captured master key, and restore validates this pair before stopping
  services. Neither check generates a replacement or exposes key material. The
  source installation must be retired before running its restored replacement.
  G2 peer trust is quarantined during staged restore and requires new approval;
  preserving identity does not automatically restore old cloud rights.
  PostgreSQL identity storage is supported by the ORM;
  the existing full-device backup feature still supports SQLite only.
- Legacy backups taken before G1 have no identity. After their restore/migration,
  first use generates a new identity; future peer enrollments must be reapproved.
- Master reset/new clean installation erases the database and therefore creates
  a new identity on first use. Reset does not claim preservation of cloud trust.
- Copying a database/SD image preserves the identity; a UUID **cannot** detect
  that clone. Running both copies is unsupported. An independent clone requires
  a clean Core state/new identity followed by explicit configuration/data import
  and fresh peer approval; G1 has no identity-fork or key-rotation API. G2 rejects
  conflicting public-key bindings and revokes old credential generations, but
  cannot detect two identical full clones sharing the same private key.

## Remaining handoff

G2/G3 are implemented and specified in INSTALLATION_PEER_V1.md. Consumers
must use that wire/SDK contract rather than provisional paths/token formats.
CME still needs its local consent UI, central Owner approval and durable
reporting integration. G4 authentication-log hardening is now implemented
and tested; details and remaining public-deployment prerequisites are
in INSTALLATION_PEER_V1.md. G5 initial migration-read connection close and G6
actual Core version validation are included with this SDK groundwork.

## Verification and delivery state

Local branch: `main`. Base commit:
`1bf18f9636a4d50476052f910812188fcbb49e44`. G1–G4 are included in the
`v0.3.0-beta.31` release scope. The peer contract records the successful isolated
Raspberry HTTPS/socket acceptance on 2026-10-02. No live deployment was performed;
concrete business-extension changes are excluded.

Targeted checks: **108 passed, 1 skipped**, with six existing warnings. Coverage
includes strict proof schemas/signatures and bindings, concurrent creation,
restart/update persistence, independent databases and copied identities,
manifest permissions, signed SDK envelopes, migration upgrade/downgrade,
actual-version compatibility errors, portable backup/restore and rollback,
captured master-key mismatch rejection, and initial SDK migration connection
closure. Existing package, platform, storage and backup regression tests were
included. `git diff --check` passed.

The skipped existing test requires a real Unix-domain socket, unavailable on
this Windows host. The signed-envelope tests use an in-memory transport; they
do not replace live Linux socket validation. No frontend files changed, so no
frontend build was required. This count records the original G1 checks; the
G2/G3 document records the expanded verification and delivery limitations.
