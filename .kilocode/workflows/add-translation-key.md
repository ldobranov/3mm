# Workflow — Add a new translation key

Goal: add a UI string safely without breaking existing translations.

## 1) Choose a namespaced key

- Prefer `extensionNamespace.section.key`.
- Example: `store.productSelector.title`.

## 2) Add to English first

- Add the key to `locales/en.json` for the owning extension.
- Provide a clear English value.

## 3) Maintain locale parity

- If the extension supports other languages, add the same key path to each locale file.
- Use a real translation when possible; otherwise use an obvious placeholder.

Examples of locale files in this repo:

- Backend-side locales: [`backend/extensions/StoreExtension_1.0.0/locales/en.json`](backend/extensions/StoreExtension_1.0.0/locales/en.json:1)
- Frontend-side locales: [`frontend/src/extensions/StoreExtension_1.0.0/locales/en.json`](frontend/src/extensions/StoreExtension_1.0.0/locales/en.json:1)

## 4) Use via i18n helper

- Always render strings through `t(key, fallback)` (see [`EXTENSION_DEVELOPMENT_GUIDE.md`](EXTENSION_DEVELOPMENT_GUIDE.md:151)).
- If dynamically loading another extension’s components, ensure its translations are loaded (see relationship/i18n notes in [`EXTENSION_DEVELOPMENT_GUIDE.md`](EXTENSION_DEVELOPMENT_GUIDE.md:222)).

## 5) Verify

- Run the UI and ensure no raw keys are displayed.
- Switch language; ensure the UI updates.

