# Core 0.3.16

**Upgrade directly from 0.3.13.** Versions 0.3.14 and 0.3.15 were tagged
for testing, but neither published an installation package.

**CAP16: reviewed status reports.** In Extensions → Application access, the
sending and receiving installations each approve the exchange. No access is
granted on upgrade. If a connection breaks, the queue preserves the original
delivery ID; a missing reply is not success, and reconnecting does not
reinstate withdrawn access. This is status reporting, not general data sync
or remote control. See the [operator guide](INSTALLATION_PEER_V2.md#reviewed-status-report-exchange-cap16).

**First login after Factory reset.** Full Setup starts with no accounts.
On a trusted LAN, choose the administrator's email and password in Setup,
then sign in with those credentials. Ordinary upgrades preserve existing
accounts and passwords. See the [older-version precautions](DEVICE_ADMINISTRATION.md#factory-reset).

**Database and rollback.** If a SQLite migration refuses to run, the entire
migration rolls back, preserving the original schema, revision, data, queues
and permission history. Before upgrading, keep a verified recovery file off
the device. Installer rollback requires the previous release together with its
matching database and configuration. Changes made after that snapshot do not
return with it.

The release tests now isolate the test server's memory from the test runner.
The two-second command check and application permissions are unchanged.
Independently installed applications and Agent updates are outside this release.
