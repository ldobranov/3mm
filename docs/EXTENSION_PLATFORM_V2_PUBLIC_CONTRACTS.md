# M20 — public extension schema catalog, first WP1 contract slice

Date: 2026-10-08. Local implementation; no deployment or release. This follows
the accepted read-only Package Inspection slice. It does not complete WP1/WP4
or enable remote/untrusted execution.

## One source of truth

Public entry point: `three_mm_protocol.extension_schemas.extension_schema_catalog()`.
It exports JSON Schema Draft 2020-12, in **validation** mode, directly from the
existing Pydantic models. There are no duplicated manifest definitions, new
package formats, Core imports, publisher assumptions or SDK version changes.

Developer command (from a checkout with the existing Python dependencies):

```text
python -m three_mm_protocol.extension_schemas
```

The command emits one JSON document to stdout; it does not inspect/import package
payloads, download, build, install or write generated source files. Consumers may
save the stdout themselves. Nothing is automatically added to a package/release.

`catalog_version: 1` versions this export format, **not** Core, the manifest,
SDK or a distribution envelope. `contracts` maps stable contract IDs to:

- `document`: package-root filename (candidate only for contract-only entries);
- `version_field` and `contract_version`, derived from the model's literal;
- `source_model`: authoritative public Python model;
- `schema`: standalone JSON Schema with a URN `$id` and local `$defs` references.
- `runtime_support: contract_only`, when present: declaration/authoring model
  only, not a currently accepted ZIP activation or runtime transport feature.
- `runtime_support: reviewed_native_scoped`: accepted optional application ZIP
  declaration plus signed runtime publication; exact installed-artifact native
  review and applied local resource grants remain mandatory. Not a sandbox.
- `declaration_support`, when present: support for an optional nested authoring
  declaration. `runtime_authority: reviewed_native_scoped_local` indicates bounded
  installed headless execution with exact applied grants. `core_admin_review_api`
  exposes those exact resources in the existing admin review dialog; native code
  trust remains `local_core_only`. Its narrower runtime bound is explicit; this is
  not feature negotiation, general installer support or hostile-code isolation.

Each schema can be extracted and used independently. URNs are identifiers, not
network locations or publisher identities; no network resolution is needed.
Repeated exports from the same models/dependencies are deterministic, with no
timestamps or host paths. Each call returns independent dictionaries. Consumers
must reject unsupported catalog/contract versions rather than guess a format.

## Existing contracts and compatibility matrix

Every supported module-v2 ZIP retains `manifest.json` / ModuleManifestV2.
The descriptor does not replace that envelope or the whole-package validator.

| Package / contract ID | Descriptor | Current runtime / remaining checks |
| --- | --- | --- |
| Agent module / `module-manifest.v2` | Manifest v2; no new Agent descriptor | Agent runtime; architecture, Agent version, permissions and lifecycle remain enforced by the existing Agent |
| Application / `application-extension.v1` | `application-extension.json`, version 1 | Supervised service; SDK 1.0–1.3 remains supported; optional UI also requires compiled-ui v1 and matching access policies |
| Application publication / `application-event-publications.v1` | Optional `application-event-publications.json`, version 1 | Installed reviewed-native publication through SDK 1.3's additive signed call and exact applied grants; no inferred device identity or cross-application consumer access |
| Declarative runtime UI / `runtime-extension.v1` | `runtime-extension.json`, version 1 | UI runtime only; existing entity/reference/action/permission rules still apply |
| Compiled UI / `compiled-ui.v1` | `compiled-ui.json`, version 1 | Existing source/build/host contract; reviewed native integration, not an untrusted frontend sandbox |
| Theme / `theme-extension.v1` | `theme-extension.json`, version 1; design API 1 | Declarative, UI-only; existing token/manifest restrictions |
| Theme / `theme-extension.v2` | `theme-extension.json`, version 2; design API 2 | Declarative, UI-only; existing design, contrast, customization and asset validators |
| Legacy language/backend | No exported module-v2 adapter | Existing legacy behavior is unchanged; not supported by the new inspector/catalog, not silently converted |

