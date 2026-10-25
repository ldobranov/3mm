# Core 0.3.0-beta.57

Release scope prepared on 2026-10-25. This version brings together the accepted
Core stabilization, setup/recovery, common session platform and application
lifecycle/consent work since beta.56. Publication requires the automatic CI and
immutable tag-driven Release workflow; the owner runs subsequent device trials.

## Changes

- Separate optional platform-runtime, application-host, connector and session
  executors from Core authority. Independent components have explicit contracts,
  health/update boundaries, bounded transport and failure handling. Optional
  executor failure must leave Core administration available.
- Add a protected setup portal for Standalone, Hub and Node. Device role and
  network ownership are separate: Linux can retain host-managed networking;
  supported Raspberry Pi adapters can use managed Wi-Fi and a temporary recovery
  AP. Network changes have verification, durable journals and bounded rollback.
  Existing identity, pairing and healthy local workloads survive recovery.
- Add opt-in bounded diagnostics and a diagnostic workspace. Bootstrap and
  component diagnostics use metadata allowlists, quotas and expiry; terminal
  input/output and credentials are excluded. Diagnostics are optional to work.
- Use manifest-v2 language extensions, including the Bulgarian language pack;
  retire obsolete prototype extension paths. Legacy application compatibility
  is not a release requirement for this prototype.
- Complete the common interactive-session boundary, actual Node execution and
  an encrypted local relay. Node TLS uses the existing Hub identity; Node workers
  and relay can update independently of Core. Revocation, startup uncertainty,
  ownership, cleanup and no-replay rules remain enforced. Slow ARMv6 cold starts
  have explicit bounded startup budgets.
- Fix local browser UI/native checks to share one current SQLite authority
  snapshot, avoiding a nested reader. Separate the five-second authority deadline
  from the one-second output poll interval, retaining checks during blocked I/O.
- Reject malformed helper action types before dispatch, so invalid array/object
  actions return a bounded refusal instead of crashing AP/system-action handling.
- Make failed application installation/startup visible and removable through the
  ordinary lifecycle. Retire unused obsolete/missing/corrupt packages only after
  exact managed-path, reference and quiescence checks.
- Track retained application data separately from packages. After uninstalling
  the last package, administrators can still find and explicitly erase its data.
  Unknown ownership, live workers, symlinks and deletion errors refuse success.
- Simplify Application access to one administrator approval with expandable
  details. Initial resource choices are selected; saved subsets stay selected.
  Approval covers the exact native package, UI build, configuration and requested
  resources. Manual code audit is optional under the owner's approved trust model.
  Native execution is not a sandbox. Direct permissions apply only to the current
  administrator; other users and roles are unchanged.
- Initialize a missing first local consent key through authenticated preview,
  without granting access. Existing corrupt, foreign or stale keys are never
  silently replaced. Upload, preview and refresh alone do not approve code.
- Preserve consent across a confirmed stop/start of the same approved application.
  Fresh execution envelopes invalidate old commands and sessions; code/config/
  resource changes, revoked rights and unknown lifecycle outcomes require review.
- Add conservative CI group selection and development tooling. Branch pushes and
  tags retain automatic checks; unknown/shared inputs and comparison bases
  without successful CI select full coverage. Superseded jobs can be cancelled;
  failures return promptly without making an incomplete run publishable.

## Upgrade and scope

This release includes additive migrations for language projections, runtime event
claims, connector dispatch and retained application data (latest revision
`3e189f465708`). Preserve a verified pre-upgrade database/key backup. A code-only
rollback to older consent handling does not adopt new administrator approvals;
nonempty migration downgrade may be refused. Do not reset keys or rewrite seals.

Device Protocol remains 1.0 and Application SDK remains 1.3; their independent
version numbers do not imply unchanged source. Release archives contain the
prebuilt frontend and component sources/contracts. Separately installed component
artifacts retain their own update boundaries.

The accepted session profile is a restricted temporary Linux workspace. Host/root
administration, a public Cloud service, complete remote Terminal UI and whole
M21/WP5 isolation are separate work. Terminal 1.0.3 is an independent application,
not a Core release asset. The CAP01-CAP21/C0-C5 capability plan is documentation,
not a claim that all planned capabilities are implemented.

## Verification and publication

Scoped Linux, frontend and physical-device evidence is recorded in
[WORKING_STATE.md](WORKING_STATE.md). The owner accepted P2 Wi-Fi/AP, local
Terminal operation, common sessions with Node/local relay, removal/data cleanup
and simplified consent. Those runs cover their recorded snapshots and overlap;
they are not a full regression result for the final release commit.

Automatic main CI checks the exact committed tree using Python 3.13 and Node 22.
After it passes, a new annotated `v0.3.0-beta.57` tag triggers Release: all suites,
frontend checks, reproducible full-profile and ARMv6 Node builds, manifests and
checksums. All seven assets must upload before the draft becomes public. See
[RELEASING.md](RELEASING.md). A tag, draft or green scoped test is not publication.

## Owner device trials

After publication, use the immutable release archives/update channels and verify
installed VERSION, readiness and component health on the VM/Raspberry devices.
Keep the existing independent Hub backup; built-in restore is Standalone-only.

Local development candidates can already report `0.3.0-beta.57`. The update
catalog offers only strictly newer versions, so it will not advertise replacement
of a different build with the same version. Use the exact published tag bootstrap
to replace such a candidate; verify the installed `.3mm-release.json` commit
matches the published manifest, not only VERSION. Preserve the existing backup.

Full profile (VM, Linux PC or supported Raspberry Pi):

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/v0.3.0-beta.57/install.sh | sudo bash -s -- --tag v0.3.0-beta.57
```

Minimal ARMv6 Node (Raspberry Pi Zero W / Python 3.13):

```bash
wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/v0.3.0-beta.57/install.sh | sudo bash -s -- --profile node --tag v0.3.0-beta.57
```

The bootstrap verifies the selected archive's size/hash and runs the immutable
installer. Existing local candidates have different release directory names;
an already installed official `v0.3.0-beta.57` directory is never overwritten.
Optional session components still use their separate installation/update path.

1. Check role, identity, pairing, host-managed networking and managed Wi-Fi/AP
   recovery as applicable. Recovery must return to the saved usable network.
2. Upload/activate a current application, inspect optional access details and
   approve once. Stop/start it: the same consent should remain effective. A
   changed package or revoked permission must not regain access automatically.
3. Exercise a failed or obsolete application install, uninstall, package removal
   and explicit retained-data cleanup. Failed cleanup must remain visible.
4. For the separately installed Terminal, connect once, require a real prompt,
   test commands/delayed output/resize/idle and confirm Disconnect cleanup.
   Never resend uncertain input. Node/local relay trials require their reviewed
   independent component configuration; updating Core alone does not enable them.

Retain timestamps, request/session IDs and metadata diagnostics for a failure.
Do not clear ownership fences, reset keys or grant extra rights as a workaround.
