# C12/C13 — Installation authority, lifecycle and recovery

Local implementation: 2026-10-03. Shared Device/Node Platform, **not Fleet-only**.
Device protocol stays `1.0`; SDK stays `1.3`. C11 is tracked separately in
[the capability-contract report](PLATFORM_NEUTRAL_C11.md).
No ESP code, frontend changes, deployment, reset, commit or release in this step.

## Authority, not an address

`device_id` identifies the node. A credential authenticates that device to Core.
Authority identifies the selected Core installation by its stable installation
ID and Ed25519 public-key fingerprint; a URL only locates that installation.
Use the existing encrypted `core_installation_identity`, not another fleet secret.

The new shared `device_platform.py` defines bounded, domain-separated proofs.
The caller creates a fresh 256-bit nonce and a short-lived challenge, bound to
device ID, credential ID and operation (plus command ID for a physical permit).
Core signs its installation identity, challenge and complete response payload.
Commands, desired state and execution permits are verified before use. An
identity proof cannot be substituted for an execution permit or command.
Command expiry, durable receipts and the existing single-use execution permit
remain mandatory; a signature does not prove that a physical action happened.

Linux Agent and the independent mock runtime use the same portable client helper
(`three_mm_protocol.device_authority`), private authority pin and signature
verifier. This helper does not import the Linux/Agent module runtime.
Minimal Node packages include the shared protocol helpers and
use the already-reviewed OpenSSL dependency when cryptography is absent; no
ARMv6 cryptography wheel is added. A pin is not silently replaced when a URL,
credential or installation key changes. A co-located bootstrap compares the
pin with its trusted local Core database and preserves it across credential
repair. It refuses revoked devices until explicit administrator recovery.

## Bootstrap and backward compatibility limits

- Remote enrollment still requires explicit administrator approval. First key
  adoption is TOFU at the selected, approved endpoint; subsequent management is
  cryptographically pinned. TOFU does **not** defeat an attacker controlling the
  first association. Use a trusted setup network/TLS for that association. This
  step is not a new PKI or an out-of-band fingerprint-confirmation UI.
- Updated nodes without a pin can retain legacy behavior if an older Core lacks
  the proof endpoint (404/405). A pinned node never accepts this downgrade. Old
  nodes/APIs remain usable but do not gain signature verification without a Node
  update. Proof failure, redirects, corruption or a missing key do not trigger
  fallback. An address change alone never authorizes another installation.
- Existing Node setup deliberately still refuses a different stored Hub URL;
  automatic alias discovery/rebinding is not added. The transport also checks
  the key, so matching an address is no longer sufficient to change authority.
- A full clone containing the **installation private key** is the same authority
  cryptographically. Detecting/managing such clones is a separate requirement;
  copying only a device credential to another installation does not suffice.
- Existing pins expect the same installation key after restore. Restore
  the existing encrypted identity and captured master key; do not regenerate a
  key to hide a recovery error. Existing rollback releases do not understand the
  new pin; security guarantees require the updated runtime, not a downgrade.
- Clock synchronization and the existing bounded command deadlines still apply.
- Signatures provide authenticity, not transport encryption. Device credentials
  and reports still need a trusted local network or TLS; this stage does not
  silently replace the existing transport-security deployment policy.

## Common Core API and reassignment

Existing paths and wire payloads are unchanged. Optional new HTTP adapters:

| Route under `/api/v1` | Authorization / purpose |
| --- | --- |
| `POST /pairing/authority-proof` | Anonymous possession proof only; no credential or ownership grant |
| `POST /devices/{id}/authority-exchange` | Device credential; signed command, desired state, permit or platform snapshot |
| `PUT /devices/{id}/lifecycle` | Device credential; revisioned active/degraded/recovery report |
| `GET /devices/{id}/platform` | Core administrator; authority/lifecycle/connectivity snapshot |
| `POST /devices/{id}/authority/release` | Core administrator; device-ID confirmation and expected revision |
| `POST /devices/{id}/authority/prepare-enrollment` | Core administrator; explicit same-installation recovery preparation |

The signed exchange uses the same queue, desired state and application permit
services as the existing APIs. Long-poll waits belong to the HTTP adapter;
revocation is checked again after waiting. Incoming proof bodies have the common
Node size/depth bounds. Only the existing bounded module-install package field
gets the larger response allowance. Core-generated lifecycle/authority audit
events cannot be forged by a device through the event endpoint.

Reassignment procedure (not performed on any live device here):

1. Administrator releases the node from A. All its credentials are revoked.
   Never-dispatched queued commands become `not_dispatched`; delivered work and
   uncertainty remain recorded. Device ID, desired state and modules are retained.
