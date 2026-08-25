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

## Trusted local-network Core access

Core was restarted manually with an all-interface listener on port `8887` and
was reached successfully from the development laptop on the same trusted local
network. Both `/health` and `/ready` returned HTTP 200. The Agent remained
bound to `127.0.0.1:8890`; a connection attempt to its port through the device
LAN address failed as intended. NetworkManager and firewall configuration were
not changed, and no systemd unit was installed. This validates local-network
development access only and does not authorize direct Internet exposure.

## Laptop-built frontend LAN smoke test

The Vue frontend was type-checked and built on the laptop, then copied to the
device as static files; Node.js was not installed on Raspberry Pi. A manual,
unprivileged stdlib SPA server exposed the artifact on LAN port `8080`, with a
runtime-only Core URL and Core CORS restricted to that frontend origin.

Browser validation confirmed that `/` redirects to the login screen, direct
reload of `/user/login` succeeds, assets load, the browser console has no
errors, and a missing asset remains HTTP 404. This server is suitable for the
current LAN smoke test only and is not the final TLS/reverse-proxy boundary.

## Standalone systemd installation

The reviewed release installer was run interactively with sudo after the
manual-process tests. It created the dedicated unprivileged `3mm` account,
installed an immutable release under `/opt/3mm/releases`, created the shared
virtual environment under `/opt/3mm/venv`, and stored runtime state under
`/var/lib/3mm`. No password was written to a command or file.

Core, Web and Agent are enabled and active. Setup is disabled and inactive.
Core listens on LAN port `8887`, Web on LAN port `8080`, and Agent remains on
`127.0.0.1:8890`. Health, readiness, SPA direct-route reload and missing-asset
404 behavior pass locally and over LAN. The migrated Agent reports the same
stable device ID as before installation. NetworkManager remains connected and
no network or firewall configuration was changed.

The first hardened Core start exposed an old writable-path assumption for the
uploads directory. Core now has a typed `UPLOADS_DIR` setting and systemd
places uploads under `/var/lib/3mm/core/uploads`; `ProtectSystem=strict` remains
enabled rather than being weakened.

Deployment contract update (2026-08-24): the shared virtual environment above
documents the original hardware validation. Current releases instead own
`/opt/3mm/releases/<release-id>/.venv`, while `/opt/3mm/current` is switched
atomically. This makes dependency rollback follow the same release boundary as
the application code.
