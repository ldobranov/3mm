# CONERAX / 3mm — Platform-neutral Nodes and Capabilities

Approved direction: 2026-10-02. Base: `5cc0edf` / `v0.3.0-beta.32`, including
installation peer v2, Application SDK 1.3 and Node Update. This plan does not
rename existing packages, IDs or endpoints. CONERAX is the product direction;
the existing 3mm contracts remain compatible.

## Scope — shared Device/Node Platform, not Fleet-only

This milestone changes the common CONERAX Device/Node Platform used by
Standalone, Hub/Fleet, the local Agent and application extensions. Fleet is
only one consumer of this layer, not its owner or a prerequisite. Embedded
devices must also be manageable by a Standalone installation without Fleet
functionality. Deployment roles do not create separate capability registries
or hardware-specific protocol paths.

## Architectural boundary

Core knows devices, capabilities, providers and protocol contracts, not ESP32,
Raspberry-specific drivers, Modbus, Zigbee or concrete hardware implementations.
Reuse the existing registry, identity, enrollment, credentials, commands,
events, state and offline mechanisms. Do not build a second device subsystem.
Cloud is optional; local operation and a Node's selected Hub authority remain.
Installation peer enrollment is separate from device enrollment.

## Delivery and acceptance

| Stage | Deliverable | Status |
| --- | --- | --- |
| C0 | Existing Linux Agent regression baseline and coverage map | Baseline retained; role/schema matrix expanded locally |
| C1 | Versioned platform-neutral inventory, legacy ingestion and neutral UI | Implemented locally; separate Fleet adoption pending |
| C2 | One provider-neutral capability registry/query contract | Implemented locally; separate consumer adoption pending |
| C3 | Independent mock embedded protocol client and reconnect proof | Implemented locally; mixed Agent/mock and real HTTP tests pass |
| C4 | Mandatory node conformance versus optional runtime operations | Defined locally; shared event envelope and conformance tests implemented |
| C5 | Runtime feature advertisement, separate from application capabilities | Implemented locally; negotiation, support gating and additive migration |
| C6 | Document extension/firmware boundary; no hardware implementation in Core | Defined locally; dependency guard added |
| C7 | Authentication, identity, replay, expiry, bounds and audit validation | Hardened locally; focused security/regression checks |
| C8 | Non-destructive migration and mixed-version compatibility | Implemented locally; migrations, portable restore/rollback and legacy recovery verified |
| C9 | Linux + mock embedded acceptance through the same Core contracts | Local runtime/application acceptance verified; deployed Hub/Zero/Fleet gate pending |

C7 and C8 constraints apply from C1 onward, not only at the end. Each stage must
leave the current Linux Agent usable. Do not publish or deploy these changes
without a separate request and the relevant acceptance evidence.

## C0 — Current behavior, not a replacement subsystem

Before the inventory/registry refactor, freeze behavior for pairing, inventory,
heartbeat, capability registration/invocation/state, events, command results and
desired/reported state. Include identity/credentials after restart, offline
outbox replay, duplicate delivery, expired commands and revoked credentials.

The joined baseline uses actual Core HTTP routers, authentication, SQLite,
Agent publisher, module runtime and command journals. Only transport failure and
hardware are simulated. It does not prove electrical timing, real Linux file
permissions, process restart or production HTTPS. See [C0 evidence](PLATFORM_NEUTRAL_C0.md).
Keep rerunning this baseline after C1/C2 and during final acceptance.

## C1 — Inventory contract

Prefer keeping device transport protocol `1.0` and adding an explicit inventory
schema version. Do not change `/api/v1` or conflate it with peer protocol v2.
The executable contract is now inventory schema `2`; see [C1 implementation,
compatibility and evidence](PLATFORM_NEUTRAL_C1.md). Its shape is:

