# 3mm 0.3.12

This release organizes Core by domain and moves shared Python packages and
independent components into neutral `packages/` and `components/` directories.
Current imports, build tools, release inventories and official application
examples follow the new structure. Scoped obsolete paths are removed rather
than retained as old-import compatibility adapters.

## Installation and component transition

- Full and Node release payloads verify the complete installer, activation and
  component-transition source closure.
- The installer verifies existing independent component artifacts through the
  previous immutable release, prepares neutral replacements and preserves
  already-compatible selections.
- A protected installation journal retains exact original current/previous pin
  pairs. Failures restore those pairs before resuming the previous release.
  Disabled application hosts remain disabled; application packages, data and
  rights are not rewritten or approved.
- Rollback uses the previous release's own interpreter, activation file and
  readiness probe. A completed rollback retry requires the explicit
  `--retry-rolled-back` option; it does not clear an interrupted transition.

**One-time upgrade boundary:** the web updater and Node OTA validators published
in 0.3.11 require old source paths. They safely refuse this reorganized archive.
Use the verified console bootstrap described in
[Installation](https://github.com/ldobranov/3mm/blob/v0.3.12/docs/INSTALLATION_GUIDE.md#one-time-upgrade-to-the-neutral-source-layout)
for this transition after publication. Do not force the archive through an old
validator, edit an immutable release or reset the device to bypass the refusal.

Existing application wheels that import removed SDK paths need separate
adaptation. An incompatible previously active application causes installer
rollback instead of silently leaving it broken. Application and component
versions remain independent; this Core release does not publish or activate a
new Monitor, Child Center or Terminal package.

## Diagnostics and interactive sessions

- Bounded diagnostic cases identify browser/host/session startup and input
  acknowledgement stages without collecting terminal text, credentials or
  business request bodies.
- Interactive-session authority work no longer blocks unrelated Core event-loop
  work, and database snapshots end before notification waits. Current rights,
  revocation, cancellation and isolation checks remain enforced.
- Scoped session startup and early executor acknowledgement fixes are included.
  Remaining interactive latency is not claimed to be eliminated by this release.

## Verification limits

The exact release commit must pass main CI before its annotated tag is pushed.
The release workflow separately runs frontend, Python, SDK and deployment gates,
builds Full/ARMv6 Node assets twice, compares them and publishes only the complete
verified asset set. Local disposable upgrade/rollback checks are not installed
root/systemd or clean-card acceptance. C5 clean installation and real-device
transition acceptance remain separate checks against the published artifacts.

Keep a tested backup before upgrading. The published bootstrap preserves the
existing host-managed network by default; `-ap` explicitly requests managed setup
Wi-Fi. Installing the release does not grant application rights or enable I2C.
Previously saved application consent may resume physical output after services
reconnect; review that consent before an upgrade.
