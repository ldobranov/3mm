# Raspberry Pi Test Baseline

Capture date: 2026-08-09
Purpose: first physical target for Core, Agent and headless provisioning validation

This report intentionally excludes hostname, IP address, machine identifiers, credentials and network names.

## Hardware and operating system

| Property | Observed value |
|---|---|
| Model | Raspberry Pi 3 Model B Plus Rev 1.4 |
| Architecture | ARM64 (`aarch64`) |
| Operating system | Debian GNU/Linux 13 (`trixie`) |
| Kernel | `6.18.34+rpt-rpi-v8` |
| Python | 3.13.5 |
| Memory | 905 MiB total, 754 MiB available at capture time |
| Swap | 904 MiB, unused at capture time |
| Root filesystem | 29 GiB total, 25 GiB available |
| Network management | NetworkManager active; Wi-Fi hardware enabled |

## Architectural implications

- The Agent and a small Standalone/Hub installation are valid targets for this device.
- Production dependencies must support Python 3.13 and ARM64.
- The frontend should be built off-device and deployed as static artifacts; the Pi must not require Node.js for normal operation.
- AI inference, module generation and large build jobs stay on a remote AI/build service or a more capable PC.
- Services need explicit memory, log, event-buffer and disk limits.
- Swap activity must be monitored because sustained build or runtime swapping would reduce responsiveness and increase SD-card wear.
- The provisioning adapter should use NetworkManager while keeping NetworkManager-specific behavior outside domain logic.

## First hardware validation sequence

1. Confirm required Python dependencies install under Python 3.13 and ARM64.
2. Install only the minimal Agent into an isolated virtual environment.
3. Verify stable identity persistence across a process restart and device reboot.
4. Measure idle Agent memory, CPU and startup time.
5. Add the local Agent to the same device as Core and measure the combined Standalone footprint.
6. Exercise NetworkManager through a read-only adapter before changing any connection.
7. Test setup access-point creation and rollback only after the recovery path is implemented.

No network configuration change is authorized by this baseline capture.

## Minimal Agent validation

Validation date: 2026-08-09

The Agent from commit `bc2353c` was installed as the regular device user in
an isolated virtual environment under `$HOME/3mm-agent-test`. The test did not
install system packages, change NetworkManager or create a systemd unit.

| Check | Result |
|---|---|
| Python 3.13 / ARM64 dependency installation | Pass |
| Loopback-only listener | Pass: `127.0.0.1:8890`; unreachable through the LAN address |
| `/health`, `/ready`, `agent.hello`, `agent.inventory` | Pass: HTTP 200 |
| Stable identity across a process restart | Pass; identity file mode `0600` |
| Stable identity across a full device reboot | Pass; device ID and identity-file SHA-256 unchanged after manual Agent restart |
| Startup to successful health response | 2.635 seconds |
| Idle memory | 46.1 MiB RSS; 40.7 MiB PSS |
| Idle CPU | 0.20% of one CPU core over 10 seconds |
| NetworkManager state | Still active; observed read-only |
| Agent systemd unit | Not created |
| Provisioned role handoff | Pass: Standalone to Hub to fallback Node across process restarts |
| Identity during role changes | Preserved across every tested role restart |

The reboot validation left the Agent under manual process control and did not
create a systemd unit. The read-only NetworkManager adapter was
validated on this device without reading connection names, SSIDs, UUIDs, IP
addresses or credentials. The general state and active-connection-set hash
were unchanged before and after inspection. Access point creation and network
mutation remain unauthorized until a separate hardware recovery plan is
approved.

## Standalone Core plus local Agent validation

Core was copied into its own test directory and installed into a separate
virtual environment using only the production Python requirements. It used a
dedicated SQLite database and was started manually on `127.0.0.1:8887` while
the local Agent continued on `127.0.0.1:8890`. No system packages, systemd
units or NetworkManager settings were changed. Core was stopped after the
measurement; the Agent was left running.

| Check | Result |
|---|---|
| Core dependency installation on Python 3.13 / ARM64 | Pass |
| Core startup to successful readiness response | 8.370 seconds |
| Core health and readiness | Pass: HTTP 200 |
| Core idle footprint | 89.9 MiB RSS; 80.4 MiB PSS; 0.10% of one CPU core |
| Agent idle footprint during combined test | 46.4 MiB RSS; 37.6 MiB PSS; 0.20% of one CPU core |
| Combined idle footprint | 136.3 MiB RSS; 118.0 MiB PSS |
| Listener isolation | Pass: Core and Agent bound only to `127.0.0.1` |
| NetworkManager state during measurement | `connected`; observed read-only |
