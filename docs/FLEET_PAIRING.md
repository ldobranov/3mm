# Fleet pairing — local beta implementation

Updated: 2026-09-30. Implemented locally; not yet deployed or accepted on Zero.

## User flow

1. Update the Hub first, including migrations and prebuilt frontend, then the Node.
2. In Node Wi-Fi Setup select the Node role and the local Hub URL (for example
   `http://rasp-3mm.local`). Existing completed Setup is read on Agent restart.
3. Open Devices on the Hub as an administrator. Under New devices, verify the
   name and device ID and choose Add device. No pairing code is needed.
4. The Node receives approval on its next retry and starts the existing inventory,
   heartbeat and command connection. The list refreshes while approval completes.

The older beta.21 binaries do not contain this flow. Updating just the UI is not
sufficient. Existing code-based pairing remains compatible.

## Durability and boundaries

- Wi-Fi success and enrollment are independent. An unavailable Hub does not
  undo working Wi-Fi. Retries use bounded backoff and jitter.
- The Node saves its request token and proposed credential in `hub-enrollment.json`
  before sending a request. Core receives only the credential hash. Approval
  atomically creates the managed device and credential. A lost response can be
  recovered without issuing another credential or creating another device.
- `core-credential.json` keeps its legacy schema. `core-binding.json` separately
  binds that credential to the selected Hub and resolved API endpoint. Mismatched
  binding fails closed; changing Setup to another Hub does not transfer authority.
- For a root HTTP Hub URL on port 80/8080, runtime configuration may supply the
  backend port, but never another hostname. The resulting endpoint is retained.
- Requests expire after 24 hours; rejected, expired and revoked requests do not
  silently renew. Explicit administrator recovery/reassignment is still required.
  New requests are refused once 1000 Node enrollment records are present; there
  is no automatic receipt cleanup in this beta.
- Public enrollment grants no control. Listing, approval and rejection require
  an administrator. The UI receives no tokens or credential hashes/secrets.
- The loopback `/api/v1/agent/hub-connection` endpoint describes enrollment state;
  `credential_available` is not proof that the Hub is currently online.

## Trust and remaining work

This beta's HTTP mode is for an explicitly trusted local network, not an untrusted
LAN or Internet exposure. Endpoint binding is not cryptographic Hub identity
verification. HTTPS uses certificate validation, but authenticated discovery,
identity pinning, public-endpoint abuse controls and reassignment UX remain work.
Never approve an unknown request merely because its display name looks familiar.

No cloud enrollment or discovery is implemented here. A Node has one local Hub
command authority. Optional simultaneous cloud management will be an independent
Hub connection, not a second Node publisher, and will not be required locally.

## Migration and rollback

Core migration `3048f9a0b1c2` allows Node-originated requests without a creating
user and enforces a unique request per Node identity. Downgrading it deletes those
enrollment receipts only, preserving managed devices and credentials. Finish
pending onboarding before downgrade, or plan explicit recovery afterward.
Rollback to old Agent code preserves credential readability but does not add the
new Setup-driven enrollment functionality to that older release.

## Verification

Targeted tests cover administrator boundaries, legacy pairing, request replay,
rejection, expiry, revocation, wrong Hub, lost enrollment response, restart with
the same credential, and authenticated heartbeat through Core routes. Migration
upgrade/downgrade tests, frontend component tests, type checking and production
build are required. The component is reviewed in a local isolated preview;
that is not deployment or real-device acceptance.

Remaining hardware acceptance: approve the real Zero, confirm inventory/heartbeat,
restart it, disconnect/reconnect the Hub, and verify there are no duplicate devices
or credentials. Do not use physical output commands as an onboarding smoke test.
