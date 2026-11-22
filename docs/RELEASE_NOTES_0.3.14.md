# Core 0.3.14

**CAP16 is closed for reviewed status reports.** Both installations approve
the exchange independently. In Extensions → Application access the sender
reviews its outgoing report and the receiver reviews the incoming request.
Upgrading does not approve existing links. A bounded application-owned queue
retains the original identity and sequence across interruption; a lost reply
is not success, and reconnection cannot revive withdrawn authority. See the
[operator guide](INSTALLATION_PEER_V2.md#reviewed-status-report-exchange-cap16).
This is not general data synchronization, remote control or automatic pairing.

**First login after Factory reset.** On a trusted LAN, complete Full Setup and
sign in with the email and password you chose. Reset starts with no users.
An ordinary update is not a reset: it does not change passwords or remove
existing accounts, including any development account from an older installation.
See the [older-version precautions](DEVICE_ADMINISTRATION.md#factory-reset).

**Updating from 0.3.13.** Keep a verified recovery file off the device. The
update includes a database migration for sender consent. Do not downgrade by
moving the release pointer alone: a rollback needs the previous release and
its matching pre-update database and configuration. Changes made after the
snapshot do not go back with it. Rollback invalidates authority that requires
fresh review.

**Refused database migrations.** If any step of a SQLite upgrade or downgrade
refuses to run, the entire invocation rolls back. The starting schema,
revision, event queue and permission history are preserved. A successful
migration to an explicitly chosen intermediate revision still works. This
database guarantee is separate from the installer's release rollback.

Independently installed applications, their releases and Agent updates are
outside this release scope.
