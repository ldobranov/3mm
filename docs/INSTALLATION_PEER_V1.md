# Installation peers v1 — Core/SDK G2 and G3

This document records the beta.31 v1 implementation. The subsequent, locally
implemented **unreleased** peer v2 / SDK 1.3 addition is described in
[INSTALLATION_PEER_V2.md](INSTALLATION_PEER_V2.md). V1 remains supported but does
not prove the exact receiving-application intent and consent before approval.

Release target: `v0.3.0-beta.31`, prepared on `main` after isolated Raspberry
acceptance, based on `1bf18f9636a4d50476052f910812188fcbb49e44`.
Publication requires the tag release workflow to pass; no live deployment is
implied. The published beta.30 does **not** contain these changes.
Application SDK runtime is now **1.2**, with 1.0/1.1 services still supported.
Application manifest, local signed socket envelopes, installation identity,
peer credential, consent and projection contracts remain version 1.
Core-Agent protocol remains 1.0. No Node pairing, Hub address, Agent token,
GPIO command authority or business IAM changes are included.

G1 identity/proof rules are in [INSTALLATION_IDENTITY_V1.md](INSTALLATION_IDENTITY_V1.md).
The exact peer schemas/encoders are in `three_mm_protocol/installation_peer.py`.
The Core owns the wire protocol and private signing keys; extensions must not
construct an alternative transport or use a human/kiosk/Agent token for it.

## Consent and trust flow

1. A local Core administrator selects an HTTPS origin, independently pinned
   central installation identity, target application module ID, summary fields
   and explicit Node IDs/fields. Core stores a durable outgoing `link_id`.
2. The sender SDK resumes this link. A signed start binds the sender, receiver,
   origin, request ID, target module and the only scope:
   `installation.status.report`. Both installations prove possession of their
   G1 keys using receiver-bound, random, expiring challenges.
3. The central Core consumes the completion once and stores a pending binding.
   It calls only the manifest's bootstrap operation, with a **bootstrap** actor
   and no authenticated reporting scope. A proof is not customer ownership.
4. The receiving extension's Owner workflow checks its own organization,
   invitation and ACL rules, then calls the approval SDK method. An explicit
   Core administrator approval is also available. There is no auto-approval.
5. The sender retries its same durable completion to collect the public
   credential. Only then can it send the locally consented status projection.

Outgoing states: `new -> pending -> active`; `revoked` is terminal for that link.
Incoming states: `challenged -> pending -> active -> revoked`. Revoke increments
the incoming credential generation, removes its certificate and keeps the
binding tombstone. It cannot be bypassed by delayed approval, old proofs,
credential rotation or automatic reconnect. Late pending replies cannot
downgrade active outgoing links. A revoked incoming binding can be explicitly
reopened by a Core administrator, using its current generation; it then requires
a **new** locally approved link/proof and another receiver approval. Reopening
does not itself activate anything and cannot change a pinned installation key.

Challenges/request signatures last at most 120 seconds, with at most 30 seconds
of forward clock skew. Pending Owner approval has a 15-minute deadline.
Certificates last at most 24 hours. Rotation must happen **before expiry**;
expired credentials do not rotate or reauthorize themselves. There is no
automatic renewal daemon in Core: the extension schedules enrollment/reporting
and proactive rotation, with bounded backoff, through these SDK methods.

Same exact completed proof returns the same public receipt/certificate; it
does not issue a second binding or credential, including after a lost response
or process restart. A completed proof cannot be replaced with another proof.
Rotation persists one prepared request and an exact-response receipt. Retry
that same request after an uncertain response; do not generate a second
rotation. If it never arrived before its deadline, explicit recovery/reapproval
is required. Old credential generations are denied immediately. Durable
one-time nonces prevent signed request replay across receiver restart.

Local withdrawal, consent revision changes and uninstall fence network replies
before they can update local state. Revocation cannot retract a snapshot already
sent or cancel an operation already dispatched; the receiver must discard or
retain previously received data according to its own business retention policy.

## Manifest and SDK contract

New permissions require `service.sdk_version: "1.2"`. Declare matching permissions
in both `application-extension.json.platform_permissions` and Module Manifest v2
`permissions`. Existing G1 identity permissions also work with SDK 1.1.

