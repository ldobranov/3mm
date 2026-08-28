# Device administration

Status: implemented and deployed for review on `rasp-3mm` on 2026-08-28.

This guide covers administrator-controlled navigation visibility, Raspberry Pi
restart and application factory reset. Network movement and recovery remain in
[NETWORK_RECOVERY.md](NETWORK_RECOVERY.md).

## Menu visibility

**Settings → Menu Configuration** keeps navigation data-driven. Each menu item
can target one audience:

- **Everyone** — visible before and after sign-in;
- **Signed-in users** — hidden from anonymous visitors;
- **Administrators** — visible only to authenticated administrators.

The audience controls visibility, not route authorization. A route whose router
metadata requires authentication cannot be made public by selecting
**Everyone**. This prevents a menu configuration error from bypassing an API or
page boundary. Existing items without an explicit audience retain their legacy
route-based behavior.

## Restart Raspberry Pi

Open **Settings → Device Control** and select **Restart device**. After browser
confirmation, Core requires an authenticated administrator, writes an audit
record and sends the fixed `restart_device` action to the privileged helper.
The helper accepts no command or path from the browser and schedules the normal
system restart after a short delay.

The application, hostname and SSH connection are unavailable until the host
boots and systemd restarts the selected runtime.

## Factory reset

Select **Erase and reset**, then enter the exact confirmation phrase:

```text
FACTORY RESET
```

The request is administrator-only and audited. The privileged helper schedules
one fixed worker under the shared release-mutation lock. It does not accept an
arbitrary executable, filesystem path or shell command from Core.

The worker removes these persistent 3mm data classes:

- Core database, users, roles and settings;
- dashboards, uploaded modules and installed runtime/compiled extensions;
- Extension Builder projects and provider configuration stored in Core;
- persistent Agent identity and local Agent state;
- provisioning and recovery markers;
- deployment backups and update-helper state.

It preserves:

- Raspberry Pi OS and normal host accounts;
- `/opt/3mm/releases` and the active immutable application release;
- reviewed systemd definitions and `/etc/3mm` service configuration;
- the last verified NetworkManager Wi-Fi profile until a replacement setup
  connection succeeds.

After clearing state, the worker recreates the required private directories,
migrates a fresh database and activates first-boot setup. Join the open
`3mm Setup XXXX` network and provision the device again. During Beta, the empty
database receives `admin@example.com` / `admin`; change that password after
sign-in.

Factory reset is intentionally not an operating-system reinstall or secure
media wipe. Use a fresh OS image when the entire device, system accounts or
storage contents must be replaced.

## Current verification boundary

Review release `worktree-4eb350b6a650-20260828075444` was installed on the clean
Raspberry Pi baseline. Core, Web, Agent and update-helper were healthy, and both
system-control endpoints rejected anonymous requests. Physical acceptance then
confirmed restart, complete 3mm state removal, setup-AP return across reboot,
phone provisioning and a fresh Standalone login. The request/helper and fixed
filesystem boundaries are also covered by focused tests. The accepted behavior
is included in `v0.3.0-beta.9`.
