# Milestone 12 report — Trusted application extension foundation

Status: completed and physically accepted on `rasp-3mm` on 2026-08-30. All
seven stages and the twelve-step neutral reference flow passed.

## Goal

Allow a separately installed business application to own transactional domain
workflows, role-specific UI, hardware events and reliable external integration
without adding its entities or vendor logic to Core or Agent.

## Stage 1 result — Contract and package boundary

- Added the strict, immutable `ApplicationExtensionV1` shared protocol.
- Declared a checksum-bound reviewed service wheel and stable SDK entrypoint.
- Added versioned `query`, idempotent `command` and persistent `job` operation
  contracts with bounded strict input/output object schemas.
- Added public, kiosk, operator, administrator and internal audiences.
- Added namespaced extension permissions and server-owned route policy metadata.
- Added event subscriptions with consumed capability, configured device scope,
  bounded backlog and acknowledgement-after-commit semantics.
- Added destination/credential configuration references for HTTP connectors,
  bounded request/response sizes and explicit mutation capability.
- Added persistent jobs, SQLite storage revision, personal-data lifecycle hooks
  and transactional disable/uninstall/rollback declarations.
- Required retention, export and erasure operations when personal data is
  declared.

## Cross-file package validation

- Bound `application-extension.json`, Module Manifest v2, optional
  `compiled-ui.json` and the reviewed service artifact to one module ID and
  semantic version.
- Verified the service artifact SHA-256 before catalog acceptance.
- Required every subscribed Agent capability and emitted event to appear in
  the manifest's consumed/provided capability sets.
- Derived the exact manifest permission set from events, connector secrets and
  service execution requirements.
- Required a strict configuration object and rejected undeclared reader,
  destination or credential keys.
- Required connector credentials to use secret-reference fields and forbade
  secret defaults in the package.
- Bound every application route to an existing compiled route entrypoint.
- Rejected duplicate ZIP paths in addition to the existing traversal, symlink,
  file-count and expanded-size protections.

## Stage 1 fail-closed runtime boundary

Stage 1 defined and validated packages without executing them. Stage 2 now
allows a package to be uploaded into the immutable catalog, but its compiled UI
and service remain inactive until explicit transactional activation succeeds.
The Agent installation API still rejects it because the service is Core-hosted.

## Stage 2 result — Supervised service runtime

- Added a small stable Extension Host SDK with installation and per-operation
  context objects.
- Added a standalone host process that imports the checksum-bound wheel; Core
  never imports application service code.
- Added bounded HMAC-SHA256 request and response envelopes over a Unix socket,
  including timestamp, request identity, correlation identity and replay
  rejection.
- Added the dedicated `3mm-app` service identity and a hardened systemd template
  with no network namespace access in this stage and write access only to the
  extension's `data` and `run` directories.
- Added a narrow helper action that accepts only a package SHA-256, resolves it
  under the fixed upload directory, independently validates the complete
  package and stages only its reviewed wheel.
- Added atomic active metadata, per-installation transport keys, readiness
  checks and restoration of the previous active pointer on failed activation.
- Added a Core installation registry through an Alembic migration, explicit
  activate/disable/health endpoints and an administrator-only generic operation
  gateway.
- Kept public, kiosk and operator invocation closed until their server-side
  authorization model is implemented in Stage 4.
- Hid inactive application UI artifacts from the public compiled catalog and
  protected active application packages from deletion.

## Stage 3 result — Owned state and recoverability

- Added one namespaced `data/state.sqlite3` database per application service;
  Core carries and backs up the file but never reads domain tables.
- Added a required, reviewed migration entrypoint and strictly ordered,
  forward-only SDK migrations that run before the service factory starts.
- Added SDK transactions and a platform-owned outbox table so a domain change
  and its outbound work item commit or roll back together.
- Snapshot application SQLite state before an upgrade and restore it together
  with the previous active service metadata when migration or health fails.
- Added only application `data` directories to the encrypted backup boundary;
  immutable wheels, sockets, transport keys and active runtime metadata remain
  excluded and reproducible.
- Quiesce application services while creating a backup and transactionally
  swap their data during restore.
- Reactivate restored applications from checksum-addressed packages recorded
  in the restored Core database, regenerate runtime-only material as needed,
  and disable stale application service instances.
- Preserve compatibility with Milestone 11 backups that contain no application
  data area.

## Stage 4 result — Server-owned application access

- Added separate public, kiosk, operator and backward-compatible administrator
  operation gateways; an operation remains unavailable unless its reviewed
  contract declares that exact audience.
