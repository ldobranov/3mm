# Output button / command probe

Independent Manifest-v2 application: one operator page and one SDK command binding.
The wheel reuses `examples/command_probe` and imports only the public application
SDK. It has no administrator device APIs, raw HTTP, browser credential access,
connector, scheduler, provider implementation or global device inventory.

The administrator selects `OUTPUT_DEVICE_ID` during installation and approves
`command:output` through normal Application access. The binding requests version
1.0 of `gpio.digital.control.set_output`, with channel `gpio.output.1` and a boolean
value. Core's existing contract matcher requires the exact argument schema.
Assign `control_output` through the existing application permission controls to
each normal user who should open the operator route `/output-button`.

Commands use a browser request UUID saved before the single dispatch. The service
namespaces that UUID by the authenticated user supplied by Core; another user's
lookup cannot read its receipt. Only the exact selected resource is discovered.
Queued work is pending until the Agent confirms it. Lost replies, reload and
restart use `lookup`, never a new command or an automatic mutation retry. Uncertain
or failed outcomes keep controls blocked until explicit review of the original
device. The displayed value is a command result, not continuously observed GPIO
state; Fleet or another client can change the resource afterwards.

## Build and checks

From the repository root:

```text
python modules/command-probe/build_package.py --output modules/command-probe/dist/output-button-0.1.0.zip
python -m pytest -q backend/tests/test_command_probe_application.py
node frontend/node_modules/vitest/vitest.mjs run --config modules/command-probe/tests/vitest.config.mjs
```

Set `THREE_MM_FRONTEND_DIR` if the existing Core toolchain is elsewhere. No second
Vue installation or new Core frontend build is required. The package compiler
builds its UI during upload. Initial local package version: 0.1.0; not published.

Linux acceptance covers the actual ZIP/compiler/native loader, an ordinary user
through Core's operator gateway, a separate Runtime with signed SDK requests,
real command queue/one-use permits/journals and real AgentModuleRuntime mock
outputs. Two registry profiles (`native` and `embedded_firmware`) execute the same
binding after explicit administrator resource replacement, with the exact same
application package. The test simulates the helper's external systemd start and
response peer while retaining Core's lifecycle fencing and signed result checks.

Owner WSL acceptance additionally installs this exact package through normal
Core upload/activation/consent APIs and exercises the existing `agent_module`
Digital GPIO Output 1.1.0 provider. ON/OFF, actual application systemd restart,
read-only result recovery, resource revocation without queueing and fresh consent
pass. The owner administrator uses the operator route; the separate Linux test
proves the ordinary-user permission gate. The VM is left ready with output OFF.
The second-provider replacement is verified in isolated acceptance, not by adding
a fabricated second device to the owner's registry. No physical GPIO acceptance,
new Core mechanism, database migration, publication or source commit is claimed.
