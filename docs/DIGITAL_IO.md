# Universal digital I/O

3mm exposes digital inputs and outputs as generic Agent capabilities. Core,
extensions and automations operate on declared capability and channel IDs; they
do not know Raspberry Pi pin numbers or application-specific concepts.

## Hardware boundary

The native driver uses the Linux GPIO character-device API through the official
`gpiod` bindings. The current input-profile path keeps physical BCM mappings in
an approved Agent provider, managed through Devices. The older low-level
environment mapping remains available for platform development, not as a step
required from an application user:

```text
THREE_MM_GPIO_DRIVER=gpiod
THREE_MM_GPIO_CHIP=/dev/gpiochip0
THREE_MM_GPIO_INPUTS=gpio.input.1:17
THREE_MM_GPIO_OUTPUTS=gpio.output.1:27
```

Input channels use an internal pull-up, active-low semantics and both-edge
notifications with a 20 ms debounce. Connecting a configured input to GND reads
as `true`. Edge callbacks are isolated from Core HTTP delivery, so a slow or
offline Core cannot delay a local hardware automation. An input-only or
output-only device is valid.

Never connect a relay coil, motor, lock or other load directly to a Raspberry
Pi GPIO. Use a correctly powered driver, transistor, optocoupler or relay board
with suitable protection and a shared reference only where the hardware design
requires it.

## Profile-configured generic digital inputs (CAP14)

Use **Devices → Hardware providers → GPIO digital input** on an Agent advertising
`gpio_input_profiles.v1`. Its `gpio.digital.input` contract 2.0 emits generic
edges, not button gestures. One immutable profile maps one to seven logical
channels to distinct supported BCM pins, with pull-up/active-low semantics and
0–1000 ms debounce (20 ms default). The starter form offers `gpio.input.1` on
GPIO17 / physical pin 11; separately authored profiles can declare other logical
channels without a Core/Agent source change. Connect contacts to GND without an
external voltage source. The native profile currently gates the supported Zero W
and Pi 3 B/B Plus `/dev/gpiochip0` mappings; simulation remains separate.

Preparation adds only immutable package bytes to the catalog. Installation still
requires exact device/package/profile approval before a GPIO line is opened.
Disable the old provider before changing its profile; two modules cannot own the
same runtime capability. Partial line-claim failure releases already claimed
lines. Disable/shutdown closes inputs without manufacturing an edge.

Each `gpio.input.changed` payload contains `capability_id`, `profile_sha256`,
`channel`, `bcm_pin`, `value`, per-channel `sequence`, activation `stream_id`,
`monotonic_ns` and `simulated`. Native timestamps come from the monotonic kernel
edge clock. Events use the existing Agent outbox and current Core event grants;
there is no GPIO polling in the application. Consumers must deduplicate events,
reject discontinuous/out-of-order pairs and never pair edges across activations.
An edge is not permission to perform a physical output.

Monitor 0.8.1 interprets a contiguous down/up pair lasting 30 ms to under
8 seconds as next saved screen. Its optional device/channel binding, event
journal and press state are owned by the application. Restart disarms an
unfinished press; long holds do nothing. AP/reset are not included. The button
does not enable stopped LCD output or change its existing permission/receipt
rules. Other applications may interpret the same generic input differently.

## Package-supplied profile forms

Core no longer imports a driver-specific Python template registry. Five starter
definitions are ordinary JSON resources in `backend/provider_templates`; the
authoring-only `python -m tools.hardware_template_catalog` reproduces them.
Physical LCD starters separate two- and four-row controller limits rather than
putting hardware conditionals in Core. Existing installed LCD providers stay
unchanged.

An ordinary inert Agent ZIP may include `hardware-template.json`, with
`profile_template: true` in capability metadata. The strict descriptor declares
bounded form fields and JSON-pointer bindings to existing same-typed profile,
metadata and contract-enum values. It cannot replace permissions, entrypoints,
actions, event names or schema structure. Profile digests and module-ID suffixes
are derived again; the final manifest/package is validated before catalog writes.
No expressions, imports, scripts or driver code run in Core.

Templates are selected by the exact source-package SHA256, not a mutable name.
Uploaded template packages appear through the existing admin upload/catalog and
can be deleted normally. Changing or corrupting a source invalidates its old
selection; preparation cannot silently use another source. Preparation is not
installation, GPIO execution, native-code isolation or application consent.

This slice makes new supported GPIO pins, profiles and consumer behavior
independent of Core/Agent code. Arbitrary new native driver code is **not**
loadable from these inert templates; a separate trusted-driver execution contract
is still future work. Existing older GPIO event sources do not gain the new
timestamp/stream guarantees merely by sharing a capability name. Use the current
profile for consumers requiring contract 2.0; the general event compatibility
preview remains a separate discovery limitation.

## Capability contract

The older environment-backed `gpio.digital.input` path publishes
`gpio.input.changed` with:

- `channel`: stable logical input ID;
- `value`: logical Boolean value;
- `sequence`: monotonic transition number for the running Agent process.

`gpio.digital.control` supports two actions:

- `set_output` with `channel` and Boolean `value` for persistent control;
- `pulse_output` with `channel` and integer `duration_ms` for bounded actuator
  control.

The output values in `configuration_defaults.outputs` are also the safe states.
A pulse writes the inverse of that safe state, then restores the safe state
automatically. The default accepted pulse is 50–10000 ms. A module can narrow
that range with `pulse_min_ms`, `pulse_max_ms` and `pulse_cooldown_ms`, up to an
absolute 60-second limit. Concurrent pulses on one channel and persistent writes
during an active pulse are rejected. Agent shutdown, module replacement and
module disable cancel active timers and restore every declared safe state.

Output transitions publish the generic `gpio.output.changed` event with the
channel, value, reason and pulse duration where applicable.

## Latency boundary

Physical edges and local Agent automations now use the fast local path. Event
upload and capability-state publishing run on a separate bounded worker and use
the persistent outbox when Core is unavailable.

Commands initiated through the Core API use a dedicated authenticated Agent
worker with a bounded five-second long poll. A committed command wakes an Agent
waiting in the same Core process immediately; the database remains the durable
source of truth and the long-poll timeout is the recovery bound if a wake-up is
missed or Core is restarted. Older Agents remain compatible because omitting
the wait parameter keeps the immediate `204 No Content` response.

The in-process wake-up assumes the current single-worker Core deployment. A
future multi-worker Hub must replace it with a shared notifier, while retaining
the same database queue and HTTP contract. Browser-side live state is still a
separate transport concern; an HTTP client may poll command completion even
though actuator delivery itself is no longer tied to the heartbeat interval.
