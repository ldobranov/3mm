# M20 — authority and isolation contract / WP4–WP5 design

Date: 2026-10-08. Status: source-backed design ready for review, with additional
tests of existing broker authority. **Not implemented enforcement, a new wire
schema, or isolation acceptance.** No runtime/authentication/installer/DB change.
SDK 1.3, installed packages and their current policy remain unchanged.

Scope: common Standalone/Hub application platform. Fleet/cloud are consumers,
not authorization authorities. The Linux runtime adapter owns OS isolation;
Core domain logic does not learn concrete hardware or extension names.

## 1. Current evidence, not inferred guarantees

| Current boundary | Source / actual limit |
| --- | --- |
| Signed instance transport | [Platform broker](../backend/services/application_platform.py) authenticates the instance key and timestamp, then resolves the installation; this is not publisher trust or human authorization |
| Own checkpoint state | Broker selects by installation ID + checkpoint ID and uses expected revision; it is not a general RPC replay ledger |
| Human access | [Application access](../backend/services/application_access.py) and gateways enforce route/operation audiences and application-scoped human permissions; a service credential is not a user session |
| Device authority | [Command broker](../backend/services/application_commands.py) resolves a declared binding to configured device/capability/action/argument bounds/TTL; execution rechecks authority and consumes a permit, not caller-selected arbitrary devices |
| Network and secrets | [Connector broker](../backend/services/application_connectors.py) checks the installation's connector/binding/credential, origin, path, methods and limits; redirects are disabled and secret values are injected by the broker |
| Supervised process | [Unit](../deployment/systemd/3mm-application-extension@.service) has read-only code, private network/devices and restricted writes, but all application instances currently use `3mm-app` |
| Files and credentials | [Activation](../three_mm_runtime/application_activation.py) prepares directories `0750`, transport keys/metadata `0640`; the [host](../three_mm_runtime/application_host.py) creates service sockets `0660`, with the common service group; foreign readability/impersonation must be tested, not assumed prevented |
| Browser integration | Existing compiled UI shares Core's origin/runtime; it is reviewed native integration, not an isolated untrusted frontend |

The service unit has no explicit per-instance MemoryMax/CPUQuota/TasksMax policy.
OS defaults and operation deadlines are not measured per-extension exhaustion
protection. The platform socket has a timestamp check, not a global durable nonce
ledger; each mutating action needs its own proven idempotency/replay boundary.
No live malicious payload or OS isolation probe was run in this task.

## 2. Keep five distinct identities/authorities

1. **Package identity:** stable module ID, version and exact artifact digest.
2. **Publisher identity:** separately verified namespace/key/trust policy; names,
   reverse-DNS IDs, registry presence and checksums cannot self-assert trust.
3. **Installed service identity:** installation/instance plus current authority
   generation; keys authenticate this principal, not an administrator.
4. **Human principal:** authenticated user/terminal and application-scoped roles,
   permissions and audience, established by Core rather than supplied by code.
5. **Approved grant:** locally authorized subset of declared operations/resources,
   bound to an artifact/plan and revocable independently of publisher trust.

Capability availability and runtime features are neither identities nor grants.
Possessing `gpio.digital.control` does not authorize every device or channel.
The same capability scope works for Linux modules, firmware and future providers.

Target rule: an effect requires a currently active instance, supported contract,
declared operation and a current grant matching its exact resource/arguments.
Human-triggered operations also require Core-verified actor/audience permission.
Background jobs use an explicit service scope, not a fabricated user/admin role.
Never trust a service-supplied user ID as evidence of human consent.

## 3. Proposed scope model (semantics, not a new wire format)

Reuse existing declarations and bindings; do not create a parallel GPIO, event,
connector, user-role or device registry. Add approved authority around them.