This is a structural-contract matrix, not a claim that any particular hardware,
installed version, package or role can install/activate every type. It is common
to Standalone and Hub/Fleet consumers; schema export requires neither running.
Device capabilities remain provider-neutral and separate from runtime features.

## Mandatory validation boundary

The catalog explicitly declares `validation_scope: structural_only` and
`requires_authoritative_validation: true`. JSON Schema does **not** encode every
Python model validator or ZIP/host policy. Examples:

- safe artifact/source paths, unique IDs and cross-entry references;
- operation/audience/grant semantics and SDK feature gates;
- descriptor identity, configuration/permission/capability agreement with manifest;
- theme v2 `design` is structurally an object: its closed keys, ranges and contrast
  remain enforced by the authoritative theme validator, not this exported shape;
- ZIP bounds, traversal, symlinks, asset bytes/digests, files and build availability;
- target architecture, running versions/features, dependency resolution and rights.

Therefore authoring tools/generators use these schemas for structural guidance,
then the existing Python models and read-only ZIP inspection for authoritative
checks within their documented scope. Upload/activation must still revalidate.
Schema validity is never a publisher signature, a dependency plan, permission
approval, installation guarantee or isolation proof. No new remote validation
service, install bypass or Core endpoint is introduced.

## Evidence and next boundary

The original focused tests compare all six existing exports to their authoritative models, resolve all
local refs, check deterministic independent outputs, real CLI JSON output,
SDK 1.3 compatibility and explicit semantic limitations. A subprocess blocks
Core/Agent/runtime/SDK imports to verify this remains a shared-protocol tool.
Existing descriptor and ZIP inspection tests remain the regression baseline.

This step: **71 focused tests passed** (10 new schema-export checks and 61 existing
descriptor/package/SDK checks; 6 warnings). Frontend production build also passed;
there are no visual changes in this step. Full release suite and live-device
acceptance were not repeated, and no dependency was added.

Remaining WP1: publisher namespace/key ownership and general target/dependency
compatibility planning. WP4 scoped grants and WP5 proven execution isolation
remain separate gates; this catalog does not authorize their implementation.

2026-10-09 additive publication delivery: seven contracts are exported. The first
slice was contract-only; the subsequent package/broker/authority/SDK integration
marks it `reviewed_native_scoped`. The six existing models, supported SDK versions
and catalog version are unchanged. Schema validity still grants no rights,
publisher trust, executable isolation or automatic installation. See the
[approved publication scope and evidence](EXTENSION_PLATFORM_V2_EVENT_PUBLICATION.md).

2026-10-09 bounded file-request follow-up: application descriptor v1 optionally
accepts `storage.private_files` contract v1 with explicit read/read-write mode and
bounded file/count limits, requiring SDK 1.3. It selects one installation-owned
logical namespace, never a host path. Existing undeclared SDK 1.0–1.3 packages
remain valid; no manifest/SDK/catalog version or contract count is changed.
JSON Schema describes its structure; coherent limits and SDK gating also require
the authoritative validator. The initial slice marked storage authority **not
implemented**. The subsequent bounded execution supports installed reviewed-native
local grants through the existing manager, signed SDK gateway and target-owned
worker. The catalog marks `reviewed_native_scoped_local` with
`authority_administration: core_admin_review_api`, local-only native attestation
and `runtime_max_file_bytes: 1048576`; larger requests remain unsupported, not
silently clamped. The existing admin HTTP review/dialog now exposes exact file
read/write resources, owner/package pins and limits with separate approve/apply.
It refuses incomplete or foreign bindings, not silently hiding rights. Inspection
never infers a grant, even for unchanged declarations. See
[file execution, evidence and remaining gates](EXTENSION_PLATFORM_V2_PRIVATE_FILES.md).

## Public application frontend host v1 (2026-10-17)

