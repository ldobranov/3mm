# Application commands and correlated passage

Implemented in 0.3.0-beta.15, in order: durable Agent attempts (B), scoped
application command broker (A), correlated sensor evidence (C). These are generic
Core/Agent contracts, not a concrete access-control application or hardware adapter.

## Declaring authority

An application definition may add `command_bindings`. The package manifest must
declare `capabilities.invoke`, list each binding capability in
`capabilities.consumes`, and declare each device configuration key as a string.
The existing installer offers the managed-device selectors. Example binding:

```json
{
  "binding_id": "entry_output",
  "target_device_config_key": "OUTPUT_DEVICE_ID",
  "capability_id": "gpio.digital.output",
  "action": "pulse_output",
  "max_ttl_seconds": 10,
  "arguments_schema": {
    "type": "object",
    "properties": {
      "channel": {"type": "string", "maxLength": 32, "enum": ["gpio.output.1"]},
      "duration_ms": {"type": "integer", "minimum": 50, "maximum": 500}
    },
    "required": ["channel", "duration_ms"],
    "additionalProperties": false
  },
  "sensor_device_config_key": "SENSOR_DEVICE_ID",
  "sensor_id": "entry.sensor.1"
}
```

Sensor fields are optional but must occur together. They are necessary to accept
passage evidence. The target must be approved, non-revoked and have the registered
capability. Driver checks, output safe-state configuration and cooldown still apply.
Argument schemas allow only bounded scalar properties; nested objects, arbitrary
JSON Schema keywords and extra arguments are not accepted.

## Requirement discovery (first Core/SDK vertical, 2026-10-25)

`GET /api/v1/application-extensions/packages/{sha256}/command-bindings/{binding_id}/discovery`
is an authenticated administrator-only projection of the existing capability
registry. It checks the package's declared command against approved devices;
it does not create another provider registry. Pages contain at most 32 devices;
pass the returned `next_after_device_id` as `after_device_id` for the next page.
The saved `selected_device_id` is retained even when it is outside that page.

Each candidate separates contract compatibility, whether the resource can be
selected, and current readiness (`ready`, `unavailable`, `unknown`). Matching is
deliberately conservative: exact declared contract version, existing action and
the same canonical argument schema required by sealed authority. Narrower or
wider schemas are not inferred to be safe. Missing configuration, runtime support
or credentials are blockers; sensor-linked authority remains unsupported in this
profile. Provider health missing or stale is unknown, not a healthy result.
`observed_at` is when Core evaluated the projection, not a new provider heartbeat.
`access: not_evaluated` explicitly means candidate discovery grants no rights.

For a fresh installation, the administrator supplies the selected device through
the existing activation `configuration` field, then grants the exact command scope
through the existing consent preview/Allow flow. These remain explicit mutations.
Discovery never starts a service, writes a configuration, provisions a key or
creates a grant. A newly registered provider adds a candidate without changing
existing selections. Ordinary activation still refuses an unreviewed change to
an enforced configuration. Use the explicit rebinding flow below to replace an
already approved command resource.

`platform.discover_command(binding_id)` uses the signed `command.discover`
operation through Runtime. With a current sealed command grant, it returns only
that installation's selected resource (`access: granted`). Missing, revoked,
unselected or stale grants return `access: required`, with no resource identities
or candidates. Disabled installations and transport/artifact failures are errors.
The SDK neither enumerates global inventory nor falls back to compatibility
authority. The observation is not a lease or permission ticket: submission and
the one-use execution permit still independently recheck current conditions.

The small [CommandProbe](../examples/command_probe/__init__.py) consumes only the
SDK and a logical binding. The [vertical acceptance](../backend/tests/test_application_command_discovery.py)
uses real manifest validation, administrator HTTP selection, consent seals, a
separate packaged Runtime process, SDK signatures, command queue, one-use permits
and durable journals. Two registered provider profiles execute simulated effects;
the external installer is simulated, so these checks do not claim live systemd
installation, physical hardware or a new frontend chooser.

## Required and optional SDK observations (CAP01 first slice)

`platform.discover_requirements(requirements)` combines the existing signed
`platform.discover` and scoped `command.discover` reads. It creates no registry,
grants, configuration or dispatches. Example, using two already declared command
binding IDs:

```python
summary = platform.discover_requirements([
    {
        "requirement_id": "main_output",
        "transport_contract_version": 1,
        "operations": ["command.discover", "command.submit", "command.lookup"],
        "binding_id": "output",
    },
    {
        "requirement_id": "optional_status_light",
        "required": False,
        "operations": ["command.discover", "command.submit"],
        "binding_id": "status_light",
    },
])
```