| Resource | Reviewable/approved scope | Not implied |
| --- | --- | --- |
| Private storage | Own installation namespace, read/write mode, approved quotas | Arbitrary host paths, Core DB, another application's files |
| Device command binding | Actual device identity, capability/contract, action, channel/argument bounds, TTL and relevant sensor binding | Every device with the capability; raw hardware access |
| Event subscription/publication | Declared event/capability + configured device scope and ownership/cursor boundary | Fleet-wide data or another application's stream |
| Connector | Declared connector, bound origin/scheme, allowed paths/mutations/limits and secret-reference identity | Arbitrary URLs, redirects, raw secret export or direct network access |
| Platform/installation operation | Exact declared operation and locally approved installation/peer scope | Fleet ownership, human admin role or cloud-wide management |
| Human operation/route | Existing audience and application permission IDs with Core-verified actor context | Global Core admin or access to another application with a same-named permission |
| Runtime/build | Approved execution profile and resource limits | Root, an arbitrary process launcher, package-supplied privileges or a sandbox label |

Manifest `permissions` remain declarations, not an arbitrary OS grant vocabulary.
For example the existing `process.spawn` declaration needed by a supervised
application does not grant arbitrary host commands. Unknown scopes/operations
fail closed in the future enforcement adapter; omission is not a wildcard.
No new package-authored field can assert `official`, `admin` or `sandboxed`.

## 4. Exact approval and change review

The future Core-owned plan/approval must bind:

- module/installation identity, exact artifact version/digest and typed descriptors;
- declared-to-approved scope diff and effective resource bindings, including
  authority-relevant configuration, device identities, connector origins and
  secret-reference generations **without secret values**;
- supported contract versions, pinned dependency artifacts when a resolver exists,
  approved runtime profile/policy revision and relevant trust/grant generation;
- authenticated approving actor, local approval evidence and policy revision.

Canonicalization/hash input must be versioned, bounded and tested before a wire
schema is exported. It excludes transient heartbeats, last-seen times and cosmetic
labels; configuration object key order cannot create a false permission change.
Security-relevant configuration/binding changes are not hidden by keeping a
same-named configuration key. Changed target identity/origin/channel bounds,
new rights, new artifact or stronger runtime invalidate the old plan/approval.

An update with fewer rights still needs exact new-artifact activation approval;
it must not retain deleted authority. A new digest is not automatically trusted
because the module ID/publisher is familiar. Stage/activation and every effect
recheck current authority; a preflight result is not a durable execution permit.
Authority-affecting changes need race-safe generation invalidation, not just UI
warnings or a successful inspection request.

Disable/revoke prevents new effects and invalidates queued authorization according
to existing command/job contracts. Preserve owned historical lookup, admin audit,
export, backup/recovery and explicit uninstall. Already-dispatched uncertain
physical/fiscal/network actions stay uncertain; revocation never replays them.
Do not blanket-disable all read-only recovery calls: current `command.lookup`
is deliberately available for owned historical requests after disable.

## 5. Linux runtime isolation direction

Preferred direction: a distinct OS service identity per logical application
instance, allocated by the trusted runtime/installer, not by package code.
Keep the existing supervisor/SDK/transport; do not introduce a second host.

- Private data/run/release/credential visibility; no shared secret-readable group
  or membership that grants an extension access to Core/other instances.
- Core keeps explicit access to required instance IPC/keys, without granting
  applications access to Core credentials, DB or foreign IPC. A tested narrow
  ACL/credential bridge is an implementation prerequisite, not an assumption.
- Namespace/read-only mounts and own writable roots complement identities;
  code/config/activation metadata remain installer-owned. Runtime cannot replace
  its approved metadata, execution profile or ownership mapping.
- Check process signalling, `/proc`, inherited descriptors/environment, symlinks,
  shared-group traversal, secrets and impersonation, not just direct file reads.
- Restrict direct networking/devices/processes and bound memory/CPU/tasks/files,
  disk growth, socket idle time/concurrency and restart storms with measured
  supported-host limits. Connector/event/job brokers retain independent quotas.
- UID/GID lifecycle and Core IPC access mechanism require a supported-host proof
  before enforcement. A manifest cannot select Linux accounts or host paths.

This design does not claim that changing a username or applying systemd hardening
alone provides a sandbox. The malicious two-instance tests below are the gate.

## 6. Frontend boundary and existing packages

