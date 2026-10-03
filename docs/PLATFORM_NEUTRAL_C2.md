# C2 — Shared provider-neutral capability registry

Implemented locally 2026-10-03 on the C0/C1 baseline. Device protocol remains
`1.0`, Application SDK remains `1.3`; installation peer v2 and Node Update
are not replaced. No deployment, release, commit or push in this stage.

## Scope: not Fleet-only

This is the common Core Device/Node Platform for Standalone, Hub/Fleet, the
local Agent and application extensions. Fleet is a consumer, not a requirement
for enrollment, capability registration, invocation or state. A Standalone
Core can manage a local Agent and another embedded node through these APIs.
No Fleet package or concrete hardware implementation is imported by the registry.

All effective registrations have the same shape:

`device + capability_id + provider_type + provider_id + provider_version + metadata + status`.

`registered_capabilities` and `has_registered_capability` are the common query
boundary. Invocation, state reporting/reading, application command bindings,
public widget reads, passage checks, Node Update checks and Builder planning
use that boundary. Builder's separate module-installation scan was removed.

## One registry, compatible storage adapters

- Existing Agent modules: a live adapter reads only enabled, successful
  installations and their package registrations. Provider type is
  `agent_module`, with the actual package ID/version. No duplicated cache or
  backfill can drift from module lifecycle state.
- Other providers: `device_capability_providers` stores device-owned versioned
  declarations and Core-owned `enabled`. No fake module installation/package
  is created. Provider types/IDs are bounded generic strings, not a hardware
  enum. `native`, `embedded_firmware` and `gateway` are examples, not separate
  Core subsystems.

Active duplicate capability IDs on one device fail closed: that ID is absent
from the effective registry until ambiguity is removed. The same capability
on different devices is valid. New declarations cannot take an ID owned by
another reported provider or an active module. Disabled reported providers
retain their declarations/ownership until withdrawal. A later conflicting
module activation also fails closed; Core does not silently pick a provider.

## Device declaration contract

Use the existing unique revocable device credential:
`Authorization: Device <credential_id>:<secret>`.

`PUT /api/v1/devices/{device_id}/capability-providers/{provider_type}/{provider_id}`
accepts `CapabilityProviderReportV1`, for example:

```json
{
  "schema_version": 1,
  "protocol_version": "1.0",
  "device_id": "dev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "provider_type": "embedded_firmware",
  "provider_id": "example.runtime",
  "provider_version": "0.1.0",
  "expected_revision": 0,
  "capabilities": [{
    "capability_id": "gpio.digital.control",
    "metadata": {"automation_channels": "output.1"}
  }]
}
```

The path/body identities must match the authenticated device/provider.
`agent_module` is reserved for the installation adapter and cannot be claimed
through this report. Inventory/hello advertisements alone do not register
effective capabilities or grant application/user rights.

A report replaces only this provider's complete declaration list, atomically
under the device write lock. Initial expected revision is `0`; a successful
change increments it. Read the current snapshot/revision using device-authenticated
`GET` at the same URL. Current identical reports and exact one-revision-old
retries return the existing acknowledgement without duplicate writes/audits.
Other stale revisions/conflicts return `409`, identity mismatches `403`, invalid
contracts `422`, invalid/revoked credentials `401`.

An empty list withdraws capabilities but retains the provider revision. Old
reports cannot resurrect them. Replacement/version change clears affected
latest capability state; fresh measurements must be reported through the
existing capability state endpoint. A reconnect retains registration/identity,
not an invented fresh measurement.

Limits: 16 reported providers/device, 64 declarations/provider, 256 total
reported declarations/device, 64 KiB validated report. Metadata is flat JSON
scalars: at most 32 keys, 96-character keys, 512-character string values,
8192 serialized UTF-8 bytes; floats must be finite. IDs/types/versions and
integer revisions are bounded. These are validation limits, not a substitute
for HTTP ingress limits or broader C7 conformance/security checks.
Metadata must not contain credentials or secrets.

