# Next-release local Terminal acceptance

Scope: one Core/Standalone or VM-Hub's **own local Linux**, using the existing
M20 service AND human authority. This is an experimental, restricted temporary
workspace, not `raspberry`/root host administration. No SSH, Node transport or
Cloud relay is enabled. M20/WP4 is separately
[functionally accepted](EXTENSION_PLATFORM_V2_WP4_FINAL_ACCEPTANCE.md); this
procedure does not close M21 or claim physical acceptance.

Prepared return-test pairing: **Core 0.3.0-beta.56 + Terminal 1.0.2**. Beta.55
introduced the declaration/host/worker profile, but its installed trial stopped
after Connected. Beta.56 repairs a reproducible worker scheduling/cleanup race;
the original VM exception was not captured, so the return test remains required.
Use beta.56 only after actual publication/update. Manifest v2 encodes only a
coarse `>=0.3.0` Core floor, not a Beta-number requirement. Older parsers refuse
the new fields, and a missing/disabled runtime grants no access.

## Release contents

Ship Core's current local-session sources, `websockets==17.2`, bounded uvicorn
WebSocket settings, and both `3mm-session-worker` systemd units. The installer
installs the optional definitions but does not enable the feature or approve
rights. Keep the old generic `/interactive-sessions` prototype router absent.
The minimal Node package must remain independent of Core/SDK/WebSocket extras.

This Core-only correction does not change Terminal 1.0.2. Keep its existing exact
ZIP/compiled UI, configuration and current reviews/grants; do not rebuild or
replace published package bytes just to test the Core repair. An existing
unchanged installation starts at the return-test section below. A fresh install
still needs steps 1–6 and exact local trust/rights; the old 1.0.0 ZIP is not this
profile. Neither Core's update nor this document repairs fenced authority.

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
3. For a fresh installation, upload/install Terminal 1.0.2, initially disabled.
   Set its saved
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

## Beta.56 return test

This is the next bounded installed acceptance gate, not a repeat of accepted
WP4 scenarios. Use the updated VM's own local device and unchanged Terminal
1.0.2. Preserve the independent Hub snapshot and leave the other WSL installation
stopped while the Hub owns ports 80/8887/8890.

1. Independently confirm `/opt/3mm/current/VERSION` is `0.3.0-beta.56`, the four
   base services and optional session socket are active, and Core is ready.
   Confirm both current service rights and the test user's `terminal_use`.
2. Refresh the Terminal page/access. Click Connect once, retain request/session
   IDs, and wait for the prompt **before** sending input. Connected alone is not
   a pass. No reinstall, new package version or review-key recovery is expected.
3. Run `pwd`, `id`, `ls`, then `printf 'M21_OK\n'` and
   `sleep 2; printf 'M21_DELAYED_OK\n'`. Require prompt/output and continuing
   independent delayed output, without disconnect or automatic input retry.
4. Resize the browser/container, run `stty size`, and require the PTY dimensions
   to follow the fitted screen. Opening still uses the reviewed 80x24 options.
5. Disconnect once and verify no owned `3mm-session-worker@*.service` remains
   running. Retain the session lifecycle close/cleanup result. Only after
   confirmed cleanup, explicitly Connect once more to prove the capacity was
   released, then Disconnect and confirm cleanup again.

If any step fails, stop without replaying the uncertain input. Preserve IDs,
observed time and the named worker unit. Core's new phase/category warnings and
metadata-only lifecycle audit help locate the failure; do not paste environment
files, credentials or terminal contents containing private data. Unknown cleanup
must remain fenced rather than being cleared to make a subsequent Connect work.

A pass accepts this local Terminal path only. Remote Node/Cloud and broader M21
completion remain separate. The existing denial/revocation checks above remain
the process-profile reference; a local fixture result never substitutes for OS
proof or permits weakening those checks.

## Still separate

Full release CI, actual installed-VM acceptance, Node/Zero resource/reconnect
acceptance, remote/cloud delegation, cross-application provider trust,
attach/detach and unrestricted maintenance sessions are not claimed by local
tests. One extension/SDK contract remains the design for every future route.