- identity: existing stable `device_id`, protocol version and collection time;
- platform: bounded family/system/model strings, not a hardcoded board enum;
- runtime: name/version, without a compulsory Python version;
- resources: optional memory, storage/flash and CPU measurements with bounds;
- network: optional generic status, not mandatory NetworkManager information;
- capabilities: advertisements, not an unauthenticated grant of authority;
- platform metadata: bounded optional metadata such as kernel/Python details.

Embedded inventory may omit hostname, OS version, kernel, Python, disk and
NetworkManager entirely. Linux adapters may still report them. Core validates
generic fields but must not branch on a concrete platform name.

Updated Core accepts the existing `AgentInventory` wire shape. Store/present a
normalized view without losing the original report or inventing Linux values.
New Linux inventory must be tested too. New Agent -> old Core (Standalone or
Hub) compatibility needs an explicit supported-schema advertisement or a
retained legacy publishing mode: do not blindly switch the sender and break
existing installations. C5 completes feature negotiation before general
rollout. UI shows available measurements
and unavailable values honestly; platform metadata is descriptive only.

## C2 — Capability providers

The shared registry, compatible module adapter, authenticated provider reports,
revision/disable/conflict semantics and additive migration are implemented
locally. See [C2 contract and evidence](PLATFORM_NEUTRAL_C2.md). This is the
common Core layer for Standalone, Hub/Fleet, local Agent and applications;
it does not require or modify the separately packaged Fleet extension.

One registration/query boundary supports:

`device + capability_id + provider_type + provider_id + provider_version + metadata + status`.

Agent modules are providers of type `agent_module`; firmware/native/gateway
providers need no `ModulePackage` or `ModuleInstallation`. Provider identifiers
are bounded and generic; do not enumerate hardware vendors in Core.
`registered_capabilities` and `has_registered_capability` use the same source
of truth for every consumer, including invocation, capability state, SDK,
Builder and Fleet. Keep the existing module ID/version view compatible for
legacy consumers; do not fabricate module identities for firmware providers.

Authenticated providers can advertise only their own device's registrations.
An advertisement cannot spoof an installed module, gain new human permissions,
override another provider or become physical execution authorization. Define
atomic replacement/removal, duplicate-provider conflict and disable/revoke
semantics before writing persistence. Existing enabled/succeeded module rules
remain enforced through the common registry or a compatible provider adapter.

If persistence changes, use Alembic and migration tests. Preserve identity,
credentials, installed packages, desired state and equivalent registrations;
test upgrading populated databases and restoring backups. No destructive
migration or re-pairing. A compatible module adapter is acceptable; multiple
independent registry/query mechanisms are not.

## C3 — Independent mock embedded client

The reference client does not import/use `AgentModuleRuntime` to obtain its
capabilities. It has stable identity and credential storage, advertises
`platform.family=embedded`, `platform.system=mock-embedded`, runtime
`conerax-embedded-test` and a firmware/native `gpio.digital.control` provider.

Through actual device HTTP contracts: enroll with approval -> inventory ->
heartbeat -> register capability -> invoke -> mock execution -> command result
-> capability state -> event -> disconnect -> reconnect. Verify durable identity,
credential and registration, buffered delivery and no duplicate/expired action.
There is no new embedded endpoint or Core branch for this reference client.

Implemented as `examples.mock_embedded`, independent of the Agent runtime and
Fleet. See [C3 run instructions, evidence and limitations](PLATFORM_NEUTRAL_C3.md).
Standalone/local Linux Agent and Hub-role Linux Agent each coexist with the
mock firmware provider on the common Core. A separate socket test runs the
default requests transport against Core on loopback. This is architectural
proof, not deployed Fleet/application acceptance or real firmware support.

## C4/C5 — Node conformance and advertised features

Mandatory node contract: stable identity, supported protocol version, approved
enrollment, per-device authentication, inventory, heartbeat, command/result,
event, registration and capability state boundaries. Document schemas, error
responses, time semantics, payload bounds, replay and persistence requirements.

The [C4 minimum Node contract](PLATFORM_NEUTRAL_C4.md) fixes these semantics,
wire schemas/statuses, optional-operation boundary and remaining legacy
enforcement gaps. The generic event envelope is shared without changing the
existing API. C4 adds no feature announcement or protocol/SDK bump.

