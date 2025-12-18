# Workflow — Create a new extension (backend + frontend)

This workflow mirrors the repo’s extension contract as described in [`EXTENSION_DEVELOPMENT_GUIDE.md`](EXTENSION_DEVELOPMENT_GUIDE.md:7).

## 0) Decide name/version/type

- Pick `Name` and `version` (example: `MyExtension` + `1.0.0`).
- Decide type: full extension vs widget vs language pack.

## 1) Create folders

- Backend folder:
  - `backend/extensions/MyExtension_1.0.0/`
- Frontend folder:
  - `frontend/src/extensions/MyExtension_1.0.0/`

## 2) Add manifests

- Add backend manifest `backend/extensions/MyExtension_1.0.0/manifest.json`
- Add frontend manifest `frontend/src/extensions/MyExtension_1.0.0/manifest.json`

Rules:

- Keep `name` + `version` identical.
- Ensure `backend_entry` points to your backend module file.
- Ensure `frontend_entry` points to your Vue entry component.

Reference examples:

- Store manifest: [`backend/extensions/StoreExtension_1.0.0/manifest.json`](backend/extensions/StoreExtension_1.0.0/manifest.json:1)

## 3) Add locales

Create locale files:

- `frontend/src/extensions/MyExtension_1.0.0/locales/en.json`
- `frontend/src/extensions/MyExtension_1.0.0/locales/bg.json` (if bg is supported)

Guidelines:

- Use namespaced keys, e.g. `my.*` or `myExtension.*`.
- Do not reuse keys from other extensions.

## 4) Implement backend entry

Create `backend/extensions/MyExtension_1.0.0/my_extension.py` (or similar) implementing:

- `initialize_extension(context)` (register an `APIRouter`)
- optional `cleanup_extension(context)`

Reference skeleton: [`EXTENSION_DEVELOPMENT_GUIDE.md`](EXTENSION_DEVELOPMENT_GUIDE.md:99)

## 5) Implement frontend entry

Create `frontend/src/extensions/MyExtension_1.0.0/MyExtension.vue`:

- Use the app i18n helper (`t()` / `currentLanguage`) from [`frontend/src/utils/i18n.ts`](frontend/src/utils/i18n.ts:1)
- Keep all extension UI inside this folder.

## 6) Wire routes (if the extension has a page)

- Add `frontend_routes` in the manifest.
- Ensure route `meta.requiresAuth` is set appropriately.

## 7) (Optional) Database schema

If the extension owns tables:

- Add `database_schema.json`
- Follow lower-case table naming guidance (see [`EXTENSION_DEVELOPMENT_GUIDE.md`](EXTENSION_DEVELOPMENT_GUIDE.md:123)).

## 8) Smoke test

- Start backend and verify your `/api/<prefix>/health` endpoint returns OK.
- Start frontend and verify the route renders, and language switching updates labels.

