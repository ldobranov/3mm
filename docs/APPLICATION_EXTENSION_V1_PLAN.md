# Application Extension v1 plan

Status: completed Milestone 12 contract. All seven stages were implemented,
deployed and physically accepted on `rasp-3mm` by 2026-08-30.

## Purpose

`application-extension v1` will let a separately installed extension implement
a complete business workflow without adding its entities, vendor integrations
or screens to 3mm Core. It fills the gap between declarative
`runtime-extension v1` CRUD and frontend-only `compiled-ui v1` packages.

The first intended consumer is a separately developed application that needs
kiosk registration, staff workflows, opaque wristband or tag scans, timed
visits, consumption records and synchronization to a local point-of-sale
system. Those concepts and the selected vendor remain outside Core and outside
the generic platform contract.

## Required capability coverage

The platform milestone is shaped by the first consumer, but every requirement
is expressed as a reusable capability:

| Consumer need | Milestone 12 platform capability | Owned by the later extension |
| --- | --- | --- |
| Self-registration on a tablet | enrolled kiosk terminal, kiosk session and compiled kiosk route | form fields, validation, consent text and domain records |
| Staff review and wristband assignment | extension permissions, operator route and versioned command | approval workflow and tag-to-record mapping |
| Entrance/exit scan | `identifier.scan.v1`, event subscription, cursor and deduplication | decision whether a scan starts, stops or rejects a session |
| Accurate elapsed time | UTC event time, deterministic clock service and transactional command | tariff, rounding, grace period and session state machine |
| Allowed products and consumption | transactional extension-owned database and operator commands | preferences, restrictions, items and business validation |
| External product catalog | scheduled connector job, checkpoint and paged request support | remote field mapping and product selection policy |
| Final external account/order | protected connector, durable outbox and idempotency/manual review | remote payload and the decision when to submit or close it |
| Temporary network/API outage | local commit before delivery, bounded retry and visible sync state | operator-facing recovery wording and business resolution |
| Support and disaster recovery | audit correlation, diagnostics, backup/restore and lifecycle hooks | domain export/erase policy and extension-specific support view |

This coverage deliberately does not require Core to understand guardians,
children, wristbands, visits, products, accounts, orders or a POS vendor.

## Target data flow

```text
Kiosk/operator compiled UI
          |
          v
Core application gateway -- authentication, permission, limits, audit
          |
          v
Supervised extension service <---- Core event broker <---- Agent identifier capability
          |
          +---- extension-owned SQLite + transactional outbox
          |
          v
Platform connector broker -- destination policy + secret injection
          |
          v
External local/remote business API
```

An accepted local operation is committed to extension state before external
delivery is attempted. External failure therefore cannot erase a registration,
scan, timed session or locally recorded item.

## Package boundary

The package continues to use immutable Module Manifest v2 and adds a strict
`application-extension.json`. The contract declares, without embedding secret
values:

- service identity, runtime compatibility and health check;
- versioned queries, commands and emitted events;
- compiled UI entrypoints and their access audience;
- extension-scoped permissions required by each operation;
- provided and consumed platform capabilities;
- extension-owned state areas and forward migrations;
- outbound connector destinations and opaque secret references;
- outbox limits, retry policy and idempotency fields;
- backup, restore, rollback, disable and uninstall behavior.

The service artifact is reviewed and administrator-installed. Its dependencies
are locked and available offline from the package or an approved platform
wheelhouse. Installation cannot contact a package index, run arbitrary package
hooks or install APT dependencies. AI-generated backend services remain outside
this milestone.

Unknown fields, undeclared operations and undeclared network or hardware access
fail validation before installation.

## Versioned operation contract

The application manifest declares operations rather than arbitrary HTTP paths.
Each operation specifies:

