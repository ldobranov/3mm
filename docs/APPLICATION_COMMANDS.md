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
