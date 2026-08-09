#!/usr/bin/env bash

set -Eeuo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${THREE_MM_PYTHON:-$project_root/backend/.venv/bin/python}"
runtime_root="${THREE_MM_RUNTIME_ROOT:-$project_root/.runtime/agents}"
pids=()

cleanup() {
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  for pid in "${pids[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
}

trap cleanup EXIT INT TERM

if [[ ! -x "$python_bin" ]]; then
  echo "Python environment not found: $python_bin" >&2
  echo "Run ./dev.sh once or set THREE_MM_PYTHON." >&2
  exit 1
fi

mkdir -p "$runtime_root/agent-1" "$runtime_root/agent-2"
cd "$project_root"

echo "Starting mock-pi3-01 on http://127.0.0.1:8890 ..."
"$python_bin" -m agent \
  --host 127.0.0.1 \
  --port 8890 \
  --data-dir "$runtime_root/agent-1" \
  --name mock-pi3-01 \
  --role node &
pids+=("$!")

echo "Starting mock-zero2-01 on http://127.0.0.1:8891 ..."
"$python_bin" -m agent \
  --host 127.0.0.1 \
  --port 8891 \
  --data-dir "$runtime_root/agent-2" \
  --name mock-zero2-01 \
  --role node &
pids+=("$!")

device_ids=()
for port in 8890 8891; do
  for attempt in {1..30}; do
    if "$python_bin" -c \
      "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$port/health', timeout=1).read()" \
      2>/dev/null; then
      break
    fi
    sleep 0.25
  done

  if ! "$python_bin" -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$port/health', timeout=1).read()" \
    2>/dev/null; then
    echo "Agent on port $port did not become healthy." >&2
    exit 1
  fi

  device_id="$("$python_bin" -c \
    "import json, urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:$port/ready', timeout=1))['device_id'])")"
  device_ids+=("$device_id")
  echo "Agent on port $port is ready as $device_id."
done

if [[ "${device_ids[0]}" == "${device_ids[1]}" ]]; then
  echo "Agents unexpectedly share the same device identity." >&2
  exit 1
fi

echo "Both Agents are healthy. Press Ctrl+C to stop them."
wait "${pids[@]}"
