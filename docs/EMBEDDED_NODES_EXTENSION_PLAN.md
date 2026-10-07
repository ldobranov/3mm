# 3mm Embedded v0.1 — future extension and firmware

Recorded: 2026-10-04, by owner request near the end of the product milestones.
Roadmap reference: Milestone 18. Design context: chat “Разширяване към ESP чипове”.
Status: deferred; no ESP hardware is available. No firmware/driver is started now.

## Dependency, not a new Core project

Use [Core Device Platform C0–C14](PLATFORM_NEUTRAL_NODES_PLAN.md) as the shared
boundary for Standalone, Hub/Fleet, local Agent and application extensions.
Its implementation exists locally; finish outstanding consumer/live acceptance
before calling a firmware implementation fully accepted. Preserve Linux and
mock-embedded regression flows. No new registry, credentials or command queue.

Core knows devices, providers, capability contracts and runtime features. It
does not know ESP board names, pin assignments or firmware implementation.
Adding a chip is not a reason for changing Core. A genuinely universal missing
contract is documented with evidence as a separate Core issue before any patch.

## Components

**Firmware:** independent runtime with identity/credential persistence, logical
protocol client and transport adapter, lifecycle, capabilities, hardware drivers,
Wi-Fi/provisioning, bounded offline buffer, update and recovery.

**Embedded Nodes extension:** optional application package for board profiles,
pin/capability configuration, firmware catalog/release selection, diagnostics,
provisioning helpers and OTA/recovery UI. It consumes generic Core APIs; it does
not own device identity, enrollment authority or command transport. It works on
Standalone without requiring Fleet or cloud.

**Existing Core:** authenticates the device, owns management authority, performs
explicit enrollment/reassignment, validates capabilities and dispatches generic
commands/results/events/state. Hardware-specific configuration stays outside it.

## Future stages

| Stage | Runnable result |
| --- | --- |
| E0 | Freeze/pin accepted generic protocol, SDK and capability contracts |
| E1 | Select one available reference board; ESP32-C3 is a candidate, not a purchase or support promise |
| E2 | Independent firmware skeleton and bounded persistence |
| E3 | Stable identity, unique credential and authority binding survive reboot/power loss |
| E4 | Phone Wi-Fi provisioning/recovery, separate from enrollment |
| E5 | Explicit enrollment into real Standalone or Hub using existing device contract |
| E6 | Real inventory/heartbeat, online/offline and reconnect |
| E7 | One supported -> explicitly configured/registered -> available digital I/O capability |
| E8 | Physical command/result flow with safe state, expiry and idempotency |
| E9 | Input event/state flow with bounded offline replay |
| E10 | Optional Embedded Nodes extension for configuration/diagnostics |
| E11 | Signed/versioned firmware OTA, health validation and rollback outside Core |

Do not start multiple chips, RFID, I2C, PWM, ADC, BLE, Modbus or a firmware matrix
before the first board and capability work. A GPIO demonstration is not proof of
turnstile safety or real-time latency; those require separate physical acceptance.

## Acceptance

- Standalone + local Linux Agent + embedded node operate together without Fleet.
- Hub/Fleet + multiple Linux/embedded devices use the same trust and transport contracts.
- An application consumes a capability from an Agent module OR firmware without
  hardware/provider-specific branches.
- Identity and authority survive reconnect/reboot; changing a Hub address alone
  cannot transfer trust.
- No fleet-wide secret; credentials are unique, revocable and bound to identity.
- Expired/replayed/malformed commands fail closed, payloads/storage are bounded,
  and ambiguous physical execution is never blindly replayed.
- Firmware upgrade/recovery and offline behavior are physically exercised before
  declaring support; existing Linux behavior remains compatible.

This backlog does not block current theme, CME, Fleet, website or entitlement work.
