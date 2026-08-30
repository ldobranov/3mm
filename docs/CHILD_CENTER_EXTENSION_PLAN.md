# Child Center Extension plan

Status: ready to start as a separate vertical application extension after the
physical acceptance of Milestone 12. This is not a Core milestone and must not
add child-center entities or vendor-specific behavior to Core or Agent.

## Objective

Build an installable application extension for a child activity center that
continues its essential local workflow during Internet or point-of-sale
outages. The extension owns guardians, children, identifiers, visits, tariffs,
consumption and external mappings. It consumes only generic 3mm contracts.

Initial module identity:

- module ID: `org.3mm.child-center`;
- package version: `0.1.0`;
- platform contract: `ApplicationExtensionV1`;
- initial location: `modules/child-center`;
- starting reference: `modules/application-reference` patterns, without
  renaming or modifying the accepted reference fixture.

## Platform boundaries

The extension may use:

- the supervised application service and Extension Host SDK;
- extension-owned SQLite storage and forward-only migrations;
- public, kiosk, operator, administrator and internal operation audiences;
- extension-scoped permissions and server-filtered compiled routes;
- `identifier.scan.v1` events scoped to configured devices/readers;
- durable jobs, transactional outbox and synchronization checkpoints;
- destination-restricted connectors with opaque credential references;
- application backup/restore, disable, upgrade and rollback behavior.

The extension must not:

- add guardians, children, visits, tariffs, wristbands or products to Core;
- add a `child-center` branch or concrete module name to Core or Agent;
- read the Core database or another extension's storage;
- expose personal data, tag identifiers, credentials or connector payloads in
  logs, diagnostics, package defaults or AI context;
- store personal data on a wristband, card or tag;
- infer continuous presence from a reader that reports only deliberate taps;
- perform fiscal calculation, payment, receipt printing or reversal;
- blindly retry an ambiguous external mutation.

## Business decisions to record before the first production package

The platform supports multiple policies, but the extension must explicitly
choose and test these behaviors:

1. **Scan meaning** — dedicated entry/exit readers, an operator-selected mode,
   or guarded toggle behavior when only one reader exists.
2. **Tariff calculation** — grace period, minimum charge, rounding unit,
   tariff changes during an active visit and timezone/day-boundary handling.
3. **External account timing** — keep the active account local and submit once
   at checkout, or update the external account during the visit only after a
   verified reconciliation contract exists.
4. **Checkout authority** — cashier/POS finalizes the account, or the extension
   requests finalization and waits for an explicit result.
5. **Retention** — how long closed visits, contact details and identifier
   assignments remain available before anonymization or deletion.

Recommended test defaults are one operator-selected reader mode, persisted UTC
timestamps with local display timezone, versioned tariffs, local accumulation
during the visit and one final mock connector submission at checkout. These
defaults are reversible business choices, not Core behavior.

## MVP workflows

### Kiosk registration

1. An administrator enrolls a browser as a kiosk terminal.
2. A guardian enters the minimum required contact and consent information.
3. The guardian adds one or more children without entering payment-card data.
4. The kiosk submits an idempotent registration request with status
   `submitted`.
5. The kiosk can show only its submission result and cannot browse other
   families or operator data.

### Operator approval and identifier assignment

1. An operator with the extension permission reviews pending registrations.
2. The operator corrects permitted fields and approves the family/child.
3. A scanned or manually entered opaque identifier is assigned to one active
   child assignment.
4. Reassignment closes the previous assignment instead of silently changing
   history.
5. Duplicate or already assigned identifiers fail with an explicit domain
   error.

### Entry, active visit and exit

1. `identifier.scan.v1` is delivered with a stable event ID, reader and device.
2. The extension resolves the opaque identifier only inside its private state.
3. The configured reader purpose or operator mode determines entry or exit.
4. Entry creates one active visit with a tariff-version snapshot.
5. Duplicate delivery returns the previous command result and creates no
   second visit or visit event.
