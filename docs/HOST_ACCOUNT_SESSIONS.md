# Local host-account sessions

Plan mapping: **CAP15 — sessions/streams**, with the **CAP20** execution/resource
profile boundary. The historical M21 session mechanism is not CAP21 application
authoring. This bounded profile does not close all CAP15/CAP20 acceptance gates.

This is an opt-in platform profile for a reviewed local terminal provider. It is
not root administration, SSH, an application-host shell, or a change to the
existing `isolated_session_v1` profile. A provider must explicitly declare
`host_account_session_v1`; an unavailable profile never falls back to another
executor. Remote Node executors do not accept this profile.

## Account and access boundary

The installer prepares a password-locked, non-login `3mm-terminal` system account,
its private persistent home `/var/lib/3mm-terminal`, separate worker units and a
disabled root-owned `/etc/3mm-host-sessions.json` policy. It starts no terminal,
enables no socket and grants no application or human rights. Existing policy
decisions are preserved; unsafe existing accounts, homes or policies are refused,
not silently repaired or taken over.

The provider's native code **and** its child commands receive this account's file
permissions. This is one shared account/home, not isolation between applications
or people. The account has no platform groups, capabilities, root or sudo access.
The worker has no IP networking or device access. Core secrets, private state and
control sockets are inaccessible; the host filesystem is read-only except for
the dedicated home and private temporary directories. Other host files remain
readable only when ordinary Linux permissions permit it.

The persistent home is retained across component updates and rollback. It is not
part of the existing Core/application backup contract. A provider is responsible
for shell history and any other content it chooses to save there. Terminal
contents are not copied into worker logs.

These restrictions are not a hostile-native-code isolation guarantee: the
administrator approves native provider code running inside the worker. A blocked
or uncooperative provider can prevent its own cooperative shutdown; the OS still
enforces the worker's resource and lifetime limits. Do not treat an IPC close
acknowledgment as proof that all processes have exited.

## Provider development

Use the public declaration `ApplicationSessionProviderV1` from
`packages.protocol.application_sessions`. Declare the exact provider factory,
capability and interactive contract as usual, with
`resource_profile: "host_account_session_v1"`. This first local profile is
self-provided: the session binding selects the same application whose reviewed
wheel contains the provider. Another application's wheel cannot inherit its
code approval.

At the provider's process boundary use the public SDK guard
`packages.application_sdk.session.require_host_account_session_process()`.
Keep `require_isolated_session_process()` for isolated providers. Changing only a
factory or bypassing the isolated guard is not an upgrade to host access. A
provider supplies its own fixed executable/PTY implementation; browser options
cannot select an account, UID, GID, shell, command, environment, home or working
directory. Core neither supplies an application-specific shell nor imports the
provider during discovery.

`ResolvedSessionScope.host_account` is runtime review evidence, not package
configuration. Core resolves its fixed account, positive UID/GID, home and policy
generation. Package authors and browsers must not fabricate those values.
Isolated resources omit this field entirely.

## Explicit installed-host opt-in

The following is a separate administrator acceptance procedure, not something
performed by local tests, package upload or an ordinary deployment:

1. Install the current Core and independent `host-session-worker` artifact with
   the normal immutable installer. Confirm its disabled policy/account validation
   succeeds. Never repurpose `raspberry`, `3mm`, root or another existing account.
2. As the host administrator, review the fixed policy and change its exact JSON
   to `{"schema_version":1,"enabled":true}`. Keep it a single-link regular
   root-owned file, readable by Core/the worker, with no group/world write access.
   Use the existing trusted `/etc` location; no symlinks or caller-selected path.
3. Preserve all other Core environment settings and secrets. Enable the existing
   `THREE_MM_LOCAL_SESSIONS=1` feature flag and the separate
   `3mm-host-session-worker.socket`, then restart Core if its environment changed.
   Keep the existing exact browser-origin checks; never add a wildcard to obtain
   a working terminal. The isolated socket is not a substitute for the host one.
4. For a fresh ordinary SDK-storage session application, configure its local
   device and activate its ordinary application service first, then open
   **Application access**. Starting that service does not launch the host worker
   or grant a session. Review native/UI code and its local session resource.
   The review shows the account/home warning outside technical details. Confirm
   the exact local device, provider/version, access mode, control and options,
   account and policy generation. Approve only the required resource and assign
   the application's declared human session permission separately.
5. Open one new explicit session after both reviews and current human access
   succeed. No package upload, policy enablement, service start or administrator
   label implicitly grants session access. There is no automatic reconnect or
   replay of input after an uncertain result.

Changing the policy file or account identity invalidates existing review evidence,
even after disable/re-enable with the same JSON. Prepare a fresh resource review;
do not edit a grant or manufacture a new request to bypass the refusal. To disable
host sessions, set the root policy to disabled and stop/disable only its socket.
Existing isolated-session settings and socket are independent.

The current generic inactive `/stage` flow deliberately excludes session
providers. This slice does not add inactive package/configuration staging for
session-provider upgrades, or first registration of a relational application
with a required self-provided session. Do not route those cases through the
ordinary Note/optional-device workflow or clear existing data to force them
through. A coordinated Terminal update must establish its supported package
lifecycle separately, as well as adapt its declaration/guard.

## Currentness and cleanup

Core retains the normal current native/resource/human checks throughout a
session. The host channel adds a three-second policy/lease check independent of
pending terminal output, and the worker closes a silent channel after ten
seconds. Connection loss, currentness failure or EOF closes that original
channel; input and control are never automatically resent.

Systemd owns the complete process cgroup. Configured budgets are at most four
connections, sixteen tasks per worker, 128 MiB memory, 50% CPU and a 900-second
maximum worker lifetime. Installed controller support must be checked separately;
a memory-controller warning means the configured RAM limit is not proven/enforced
on that host. Installing a unit file is not OS resource-limit acceptance.
Disconnect/revocation normally closes the cooperative provider and its process
tree. If startup or cleanup is uncertain, Core keeps the session fenced until
the exact cgroup is absent or empty. A blocked native provider may survive until
the OS lifetime limit; a success message must not be substituted for OS proof.

## Acceptance still required

Source checks cover declarations, exact account/policy review, denial/revocation,
local-only routing, stream bounds/lease/cleanup handling and immutable component
packaging. They double host metadata/systemd and do not create a real user or run
a host shell. Before installed acceptance, adapt the separately maintained
Terminal provider to this profile and test on a disposable Linux host: actual
UID/groups/home, allowed reads/home writes, private-path and network denial,
prompt/input/output/resize, idle revocation, policy replacement, disconnect and
the complete process tree disappearing. Keep installed evidence separate from
these source checks.