Module installation, Python, filesystem packages, NetworkManager and Linux
update helpers are optional runtime features, not node prerequisites.
`features` describes protocol/runtime support (e.g. module lifecycle or signed
updates); `capabilities` describes application behavior (e.g. GPIO or identifier
scan). Neither implies the other. Missing legacy advertisements require a safe,
documented compatibility policy, not fabricated support. Unsupported commands
are rejected before queueing/dispatch where possible and on the node boundary.
Use generic advertised contracts for versioned/signed update metadata, without
assuming that firmware uses the Linux installer.

The [C5 implementation and compatibility policy](PLATFORM_NEUTRAL_C5.md) adds
device-authenticated protocol discovery and revisioned runtime advertisements,
shared queue/permit checks, Linux Agent negotiation and independent mock
adoption. Legacy nodes retain unknown support and their existing behavior;
explicit declarations govern new work. No SDK or transport version bump.

## C6 — Work outside Core

The [C6 ownership and integration boundary](PLATFORM_NEUTRAL_C6.md) specifies
Core/shared protocol, Linux runtime, future extension/firmware and consumer
responsibilities, with a dependency guard and no hardware implementation.

A separate Embedded Nodes extension may own provisioning UI, board profiles,
pin mapping, firmware catalogs/releases, OTA management and recovery/diagnostics.
A separate firmware runtime owns Wi-Fi, credential storage, protocol client,
dispatcher, hardware drivers, provisioning, OTA and recovery.

Not started here: ESP-IDF/Arduino, actual ESP firmware/provisioning/GPIO/OTA,
board variants, RFID, I2C, PWM, ADC, BLE or Modbus implementation. Examples in
this plan are not supported hardware claims or a repository creation request.

## C7/C8/C9 — Security, compatibility and final proof

The [C7 hardening and evidence](PLATFORM_NEUTRAL_C7.md) closes common JSON/body,
receipt binding, cached revocation and Core-audit spoofing gaps while preserving
physical/OTA uncertainty. Live Linux storage and final
consumer/runtime acceptance remain explicitly separate gates.

The [C8 compatibility and recovery matrix](PLATFORM_NEUTRAL_C8.md) now verifies
additive migrations, old/new wire adapters, encrypted portable restore and
failed-health rollback. Historical oversized state/commands/receipts remain
preserved with explicit recovery conflicts, not destructive migration or replay.
The [C9 local acceptance](PLATFORM_NEUTRAL_C9.md) now proves the signed
application path for both runtime implementations. Live deployment and separate
Fleet consumer adoption remain pending; local role tests are not deployment proof.

- Unique device credentials, revocation and identity binding; no fleet-wide key.
- Existing actor/application permissions, selected Hub authority and audit remain.
- Durable idempotency, command expiry and rejection of uncertain physical replay.
- Bounded messages, registrations, metadata, buffers and event retention.
- Credential storage and redaction are platform responsibilities under the same
  security contract; embedded support does not waive them.
- Mixed legacy/new nodes retain identity, credentials, modules, registrations
  and desired state across Core update, failure, rollback and backup restore.

Final acceptance requires Linux Agent + independent mock embedded simultaneously
using the same device registry/authentication, command/event transport,
capability registry and state model, in each of these scenarios:

- Standalone + local Agent + embedded node, without a Fleet extension;
- Hub/Fleet + multiple Linux/embedded nodes;
- application extension + capability from a Linux OR embedded node.

An application extension requests the same capability contract (for example
`gpio.digital.control`) without knowing whether it is provided by a Linux
Agent module, embedded firmware or another provider. No application-specific
hardware branching or Fleet dependency is required for invocation/state.

Only after C9 starts a separate CONERAX Embedded Runtime / ESP32 MVP milestone.
New hardware is not a reason to edit Core. A proven missing generic contract
must be specified first, and be useful beyond a concrete board or extension.