6. Exit closes the active visit, calculates a deterministic charge and creates
   durable outbound work in the same transaction.
7. Restart, backup/restore or connector outage cannot lose or reset an active
   visit.

### Consumption and checkout

1. An operator records a catalog item and quantity against an active visit.
2. The extension stores the local price/mapping snapshot used for the record.
3. Corrections are append-only adjustments, not destructive history edits.
4. Checkout totals time and consumption locally.
5. The MVP submits one idempotency-protected final account to a deterministic
   mock connector.
6. Success, retryable outage and ambiguous completion remain distinct states.
7. Ambiguous mutations require reconciliation or explicit operator review.

## Owned data model

The first migration should use stable text IDs, UTC ISO timestamps, foreign
keys, uniqueness constraints and indexes for daily operator queries. Expected
domain tables are:

- `guardians` — minimal contact and lifecycle status;
- `children` — display identity, optional notes and lifecycle status;
- `guardian_children` — explicit relationship and authority/consent metadata;
- `registrations` — kiosk submission, approval status and idempotency identity;
- `identifier_assignments` — opaque identifier mapping with active interval;
- `visits` — state, entry/exit, tariff snapshot, totals and checkout state;
- `visit_events` — append-only entry, exit and correction history;
- `tariffs` and `tariff_versions` — editable policy with immutable applied
  versions;
- `catalog_items` and `catalog_staging` — atomically published external/local
  catalog revision;
- `consumption_records` — append-only item, quantity, price and correction;
- `external_mappings` — local-to-vendor identifiers without credentials;
- `command_results` — idempotency key, payload hash and stable result;
- `domain_audit_events` — bounded business transitions without secret values.

The SDK-owned outbox and platform checkpoints remain the mechanisms for
connector delivery and paginated synchronization; do not invent a second
unreliable retry queue.

## Contract outline

Exact JSON schemas are completed during Stage CC-1. The initial contract should
remain deliberately small.

Permissions:

- `registrations_manage`;
- `children_manage`;
- `visits_manage`;
- `consumption_manage`;
- `configuration_manage`;
- `privacy_manage`.

Routes:

- kiosk registration;
- operator desk for pending registrations, identifier assignment and visits;
- operator active-visits/checkout view;
- administrator configuration, tariff, privacy and integration status.

Initial operations:

- health;
- submit/get kiosk registration result;
- list/get/approve registration;
- assign/retire identifier;
- list active visits and get visit detail;
- start/close/correct visit;
- add/correct consumption;
- process identifier scan;
- read/update tariffs and reader-purpose configuration;
- deliver final-checkout outbox;
- synchronize catalog;
- retention job, personal-data export and erasure.

Every mutation is a strict command with an idempotency key. List and detail
queries use bounded pagination and strict output schemas. Personal-data export
and erasure are administrator commands; retention is an internal job.

## Delivery stages

### CC-0 — Decisions and acceptance examples

- record the five business decisions above;
- write concrete examples for registration, entry, duplicate scan, exit,
  tariff rounding, connector outage and ambiguous checkout;
- define the minimum personal data and retention behavior;
- freeze the first MVP exclusions.

Acceptance: the examples have unambiguous expected results and no requirement
for a Core or Agent special case.

### CC-1 — Package, contracts and first migration

- scaffold `modules/child-center` independently of the reference fixture;
- add strict manifests, compiled route declarations and reviewed wheel build;
- define permissions, operations, jobs, event subscription and connector;
- implement migration `0001` and health operation;
- declare storage classifications as private/secret and
  `contains_personal_data: true` with retention/export/erasure operations;
- add package, schema, migration and deterministic-build tests.

Acceptance: version `0.1.0` validates, builds deterministically and installs as
an inactive reviewed package without changing Core or Agent.

### CC-2 — Local registration and operator approval

