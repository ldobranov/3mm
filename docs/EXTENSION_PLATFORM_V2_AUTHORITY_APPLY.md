# M20 WP4 — installed authority review, apply and revocation

Date: 2026-10-09. Status: **implemented and tested locally, not deployed**.
This delivers the bounded backend command/connector/event-consumption cycle and
its management UI, not all WP4 or WP5. The owner accepted the command/connector
management UI and the additive event-resource view on **2026-10-09**.
Visual acceptance is not live grants, rollout or isolation.
SDK 1.3, module manifests and device/connector transport contracts are unchanged.
The common Standalone/Hub application layer is used; there are no Fleet-specific
or concrete-extension/provider branches.

## Delivered boundary

An already installed, headless supervised application can be individually adopted
into `enforced` authority after **manual review of its exact code**. Core records
an authenticated local review attestation, not an automatic code audit, publisher
ownership proof or sandbox. Executable frontend, staged/new artifact, unresolved
sensor contracts and unsupported authority families stay blocked in this adapter.

Package permissions, inspection fingerprints and an HTTP checkbox cannot supply
native trust. The local Core administration command is deliberately separate from
the admin permission API. Existing installations keep `compatibility` behavior;
there is no inferred trust/grant backfill or automatic migration of running apps.

Whole supported command/connector/event bindings are selected by stable IDs. The first
profile requires all supported declared scopes, with exact command schema equality;
optional feature omission and arbitrary schema/range/path narrowing are not claimed.
Private configuration is represented by a Core-keyed identity; passwords, token
values and full configuration are never returned in a review.

## State and admission

Review reconstructs the actual artifact, logical installation/incarnation, baseline
epoch, full private configuration identity, current device/control/provider/runtime
contract and owned connector origin/credential reference/version. A plan lasts
15 minutes on Linux boot time, including suspend. Reboot expires pending plans;
ordinary process restart does not automatically invalidate current durable grants.

`review_required → approved_pending_apply → applied` is the decision sequence.
Approval alone leaves current authority untouched. Apply revalidates exact resources,
the current signed administrator session and policy, then atomically writes a sealed
grant, fresh authority epoch, command invalidation and redacted audit/receipt. Denial
leaves running authority unchanged. Grant/native-review revocation fences new work.

Command queue admission and the existing one-use execution permit both recheck
current grants. Connector attempts commit admission before HTTP dispatch. Lock order
is **Core key → DB authority guard → actor/application → device**, as applicable.
Package preparation precedes the lock; no lease spans external HTTP or helper I/O.
Legacy admission uses a final application row CAS against adoption/disable/rotation.

Revocation committed before admission wins. An already admitted POST or physical
permit may still take effect: revocation cannot recall it. Lost responses retain
uncertain outcomes; retries return owned historical evidence without replay. Existing
TTL, idempotency, device authority, human access and broker checks remain independent.
Opted-in unsupported platform writes cannot fall through to legacy authorization.

Same-artifact re-enable uses the existing lifecycle and exact native/configuration
check, but invalidates the old grant. A new permission review/apply is required after
start. Changed artifact/configuration and incomplete lifecycle recovery cannot reuse
this installed-only activation adapter.

## Operator sequence — explicit, not automatic rollout

These are instructions for later authorized local adoption; no live key, review,
grant, device command or connector action was created by this development work.

1. Verify a recoverable backup and select a supported headless application. Use the
   existing disable operation and confirm stopped/disabled before first adoption.
   This cycle enforces disabled adoption but **does not verify the backup itself**;
   full adoption recovery remains WP3 acceptance.
2. Run local administration as the **Core service UID**, with its existing database,
   uploads, signing environment and import path. Do not run as root/application UID
   or change immutable release permissions. The default SQLite key directory is
   beside the Core database, normally `/var/lib/3mm/core/authority-review`; trusted
   host configuration may set `THREE_MM_AUTHORITY_REVIEW_KEY_DIR`.
3. Explicitly provision the Core-private key; there is no startup/API provisioning.
   Supply a current Core administrator login token at the hidden prompt, never as
   a command argument or in logs:

   ```text
   python -m backend.services.application_authority_admin provision-key
   ```

4. A trusted reviewer actually reviews the exact installed artifact and retains a
   review document. Record that manual attestation locally:

   ```text
   python -m backend.services.application_authority_admin native-review \
     --installation-id <actual-installation-id> \
     --artifact-sha256 <exact-zip-sha256> \
     --review-document <local-review-document> \
     --code-review-completed --accept-native-host-risk
   ```

   The document is read bounded to 1 MiB and its digest recorded; no document/package
   code is executed. These flags attest a completed manual review; they do not
   perform one or claim isolation. The result supplies `native_review_id`.
