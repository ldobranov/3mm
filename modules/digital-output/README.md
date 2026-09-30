# Digital GPIO Output 1.0.0

Output-only package for the existing trusted digital GPIO handler. Unlike the
development Mock GPIO package, it needs no input mapping. The package uses the
existing handler; configuring pins through Fleet requires Core/Agent beta.24
and Fleet 0.1.6. The Agent selects mock versus gpiod; the package
does not force either driver and does not configure physical pin numbers.

Disable other packages providing `gpio.digital.control` before installation:
this package must be the only active owner of that capability on the device.
In particular, disable Mock GPIO and await its confirmed command result.
Install this package through Fleet and await its confirmed result.

## Preferred configuration without SSH

Update Hub and Zero to beta.24, then install Fleet 0.1.6. Disable all GPIO modules
and await confirmation. In the device configuration panel choose gpiod and BCM17
(physical pin 11), confirm active-high/inactive-LOW wiring, apply and wait for
the reported configuration. Enable this output-only module after success.
See [configuration and upgrade guide](../../docs/FLEET_GPIO_CONFIGURATION.md).

Managed configuration survives restart and takes precedence over environment
settings. Return to mock through the same disabled-module workflow, not by
editing environment variables. New-flow hardware acceptance remains pending.

## Historical environment-based LED test

For the approved Zero LED test before managed configuration (GPIO17, physical header pin 11; LED cathode to
GND physical pin 30; a series resistor is required), edit only these keys in
the existing root-owned `/etc/3mm/3mm.env`:

```ini
THREE_MM_GPIO_DRIVER=gpiod
THREE_MM_GPIO_CHIP=/dev/gpiochip0
THREE_MM_GPIO_INPUTS=
THREE_MM_GPIO_OUTPUTS=gpio.output.1:17
```

Check that gpiochip0 is the board GPIO controller before enabling it; use the
read-only `gpiod.Chip(...).get_info()` check in the installed virtualenv.
Do not overwrite the environment file or its other settings. Restart only
`3mm-agent.service` on the Node, then check `/ready` and the Agent logs before
sending commands. No networking/AP/recovery/Hub service changes are needed.

The output initializes inactive, and disable/runtime shutdown returns it to
false. A pulse is handled locally by Agent and returns to false after its timer;
mechanical/fail-safe guarantees still require hardware verification.

To undo the driver change, restore `THREE_MM_GPIO_DRIVER=mock` and restart
the Node Agent. Existing identity, Hub enrollment and module data are retained.
Never test a connected turnstile using this LED acceptance configuration.

Local test: `agent/tests/test_digital_output_package.py` validates the actual
package on simulated ARMv6, rejects any input access, and verifies set/disable
with mock output hardware. On 2026-09-30 the user confirmed the physical GPIO17
LED test through Fleet on a Zero W. See
[test evidence and remaining acceptance](../../docs/FLEET_ZERO_BASELINE.md#fleet-and-physical-led-acceptance--2026-09-30).
Pulse timing, failure/reconnect and a relay/turnstile were not separately accepted.
