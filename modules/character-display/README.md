# CAP14: profile-driven character display — mock and PCF8574T provider

This is a bounded display slice, **not physical I2C acceptance** and not
completion of all CAP14. The optional Agent provider uses the existing generic
command path. Core and applications do not open `/dev`; the native Agent child
opens only its bound I2C bus during an explicitly authorized frame. No scanning,
GPIO/network configuration or application-specific Core route is introduced.

Owner identified PCF8574T at `0x27`, I2C-1, SDA=GPIO2/physical pin3,
SCL=GPIO3/physical pin5. The supplied marketplace page could not be inspected.
LCD/backpack mapping and actual voltage/level shifting still require physical
confirmation. The native profile below is HD44780-compatible; do not infer that
every PCF8574T board has this wiring. There is no native-to-mock fallback. An
extra mock deployment is not a prerequisite for physical acceptance; automated
tests use memory/syscall/process doubles without hardware.

## Contract

### Optional local-clock scenes (contract 3.0, profile 3)

`builtin:display.character.scene.v1` is a separately reviewed Agent provider, not
an upgrade of static-frame consent. It keeps `write_frame` and adds `set_scene`
and `stop_scene` on the existing generic command path. No Core runtime change,
application-specific route, schema-dialect expansion or per-second RPC is used.

A scene carries exact ASCII base rows, profile identity, IANA timezone, scene ID,
strictly increasing sequence and an absolute `valid_until_ms` no more than 30
seconds ahead. `clock_fields` is a bounded JSON scalar (512 bytes, at most 32
tuples `[row,column,format_index,offset,length]`; formats 0=HH:MM, 1=HH:MM:SS,
2=DD.MM.YYYY). Only those nonoverlapping visible cell spans may change; the
application retains all template, market, clipping and OLD-marker logic.

After normal admission, Agent projects OS UTC into the selected zone locally,
aligned to seconds with no catch-up queue. The lease is also capped monotonically
so a wall-clock adjustment cannot lengthen it. Fresh normal authorization renews
the scene; a duplicate receipt never renews it. A higher scene sequence supersedes
an uncertain older desired state without replaying its original command. Stop
records a bounded tombstone against delayed older sequences and cancels ticks.
Disable, worker failure, replacement and Agent restart do not restore a scene.
Without renewal local ticking ends within 30 seconds; existing LCD text remains.
Accepted scene/last-write state is not optical readback of every future tick.

The native writer uses only its last acknowledged frame to update contiguous
dirty DDRAM spans. Identical frames do not open I²C; backlight-only changes write
one control byte. Failure invalidates that cache; recovery only prepares code.
Every byte retains the finite I/O and monotonic scene deadlines.

Build a distinct inert package with `--local-clock`, for example:

```powershell
& .\.venv\Scripts\python.exe modules/character-display/build_package.py `
  --local-clock --driver pcf8574 --columns 16 --rows 2 --bus 1 --address 0x27 `
  --output .runtime/cap14-clock/character-display-clock-16x2.zip
```

`tools.hardware_template_catalog.clock_documents()` supplies separate inert
admin-form templates gated by `display.character.scenes.v1`. Their data can be
uploaded through the existing template system; current Core need not interpret
clock fields or import a new driver. Disable the static provider before installing
its separately approved replacement. Application scene, Stop and manual-frame
rights are separate; packaging does not approve or activate any of them.

### Static-frame provider (contract 2.0)

- Capability `display.character`, version `2.0`, action `write_frame`.
- One fixed input schema for every geometry: display_id, profile_sha256, text,
  backlight. Text has newline-delimited printable-ASCII rows and a 512-character
  wire budget. The exact immutable profile declares columns/rows; shorter lines
  are space-padded. Oversize text, control characters, Unicode, raw bytes and
  caller-selected bus/address/path are rejected. No silent truncation or glyph
  substitution. Transliteration/formatting belongs to the application.
- Explicit Boolean backlight; no arbitrary LCD instructions or custom glyphs.
- The immutable package declares display ID, driver, LCD controller/pin mapping,
  backlight polarity, bus, 7-bit address, width and height. The frame includes
  the exact profile SHA-256; changes to the
  locator change the capability contract digest as well as the package digest.
  Mock and physical profiles have different identities, never reuse mock trust.
