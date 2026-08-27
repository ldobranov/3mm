# 3mm installation

The supported Raspberry Pi installation uses an official immutable release.
It does not clone the repository, build the application on the device or write
passwords to command arguments.

## One-command Raspberry Pi installation

On a current 64-bit Raspberry Pi OS or Debian installation, run:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | sudo bash
```

The bootstrap defaults to the latest published Beta release while 3mm remains
in Beta. It:

1. selects the official artifact for the current CPU architecture;
2. validates the release identity and reviewed dependency list;
3. installs only those APT dependencies;
4. verifies the artifact size and SHA-256 digest;
5. runs the read-only first-boot preflight;
6. starts the rollback-capable immutable installer as a detached systemd job.

Git is not required on the Raspberry Pi.

## Wi-Fi-only installation

The detached job continues after SSH disconnects. On an unprovisioned device,
the connection is expected to close when `wlan0` becomes the open `3mm Setup
XXXX` access point. Join that network from a phone. The captive portal should
open automatically; its fallback address is:

```text
http://10.42.0.1:8895/setup
```

The command prints the transient service name. While LAN access remains, follow
its log with the printed `journalctl` command.

## Installer options

Pin an exact published release:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | \
  sudo bash -s -- --tag v0.3.0-beta.6
```

Select a channel explicitly:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | \
  sudo bash -s -- --channel beta
```

Override the detected application origin only when necessary:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | \
  sudo bash -s -- --frontend-origin http://192.168.1.88
```

Available options are shown without changing the system:

```bash
bash install.sh --help
```

## Installed layout

```text
/opt/3mm/current  -> active immutable release
/opt/3mm/previous -> rollback release
/opt/3mm/releases -> installed release directories
/var/lib/3mm      -> persistent application and device state
/etc/3mm          -> protected service configuration
```

After setup, the application is available at `http://<device-ip>/` and
`http://<hostname>.local/`. Port `8080` remains as a compatibility listener.

Continue with the complete
[Raspberry Pi first-boot procedure](docs/RASPBERRY_PI_FIRST_BOOT.md) for phone
setup, administrator creation, local Agent pairing and acceptance checks.

## Development deployment

For an unpublished development commit, use the laptop-driven `deploy.ps1`
workflow documented in the first-boot procedure. The public one-line installer
intentionally accepts only published release artifacts.
