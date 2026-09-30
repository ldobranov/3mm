# Fleet Zero W baseline

Read-only inspection: 2026-09-29, user-provided `rasp-3mmw.local`.

- Board: Raspberry Pi Zero W Rev 1.1; machine architecture `armv6l`.
- OS: Raspbian GNU/Linux 13 (trixie), reported Debian version 13.6.
- Python: 3.13.5; `python3-venv` installed, venv CLI available.
- System Python has no pip module. This does not prove pip is unavailable in
  a freshly created virtualenv; no environment was created during this inspection.
- NetworkManager: active; wlan0 connected; no network changes performed.
- Memory snapshot: 426 MiB total, 311 MiB available; swap unused.
- Root filesystem: 29 GiB total, approximately 25 GiB available.
- No `/opt/3mm/current` release exists.
- System `python3-libgpiod`: 2.2.1-2+rpi1+deb13u1.
- APT offers `python3-pydantic-core` 2.27.2-3, not installed. This is not the
  pydantic-core version resolved by current pinned Node requirements; do not mix
  those dependencies or claim the package proves compatibility.

SSH host key recorded on first connection (TOFU) in the ignored local Fleet
known-hosts file; matching remote public fingerprint reported:
`SHA256:6sKQfM15lcz/4xtR04CYp8AAUZh0Lnf5sVei+/2IzYI` (ED25519).
No password or private key is recorded in this document.

## Isolated dependency check — 2026-09-29

Created an unprivileged test virtualenv under
`/home/raspberry/3mm-node-check.7soz8Y`, separate from system Python.
Installed `deployment/node-requirements.txt` with `--only-binary=:all:`;
no source compilation, apt changes or system service activation.
Agent, Setup, Node recovery and gpiod imports succeeded on the actual ARMv6 CPU.

Important packaging discrepancy: piwheels supplied filenames tagged ARMv6 for
`pydantic_core 2.46.4` and `gpiod 2.5.0`, but both installed `WHEEL` metadata
files declare `cp313-cp313-linux_armv7l`. The interpreter supports
`cp313-cp313-linux_armv6l`; `pip check` therefore reports both as unsupported.
Successful imports do not resolve this metadata discrepancy or certify all
native code paths. Do not silently patch metadata or suppress this check in the
installer. Resolve and validate the ARMv6 artifact source before release support.

Follow-up: the [piwheels FAQ](https://www.piwheels.org/faq.html) explains that
most ARMv6/ARMv7 wheel files are identical. This explains the observed aliasing,
but is not a blanket acceptance of ARMv7 binaries. The experimental installer
retains `pip check` as a blocking gate. A release wheelhouse needs explicitly
validated tags and recorded source/output hashes; no installed metadata edit or
global platform-check bypass is approved by this evidence.

## Loopback runtime smoke check

- Agent on `127.0.0.1:18890`: health, readiness, hello and inventory HTTP checks
  passed. Device identity persisted across a process restart using the same test
  state directory.
- Setup on `127.0.0.1:18895`: health, readiness and `/setup` HTML returned OK.
- Agent RSS: 41,484 kB; Setup RSS: 38,660 kB. Each showed approximately 1% of
  one CPU over a five-second idle sample; these are snapshots, not load benchmarks.
- Services ran sequentially, unprivileged, with isolated state. Agent used
  `mock-linux` inventory/mock GPIO; Setup used its mock network adapter.
  No pairing, physical GPIO, real AP, Wi-Fi mutation or captive portal was tested.
- All smoke-test processes stopped. The test directory/venv remains for follow-up.

Current public release artifacts still do not support armv6l. The Hub at
`rasp-3mm.local` was not changed or used as this test target.

## Installed Node and real rollback acceptance

Installed on 2026-09-29; independently rechecked over a new SSH connection on
2026-09-30. This is a working-tree test artifact, not a published beta.19 release.

- Reviewed release-time wheel retagging verified both piwheels aliases against
  their source hashes. Native binary bytes were unchanged. Offline installation
  and `pip check` succeeded in the fresh release-specific virtualenv.
- Archive SHA-256:
  `5536e00732a83a4b78d29f14fab7a80ffcfbf8d8f5c05cb40d6a20886802b5d6`.
- Current release: `/opt/3mm/releases/node-acceptance-20260929`.
- Initial installation completed successfully. Agent and Node recovery services
  are active; `/ready` returns `ready`.
- Existing Wi-Fi was retained for acceptance by explicitly initializing an
  unpaired Node provisioning snapshot before installation. No Wi-Fi credentials
  were read or copied. This is not a clean-media AP onboarding test.
- A second immutable installation, `rollback-test-node-20260929`, deliberately
  failed **after** its health check. Exit status 1 for this test job is expected.
  The installer restored the original current link, services and environment.
- Device ID before/after: `dev_e442cbc91980410586f45b16759fed61`.
  Identity-file SHA-256 remained
  `3708c3c894009b8eb6349c04cf138f542a345da49377ff479d04e92d8082f5b2`.
- The environment matches its pre-update backup byte-for-byte. The failed
  candidate release was removed; source archive and deployment backup remain.
- No Core state was created. No Hub, payment, physical GPIO or business extension
  was touched. No automatic pairing or permanent Node web UI is claimed.

Pending: publication of the new bootstrap/Node assets, clean-media phone/AP
onboarding and later Fleet pairing/hardware acceptance. The GitHub one-command
path cannot be tested end-to-end until a new release is published.
