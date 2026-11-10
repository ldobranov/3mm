# 3mm 0.3.11

This release prepares the generic GPIO-input and local character-display clock
contracts together with application activation, authority and runtime hardening.
Applications and independently updated components keep their own versions.

- Reviewed GPIO input profiles publish ordered source-timed edges. Applications
  interpret the input; Core does not contain Crypto Monitor button rules.
- Character-display scenes support finite, renewable local clock execution in
  Agent. Seconds tick locally without per-second Core or market requests.
- Event admission and response handoff have explicit finite budgets. Immutable
  code verification can be reused within one event RPC while current rights,
  revocation and exact code identity remain separately checked.
- Optional Agent telemetry no longer serializes input edges or blocks the next
  physical command behind full capability-state reports.
- Application hosts contain disconnected reply failures without replaying a
  handler. Component activation, cold-start budgets, durable receipts and signed
  schema-metadata handling include additional recovery and denial coverage.
- Native component and connector-worker source inventories remain explicit;
  immutable selection, health checks and rollback remain required.
- Absent optional image providers report unavailable without starting a codec
  probe child. Present or inconclusive providers retain bounded child checks.
- Typed review-key contention retains its distinct busy diagnostic category;
  denial behavior, public responses and access checks remain unchanged.
- Unreadable optional AP status remains visible as unavailable without breaking
  administration. Source exports omit legacy mutable data and editor settings;
  no local database, upload or network configuration is deleted.

Crypto Monitor **0.8.3** is a separate application package, not a Core dependency.
The owner accepts its display, local seconds and physical-button functionality.
Measured button-to-screen latency of **18–27 seconds** remains a known deferred
issue; this release does not claim immediate input response or remove authority
checks to achieve it. Existing uncertain command/event evidence is retained.
Local-clock output requires the separately reviewed scene-capable provider; a
static-frame provider does not gain that capability from an application upgrade.

Keep a tested backup before upgrading. ARMv6 Hub and Node use distinct artifacts
and catalogs. Bulgarian pack 1.0.6, Device Protocol 1.0 and Application SDK 1.3
retain their independent versions. Local software checks and the existing Pi3
acceptance do not replace clean-card or separate-user hardware acceptance of the
published release.
