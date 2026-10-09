# M20 WP4 — scoped application event publication

Date: 2026-10-09. Status: **contract, installed-package review and scoped SDK/runtime admission implemented locally**.
Scope: common Standalone/Hub/local application platform, not Fleet-only.
The first-slice section is delivery history. Current runtime behavior and remaining
WP4 gates are recorded below; no deployment or WP5 isolation is claimed.

## Proven gap

The approved next task was scoped publication through existing SDK/broker paths.
The initial source audit, before these deliveries, found that this path did not exist:

- [Application SDK 1.3](../three_mm_application_sdk/__init__.py) has a private
  transactional outbox, but no Core event-publication client method. Outbox event
  labels also describe extension-owned external work; draining the whole outbox
  into Core would change existing application behavior.
- [Application operations](../three_mm_protocol/application_extension.py) declare
  `emitted_events` as event-type strings. They declare neither publication payload
  schemas nor producer scopes. An operation's output schema is not its event schema.
- [Package validation](../backend/services/module_packages.py) checks provided
  capabilities and `events.publish` against those declarations. This is declaration
  consistency, not implementation of publishing, payload validation or grants.
- [Platform socket](../backend/services/application_platform.py) dispatches
  commands/connectors/checkpoints/identity/peers, not publication. Enforced mode
  currently refuses unsupported actions.
- [Device ingestion](../backend/routes/device_events.py) authenticates the device
  credential and requires its real device identity. The
  [event envelope](../three_mm_protocol/device_event.py),
  [persistent event](../backend/db/device.py) and
  [application broker](../backend/services/application_events.py) require a device
  producer; subscription scope is a configured device.

Do not create a fake Device/credential/provider for an application, attach its
event to somebody else's device or let an arbitrary service claim a producer ID.
Do not issue a positive publication grant for an effect Core cannot yet validate.
Existing event-consumption grants and legacy behavior stay unchanged.

## Owner-approved minimum extension

Reuse and extend the current event broker; no second event bus or publisher-specific
hardware logic. The owner approved the following scope; the first slice below
fixes additive field names/versions without enabling runtime publication:

1. **Producer ownership:** device and application producers have distinct typed
   identities. Core derives an application's logical installation/incarnation from
   its authenticated signed service session, not caller-supplied fields. Existing
   device authentication and identities stay intact.
2. **Publication declaration:** exact stable publication ID, event type, payload
   schema and size bound. Bind these to the exact validated artifact and declaring
   operation. Version this additive contract independently; old `emitted_events`
   strings remain declarations, not inferred unrestricted publication permission.
   Arbitrary operation output or local outbox content is not an event schema.
3. **Durable ingestion:** common producer-aware event representation behind the
   existing broker. Preserve device event/record IDs, deliveries and cursors through
   an explicit non-destructive migration/adapter; no copying into competing streams.
   Acknowledgment follows durable admission, not an attempted socket send.
4. **Idempotency:** an exact owned event retry returns its original receipt;
   changed content/owner/identity conflicts. Recovery or new approval cannot turn an
   already recorded event into another publication. Historical receipt access does
   not authorize a new effect or automatically replay subscriber work.
5. **Authority:** the current native-review/approve/apply/revoke cycle gains exact
   publication scopes. Recheck schema/bounds, authenticated producer, artifact,
   configuration, recovery generation and current approval epoch under the same
   short authority transaction before event admission. No lock spans IPC.
6. **SDK adapter:** add a bounded publication call over the existing signed platform
   transport. Keep SDK 1.3/old clients compatible; unsupported Core reports a clear
   refusal, never falls back to device ingestion. Applications choose which outbox
   items represent Core publications; no automatic drain or background replay.
7. **Consumers:** publication alone grants no other application's stream access.
   Preserve device subscriptions. Application-producer subscription scopes require
   their own explicit declaration/ownership/handler contract before delivery;
   no any-producer subscription, global stream, websocket or public exposure.

Acceptance must cover declared/undeclared and foreign/reserved types, invalid and
oversized/nested payloads, missing/revoked/drifted grants, two applications, exact
retry/content conflict, admission/revocation races, lost acknowledgment, restart/
restore, and old device events/cursors/SDK outbox behavior. Standalone and Hub use
one implementation. Retain denial for unsupported families and WP5 isolation gates.

## First implemented slice — contracts, not runtime admission

[Shared authoritative models](../three_mm_protocol/application_event_publication.py)
now define independently versioned, closed declarations, requests, typed producers,
an internal envelope candidate and historical receipts. No Core/Agent/SDK/runtime
imports, new dependency, DB writes, authorization grants or transport calls are
needed to use these validators. The existing descriptor and device wire models
are unchanged; SDK 1.3 is unchanged.

