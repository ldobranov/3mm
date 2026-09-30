# Minimal Node installation

Introduced in beta.21 (beta.20 published no assets). Beta.19 has no Node
artifact. Do not confuse this with selecting the Node role in a full installation.

## Supported initial target

- Raspberry Pi Zero W Rev 1.1, ARMv6 (`armv6l`).
- Raspbian 13, CPython 3.13, NetworkManager and systemd.
- A full installation on the existing Hub is independent and is not replaced.
- No Core database, AI dependencies, npm/compiler, business extensions or default
  Core administrator account are created on a minimal Node.

After publishing a release with Node assets, install using:

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | sudo bash -s -- --profile node
```

Add `--tag vX.Y.Z` to select a published version explicitly. The bootstrap validates
the separate `3mm-node-manifest.json`, host Python/architecture, archive size and
SHA-256. It runs detached so fresh-install AP activation may safely disconnect SSH.
Join `3mm Setup XXXX`; the fallback portal is `http://10.42.0.1:8895/setup`.
Only Node is selectable; direct requests for Hub/Standalone are rejected before
network changes. A saved Hub address is not completed enrollment. Pairing remains
the next Fleet stage; no cloud is needed for local installation.

Agent RPC stays on `127.0.0.1:8890`. After network setup the permanent Node web
administration UI is not implemented yet, so no Core login page is expected.

## Packaging and upgrades

The release workflow builds the Node artifact separately; Core OTA manifests stay
unchanged. `prepare_node_wheels.py` downloads binary wheels for CPython 3.13 ARMv6.
For the two reviewed gpiod/pydantic-core versions it verifies the piwheels ARMv6
and ARMv7 aliases have the same source hash before correcting the wheel platform
tag. It regenerates RECORD, leaves binary bytes unchanged, and records original
and output hashes in `deployment/node-wheels/provenance.json`. It never patches
an installed environment or globally disables pip compatibility checks.

The artifact contains this wheelhouse. Installation uses `--no-index` and
`--only-binary`, then `pip check` and runtime preflight before stopping services.
No Rust/C build runs on Zero. New native versions require explicit review.

The existing immutable layout, deployment lock, environment backup, readiness
checks and previous-release link are reused. Existing Node identity, configured
Hub URL and GPIO mappings are retained. Cross-profile replacements are refused.
Node uses `3mm-node-recovery.service`, not the Core update helper. There is no
Node OTA UI yet; the same bootstrap/installer can apply a later Node artifact.

## Diagnostics

```bash
sudo systemctl status 3mm-agent 3mm-node-recovery
sudo journalctl -u 3mm-agent -u 3mm-node-recovery -n 40 --no-pager
curl -fsS http://127.0.0.1:8890/ready
sudo /opt/3mm/current/.venv/bin/python -m pip check
```

Agent runs after provisioning; during first-boot setup inspect `3mm-setup`,
`3mm-setup-ap` and `3mm-network-helper` instead. No GPIO output is enabled by
installation. Electrical tests, pairing and access-control behavior are not
certified by these health checks. See [target evidence](FLEET_ZERO_BASELINE.md).