- stable operation ID and contract version;
- `query`, `command` or asynchronous `job` behavior;
- input and output JSON schemas with strict size limits;
- required extension permission and allowed audience;
- whether an idempotency key is required;
- synchronous timeout or asynchronous operation-status contract;
- emitted event types and audit sensitivity.

Commands that create or mutate business state require a caller-generated
idempotency key. Repeating the same key with the same payload returns the stored
result; repeating it with another payload fails. Long-running jobs return an
opaque operation ID and expose bounded status instead of holding an HTTP
request open.

Errors use one generic envelope containing a stable code, safe localized
message key, correlation ID, retryability and optional field errors. Internal
tracebacks and connector responses are never returned to the browser.

## Runtime and API boundary

An application backend runs as a supervised process outside the Core API
process with a restricted service identity and writable access only to its
namespaced state. Core communicates over an authenticated local transport and
exposes a generic versioned gateway such as:

```text
/api/v1/application-extensions/<module-id>/<operation>
```

The concrete path is finalized with the contract. Core owns authentication,
authorization, request limits, correlation IDs and audit records. The extension
owns validation and transactional business behavior. Core never imports the
extension's Python modules and never branches on its module ID, entity names or
external vendor.

Long-running work is acknowledged and processed by the extension worker. It is
not executed inside the Core request handler.

The generic service host owns process start/stop, a private Unix socket,
readiness, resource limits and crash backoff. Each enabled application
extension receives a distinct runtime identity and state directory. It cannot
import Core source, read the Core database or call another extension's socket.
The Extension Host SDK provides only the versioned request, event, clock,
secret-reference and connector contracts.

Service activation follows the existing transactional module lifecycle:
validate package, prepare isolated runtime, migrate staged data, start candidate,
check readiness, switch registration and retain the previous healthy version.
A candidate that fails migration or readiness never replaces the active
version.

## Data ownership and lifecycle

Each application extension owns a namespaced data directory and database under
persistent 3mm state. Its service is the only component allowed to interpret
that schema. Other modules use declared service contracts rather than table or
file access.

The initial storage layout is intentionally small and backup-friendly:

```text
/var/lib/3mm/application-extensions/<module-id>/
  state.sqlite3
  files/
  runtime/
```

`state.sqlite3` supports relationships, uniqueness constraints, transactions
and an outbox record in the same commit as the business mutation. `runtime/`
contains reproducible caches and bounded transient state; the manifest marks
which paths are excluded from backup. Arbitrary tables in the Core database are
not permitted.

Schema changes are forward-versioned and tested. Installation, upgrade,
health-check and rollback are transactional. Disable stops routes, workers and
hardware subscriptions while preserving data. Uninstall and data erasure remain
separate explicit operations.

The backup manifest includes extension data, migration revision, connector
outbox and required secret references. Restore validates compatibility before
activation and must not silently bind a restored secret reference to an
unrelated credential.

Because a vertical application may hold personal or child-related data, the
manifest also classifies state as public, private or secret and declares
retention, export and erasure operations. Core does not inspect domain rows, but
it can require that these lifecycle operations exist and audit who invoked
them. Diagnostics contain counts and health only, never names, tag values or
raw connector payloads.

## Access audiences

The application contract distinguishes:

- `public`: deliberately anonymous, read-only or narrowly submitted actions;
- `kiosk`: short-lived, device-scoped interaction without a normal user
  account;
- `operator`: authenticated daily workflow permissions;
- `administrator`: configuration, mappings, recovery and lifecycle actions.

Routes and operations declare their audience independently. A public menu item
does not make its API public. Kiosk enrollment and sessions are revocable,
short-lived, rate-limited and unable to obtain normal administrator access.
Extension permissions are assignable through the existing role system without
hardcoding new business roles into Core.

Permission IDs are namespaced by module, for example
`<module-id>:session.manage`; role names remain administrator-defined. The
manifest requests permissions but never creates an all-powerful role. Core
enforces the operation permission before forwarding, and the service repeats
the decision against signed caller context for defense in depth.

