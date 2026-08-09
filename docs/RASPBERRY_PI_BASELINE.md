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
