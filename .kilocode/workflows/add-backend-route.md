# Workflow — Add or change a backend API route

## 1) Pick the right router module

- Add or update endpoints under [`backend/routes/`](backend/routes/:1).
- Keep routes grouped by domain (extensions, pages, auth, etc.).

## 2) Update schemas

- If request/response shapes change, update/add Pydantic models under [`backend/schemas/`](backend/schemas/:1).

## 3) Auth + permissions

- Default: require authentication unless the endpoint is explicitly public.
- For extension routes, keep public endpoints consistent with manifest `public_endpoints` contract (see guidance in [`EXTENSION_DEVELOPMENT_GUIDE.md`](EXTENSION_DEVELOPMENT_GUIDE.md:271)).

## 4) DB changes

- If you change persistent data schema, add an Alembic migration under [`backend/alembic/versions/`](backend/alembic/versions/:1).

## 5) Tests

- Add/adjust tests under [`backend/tests/`](backend/tests/:1) for behavior changes.

## 6) Verify

- Start backend and hit the endpoint (or run tests).

