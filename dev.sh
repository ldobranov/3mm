#!/usr/bin/env bash

set -Eeuo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
backend_venv="$project_root/backend/.venv"
backend_pid=""

cleanup() {
  if [[ -n "$backend_pid" ]] && kill -0 "$backend_pid" 2>/dev/null; then
    kill "$backend_pid" 2>/dev/null || true
    wait "$backend_pid" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM
cd "$project_root"

if [[ ! -x "$backend_venv/bin/python" ]]; then
  echo "Creating backend virtual environment..."
  python3 -m venv "$backend_venv"
fi

echo "Installing backend dependencies..."
"$backend_venv/bin/python" -m pip install -r backend/requirements.txt

if [[ ! -d frontend/node_modules ]]; then
  echo "Installing frontend dependencies..."
  npm --prefix frontend ci
fi

echo "Starting 3mm Core on http://localhost:8887 ..."
"$backend_venv/bin/python" -m uvicorn backend.main:app \
  --reload \
  --host "${BACKEND_HOST:-0.0.0.0}" \
  --port "${BACKEND_PORT:-8887}" &
backend_pid=$!

for attempt in {1..30}; do
  if ! kill -0 "$backend_pid" 2>/dev/null; then
    echo "Backend stopped before becoming healthy." >&2
    wait "$backend_pid"
  fi

  if "$backend_venv/bin/python" -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${BACKEND_PORT:-8887}/health', timeout=1).read()" \
    2>/dev/null; then
    break
  fi
  sleep 0.5
done

if ! "$backend_venv/bin/python" -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${BACKEND_PORT:-8887}/health', timeout=1).read()" \
  2>/dev/null; then
  echo "Backend did not become healthy within 15 seconds." >&2
  exit 1
fi

echo "Starting 3mm web interface on http://localhost:5173 ..."
npm --prefix frontend run dev -- --host "${FRONTEND_HOST:-127.0.0.1}"
