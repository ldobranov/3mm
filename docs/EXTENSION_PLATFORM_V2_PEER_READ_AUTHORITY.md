# M20 WP4 Block 1 — sealed outbound peer-read approvals

Update **2026-10-17**: the dedicated public SDK outbound reader is now wired to
these exact grants. The 2026-10-16 runtime-unavailable statements below are
historical; current implementation and verification are tracked in the
[short WP4 closeout checklist](EXTENSION_PLATFORM_V2_WP4_CLOSEOUT.md). Generic peer
leases, unfiltered lists, signing, mutations and SQL-mixed profiles remain denied.

Date: **2026-10-16**. Implemented/tested locally: an installed-only, headless
internal-v9 source → native review → permission review → approve → apply →
current-grant/revoke cycle for exact **outbound peer metadata reads**.
This is persisted authorization metadata, **not a working peer-read SDK method,
WP5 isolation or WP4 closure**. The later local management UI is recorded in
[the peer-read UI follow-up](EXTENSION_PLATFORM_V2_PEER_READ_UI.md). It builds on the
[pure v9 context contract](EXTENSION_PLATFORM_V2_PEER_READ_CONTEXT.md).

## Supported installed profile

- A validated, digest-pinned current installed application, SDK 1.3, with 1–32
  configured bindings, every binding **outbound** and operations exactly `read`.
- No receiver descriptor and no relational storage in this first installed
  profile. Wider/mixed actions, inbound/receiver work and SQL lifecycle consent
  remain separate gates. Other existing unsupported families still block the
  whole subject, even when omitted from the user's selected rights.
- Existing public-identity, local-status, checkpoint, private-file, command,
  connector and event/publication families retain their existing validation.
  Compiled UI, application-provided public HTTP routes, jobs, unresolved dependencies and undeclared
  coarse peer access do not become supported by adding a read declaration.

The saved configuration, current owner/incarnation/instance and actual installed
package are resolved in the existing Core transaction. The shared reader checks
the complete declared set, public identity pins, signed enrollment metadata,
origin, target and consent. Missing, foreign, revoked, aliased or malformed links
produce no partial peer family or reviewable supported subset. Native-review
recording also refuses unsupported subjects; old attestations cannot authorize
a changed artifact. No identity, key or missing peer state is initialized.

The existing package validator still requires the coarse `installation.peers.enroll`
and structural `network.outbound` manifest declarations for this descriptor
family. They remain **requests, not executable rights**. Only exact
`peer:<logical_binding_id>:read` selections are approved. Generic network,
enrollment and signing access is not granted or inferred from those fields.

## Sealed review and selection

Current Core local administration must record its authenticated exact-artifact
manual native code review. Neither HTTP, an SDK request nor a browser checkbox
can manufacture native trust. The existing protected Core key authenticates the
v9 subject, review plan, selected scopes, policy, grant and action receipts.

Peer reads are individually selectable, including an explicit empty set. The
complete declared peer family still participates in review/current-resource
comparison, so an unsupported or disappeared omitted peer cannot hide behind a
supported selection. The manager's required-selection behavior for all earlier
resource families is unchanged. Empty or partial peer choices never mean all
peers, raw-ID discovery, inbox history, mutation or a generic signer.

Review creation does not approve; approval does not apply. First adoption still
requires actual disabled/stopped installation state. Apply changes the guarded
authority epoch and writes the sealed grant, plan, action and audit in the same
transaction; failed audit rolls the whole change back. Apply never starts the
application. Exact retries are historical receipts, not permission reapplication
after revocation. Grant revocation is distinct from revoking a peer connection;
it never restores compatibility authority or rewrites pairing/business consent.

Before approving/applying or accepting a stored grant as current, Core rebuilds
the current complete subject. It checks exact configuration HMAC, owner,
instance, package/service, public pins, origin/target/consent, native review,
key/recovery generation, epoch and grant revision/seal. Pending reviews additionally
retain the existing current-actor/session, bounded boot clock, expiry and revision
checks. No retained source snapshot is treated as future admission. A changed
dynamic observation alone does not rename the resource; revocation or invalid
proof-state still makes fresh source resolution fail.

## API and runtime boundary

The existing administrator-only review API accepts the additive exact peer-read
scope vocabulary and returns the protected public resource metadata. It rejects
caller resource/configuration/owner/native-trust payloads. The request ceiling is
261 only when a peer-read scope is present; earlier 197/229 HTTP bounds and the
manager's earlier version-specific bounds remain intact. The Core-resolved
subject chooses internal v9, never a caller-supplied version hint.