5. In **Extensions → Application access**, select a current verified local review,
   create an exact-resource review, inspect its returned resources, acknowledge
   those resources, approve and separately apply while disabled. The equivalent
   admin API is below. Approval returns a new record revision: apply uses that
   revision, not the original review revision.
6. Re-enable the same reviewed artifact via the normal lifecycle. It remains denied
   for new effects until a **fresh post-start permission review/approve/apply**.
   Then verify operation through the existing SDK/brokers, not raw DB edits.

## Additive administrator API

Base: `/api/v1/application-extensions/{module_id}/authority`.
Normal Core admin authentication is required. Mutations additionally verify the
actual current signed token/session/user role, not a supplied actor ID or role claim.

| Method/path | Closed request / result |
| --- | --- |
| `GET /` | Current mode, installation state/enabled flag, artifact, scopes, verified local-review IDs/revisions, sealed-grant state/revision and effective status |
| `POST /reviews` | `request_id`, `native_review_id`, `scopes`; returns exact redacted resources, `plan_id`, `revision`, `fingerprint`, lifetime |
| `POST /reviews/{plan_id}/approve` | `request_id`, `expected_revision`, `fingerprint`; no authority/effect change |
| `POST /reviews/{plan_id}/deny` | Same fields; running authority unchanged |
| `POST /reviews/{plan_id}/apply` | Same fields, approved revision; fresh current grant/epoch |
| `POST /revoke` | `request_id`, `expected_revision` from `grant_record_revision` |

IDs/revisions are 32 lowercase hex characters, fingerprints 64; supported scopes
are `command:<binding-id>`, `connector:<connector-id>` and
`event:<subscription-id>`. Unknown fields are denied.
No native-review creation endpoint, client-authored context or raw-secret input
exists here. Errors are fixed redacted codes, responses are not cached. These are
admin control endpoints, **not a new public application SDK/wire schema**.

An exact same-actor/request retry returns `historical: true, replayed: true` and the
original result, not a new live approval. Changed requests conflict. Current status
must be checked separately; old apply receipts are not execution tokens.

## Extensions management screen

The administrator-only entry appears on installed manageable application cards,
not staged packages, Agent modules, widgets, themes or languages. Core still
authenticates every request; the browser role flag is only a presentation filter.
Opening performs a read only, without adopting, stopping or approving anything.

The bounded selector contains at most 32 local native reviews that Core verifies
against the current key, exact subject, native trust and current policy. Revoked,
tampered and stale reviews are omitted. An unreadable old grant is reported as
`unavailable`, never effective; it does not hide an otherwise valid fresh review.
This read-only status behavior does not loosen effect admission or issue trust.

The screen shows resolved command/sensor devices and declarations, exact connector
origin/operations and credential reference/version/kind, and event source device,
type, capability, handler, acknowledgment and backlog bound, never credential values
or full private configuration. Resource acknowledgment is permission review only,
not an assertion that code is trustworthy. Supported whole bindings are selected
together; optional omission/narrowing is not claimed by this first profile.

Approve and apply remain separate buttons. First adoption cannot be applied to a
running/unconfirmed installation; no automatic disable or backup verification is
performed. Expiry disables decisions; actor/resource/recovery conflicts clear the
review. Historical/replayed receipts are not treated as live approval. Unconfirmed
network outcomes are shown without an automatic mutation replay. Refresh creates
no rights and discards the current draft. Requests use fresh browser-random IDs;
no browser grant, native trust or approval cache is written.

Revocation has a separate confirmation and the current sealed-grant revision.
Pending requests prevent duplicate sends and dialog dismissal; late unmounted
responses cannot update a new target. Read-only status explains compatibility
access separately from effective reviewed grants. Unsupported applications remain
unsupported; the screen does not manufacture an executable frontend/sandbox proof.

The screen uses existing theme tokens/dialog/button primitives and dynamic module
IDs. English/Bulgarian fallbacks use the existing translation override mechanism.
Fixture-based browser inspection covered desktop light EN, desktop dark BG and
390px mobile dark BG, wrapping, dialog scrolling, separate decisions and revoke
confirmation. These browser fixtures do not connect to Core or Raspberry and
are not a real permission rollout or an end-to-end production claim.

## Persistence, keys and recovery

Migration `dab239e0f1a2` follows `c9d128d9e0f1`, adds four Core-private sealed-record
tables and the opt-in `enforced` mode. Existing identities, configuration, device
bindings, compatibility modes and history are preserved; no grant is backfilled.
Complete precreated schemas must match frozen DDL; partial/corrupt schemas fail
without repair. Empty unused downgrade is supported; retained history/enforced
installs block destructive downgrade and require verified recovery instead.