- Sender: `installation.peers.enroll`, `installation.peers.report`,
  `installation.status.read`; Module Manifest also needs `network.outbound`.
- Receiver: `installation.peers.receive`, plus `peer_receiver` declaring
  `bootstrap_operation_id` and `report_operation_id`.

Receiver operations are exactly two separate `kind: "command"` declarations,
with `idempotency: "required"`. Their singleton audiences are respectively
`installation_bootstrap` and `installation_peer`. No mixed human/internal
audiences, required human permissions, emitted events or extra peer operations
are accepted. They may coexist with ordinary application UI/business operations.

Bootstrap payload is exactly `binding_id`, `installation_identity`,
`requested_scopes`. Reporting payload is exactly `projection`; its durable
`report_id` is supplied as `context.idempotency_key`. Declare those input fields
with their string/object/array types. Handler outputs are not returned to the
sender; use an empty object output schema/result. Reporting handlers must
persist deduplication by `(machine.binding_id, idempotency_key)` before making
their own durable business changes. Core replay protection is not a replacement
for application idempotency after a lost host response.

| `ApplicationPlatformClient` method | Local platform action | Permission |
| --- | --- | --- |
| `enroll_installation_peer(link_id)` | `installation.peers.enroll` | enroll |
| `list_installation_peers()` | `installation.peers.list` | enroll or receive |
| `approve_installation_peer(binding_id, expected_generation=...)` | `installation.peers.approve` | receive |
| `revoke_installation_peer(peer_id, direction="inbound"/"outbound")` | `installation.peers.revoke` | receive/enroll respectively |
| `rotate_installation_peer(link_id)` | `installation.peers.rotate` | enroll |
| `get_installation_status(link_id)` | `installation.status.get` | status.read |
| `report_installation_status(link_id, report_id=...)` | `installation.peers.report` | report + status.read + enroll |

The sender cannot choose arbitrary origins, payloads or Node/field scope through
the SDK. A local administrator creates/changes consent through the Core API.
Status/enrollment/rotation SDK results use shared validated models, not private
keys or user sessions. `list` returns public identities, states, revisions and
consent selections, up to 100 entries per direction.

`OperationContext.machine` is an immutable `InstallationMachineActor` containing
`installation_id`, `key_id`, `binding_id`, `generation`, `scopes`. The Core
constructs it **after** verifying proof/credential/signature. The host constructs
this SDK object only after authenticating its existing signed Core envelope.
Bootstrap scopes are empty; reporting scopes are exactly
`("installation.status.report",)`. There is no `user_id`. Payload context claims,
human admins, kiosk subjects and anonymous callers cannot gain these audiences.
Core proves the machine subject/technical scope; the extension still decides
organization ownership and whether a report belongs to that organization.

## HTTP wire and limits

Base path: `/api/v1/installation-peers`.

| Method/path suffix | Request/result |
| --- | --- |
| `GET /v1/identity` | Public `InstallationIdentityResultV1`; pin its `identity` independently |
| `POST /v1/enrollments/start` | `PeerEnrollmentStartV1` -> `PeerEnrollmentChallengeV1` |
| `POST /v1/enrollments/complete` | `PeerEnrollmentCompleteV1` -> `PeerEnrollmentResultV1` |
| `POST /v1/rotate` | Signed `PeerRequestV1` with empty payload -> `PeerEnrollmentResultV1` |
| `POST /v1/report` | Signed `PeerRequestV1` containing `PeerReportV1` -> fixed receipt |
| `GET`, `PUT /origin` | Administrator read/configure canonical HTTPS origin |
| `GET /applications/{module_id}` | Administrator binding/consent list |
| `POST /applications/{module_id}/outbound` | Administrator origin, receiver_identity, target_module_id, consent |
| `PUT /applications/{module_id}/outbound/{link_id}/consent` | Administrator consent + expected_revision |
| `POST /applications/{module_id}/inbound/{binding_id}/approve` or `/reopen` | Administrator expected_generation |
| `DELETE /applications/{module_id}/{direction}/{peer_id}` | Administrator revoke |

