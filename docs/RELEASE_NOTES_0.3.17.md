# Core 0.3.17

This maintenance update is for installations running 0.3.16. It does not
change command deadlines, approvals, the SQLite journal mode or the database
schema. No application or provider update is required.

- An idle Agent can check for work without Core starting a write solely to
  record a poll. Credential activity is recorded with the heartbeat; each
  request still checks the current credential.
- Opening Application access reads the effective rights; preparing a change
  remains a separate action. A read no longer reserves the review needed by
  an in-flight command. There is no automatic command replay.
- Settings loads operational panels when visited. Diagnostics shows recent
  failures first and offers detailed tools on demand. Its normal preview does
  not run an integrity scan on the live database.
- Device exchange and heartbeat errors can report the failed step, last
  confirmed step and measured duration. Unknown outcomes remain unknown.
  Clearing recent history requires administrator confirmation; audit records,
  command receipts and detailed recordings are not cleared.

Use the normal update workflow and keep a recovery file off-device. A successful
0.3.16 update preserves current application approvals. If the installer has to
restore the previous database during rollback, it restores the old release and
data but invalidates prior execution approvals. Review the affected application's
access before using it again; an unchanged user permission is not a new approval.
If an older admin tab still shows the previous interface, reload it; do not
repeat an unconfirmed command. This update does not install application
authoring tools or grant any new rights.