The result uses `satisfied`, `degraded` (only optional needs unmet) or `blocked`
(a required need unmet). Each item echoes its request and separates `supported`,
`missing_operations`, `met`, `reason` and the existing scoped `command` observation.
An exact transport-contract mismatch or missing action is explicit; discovery
does not try an older protocol. Non-enforced authority is reported as
`scoped_authority_required`, with no resource query or compatibility fallback.
Missing command access returns no resource identities. An approved resource can
still be incompatible, unavailable or unknown; health observation is independent
of permission. No second provider is selected automatically.

Without `binding_id`, the item checks **Core transport support only**. It does
not assert an installed/live executor, a service resource grant, or a human's
permissions for that action. The Core listener advertises only its allowed
actions; independent Runtime/worker compatibility and availability still require
the applicable family's real operation/profile checks. A `satisfied` observation
is never an execution permit: `admission_required` is always true.

The batch allows at most 16 unique requirement IDs, 16 distinct operations per
requirement and 64 KiB input. One absolute client deadline (at most 35 seconds)
covers all reads; aliases of the same binding share only that batch's read.
Command observations are fenced by a second platform read. A change to instance,
transport, recovery, authority or supported-operation metadata discards the whole
result with `observation_changed` (or `response_invalid` for an invalid identity).
Authentication/invalid responses are never softened into optional-feature absence.
There is no retry, retained cache or lease; a caller may explicitly request a new
observation later. Ordinary command submission/permit still checks current rights.

Caller-supplied binding requirements are **not** optional-resource declarations
and do not waive sealed-grant composition rules. Packages may additionally use
the transport-only and optional-resource declarations below. The resource view
adds bounded observations and an explicitly approved administrator browser
profile. These local slices have no Raspberry deployment or
hardware acceptance. The reference scenario extends the existing real-Runtime
vertical with required/optional needs, a second provider, stale health, read-only
SQL checks and revocation.

## Installation resource observations (CAP01 third slice)

`platform.discover_resources(scopes)` returns up to 16 unique, exact declared
scope names for the calling installation. It uses the existing signed
`platform.discover` action with the sole additional `resource_scopes` array;
the ordinary envelope-only platform report stays unchanged. No new Runtime
action, registry, selection, grant or business operation is introduced.

```python
view = context.platform.discover_resources([
    "storage:private_files_read", "storage:private_files_transform"
])
```

The response pins `instance_id`, `artifact_sha256`, an aware `observed_at`, ordered
`resources` and `admission_required: true`. Each resource separates `required`, `declared`,
`configured`, `access` (`not_evaluated`, `required`, `granted`), `readiness`
(`not_evaluated`, `unknown`, `unavailable`, `ready`), `reasons`, nullable provider
type/ID/version/contract and the selected resource ID when applicable. Access is
the **application service grant**, not permission for an arbitrary human action.
Missing/stale consent redacts configuration, provider and selected identities;
an undeclared scope is explicit when current source composition is available.
An unreviewable source remains redacted rather than exposing partial resources.

Current evidence profiles:

- Commands: existing capability catalog/health and the exact granted device;
  another provider never replaces that selection automatically.
- Files: authenticated file-worker metadata matching the instance/package and
  declaration, without opening a file namespace or reading user content.
- Image derivatives: a separate authenticated probe runs PNG/JPEG/WebP memory-only
  encode/decode checks in a bounded child. Missing Pillow is `unavailable`; a
  broken/timed-out probe is `unknown`. Ordinary files remain independently usable.
  Core and the file worker do not import Pillow.
- Prepared SQL: the existing signed host lifecycle/status handshake and fresh
  authority checks, without application SQL, permits or journal writes. An
  unconfirmed host is `unknown`.
- Sessions: the trusted directory's exact connectivity observation, without
  constructing/opening an executor. Ambiguous sources remain unavailable.
- Connectors: the existing local worker nonce/contract and kernel-principal
  probe. `ready` describes that executor; no destination HTTP, credentials, DNS
  or remote business operation is sent to test a connector.
- Event consumption: current source capability health, the actual Runtime event
  queue-boundary probe, and signed metadata from the exact application host.
- Tasks: a read-only local worker socket verifies the kernel principal, nonce,
  contract and a recent successful Core exchange. Missing/stopped/stale worker
  is unavailable. The exact signed application-host metadata must also match
  the current artifact/instance/configuration. No task is created, claimed,
  dispatched or ticked by discovery.