All `/v1` peer endpoints require HTTPS and the exact configured origin, without
query parameters. Bootstrap POSTs reject Authorization headers. Report/rotate
require exactly `Authorization: ThreeMM-Peer`; their JSON carries a public
receiver-signed PoP certificate and a sender-signed request, **not** a bearer
secret. User/Agent APIs continue to reject this scheme.

Certificates bind full issuer/subject G1 identities, HTTPS origin, target module,
scope, binding ID, generation and issue/expiry timestamps. Requests bind the
certificate, POST method, exact path, nonce, timestamps and complete payload.
Ed25519 signatures use padded standard base64, and canonical JSON uses sorted
keys, compact separators, ASCII escaping, JSON-mode UTC `Z`, and rejects NaN.
Domain-separated signed bytes are:

- start: `3mm.installation.peer.start.v1\n` + start JSON excluding signature;
- certificate: `3mm.installation.peer.credential.v1\n` + claims JSON;
- request: `3mm.installation.peer.request.v1\n` + request JSON excluding signature.

The challenge resource is `peer.enroll:<request_id>:<sha256>`, where the hash
covers canonical `{"module_id": ..., "scopes": [...]}`. Binding/link IDs are
`peer_<32 lowercase hex>`, report IDs `report_<32 lowercase hex>`, nonce/challenges
canonical unpadded base64url of 32 random bytes. Module IDs are bounded to 160
characters. Unknown model fields/contract versions and non-integer generations
are rejected. Request/response bodies are capped at 128 KiB; projection at
64 KiB. Core bounds each application's non-revoked outgoing links to 32 and the
receiver's unexpired bootstrap queue to 256. Expired unapproved entries can be
pruned after 24 hours; active/revoked trust records are retained.

Outgoing HTTPS verifies certificates, disables redirects/environment proxies,
uses 4-second connect and 12-second HTTP I/O timeouts, and bounds streamed replies.
Timeouts leave durable state for explicit retry, not a guessed successful action.
The accepted report receipt is exactly `status: "accepted"`, `report_id`,
`installation_id`; it cannot contain reverse commands or receiver business data.
One outstanding report/snapshot is persisted per link. Retry uses the same
report ID and snapshot, with a fresh signed request nonce. A different report
cannot overwrite an unresolved one. The last accepted receipt is cached; callers
must use a new ID for a new sample. This is not a historical reporting queue.

Deployment must configure a real HTTPS ingress and the ASGI server's trusted
proxy/scheme/Host handling. The routes do not themselves trust arbitrary
Forwarded headers and have **no HTTP fallback**. A Cloudflare hostname alone
does not supply this configuration. No live ingress was configured or verified
in this stage. G4 authentication-log hardening is included in beta.31 (see
below); it must be included in the deployed build before public use. Ingress
rate limits and a public-ingress acceptance test are still needed. The isolated
Raspberry TLS/Linux acceptance below does not configure that public ingress.

## G3 projection

`ProjectionConsentV1` explicitly selects `summary_fields`, `node_ids`,
`node_fields`; empty selection is allowed. No wildcard or automatic future-Node
inclusion. At most 64 unique Nodes and 9 Node fields, within the 64-KiB result
limit; oversized results fail rather than silently broaden or truncate consent.
Both Node IDs and Node fields must be selected together. Only registered,
non-revoked IDs can be granted. SQL filters consented IDs before reading source
records; only requested source families/fields are used, not a broad serializer.

Summary allowlist: `core_version`, `protocol_version`, `sdk_version` from actual
Core runtime/version sources. Node allowlist:

- `display_name`, `role`, `protocol_version`: registry revision/update time;
- `online`, `last_seen_at`: latest received heartbeat, existing offline policy;
- `architecture`, `memory_total_bytes`, `root_free_bytes`: latest inventory;
- `agent_version`: **unknown** until the Agent contract reports its actual
  version. Neither extension, desired module nor OTA version is substituted.

