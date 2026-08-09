# Milestone 5 Report

Date: 2026-08-09  
Baseline: Raspberry Pi `rasp-3mm` (`aarch64`, 4 logical CPUs)  
Accepted runtime release: `782a4b9-m5`  
Device identity: `dev_a3ad5f8844f1466f847f5f8cf78d6fe3`

## Result

Milestone 5 is complete. The system now has portable digital input/output
contracts, a deterministic in-memory GPIO driver, a trusted manifest-driven
Agent module, capability-driven Core controls, timestamped device events, and
local input-to-output rules that continue while Core is unavailable.

For this vertical slice, the Core UI is derived from the generic capability
registration and invokes its declared action. Initial inputs, outputs, and
rules remain manifest-owned configuration; a general-purpose JSON Schema form
renderer is not required for the fixed reference module.

The mock driver is deliberately isolated from Linux GPIO. It can run on a
native Raspberry Pi profile for acceptance testing without opening or changing
physical pins. Real Raspberry GPIO access remains deferred to Milestone 7.

## Physical acceptance evidence

The final acceptance procedure ran on `rasp-3mm` from
`2026-08-09T21:52:09+03:00` through `2026-08-09T21:52:55+03:00`:

- all `3mm-agent`, `3mm-core`, and `3mm-web` services were active before and
  after the test;
- Agent restarted with input and output both `false`;
- Core was stopped and its readiness endpoint was confirmed unreachable;
- simulated `gpio.input.1=true` changed `gpio.output.1` to `true` locally while
  Core remained stopped;
- Agent retained one offline `gpio.input.changed` event with ID
  `evt_30c680e45a4549f7b9a67e44a66f2fe7`;
- after Core restarted, the outbox emptied and Core contained exactly one copy
  of that event;
- the same acknowledged outbox entry was deliberately replayed again; the
  outbox emptied and Core still contained exactly one event;
- Agent restarted after the replay with its persistent device identity
  unchanged and its deterministic GPIO state reset to `false`.

This proves the offline automation and replay acceptance criteria, including
idempotent duplicate handling.

## Resource snapshot

The process snapshot was captured several minutes after the acceptance restart:

| Service | RSS | Lifetime CPU average |
| --- | ---: | ---: |
| Agent | 53,772 KiB (52.5 MiB) | 1.2% |
| Core | 98,384 KiB (96.1 MiB) | 2.9% |
| Web | 20,808 KiB (20.3 MiB) | 0.0% |
| Combined | 172,964 KiB (168.9 MiB) | 4.1% |

The host reported 949,071,872 bytes of RAM with 305,328,128 bytes available
during the earlier acceptance snapshot. These are observational values on the
current Pi image, not hard resource limits.

## Automated verification

- 94 backend, Agent, and shared-protocol tests passed on the Raspberry Pi test
  environment;
- the suite covers deterministic GPIO transitions, trusted activation,
  restart restoration, offline local rules, event persistence, duplicate
  replay, capability commands, and the administrative event read API;
- frontend TypeScript checking passed;
- the frontend production build passed (247 modules transformed).

The existing bundle-size and dynamic-import warnings remain non-blocking and
are unrelated to this milestone.