- `ApplicationEventPublicationsV1`: `publication_contract_version: 1`, module ID,
  exact version, service wheel digest and 1–32 unique publications. Each declaration
  contains `publication_id`, `operation_id`, `event_type`, `payload_schema` and
  `max_payload_bytes`. Cross-document validation requires the actual descriptor's
  identity/digest and an emitting idempotent command/job. It is not package trust,
  proof of which operation is executing, or approval. Full ZIP digest/current
  installation/configuration/recovery/grant pins remain runtime responsibilities.
- Payload schemas reuse the existing capability-contract dialect: closed nested
  objects and bounded scalars, depth at most four, at most 32 object properties,
  finite numeric bounds and strings at most 512 characters. Arrays, refs, regexes,
  arbitrary formats and unknown keywords are refused, not ignored. Each schema is
  bounded to 8 KiB; the whole declaration to 64 KiB and existing JSON item/depth
  limits. No new unrestricted JSON Schema interpreter is introduced.
- `ApplicationEventPublishRequestV1`: `publication_request_version: 1`, `event_id`,
  `publication_id`, `payload`, `occurred_at`. No producer, device, user, event type,
  operation or authority fields may be supplied. Exact declaration selects the
  event type; Core must supply authenticated installation/incarnation separately.
  The bounded raw parser refuses duplicate keys, non-finite numbers, invalid UTF-8,
  invalid Unicode, oversized/nested structures and coerced versions/timestamps.
  Normal Pydantic JSON parsing alone is not the ingress parser.
- Device producer: `kind: device` with its real `device_id`. Application producer:
  `kind: application`, current `core_installation_id`, decimal logical
  `application_installation_id`, `incarnation`, `module_id`. No fake Device row or
  runtime-process ID is needed. Producer model validity alone never authenticates
  a caller. Application declarations cannot claim the `core.*` namespace or
  existing Core-owned device audit event types.
- A new publication needs an aware timestamp, normalized to UTC, and exact closed
  payload validation. Default payload limit is 8 KiB; declared limits are at most
  60 KiB inside the 64-KiB request budget. JSON values are not coerced; booleans are
  not integers, Python-only containers/bytes and malformed nested values fail.
- `PlatformEventV1` is an internal candidate, not a new ingestion API. Its pure
  legacy device adapter retains IDs/types/payloads, treating old naive timestamps
  as UTC without changing the original event. A bounded internal-only 4-KiB metadata
  allowance preserves valid legacy messages at the existing 64-KiB wire limit.
  The original device item/depth budget and serialized JSON values are retained
  too; fixed internal metadata cannot shrink a valid legacy message's budget.
  No DB stream, delivery/cursor or old device authentication is replaced.
- Content SHA-256 covers the versioned, domain-separated canonical envelope,
  exact producer/IDs/type/payload and normalized occurrence time. Object key order
  and equivalent timezone spelling do not change content identity. Authority epochs,
  current configuration and receipt timestamps are not event content. Receipts
  (`publication_receipt_version: 1`) contain exact producer/event/publication IDs,
  content digest and original commit time; matching is pure comparison, not admission,
  a grant, a response from a running Core or permission to dispatch a subscriber.
  Future historical retries must compare the original stored event/declaration,
  not reinterpret content through a changed current declaration/schema.

The public schema catalog adds `application-event-publications.v1`, candidate
document `application-event-publications.json`, explicitly marked
`runtime_support: contract_only`. It is authoring guidance: the ZIP validator,
activation and signed runtime transport do not interpret/authorize this declaration yet.
Old descriptors cannot self-upgrade through schema catalog presence.

Evidence: **141 focused tests passed on Windows**, covering this contract/parser,
legacy device events including the byte-limit boundary, old application descriptors,
capability schemas, independent structural exports and SDK 1.3 private outbox/
identity behavior. **48 existing Core broker/event-authority tests also passed on
Linux** (288 existing warnings). No frontend file changed; no frontend build or live test was
needed for this non-visual slice. Full release and runtime publication acceptance
are not claimed.

## Runtime follow-up — installed, reviewed-native publications

The package validator now accepts the optional root document
`application-event-publications.json` for application ZIPs only. Its identity,
version, service wheel digest, emitting operation and event types must exactly
match the authoritative descriptor. Every emitted type needs an exact declaration;
old descriptors without this document remain compatible, not implicitly authorized.
Inspection includes publication declarations in the exact-artifact access diff.
The public catalog now reports `runtime_support: reviewed_native_scoped`, not
`contract_only`; this is not an isolation or installability claim.

The existing native-review / review / approve / apply / revoke flow now binds
`publication:<publication_id>` alongside command, connector and subscription scopes.
Internal context/policy version 3 adds these resources; version 1/2 shapes remain
supported. Grants pin the original schema, byte limit, declaring operation, wheel,
whole ZIP, configuration identity, installation incarnation and recovery generation.
The same admin dialog displays these exact resources. Approval alone cannot publish.
Unreviewed/native-unattested, disabled, stale, revoked or unsupported installations
cannot publish new events. This does **not** prove that a particular human or operation
caused a service's event: operation binding is a declaration/trust boundary, not a
caller-authored execution attestation or a substitute for human application access.

