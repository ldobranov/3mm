# C14 — Capability discovery, configuration and availability

Implemented locally on 2026-10-03. Common Device/Node Platform for Standalone,
Hub/Fleet, local Agent and application extensions, not a Fleet subsystem.
Device protocol stays **1.0**, `/api/v1` stays unchanged, Application SDK stays
**1.3**. No ESP firmware, hardware driver or electrical acceptance is added.

## One registry, three different questions

| Level | Meaning | Authority |
| --- | --- | --- |
| Supported | Runtime/provider offers this capability, or inventory describes it | Discovery only |
| Registered | Existing Core-approved module installation, or explicit provider selection | Application binding and queue validation |
| Available | Registration, authority, connectivity and fresh provider health allow execution now | New dispatch and physical execution permit |

`registered_capabilities` / `has_registered_capability` remain the shared
configuration boundary. They do not delete registration on temporary outages.
`capability_catalog` and `can_dispatch_capability` compose the current health
view with that same registry, not a second source of registrations. A measured
`false` GPIO value is valid state, not evidence that its provider is unhealthy.

Inventory-only advertisements are returned as supported, unregistered and
unavailable (`inventory_only`). They cannot authorize binding, raw commands,
provider health or physical execution. Core does not branch on platform names.

## Wire contracts and approval

The administrator query remains:

`GET /api/v1/devices/{device_id}/capabilities?registry_version=3`

It includes provider identity/version, optional C11 contract, `supported`,
`registered`, `available`, `unavailable_reason` and provider declaration digest.
Registry query versions 1 and 2 retain their previous serialization and only
return registrations. No new fields are added to the strict protocol-discovery
envelope: its existing supported-version lists advertise registry 3 and provider
reports 1/2.

`CapabilityProviderReportV2` uses the existing device-authenticated provider PUT.
Its declarations are **offers**, not automatic registrations. New providers
start with `configured_capability_ids=[]`. Selection is Core-owned:

`POST /api/v1/devices/{device_id}/capability-providers/{type}/{id}/configuration`

```json
{"expected_revision": 1, "capability_ids": ["gpio.digital.control"]}
```

Only a Core administrator may select current provider offers. Revision conflicts
return 409; configuration changes are audited. Device credentials cannot change
selection, enabled state or module installation state. Conflicting provider IDs
for the same capability fail closed under the existing C2 ownership rule.
Withdrawal and reconnect retain the selection. New capability IDs from an
updated firmware remain supported only until approved. C11 still checks exact
contract version and digest; provider version is not the capability contract.

Linux module selection continues through existing approved module install/enable
operations. A new module version must go through that existing control path;
device inventory cannot fabricate a ModuleInstallation.

## Fresh, device-bound health

`CapabilityAvailabilityReportV1` is accepted through the common logical
`DeviceOperations.availability` service and its reference HTTP adapter:

`POST /api/v1/devices/{device_id}/capability-availability`

The report binds device ID, provider type/ID/version and SHA-256 of its complete
current declaration (capability IDs, metadata and C11 contracts). It carries
observed time, a **5–300 second** lifetime (default 90) and at most 64 strict
boolean health entries. Shared Node body/JSON bounds apply. Wrong identity,
unknown provider, changed declaration, stale/conflicting evidence or excessive
clock skew is refused. Exact retries do not renew the original expiry.

Health is ephemeral: neither Agent nor reference mock places it in the durable
offline outbox. Reconnect publishes a newly observed report. Expired health,
offline connectivity, inactive authority, provider conflict or changed provider
declaration make a registration unavailable with a reason, not unconfigured.
Node-reported health is runtime evidence, **not mechanical outcome proof** or
permission to bypass application access controls.

New Linux Agent negotiates `capability_availability.v1` only when Core advertises
registry 3. Reports probe the active module service and, where present, validate
the declared capability state. Service activation/probe failures report unhealthy.
The local dispatcher also refuses unavailable work before driver invocation.

## Dispatch, expiry and uncertainty

For health-aware providers, new capability commands remain queued while
unavailable, without delivery attempts. Eligible unrelated commands can advance.
The same queued command becomes eligible after fresh health/reconnect, only if
its original expiry and contract still permit it. Command expiry is not extended.
Application execution permits recheck availability before the one-time claim.

Already dispatched work retains delivery/receipt evidence and existing journal
semantics. Health loss never labels a dispatched action `not_dispatched`, clears
a claim or authorizes automatic replay of an uncertain physical effect.

## Compatibility and migration

- Old provider report v1 retains its historical implicit selection until opt-in.
  This is compatibility, not a claim of explicit administrator approval.
- Transition to explicit mode preserves old selected IDs and disabled state.
  A v2 report or the C14 runtime feature activates this mode; existing explicit
  provider rows keep it sticky even if a device changes format/features/provider ID.
- Legacy health is honestly `available=null` / `legacy_health_unknown` while
  online. Old runtimes retain existing dispatch behavior; they are not silently
  required to implement a new health endpoint. A provider's accepted health
  evidence makes subsequent dispatch health-gated even if the runtime feature
  is later absent.
- New Agent filters the feature against older Core support before advertising;
  old inventory/module/command behavior remains compatible. Explicit C14 mock
  mode requires an upgraded Core.
- Alembic `96aef5a6b7c8` follows `859de4f5a6b7`, adds nullable Core-owned provider
  selection and the current health table. It does not reset identity, credentials,
  modules, desired state or existing registrations.
- Legacy-only downgrade is tested. Downgrade refuses when any explicit selection
  exists: dropping that column would turn unapproved offers into legacy automatic
  registrations. Rollback then requires the pre-upgrade database backup; do not
  force-drop the column or disable this guard.

## Evidence and remaining gates

`backend/tests/test_capability_availability.py` covers both Standalone and Hub:

- actual Linux module runtime and independent firmware mock use the same SDK
  application command binding and registry;
- discovery without selection, administrator/CAS checks, inventory spoofing and
  firmware additions; old report/new provider cannot bypass explicit mode;
- outage, expired/unhealthy health, deferred dispatch, reconnect and stable identity;
- denied execution permit preserves dispatched evidence; fresh health permits it;
- device authentication, declaration/timestamp/TTL/retry checks and direct
  non-HTTP invocation of the same service;
- populated migration preservation, clean Alembic metadata check and downgrade guard.

Existing C11/provider, transport, Linux publisher/runtime and migration tests are
also run as focused regressions: the final C14/C11/provider/security/negotiation
run passed **61 tests**; a separate transport/runtime/migration run passed
**52 tests** (the suites overlap, so these are not added as a unique count).
This is local contract/runtime evidence, not a live Hub/Zero/Fleet or real
hardware test.

Release preparation also passed a **68-test integrated gate** covering common
transport, C11/C14, C12/C13 authority/lifecycle/migrations and VM/Node installer
bootstrap. These checks do not close the separate live deployment gate.

Run the independent mock with its existing enrollment options plus
`--explicit-capabilities` (optionally `--versioned-contracts`). After Core device
approval, its offered capability is visible in registry 3 but remains unselected.
Use the administrator configuration API with the current provider revision, then
its next health report permits new commands. The default mock retains legacy mode.

No frontend redesign, separate Fleet consumer update, deploy, release or reset
was performed. Consumers still need to adopt the new status view/configuration UI;
live mixed-version acceptance is the remaining extended C10–C14 gate.
