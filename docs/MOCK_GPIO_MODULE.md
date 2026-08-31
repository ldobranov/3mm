# Mock GPIO Module

`org.3mm.mock-gpio` is the reference vertical-slice module for the trusted
Agent runtime. It proves GPIO-shaped behavior without accessing Raspberry Pi
pins or importing Raspberry-specific libraries.

## Capabilities and behavior

- input: `gpio.input.1`;
- output: `gpio.output.1`;
- registered control capability: `gpio.digital.control`;
- trusted entrypoint: `builtin:gpio.digital.v1`;
- local rule: when input 1 becomes `true`, output 1 becomes `true`;
- safe bounded `pulse_output` control with automatic output restoration;
- emitted event: `gpio.input.changed` with the input value, sequence, target
  output, and applied output value.

Output changes from Core use the generic capability invocation API. Input
events use the authenticated device event API. Failed event delivery is stored
in the Agent outbox and retried after Core reconnects. Core treats `event_id` as
an idempotency key, so acknowledged replay cannot create duplicate records.
Hardware callbacks only enqueue delivery work, so Core latency cannot block a
local input rule.

## Safety boundary

The driver stores all state in Agent memory. Enabling it on a native hardware
profile does not imply real GPIO support and does not touch NetworkManager,
`/dev/gpiochip*`, sysfs GPIO, or pin configuration. The Agent HTTP service
remains bound to `127.0.0.1`.

The loopback-only diagnostic endpoints are:

- `GET /api/v1/agent/mock-gpio/state`;
- `POST /api/v1/agent/mock-gpio/inputs/{capability_id}` with a Boolean `value`.

They exist for deterministic local acceptance. The same trusted capability
handler runs against the native `gpiod` adapter when explicit physical line
mappings and permissions are configured.

## Manifest configuration

The module manifest declares inputs, output safe states, pulse bounds and local
rules in `configuration_defaults`. Agent validates capability names, Boolean
values and duration limits before activation. Unsupported capabilities or
untrusted entrypoints fail closed, while failed module updates preserve the
previously active release. The complete hardware and capability contract is in
[`DIGITAL_IO.md`](DIGITAL_IO.md).
