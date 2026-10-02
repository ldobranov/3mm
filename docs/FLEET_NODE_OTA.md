# One-Node runtime update from Fleet

Updated: 2026-10-02. The user reports a successful real **Hub -> Node runtime
update**, with remaining bugs. This is happy-path acceptance based on the user's
confirmation, not an independent inspection of release versions or final logs.
Stage 4 is in progress; failure-path acceptance and bug triage remain open.
This updates the complete Node runtime, not an installed Agent module package.
Beta.25 contains the earlier execution foundation/prepare transport, not the
signed remote-apply path. Fleet 0.1.7 implements the Node OTA interface.

## User-reported physical update — 2026-10-01

- Evidence: the user explicitly confirmed a successful update from Hub to Node.
- Bugs were reported but not yet described; do not infer causes or fixes.
- Exact Hub/Node/Fleet versions, operation ID and final installation report were
  not supplied with this confirmation. Record them with the reproducible bug list.
- This does not confirm failed-health rollback, reboot/network interruption,
  lost-response recovery, preserved GPIO/binding state or clean-media onboarding.
- No live changes or additional physical test were performed by this planning chat.

## Delivery stages

1. **Node execution foundation (implemented):** versioned handoff, root-only staged
   artifact validation, narrow local helper, detached immutable installer and
   durable outcome. The minimal artifact includes the helper without Core.
2. **Hub/Agent orchestration (implemented):** administrator-scoped catalog and preparation from
   official Node releases, authenticated per-device download, bounded disk use,
   Agent handoff and durable prepare-status reporting. Zero downloads from its Hub;
   it need not access the internet. Explicit apply is signed by the Hub and
   validated against root-pinned trust on the Node. Never accept arbitrary URLs
   or shell commands. Durable final reporting is separate from command acceptance.
3. **Optional Fleet UI (implemented in Fleet 0.1.7):** version/current status, check, prepare, review and
   explicitly install one device; reconnect and show the final outcome.
4. **Physical acceptance and publication (in progress):** the user reports a
   successful real update; remaining bugs and failure tests are still open.
   The full acceptance procedure is to publish/bootstrap a release containing
   signed apply on both Hub and Node, explicitly pin the Hub key, then test a
   subsequent real Fleet update, failed-health rollback, network/reboot and
   lost-response tests. Only then advertise subsequent updates without SSH.

No automatic fleet-wide updates, rollout groups, Cloud enrollment or concrete
business-extension behavior are included. Internet/catalog loss must not stop
existing local work. An already verified staged package can later be installed
without a fresh public-network download.

## Implemented Stage 1 boundary

- `three_mm_protocol/node_updates.py`: strict versioned metadata, explicit
  confirmation, exact device/release/archive identity and an aware-UTC bounded
  handoff deadline (at most 120 seconds). No caller-controlled path or command.
- `agent/node_update_client.py`: bounded AF_UNIX request/status client. It does
  not execute root commands. The Node command loop delegates signed apply to it.
- `three_mm_runtime/node_update_helper.py`: root / `3mm` peer checks, persisted
  operation identity and replay conflict detection; fixed detached worker.
- `deployment/apply_node_update.py`: validation and existing immutable installer.
  Final success is distinct from acceptance/delivery and requires healthy target
  runtime with the original device identity and a responding update helper.
  `rolled_back` means the previous release is verified healthy and unchanged
  after an installer failure; it also covers failure before release mutation.
- Root-controlled state: `/var/lib/3mm-node-update`, outside service-owned
  `/var/lib/3mm`. Socket: `/run/3mm-node-update/helper.sock`. The helper reads
  only an already root-prepared `staging/<operation_id>/release.tar.gz`.

Core provides administrator-scoped official Node release discovery, Hub-side
verified staging, authenticated per-device archive delivery, `agent.update.prepare`,
and explicitly approved `agent.update.apply`. Apply requires completed matching
preparation, unexpired/reverified Hub staging, fresh Node readiness and idle
hardware/command state. An existing operation reuses its original approval and
deadline; it does not receive a new authorization lifetime. Fleet 0.1.7 exposes
the installation workflow. No release is called updated until the durable final
helper outcome is known.

