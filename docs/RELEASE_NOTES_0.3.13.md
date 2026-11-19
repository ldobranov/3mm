# Core 0.3.13 — Standalone recovery and diagnostics

This release closes CAP19 for the supported Standalone profile: a trusted-LAN
Full installation on Raspberry Pi (aarch64) with reviewed native applications.
It includes the Core and admin Web changes verified on the restored Pi, including
the previously accepted application resource limits. It does not release new
versions of the independently maintained applications.

## What changes for an operator

- Backup readiness distinguishes recoverable packages from blocked or separately
  prepared ones. Check a portable export offline without importing it. On
  restore, application package references are resolved on the destination.
  A recovered interface may require new approval; restoring data does not
  itself issue grants.
- Inspect a selected application's package, resource limits and original
  work references without SSH. Distinguish a Core offer, a receipt and proof
  of physical execution. Diagnostics do not submit work or expose application
  payloads. Missing Linux resource measurements are shown as unavailable.
- Core uses indexed lookups for command submission and delivery. The recovery
  fence for a dispatched physical command remains in place: the original
  Agent receipt can now be acknowledged without replay or a change of rights.
- The optional Public Web listener no longer introduces a service-ordering
  cycle on startup.

## Acceptance and limits

The owner recovered the downloaded Standalone backup on a fresh SD card.
Core and Agent reconnected with the original device identity. The application
packages and databases were checked, including saved Monitor records.
After the receipt correction, the Agent's pending reports drained without
manually clearing its queue. One old delivery stayed one delivery.

Recovery is not evidence of an operation on physical hardware, erasure of
external copies, or automatic recovery of separately provisioned relational
applications. This release does not add remote pairing, cloud sync, or a
different hardware acceptance profile.

Factory reset is a separate operation: its implementation is unchanged from
0.3.12, including its first-login limitation. Do not use it to rehearse
recovery or expose a just-reset device to an untrusted network. Use a fresh
OS card and the normal Standalone Setup and restore-from-file flow instead.
