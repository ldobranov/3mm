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
