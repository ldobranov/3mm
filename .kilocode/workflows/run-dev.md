# Workflow — Run the app locally (backend + frontend)

## 1) Backend

Preferred:

- First-time setup + run:
  - `./start_backend.sh` (see [`start_backend.sh`](start_backend.sh:1))
- Subsequent runs:
  - `./quick_start.sh` (see [`quick_start.sh`](quick_start.sh:1))

Manual fallback:

- `source backend/venv/bin/activate`
- `uvicorn backend.main:app --reload --host 0.0.0.0 --port 8887` (config reference in [`config.json`](config.json:1))

## 2) Frontend

- `cd frontend && npm install` (first time)
- `cd frontend && npm run dev` (see [`frontend/package.json`](frontend/package.json:6))

## 3) Smoke-test checklist

- Open frontend (typically `http://localhost:5173`).
- Verify it can reach backend (`http://localhost:8887`).
- Check browser console: no runtime errors.