- Publications, checkpoint/identity reads and status/peer projections: the
  current Core-local journal/metadata provider. Projection readiness describes
  that local read profile, not remote enrollment, connectivity or reporting.

Unsupported/broken/unconfirmed probes stay `unknown`; configured support never
implies readiness. The optional task worker's new probe is provided by the new
Runtime component and uses `/run/3mm-tasks/worker.sock`; the systemd unit owns the
directory. An older independent worker does not acquire readiness from its unit
name. This profile uses the current public SDK/frontend and matching native
host SDK. Rollout must explicitly update the applicable Runtime/host components
through their existing health/rollback paths; a Core update is not an implicit
component update. Old components never gain new APIs from a matching SDK label.

Provider IPC runs outside Core database snapshots and review-key leases. Before
returning, Core rereads the artifact, current grant, resource identities,
installation/authority/recovery metadata and runtime binding; a changed authority
discards the result. All probes are bounded; there is no automatic retry/cache.
The report cannot waive any subsequent execution admission. Browser access uses
the same service and the separate administrator UI checks described in
[Public Extension UI](EXTENSION_UI_V1.md#cap01-resource-observations-in-an-administrator-route).
Optional-resource composition is specified below. Additional browser profiles
remain explicitly unsupported. No device or hardware acceptance is implied.

## Optional external resources at installation (CAP01 supported profile)

SDK 1.3 descriptors may declare up to 16 unique exact `optional_resources`:

```json
{"optional_resources": ["command:status_light", "connector:business_api", "event:changes", "session:console:open"]}
```

Every name must refer to its existing command, connector, event subscription or
session declaration; those declarations continue to carry the exact contracts,
versions and configuration selectors. No wildcard, unknown scope, older SDK,
unresolved sensor command or implicit fallback is supported. Owned storage,
prepared SQL, publications and peer enrollment/consent keep their existing
lifecycle/profile requirements and cannot be made optional through this field.
Unsupported combinations are rejected, not treated as degraded support.

Optional resource-resolution absence/incompatibility can omit that rule from the
current review while retaining the exact configured choice. Configuration still
obeys the author's schema; Core stops forcing a device key that is used only by
optional bindings. If the author explicitly requires that key in the schema,
it remains required. Setup/activation omits empty optional selectors. Required
resource failure still denies; arbitrary source corruption/unsupported handlers
are not softened into optional absence. No wipe or schema migration is needed.

The new scopes are never selected by default. A provider appearing later does
not gain rights. Required authority is compared independently from optional
resources; each optional use additionally compares its current exact resource
against the sealed approved one. Loss/replacement of an optional resource leaves
required work available but denies that optional use until fresh explicit
consent. Restoring the identical already-approved resource retains its choice;
changing the selection/configuration follows ordinary fresh-consent rules.
Review/allow still recheck the complete current preview, actor and artifact.
Revocation, disable and recovery continue to invalidate execution normally.

Discovery marks these rows `required: false`. Missing optional sources report
`optional_resource_unavailable`; changed approved resources report
`resource_changed_review_required`, with no provider/target disclosure. Optional
scope absence is a degraded application feature, not permission to invent a
replacement or retry a mutation. The administrator browser projection preserves
this field; the application owns its degraded-mode presentation.

## Declared transport dependencies before activation (CAP01 second slice)

An SDK 1.3 application's `application-extension.json` may declare
`platform_requirements` (at most 16 unique IDs):

```json
{
  "platform_requirements": [
    {
      "requirement_id": "command_transport",
      "transport_contract_version": 1,
      "operations": ["command.discover", "command.submit", "command.lookup"]
    },
    {
      "requirement_id": "optional_task_transport",
      "required": false,
      "operations": ["task.lookup"]
    }
  ]
}
```

This asks whether Core implements the exact transport contract/operations in the
scoped profile. `required` defaults to true. Unknown versions/actions are valid
inspectable declarations: a required mismatch blocks stage/activation; an optional
mismatch is `degraded` and permits the ordinary lifecycle. Compatibility-only
operations do not become scoped support. Duplicate IDs/actions, scalar coercion,
unknown fields and resource `binding_id` values are rejected structurally.
Resource bindings, grants and live provider readiness remain separate. In
particular, an optional transport declaration cannot make a command/session/SQL
resource optional or grant access to a named operation.

`GET /api/v1/application-extensions/packages/{sha256}/platform-requirements`
is administrator-only, read-only and `Cache-Control: no-store`. It revalidates
the exact catalog bytes and returns `artifact_sha256`, module/version and the
shared support assessment (`basis: core_transport_contract`). Valid unsupported
packages return HTTP 200 with `blocked`/`degraded` and per-requirement reasons.
`permission_approval`, `resource_bindings` and `runtime_readiness` explicitly
remain `not_evaluated`. Missing packages return 404; changed/invalid bytes 409.
This report is not an approval ticket and is not accepted as activation input.

Core recomputes the check before ordinary staging/key bootstrap and activation
state changes; required failure returns 409 naming the unmet IDs without a
helper call. It also checks before issuing prepared relational registration,
candidate adoption, preparation/start/upgrade work. The native installer checks
again after immutable package validation: generic activation refuses before
creating instance/key files, stopping the old service or touching its database;
prepared helpers check before package execution/migration/start. Existing outcome
callbacks, disable/uninstall and data-recovery evidence remain administrable.
Ordinary consent, current actor/resource checks, health verification and rollback
still run. Optional support never supplies a grant or resurrects previous consent.

The host passes validated declarations as the immutable tuple
`context.platform_requirements`. During an ordinary operation after activation,
an application can use the same declarations with
`context.platform.discover_requirements(context.platform_requirements)` when the
tuple is nonempty and the platform client is present. Host loading validates
them before importing application/migration code; this adds no startup RPC or
automatic mutation. With no declarations, existing metadata remains unchanged
and the context supplies an empty tuple.

The check is intentionally **Core transport support**, not an independent
Runtime/host build, installed provider, resource grant or live-health guarantee.
Those need the applicable family's real readiness and admission checks. No new
resource permission, persistence table, service, package version axis or
automatic installation is introduced.

## Replacing an approved command resource

The administrator API under
`/api/v1/application-extensions/{module_id}/authority/command-rebindings`
changes one command binding of the same installed artifact. It reuses the
existing registry, sealed plans/grants, authority transaction and one-use helper
lifecycle tickets. No additional registry, database migration or SDK mutation API
is introduced. The application continues to use its logical binding ID.

1. `POST` the base URL with `request_id` (32 hex), `binding_id` and `device_id`.
   The sealed preview returns `preview_id`, `revision`, `fingerprint`, exact
   `before`/`after` resources, `before_provider`/`after_provider`, retained scopes
   and the required restart. Preview saves no configuration or resource grant.
2. After reviewing the change, `POST /{preview_id}/apply` with a fresh
   `request_id`, `expected_revision`, `fingerprint` and `approve_change: true`.
   Core rechecks the same administrator session, current grant, package,
   resources and configuration. Previews expire after 15 minutes or a reboot;
   participating authority changes also make them stale.
3. Core commits the desired configuration in a disabled, `activating` state,
   retiring the previous execution epoch before calling the existing helper.
   After confirmed restart, Core verifies the immutable artifact again and
   rechecks the administrator, exact resources and policy. The new sealed grant
   and active installation become effective in one transaction. Selected scopes
   and user permission grants are preserved; the change adds no permissions.
4. `GET /{preview_id}` observes the durable state. A repeated apply request returns
   a **historical admission receipt**, never another helper call. Read status to
   distinguish `applying`, `completed`, `recovering`, `recovery_required` and
   `recovered_disabled`. Completed records are history; `access: not_evaluated`
   is not a promise that the resource or grant is still available now.

Timeout, lost process or failed completion checks leave execution blocked. They
do not restore the old grant or retry activation. Review outstanding physical
outcomes, then `POST /{preview_id}/recover` with the latest `expected_revision`
and `confirmed_external_outcome_reviewed: true`. A new lifecycle ticket fences
delayed activation. Recovery requires positive helper evidence that the runtime
is stopped and leaves the desired configuration disabled. Fresh ordinary package
consent followed by ordinary activation is required to use it. Unconfirmed
recovery remains blocked; query status before another explicit recovery attempt.

This bounded profile requires an active installation with a current enforced
grant for the selected command, the same artifact, an exactly compatible target,
and an isolated binding change. It preserves the active package's public-route
reservation through the pending restart; it does not start a disabled candidate.
Changing a shared configuration key that also changes another declared resource
is refused. Sensor-linked authority and applications with relational storage
remain outside this flow. A failed/revoked old grant needs its existing authority
recovery process; rebinding does not manufacture permission from stale consent.
Readiness is still checked when executing, and an offline provider never causes
automatic failover.

Administrators can use **Extensions → Command resources** on an installed
application. The dialog reads the installed package's declared commands, pages
through existing discovery candidates, and shows compatibility separately from
readiness. Reviewing a change shows both exact devices/providers; applying it
requires an explicit restart acknowledgment. Changing selection discards the
previous preview/acknowledgment. Expired, malformed or foreign observations cannot
enable approval. Initial installation retains its existing device-configuration
dialog; this resource replacement screen targets the active, approved profile.

`GET` the command-rebindings base URL returns the current `pending` change, or
null. It uses a DB-enforced read-only snapshot, authenticated sealed plans and
the current incarnation/epoch/guard, allowing recovery after browser/Core restart
without browser storage. It does not create keys or grants. Rebinding previews
and status observations identify `rebinding_version: 1` and `module_id`.
An uncertain apply/recovery reply is followed by a status read, never automatic
mutation replay. The dialog can find interrupted work before loading optional
package/authority details. Recovery requires a separate acknowledgment and leaves
the application stopped for fresh ordinary consent and activation.

Command history now includes `target_device_id` and `execution_status`, separately
from `status` (which becomes `invalidated` when execution authority changes).
Claimed commands remain associated with the original device and can record its
receipt under the original result/expiry rules. Invalidation cannot recall an
already-issued physical permit.
Unclaimed commands are cancelled. While original history is retained, the same
application/binding/request ID cannot be submitted to another target, even if its
previous outcome is unknown or completed. Lookup never renews permission, and a
fresh request ID must not be generated automatically to bypass uncertain work.

[Rebinding acceptance](../backend/tests/test_application_command_rebinding.py)
uses real HTTP authentication, seals, SDK/Runtime transport, command permits,
helper ticket validation/consumption, restart recovery and late result recording.
Systemd activation and physical effects are simulated; live-device acceptance
remains separate.

## SDK and execution

Use the configured `ApplicationPlatformClient`, without a Core admin credential:

```python
command = platform.submit_command(
    "entry_output", request_id="intent-unique-id",
    arguments={"channel": "gpio.output.1", "duration_ms": 100},
    ttl_seconds=10, direction="forward",
)
state = platform.command_status(command["command_id"])
```

The signed platform operations are `command.submit` and `command.status`. The
caller selects a declared binding, never a device/action outside its declaration.
Status is scoped to the owning installation. There is no additional result-event
transport: poll status using the returned command ID. Submission is queueing, not
execution or passage. Reusing an installation/target/request ID returns the same
command; changed arguments, binding, direction or TTL are a conflict. A retry does
not extend expiry. The ID must remain stable across transport retries.

The existing device queue carries `application.capability.invoke`. Immediately
before invocation the Agent obtains one live permit from
`POST /api/v1/devices/{device_id}/commands/{command_id}/authorize-execution` using
its own device credential. Core atomically claims it only for a delivered,
unexpired command in the active installation generation. The Agent refuses a
permit round trip exceeding two seconds and checks expiry again before the driver.
There is no offline authorization fallback. A briefly disconnected device may
execute after reconnecting only while the original TTL remains valid.

TTL is 1–10 seconds and cannot exceed the binding's limit. Equality with expiry
is expired. Core and Agent clocks must be synchronized; this is not a hard-real-time
transport. Permissions constrain trusted installed services, not a sandbox against
host-root compromise. Extensions remain responsible for authorizing their users
before requesting a command.

## Deadline and lost-reply recovery (0.3.0-beta.16)

`submit_command` now accepts optional `not_after`, a timezone-aware Python
`datetime` in the SDK or ISO datetime in the shared wire contract. Offsets are
normalized to UTC. Core sets expiry to `min(queue time + TTL, not_after)` and
refuses an already-expired new request. Replay preserves the original expiry;
changing/adding/removing a deadline for the same key is a conflict. Equivalent
UTC instants are equivalent deadlines. Omitting the field preserves beta.15 behavior.
The existing live permit and Agent checks enforce the resulting expiry unchanged.

For a lost submit reply, use the new signed, read-only operation:

```python
result = platform.command_lookup(request_id="intent-unique-id", binding_id="entry_output")
if result["status"] == "found":
    command = result["command"]
```

The response is `{"status": "not_found"}` or `{"status": "found", "command": ...}`.
The command contains the original `command_id`, generation, authoritative
`expires_at`, claimed flag, status, result/error and accepted `passage_event_id`.
Lookup searches only the authenticated installation's stored request hashes and
original target-device associations, never the current binding configuration.
This also supports beta.15 history without a database migration. Multiple matches
after target changes cause an explicit ambiguity error, never arbitrary selection.
History has the same retention lifetime as its original command/device records.

Only `command.lookup` may read a disabled installation's history using its still
valid instance signature; this does not start its stopped service. Disabled or
restored authority is reported as invalidated. Other platform operations still
require an active installation. Authentication/transport errors are errors, not
`not_found`. Lookup never queues, claims, commits or renews a command.

**A not-found result is a snapshot, not proof that an in-flight submit cannot
commit later.** Stop/join the submitting worker and respect the original absolute
deadline before clearing uncertain work. Never resubmit merely to discover status.
Existing in-flight permits still cannot be retracted; no hard-real-time guarantee
or automatic physical retry is introduced.

## Crash and lifecycle safety

For both `capability.invoke` and `application.capability.invoke`, the Agent commits
a SQLite FULL-synchronous attempt record before live authorization or hardware.
The record contains device/idempotency identity, a canonical content digest and
eventual result. A pending record on restart means `execution_state: unknown`;
there is no automatic physical retry, even if the crash happened before the action.
Completed results replay without invoking the driver. Journal storage errors fail
closed. Historical entries from the older result journal are reused without an
additional action. Do not delete journal files to "retry" a physical operation.

`executed` means the driver returned success, not that a person passed or that a
pulse timer completed. Driver errors after invocation are conservatively unknown.
There is no exactly-once physical guarantee without hardware transaction support.
An operator or a future device-specific transaction-status adapter must reconcile
unknown outcomes; do not issue a fresh request ID automatically to bypass them.

Disable, uninstall and activation transitions invalidate pending application
authority. Restore rotates all stored command generations before starting services
and cancels queued/delivered capability commands, including direct admin commands.
Previously accepted passage events cannot be delivered under a restored generation.
Already-issued permits and in-flight hardware actions cannot be retracted by
disable/revoke; these checks do not act as a physical emergency stop.

An extension must also discard its restored unsubmitted physical intents: Core
cannot recognize an old domain intent resubmitted as a brand-new request ID.
Normal restart preserves generations and completed journal tombstones. Journal
tombstones are not automatically pruned; include their disk usage in operations.

## Passage evidence

Only an authenticated, registered `access.passage.v1` adapter on the configured
sensor device can publish an event with this envelope:

```json
{
  "event_id": "evt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "device_id": "dev_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "event_type": "access.passage.v1",
  "occurred_at": "2026-09-13T09:00:00Z",
  "payload": {
    "schema_version": 1,
    "capability_id": "access.passage.v1",
    "binding_id": "entry_output",
    "direction": "forward",
    "command_id": "cmd_cccccccccccccccccccccccccccccccc",
    "generation": "dddddddddddddddddddddddddddddddd",
    "sensor_id": "entry.sensor.1",
    "device_health": "ok"
  }
}
```

Values above are illustrative, not live IDs/timestamps. A valid event must match
the claimed command, current generation, exact binding/direction and configured
sensor. Arrival must precede command expiry; future or pre-command timestamps,
degraded health and mismatches are rejected. There is at most one accepted passage
event per command. Identical event-ID replay is acknowledged without creating a
new event; conflicting reuse is rejected. Delivery uses the existing durable event
broker only for the owning application and its matching declared subscription.
Consumers must deduplicate by event ID because delivery acknowledgement can be lost.

Raw GPIO edges and successful pulses are never promoted to passage evidence.
A compatible adapter must establish direction and obtain the command/generation
correlation; that hardware-specific integration is not included in this release.
Late evidence does not automatically update domain state. Manual-review UI,
quarantine workflows and business counters belong to the consuming extension and
are not implemented here.

## Verification and rollout

Focused tests cover signed platform requests, scope/argument rejection, live
authorization, crash before/after action, duplicate/conflicting attempts, expiry,
restore invalidation and correlated/invalid passage evidence. Migration tests
cover clean upgrade/check/downgrade and upgrade from an earlier release.
No physical GPIO was toggled for these tests. Two-device and real-sensor acceptance,
network/power interruption and device-specific safe-state testing are still required.

Upgrade Core and Agent together through the immutable release mechanism. Older
Agents do not support application commands and must not be used for this feature.
Before rolling back to an older release, stop physical command producers and drain
or cancel pending actions. Older code cannot enforce the new execution journal or
authorization semantics. Keep a backup and follow the normal recovery procedure;
restoring a backup never grants permission to replay a physical action.