An administrator explicitly enrolls a browser as a kiosk terminal. Enrollment
creates a revocable terminal identity scoped to one extension, device label,
route set and operation set. The resulting short-lived kiosk sessions are not
normal user tokens, cannot access the main application APIs and survive browser
refresh without placing a permanent credential in a URL. Lost tablets can be
revoked independently.

Compiled application routes add explicit `audience`, `required_permissions`
and `layout` metadata. A `kiosk` layout may be full-screen, but it still uses
the platform theme, locale, accessibility and responsive tokens. An operator
route uses the normal application shell. Navigation visibility is derived from
the same server-authorized audience and permissions rather than from a label or
client-only route guard.

## Identifier and hardware events

The first generic Agent capability is `identifier.scan.v1`. An adapter may read
a keyboard-style USB reader, serial reader, NFC/RFID device or deterministic
mock driver. The Agent publishes only an opaque identifier, reader identity,
timestamp, sequence/idempotency ID and device health metadata.

The contract also includes device ID, adapter kind, signal/scan metadata when
available and a schema version. It does not claim continuous presence from a
reader that only detects deliberate taps. Direction, entrance/exit meaning and
session transitions belong to the application workflow, not the driver.

Personal data is never written to a tag and never emitted by the Agent. The
application extension maps the opaque identifier to its own record. Duplicate
delivery is expected and handled idempotently. Offline Agent buffering uses the
existing bounded event path.

Core adds a generic event broker cursor for authorized application services.
Subscriptions declare event type, device scope and consumed capability. Events
are acknowledged only after the service commits its processing result. Service
restart, Agent reconnect and duplicate delivery must not create a second state
transition. Backlog and dead-letter limits are observable.

## External connector boundary

Application extensions declare named connectors to administrator-approved
destinations. A platform connector broker enforces scheme, host, port, path
prefix, request/response size and timeout. The extension service does not get
unrestricted network access for declared integrations.

Credentials are stored by the platform secret service and referenced by opaque
ID. The broker injects Basic, bearer or API-key authentication according to the
connector configuration; the secret is not returned to the extension service
or Vue, included in package configuration, logged or sent to AI. Administrators
can replace a credential without reinstalling the extension.

External mutations use an extension-owned durable outbox containing a stable
operation ID, payload hash, remote idempotency identity, attempt count,
next-attempt time and terminal result. The business mutation and its outbox row
are one SQLite transaction. The broker performs one declared request; the
extension worker owns business retry/reconciliation policy.

Retries use bounded backoff. An explicit remote rejection is terminal. A
connection failure before sending may be retried. A timeout or disconnect after
submission is `ambiguous`: it is reconciled through a remote lookup or
idempotency mechanism when available, otherwise it enters manual review instead
of being repeated blindly. This distinction is required because some external
systems deduplicate account creation but not each line added to an account.

Read-side catalog synchronization supports bounded pagination, a persisted
cursor/watermark, full-resync fallback and atomic publication of a completed
snapshot. A page failure cannot replace the last complete catalog. The
extension decides remote field mappings; the platform supplies only scheduling,
checkpoint and connector primitives.

A deterministic mock connector can simulate success, validation error,
unavailability, slow response, ambiguous timeout, duplicate response and
paginated catalog changes. Automated tests never require a real vendor server.

### First-consumer compatibility notes

These notes validate the generic connector design against the intended separate
extension. They do not add vendor concepts to Core:

- Barsy uses a local HTTP API with Basic Authentication, so the connector
  broker must support administrator-approved local destinations and
  broker-injected Basic credentials without returning them to the extension UI.
- Business location and POS context (`bid` and `POSKEY`) must be configurable
  per connector instance. Sensitive values use opaque secret references;
  non-secret identifiers remain ordinary extension configuration.
- Article synchronization may be incremental by last-update marker and paged,
  so scheduled jobs need persisted watermarks, pagination bounds and atomic
  completed snapshots.
