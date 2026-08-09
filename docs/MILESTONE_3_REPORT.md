# Milestone 3 Report

Date: 2026-08-09  
Baseline: Raspberry Pi `rasp-3mm` (`192.168.1.88`)  
Accepted release: `423cfed-m3-final`

## Result

Milestone 3 is complete. Core-to-Agent operations now have persisted desired and
reported state, an expiring idempotent command queue, structured results,
redelivery, a persistent offline outbox, and an administrator diagnostics view.

## Physical acceptance evidence

- Core downtime buffered the Agent heartbeat in
  `/var/lib/3mm/agent/outbox.json` with mode `0600`; reconnect replayed it and
  emptied the outbox.
- Revoking the active credential caused authenticated Agent requests to return
  `401 Unauthorized`.
- Controlled credential replacement retained device identity
  `dev_a3ad5f8844f1466f847f5f8cf78d6fe3`; the replacement file remained owned
  by `3mm:3mm` with mode `0600`.
- After Agent restart, Core accepted the next heartbeat with `202 Accepted` and
  the queued event was removed.
- Core, Agent and Web remained active; Core readiness and Agent health returned
  successful responses.
- The focused acceptance suite passed: 21 tests covering offline replay,
  pairing and credential lifecycle, reliable commands, and desired state.

Duplicate command execution, command expiry, redelivery, and desired/reported
reconciliation are covered by the automated suite and were also exercised in
the preceding physical command/state slices.

## Operational boundaries retained

- NetworkManager was not changed.
- The Agent listener remains bound to `127.0.0.1`; Core and Web retain their
  approved LAN listeners.
- No password or credential secret is stored in Git.
- Credential replacement is audited and does not delete device history.

The next roadmap work starts at Milestone 4: Module manifest v2 and runtime
lifecycle.
