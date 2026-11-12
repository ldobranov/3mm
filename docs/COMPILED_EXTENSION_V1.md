# Compiled UI Extension v1

Current source uses neutral `@platform/*` public imports. For a service plus UI
application, start with [Building applications](APPLICATION_DEVELOPMENT.md).

## Purpose

Compiled UI extensions contain reviewed Vue source that is converted once during installation into immutable browser-ready JavaScript and CSS. They support widgets, routes, editors and reusable components through one data-driven contract. They do not require a Vite development server and do not modify the prebuilt Core frontend.

Compiled UI crosses an executable-code trust boundary and requires administrator
review and protected compilation. It is not a hostile-code browser sandbox.

## Source package

A source package contains:

- `manifest.json` using module manifest v2;
- `compiled-ui.json` using `CompiledUiExtensionV1`;
- declared `.vue` entrypoints under `source/frontend/`;
- optional supporting TypeScript, JavaScript, CSS and JSON under `source/frontend/`.

A UI-only package declares `entrypoints.ui` as `compiled-ui.json`. A current
application may combine this UI with a separately packaged, checksum-bound service
wheel through `application-extension.json` and the `core` runtime. Backend source
is not part of the UI compiler's input boundary; see the application guide rather
than the historical UI-only Stage 1 restriction for that combined format.

## UI entrypoint kinds

- `widget`: a component mounted inside Display Canvas;
- `route`: a component registered at its declared route;
- `editor`: a configuration component targeting a widget entrypoint;
- `component`: a reusable component exposed through the Extension Host SDK.

Entrypoint IDs, source paths and routes are unique. Editors must reference a widget in the same package. Every source is a safe relative `.vue` path under `source/frontend/` and must exist in the ZIP.

## Compiled artifact

The install-time compiler produces a content-addressed artifact beneath persistent writable state, not the application release:

```text
/var/lib/3mm/core/extensions/compiled/<module-id>/<version>/<source-hash>/
  compiled-ui.json
  entrypoints.json
  assets/<entrypoint-hash>.mjs
  assets/<style-hash>.css
```

The compiler runs in a temporary workspace, resolves only bundled build dependencies, rejects non-allowlisted source imports and publishes atomically only after every declared entrypoint compiles. A failed build leaves no catalog record or partial artifact. The production process-level CPU, memory, filesystem and network restrictions are completed and verified during Stage 4 Raspberry hardening.

## Host boundary

Compiled source may import only the stable Extension Host SDK and an allowlisted set of frontend dependencies. Imports from arbitrary Core source paths are rejected. Backend Python, shell commands, package-manager hooks and runtime dependency downloads are outside compiled-UI v1.

The current bare-import allowlist is `vue`, `@platform/ui/v1` and
`@platform/application-ui/v1`. The UI entry is a separately versioned
**presentation-only** contract; the application entry supplies reviewed host
operations and presentation access. Neither exposes private Core stores, router
or credentials. The host import map resolves these entries to hashed modules in
the prebuilt frontend; the installer does not bundle another Vue or download
dependencies. Hosts must supply the actual current import entries; there is no
old-name alias. See [Public Extension UI v1](EXTENSION_UI_V1.md)
and the [neutral UI reference](../modules/ui-reference/README.md).

This is reviewed executable code, not a browser security sandbox. The public
UI contract does not weaken backend authorization and does not make arbitrary
global CSS a supported theme integration. Declarative theme ZIPs are separate.

The Stage 3 frontend loader resolves widget, route, editor and component entrypoints from validated catalog metadata and loads only the immutable JavaScript/CSS URLs that include the reviewed source hash. Persisted compiled widget types include module ID, version and entrypoint ID. Core never branches on a concrete extension name.