## Independent Hub approval

Checksums alone do not authorize root execution. A compromised service account
could otherwise supply both an archive and its hash. Apply now requires an
Ed25519 Hub signature over the exact operation, device, release, digest,
confirmation and original UTC handoff deadline, with a versioned domain separator.
The helper and detached worker both verify it; no unsigned execution fallback is
available. Legacy unsigned records remain readable for diagnostics, not execution.

The Hub keeps its private approval key beside the update policy, normally
`/var/lib/3mm/core/node-update-approval-key.pem`, outside immutable releases and
temporary staging. The public endpoint is
`GET /api/v1/devices/node-updates/approval-key`. No private key is returned.
This is **Hub approval**, not a claim of independently signed GitHub artifacts;
the Hub still verifies official release metadata, size and checksum before approval.

The Node pins the public key and its own device identity in the root-controlled
`/etc/3mm/node-update-trust.json`. Agent credentials or environment files cannot
replace this trust. Signature verification uses the OS OpenSSL executable,
declared as a Node APT prerequisite; it adds no Core/cryptography dependency to
the minimal Python runtime. Root-controlled temporary files, fixed arguments and
a bounded subprocess are used; caller commands, executable paths and key paths
are never accepted by the socket API.

### One-time trust bootstrap for existing Nodes

First install a **published release containing this signed path** on Hub and Node
using the existing immutable bootstrap. Beta.25 only contains the earlier
foundation: it is not sufficient for signed remote apply. This guide does not
identify the live release used in the user's successful update.

On the Hub, read `/api/v1/devices/node-updates/approval-key` and verify its
`key_id` fingerprint through a trusted connection/administrator session. On Zero:

```bash
sudo /opt/3mm/current/.venv/bin/python /opt/3mm/current/deployment/trust_node_update_hub.py --hub http://rasp-3mm.local
sudo /opt/3mm/current/.venv/bin/python /opt/3mm/current/deployment/trust_node_update_hub.py --hub http://rasp-3mm.local --key-id <verified-key-id>
```

The first command only displays the fetched fingerprint; the second explicitly
pins the independently verified value. Plain HTTP is a trusted-LAN beta bootstrap,
not protection against an active LAN attacker. Use authenticated TLS/trusted
out-of-band verification where required. The CLI refuses redirects, changed keys
and changed device identities; it never silently trusts or rotates a key.
Integrating this root-authorized step into customer onboarding remains future work.
Key loss, reassignment, factory reset or Hub restore with a different key require
explicit trust reconciliation, not automatic re-enrollment. Preserve the Hub key
alongside its persistent state. A backup must not be assumed to contain this new
key until that path is explicitly tested.

The Agent reports signed-helper support and the pinned key/device identity in
`reported-state.node_update`. Core refuses apply until fresh state matches its
own approval key. This avoids queueing an install on an older unsupported Agent.

## API and durable result

- `GET /api/v1/devices/{device_id}/node-updates/check?channel=beta` (Core
  beta.31+): read-only administrator check of the official catalog. Returns
  `current_release_id`, `latest_release_id`, `latest_version`, `channel` and
  `update_available`. It never downloads, prepares or installs an archive.
- `POST /api/v1/devices/{device_id}/node-updates/prepare`: administrator-only
  official Beta/Stable/Test preparation; returns the operation and prepare command.
- `POST /api/v1/devices/{device_id}/node-updates/{operation_id}/apply`:
  administrator-only, body `{"confirmed_install":true}`. The signed handoff
  expires within 120 seconds; this limits starting, not the full install duration.
- `POST /api/v1/devices/{device_id}/node-updates/{operation_id}/report`:
  paired-device authentication, exact `NodeUpdateOperation` body. The path,
  device, operation, release and hash must match an approved apply command.
- `GET /api/v1/devices/{device_id}/node-updates/{operation_id}`:
  administrator-only prepare state plus `installation` and apply-command identity.
  The installation field, not a succeeded command handoff, determines the outcome.