The POSIX store requires Core-owned private permissions and binds its key to local
Core identity/recovery generation. Records are bounded and authenticated with
domain-separated HMAC. Key administration authenticates/audits the current admin.
First-provision retry reuses the same valid key; rotate/recover are explicit CAS
operations (`--expected-key-id`) and stale retries fail. File replacement cannot be
atomic with DB audit: a crash may leave a replacement key, but never a fabricated
review/grant. Do not restore an old key to force old grants valid.

Restore/rollback/reset fences retain evidence while invalidating current authority.
A copied private key does not bypass a fresh recovery generation. After recovery,
explicit local `recover-key`, fresh native attestation and permission review/apply
are needed. Neither reapproval nor recovery releases uncertain jobs or replays work.
Backup/export retains authority tables as evidence; this report does not claim a
complete portable backup/UI restore rehearsal or interrupted-stage recovery.

## Initial event-delivery denial boundary — delivery history

The first event slice rejected new deliveries for `enforced` and `review_required`
installations. A manifest subscription is not an approved event grant. That initial
command/connector-only slice added no positive event approval. The subsequent
scoped-consumption delivery below supersedes that limitation, not the denial rule.

Compatibility deliveries retain their existing event ID/idempotency contract.
Every pending attempt rechecks the current installation/artifact, manifest
permission, consumed capability, subscription event/capability, configured source
and device revocation. Denied backlog becomes a bounded dead letter with its
original event and cursor evidence retained; subsequent retries cannot re-enqueue
that terminal delivery or increment its terminal count again. Disabled apps still
retain their pending backlog under the existing lifecycle behavior.

After package/key preflight, the real gateway's callback conditionally locks the
same compatibility application epoch/artifact, then the source device. It rereads
the bindings and passage correlation, commits the attempt and releases DB locks
**before** service IPC. A mode/epoch/disable/rebind/revocation committed before
admission denies dispatch; a later revocation cannot recall an admitted delivery.
Gateway IPC pins the socket paired with the preflight transport key, avoiding
lazy ORM reload/retargeting after the callback commits. Stored package defaults
are copied for configuration resolution instead of mutated by another binding.

These checks do not introduce event publication, quotas/grants, a distributed
exactly-once worker, an uncertain-handler reconciliation policy or replay-safe
external side effects. Existing bounded transient retries keep their original
event idempotency key; handlers remain responsible for their external-effect
idempotency. Positive scoped consumption was left for the following delivery.

Verification: 25 event tests and 11 scheduler tests passed together on Windows
with disposable SQLite files (**36 passed**). Coverage includes a separate real
DB writer between gateway preflight and admission, denied/current-state retries,
cached ORM snapshots, source revocation, isolated configuration defaults, durable
attempt visibility and a writer committing during controlled service I/O. The
gateway, command, application access and job/startup regression cases also passed.
One older restore fixture initially lacked the migration-seeded guard singleton;
its test setup was corrected, leaving real recovery's fail-closed policy intact,
and the complete scheduler set passed again. Python compilation and whitespace
checks passed. The gateway is real; its package loader/service transport are
controlled. No Linux/socket/OS-isolation, PostgreSQL or live Raspberry proof,
frontend build, full release suite, deploy, commit/push or release is claimed
for this backend-only follow-up.

## Scoped event consumption — local follow-up

The existing administrator review/approve/apply/revoke flow now supports a whole
`event:<subscription-id>` binding for an installed reviewed-native headless app.
It reconstructs the configured source device and its current selected capability
through the common provider-neutral registry. The source revision pins actual
device/control/credential, provider/module artifact and runtime evidence; it is
not a caller-authored device or a declaration-only capability.

The review includes the exact event type, consumed capability, source-device
binding, internal command handler, required idempotency, `after_commit`
acknowledgment and declared backlog bound. Unsupported publication, emitted
handler events, jobs, public routes, platform/frontend and other authority families
still block this profile. These are whole-binding grants, not arbitrary event
payload filters or optional subsets. Approve alone never grants consumption.

Core-private context/selection/policy snapshots use version 2 only for event
subjects. Version 1 command/connector records retain their prior canonical bytes,
fingerprints, policy adapter identity and exact request-retry shape. Unknown versions
and mismatched context/selection versions fail closed; this is not a public SDK
or manifest version bump. SDK 1.3 remains unchanged.