- Account placement supports a stable UUID that protects account creation from
  duplicates. The extension must persist that UUID before its first attempt.
- Equivalent idempotency is not guaranteed for every subsequently added line.
  The first extension should therefore keep the active account locally and
  prefer one final submission at checkout until a verified reconciliation
  strategy exists.
- A remote timeout can occur after the server accepted a request. The platform
  must preserve `ambiguous` separately from `failed` and require lookup or
  operator review before retrying a non-idempotent mutation.
- Fiscal calculation, payment, receipt printing and reversal remain owned by
  Barsy. The 3mm extension prepares and transfers domain-approved lines but does
  not impersonate the fiscal system.

## Scheduler, clock and local continuity

The host provides a small persistent job scheduler for declared extension jobs.
Jobs have stable IDs, UTC schedules, single-run leases, bounded execution time
and catch-up policy after reboot. It supports periodic catalog refresh, outbox
delivery and reconciliation without becoming a general workflow engine.

The SDK supplies an injectable UTC clock so elapsed-time and retry behavior can
be tested deterministically. Business duration uses persisted event timestamps;
wall-clock display uses the configured timezone. A Core restart, service crash
or connector outage cannot reset an active timed session.

## Operations and observability

Core exposes generic administrator status for each application extension:

- service version, readiness, restart count and migration revision;
- event cursor, pending backlog and last processed event;
- scheduler lease/next run and last job outcome;
- connector health without credential or payload disclosure;
- outbox counts by pending, retrying, ambiguous, failed and succeeded state;
- backup compatibility and last successful restore validation.

The extension may add a richer operator view through compiled UI. Retry,
discard or manual resolution actions require explicit extension permissions and
audit records. Correlation IDs join the browser command, Core gateway, service
transaction, Agent event and connector attempt without exposing personal data.

## Milestone 12 stages

1. Define and contract-test `ApplicationExtensionV1`, operation schemas,
   extension permissions, event subscriptions and lifecycle declarations —
   completed locally on 2026-08-28.
2. Add the offline-installable supervised service runtime, restricted service
   identity, Extension Host SDK, authenticated local transport, generic Core
   gateway and health/rollback integration — completed locally on 2026-08-29.
3. Add extension-owned SQLite/files, forward migrations, transactional outbox,
   data classification and backup/restore participation — completed locally
   on 2026-08-29.
4. Add public/kiosk/operator authorization, kiosk terminal enrollment and
   generic compiled route/menu support based on server permissions — completed
   locally on 2026-08-29.
5. Add the application event broker and `identifier.scan.v1` with deterministic
   mock, Agent buffering, cursor/acknowledgement and permission enforcement —
   completed and physically accepted on 2026-08-29.
6. Add the secret store boundary, destination-restricted connector broker,
   persistent scheduler/checkpoints, retry/reconciliation states and generic
   operational status — completed and deployed on 2026-08-29; migration,
   sandbox write boundary and Unix listener verified on Raspberry.
7. Validate the neutral reference package on laptop mocks and physical
   Raspberry before starting a real vertical application extension — completed
   on 2026-08-30, including failure, restart, backup/restore, rollback and
   disable/re-enable acceptance.

## Neutral reference acceptance flow

The reference package uses generic participants, tokens, sessions, item
entries and sync envelopes. It exists only as a test fixture and is not the
future child-center extension.

1. Install and enable the package without changing Core or Agent source.
2. Enroll one browser as a kiosk and use it to submit a limited registration;
   verify that it cannot open operator, admin or generic Core APIs.
3. Give a normal user one extension operator permission and approve the record
   without granting administrator access.
4. Attach an opaque mock token and deliver a scan event that opens a timed
   session. Redeliver the same event and prove no duplicate transition occurs.
5. Add an item through an idempotent operator command, then deliver a second
   scan that closes the session and records deterministic duration.
