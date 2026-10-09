# M20 — private configuration review-key foundation

Date: 2026-10-08. Status: **implemented locally, internal/unwired foundation**.
Follows the [installed-source resolver](EXTENSION_PLATFORM_V2_SOURCE_RESOLVER.md)
and [key ownership decision](EXTENSION_PLATFORM_V2_RESOLVER_DESIGN.md).
Common Standalone/Hub Core infrastructure, not Fleet-specific. SDK 1.3, existing
extensions, authentication and current workload authorization are unchanged.

## Delivered boundary

[CoreReviewKeyStore](../backend/services/application_authority_keys.py) supplies
an explicit purpose-separated local key for private configuration evidence.
There is **no production caller**, startup/restore hook, environment setting, CLI,
public endpoint, approval issuer or effect enforcement. It does not remove the
installed-source resolver's configuration-key blocker.

The directory is trusted Core configuration, never a package/request path.
Proposed Linux location: `/var/lib/3mm/core/authority-review`, outside immutable
releases, public uploads and application-owned storage. No production directory
or key was created. No automatic portable-backup inclusion is added: old review
material is not authority to restore.

- Dedicated random 32-byte key and independent opaque `review_<random>` ID.
  No reuse/derivation from login, installation signing, device pairing, application
  transport, Node OTA approval or encryption-master keys.
- Closed, bounded internal record bound to the actual existing Core installation
  ID and `CoreAuthorityGuard.generation`. Both come from the existing dedicated
  consistent read-only DB snapshot adapter, not client claims or lazy creation.
- Ordinary guard **revision** changes do not rotate the key. Recovery
  **generation** changes do: existing offline recovery fences allocate a fresh
  generation before restart, making old/copy-restored material unusable.

The file is not encrypted with another existing key. Its boundary is Core-only
POSIX access; root/Core-process compromise and reviewed in-process native code
sharing the Core UID are not isolated by this store.

## Explicit lifecycle and filesystem boundary

| Internal operation | Behavior |
| --- | --- |
| `identity` / `fingerprint` | Read current material only; no directory, lock, key or DB creation |
| `provision` | Explicit first creation after Core identity/guard validation; exact retry preserves the same valid current key |
| `rotate(expected_key_id=...)` | Fresh ID/bytes only if the currently bound key ID matches; stale retry fails |
| `recover(expected_key_id=...)` | Explicit fresh local replacement of a valid but foreign/recovery-stale record; never adopt its old secret |

Missing material needs explicit provisioning. Malformed/unsafe material stays
denied for separately authorized operator quarantine, not silent repair/deletion.
Recovery on an already-current record is refused; normal rotation is distinct.
Normal read/restart and identical provisioning preserve key identity.

All cooperating operations use a private POSIX flock with nonblocking admission:
busy is unavailable, not an unbounded server wait. Rotation compares the expected
ID under that lock. Atomic replacement uses file fsync, rename and directory
fsync. A pre-replace failure preserves the old file. A post-replace error is not
reported as success or rolled back; the trusted caller must inspect/reconcile.
Interleaved DB recovery leaves a mismatched file unusable, never auto-rebound.
DB and filesystem do not share an atomic transaction.

Each path component is opened with anchored dirfd + `O_NOFOLLOW`. Ancestors must
be root/Core-owned and not group/world-writable, except root-owned sticky parents
such as disposable-test `/tmp`. The final Core-owned directory requires `0700`;
regular, single-link Core-owned key/lock files require `0600`. Symlinks, hardlinks,
FIFOs, unsafe ancestors, directories-as-files and nonempty locks are refused.
Only provisioning may create the final directory/lock, never its ancestors.
Existing paths are never chmod/chown repaired. Run as the Core UID, not root in
its place. Windows storage fails closed, without simulated POSIX protection.
Tested filesystem: Linux WSL `/tmp`; no NFS/distributed-lock guarantee is inferred.

## Private configuration identity

HMAC-SHA-256 covers the **full** bounded resolved configuration, complete
application principal, key ID and recovery generation. No guessed cosmetic-field
exclusions. Domain: `3mm:m20:private-configuration:v1\0`, using the existing
[internal typed canonical encoding](EXTENSION_PLATFORM_V2_CONTEXT_VALIDATOR.md).
Object order is canonical; sequence order, types, Unicode, signed zero and
absence/null remain conservatively distinct. This is not a public signing format.

Only `ConfigurationIdentity(key_id, keyed_sha256)` is returned: no values, key
bytes, unkeyed password hashes, token or approved authority. Invalid input has
generic redacted failures; the private record's representation excludes its key.
This is **not a public HMAC oracle**. The future Core resolver must provide
validated effective configuration and actual application identity from an
accepted source context. This primitive does not prove schema/source freshness,
application existence, publisher trust, isolation, policy or package completeness.

## Remaining gates

- Trusted policy/evidence and staged proposal/configuration adapters, without
  filling evidence with constants or automatically selecting reviewed native.
- Provisioning/rotation/recovery coordinator with current administrator checks,
  durable redacted audit and lifecycle/release coordination. These methods are
  not an actor-authorized management API.
- Full resolver composition and durable review clock; current-key revalidation
  alongside authoritative resources at approval/apply.
- Rotation versus approval/apply/effect-admission serialization. File CAS is not
  the DB grant/admission fence. No pending reviews/live grants exist in this
  slice; future enforcement must independently reject noncurrent key identity.
- Deployment ACLs, clean install/upgrade/recovery UX and live PostgreSQL acceptance.
  A trusted coordinator must quiesce/stabilize managed DB file replacement.
  Command/job uncertainty, replay policy, credentials and cursors are untouched.

## Verification

[Tests](../backend/tests/test_application_authority_keys.py) cover full HMAC
purpose/owner/key/generation binding, malformed bounds/redaction/canonical types,
closed records, explicit lifecycle, actual source reads excluding encrypted
identity columns, unsafe files/paths, atomic failure and recovery drift. Real
Linux two-process rotation has one CAS winner. A disposable root-run Linux case
drops to UID/GID 65534: public parent sentinel readable, Core key unreadable.
This proves key-file protection, not extension/runtime/browser isolation.

Local overlapping runs, not the full release suite:

- Windows/Python 3.13, key/context/installed-source/recovery suites:
  **182 passed, 23 platform skips**, 7 warnings, 16.17 s.
- WSL/Linux/Python 3.14, key suite: **50 passed, 2 platform skips**,
  6 warnings, 5.65 s, including actual POSIX and two-process checks.
- WSL/Linux root, disposable foreign-UID case: **1 passed**, 5 warnings, 4.30 s.

Linux used a disposable `/tmp` pytest dependency environment alongside read-only
existing Python dependencies; installed services/runtime dependencies unchanged.
No schema migration, frontend change/build, live installation mutation, full
release suite, commit/push, deploy or release is included.
