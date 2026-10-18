# M20 WP4 Block 1 — scoped existing local status read

Date: **2026-10-16**. The bounded adapter and its administrator resource view are
implemented and tested locally. Isolated browser review is now complete; owner
visual/live acceptance is **pending**. This is not WP4/Block 1 closure, deployment
or a release.

## Supported contract

The existing SDK 1.3 `get_installation_status(link_id)` method and signed
`installation.status.get` operation are reused. Application descriptor v1 and
Module Manifest v2 must both declare `installation.status.read`; a declaration
alone is not a grant. No public descriptor/SDK-major or database migration is
introduced.

Core resolves the complete bounded set of **already existing**, non-revoked
outbound links for the exact module and current service instance. Each link has
its own `status:peer_<32 lowercase hex>:read` scope. There is no wildcard,
installation-wide device grant or caller-selected resource subset. An empty set,
more than 32 links, a corrupt binding or an unavailable source refuses review;
there is no partial subject that keeps only readable links.
Existing total review byte/depth/node bounds also remain in force.

A status-only declaration **cannot create a link**. This slice is not a new
enrollment workflow: existing peer creation still requires its separate human
consent and declaration/authorization rules. Adding unsupported peer permissions
to a package still blocks its adoption; selecting only status cannot hide them.
Existing local link states `new`, `pending` and `active` may be projected, as in
compatibility mode. This does not assert remote approval or connectivity.

## Exact review binding

Internal context/selection/subject/policy version **8** adds `status_projections`.
Each resource contains only:

- exact Core/application/incarnation/module owner and package SHA-256;
- `operation: installation.status.read`, exact link and current service instance;
- both complete seven-field public installation identities;
- canonical HTTPS receiver origin and target module ID;
- positive consent revision and exact selected summary fields, node IDs and node
  fields from the existing local consent.

Core validates public-key digests; the sender must match the current public Core
identity. A receiver public pin is **not** proof of remote key possession, remote
consent, network reachability, code trust or permission to report.

Consent selections are sets in v8: canonical sorting changes only new typed
review copies, not stored consent or the existing projection's presentation order.
Earlier versions 1–7 retain their original shapes/canonical behavior. Mixed
supported resources retain their independent checks. Status cannot grant identity
read, file/SQL/checkpoint writes, signing or another resource family.

Review → approve → apply remains separate from exact local native-code review.
The first adoption still requires the existing stopped/disabled state. Review may
read stopped metadata through an explicit internal flag; neither that flag nor
approval permits a stopped runtime to return device data. Re-enable requires
fresh current permission review/apply under the existing lifecycle rules.

## Runtime and revocation

Only the authenticated platform instance boundary dispatches the scoped adapter.
The closed request accepts the existing transport fields and **only** a link ID;
it cannot replace the owner, receiver, origin, consent, nodes or selected fields.

Package preparation precedes the lease. Under **Core key → authority guard → exact
outbound row** coordination, admission re-resolves the complete current subject
and sealed grant, rechecks the service instance, then re-reads and compares the
full local binding before projection. The guard transaction commits before the
lease is released or data returned. Pending caller writes/nested transactions
are refused. No lease spans network or helper I/O.

Revoke, disable, native/key/configuration/recovery/artifact/incarnation drift,
changed public identities/receiver/origin/target/consent, withdrawn links or a new
link invalidate old authority. Reordering an unchanged consent set does not expand
access. A change after grant comparison but before the locked binding read is
also refused. The existing row lock serializes local withdrawal with projection;
already completed reads cannot be recalled.

The shared [public-only foundation](EXTENSION_PLATFORM_V2_STATUS_READ_FOUNDATION.md)
selects explicit public columns, never Core signing keys or peer credentials.
Only selected devices are fetched; heartbeat/inventory reads depend on selected
fields. No peer list, private configuration, report snapshot, signing, identity
initialization/repair, remote call or automatic regrant is performed. Missing
schema fails closed rather than being interpreted as an empty consent set.

## Administrator view