Signed `event.publish` runs over the existing private platform socket. There is no
new public HTTP ingest route. Core derives the producer from the actual authenticated
service's logical installation/incarnation and current Core identity. It validates
the bounded request and current grant under the existing key/authority lease, commits
the event and original receipt, then sends the ACK. No lock spans socket or other
external I/O. Caller-owned producer/device/type/actor fields are rejected.

### One journal and recoverable migration

Alembic revision `fcd45b0213c4` extends the existing `device_events` journal with
`producer_kind`, typed application producer, original publication declaration,
receipt and admission epoch. An application row has no device FK; no fake Device,
credential, module installation or parallel event stream is created. Device row IDs,
delivery FKs, pending backlog and cursor counters remain unchanged. Legacy device
writers retain a database default of `device`. An explicit check distinguishes
device and application rows. Partial or incorrectly precreated schemas are refused.
Downgrade with application/authority history is refused before DDL; recover using
a verified compatible backup instead of deleting history.

Only new admission requires current authority. An exact owned retry compares the
original stored producer/declaration/content and returns the original durable receipt,
including after disable/revocation, changed current schema, key rotation or an offline
restore fence. It does not re-admit, enqueue work or restore rights. Changed typed
content, timestamp, owner, publication ID or incarnation conflicts; `1` and `1.0`
are distinct event content. The device credential path cannot borrow an application's
receipt. A failed commit returns no ACK. In-flight/nonblocking key contention may
fail closed; an application may retry the same persisted identity after the first
commit. The Core/SDK do not generate a replacement event ID or automatically replay.

Existing device-only subscriptions do not receive application-producer records.
There is deliberately no cross-application consumer grant, any-producer/global
stream, websocket or public exposure. Application consumers need a separately
accepted typed producer/handler ownership contract before delivery can be enabled.

### Public SDK 1.3 adapter

`ApplicationPlatformClient.publish_event()` is additive. Keep SDK 1.3, earlier
supported clients, private SQLite migrations and existing outbox behavior. Example:

```python
# Persist this ID, timestamp and payload with the application's business change.
# Read the SAME values back for every retry; do not regenerate them on timeout.
receipt = context.platform.publish_event(
    "record_changed",
    event_id=persisted_event_id,       # evt_ followed by 32 lowercase hex digits
    occurred_at=persisted_aware_time,  # datetime with a timezone
    payload={"value": persisted_value},
)
```

The current package must declare `record_changed`, `events.publish`, its provided
event type and an exact bounded payload schema, and have an applied local resource
grant. The SDK validates the signed matching receipt. Known older-Core unsupported
responses become a clear feature refusal; authorization errors remain authorization
errors. There is never a device-ingest fallback, automatic outbox drain, background
replay or implicit permission approval.

### Evidence and remaining gates

Targeted Linux checks use real installed ZIPs, protected POSIX review keys, signed
administrator sessions, SQLite transactions and a real signed Unix socket/SDK client.
They cover exact scope/schema/wheel binding, approval versus apply, common Standalone/
Hub admission, foreign/invalid requests, cross-owner/device/reincarnation collisions,
lost ACK, failed commit, revoke-before-admission, key/config/artifact/recovery drift,
restart, real offline recovery fencing and two-connection same-ID races. Populated
migration checks preserve backlog/cursors and test safe downgrade refusal. These are
disposable local fixtures, **not** Raspberry/production recovery acceptance.

The first runtime regression batch passed **117 Linux tests** (915 existing warnings).
The additive dialog passed **20 frontend tests**, type checking and production build;
isolated light-desktop/dark-mobile browser inspection found no clipped controls or
horizontal overflow. Package/protocol compatibility checks passed **115 tests**.
The targeted Linux publication/SDK/journal-migration run passed **48 tests**
(325 existing warnings). The final journal migration run passed **9 tests**, also
checking used-authority downgrade refusal and exact precreated uniqueness/FK/default
constraints; the broader preceding authority migration regression passed **13 tests**.
The earlier Windows SDK/journal batch passed **22 tests**;
backup/portable-recovery/device-transport compatibility passed **26 tests**.
No Core/Agent dependencies were added and no live data or rights were changed.

WP4 remains open for the accepted scoped storage/platform/frontend-host boundaries
and neutral public-SDK human/kiosk/Standalone/Hub acceptance with explicit live recovery.
Cross-application consumers, staged new-artifact adoption and malicious-code isolation
are not silently enabled by this publication delivery. No commit/push/release/deploy
has been performed for this step.
