# Workflow — Run fast checks before pushing/PR

Goal: catch type/lint/test failures quickly.

## 1) Frontend checks

From repo root:

- Typecheck:
  - `cd frontend && npm run type-check` (see [`frontend/package.json`](frontend/package.json:6))
- Lint:
  - `cd frontend && npm run lint`
- Unit tests (when changing UI logic/components):
  - `cd frontend && npm run test:unit`

## 2) Backend checks

With the backend venv active (created by [`start_backend.sh`](start_backend.sh:1)):

- Tests:
  - `pytest` (tests live under [`backend/tests/`](backend/tests/:1))
- Formatting (when you touched Python code):
  - `black backend/`
  - `isort backend/`

## 3) Minimal DoD

- No console errors in frontend.
- No failing tests.
- No obvious i18n regressions (no raw keys shown).

