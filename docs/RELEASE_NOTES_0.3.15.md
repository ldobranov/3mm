# Core 0.3.15

**Update directly from 0.3.13.** The v0.3.14 tag was a release candidate;
no installation packages were published for it.

- **CAP16: reviewed status reports.** The sending and receiving installations
  each approve the exchange in Extensions → Application access. An update
  grants no new access. After an interruption the queue uses the original
  delivery ID; a lost reply is not success, and reconnecting does not restore
  revoked permission. This covers status reports, not general synchronization
  or remote commands. See the [operator guide](INSTALLATION_PEER_V2.md#reviewed-status-report-exchange-cap16).
- **First login after Factory reset.** Full Setup starts with no accounts.
  On a trusted LAN, choose the administrator's email and password in Setup
  and use them for the first login. An ordinary upgrade does not reset any
  accounts or passwords. See the [older-version precautions](DEVICE_ADMINISTRATION.md#factory-reset).
- **Refused SQLite migrations leave the database unchanged.** On refusal,
  the whole migration rolls back, including schema, data, revision, queued
  events and permission history.

Keep a verified recovery file off the device before upgrading. Installer
rollback needs the previous release **and its matching database and
configuration**; changing the release pointer alone is not a rollback.
Changes made after the snapshot do not return with it. Independently
installed applications and Agent updates are outside this release.