The existing Application access dialog displays each exact receiver/origin/target,
consent revision and selected summary/node fields. Expandable binding details show
the owner/incarnation/instance/artifact and both complete public identities, not
private credentials or current device values. EN/BG wording distinguishes local
projection from reporting/enrollment and from private-key possession.

Resources are read-only review cards, not peer-consent editors. Acknowledgment,
approve and apply remain separate, with no automatic retry. Malformed/foreign/
mixed-owner resources are rejected as a whole. The frontend ceiling is 229 scopes
only for a profile containing exact status scopes; no-status profiles retain their
previous 197-scope bound. At most 32 links are accepted.

## Verification and acceptance

- Full frontend suite: **369 passed / 49 files**, including the new nine parser
  and three dialog cases. TypeScript checking and production build passed.
- The first parallel frontend run had a bootstrap import timeout and a later
  catalog assertion failure. All 19 bootstrap cases passed alone and the full
  suite passed with one worker/file at a time. No unrelated bootstrap behavior or
  timeout setting was changed; existing fixture warnings remain visible.
- **867 distinct native Linux/Python 3.14.4 passed cases**, verified from JUnit:
  the integrated non-root run passed **835**, with **16 environment-specific
  skips**; **15 actual Root/helper cases** cover its Root-only skips and **17
  HTTPS/catalog cases** pass without skips. The latter includes the existing
  two-Core verified TLS/Unix-socket acceptance with a disposable local CA. The
  remaining non-POSIX-only refusal case passed separately on Windows/Python
  3.13.15. Overlapping earlier focused runs are not added to these totals.
- Logs/JUnit: `.runtime/m20-status-v8-{regression,root,https}.*` and
  `.runtime/m20-status-v8-windows-refusal.*`; frontend logs use the same prefix.
  Fifteen changed adapter/authority/protocol and new regression files in the
  final Linux snapshot are byte-identical to the local source. Whitespace checks
  passed; pre-existing deprecation/fixture warnings were not hidden. This is a
  broad scoped regression, not the entire Python release gate.
- Isolated browser follow-up: desktop **1440 × 1000** Slate Copper/light/EN,
  Graphite Mint/dark/BG and mobile **390 × 844** dark/BG. Two links, empty consent,
  64 selected devices, expanded full public identity/package bindings and long
  identifiers were inspected. Read-only DOM measurements show no horizontal
  overflow; the 64-device list scrolls inside its 192px bound. Approval remains
  disabled without acknowledgment. No live permission controls were used.
  Screenshots/build log are under `.runtime/m20-status-ui/`; the fixture has no
  real backend or credentials and blocks permission mutations. A previous Windows
  capture was stopped; this later review used a separate supported in-app browser
  and a known local fixture URL. Owner visual/live acceptance is still separate.

Tests use disposable databases, packages, local sockets/CA and private mount
namespaces, not the VM or parallel development checkout. No live key, identity,
grant, service, immutable release or persistent application data is changed.
No version bump, commit, push or release is included.

## Remaining work

Scoped proof signing needs an explicit audience/receiver/resource authorization
contract. Scoped peer enrollment/approval/rotation/revocation/reporting needs its
own exact consent/generation and separate pre-dispatch/completion checks; local
status grants cannot supply them. Jobs/public routes/provides, the public frontend
bridge and neutral Standalone/Hub/SDK acceptance remain separate WP4 gates. This
reviewed-native adapter does not prove WP5 OS/browser isolation.

Generic mixed SQL status conservatively retains `relational_runtime_unavailable`;
this adapter does not start, migrate, repair or recover relational runtimes.
Accepted beta.51 bounded SQL evidence and checkpoint behavior are not reopened.
The next [public peer-listing preparation](EXTENSION_PLATFORM_V2_PEER_READ_FOUNDATION.md)
reduces unnecessary private-column reads without enabling scoped peer operations.

Related: [identity read](EXTENSION_PLATFORM_V2_IDENTITY_READ.md),
[authority administration](EXTENSION_PLATFORM_V2_AUTHORITY_APPLY.md),
[WP4 plan and remaining gates](../EXTENSION_PLATFORM_V2_CORE_PLAN.md#wp4--public-platform-api-sdk-and-authorization).