`current_release_id` is derived only from the newest durable OTA installation
outcome held by this Hub: `succeeded` selects the new release, `rolled_back`
selects the verified previous release. Missing, malformed, failed or uncertain
outcomes return null, as does a newer attempt without a final report. A known
matching release returns `update_available: false` and prepare refuses to
download it again. Unknown is **not** up to date. This is not a fresh Agent
version query: direct SSH/manual installs may not be represented by Hub history.
Fleet consumes this generic Core endpoint; no Fleet ZIP is bundled in Core.

Core stores handoff and installation outcome separately in existing command JSON,
so no database migration is required. A late handoff acknowledgement cannot erase
a final report. Terminal outcomes cannot regress; conflicting reports fail closed.
Unconfirmed/unknown applies block another install and are never automatically
replayed or erased to free the device.

While a Node update is pending or unconfirmed, Core also pauses new physical,
GPIO-configuration and module-lifecycle commands for that Node. Conversely,
pending device mutations prevent approval of an update. Existing idempotent
lookups keep their original result; a verified terminal OTA outcome releases the
queue interlock. This is an execution fence, not a guarantee of exactly-once
physical action. An ambiguous handoff still requires explicit operator recovery;
the future recovery UI/API must not clear it merely because a command expired.

Before contacting the helper, Agent persists the signed request in private
`node-update-tracking.json`. After restart it only polls the exact root operation
and reports the latest outcome; it never resumes installation from this file.
Offline reports retry from durable state. Intermediate reports are not placed in
the generic outbox where an old `accepted` could overtake a terminal result.

Operations use `nodeupd_<32 hex>` and carry `device_id`, `release_id`, SHA-256,
original `created_at`/`expires_at` and `confirmed_install: true`. Local envelopes
are `{"action":"apply","request":<signed authorization>}` and
`{"action":"status","operation_id":...}` (latest status remains supported); responses
carry a validated operation or no prior operation. Safe outcome states are
`accepted`, `running`, `succeeded`, `rolled_back`, `failed`, `unknown`.
Lost replies/restarts reuse the identity. Unresolved interrupted work stays
unknown, not queued again. A missing unit or delivery acknowledgement does not
prove successful installation.

History is limited to 128 operations and refuses new work when full. Controlled
retention and operator resolution remain follow-up work; active or unknown attempts must never
be discarded simply to permit another install. The detached worker has its own
45-minute systemd deadline for the entire process tree, independent of helper
restarts.

The archive must match Node/ARMv6/Python 3.13 metadata, expected digest and
release identity, and pass bounded archive/path checks. The existing installer
retains its deployment lock, offline wheelhouse, current/previous links, health
checks and rollback. Agent identity, Hub binding and GPIO state remain outside
the release tree. The root helper is deliberately separate from the Hub's
Core-dependent update/backup helper.

The new helper service survives normally across boots; its detached install
worker does not depend on the old Agent or helper remaining alive. Rolling back
to a Node release predating the helper removes its unit and restores the older
recovery-only service set. Do not claim remote management after that downgrade.

## Verification

Beta.31 release preparation (2026-10-02): **16 Node Update route checks passed**,
including administrator/device guards, read-only unknown results, redundant
prepare rejection and no fallback to an older success after an uncertain attempt.
The broader scoped Core/SDK/Node preparation run passed 199 checks; this does
not add a physical Node update or close the failure-path acceptance below.

Combined scoped check on Windows (2026-10-01): **134 passed, 2 skipped**.
The skipped tests require POSIX ownership and `O_NOFOLLOW`; they remain Linux
acceptance gates. Actual Ed25519 verification also passed through the available
OpenSSL executable on the development host. No physical Node update was run
as part of those automated checks; the later user-reported update is recorded above.

Focused tests cover signed approvals, wrong keys/devices, tampering, unsafe trust
files, original deadlines, durable replay, Agent restart/lost replies, outcome
monotonicity, device/admin authorization and unchanged prepare/packaging behavior.
They use isolated state and fake installers; no live device, network mutation or
GPIO action is performed. Unix ownership boundaries still require Linux runs.

Pending: capture the successful test's versions/final outcome and remaining bugs;
verify signed-path trust, failed-health rollback, Hub/network interruption,
Agent/Node reboot and lost install response. Verify identity, Hub binding and GPIO
configuration after each case. Only final `succeeded` may be labeled "Updated".
