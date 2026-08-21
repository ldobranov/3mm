# Compiled UI Extension v1

Status: Stage 3 generic browser loader; Milestone 8

## Purpose

Compiled UI extensions contain reviewed Vue source that is converted once during installation into immutable browser-ready JavaScript and CSS. They support widgets, routes, editors and reusable components through one data-driven contract. They do not require a Vite development server and do not modify the prebuilt Core frontend.

This format is separate from declarative runtime extensions. Runtime extensions remain the preferred no-code path. Compiled UI extensions cross an executable-code trust boundary and require administrator review and isolated compilation.

## Source package

A source package contains:

- `manifest.json` using module manifest v2;
- `compiled-ui.json` using `CompiledUiExtensionV1`;
- declared `.vue` entrypoints under `source/frontend/`;
- optional supporting TypeScript, JavaScript, CSS and JSON under `source/frontend/`.

Stage 1 rejects backend source and files outside this boundary. The package declares `entrypoints.ui` as `compiled-ui.json` and targets only the `ui` runtime.

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

The Stage 3 frontend loader resolves widget, route, editor and component entrypoints from validated catalog metadata and loads only the immutable JavaScript/CSS URLs that include the reviewed source hash. Persisted compiled widget types include module ID, version and entrypoint ID. Core never branches on a concrete extension name.
