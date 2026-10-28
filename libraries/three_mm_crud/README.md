# Optional declarative CRUD

This application dependency provides one shared typed engine, migration and Vue
renderer. It is bundled by the application builder into the ordinary immutable
service wheel and compiled UI sources, never loaded or installed into Core.
Core's normal application route/audience/permission and scoped relational gates
remain authoritative. Factories/health do not open a database. The relational
profile is cooperative, not a sandbox for hostile Python.

`CrudDefinition` describes entities and fields. `declarations()` produces ordinary
per-entity read/write permissions and CRUD operations. Current permissions are
checked by Core on every call; actor references stored in records are provenance,
not foreign keys or authority. `CrudService` uses only the host-provided scoped
SDK adapter, without direct SQLite fallback, Core SQL, tokens or private imports.
The renderer uses only `@3mm/application-ui/v1` and the common UI surface.
It now uses public `UiField`, `UiForm`, `UiTable` and `UiState` and therefore
requires a Core build that includes the CAP09 UI additions. Native field
validation does not replace service validation. Pagination and mutations still
belong to this renderer's SDK operations; presentation never retries a command.
Request IDs use secure random bytes on HTTP LAN and are persisted before one
dispatch. Failure to obtain or preserve an ID blocks the change visibly.

The bounded profile supports 1000 records, 4096 encoded bytes per record, 10 rows
per page and 5000 ordinary command receipts. Explicit administrator erasure may
add a tombstone beyond that journal threshold, within the same database bounds,
so the ordinary command limit cannot prevent personal-data removal.
Writes use saved random command IDs, exact
payload/actor fingerprints and optimistic record revisions. No automatic retry
occurs. Outcome queries reveal receipts only to the original actor; application
data remains shared according to the declared read permission. The UI persists
only the random pending ID and requires outcome review before another change.
Fresh access failure clears visible records.

Personal-data storage explicitly declares `retention_policy:
until_explicit_erasure`. This is an inert retention choice, not a grant or a
scheduled task. It retains administrator-only export and erasure operations.
Exports are bounded current pages, not a consistent multi-page backup snapshot.
Erasure removes record payloads, provenance and old result/fingerprint data;
random request tombstones prevent delayed old commands from recreating records.
Receipts/tombstones are bounded; maintenance requires a separate reviewed scope.

Administrator-only import preserves original record IDs, values, timestamps and
actor references and refuses conflicting existing identities. An explicit import
does not copy old grants or enable an application. Import validates the current
schema/limits; incompatible historical data remains intact in retirement archives
for a deliberate conversion. No owner data is imported automatically.

Original Core CRUD/model/renderer/protocol sources are preserved byte-for-byte in
`source/legacy`; mixed originals are in `source/reference`. Their paths/hashes are
in `modules/product-source-map.json`. These are evidence, not a compatibility
server. The source-only marker excludes this entire dependency from Core payloads.

Migration `8d63e4b5fc53` copies the old definitions/records into two `retired_`
archives without cascading FKs into current users. Exact existing package/version
references use Core's generic retained-resource pins. Empty retirement can
downgrade; populated archives/pins require verified backup recovery and reviewed
application import. Existing packages/uploads and historical values are retained.
