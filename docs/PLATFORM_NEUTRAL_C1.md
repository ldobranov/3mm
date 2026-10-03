# C1 — Platform-neutral inventory

Implemented locally 2026-10-02/03, based on `5cc0edf` / `0.3.0-beta.32`.
Device protocol remains `1.0`, Application SDK remains `1.3`, installation
peer v2 and Node Update remain supported. No release or deployment in C1.

Scope: the shared Core Device/Node Platform for Standalone, Hub/Fleet, local
Agent and application extensions. Inventory schemas and authentication do not
depend on a Fleet extension or a deployment role. Fleet is one UI consumer.

## Versioned wire contract

`three_mm_protocol.DeviceInventoryV2` describes inventory **schema 2**, not
device protocol v2 or installation peer v2. The authenticated endpoint remains
`POST /api/v1/devices/{device_id}/inventory`; successful submission returns
the existing `202 {"status":"accepted"}` response.

The same endpoint still accepts the unchanged flat `AgentInventory` contract
(legacy schema 1, no `schema_version` tag). New reports require the integer
`schema_version: 2`; missing/unknown versions, invalid identity, extra fields
and invalid measurements are rejected. Existing device authentication,
credential revocation and path/payload identity binding apply to both formats.

Minimal example, deliberately without Linux fields:

```json
{
  "schema_version": 2,
  "protocol_version": "1.0",
  "device_id": "dev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "collected_at": "2026-10-03T00:00:00Z",
  "platform": {"family": "embedded", "system": "mock-embedded", "model": "Test board"},
  "runtime": {"name": "conerax-embedded-test", "version": "0.1.0"},
  "resources": {"memory_total_bytes": 409600, "flash_total_bytes": 4194304},
  "capabilities": ["gpio.digital.control"]
}
```

Platform family/system and runtime name are bounded strings, not hardware
enums. Model, platform version/architecture and runtime version are optional.
Resources optionally describe logical CPUs, memory, storage and flash.
Optional network fields are hostname and connected status. Kernel, Python,
distribution and NetworkManager details belong in `platform_metadata`.
Core has no concrete-board conditional logic.

Bounds: positive integer totals/CPU count, nonnegative free bytes, signed
64-bit maximum; free cannot exceed a supplied total. Collection time needs a
timezone. At most 128 unique capability advertisements, 160 characters each.
Metadata permits JSON values with depth <= 4, <= 32 entries per object/array,
96-character keys, 512-character string values and 8192 serialized UTF-8 bytes.
The validated complete schema-2 report is limited to 64 KiB. These are report
validation limits, not a replacement for HTTP ingress limits in C7.
Metadata must never contain credentials, passwords or tokens.

Inventory capabilities are descriptive advertisements only: C1 does not grant
invocation authority or register firmware providers. That is C2's boundary.

## Compatibility and storage

| Sender | Legacy Core | C1 Core |
| --- | --- | --- |
| Existing Agent / schema 1 | Unchanged | Accepted unchanged |
| Updated Agent / default schema 1 | Unchanged | Accepted unchanged |
| Explicit schema 2 / other runtime | Not supported | Accepted |

Keep updated Agents in legacy publishing mode until their Core and UI consumers
support schema 2. Set `THREE_MM_INVENTORY_SCHEMA_VERSION=2` or start the Agent
with `--inventory-schema-version 2` only against an updated Core (Standalone or
Hub). Default is `1`; invalid configuration fails explicitly. There is no automatic downgrade or
schema negotiation in C1; C5 will establish negotiation before general rollout.

Agent conversion keeps the same identity, collected measurements and hardware
advertisements. It reports the actual host platform and Agent runtime version,
with Linux-specific descriptive values in metadata. Internal module/GPIO boot
inventory remains compatible. Local diagnostics support:

- `GET /api/v1/agent/inventory`: unchanged legacy response;
- `GET /api/v1/agent/inventory?schema_version=2`: neutral response.

Database snapshots preserve the submitted report format. No Alembic migration
or rewrite is needed: the existing JSON snapshot model stores either contract.
No identity, credential, installation, registration or desired state is reset.

Administrator list/detail APIs retain their existing response envelope:

- `GET /api/v1/devices` and `/{device_id}` return the original latest report;
- add `?inventory_schema_version=2` to request a normalized neutral read view.

The read view is not a new device report. Historic partial snapshots may have
null identity/time/measurements; legacy platform family is honestly `legacy`
and unknown Agent version stays null. Original data is never rewritten.
No Linux field is fabricated for an embedded report; flash is not mapped to
Linux root storage. Module compatibility and consent-limited installation
status projections use the same generic field accessor for both versions.
Projection scopes are not expanded; firmware version is not Agent version.

## UI / separate Fleet adoption

The reusable `DeviceInventorySummary.vue` and `device-inventory.ts` present
available platform/runtime/resources fields in either format, preserve zero
measurements and omit unsupported measurements. The bundled reference device
screen uses the normalized API view and supplies EN/BG labels. Presentation
uses existing theme tokens and a wrapping grid, not a new UI framework.

The separately packaged `3mm-fleet` extension and the installed `/fleet` UI
are **not updated or redeployed by this Core task**. This is a consumer adoption
requirement, not a requirement to install Fleet. Before switching a physical
Agent/Node to schema 2, update whichever UI is used to these generic field paths
or adopt the normalized read API/helper. It must not directly assume flat
`hostname`, `architecture`, RAM or root filesystem fields. Old Agents remain
fully compatible with existing Fleet while publishing schema 1.

## Evidence

- Focused C0/C1 + Agent API/config/CLI + installation-peer regression gate:
  **168 passed** on Windows/Python 3.13 in 58.08s. Existing dependency warnings.
- Joined Linux Agent/Core scenarios run both inventory formats with both
  deterministic hardware profiles, including reconnect, module commands,
  capability/state/event paths and revoked credentials.
- The 2026-10-03 test extension covers Standalone/Hub/Node device roles in joined
  Linux scenarios and authenticated legacy/Linux/embedded inventory ingestion.
  Historic totals above remain unchanged; current matrix evidence is recorded
  in [C3 evidence](PLATFORM_NEUTRAL_C3.md). Local Agent inventory diagnostics
  remain separately tested.
- Authenticated ingestion accepts minimal embedded inventory without a module
  package; its advertisement does not bypass capability registration.
- Four focused frontend component tests pass: legacy/Linux/embedded display,
  zeros, unsupported/missing inventory, inert metadata and EN/BG labels.
- `npm --prefix frontend run build-only` and `run type-check` pass.

This is local contract/test evidence, not live Raspberry, systemd, a complete
independent embedded client (C3), active Fleet integration or browser visual
acceptance. No ESP firmware or hardware-specific endpoint was introduced.