- Added application-scoped permission grants for normal users. Operator
  requests check the active package's declared permission on every call, and a
  revoked grant stops access immediately without changing the user's global
  role.
- Added high-entropy, one-use kiosk enrollment codes, a persistent terminal
  identity and a credential whose plaintext is returned only at enrollment.
- Added renewable 15-minute kiosk sessions. Their JWT type and subject are
  distinct from normal users, and every use checks the active installation and
  non-revoked terminal record.
- Added administrator terminal catalog and revocation endpoints; revocation
  invalidates an already issued kiosk JWT immediately.
- Filtered application compiled routes in Core according to the resolved
  server principal and extension permissions before returning the UI catalog.
- Derived Vue route guards and menu entries from that filtered metadata and
  refresh the compiled route registry when authentication changes.
- Rejected compiled application routes that lack an
  `application-extension.json` access policy or try to define a separate
  client-only role override.

## Stage 5 result — Durable application events

- Added the strict `identifier.scan.v1` event contract. It carries only an
  opaque identifier, source device and reader identity, adapter kind,
  restart-safe sequence, timestamp, health and bounded non-personal scan
  metadata.
- Added a generic identifier adapter boundary and a deterministic loopback
  mock. The installed test system enables the mock explicitly and advertises
  the capability in Agent inventory without mapping it to physical hardware.
- Kept Agent delivery on its existing bounded persistent outbox. Core-owned
  device identity, event identity and timestamp can no longer be overridden by
  an event producer.
- Validated the versioned scan envelope at authenticated Core ingestion and
  retained the existing event-ID deduplication behavior.
- Added durable per-subscription delivery rows and observable cursors through
  an Alembic migration.
- Matched only active reviewed application packages that declare
  `events.consume`, consume the exact capability and select the source device
  through their declared configuration key.
- Delivered events in source order with the event ID as correlation and
  idempotency key. Core acknowledges and advances the cursor only after the
  supervised service handler returns successfully after its own commit.
- Added a bounded 30-second retry worker, five attempts, manifest-defined
  backlog limits and at most 1,000 retained dead letters per subscription.
  Administrator-only status and manual drain endpoints expose backlog,
  acknowledgements, dead letters and pruned totals.
- Moved matching and application delivery out of the Agent ingestion request,
  so an accepted scan does not wait for the application service.

## Stage 6 result — Protected connectors and persistent jobs

- Added installation-scoped encrypted Basic, bearer and API-key credentials.
  APIs expose only opaque references and lifecycle metadata; plaintext values
  are never returned to the extension service, browser or audit record.
- Added administrator-controlled connector bindings to reviewed destinations.
  The broker enforces scheme, origin, port, path prefix, methods, headers,
  request/response sizes, timeout and redirect denial before injecting the
  credential.
- Kept application services in their network-isolated systemd sandbox and
  exposed connector/checkpoint access through a signed, installation-specific
  Unix socket instead of granting general network access.
- Persisted connector attempts without payloads or credentials and separated
  successful, rejected, retryable, ambiguous and failed outcomes. Stable
  request IDs prevent an ambiguous mutation from being replayed blindly.
- Expanded the extension-owned transactional outbox with payload hashes,
  remote idempotency keys, attempt scheduling and explicit terminal/manual
  review state.
- Added compare-and-swap synchronization checkpoints for bounded paginated
  reads and a small persistent scheduler for reviewed jobs, including stable
  UTC invocation identities, leases, catch-up behavior and last outcome.
- Added an injectable SDK clock and generic administrator operational status
  for service/storage, events, jobs, connectors and outbox state.
- Added a clean Alembic migration for secrets, bindings, attempts, job state
  and checkpoints, plus immutable-deployment ownership and socket settings.

## Stage 7 result — Neutral reference acceptance

- Added the checksum-bound `org.3mm.application-reference` fixture with a
  supervised service, kiosk registration route, operator route, owned SQLite
  migrations, transactional outbox, scheduled delivery and paginated catalog
  synchronization.
- Added a deterministic mock connector that covers success, outage, ambiguous
  completion and paginated failure/recovery without a real vendor dependency.
- Proved kiosk enrollment and revocation, extension-only operator grants,
  idempotent commands, duplicate scan delivery, timed session state and
  extension-owned record persistence.
- Proved local acceptance during connector downtime, durable retry after Core,
  Agent and service restart, one successful recovery delivery and no blind
  replay after an ambiguous mutation.
- Proved failed catalog pages cannot publish a partial revision, while a later
  successful run advances the checkpoint and publishes atomically.
