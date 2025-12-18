# Workspace Rules — 3mm

These rules are **repo-specific**. They exist to keep the FastAPI backend, Vue 3 frontend, and the extension system consistent.

## 1) Repo layout (where code belongs)

- Backend code lives in [`backend/`](backend/:1).
  - API routes in [`backend/routes/`](backend/routes/:1).
  - Pydantic schemas in [`backend/schemas/`](backend/schemas/:1).
  - Shared extension infrastructure and helpers in [`backend/utils/`](backend/utils/:1).
- Frontend app lives in [`frontend/src/`](frontend/src/:1).
  - Shared utils in [`frontend/src/utils/`](frontend/src/utils/:1).
  - Extension UI under [`frontend/src/extensions/`](frontend/src/extensions/:1).

## 2) Extensions: versioning + required files

Extensions are versioned folders (examples under [`backend/extensions/`](backend/extensions/:1)).

### 2.1 Folder naming

- Use `Name_1.0.0` folder names, e.g. `StoreExtension_1.0.0`.
- Keep **name + version** consistent between backend and frontend sides.

### 2.2 Minimum extension contract

Backend extension directory (installed runtime) must include:

- `manifest.json` (see patterns like [`backend/extensions/StoreExtension_1.0.0/manifest.json`](backend/extensions/StoreExtension_1.0.0/manifest.json:1))
- `locales/<lang>.json` if it has backend-side text / API-driven UI strings
- a backend entry module implementing an initializer (see guide skeleton in [`EXTENSION_DEVELOPMENT_GUIDE.md`](EXTENSION_DEVELOPMENT_GUIDE.md:97))
- optional `database_schema.json` when the extension owns tables

Frontend extension directory must include:

- `manifest.json`
- `<ExtensionName>.vue` entry component
- `locales/<lang>.json` (at least `en.json`, and `bg.json` when Bulgarian is supported)

## 3) i18n rules (avoid broken keys)

- Use namespaced keys (e.g. `store.*`, `pages.*`, `myExtension.*`).
- Key paths must match the JSON structure exactly; don’t “guess” nesting.
- Never delete or rename existing keys without a migration plan; prefer adding new keys.
- Always use the app i18n helper (see usage in [`EXTENSION_DEVELOPMENT_GUIDE.md`](EXTENSION_DEVELOPMENT_GUIDE.md:141) and implementation in [`frontend/src/utils/i18n.ts`](frontend/src/utils/i18n.ts:1)).

## 4) Backend conventions

- New endpoints go in the relevant router file under [`backend/routes/`](backend/routes/:1).
- Changes that alter API response shape require schema updates under [`backend/schemas/`](backend/schemas/:1).
- DB changes require Alembic migrations under [`backend/alembic/versions/`](backend/alembic/versions/:1).

### 4.1 Extension table naming (critical for deletion)

Extensions must create tables with consistent naming for proper cleanup:

- **Pattern**: `ext_{extension.name.lower()}_table` (lowercase)
- **Example**: StoreExtension → `ext_storeextension_products`
- **Deletion**: looks for `ext_{extension.name.lower()}%` (case-sensitive match required)

**Violation causes**: tables not dropped during extension deletion, leaving orphaned data.

### 4.1 Extension table naming (critical for deletion)

Extensions must create tables with consistent naming for proper cleanup:

- **Pattern**: `ext_{extension.name.lower().replace('extension', '')}_table`
- **Example**: StoreExtension → `ext_storeextension_products`
- **Deletion**: looks for `ext_{extension.name.lower()}%` (case-sensitive match required)

**Violation causes**: tables not dropped during extension deletion, leaving orphaned data.

## 5) Frontend conventions

- Keep extension UI concerns inside the extension folder under [`frontend/src/extensions/`](frontend/src/extensions/:1).
- Shared, reusable logic belongs in [`frontend/src/utils/`](frontend/src/utils/:1).

## 6) Definition of Done (DoD)

For any PR/changeset:

- Backend:
  - [ ] Routes updated (if needed)
  - [ ] Schemas updated (if response/request shape changed)
  - [ ] Tests updated/added under [`backend/tests/`](backend/tests/:1) when behavior changes
- Extensions:
  - [ ] Manifest updated if contract changed
  - [ ] Locales updated for new UI strings (at least `en`)
  - [ ] Version bump rules followed for breaking changes
- Frontend:
  - [ ] UI renders + basic smoke test (no console errors)
  - [ ] i18n keys resolve (no raw key strings)

## 7) Standard local dev commands (preferred)

- Backend (first time): use [`start_backend.sh`](start_backend.sh:1)
- Backend (subsequent runs): use [`quick_start.sh`](quick_start.sh:1)
- Frontend: `cd frontend && npm run dev` (see [`frontend/package.json`](frontend/package.json:6))

## 8) Extension packaging

Extensions can be packaged from their installed location (recommended):

```bash
zip -r ExtensionName_Version.zip \
    backend/extensions/ExtensionName_Version/ \
    frontend/src/extensions/ExtensionName_Version/
```

The installer recognizes both traditional `frontend/` directory structure and installed `frontend/src/extensions/` structure.

## 8) Quality gates (fast checks before PR)

- Frontend:
  - `cd frontend && npm run type-check`
  - `cd frontend && npm run lint`
  - `cd frontend && npm run test:unit` (if relevant)
- Backend (with venv active):
  - `pytest`
  - `black backend/` and `isort backend/` when formatting/imports change
