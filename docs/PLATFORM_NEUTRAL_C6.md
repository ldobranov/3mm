# C6 — Core / extension / firmware boundary

Defined locally 2026-10-03 on C0–C5. This is the shared Device/Node Platform,
not a Fleet feature. Standalone, local Agent, Hub/Fleet and application
extensions use the same registry, credentials, providers and transports.
Transport stays `1.0`, HTTP `/api/v1`, Application SDK `1.3`.

## Ownership

| Owner | Responsibilities | Must not own |
| --- | --- | --- |
| Core + shared protocol | Device identity/trust, enrollment approval/revocation, inventory schemas, provider registry, runtime features, command/result/event/state contracts, permissions, execution permits and audit | Board names/profiles, pin numbering, concrete drivers, Wi-Fi implementation, firmware build tooling |
| Existing Linux Agent/runtime | Linux implementation of these contracts, module lifecycle, local hardware adapters, Linux update helper and provisioning | A second Core registry or special permissions for Linux providers |
| Future Embedded Nodes extension | Provisioning/configuration UI, board profiles/pin mapping, firmware catalog/releases, optional OTA management, diagnostics/recovery UI | Device credentials as a fleet-wide secret, bypasses of Core permissions or a parallel capability registry |
| Future embedded firmware | Persistent identity/credential/authority, protocol client, bounded outbox/receipts, capability dispatcher, drivers, Wi-Fi/provisioning, OTA/recovery | Core database access, Linux module/package emulation or authority inferred from a hostname |
| Application extension | Request a capability/action on a bound managed device, with its existing application/actor permissions | Branch on board/platform/provider implementation or require Fleet for local devices |
| Fleet/cloud consumers | Discovery/management of multiple devices/installations through existing generic contracts | Ownership of the common device layer, mandatory cloud access or silent replacement of local authority |

Examples of board/driver names in descriptive inventory metadata are not Core
domain rules. `agent_module`, `native` and `embedded_firmware` describe provider
contracts, not grants of human permissions or proof of physical execution.

## One integration path

An independent runtime uses approved device enrollment, per-device
authentication, protocol negotiation and inventory schema 2; advertises its
runtime features and provider registrations; consumes the existing command
queue and publishes results, events and capability state. It needs neither a
module ZIP nor an inbound Node web server. Linux retains its module adapter.

Every consumer resolves `device + capability_id` through the same registry.
An application requesting `gpio.digital.control` must not need to determine
whether a Linux module, firmware or another provider implements it. Provider
conflicts and Core-owned disable remain authoritative.

Runtime feature != application capability != execution authorization.
Firmware advertising `ota` does not support Linux `agent.update.apply` by
implication. Firmware can use bounded, versioned/signed update metadata in a
future generic workflow; its installer, signing policy and recovery are outside
Core. No firmware OTA implementation/catalog endpoint is introduced here.

Signed application execution remains a distinct optional contract. A runtime
without `application_execution_permits` must not execute
`application.capability.invoke` as unsigned `capability.invoke`. The C3 reference
initially lacked this feature. [C9](PLATFORM_NEUTRAL_C9.md) now implements and
advertises it independently, with a durable attempt before the existing one-time
Core permit. The signed application path is locally verified for both providers;
this does not replace the deployed consumer acceptance gate.

## Rule for future work

Adding a board, ESP variant, Modbus/Zigbee adapter or hardware driver is not a
Core task. Put it in the extension/runtime owning that implementation. If an
existing generic contract really cannot represent the requirement, document
the failing protocol scenario first and propose a platform-neutral contract
useful beyond that hardware. Do not add an endpoint or platform conditional
for each board or application.

No ESP-IDF/Arduino, real firmware, GPIO implementation, board profiles, RFID,
I2C, PWM, ADC, BLE, Modbus or new repository was started. This stage does not
remove existing Linux implementation adapters from the project.

## Guard and evidence

`backend/tests/test_node_security.py` includes an AST dependency guard on the
neutral inventory/provider/features/security contracts, common registry/feature
services and independent reference client. They cannot import Agent runtime,
provisioning/runtime helpers, GPIO libraries or Fleet. Descriptive platform
strings and the compatible Core module-provider adapter remain allowed.

This scoped dependency guard is not a full repository architecture proof.
The C0/C3 role matrix supplies the separate common-Core runtime proof; C8/C9
remain migration, recovery, deployed consumers and final acceptance gates.
See [C7 focused security evidence](PLATFORM_NEUTRAL_C7.md).