- implement guardian/child registration with minimum data;
- implement pending list, detail, approval and correction rules;
- add identifier assignment history and uniqueness enforcement;
- build responsive kiosk and operator routes using platform theme/i18n tokens;
- add authorization, idempotency and personal-data leakage tests.

Acceptance: kiosk cannot enumerate records; an authorized operator can approve
and assign an identifier; an unauthorized user cannot invoke either workflow.

### CC-3 — Visits and identifier events

- implement reader-purpose configuration and `identifier.scan.v1` handling;
- create append-only visit events and one-active-visit invariant;
- handle duplicate, late, unknown and wrong-reader scans deterministically;
- preserve active visits through service/Core/Agent restart;
- provide active-visit operator UI and explicit stale/offline state.

Acceptance: a duplicate event cannot duplicate or reverse a transition, and a
restart does not change elapsed visit time.

### CC-4 — Tariffs and deterministic checkout

- implement versioned tariffs and deterministic UTC-based calculation;
- snapshot the applied tariff version on entry;
- add consumption and correction records;
- calculate a local checkout preview without contacting a vendor;
- cover boundaries with an injectable clock.

Acceptance: identical persisted inputs always produce the same total, and a
later tariff edit cannot alter a closed or active visit unexpectedly.

### CC-5 — Mock integration and offline continuity

- add a deterministic child-center/POS mock connector;
- synchronize a paginated catalog through staging and atomic publication;
- submit final checkout through the transactional outbox;
- exercise success, retryable outage, malformed pages and ambiguous mutation;
- expose useful operator status without payloads or credentials.

Acceptance: local operation continues during outage, recovery delivers exactly
once where the remote contract permits it, and ambiguity never triggers blind
replay.

### CC-6 — Privacy, recovery and lifecycle

- implement retention, scoped export and erasure operations;
- ensure closed history can be anonymized without corrupting financial totals;
- verify diagnostics contain counts/health only;
- test upgrade, failed migration rollback, disable/re-enable and uninstall
  separation;
- verify encrypted backup/restore with active visits and pending outbox work.

Acceptance: personal-data lifecycle operations are audited and bounded, and a
portable restore reproduces the complete local workflow state.

### CC-7 — Physical acceptance and first beta

- deploy through the immutable Raspberry release layout;
- enroll kiosk and operator access;
- use mock identifier scans first, then one approved physical reader adapter;
- test reboot, network loss, duplicate scan, backup/restore and connector
  recovery;
- document operator recovery and known limitations;
- publish the first extension beta only after the acceptance checklist passes.

## Required test matrix

- contract rejection for unknown fields, undeclared permissions and unsafe
  routes/configuration;
- role and audience isolation for kiosk/operator/administrator/internal calls;
- idempotency-key reuse with same and different payloads;
- database constraints and forward-only migration history;
- duplicate, reordered, late and unknown identifier events;
- timezone, midnight, rounding and tariff-version boundaries;
- service, Core, Agent and device restart during an active visit;
- connector success, timeout, retryable outage, ambiguous completion and
  malformed paginated catalog;
- credential rotation without package reinstall;
- personal-data export, erasure, retention and diagnostic redaction;
- backup/restore with active visit, event cursor, checkpoints and outbox;
- failed upgrade rollback and disable/re-enable with data retention;
- responsive kiosk/operator/admin UI in light and dark modes.

## Definition of first useful release

The first useful release is not a generic generated CRUD application. It is a
reviewed extension package that can complete this local flow on Raspberry:

1. enroll a kiosk;
2. submit one guardian and child;
3. approve them as an operator;
4. assign an opaque test identifier;
5. start and close a visit from two deterministic scan events;
6. calculate the expected local time charge;
7. survive restart and encrypted backup/restore;
8. remain usable while the mock external service is unavailable;
9. deliver or explicitly flag the final checkout after recovery;
10. export or erase the child's personal data through an administrator action.

Only after this flow passes should the project bind a real Barsy/POS endpoint
or physical RFID/NFC reader.
