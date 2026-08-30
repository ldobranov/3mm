# Runtime Extension v1

Status: draft contract; Milestone 7 stage 1

## Purpose

Runtime extensions are declarative packages that Core can validate, install and render immediately. They do not contain Vue, JavaScript, Python, shell commands or arbitrary HTML. The existing compiled extension format remains separate and requires an external trusted build pipeline.

## Trust boundary

Core accepts only fields represented by `RuntimeExtensionV1`. Unknown fields fail validation. A runtime extension may declare entities, typed fields, pages, navigation and a fixed set of CRUD actions. It cannot declare executable entrypoints, arbitrary HTTP endpoints, dependencies or operating-system permissions.

All runtime data access is mediated by Core. Read access requires `runtime.data.read`; create, update or delete actions additionally require `runtime.data.write`. Authentication is the default, and an optional page role may only narrow access further.

## Package direction

The planned package contains:

- the normal immutable module manifest v2;
- `runtime-extension.json`, validated as `RuntimeExtensionV1`;
- locale data only when it can be represented by the contract.

The package contains no compiled frontend asset or generated backend executable. Core registers page and navigation metadata generically. The frontend loads the definition through a versioned API and renders it with precompiled components.

## Core API boundary

Core stores immutable versioned definitions and activates one version per module. Runtime entity records are namespaced by module and entity ID so compatible data survives definition upgrades and rollback. The `/api/v1/runtime-extensions` API validates every create and update payload against the declared field types, rejects unknown fields, and enforces page actions, roles and declared read/write permissions on the server.

Publishing or activating a definition requires an administrator and creates an audit record. A runtime package uses the ordinary immutable module catalog, contains only `manifest.json` and `runtime-extension.json`, and is revalidated before activation. Reading definitions and entity data requires authentication.

## Stage 1 supported UI

- entity field types: text, multiline text, integer, number, boolean, date and datetime;
- page views: table, form and detail;
- actions: create, read, update and delete;
- localized names and labels with an English fallback;
- Bootstrap Icon identifiers for optional navigation icons.

Relationships, custom layouts, remote APIs, media fields and capability actions are intentionally deferred until the basic CRUD reference extension passes the full install-to-use acceptance scenario.

They are not added to `runtime-extension v1` by allowing arbitrary handlers or
scripts. A workflow that needs related transactional records, background work,
hardware events or an external business API moves to the separately supervised
`application-extension v1` boundary described in
[APPLICATION_EXTENSION_V1_PLAN.md](APPLICATION_EXTENSION_V1_PLAN.md).

## Required validation

- IDs, routes, field IDs and navigation IDs are unique;
- every page references a declared entity;
- every navigation item references a declared page;
- write actions require explicit write permission;
- unknown or executable fields are rejected;
- package installation remains immutable, transactional and reversible.
