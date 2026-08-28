# Network recovery

Status: implemented and physically accepted on `rasp-3mm` on 2026-08-27.

This guide describes how an administrator moves a provisioned 3mm device to a
different Wi-Fi network or recovers local access after its network disappears.

## Normal local access

The provisioned application listens on:

- `http://<device-ip>/`;
- `http://<hostname>.local/` when the client supports mDNS;
- `http://<device-ip>:8080/` as a compatibility address.

Core remains on port 8887. The local Agent remains loopback-only on port 8890.
Changing the frontend URL in Network Configuration does not change the Linux
hostname; the page exposes the hostname already configured on the device and
can apply that URL to the frontend configuration.

## Administrator controls

Open **Settings → Network Configuration**. The recovery card shows whether a
Wi-Fi or Ethernet link is active and offers two controls.

### Start setup Wi-Fi

This is the manual path for moving the device or recovering it before transport.
After confirmation, the request is audited and delegated to the narrow root
helper. The normal Core, Web and Agent runtime is replaced by setup services.

On a Wi-Fi-only device this intentionally removes the current LAN address and
drops active browser and SSH sessions.

### Automatically start after five minutes offline

This option is enabled by default. The monitor starts setup mode only after both
Wi-Fi and Ethernet have remained disconnected for 300 continuous seconds.

The test is deliberately local-link-only. Loss of Internet access while the
device remains connected to its router does not start the AP. Returning either
link resets the timer. An administrator can disable the option, for example
when the device is protected by a UPS but the router is not.

## Phone setup flow

1. Join the open network `3mm Setup XXXX`. It has no password and exists only
   while setup mode is active.
2. The phone should open its captive-portal window automatically. Depending on
   the operating system, it may instead display a **Sign in to network**
   notification.
3. If automatic opening does not occur, browse to
   `http://10.42.0.1:8895/setup`.
4. Select a network from the scan results or enter its SSID manually.
5. In recovery mode the previous device name, locale, administrator metadata,
   role and Hub address are pre-filled. Select the destination network, enter
   its Wi-Fi password and review the remaining values, then save.
6. Reconnect the phone to the destination network and open the device through
   its IP address or `<hostname>.local`.

The portal reuses the saved light/dark theme. A successful save can disconnect
the phone before the final response arrives; the setup client treats the
expected runtime transition as success once the profile was accepted.

## Runtime and security boundary

- Only an authenticated administrator can change the automatic policy or
  request manual setup.
- The policy and recovery marker contain no Wi-Fi password.
- Recovery prefill contains only non-secret provisioning metadata. The Wi-Fi
  password must always be entered again.
- The destination password is passed to NetworkManager and is not written to
  the application database, provisioning journal or logs.
- Setup Web remains unprivileged and receives only the low-port bind capability
  required for port 80.
- Privileged NetworkManager changes remain behind the existing helper/runtime
  boundary and the shared release-mutation lock.
- Captive DNS is installed only while `3mm-setup-ap.service` is active and is
  removed when setup stops.
- A failed Wi-Fi change rolls back and leaves setup mode available.
- Successful recovery preserves the Core database, extension state and Agent
  identity.

The setup AP is intentionally open for usability. It is a local, temporary
recovery boundary and is not presented as the final production security model.

## Accepted Raspberry result

Immutable review release `worktree-f433dada70b5-20260827170249` was tested on a
Wi-Fi-only Raspberry Pi 3B+:

- normal access returned HTTP 200 through IP port 80, `rasp-3mm.local` and the
  port 8080 compatibility listener;
- manual setup activation worked from Settings;
- the phone detected and opened the captive portal;
- nearby-network scanning and themed setup rendering worked;
- saving a destination profile restored the normal runtime and LAN access;
- 38 focused setup/systemd tests and all 47 frontend tests passed before the
  accepted deployment.

The one-command flow has also been repeated successfully on clean media.
Setup-profile behavior across a full Raspberry reboot remains part of the open
Milestone 10 acceptance boundary.