Compiled **application routes** can import `useApplicationHost`,
`ApplicationHostError` and the public TypeScript types from
`@3mm/application-ui/v1`. The build emits a versioned import-map entry. The
install-time compiler allows this exact import, not its private subpaths.
Existing `@3mm/ui/v1` presentation exports and SDK 1.0–1.3 are unchanged.

```typescript
import { useApplicationHost } from '@3mm/application-ui/v1'
const host = useApplicationHost() // during the route component's setup
const access = await host.getInfo()
const record = await host.invoke('get_record', { record_id: selectedId })
// Commands require the caller's stable key for this exact logical request:
const result = await host.invoke('register', { label }, { idempotencyKey: requestId })
```

The only host methods are `getInfo()` and `invoke(operationId, payload, options)`.
No caller-selected module, audience, URL, headers, token, HTTP client, router or
Core store is exposed. The dynamic route loader binds module, package SHA-256,
version, entrypoint and audience from the existing server catalog. Non-application
widgets/editors and components mounted outside that boundary get no host.

`getInfo()` makes a fresh, no-store request to
`/api/v1/application-extensions/{module_id}/ui-host/{entrypoint_id}` with the
bound `artifact_sha256`. Its closed public projection includes `host_version: 1`,
the matching binding, and permitted query/command IDs with their idempotency
requirements. Internal jobs and other audiences are not offered. The feature
flags are `operations: true`, `resource_authority: "separate"` and
`browser_isolation: false`: human operation access is **not** a resource grant.
Resource authority remains enforced by the existing service/platform adapters.
The original delivery did not lift the headless-only limitation. The separate
reviewed UI profile below now binds executable output before admitting it.

Each invocation rechecks this information and sends exactly one POST through the
existing audience-specific operation route. Its additive `ui_context` has the
exact host version, entrypoint and artifact hash. Core revalidates the installed
ZIP, active state, route/audience and current user permissions or kiosk terminal;
the existing operation and payload checks still apply. Legacy callers without
`ui_context` keep their existing API behavior. There is no browser-selected actor
or upgrade from kiosk/operator to administrator. Public calls send no bearer;
kiosk calls use only the kiosk session, even if a human is logged in too.

Host v1 accepts JSON object payloads up to 512 KiB UTF-8, 10,000 values and depth
32, and access descriptions up to 256 operation entries. Cycles, non-JSON values,
path-like operation IDs and invalid command/query keys fail before dispatch.
Unknown/unavailable host versions do not fall back to a generic HTTP client.
The Core origin is pinned for the mounted host lifetime. Unmount aborts pending
transport and invalidates retained handles; cancellation does not prove rollback.

Errors expose only `ApplicationHostError.code`: `invalid_request`,
`access_denied`, `unavailable`, `unconfirmed` or `disposed`, never raw HTTP errors,
request headers or backend responses. Failed POSTs have **no automatic retry,
token-refresh replay, fallback audience or inferred rollback**. On an unconfirmed
mutation, retain its original key/payload for the application's explicit outcome
review; do not generate a new key and resubmit. The neutral reference's kiosk
screen stops further submission and displays that key for review.

This is a public API for reviewed same-origin code, **not a security sandbox**.
It does not prevent such code from accessing browser globals directly. WP5's
untrusted browser/OS isolation and the broader WP4 owner/layout acceptance remain
separate gates. Current evidence and queue: [WP4 closeout](EXTENSION_PLATFORM_V2_WP4_CLOSEOUT.md).

## Execution-profile coverage (2026-10-17)

The application entry now includes additive `execution_profiles` describing
compatibility, installed reviewed-native scoped authority and the public frontend
host. These are authoring facts, **not** live negotiation, an approval or a claim
that arbitrary combinations work. The original scoped profile remains headless;
the separate reviewed UI profile below additionally requires exact build evidence.

