# Agent Lifecycle Probe 1.0.0

This optional acceptance package exercises the existing remote Agent module
lifecycle on a paired Node, including ARMv6 Raspberry Pi Zero W. It contains
only a manifest and a JSON package health marker. No runtime executable,
capabilities, GPIO, network changes, dependencies or module permissions.
It does not prove reader/relay support or live hardware health.

## Build

From the repository root, using the development Python environment:

```powershell
backend/.venv/Scripts/python.exe modules/agent-probe/build_package.py --output .runtime/agent-probe-1.0.0.zip
```

On Linux use `python3` with the project dependencies for validation/tests;
the builder itself uses only the standard library. Output is deterministic
across checkout newline conventions; the builder prints its SHA256.

## Real-device acceptance

1. On the Hub, upload the ZIP through the module-package upload control in
   Devices/Fleet. This is an **Agent module**, not a Core application extension.
2. Open the paired Zero's device page and install Agent Lifecycle Probe 1.0.0.
3. Wait for the install command to reach `succeeded` and the installed version
   to become 1.0.0. `queued`/`delivered` is not acceptance. Refresh if necessary.
4. Disable it; wait for a separate command to reach `succeeded` and the module
   to become disabled. Existing module data is retained.

The Functions section remains empty deliberately: this fixture registers no
fake functions. No SSH, Node release upgrade or Hub restart is needed for this
test. Do not keep pressing Install while a command is pending or uncertain.
Re-enable/reinstall-after-disable is a separate lifecycle scenario, not claimed
by this first acceptance cycle.

## Local evidence versus target evidence

`agent/tests/test_lifecycle_probe.py` checks Core package validation,
deterministic bytes, simulated ARMv6 install/restart/disable and rejection of
an invalid JSON health marker. This is not a real transport/Zero acceptance
test. Record the two real command IDs and outcomes after the browser test.
