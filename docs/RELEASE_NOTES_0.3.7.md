# 3mm 0.3.7

## Independent components through Updates

Updates now manages the local Agent and one explicitly selected application
host alongside the existing Platform Runtime controls. Prepare from the installed
immutable Core, review the exact target/build, then separately confirm an update,
previous-build rollback or recovery of an interrupted operation.

Local preparation reuses the selected native component's verified interpreter
and vendor dependencies. It performs no download or dependency installation.
Changed locks require separate compatible dependency delivery; preparation does
not silently modify Core or the existing native artifact.

Only the selected component restarts. Core and Runtime stay running; default and
other application-host pins, application packages, data and rights are unchanged.
Agent restart briefly interrupts its capabilities. Existing persistent application
consent may resume hardware output on reconnection; these controls do not grant
access or invoke application Start/Send operations.

Unknown outcomes retain the original identity and are resolved by reading status
or explicitly reviewing recovery, never by automatic mutation replay. A proven
pre-acceptance refusal is distinguished from lost persistence/scheduling replies.

Remote Node controls reuse signed, published ARMv6 Node OTA packages, including
Agent and Node service files. They retain pinned Hub trust, freshness, conflicting
command, maintenance-window, current-administrator and installation/rollback checks.
No catalog request or update occurs merely by opening the page. Other architectures
are not inferred from the local Agent builder. Real remote-device update acceptance
is deferred; no enrolled Node was available during this release's local trial.

## Configure supported hardware providers in administration

Devices -> Hardware providers offers the installed PCF8574T/HD44780 character-
display driver and simulation. Choose actual geometry, display ID, bus, address
and backlight polarity, then prepare the immutable package directly in the catalog.
There is no need to generate and transfer a local ZIP for this supported path.

Preparation does not install, approve access, enable I2C, reboot, scan the bus or
write a frame. Review the exact device/package/profile before installation and
separately approve a consuming application's resource. Changed settings create a
different profile; existing installations and bindings are not silently rewritten.
ZIP upload remains under Advanced. Normal inventory and removal controls remain.

## Language and acceptance

- Bundles Bulgarian 1.0.6. A previously selected language package is retained;
  choose the new version explicitly in administration when desired.
- Local Raspberry trials verified preparation, update and manual rollback for
  both Agent and one application host, with Core PID continuity, unchanged other
  pins and unchanged application active metadata. Trial component currents were
  deliberately returned to the inspected working originals afterward.
- Real systemd checks verified that the helper can read local Agent readiness
  while non-local IP traffic remains denied.
- An initial trial host update failed and safely restored the previous healthy
  build. Its original cause was not retained; a fresh request under the final
  trial Core succeeded. Bounded failure-location logging is now available if it
  recurs. This is not a claim that every startup/performance profile is accepted.

Core, SDK/protocol, language and application versions remain independent. Native
reviewed code is not a universal sandbox. This release does not expand application
privileges, automatically repin existing hosts, complete remote Node acceptance,
or change Crypto Monitor's application version. Preserve database/key backups;
changing a Core pointer alone does not restore data or independent components.
