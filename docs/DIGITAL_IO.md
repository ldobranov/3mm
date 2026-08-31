# Universal digital I/O

3mm exposes digital inputs and outputs as generic Agent capabilities. Core,
extensions and automations operate on declared capability and channel IDs; they
do not know Raspberry Pi pin numbers or application-specific concepts.

## Hardware boundary

The native driver uses the Linux GPIO character-device API through the official
`gpiod` bindings. Physical BCM line mappings stay in the Agent service
environment:

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

## Capability contract

`gpio.digital.input` publishes `gpio.input.changed` with:

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