2. Local operator stops the Agent and explicitly resets its authority. Old
   credentials, pin, enrollment, pending outbox and reconciliation evidence move
   to private quarantine. They are **not** delivered to B. Identity, modules,
   command receipts and physical execution journals remain.
   Review retained module/local application configuration before use at B; a
   credential rotation is not a wipe of previously authorized local behavior.
3. Select B through setup and request new enrollment with a newly generated
   credential. Administrator approval is still required. Pin B's identity.
   A's key/credentials no longer authorize new commands on this runtime.
4. To return to the **same** Core, use `prepare-enrollment` after release, then
   approve the new request. Historical approvals are retained as archived
   records, not deleted. Old credentials are never reactivated. The co-located
   local Agent uses the trusted bootstrap after explicit recovery preparation.

If A is unavailable, physical/local root recovery can remove local authority,
but cannot revoke a credential in an unreachable database. Revoke it on A when
available. Local reassignment still rotates the credential and rejects A's key.

Linux reference action, only after release/review and explicit device selection:

```bash
sudo systemctl stop 3mm-agent.service
sudo env PYTHONPATH=/opt/3mm/current /opt/3mm/current/.venv/bin/python \
  -m three_mm_runtime.device_authority_reset --confirm-device-id dev_REPLACE_WITH_REAL_ID
```

This command does not edit networking, reboot or restart services. It also
quarantines the optional Node OTA approval pin; a different Hub's update key
needs fresh explicit approval. An interrupted reset leaves a recovery marker
that blocks normal Agent startup/enrollment. Do not delete that marker to bypass
review. The mock runtime has an equivalent explicit foreground `reset_authority`
action backed by private SQLite history; close/reopen it at the intended Core.

## Lifecycle is not connectivity

Shared states: unprovisioned, provisioning, enrollment_pending, active, degraded,
revoked, recovery and unowned. Pre-approval setup/enrollment remain represented
by existing provisioning/request records; no fake approved device is created.
Registered devices have an additive, revisioned `device_platform_states` record.
Core ownership/revocation overrides device lifecycle reports. A device cannot
self-clear release/revocation or automatically enroll again to bypass it.

`active + offline` is valid. Connectivity is calculated from heartbeat freshness,
not persisted as ownership. Reports change lifecycle explicitly; a connection
failure does not erase setup, binding, desired state or registration. Recovery
blocks command queueing/delivery, desired-state application and physical permits.
Diagnostics/platform, heartbeat and evidence reporting remain possible. Safe
local recovery implementations belong to each runtime, not Core hardware logic.

The shared reset policies are intentionally distinct:

| Policy | Device ID | Authority/credentials | Execution evidence |
| --- | --- | --- | --- |
| Network reconfiguration / Setup AP | Preserved | Preserved | Preserved |
| Authority reset / reassignment | Preserved | Removed; next enrollment rotates credentials | Preserved; pending installation-specific outbox quarantined |
| Explicit full factory reset | Regenerated under existing Linux policy | Removed | Cleared as part of the expressly destructive reset |

This does not redesign Linux Master reset: its current release, OS/SSH access
and retained backup behavior remain. It clears 3mm provisioning/application state
and enters setup; it is **not** secure erasure of all OS/NetworkManager profiles.
Network recovery continues to preserve existing 3mm identity and credentials.
Revocation is never a synonym for any of these resets.

## Migration and evidence

Migration `859de4f5a6b7` adds/backfills platform state. It does not replace device
IDs, credentials, module installations, capabilities or desired/reported state.
Downgrade removes only the new table. The historical baseline exclusion list
is updated so clean installs create this table at its correct revision.

Focused tests exercise real Core services/SQLite/HTTP with Linux transport and
independent mock runtime: key mismatch even with copied credentials, nonce,
tampering, expiry, unsigned-downgrade refusal, explicit release/second approval,
active/offline, recovery gating, restart, credential repair, preserved reset
evidence, interrupted reset and populated/clean migration. The minimal verifier
also checks real Ed25519 bytes through OpenSSL without cryptography imports.

Final focused regression run: **69 passed** (command/permit authorization,
security boundary, lifecycle/authority, reset, local bootstrap and Node
packaging). Migration and Linux/mock transport compatibility were also checked
in the preceding focused run: **74 passed, 1 skipped** (POSIX-only permission
check on Windows). These runs overlap; their totals must not be added together.

Local proof is not a deployment or electrical test. Hub/Zero performance, POSIX
permissions, real process/reset/restore behavior and separate Fleet UI adoption
remain acceptance gates. No reset/reassignment UI or ESP implementation was added.