- Rotated the connector credential without reinstalling the package and
  confirmed the plaintext remained outside package, browser and service state.
- Restored the encrypted Standalone backup and retained application records,
  migration revision, event delivery state and outbox work.
- Rejected an intentionally unhealthy `1.0.2` upgrade and retained healthy
  version `1.0.1`, its compiled UI and compatible data.
- Proved disable stops the service and hides its active routes while retaining
  `state.sqlite3`; re-enabling `1.0.1` restored the route and returned the
  pre-disable record unchanged.

## Verification

- 160 focused protocol, SDK storage, package, transport, host, activation,
  gateway, migration, backup/restore, helper, systemd, compiled UI and runtime
  tests passed.
- 10 focused frontend authorization/navigation tests and the production
  frontend build passed.
- Deployed the Stage 4 working-tree snapshot to the physical Raspberry and
  activated a neutral, checksum-bound application package under the dedicated
  `3mm-app` service identity.
- Physically verified signed service health, an anonymous-closed catalog and
  public gateway, normal-user permission grant/use/revocation, kiosk
  enrollment and immediate terminal revocation, administrator route access,
  and disable-with-data-retention behavior.
- The physical test exposed restrictive parent and instance directory modes;
  activation now repairs its service directories independently of `umask`,
  while `/var/lib/3mm` grants `3mm-app` traverse-only access to its isolated
  subtree. The focused runtime/systemd regression suite passes 24 tests.
- Existing runtime-extension and compiled-ui packages remained compatible.
- New tests cover unknown fields, unsafe service paths, strict schemas,
  idempotency, permissions, kiosk/internal boundaries, personal-data hooks,
  connector credential semantics, artifact integrity, configuration references,
  capabilities, compiled routes, forbidden files, signed transport, isolated
  wheel loading, idempotency, administrator audience enforcement, activation
  and database rollback, migration history, outbox atomicity and restored
  application reactivation.
- Stage 4 Raspberry lifecycle and access acceptance is complete, and the full
  neutral reference flow subsequently passed with the Stage 5 and Stage 6
  runtime boundaries.
- 24 focused identifier protocol, Agent mock/config/API, broker, ingestion and
  clean migration-history tests pass. The broader relevant suites pass 153
  tests. Four existing POSIX mode-bit assertions are not meaningful on the
  Windows checkout; those permissions remain enforced and physically tested on
  Linux.
- The remaining warnings are pre-existing Pydantic v2 migration warnings plus
  the intentional duplicate-ZIP fixture warning.
- Stage 6 adds eight passing focused secret, connector, scheduler, SDK outbox,
  migration and administrator-authorization tests. The signed platform socket
  integration test is skipped only on the Windows host that lacks `AF_UNIX`;
  it is exercised on the Linux deployment target.
- Deployed working-tree release
  `worktree-6c44456d15c2-20260829171820` through the immutable installer after
  its first attempt safely rolled back on a missing systemd write boundary.
  The final unit grants Core write access only to the application platform
  socket directory.
- Physically verified Core, Web and Agent readiness, database revision
  `dae2f3a4b5c6`, all five Stage 6 tables, the owned `0660` platform socket and
  its active Unix listener. Agent inventory advertises `identifier.scan.v1`.
- Paired the fresh Agent through the audited local bootstrap, restarted it with
  its private installation credential and delivered mock scan
  `evt_9ae78b7ab9974e5a99d11bdfcd2b5e69` through authenticated Agent → Core
  ingestion. The persisted payload retains the opaque identifier, reader,
  adapter and restart-safe sequence, completing Stage 5 physical acceptance.

- Built the reference package deterministically and passed 34 focused
  reference, SDK storage, platform transport and package tests (one Windows
  `AF_UNIX` integration skip), plus 62 frontend tests, type-check and production
  build.
- Activated reference version `1.0.1` with package SHA-256
  `d488e6927ed024677528aadf2ef9bd27dd1db533883584ac985f99d20a6875e1`.
  The intentionally broken `1.0.2` package returned HTTP 409 and left `1.0.1`
  healthy.
- Preserved accepted record `record_f73f225bddd044e98af83df93b76f065`
  through restart, backup/restore and disable/re-enable; its final state remains
  `closed` with two items.
- Fixed restore of excluded runtime directories for the platform socket and
  portable-backup import boundary, then added a post-restore privileged-helper
  refresh. The focused backup/helper regression suite passes 26 tests.

## Handoff

Milestone 12 is closed. The next vertical project may implement the child-center
domain as a separate application extension while Core and Agent remain unaware
of its people, visits, wristbands, consumption records and external vendor.