## Administration and read compatibility

Administrators can inspect all reported providers, including disabled/withdrawn
ones and current revisions:

`GET /api/v1/devices/{device_id}/capability-providers`.

`POST /api/v1/devices/{device_id}/capability-providers/{provider_type}/{provider_id}/enabled`
accepts `{"expected_revision": 1, "enabled": false}`. This control increments
revision, clears latest state and writes an administrator audit. Device reports
cannot set or overwrite `enabled`, even when they change provider version.
Module enable/disable continues through the existing module lifecycle APIs.

Provider disable blocks new effective capability lookups/invocations/state
reports, and the existing application command broker rechecks availability
before issuing an execution permit. It does not undo dispatched/authorized
actions or claim cancellation of already-delivered commands. Legacy administrator
commands already queued use the existing transport/expiry semantics; this stage
does not redesign that transport or add automatic physical replay. Revoking
the device credential/device remains the whole-device trust control.

Device semantic declaration changes are recorded as secret-free
`capability.provider.updated` device audit events. Neither declarations nor
administrative diagnostics expand user/application permissions.

- Existing `GET /{device_id}/capabilities` keeps the module-only legacy
  serialization: `capability_id/module_id/version/metadata`.
- Add `?registry_version=2` for all effective providers with
  `capability_id/provider_type/provider_id/provider_version/metadata/status`.
- Both views serialize the same registry; firmware is never mislabeled as a module.
- Module-only Builder/automation contexts keep their exact schema-1 response.
  A context containing non-module providers uses `context_version: 2` and
  provider-neutral entries for all devices. The built-in Builder accepts these
  entries and uses device/capability/channel metadata, not module identity.
- Application extensions retain identical signed declarations, configuration,
  request IDs, argument checks, TTLs and one-time execution permits. An extension
  need not know whether the capability comes from a module, firmware or adapter.

Separately packaged Fleet/other consumers must explicitly adopt the neutral
read/context formats to show non-module providers. They are not modified here;
existing Linux nodes/legacy displays remain compatible. C5 will specify runtime
feature advertisement/negotiation before general embedded rollout.

## Migration and evidence

Alembic revision `637bc2d3e4f5` adds only the provider table/index. The legacy
baseline's post-baseline exclusion list includes it so clean databases create
it at the correct revision. No existing device/module/credential/desired-state
rows are rewritten. The module adapter provides equivalent existing registrations.

Local Windows/Python 3.13 evidence:

- Broad C0/C1/C2 + protocol, application-command/public-widget and AI-context
  regression gate: **187 passed in 45.31s**, existing dependency warnings.
- Final affected-file gate after administrator diagnostics: **45 passed in
  16.77s**; includes the joined Linux Agent scenarios and migration tests.
- Core HTTP-only tests, without Fleet or Agent module runtime, exercise native
  registration -> invoke -> existing command/result -> capability state for
  Standalone/Hub/Node device roles. A local module and another node's native
  capability coexist under the same capability ID in one Core context.
- The same signed application binding works with Agent module, native and
  firmware providers; argument limits, one-time permit and provider disable
  remain enforced without changing the application manifest/request.
- Identity/credential scope, revocation, module spoofing, stale revisions,
  idempotent retry, atomic conflict/withdrawal, quotas and state invalidation
  have focused tests.
- Migration tests cover clean-history traversal to the previous head, populated
  upgrade, Alembic model comparison, additive downgrade and SQLite backup-copy
  preservation of module/native declarations, credentials and desired state.
- Frontend Builder/inventory component tests: **11 passed**. Vite build and
  TypeScript check pass; no visual redesign in this stage.

This does not prove a deployed Standalone/Hub topology, physical timing,
PostgreSQL concurrency, encrypted recovery UI or a separate embedded client.
C3 supplies the independent client; C7/C8/C9 retain their full security,
restore/rollback and Standalone/Hub/application acceptance matrix. No ESP
firmware, driver, Fleet UI release or hardware-specific Core endpoint was added.
