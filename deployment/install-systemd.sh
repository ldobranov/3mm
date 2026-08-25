#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this installer as root." >&2
  exit 1
fi
if [[ $# -lt 3 || $# -gt 5 ]]; then
  echo "Usage: $0 RELEASE_ARCHIVE RELEASE_ID FRONTEND_ORIGIN [IDENTITY_FILE] [ARCHIVE_SHA256]" >&2
  exit 1
fi

release_archive=$(realpath "$1")
release_id=$2
frontend_origin=$3
identity_source=${4:-}
expected_archive_sha256=${5:-}

if [[ ! $release_id =~ ^[a-zA-Z0-9._-]+$ ]]; then
  echo "Release ID contains unsupported characters." >&2
  exit 1
fi
if [[ ! $frontend_origin =~ ^https?://[a-zA-Z0-9.-]+(:[0-9]{1,5})?$ ]]; then
  echo "Frontend origin must be a plain HTTP(S) origin without a path." >&2
  exit 1
fi
if [[ -n $expected_archive_sha256 && ! $expected_archive_sha256 =~ ^[a-fA-F0-9]{64}$ ]]; then
  echo "Archive SHA-256 is invalid." >&2
  exit 1
fi
if [[ ! -f $release_archive ]]; then
  echo "Release archive does not exist: $release_archive" >&2
  exit 1
fi
if [[ -n $expected_archive_sha256 ]]; then
  actual_archive_sha256=$(sha256sum "$release_archive" | awk '{print $1}')
  if [[ $actual_archive_sha256 != "${expected_archive_sha256,,}" ]]; then
    echo "Release archive checksum does not match." >&2
    exit 1
  fi
fi

install_root=/opt/3mm
releases_root=$install_root/releases
release_dir=$releases_root/$release_id
current_link=$install_root/current
state_root=/var/lib/3mm
core_state=$state_root/core
database=$core_state/3mm.db
backup_root=$state_root/deploy-backups/$release_id
environment_file=/etc/3mm/3mm.env
ai_master_key_file=/etc/3mm/ai-settings.key
all_services=(
  3mm-agent.service
  3mm-core.service
  3mm-web.service
  3mm-setup.service
  3mm-setup-ap.service
  3mm-network-helper.service
)
previous_release=""
release_created=0
mutation_started=0
database_backup_created=0
environment_backup_created=0
environment_tmp=""

log() {
  printf '\n==> %s\n' "$1"
}

fail() {
  echo "$1" >&2
  return 1
}

assert_release_path() {
  local target=$1
  case "$target" in
    "$releases_root"/*) ;;
    *)
      echo "Refusing unsafe release path: $target" >&2
      return 1
      ;;
  esac
  [[ $target != "$releases_root" ]]
}

install_units() {
  local source_release=$1
  local unit
  for unit in "${all_services[@]}"; do
    install -o root -g root -m 0644 \
      "$source_release/deployment/systemd/$unit" "/etc/systemd/system/$unit"
  done
  systemctl daemon-reload
}

release_python() {
  local source_release=$1
  if [[ -x $source_release/.venv/bin/python ]]; then
    printf '%s\n' "$source_release/.venv/bin/python"
    return
  fi
  if [[ -x $install_root/venv/bin/python ]]; then
    # Compatibility only for rolling back the pre-2026-08-24 release layout.
    printf '%s\n' "$install_root/venv/bin/python"
    return
  fi
  fail "No Python environment is available for $source_release"
}

restore_database() {
  if [[ $database_backup_created -eq 1 && -f $backup_root/3mm.db ]]; then
    install -o 3mm -g 3mm -m 0640 "$backup_root/3mm.db" "$database"
    rm -f -- "${database}-wal" "${database}-shm"
  fi
}

restore_environment() {
  if [[ $environment_backup_created -eq 1 ]]; then
    install -o root -g 3mm -m 0640 "$backup_root/3mm.env" "$environment_file"
  elif [[ -f $backup_root/environment-was-absent ]]; then
    rm -f -- "$environment_file"
  fi
}

verify_endpoint() {
  local endpoint=$1
  local ready=0
  local attempt
  for attempt in $(seq 1 60); do
    if curl -fsS --max-time 3 "$endpoint" >/dev/null; then
      ready=1
      break
    fi
    sleep 1
  done
  if [[ $ready -ne 1 ]]; then
    echo "Health check failed: $endpoint" >&2
    return 1
  fi
}

verify_runtime() {
  local active_count=0
  local pair service endpoint
  local checks=(
    '3mm-agent.service|http://127.0.0.1:8890/ready'
    '3mm-core.service|http://127.0.0.1:8887/ready'
    '3mm-web.service|http://127.0.0.1:8080/user/login'
    '3mm-setup.service|http://127.0.0.1:8895/ready'
  )
  for pair in "${checks[@]}"; do
    service=${pair%%|*}
    endpoint=${pair#*|}
    if systemctl is-active --quiet "$service"; then
      active_count=$((active_count + 1))
      verify_endpoint "$endpoint"
    fi
  done
  if [[ $active_count -eq 0 ]]; then
    echo "Runtime planner did not activate an application or setup service." >&2
    return 1
  fi
}

activate_runtime() {
  local source_release=$1
  local python_path
  python_path=$(release_python "$source_release")
  PYTHONPATH="$source_release" \
    "$python_path" -m three_mm_runtime.activate
  verify_runtime
}

rollback() {
  local exit_code=$?
  trap - ERR
  set +e
  echo >&2
  echo "Deployment failed; restoring ${previous_release:-the previous system state}." >&2

  if [[ $mutation_started -eq 1 ]]; then
    systemctl stop "${all_services[@]}" >/dev/null 2>&1 || true
    restore_database
    restore_environment
    if [[ -n $previous_release && -d $previous_release ]]; then
      ln -sfnT "$previous_release" "$current_link"
      install_units "$previous_release" || true
      activate_runtime "$previous_release" || {
        systemctl --no-pager --full status "${all_services[@]}" >&2 || true
        echo "Rollback completed, but the previous release is not healthy." >&2
      }
    fi
  fi

  if [[ $release_created -eq 1 && -d $release_dir ]]; then
    assert_release_path "$release_dir" && rm -rf -- "$release_dir"
  fi
  if [[ -n $environment_tmp ]]; then
    rm -f -- "$environment_tmp" "${environment_tmp}.next"
  fi
  rm -f -- "$release_archive"
  exit "$exit_code"
}

if [[ -L $current_link ]]; then
  previous_release=$(readlink -f "$current_link")
fi
if [[ -n $previous_release && ! -d $previous_release ]]; then
  echo "Current release link does not resolve to a directory." >&2
  exit 1
fi
if [[ -e $release_dir ]]; then
  echo "Release already exists: $release_dir" >&2
  exit 1
fi
assert_release_path "$release_dir"

if ! id -u 3mm >/dev/null 2>&1; then
  useradd --system --home-dir "$state_root" --shell /usr/sbin/nologin 3mm
fi

install -d -o root -g root -m 0755 "$install_root" "$releases_root" /etc/3mm
install -d -o 3mm -g 3mm -m 0750 "$state_root"
install -d -o 3mm -g 3mm -m 0700 "$state_root/agent"

if [[ -n $identity_source && ! -e $state_root/agent/identity.json ]]; then
  identity_source=$(realpath "$identity_source")
  install -o 3mm -g 3mm -m 0600 "$identity_source" \
    "$state_root/agent/identity.json"
fi

trap rollback ERR

log "Extracting immutable release"
unsafe_archive_entry=$(tar -tzf "$release_archive" | awk '
  /^\// || /(^|\/)\.\.(\/|$)/ { print; exit }
')
if [[ -n $unsafe_archive_entry ]]; then
  fail "Release archive contains an unsafe path: $unsafe_archive_entry"
fi
install -d -o root -g root -m 0755 "$release_dir"
release_created=1
tar -xzf "$release_archive" -C "$release_dir" \
  --no-same-owner --no-same-permissions

required_files=(
  frontend/dist/index.html
  backend/requirements.txt
  deployment/migrate_database.py
  deployment/systemd/3mm-core.service
  deployment/systemd/3mm-web.service
  deployment/systemd/3mm-agent.service
)
for required_file in "${required_files[@]}"; do
  if [[ ! -f $release_dir/$required_file ]]; then
    fail "Release artifact is incomplete: $required_file is required."
  fi
done
if [[ ! -d $release_dir/frontend/dist/assets ]] || \
   ! find "$release_dir/frontend/dist/assets" -maxdepth 1 -type f -name '*.js' -print -quit | grep -q .; then
  fail "Frontend artifact is incomplete: dist/assets/*.js is required."
fi

log "Creating the release-specific Python environment"
python3 -m venv "$release_dir/.venv"
"$release_dir/.venv/bin/python" -m pip install \
  --disable-pip-version-check \
  --requirement "$release_dir/backend/requirements.txt"

if ! command -v npm >/dev/null 2>&1; then
  fail "Node.js/npm is required for the compiled UI extension toolchain."
fi
npm install --prefix "$release_dir/frontend/compiler" \
  --ignore-scripts --no-audit --no-fund

log "Stopping services and backing up persistent state"
systemctl stop "${all_services[@]}" >/dev/null 2>&1 || true
mutation_started=1
install -d -o root -g root -m 0700 "$backup_root"
if [[ -f $database ]]; then
  "$release_dir/.venv/bin/python" - "$database" "$backup_root/3mm.db" <<'PY'
import sqlite3
import sys

source = sqlite3.connect(sys.argv[1])
backup = sqlite3.connect(sys.argv[2])
try:
    source.backup(backup)
finally:
    backup.close()
    source.close()
PY
  chown root:root "$backup_root/3mm.db"
  chmod 0600 "$backup_root/3mm.db"
  database_backup_created=1
fi
if [[ -f $environment_file ]]; then
  install -o root -g root -m 0600 "$environment_file" "$backup_root/3mm.env"
  environment_backup_created=1
else
  : > "$backup_root/environment-was-absent"
  chmod 0600 "$backup_root/environment-was-absent"
fi

log "Updating the persistent service environment"
environment_tmp=$(mktemp /etc/3mm/3mm.env.XXXXXX)
if [[ -f $environment_file ]]; then
  cat "$environment_file" > "$environment_tmp"
fi
upsert_environment() {
  local key=$1
  local value=$2
  local next_file=${environment_tmp}.next
  awk -F= -v wanted="$key" '$1 != wanted' "$environment_tmp" > "$next_file"
  printf '%s=%s\n' "$key" "$value" >> "$next_file"
  mv "$next_file" "$environment_tmp"
}
upsert_environment DATABASE_URL sqlite:////var/lib/3mm/core/3mm.db
upsert_environment UPLOADS_DIR /var/lib/3mm/core/uploads
upsert_environment BACKEND_EXTENSIONS_DIR /var/lib/3mm/core/extensions/backend
upsert_environment FRONTEND_EXTENSIONS_DIR /var/lib/3mm/core/extensions/frontend
upsert_environment COMPILED_UI_ARTIFACTS_DIR /var/lib/3mm/core/extensions/compiled
upsert_environment BACKEND_HOST 0.0.0.0
upsert_environment BACKEND_PORT 8887
upsert_environment CORS_ORIGINS "[\"$frontend_origin\"]"
upsert_environment DEVICE_OFFLINE_AFTER_SECONDS 90
upsert_environment THREE_MM_AGENT_HOST 127.0.0.1
upsert_environment THREE_MM_AGENT_PORT 8890
upsert_environment THREE_MM_AGENT_ROLE standalone
upsert_environment THREE_MM_AGENT_HARDWARE_PROFILE native
upsert_environment THREE_MM_CORE_URL http://127.0.0.1:8887
upsert_environment THREE_MM_HEARTBEAT_INTERVAL_SECONDS 30
upsert_environment THREE_MM_PROVISIONING_DATA_DIR /var/lib/3mm/provisioning
upsert_environment THREE_MM_SETUP_HOST 0.0.0.0
upsert_environment THREE_MM_SETUP_PORT 8895

if [[ -s $ai_master_key_file ]]; then
  ai_master_key=$(cat "$ai_master_key_file")
else
  ai_master_key=$(awk -F= '$1 == "AI_SETTINGS_MASTER_KEY" {sub(/^[^=]*=/, ""); print; exit}' "$environment_tmp")
  if [[ -z $ai_master_key ]]; then
    ai_master_key=$("$release_dir/.venv/bin/python" -c \
      'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
  fi
  printf '%s\n' "$ai_master_key" > "$ai_master_key_file"
fi
chown root:3mm "$ai_master_key_file"
chmod 0640 "$ai_master_key_file"
upsert_environment AI_SETTINGS_MASTER_KEY "$ai_master_key"
install -o root -g 3mm -m 0640 "$environment_tmp" "$environment_file"
rm -f -- "$environment_tmp"

install -d -o 3mm -g 3mm -m 0750 \
  "$core_state" \
  "$core_state/uploads" \
  "$core_state/uploads/modules" \
  "$core_state/extensions/backend" \
  "$core_state/extensions/frontend" \
  "$core_state/extensions/compiled" \
  "$state_root/provisioning"

log "Installing service definitions and migrating the database"
install_units "$release_dir"
runuser -u 3mm -- env \
  DATABASE_URL=sqlite:////var/lib/3mm/core/3mm.db \
  UPLOADS_DIR=/var/lib/3mm/core/uploads \
  BACKEND_EXTENSIONS_DIR=/var/lib/3mm/core/extensions/backend \
  FRONTEND_EXTENSIONS_DIR=/var/lib/3mm/core/extensions/frontend \
  COMPILED_UI_ARTIFACTS_DIR=/var/lib/3mm/core/extensions/compiled \
  PYTHONPATH="$release_dir" \
  "$release_dir/.venv/bin/python" "$release_dir/deployment/migrate_database.py"

log "Activating release atomically"
ln -sfnT "$release_dir" "$current_link"
activate_runtime "$release_dir"

log "Deployment succeeded"
rm -f -- "$release_archive"
systemctl --no-pager --full status "${all_services[@]}" 2>/dev/null || true
trap - ERR