- The public SDK's existing command discovery now includes the bounded selected
  provider contract after M20 approval. State-schema singleton declarations expose
  exact columns, rows, display_id and profile_sha256; no bus scan or live state
  read is needed. Denied/revoked discovery reveals no selected resource/contract.
  Applications declare ONE frame binding with no per-size hashes or alternatives.
  M20 still pins the complete contract digest and package/provider identities.
- Core has no supported-size catalog. The common profile helper has bounded
  resource budgets (up to 80 columns / 4 rows). The current HD44780 driver alone
  validates its topology: two rows up to 40 columns, or standard split-bank four
  rows up to 20 columns. Width is a parameter, not a 16/20 whitelist. Unknown
  controllers/mappings are refused by the driver before I/O; they need an Agent
  driver, not extension-specific Core code. Mock supports the full wire budget.
- Mock result/state say `simulated: true`; native results say `false`.
  `has_frame: false` means there has been no completed write since activation,
  not an observed blank LCD.
  State is the last successful local write, not optical/electrical readback.
  `last_write_at` is that completion time (empty when no confirmed write);
  publishing a heartbeat/state snapshot does not refresh it. Physical content
  can remain after service/link loss; it has no automatic freshness guarantee.
- A new Agent starts without a frame; install, health/readiness, discovery,
  enable and restart do not restore a previously displayed frame.
  A native provider with an accessible bus preloads one private Agent worker
  during activation, without opening I2C. Subsequent authorized frames reuse
  that process so Python cold startup does not consume each command's lifetime.
  The worker is idle between frames; it has no saved-frame queue or automatic
  replay. Each write retains the original absolute command deadline and the
  bounded I/O budget. A failed write retires/fences that worker and leaves the
  original result unknown. After a ten-second minimum backoff and proof that
  the old child has exited, explicit Agent heartbeat maintenance may prepare a
  replacement process. Preparation never sends a frame or opens I2C; probes
  and validation remain non-mutating. No replacement is started over an
  unreaped/uninterruptible child. The next separately journaled and authorized
  command initializes the complete LCD with its new frame; the original failed
  command is never replayed. Missing hardware/rights still prevent execution.
  Close/disable is permanent for that service instance, unlike a worker fault.
- Driver errors invalidate local frame certainty. The existing physical-command
  journal returns `unknown` without automatic replay, including after a crash.
  A successful repeated request returns its historical result, not a new write
  and not proof that that frame is still displayed.

## Build an inert provider package

From the Core repository, in its existing Python environment:

```powershell
& .\.venv\Scripts\python.exe modules/character-display/build_package.py `
  --output .runtime/cap14-geometry/character-display-mock-v2-20x2.zip
```

For an inert native package, use a different output path and `--driver pcf8574`:

```powershell
& .\.venv\Scripts\python.exe modules/character-display/build_package.py `
  --driver pcf8574 --bus 1 --address 0x27 --columns 16 --rows 2 `
  --output .runtime/cap14-geometry/character-display-pcf8574-v2-16x2.zip
