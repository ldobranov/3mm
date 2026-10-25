# Next-release local Terminal acceptance

The separate [common platform continuation](#common-platform-continuation--2026-10-25)
now passes the selected physical Node/local-relay gate with an independent SDK
probe. The accepted local Terminal baseline below is unchanged.

Current continuation, 2026-10-24: Terminal 1.0.3 passes the installed Ubuntu
browser gate with local Core terminal-ui-snapshot-20261024 (beta.56 plus the
three UI snapshot files). Prompt, commands, delayed output, resize, explicit
close/worker cleanup and owner fresh connection are confirmed. 97 direct Linux
UI/auth/session checks pass; unchanged 41 frontend/TypeScript/compiler and private
PTY/M20 evidence is reused. This accepts the restricted VM-local profile only.

rasp-3mm physical Pi 3B+ now passes the installed browser gate too. Terminal
1.0.3 installation 1 is active with the optional local-session flag/socket,
exact native/UI review, its own console resource and user 1 terminal_use.
The helper first-install write-boundary fix remains in place (5 scoped checks).
Its local Core terminal-authority-20261024 is beta.57 plus two output files:
current-authority I/O now has a separate bounded 5-second deadline, while idle
polling stays at 1 second. Real Pi contention reproduced the old false timeout;
two regressions fail before the repair, then 127 targeted Linux tests pass.
Actual Pi prompt, commands, delayed output, resize 24x158 -> 23x116, private-path
and immutable-write refusal, IPv4/IPv6 refusal, both human/service revocation,
fresh sessions and normal Disconnect/worker cleanup are confirmed. Final rights
are effective, no workers remain and the verification login is closed. Exact
artifacts, reviews, evidence and rollback base are recorded in WORKING_STATE.
Existing Terminal ZIP/wheel/UI bytes are unchanged; 41 frontend tests,
TypeScript/compiler and earlier PTY/M20 evidence are reused for those inputs.

After forced close/revocation the current browser adapter intentionally fences
another Connect with unconfirmed, even if Refresh access succeeds. First confirm
owned worker/cgroup cleanup and restore the exact required rights; explicitly
reload the page, then Connect once for a NEW session. Never reuse the old
request/session or replay uncertain input. A normal acknowledged Disconnect
releases its session without this forced-close barrier.

The beta.56/1.0.2 instructions below are historical reference. Use actual current
identities, packages and reviewed fixes; never copy IDs from another device.

Scope: one Core/Standalone or VM-Hub's **own local Linux**, using the existing
M20 service AND human authority. This is an experimental, restricted temporary
workspace, not `raspberry`/root host administration. No SSH, Node transport or
Cloud relay is enabled by this local procedure. M20/WP4 is separately
[functionally accepted](EXTENSION_PLATFORM_V2_WP4_FINAL_ACCEPTANCE.md); this
procedure does not close M21 or claim remote Node/Cloud acceptance.

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

## Common platform continuation — 2026-10-25

The owner selected the common execution boundary, real paired Node and a local
relay. This is platform work behind the same public SDK/session host; Terminal's
package/UI is unchanged. The independent SDK probe passes normal physical Zero W
sessions directly and through the local relay, plus relay failure/recovery,
human/service revocation, Node restart and pending-startup revocation. This does
not claim installed remote Terminal UI acceptance or the complete M21 gate.

The trusted runtime directory resolves one exact reviewed source. Missing or
ambiguous runtime offers refuse execution, with no automatic local/SSH fallback.
Fixed root-owned remote routes and the current registry bind the exact device,
provider/version, wheel digest and certificate to the reviewed resource. Node TLS
uses the existing paired Hub installation identity. Each session retains the
same current native/UI review, M20 service resource and tracked human permission;
connectivity and fresh Agent support are not grants. Node execution uses its own
optional component and the same restricted OS worker profile, without Core code
or a database on the Node.

The separate local relay binds loopback and forwards encrypted bytes to one
configured Node. TLS remains end to end between Hub and Node; the relay stores
no identity keys or device credentials and performs no command execution,
reconnect or input replay. Root routes can change for new requests without a
Core restart; existing sessions stay pinned and stop on currentness drift.

The Zero W needed about 37 seconds for a cold import under its CPU limit. Startup
has separate bounds of 90 seconds for worker ready, 95 for Node open, 100 for
remote ready, 110 for Core and 120 for browser opening. The relay allows 120
seconds between encrypted reads during this cold start. Core continues the same
live authority checks while open is pending and cancels/joins it before cleanup
on denial or timeout. Node pre-ready EOF, unexpected input or currentness drift
also cancels/joins startup; its watcher is removed before normal stream reads.
Only browser opening changed; the existing 10-second input/control/close
acknowledgment deadlines remain unchanged.

For a failed/finalized session, a current tracked administrator can inspect
session-recovery metadata and request read-only confirmation of that exact
worker's OS cleanup. Successful proof releases only its fenced lease and is
audited; it does not repeat an operation or restore rights. A terminal barrier
blocks late startup with the old session ID. Do not replay input or manufacture
a new request while cleanup remains uncertain.

If Node knows the exact execution cgroup, it can reconcile a lost close/startup
acknowledgment using that cgroup. If its own socket startup was uncertain and no
execution identity was obtained, cgroup absence cannot rule out a queued systemd
start. Restart only the optional Node component, verify the old handlers/workers
are gone, then request read-only cleanup confirmation again. Core needs no
restart. Once cleanup and current rights are confirmed, reload a forced-closed
browser page and explicitly open a new session.

Direct and relay normal sessions produced ready/delayed output before input,
echoed 1,024 bytes exactly, applied resize 99x31 and closed with the exact worker
cgroup absent. The observed dynamic UID was 63972; private paths and IPv4/IPv6
access were denied, and secret-bearing environment was absent. Relay drop/restore
and human
revocation/403/restoration both required a fresh explicit session. Independent
Node/relay updates preserved Core PID 142048/start tick 5936021. These are
independent-probe platform results, not an installed remote Terminal UI trial.

Targeted verification includes 214 integration cases before the final remaining
expiry correction, 39 final browser cases covering that correction, 39 final
TLS/worker/support cases, 51 packaging, 90 delivery and 32 credential cases.
Seventeen frontend cases, TypeScript checking and the Vite build pass. Counts
overlap; they are not unique coverage or full release CI.

All selected physical fault gates pass. Service revocation and Node restart close
old sessions, prove exact OS cleanup and allow fresh sessions with current rights.
Pending-startup human revocation produces no opened/data and sends zero input.
The unknown-start fence returns HTTP 409 for cleanup confirmation despite an empty
cgroup, then accepts read-only proof after only the optional Node restarts. Core
remains PID 142048/start tick 5936021 throughout. The actual TLS listener refuses
missing Hub client identity. Final device identity/credential/provisioning/pin
and unchanged Terminal grant revision 3/human permission checks pass.
No owned workers remain; the disposable probe is disabled, its test human grant
removed and the private test machine/WSL stopped. Consolidated evidence is
`.runtime/dev-lab/evidence/session-platform-final-20261025.json`.
The probe does not convert Terminal into host administration.
Root/`raspberry` maintenance and public Cloud authentication/delegation/deployment
remain outside this scope. See the
[common platform plan](M21_CORE_INTERACTIVE_SESSIONS_PLAN.md#16-common-runtime-boundary-paired-node-and-local-relay--2026-10-25)
for the accepted mechanism and scope; complete M21 acceptance is not claimed.

## Still separate

Full release CI, prolonged resource/endurance testing, public Cloud delegation,
cross-application provider trust, attach/detach and unrestricted maintenance
sessions remain separate. This gate accepts the tested restricted profile and
explicit new sessions after confirmed cleanup; it provides no automatic reconnect
or input replay. One extension/SDK contract remains the design for future routes.
