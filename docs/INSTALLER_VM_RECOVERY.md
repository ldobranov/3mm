# Installer — wired-only Linux / VM recovery

Local correction: 2026-10-03; not yet deployed or published by this task.

## Failure addressed

A Linux VM without Wi-Fi had no provisioning journal. The runtime planner chose
first-boot Setup AP, stopped Core/Web/Agent, then failed on missing `wlan0`.
Rollback repeated that plan. A missing `gpio` group also prevented Agent startup
because the installed service declares it as a supplementary group.

## New behavior

The existing one-command `install.sh` still selects verified published immutable
release assets. No Git checkout or new installer architecture is required.

- The Linux installer creates the `gpio` system group before service activation,
  including on hosts without GPIO hardware. New full installations default to the
  mock driver; upgrades preserve a selected driver.
- `three_mm_runtime.install_bootstrap --check-only` validates the persistent runtime
  plan before stopping existing services. Missing/corrupt/interrupted recovery,
  incompatible roles and unsupported Setup interfaces fail closed.
- With no wireless interface, a full-profile installation with an absent journal
  initializes secret-free Standalone provisioning after migration/default admin
  bootstrap. An existing database must already have an administrator. It does not
  change users/passwords. Existing role/journal/identity/credentials are preserved.
- Automatic AP recovery defaults off only when a wired-only policy file is absent.
  An explicit existing choice is not overwritten. No NetworkManager configuration
  is changed. A wired-only VM has no Setup AP to join.
- Existing activation creates/pairs a missing local Agent identity; the new
  installer helper does not require identity.json to exist beforehand.
- Raspberry first boot with `wlan0` keeps its current Setup AP flow. An unprovisioned
  Node without the supported Wi-Fi interface is rejected, not silently converted
  into a Standalone server.
- Activation checks the Setup interface before disabling application services.
  Success requires every selected service plus its existing endpoint health checks,
  not merely a healthy Core while Agent continually restarts.
- Failed upgrade rollback restores the previous release, database/environment and
  captured active/enabled runtime units instead of repeating a broken Setup plan.
  Previous endpoints are checked; an unhealthy rollback is reported explicitly.

The full-profile preflight now accepts `x86_64` and wired-only NetworkManager
hosts without a `wlan0`; a present alternative Wi-Fi interface is not misrepresented
as supported AP hardware. Existing Python/systemd/dependency checks still apply.

## Validation and remaining live gate

Focused tests cover missing journal, read-only preflight, idempotency, preserved
role/policy, interrupted/corrupt state, Node and interface rejection, service
selection, shell syntax, rollback order and release packaging. Windows shell tests
pass LF bytes to Bash rather than accidentally converting stdin to CRLF.

The user's manual beta.33 VM recovery demonstrated healthy Core/Agent/Web, but
did not exercise this new installer code. After a release containing these changes,
verify a clean wired-only VM and a failed upgrade rollback, then confirm provisioned
Hub/Zero identity and pairing are unchanged. Do not use a Master reset as an OTA test.

## Browser-origin recovery — 2026-10-07

On the existing WSL host, the beta.42 console installation completed successfully:
Core, Agent, Web and the update helper were active. Browser preflight requests
from `http://localhost` returned HTTP 400 `Disallowed CORS origin`, while requests
from the configured WSL IP returned 200. The old installer replaced
`CORS_ORIGINS` with LAN/mDNS addresses and omitted local browser origins.

The new full-profile installer uses the bounded stdlib `frontend_access` policy
to preserve custom allowed origins and include localhost/127.0.0.1 on ports
80 and 8080. Invalid/wildcard policy entries fail before services stop. Console
bootstrap keeps the saved frontend URL unless explicitly overridden; UI update
already passes the configured URL to the verified target installer. New-release
CORS health checks run only when Core is active, not during Setup-only first boot
or when restoring an older rollback release. Node environment behavior is unchanged.

Live recovery changed only `/etc/3mm/3mm.env` after a root-only 0600 backup, then
restarted Core. Windows localhost preflight now returns 200 with the expected
allow-origin header. Configured LAN access still works; an untrusted origin still
returns 400. Core/Agent readiness passed and the immutable beta.42 release pointer
and local Agent identity were unchanged. No database, users, extension packages,
provisioning or network configuration was reset or rewritten.

Focused automated checks cover clean origin generation, console URL preservation
and explicit overrides, UI worker argument preservation, safe policy merging,
environment injection rejection, bounds, Node isolation, shell syntax, browser
health failures and target artifact packaging. This is not a live clean install
or an end-to-end UI update of the new unpublished source. Publish a subsequent
release before exercising that flow; do not reinstall beta.42 as a durability test
because that older artifact still has its original overwrite policy.
