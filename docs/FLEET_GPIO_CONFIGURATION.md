# Fleet — one GPIO output without SSH

Status: implemented locally on 2026-09-30; not deployed or hardware-accepted.
Fleet package: `0.1.6`. A new Core/Agent build is required; installing only the
Fleet ZIP does not update the Zero. The previously accepted GPIO17 LED test used
environment settings, not this new configuration flow.

## Updating the existing devices

Target: Core/Agent `v0.3.0-beta.24` and optional Fleet `0.1.6`. Wait for both
GitHub release workflows to succeed and publish their assets before updating.

1. Hub: open `/system/updates`, choose Beta, stage and explicitly install beta.24.
2. Zero: run the command below in its SSH terminal. Wait for the detached
   installer to complete successfully; do not judge Zero readiness after only
   three seconds. Provisioned upgrades retain identity, Hub binding and settings.
3. Upload and activate `3mm-fleet-0.1.6.zip` through Extensions on the Hub.
4. Check the Node is online, then follow the disabled-module workflow below.

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | sudo bash -s -- --profile node --tag v0.3.0-beta.24
readlink /opt/3mm/current
curl -fsS http://127.0.0.1:8890/ready
```

No clean installation, formatting or factory reset is required. Fleet updates
are separate ZIPs; the Core release workflow builds both Hub and ARMv6 Node assets.

## Supported first delivery

- One active-high output, logical channel `gpio.output.1`, initial/safe LOW.
- Simulation (`mock`), or Linux `gpiod` on native Raspberry Pi Zero W Rev 1.x
  and Raspberry Pi 3 Model B Plus. Other boards remain simulation-only in this UI.
- Fixed GPIO chip `/dev/gpiochip0`; BCM choices 17, 18, 22, 23, 24, 25, 27.
  Agent reports each choice's physical 40-pin header position. These are not
  guarantees that a particular connected peripheral makes a pin safe to use.
- Reserved EEPROM/I2C/SPI/serial selections are excluded from this first UI;
  an unavailable/busy line, missing gpiod package, permission failure or inactive
  readback failure rejects the change. There is no silent mock fallback.
- Existing input/multi-channel configuration is read-only, not silently replaced.
- No cloud, reader installation, local/offline hardware-control bypass or root-file editor.

## User flow

1. Open Fleet -> device details. Confirm the Node is online and its configuration
   report is fresh. An older Agent shows an upgrade notice, not guessed settings.
2. Disable every GPIO module listed in the configuration panel and wait for
   device confirmation. This stops pulses and restores module safe outputs first.
3. Select simulation/physical driver and BCM pin. GPIO17 means physical pin 11;
   physical pin 30 is GND, not GPIO30. Check wiring with power disconnected.
4. Confirm the wiring is suitable for an active-high inactive-LOW output, then
   apply. No output-on action or test pulse is sent during configuration.
5. Wait for device-confirmed success. Enable the installed output-only module
   using **Enable**; this reuses its installed package/version, without regeneration.
6. Use the separate capability controls for on/off/pulse with their own safety
   confirmation. An Agent report is not proof that a turnstile moved.

Use a resistor with a test LED or a suitable isolated interface. Do not connect
motors, locks, mains or active-low relays directly. This configuration does not
provide relay inversion or emergency-egress control.

## Generic contract and persistence

The existing administrator command endpoint queues `agent.gpio.configure`:

```json
{
  "command_type": "agent.gpio.configure",
  "idempotency_key": "fleet:<unique-32-hex-request-id>",
  "ttl_seconds": 10,
  "payload": {
    "expected_revision": "<64-hex-revision-from-Agent-report>",
    "confirmed_safe": true,
    "configuration": {"schema_version": 1, "driver": "gpiod", "bcm_pin": 17}
  }
}
```

Read the report at `GET /api/v1/devices/{device_id}/state`, field
`reported_state.gpio_configuration`. It contains the revision, source,
driver/chip/mappings, allowed pin positions, blocking module IDs and errors.
It is refreshed during normal Agent publishing and after configure/lifecycle
commands. Reads and desired-state reconciliation never apply a GPIO change.
Core does not know concrete extension IDs; no database migration is required.

Commands remain scoped by administrator/device authentication, expiry and the
durable physical-command journal. Duplicate delivery returns the recorded result;
a crash with an unresolved attempt never authorizes automatic replay. Pending UI
intent survives page reload. Offline, stale, missing or revoked state blocks apply.
Concurrent configuration revisions are rejected, not overwritten blindly.

Agent persists only the checked configuration in its private data directory,
normally `/var/lib/3mm/agent/gpio-configuration.json`, after opening the output
inactive and verifying readback. Startup loads it before activating modules.
Environment mappings are the fallback only when there is no managed file.
No credentials or root-owned environment files are written by Fleet.

Failure returns `not_executed`, `rolled_back`, or `unknown`. A failed apply
reconstructs the previous inactive mapping and retains the previous committed
file. If rollback also fails, hardware control is unavailable and the UI does
not claim recovery. Crash-time results require operator review, not retries.
Managed mode rejects GPIO modules with inputs, rules, unsafe initial values or
a second active owner; enable/disable does not delete module data.

Module install/disable supports an optional `Idempotency-Key` header. A fresh
request represents a new lifecycle operation; retries reuse that identity.
Legacy clients get a new episode after the opposite operation completes. An
old replay cannot overwrite a newer installation state. Fleet correlates lost
POST replies from history, rather than repeating the request.

## Compatibility and acceptance still pending

Upgrade Core (lifecycle key support), Agent (configuration command/report) and
Fleet before testing this flow. Older Agents ignore the managed file and read
the old environment mapping. Do not downgrade such a configured Node assuming
that the new mapping will be retained; review its hardware and environment first.
Hardware-configuration rollback here is distinct from OTA release rollback.

Local checks: 17 new Agent configuration tests, 14 lifecycle idempotency tests,
13 Fleet UI tests, type-check and actual ZIP production compilation passed.
The wider Agent check passed 32 tests; four existing POSIX `0600` assertions
failed on Windows (NTFS does not expose that Unix mode), without a functional
failure in the new flow. Linux permission/hardware acceptance remains required.

Next physical acceptance: configure GPIO17 through Fleet -> enable -> LED
on/off/pulse -> disable -> restart and confirm inactive startup/persistent mapping
-> disconnect/reconnect Hub and confirm no stale or uncertain command replay.
Repeat clean Node installation. These tests have not yet been performed for
the new configuration feature; Milestone 13 remains open.