The broker checks current exact grants before enqueue and again before each
dispatch. After gateway preflight, admission rechecks the validated subscription,
artifact/configuration, installation epoch and current source under the existing
key/authority/application/device locks. The attempt is committed and locks released
before service IPC. Revocation/drift committed first wins; already admitted work
cannot be recalled. No grant/native trust is inferred from the manifest or UI.

Migration `ebc34af102b3` follows `dab239e0f1a2` and adds a nullable delivery
`authority_epoch` without backfill. Legacy queue rows retain NULL and evidence;
they cannot acquire event rights by adoption. New enforced backlog belongs to its
original approval epoch: revoke/reapply, handler/configuration drift or recovery
cannot silently replay it under fresh rights. Denied backlog retains its existing
terminal cursor/evidence. A used epoch or retained sealed authority/enforced
installation blocks destructive downgrade. Unused legacy-only downgrade is tested.

Within an unchanged valid grant, existing bounded transient retries still use the
original event ID/idempotency key. This is not distributed exactly-once delivery
or automatic reconciliation of an ambiguous external action. Handlers must keep
external effects idempotent; recovery/reapproval does not authorize a new payment,
physical action or replay of old backlog.

Local evidence: 128 backend management/source/subject/event-grant tests passed on
Linux (one non-POSIX-only test skipped), and six migration checks passed, including
populated queue preservation, model parity, no grant backfill and downgrade refusal.
The final event-grant run passed 23 tests, including the actual admin API, all three
generic provider paths, foreign sources and approval-epoch backlog denial. The
context/policy/compatibility-event regression run passed 178 tests on Windows.
The frontend dialog's 18 tests, type checking and production build passed.
Desktop light EN, desktop dark BG and 390px mobile dark BG were inspected, including
resource wrapping, modal scrolling and disabled approval before acknowledgment.
The owner accepted this additive event-resource view on **2026-10-09**.
Browser review uses only isolated UI fixtures, not real rights or live devices.
The actual gateway/package/key/SQLite admission is tested; service IPC is controlled.
No live rollout, full release suite, deploy, commit/push or release is claimed.

## Local verification and remaining acceptance

Targeted checks use disposable databases/artifacts and no live physical/fiscal/
connector operations. External HTTP and lifecycle helpers are controlled transports,
but keys, SQLite transactions, signed sessions, routes and broker admissions are real.

- Native trust versus permission approval; tampered/missing evidence and foreign
  actor rejection; role/session revocation; private data/error redaction.
- Approve without apply, disabled-only adoption, command/one-use permit/connector
  admission, grant/native revocation and historical lookup without replay.
- Resource/key/policy/recovery drift, expiry/reboot, concurrent apply and revocation
  between artifact preflight and durable admission.
- POST success/lost response and revocation during external I/O; lifecycle helper
  called outside the key lease; fresh review after same-artifact restart.
- Offline SQLite restore fence plus explicit fresh-key/native/permission regrant.
- Populated migration/model parity, full/partial precreated schemas, no backfill,
  evidence retention and non-destructive downgrade restrictions.
- Existing compatibility brokers and guarded resource/lifecycle writers.

Results: 38 POSIX management/API/broker/CLI/status tests passed; the key/subject checks
passed 74 tests with three environment-specific skips (foreign-UID root test and
two non-POSIX-only tests). Guarded writer/lifecycle/policy regression checks passed
285 tests; compatibility command/connector/recovery checks passed 42 tests. Current
grant migration checks passed five tests and historical review-store migration
checks passed ten. These are targeted runs, not a full release-suite claim. Python
compilation, local CLI help and documentation link/whitespace checks also passed.
The focused frontend run passed 38 tests (16 new dialog/response-boundary tests,
20 Extensions workflow tests, two shared primitive tests). Frontend type checking
and the production build passed. The release suite was not run for this UI slice.

Outstanding WP4 gates are the remaining accepted scoped
storage/event-publication/platform/frontend contracts and neutral
SDK acceptance across Standalone/Hub with Linux and mock embedded providers,
including human/kiosk and live recovery.
The next intended WP4 slice is scoped event publication. Source inspection found
that the SDK has only a private outbox, not a Core publication method, and the
broker is device-producer-only. The prerequisite producer/schema/transport
extension is [proposed for explicit owner approval](EXTENSION_PLATFORM_V2_EVENT_PUBLICATION.md),
not an implemented publication grant or an authorization-only patch.
WP3 new-artifact staging/data-recovery and WP5 malicious-code OS/browser isolation
remain separate, required gates. There is no remote/untrusted executable acceptance,
publisher ownership proof, deployed rollout, PostgreSQL race rehearsal or release
claim in this delivery.