`review_available` can be true and a grant can be `active` while runtime is
unavailable. Status therefore explicitly reports
`runtime_blockers: ["peer_read_runtime_unavailable"]` and does **not** report
`grant_effective: true` for this new profile, even for an enabled application.
The generic effect-admission helper refuses every `peer:` scope before both
compatibility and reviewed admission. A signed/sealed v9 record is not a generic
lease. No peer read executor, IPC action, public SDK method or catalog runtime
promotion was added.

Existing identity/status adapters keep their separately approved resource data
when the enclosing subject is v9. A real signed Unix-socket test exercises those
reads with current v9 grants and still refuses the legacy unfiltered peer list
and enrollment. Existing peer/signing/mutation helpers remain closed for packages
with exact bindings. Independent receiver consent and explicit human cleanup are
unchanged. This is reviewed native code, not a sandbox or host/network isolation.

The subsequent local frontend slice now accepts this exact installed profile,
with closed EN/BG public resource cards, optional subset/empty choices and the
runtime-unavailable warning. It rejects inbound/wider/SQL-mixed profiles and never
claims that a saved approval enables SDK reads. See the separate
[UI verification and remaining acceptance boundary](EXTENSION_PLATFORM_V2_PEER_READ_UI.md).
Its synthetic browser checks are not owner/VM or live peer SDK acceptance.

## Verification

- Final new native suite: **55 Linux/Python 3.14.4 cases passed** in 87.34 seconds,
  without skips. Real POSIX review keys, installed ZIPs, current administrator
  sessions, signed fixture enrollment starts, SQLite transactions, sealed plans/
  grants and signed Unix SDK transport are used. Both peer wire versions and
  mixed identity/status/checkpoint requests are included; no live pairing or
  Internet ingress acceptance is claimed.
- Cases cover approve-versus-apply, stopped adoption, exact subset/empty rights,
  unconfigured peers, source/config/artifact/consent/key/recovery/epoch drift,
  current actors/boot clocks, seal corruption, native/grant revocation,
  historical retry, audit rollback, unsupported receiver/mutation/SQL profiles,
  HTTP administration and refusal of generic peer execution.
- **460 Windows cases passed** in the old/new authority context/policy families
  and the actual non-POSIX key refusal. **20 additional Windows HTTP-contract
  cases passed**, including old/new count ceilings and closed inputs. These are
  scoped checks, not the complete release suite.
- Frontend production build passed in **5.98 seconds**. No frontend source was
  changed and no new visual acceptance is claimed.
- Native follow-up: **276 regression cases passed** in 270.33 seconds, with one
  non-POSIX-only refusal skipped and already passed in the Windows run above.
  The selection covers old sealed management, sources/subjects, peer request/
  adoption/SDK denial, identity/status/checkpoint execution and exact v6/v7/v8
  SQL start consent. **152 contract cases passed** in 10.61 seconds, including
  v9/old canonical vectors and the new HTTP grammar.
- Final distinct coverage across these runs: **483 passing Linux cases** and
  **480 passing Windows cases**. Cross-platform and prior-slice checks overlap;
  they are not added together as unique release/acceptance coverage. JUnit
  evidence contains no failures or errors. Four implementation files and the
  55-case suite match `/var/tmp/3mm-peer-grants.mRSHR7` byte-for-byte; the HTTP
  contract suite matches `/var/tmp/3mm-peer-grants.Q3Qx7O`.

Evidence: `.runtime/m20-peer-grants-*`. Preliminary/faulty fixture attempts are
not extra passing coverage; the initial fixture omitted an existing structural
manifest permission and was corrected without weakening the package validator.
Existing deprecation and fixture JWT-key warnings remain visible. Tests run with
disposable databases, isolated mount namespaces and unprivileged native processes,
not against the installed VM or the parallel `/opt/3mm-dev` project.

No database schema migration, SDK/manifest/peer-wire/Core release version change,
new key provisioning path, VM/service/live-grant mutation, branch, commit, push
or release is included. Next after the management UI: bounded SDK reading with
fresh key/guard/peer serialization and revocation-race verification. Block 1 and
WP4 remain open; neither this metadata cycle nor earlier beta.51 relational
acceptance closes the remaining frontend/platform and neutral acceptance gates.