6. Stop the mock connector. Commit a final local operation and verify it stays
   usable with a visible pending sync state.
7. Restart Core, Agent and the extension service; verify the active session,
   event cursor, scheduled job and outbox survive.
8. Restore the connector and prove one successful remote submission. Simulate
   an ambiguous timeout and prove the item enters reconciliation/manual review
   instead of being submitted blindly again.
9. Run a paginated catalog sync, fail a middle page and prove the last complete
   catalog remains active; then complete an incremental sync from its checkpoint.
10. Rotate the connector credential and revoke the kiosk terminal without
    reinstalling the package.
11. Create and restore a portable 3mm backup and verify application records,
    migration revision, event cursor and pending outbox are preserved without
    leaking the credential.
12. Attempt a broken upgrade and verify the previous service, UI registration
    and compatible schema remain active. Disable it and verify routes, jobs and
    subscriptions stop while data remains.

All twelve steps passed on the physical Standalone Raspberry. The accepted
reference package is `org.3mm.application-reference` version `1.0.1`; the
intentionally unhealthy `1.0.2` candidate was rejected while `1.0.1` remained
usable. The test also exposed and fixed recovery edge cases: restore now
recreates excluded runtime directories with the correct ownership, and it
refreshes the privileged helper after atomic application-state replacement so
later lifecycle operations see the restored filesystem.

## Acceptance criteria

- installing the neutral package adds its service, UI routes and permissions
  without a Core code change or restart-specific module branch;
- kiosk terminal, operator and administrator operations are independently
  enforced by the server, not only by the Vue router;
- a normal operator can execute declared daily operations without receiving
  global administrator access;
- a mock identifier scan reaches only a subscribed, authorized extension and
  duplicate delivery does not duplicate business state;
- active timed state, scheduler leases, event cursors and accepted local
  mutations survive service/Core/Agent restart;
- an external mutation survives connector downtime and is delivered once or
  enters explicit manual review after an ambiguous result;
- failed paginated synchronization cannot replace the last complete catalog;
- secrets remain absent from manifests, browser responses, logs, diagnostics,
  backups without their protected secret material and AI context;
- kiosk terminal and connector credentials can be independently revoked or
  rotated without reinstalling the extension;
- upgrade failure restores the previous healthy service and schema state;
- backup and restore preserve the extension database, outbox and compatible
  credential references;
- disabling preserves data and stops routes, jobs and hardware subscriptions;
- the complete neutral flow passes with mock reader/connector and the scan plus
  service lifecycle passes on the physical Raspberry;
- Core and Agent contain no concrete business application or vendor name.

## Non-goals

- fiscal calculation, payment or receipt printing inside generic Core;
- a universal low-code workflow engine in this milestone;
- arbitrary generated backend code or in-process Python imports;
- direct browser access to serial, USB, RFID/NFC or external-system secrets;
- automatic continuous-presence claims from a tap-only NFC/RFID reader;
- encoding personal data on a wristband or tag;
- blind replay of an external mutation after an ambiguous timeout;
- beginning the child-center application before the neutral acceptance package
  passes.

## Handoff to the separate child-center extension

With Milestone 12 accepted, the vertical extension can be built from:

- one application service owning guardians, children, tag assignments, visits,
  preferences, consumption, product mappings and synchronization history;
- one kiosk route for limited parent registration;
- operator routes for approval, tag assignment, entry/exit and consumption;
- administrator routes for tariff, reader, retention and connector settings;
- one `identifier.scan.v1` subscription scoped to selected readers/devices;
- one Barsy connector instance and protected credential references;
- a local active account plus durable final-checkout synchronization.

That project will still need explicit business decisions about tap versus
automatic presence detection, time rounding/tariffs, whether an open external
account is updated during the visit or only at checkout, and whether the cashier
or the extension initiates finalization. Milestone 12 must support either choice
without another Core schema or routing change, but it does not choose the
business policy.
