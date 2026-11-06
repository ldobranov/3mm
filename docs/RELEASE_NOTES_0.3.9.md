# 3mm 0.3.9

- **Clean installs:** Setup now assigns the first administrator a stable user
  subject when creating the account. This prevents successful logins from
  immediately failing session refresh and application access. The fix applies
  to fresh Standalone and Hub setup, including Raspberry Pi Zero W. It does not
  backfill or change existing accounts. The fresh-database login flow passed
  automated checks; a clean Zero W card with this exact release remains to be
  tested.
- **Resource limits:** `python -m tools.application_resource_report` reports
  application-host limits from the running Linux cgroup. The full-profile
  Raspberry Pi preflight warns if it cannot verify cgroup v2 memory support.
  It does not enable memory control or change boot settings. A separate
  disposable service on Pi 3B+ verified memory-limit isolation without
  restarting Core or running applications.
- **Webhooks:** A reviewed loopback pilot exercises signed ingress, durable
  receipts and one-shot delivery. It does not enable a production webhook
  endpoint, start a background consumer or retry an unconfirmed delivery.

Keep a tested backup before upgrading. ARMv6 Hub and Node still have separate
artifacts and catalogs. Bulgarian language pack 1.0.6, Device Protocol 1.0 and
Application SDK 1.3 retain their independent versions.