Identity possession proofs, peer mutations/receiver/unfiltered listing, scheduled
jobs and public HTTP handlers have no scoped grant adapter. They are explicitly
listed as unsupported, not inferred from the descriptor's structural validity.
The signed gateway refuses proof/peer actions before private-key or network
access. Jobs are excluded from scoped discovery, refused at claim and rechecked
before dispatch; the shared invocation gateway also refuses direct job/public
HTTP handler calls outside compatibility. Public HTTP keeps route ownership but
returns unavailable without invoking unsupported code or disabling unrelated
compatibility applications. Unknown/expired job claims remain quarantined,
including across a later compatibility restart; a mode refusal proves no rollback.

Existing SDK compatibility behavior remains subject to its existing declaration,
audience and consent checks. Exact event publications can supply their declared
event types; arbitrary capability `provides` are not scoped registration authority.
Relational/peer combinations are still unsupported. Missing features never
select compatibility as a fallback for an already opted-in installation.

The stale relational catalog entry has been corrected to
`reviewed_native_scoped_prepared`: exact local review/grants plus protected
preparation and explicit local-admin/helper activation are required. Generic
activation remains blocked, and `cooperative_v1` is not an OS resource quota.
No descriptor, SDK version, contract count or publisher/permission policy changed.

## Reviewed UI with scoped service resources (2026-10-18)

`supervised_reviewed_native_ui_v1` reuses the installed manager, sealed native
review, exact resource scopes and `AuthorityArtifact.built_ui_sha256`. No new
subject version, database model, SDK version, publisher trust or sandbox exists.
Human/kiosk route and operation access is independent of service resource grants.

New install-time builds record a Core-owned `build-provenance.json`: source ZIP
SHA-256, compiler script SHA-256, Node/Vite/Vue-plugin versions and a complete
output inventory (including chunks, CSS, descriptors and entrypoint index).
The bounded reader checks ownership/protection, regular paths, hashes and sizes;
the canonical record has a domain-separated SHA-256. This is local build
provenance, not a publisher signature or proof of reproducible/untrusted builds.
Validation happens outside the authority key/DB guard. Published output remains
immutable; replacing it requires new explicit trust and resource review.

Local Core administration, using the normal service account/environment:

```text
python -m backend.services.application_authority_admin inspect-ui-build --installation-id <id>
python -m backend.services.application_authority_admin native-review --installation-id <id> --artifact-sha256 <source-sha> --built-ui-sha256 <build-sha> --review-document <review.md> --code-review-completed --accept-native-host-risk --accept-same-origin-ui-risk
```

Tokens are still prompted hidden, not passed on the command line. The reviewer
must review the exact source AND emitted executable output/toolchain, and
explicitly accept same-origin browser code risk as well as native host risk.
Inspection/review never starts a service or approves permissions. Existing
disabled first-adoption, approve/apply, lifecycle and fresh-review rules remain.
The native review seals the build pin and UI-risk acknowledgment; headless calls
and historical request hashes keep their previous behavior.

The catalog carries optional `built_ui_sha256`; new assets use
`.../<source-sha>/build/<build-sha>/assets/...`. Host info and `ui_context` carry
that exact optional pin. A missing/changed pin cannot dispatch a reviewed UI
request. The server checks current native UI trust for catalog/assets and the
shared service gateway, including raw legacy operation callers. Verified asset
bytes are read before constructing the response, not opened lazily afterwards.
Removing service rights blocks resource effects but does not revoke native code
trust or supply missing human rights; revoking native trust also blocks new UI
catalog/asset/service admission. Already-loaded browser code cannot be recalled
or sandboxed by a grant change; operation/effect checks remain current.

Old cached outputs with no build evidence are **compatibility-only**. Loading
them does not rebuild, promote or fabricate provenance. Use a new package version
through the normal install/review flow to produce a reviewed build. A valid new
compiler build alone is still neither native trust nor a resource grant.
Jobs, public HTTP handlers, proof/peer mutations and other explicitly unsupported
families remain refused. This delivery proves a neutral UI→signed service→signed
SDK command path; it does not claim every resource/layout combination has live
owner acceptance. See the current [closeout checklist](EXTENSION_PLATFORM_V2_WP4_CLOSEOUT.md).