Each `ProjectionValueV1` has known/unknown status, bounded primitive value or
null, source, observed_at, received_at and revision. Heartbeat/inventory IDs
identify source revisions; their source/receive timestamps distinguish age
from report generation. Runtime observations use source-file modification times
and version revisions, not heartbeat times. Missing/deleted/revoked selected
devices and unreported/malformed fields are unknown, not fabricated offline or
zero values. `generated_at` alone is not evidence of a fresh measurement.

The result includes installation_id, consent_revision and generated_at. Local
consent changes take a database write fence, increment revision and clear any
pending cached report. Disabled/uninstalled applications, withdrawn links,
wrong instance ownership and changed installation keys fail closed. No network
credentials, sessions, configuration, GPIO/capability payloads, business records
or command permissions are exposed.

## Migration, restore and handoff

Alembic `526ab1c2d3e4`, after G1 `4159a0b1c2d3`, adds five platform tables:
`installation_peer_origin`, `installation_peer_inbound`,
`installation_peer_outbound`, `installation_peer_nonces`,
`installation_peer_audit`. The legacy dynamic baseline excludes them. Machine
events use the dedicated audit table without fabricating a human user; human
consent/approval/revoke also use the existing human audit. Uninstall retains
revocation tombstones rather than transferring old trust to a reinstall.

Full/portable backup already includes these records in the protected Core DB.
Restore quarantines **both directions** in the validated staging database before
services stop: revoke, clear certificates/report cache, advance generations/
consent revisions and clear nonces. Identity is preserved under G1's key rules;
old trust is not automatically restored. The immutable archive is unchanged,
and restore rollback restores the original live DB. Legacy backups without peer
tables still work. Reapprove a new sender link; explicitly reopen/reapprove the
retained receiver binding when needed. Retire the old source installation first.

A known installation ID with a different public key is denied, as is another
enrollment for an existing live binding without review. **Identical full clones
with the same database and private key cannot be distinguished by this protocol.**
Running both copies is unsupported; an independent clone requires clean Core
identity and new consent/approval. G2 credential generations are not G1 signing
key rotation, for which there is no API.

Next CME CM3 work is its local administrator consent UI, central Owner approval,
organization mapping, persistent report deduplication and its own durable
retry/rotation schedule using SDK 1.2. Neither business UI nor automatic cloud
connection is delivered by this Core stage. Package compatibility must require
Core `0.3.0-beta.31` or later with SDK 1.2; do not claim released
beta.30 supports it. Zero/local operations remain independent of cloud reporting.

## Local verification

Final combined targeted/regression run: **166 passed, 1 skipped** in 63.24s,
with 120 existing/fixture deprecation, JWT test-key and duplicate-ZIP warnings.
The skip is the existing Linux-only platform socket test. `git diff --check`
passed. An earlier UI artifact/catalog test failed once, passed in isolation,
and also passed in this final combined run; no unrelated compiler change was made.
Tests cover real
database transitions and HTTP handlers with an in-process HTTPS TestClient,
signatures/replay, two installations, restart/lost responses, concurrent proof
completion, consent withdrawal, projection filtering, migration and restore
quarantine. Signed local SDK/host envelopes use in-memory sockets on Windows;
they are not a real TLS connection or Raspberry Unix-socket acceptance test.
These implementation checks did not perform OTA/deploy, a live cloud test or
frontend changes. Release preparation is recorded at the top of this document.

## G4 — authentication log hardening

Included in beta.31. `backend/routes/user.py` no longer
logs registration/login bodies, user objects, Authorization headers, tokens or
decoded JWT claims. Its error and language fallback logs, and optional token
decoding in `backend/utils/auth_dep.py`, log only literal event names and
exception class names. Raw exception text/tracebacks are deliberately excluded:
SQLAlchemy errors may contain password hashes and bound session tokens.
Authentication, sessions, HTTP responses and audit/database behavior are unchanged;
there is no new migration or SDK/Core version change.

Eight G4 tests run DEBUG-level checks with fixture-only passwords, hashes,
tokens, claims and SQL exceptions. They cover successful registration/login/
profile, duplicate registration, wrong/blocked/missing login, expired/invalid/
revoked profile tokens, validation failures and optional auth error handling.
An AST guard also checks the other user-management logging branches without a
large test matrix. Together with session/user-management/blocking regressions:
**16 passed** in 6.14s (68 existing deprecation warnings); `git diff --check`
passed. This is scoped authentication-log coverage, not a system-wide logging
audit or a guarantee about third-party debug/access/SQL logging configuration.
No old log files were inspected/erased and no real credentials were used.

