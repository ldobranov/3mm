# Workflow — Add a cross-extension relationship (e.g., content embedder)

This repo supports manifest-driven integration between extensions (see [`EXTENSION_DEVELOPMENT_GUIDE.md`](EXTENSION_DEVELOPMENT_GUIDE.md:198)).

## 1) Provider extension: declare what it provides

- Update the provider’s manifest:
  - Example location: [`backend/extensions/StoreExtension_1.0.0/manifest.json`](backend/extensions/StoreExtension_1.0.0/manifest.json:1)
- Add/extend a `provides` block (e.g. `content_embedders`).

## 2) Provider backend: implement the API contract

- Ensure the backend entry registers endpoints needed by the relationship.
- Keep the router wiring inside the extension entry module (see [`EXTENSION_DEVELOPMENT_GUIDE.md`](EXTENSION_DEVELOPMENT_GUIDE.md:99)).

## 3) Provider frontend: expose the component

- Put relationship UI components under the provider extension folder:
  - [`frontend/src/extensions/`](frontend/src/extensions/:1)
- Ensure the component is referenced correctly in the manifest.

## 4) Consumer frontend: discover + load

- Use the relationship helper in [`frontend/src/utils/extension-relationships.ts`](frontend/src/utils/extension-relationships.ts:1).
- When dynamically importing a provider component, also load its translations for the current UI language (see [`EXTENSION_DEVELOPMENT_GUIDE.md`](EXTENSION_DEVELOPMENT_GUIDE.md:222)).

## 5) Verify end-to-end

- Provider enabled.
- Consumer can discover the relationship and render the UI.
- Language switch updates all related UI strings.