```

The builder validates the manifest and emits package/profile SHA-256. It installs/activates
nothing. Two files only: the manifest and inert package health marker. It refuses
to overwrite an output path containing different bytes. The ZIP is not bundled
or enabled automatically with Core. The example bus=1/address=0x27 are declared
locators, not evidence of a detected device. `--columns 16 --rows 2` creates a native
16x2 profile. Profile schema 2 and command contract 2.0 are an explicit prototype
break: neither default geometry nor an old file name preserves old package bytes.
Use a distinct output filename (for example character-display-pcf8574-16x2-1.0.0.zip).
`--columns`, `--rows`, `--bus`, `--address` and
`--display-id` create a different exact profile/package.
The module ID includes the complete profile digest, so two hardware profiles do
not overwrite the same immutable module/version. Disable/remove the old provider
before selecting another: simultaneous providers of `display.character` are a
registry conflict, not permission to choose one arbitrarily.

On 2026-10-31 the owner corrected the actual LCD identification to **16x2**.
The earlier visible two-line test used strings shorter than 16 characters and
therefore proved writing, not 20-column hardware. Do not reinterpret the approved
20x2 profile as 16x2. After software delivery, disable the old provider, review
and install the new exact 16x2 profile, then separately review the application
binding. This documentation does not install, stop or write to either provider.

## Agent and authority boundary

The updated Agent provides trusted entrypoint `builtin:display.character.v1`.
Native installation requires explicit administrator consent bound to the device
ID, package SHA-256 and profile SHA-256. Both Core and Agent check this before
activation; an environment flag cannot replace it. Hardware consent is distinct
from an application's M20 resource approval; neither grants the other. Native execution additionally
requires the Agent's `native` hardware profile, never a mock Agent. An unavailable
display must not prevent the Agent/Core from being administrable. The optional
provider is installed through the normal Agent module lifecycle, not as a
Core-hosted application. Provider permission is `hardware.display`, **not raw
I2C access for a consuming application**.

Core's validator and the independent Agent must both contain this slice. A
Core-only deployment does not update a pinned Agent artifact. No deployment,
environment/service/group change is performed here.
The old display environment opt-in keys are no longer used or copied into
Agent's filtered environment. Consent is stored with the exact installed module
and checked against device identity and manifest again at Agent startup. A new
installation needs explicit consent again; disabling the provider prevents
startup and new invocations, without clearing a physical LCD.

### Reviewed installation through Devices

Use **Devices → Hardware providers** on the selected device. **Configure a
supported provider** offers the installed HD44780/PCF8574T driver and a simulation
template. Set the actual display ID, columns/rows, bus/address and backlight
polarity, then **Prepare provider**. The administrator need not generate or
transfer a ZIP: the server prepares the same deterministic data-only package
using the shared builder and the normal immutable catalog. This step neither
approves nor installs a provider, changes app rights, scans the bus or writes a
frame. Preparation is repeatable for the same settings without a device command.
Arbitrary drivers, code, manifests, permissions and paths are not template input.
Driver topology validation still applies; the width is not a 16/20 whitelist.

The prepared package appears in the existing catalog and Extensions inventory,
including normal deletion/removal controls. Changing settings creates a different
immutable profile; it does not silently rewrite an installed provider or move an
application's approval. Disable the previous display provider before installing
its replacement, then separately review the consuming application's binding.
An existing ZIP can still be uploaded under the collapsed **Advanced** option.
Inspect the selected device, package/profile digests and full configuration
before proceeding. Preparation, upload and inspection do not touch hardware.
The Agent must advertise `module_hardware_profiles.v1`; old/unadvertised Agent
support is refused for native installation, not guessed from the Core version.

**Review profile and installation** opens a separate confirmation. It starts
unchecked. Confirming explicitly approves the displayed native profile and
queues normal installation/activation; it does not send a frame, reboot the
device, grant application access or claim physical wiring was verified. Preserve
the request ID. Refresh reads the existing installation receipt; no automatic
retry or replacement request is sent after an uncertain outcome. Reported
installation success is not a live LCD readback; inspect capability availability
before a separate first-frame test. **Disable provider** uses the existing
module lifecycle and requires its own confirmation. No Core route names a
particular display/application module.

The normal module install API accepts an explicit body for native packages:

```json
{"hardware_profile_approval":{"schema_version":1,"device_id":"dev_<32 hex>","package_sha256":"<64 hex>","profile_sha256":"<64 hex>"}}
```

Use a preserved `Idempotency-Key`. Missing, stale/wrong-device or changed-package
consent is refused before queueing/activation. No database migration or global
hardware permission is introduced. The existing package bytes/profile do not
change merely because this administrative delivery path is added.

### Native execution

Supported mapping only: PCF8574T P0=RS, P1=RW (always low), P2=E, P3=backlight,
P4..P7=LCD D4..D7; default backlight active-high. Addresses `0x20..0x27` only,
not PCF8574A at `0x38..0x3f`. Controller must be HD44780-compatible, with 20-column
rows at DDRAM `0x00`/`0x40`. Other pin maps/controllers need a deliberate profile,
not application-supplied raw I/O.
The host bus must satisfy the PCF8574T's Standard-mode limit (100kHz); this driver
does not silently change the bus speed. The child is a failure/deadline boundary,
not a new sandbox or proof of isolation of reviewed-native application code.

Activation/readiness do no I2C transactions. Native availability checks only that
the bound `/dev/i2c-N` is a writable character device, not whether an LCD exists.
A write runs in a standard-library-only child from the same immutable Agent code
(also inside `service.pyz`), without shell/application paths. It uses `I2C_SLAVE`
(never FORCE), single-byte writes and no adapter-wide timeout/retry changes.
First write initializes four-bit mode and clears the LCD; later successful writes
replace both padded rows without clearing/reinitializing. A power-cycled LCD
requires a fresh provider activation before the next explicit frame. Close does
not clear the physical display or change backlight.

The child has at most three seconds, shortened by the command's authoritative
deadline; expiry is checked before device access and before every byte. On timeout
the parent kills it and waits at most another 0.2s. A per-bus/address file lock
in the configured Agent data root fences its concurrent workers, including an
old child stuck in kernel I/O. This is a cooperative lock, not exclusion of
unrelated I2C tools/other Agent roots; do not run another writer. The
provider fails closed after driver failure. This does not make kernel I/O or
a partial frame electrically atomic: an error/timeout means unknown, never
permission to replay automatically.

The OS must already enable the chosen bus and permit the non-root Agent service
user to write that device. Do not run Agent as root or make devices world-writable.
Device group/service access is a separate, explicit hardware preparation step.

Consumers use the existing `capabilities.invoke` / M20 command bindings and SDK,
not the Agent HTTP diagnostics API. Declare a `command_bindings` item with:

```text
binding_id: display
target_device_config_key: DISPLAY_DEVICE_ID
capability_id: display.character
contract_version: 2.0
action: write_frame
arguments_schema: the exact write_frame arguments_schema in the provider contract
max_ttl_seconds: 10
```

Bind configuration to the selected managed device. Review/approve/apply its exact
current M20 resource rights separately. Discovery is not consent; activation is
not a grant. Bus/address/backlight fields already saved by Crypto Monitor do not
authorize writes or configure Agent hardware. Crypto Monitor integration remains
a separate change in that application's repository; it is not silently modified
by this Core slice.

Existing SDK calls (persist the original request ID before submission):

```python
context.platform.discover_command("display")
context.platform.submit_command(
    "display", request_id=original_request_id, ttl_seconds=5,
    arguments={"display_id": reviewed_display_id,
               "profile_sha256": reviewed_profile_sha256,
               "text": "BTC/USD\n123.45", "backlight": True},
)
context.platform.command_lookup(binding_id="display", request_id=original_request_id)
```

`queued` does not prove a frame was written. Use lookup/status and preserve an
unconfirmed request ID; do not resubmit it under a replacement ID. Expiry,
revocation and unavailable live execution permission must prevent the driver call.
There are no new privileges, automatic resource grants or permission bypasses.

## Owner checks

Run the existing `tools/dev_lab.py` profile `cap14-display` in an unprivileged
Linux/WSL source snapshot. It covers the frame contract, normal package validator,
Agent activation/readiness, actual command dispatch with live-permit doubles,
expiry/denial/offline, local native opt-in, LCD encoding/syscall/process doubles,
deadline/lock fencing, idempotency/conflicts, unknown outcomes and existing generic
M20 authority/rebinding/recovery regressions plus the standalone Agent artifact.
No frontend build, I2C device access, service restart or deployment is needed.
These checks are prepared, **not run by the agent**. They do not test Crypto
Monitor or physically prove a PCF8574T/LCD pairing.

## Before a real display write

Confirm LCD controller/backpack mapping, I2C bus/address, voltage/level shifting
and the chosen service identity's device access. Do not enable a bus or run a
scan as part of application activation. Raspberry Pi GPIO uses 3.3V logic;
do not assume a 5V backpack has safe SDA/SCL pull-ups. Sources:
[Raspberry Pi GPIO](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio),
[PCF8574/PCF8574A datasheet](https://www.nxp.com/docs/en/data-sheet/PCF8574_PCF8574A.pdf).

Native timing/encoding references:
[HD44780U datasheet](https://support.newhavendisplay.com/hc/en-us/article_attachments/4414500986647),
[standard character-panel DDRAM layouts](https://orientdisplay.com/knowledge-base/reference/standard-character-lcd-configurations/),
[Linux I2C interface](https://www.kernel.org/doc/html/latest/i2c/dev-interface.html).
Run the character-display, hardware-profile and hardware-interface tests on
Linux, and the hardware-panel component tests in the frontend workspace. The
software checks do not need a physical display. A Core-only deployment does not
update the independent Agent: use a compatible Agent before testing on hardware.
Button press events and long-press Wi-Fi/AP/application reset authority are
separate capabilities; a display grant must not authorize them. No shell,
network-reset, Core factory reset or unrestricted device operations belong here.
This is a discrete-command interface, not a frame stream or autonomous local
clock workload. Update cadence, queue backpressure and command-history retention
must be addressed during application/workload integration before sustained
high-frequency refreshes are claimed as accepted.
