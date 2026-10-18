# M20 WP4 Block 1 — public-only status projection foundation

Date: **2026-10-16**. This is a locally verified backend preparation step after the
locally verified [checkpoints](EXTENSION_PLATFORM_V2_CHECKPOINTS.md) and
[existing public identity read](EXTENSION_PLATFORM_V2_IDENTITY_READ.md).
It does **not** complete scoped status/peer authority, Block 1 or WP4.

Subsequent local work: the [scoped status adapter and review](EXTENSION_PLATFORM_V2_STATUS_READ.md)
now consume this foundation. The limitations below describe this earlier
preparation slice; visual/live acceptance and the remaining peer contracts stay open.

## Implemented boundary

`read_existing_status_binding` reads a single existing outbound link using
explicit public SQL columns, filtered by exact module and current application
instance. Revoked, foreign, missing and invalid links are refused. It returns:

- the exact link, module and application instance;
- both public installation identities, validated with their public-key digests;
- the canonical HTTPS receiver origin and target module;
- the exact positive local consent revision and selected summary/node fields.

The stored sender identity must equal the already initialized public Core
identity. There is no identity creation/repair, key decryption, credentials,
enrollment proof, report snapshot, network call, autoflush or transaction control
in this read. A public receiver binding does not prove remote possession,
remote approval, connectivity or permission to report.

The existing compatibility projection now uses this public-only reader rather
than loading an entire peer ORM row and decrypting the Core private key. A valid
local public status read therefore needs no encryption master key. Pairing,
proof signing and outbound reporting retain their independent key/permission
checks; compatibility identity GET/prove behavior is unchanged.

The existing projection format, order of consent selections, source timestamps,
unknown-value semantics and bounds are preserved. Devices are filtered in SQL
before output; inventory/heartbeat queries run only for selected fields.

`bound_installation_projection` is an **internal helper, not an admission API**.
It refuses pending writes/nested transactions, acquires the existing outbound
row write lock, re-reads the full public binding and refuses a changed receiver,
origin, target, consent/revision or application instance before projection.
The caller owns commit/rollback. The lock serializes local consent withdrawal
with the complete projection; the helper does not commit under an outer lease.

## Deliberately not enabled

No public manifest/SDK contract, authority context version, sealed record,
database model/migration, route, UI or platform allowlist is changed here.
`installation.status.get` and peer operations **remain blocked in scoped mode**.
Possessing or constructing this internal snapshot is not an applied grant.
Existing identity-read authority cannot be reused to sign, read status or pair.

The next scoped status slice must bind these public fields to the installed
artifact/incarnation and current native/configuration/recovery/key evidence in
review → approve → apply. Its runtime adapter must obtain the current Core
key/authority lease, revalidate the authenticated instance, call the exact-bound
projection and end its transaction before releasing the lease. It needs exact
EN/BG resource review and revocation/race tests, not a blanket device read.

Enrollment, receiver approval, rotation, revocation and reporting remain separate
work. Their existing local human consent and remote generation/nonce rules must
not be replaced by a Core service grant. Network phases cannot hold the local
lease; dispatch and completion require their own fresh checks. In particular,
do not remove a package's unsupported peer-family blocker merely to expose this
read helper. A status-only declaration by itself cannot create a peer link.

## Verification

The final targeted suite has **54 cases**, passing on Windows/Python **3.13.15**
and native Linux/Python **3.14.4**. The test fixture intentionally has
**no private Core key column and no private peer
columns**, so accidental entity/key/credential reads fail at the SQL boundary.
Negative cases cover malformed public metadata/consent, foreign module/instance,
withdrawal, changed receiver/origin/target/revision, no initialization and no
transaction side effects. Real independent SQLite connections verify withdrawal
serialization, and the existing pairing/signed-SDK/projection suites protect
compatibility.

The broad disposable non-root Linux run passed **527 cases**, with one opt-in
HTTPS skip and one intentionally non-POSIX-only refusal skip. A final separate
run passed **58 cases without skips**: all 54 targeted cases, three existing
module-ID compatibility cases and the real two-Core HTTPS/Unix-socket acceptance.
JUnit identifies **529 distinct Linux passed cases**, not 527 + 58; the opt-in
case is covered by the final run. The non-POSIX-only branch also passed separately
on Windows (one case, `.runtime/m20-status-nonposix.*`), covering the remaining
platform-specific skip without pretending to run it on Linux.
Logs/XML are `.runtime/m20-status-binding-{linux,windows}.*` and
`.runtime/m20-status-https-linux.*`.

The final review added an expired-ORM-caller regression: reading application
attributes during validation could trigger an unrelated autoflush before the
public SQL query. The test first reproduced that failure. The no-autoflush
boundary now includes validation; all 54 targeted and real HTTPS cases above
were rerun after this correction. The broader 527-case run preceded that final
correction; it is not represented as a second full regression on the final bytes.
The final Linux integration snapshot's two production files are byte-identical
to the local source. Existing deprecation/fixture-key warnings are preserved.

Frontend production build, changed-file formatting and diff whitespace checks
passed. There is no visual/UI change to accept in this step. None of these
checks is production/VM acceptance or a full release gate.

Development uses the local checkout and disposable test data only. No live VM
key, grant, service, immutable release, version, commit, push or release is changed.
