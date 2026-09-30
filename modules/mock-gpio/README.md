# GPIO development package 1.0.6

1.0.6 adds `armv6l` (Raspberry Pi Zero W) to the package architecture list.
The shared `builtin:gpio.digital.v1` handler is portable Python; no per-board
module implementation is required. Existing aarch64/x86_64 support is retained.

## Simulation versus physical pins

Despite the historical **Mock GPIO** name, this package uses the Agent's
configured GPIO driver. It does **not** force simulation:

- `THREE_MM_GPIO_DRIVER=mock` (the Agent default) uses memory only. No physical
  pin will change. This is the first safe Fleet test on a freshly installed Node.
- `THREE_MM_GPIO_DRIVER=gpiod` uses the Linux GPIO device with explicit
  `THREE_MM_GPIO_INPUTS` and `THREE_MM_GPIO_OUTPUTS` mappings. This package
  needs both logical channels `gpio.input.1` and `gpio.output.1` configured.

Installation initializes the configured output to false. Disable/shutdown
also restores false. Do not install on an unknown physical mapping or a
connected turnstile. Real wiring and active-low relay polarity require a
separate approved hardware test. Architecture admission is not proof of a
physical GPIO test on Zero.

## First test

Upload `mock-gpio-1.0.6.zip` to the Hub's Fleet module package list, then install
on Zero only after confirming its driver is `mock`. Wait for the command's
`succeeded` result, not merely queue delivery. The device should then expose
`gpio.digital.input` and `gpio.digital.control`. Disabling the module should
also produce a confirmed command result. No Node/Core release update is needed
for the manifest change.

`agent/tests/test_gpio_armv6_package.py` validates the actual package against
Core and Agent ARMv6 checks, input event publication, output invocation and
safe disable with the mock driver. The Zero baseline separately records native
gpiod import success; actual physical pin I/O on Zero remains untested.
