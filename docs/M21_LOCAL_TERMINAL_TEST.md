# Next-release local Terminal acceptance

Scope: one Core/Standalone or VM-Hub's **own local Linux**, using the existing
M20 service AND human authority. This is an experimental, restricted temporary
workspace, not `raspberry`/root host administration. No SSH, Node transport or
Cloud relay is enabled. Neither M21/WP4 nor physical acceptance is closed here.

Prepared pairing: **Core 0.3.0-beta.55 + Terminal 1.0.2**. Use only after Core
publication/update, not the older installed beta.54. Manifest v2 encodes only a
coarse `>=0.3.0` Core floor, not a Beta-number requirement; this trial specifically
needs beta.55's session declaration/host/worker profile. Older parsers refuse the
new fields, and a missing/disabled runtime grants no access.

## Release contents

Ship Core's current local-session sources, `websockets==17.2`, bounded uvicorn
WebSocket settings, and both `3mm-session-worker` systemd units. The installer
installs the optional definitions but does not enable the feature or approve
rights. Keep the old generic `/interactive-sessions` prototype router absent.
The minimal Node package must remain independent of Core/SDK/WebSocket extras.

Build a new Terminal package from its checkout, including the provider factory
and current renderer. Use its normal **new immutable version**, not the old
`dist/3mm-terminal-1.0.0.zip`. Run its check-only builder/typecheck/tests before
publication. The ZIP and compiled UI have new hashes and require fresh review.
Keep the documented beta.55 minimum alongside the manifest's coarse Core floor;
do not claim that the manifest comparator distinguishes older 0.3.0 Betas.

## Owner steps AFTER updating the test VM

1. Take a recoverable VM snapshot/backup. Confirm the intended distribution,
   installed version, four base services and `/ready` responses. Do not run this
   on the owner Hub while another WSL distribution owns the same forwarded port.
2. In `/etc/3mm/3mm.env`, set `THREE_MM_LOCAL_SESSIONS=1`. Preserve every other
   setting and secret; do not paste the file into chat. Enable the optional socket
   and restart Core:

   ```sh
   sudo systemctl enable --now 3mm-session-worker.socket
   sudo systemctl restart 3mm-core
   systemctl is-active 3mm-core 3mm-session-worker.socket
   ```

   The environment must list the exact browser origin in existing `CORS_ORIGINS`
   / `FRONTEND_URL`; no wildcard, missing Origin or credential in a WebSocket URL.
   Unsupported systemd/kernel isolation fails closed; do not weaken the unit.
3. Upload/install the NEW Terminal package, initially disabled. Set its saved
   `SESSION_DEVICE_ID` to this installation's EXISTING local Agent `device_id`.
   The platform reads the local identity file; a remote Node ID cannot select
   a local shell. Do not change Linux identity, enrollment or pairing for this.
4. Build the package UI through normal Core administration. Review the exact
   source, service wheel and compiled UI; record local native/UI trust with the
   existing `application_authority_admin native-review` flow. Use actual current
   installation/package/build hashes, not IDs from the old WP4 test extension.
5. In Application access choose **only** the declared `session:console:open`
   resource, inspect its exact local device, provider/version, write mode,
   `resize`, and `cols=80, rows=24`. Review → Approve → Apply. Enable the app and
   create a fresh review/apply if lifecycle changed its authority baseline.
6. Separately assign the application's **human** `terminal_use` permission to
   the logged-in test user. Even a Core administrator needs this permission.
   The user must also satisfy the route audience: the current Terminal route is
   administrator-only, so use a test administrator for this first scenario.
   Refresh application access, then open Terminal and **Refresh access**.

No step above implicitly creates a review key or grants fallback rights. If a
key is missing/stale, use the existing explicit local Core administration flow.

## Observe and retain evidence

- Target is the exact saved local binding; Connect is enabled only with both
  current grants and the optional runtime. No fabricated `local` or SSH fallback.
- Connect once. Preserve request/session IDs. Prompt arrives before input.
- Try `pwd`, `id`, a short `printf`, delayed output, and terminal resize. Expect a
  temporary `/tmp/terminal-work-*` directory and a per-session dynamic UID, not
  `raspberry` or root. The workspace disappears on close; this is intentional.
- Resize the browser/container and use `stty size` to confirm the PTY follows
  the fitted screen, while opening still uses the reviewed 80x24 options. Paste
  text over 16 KiB only in the disposable scratch session, not host maintenance;
  check exact content and that input is never automatically resent on failure.
- Verify Core private paths/homes/Windows mounts and IPv4/IPv6 are inaccessible,
  and writes to the immutable release are refused. Do not copy secrets as probes.
- Remove the human permission while idle: output/input must stop and the worker
  cgroup must empty. Restore the human grant explicitly for a NEW session.
- Revoke the service grant while the human grant remains: same stop/refusal.
  Reapproval must not renew an old session. No automatic reconnect/input replay.
- Disconnect/close the tab; check no running `3mm-session-worker@*.service`
  remains. Core restart/update must stop owned workers; a new explicit session
  is required after login/authority checks. There are no durable PTY receipts.

If startup, input or cleanup is unconfirmed, preserve the IDs and inspect the
named unit/metadata audit. Do not retry input, manufacture a replacement request
ID or relax permissions/isolation to make Connect green.

To disable the experimental feature: remove/disable the environment flag,
restart Core and disable/stop `3mm-session-worker.socket`. Do not delete keys,
application data or permission history as cleanup. Rolling Core back to a version
without this descriptor/profile may leave Terminal unavailable, never privileged.

## Still separate

Full release CI, actual installed-VM acceptance, Node/Zero resource/reconnect
acceptance, remote/cloud delegation, cross-application provider trust,
attach/detach and unrestricted maintenance sessions are not claimed by local
tests. One extension/SDK contract remains the design for every future route.