## Raspberry HTTPS/Linux acceptance — 2026-10-02

Passed on `rasp-3mm` (aarch64, Python 3.13.5), in a separate temporary checkout
and virtualenv. The reusable opt-in test is
`backend/tests/test_installation_peer_https.py`. **4 passed** in 59.90s:
one end-to-end scenario plus three local-consent module-ID regressions.
The eight G4 authentication-log tests also passed on this Linux host.
Five fixture/deprecation warnings remain in the acceptance run.

Two independent Core processes have their own SQLite databases, encrypted G1
keys, origins and application platform sockets. Two actual application hosts
load a fixture service artifact and SDK migrations, and persist report receipts
in their own application databases. No Core gateway, peer transport or SDK
socket is replaced with an in-memory transport.

Verified:

- Real loopback HTTPS connections; untrusted CA and wrong hostname are denied.
  Production `peer_http` still uses `verify=True` and `trust_env=False`.
  A private test CA is injected into the trust bundle of fixture processes only;
  system and production trust stores are not changed.
- Real administrator HTTP consent creation/update, separate receiver SDK
  approval, and denial of reports before approval. Human bearer credentials
  cannot authenticate a machine report.
- Only explicitly selected summary fields, Node ID and Node fields are sent;
  an unselected Node/private inventory sentinel is absent and unreported Agent
  version remains unknown. The receiving host gets a machine-only SDK actor.
- Actual connection interruption after completion/report/rotation processing;
  retry uses durable state, with receiver process restarts between report and
  rotation retries. The fixture service deduplicates report effects.
- Signed nonce replay remains denied after restart; old credential generations,
  expired requests, revoked bindings and local consent withdrawal are denied.
  The 24-hour credential-expiry case uses a fixture clock advanced by 25 hours,
  not a wall-clock wait or a system clock change.

The test exposed a real local-consent API defect: its private module-ID regex
rejected valid manifest IDs containing the `3mm` component. The route now reuses
the shared `MODULE_ID_PATTERN`; valid IDs are accepted and invalid IDs still fail.
No authentication bypass or manifest exception was added.

Run in an isolated Linux checkout/virtualenv with Core dependencies plus
`pytest` (never install test dependencies into the active release):

```sh
test_root="$(mktemp -d /tmp/3mm-peer-test.XXXXXX)"
DATABASE_URL="sqlite:///$test_root/parent.db" \
APP_CONFIG_FILE="$test_root/no-config.json" \
THREE_MM_RUN_PEER_HTTPS_TEST=1 \
python -m pytest --noconftest backend/tests/test_installation_peer_https.py -q -s
```

The test skips by default and on Windows. It stops its own child processes and
removes their temporary keys/databases, retaining diagnostic logs under pytest's
temporary test output. Do not treat the fixture receiver as CME business ACL or
organization-ownership implementation: that remains the extension's workflow.

Before/after checks confirmed the live `beta.30` release symlink and Core/Agent
PIDs were unchanged; Core `/ready` returned `{"status":"ready"}` afterwards.
Zero, NetworkManager, live application/Child Center data and systemd services
were not changed. This was not an OTA/deploy, public cloud test or release.
All G1–G4 source changes and this API fix are in the beta.31 release scope.
The production requirements now include pinned `httpx` for the peer transport;
the minimal Node requirements are unchanged.

## Beta.31 release preparation — 2026-10-02

Combined scoped identity/peer/SDK, authorization logging, migration,
backup/restore, package and Node Update checks: **199 passed, 2 skipped** on
Windows in 141.31s. The skips are opt-in Linux HTTPS acceptance (already run
on Raspberry above) and the existing Linux-only platform socket test.
The production frontend build and staged `git diff --check` passed.
Node Update includes a read-only catalog/history check and rejects a redundant
prepare only when the newest OTA outcome confirms that same release. Missing,
invalid or unconfirmed outcomes stay unknown; revoked devices remain rejected.