Declarative themes/runtime pages remain their constrained adapters. Existing
compiled UI stays explicitly reviewed native integration. Untrusted executable UI
needs a separate proven origin/frame boundary and narrow authenticated bridge,
with sender/origin/schema checks, no Core tokens and no arbitrary DOM/store access.
Backend isolation alone cannot make same-origin JavaScript safe. Do not silently
relabel or break existing SDK/UI packages while introducing this policy.

Agent modules remain the separate reviewed device-local hardware/runtime adapter;
application isolation does not prove arbitrary Agent code safe. Legacy language
compatibility is not permission for untrusted legacy backend execution inside
Core. No inspector/registry may downgrade or fallback to that execution path.

Migration must retain module/instance IDs, configuration, private data, current
installation versions, bindings and recovery evidence. Record existing trusted
provenance; absence of a new approval record does not invent a wildcard grant or
trigger a destructive conversion. Do not force an existing service onto the new
policy until its adapter/migration and rollback are accepted.

OS ownership migration runs quiesced under the existing mutation lock and a
verified backup; stop/ownership/key/health failure restores a coherent old state
or leaves an explicit review-required disabled state. Portable restore remaps OS
identity locally rather than granting a backed-up numeric UID arbitrary privilege.
Foreign-installation grants/keys require their existing binding/review policy;
restoring data does not authorize effects or release uncertain job quarantine.

## 7. Small implementation order and acceptance

1. **Read-only authority review:** derive declared scopes from existing validated
   packages + resolved configuration; compare a trusted supplied current policy,
   report additions/removals/widening/unresolved scopes. No grants or install writes.
2. **Approval contract/persistence:** settle canonical plan schema, supported scope
   subset, race-safe generation and audit; add non-destructive migrations/tests.
3. **Two-instance Linux proof:** implement private identity/IPC/credential ownership
   in the existing adapter with failure/rollback/restore tests. No untrusted enable.
4. **Broker enforcement:** enforce approved scopes at effect boundaries while
   preserving SDK 1.3, actor/access rules, existing permits and recovery behavior.
5. **Browser/resource proof:** implement/prove the required frontend boundary and
   measured exhaustion controls before any remote/untrusted executable install.

Required negative acceptance: A cannot read/write B or Core data/keys, impersonate
B, connect to foreign privileged IPC, signal/debug foreign processes, escape
browser scope or invoke undeclared/unapproved targets/actions. Changes/revocation
between review, queue and dispatch fail safely. Denial/restart/rollback never
replays an ambiguous external effect. Resource abuse cannot prevent admin recovery.
Run these under actual production identities, mounts, systemd and transport;
mocked file permissions or a separate Python process are not sufficient.

Current task adds isolated real-Unix-socket broker tests for two-instance checkpoint
ownership, wrong/foreign/unknown credentials, disable/data retention and repeated
checkpoint CAS. Together with existing command/connector checks these preserve
the current policy; they do not implement grants or prove the Linux/browser gates.

Verification: **17 focused tests passed** (6 new broker-authority cases and 11
existing checkpoint/command/connector cases; 14 warnings) in isolated WSL/Linux,
with temporary keys and an in-memory/test database, no live connector/device.
Frontend production build passed; there are no visual changes. Full release suite,
production OS/browser isolation and live migration/restore were not run. No new
dependency, deploy, commit/push or release was introduced.

Subsequent local slice: [read-only application authority comparison](EXTENSION_PLATFORM_V2_AUTHORITY_REVIEW.md)
implements the first declaration projection/diff with focused tests. Its current
baseline is explicitly **previous package declarations, not approved grants**;
there is no approved-policy persistence to compare yet. Missing effective bindings,
peer scope and executable frontend effects remain unresolved. The comparison is
now integrated read-only into Package Inspection/Extensions, with owner visual
acceptance on 2026-10-08, but no lifecycle integration or authority enforcement.
The trusted approved
policy comparison in step 1 and the later approval/isolation gates remain open.

Subsequent design slice: the [explicit approval contract](EXTENSION_PLATFORM_V2_APPROVAL_CONTRACT.md)
defines resource subsets, actual credential versions, observed/apply epochs,
invalidation/concurrency and compatibility/restore semantics. It is a local draft
for owner review, not a new wire schema, grant store or authority switch. Its
acceptance matrix is future work, not additional test evidence.
