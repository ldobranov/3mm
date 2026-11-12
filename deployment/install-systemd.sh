#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this installer as root." >&2
  exit 1
fi
if [[ $# -lt 3 || $# -gt 6 ]]; then
  echo "Usage: $0 RELEASE_ARCHIVE RELEASE_ID FRONTEND_ORIGIN [IDENTITY_FILE] [ARCHIVE_SHA256] [full|node]" >&2
  exit 1
fi

release_archive=$(realpath "$1")
release_id=$2
frontend_origin=$3
device_hostname=$(hostname -s)
identity_source=${4:-}
expected_archive_sha256=${5:-}
install_profile=${6:-full}
architecture=$(uname -m)
if [[ $install_profile != full && $install_profile != node ]]; then
  echo "Installation profile must be full or node." >&2
  exit 1
fi
if [[ $install_profile == full && $architecture == armv6l ]]; then
  [[ -n $expected_archive_sha256 ]] || { echo "ARMv6 Hub requires a verified release archive." >&2; exit 1; }
  python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 13) else "ARMv6 Hub requires Python 3.13")'
fi
# Node packaging is experimental until clean-install/rollback acceptance.
if [[ $install_profile == node && -z $expected_archive_sha256 ]]; then
  echo "Node installation requires an explicit archive SHA-256." >&2
  exit 1
fi
test_fail_after_health=${THREE_MM_INSTALLER_TEST_FAIL_AFTER_HEALTH:-0}

if [[ ! $release_id =~ ^[a-zA-Z0-9._-]+$ || $release_id == . || $release_id == .. ]]; then
  echo "Release ID contains unsupported characters." >&2
  exit 1
fi
if [[ ! $frontend_origin =~ ^https?://[a-zA-Z0-9.-]+(:[0-9]{1,5})?$ ]]; then
  echo "Frontend origin must be a plain HTTP(S) origin without a path." >&2
  exit 1
fi
if [[ ! $device_hostname =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]]; then
  echo "Device hostname cannot be published through mDNS: $device_hostname" >&2
  exit 1
fi
if [[ -n $expected_archive_sha256 && ! $expected_archive_sha256 =~ ^[a-fA-F0-9]{64}$ ]]; then
  echo "Archive SHA-256 is invalid." >&2
  exit 1
fi
if [[ $test_fail_after_health != 0 && $test_fail_after_health != 1 ]]; then
  echo "THREE_MM_INSTALLER_TEST_FAIL_AFTER_HEALTH must be 0 or 1." >&2
  exit 1
fi
if [[ $test_fail_after_health == 1 && $release_id != rollback-test-* ]]; then
  echo "Post-health failure injection requires a rollback-test-* release ID." >&2
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
previous_link=$install_root/previous
state_root=/var/lib/3mm
core_state=$state_root/core
database=$core_state/3mm.db
database_existed_before_deploy=0
if [[ -f $database ]]; then
  database_existed_before_deploy=1
fi
backup_root=$state_root/deploy-backups/$release_id
deploy_cache_root=/var/cache/3mm/deploy
deploy_home=$deploy_cache_root/home
npm_cache=$deploy_cache_root/npm
environment_file=/etc/3mm/3mm.env
agent_environment_file=/etc/3mm-agent/agent.env
network_backend=${THREE_MM_NETWORK_BACKEND:-}
if [[ -z $network_backend && -f $environment_file ]]; then
  network_backend=$(awk -F= '$1 == "THREE_MM_NETWORK_BACKEND" {value=$2} END {print value}' "$environment_file")
fi
if [[ -z $network_backend ]]; then
  if [[ -f $environment_file || -L $current_link || -d $state_root/provisioning ]]; then
    network_backend=host
  else
    network_backend=network-manager
  fi
fi
if [[ $network_backend != host && $network_backend != network-manager ]]; then
  echo "Network backend must be host or network-manager." >&2
  exit 1
fi
export THREE_MM_NETWORK_BACKEND=$network_backend
ai_master_key_file=/etc/3mm/ai-settings.key
runtime_services=(
  3mm-agent.service
  3mm-core.service
  3mm-platform-runtime.service
  3mm-connector-worker.service
  3mm-web.service
  3mm-public-web.socket
  3mm-session-worker.socket
  3mm-host-session-worker.socket
  3mm-setup.service
  3mm-setup-local.service
  3mm-setup-ap.service
  3mm-network-helper.service
)
always_on_services=(
  3mm-update-helper.service
)
installed_units=(
  "${runtime_services[@]}"
  "${always_on_services[@]}"
  3mm-application-extension@.service
  3mm-session-worker@.service
  3mm-host-session-worker@.service
  3mm-public-web.service
)
if [[ $install_profile == node ]]; then
  runtime_services=(3mm-agent.service 3mm-setup.service 3mm-setup-local.service 3mm-setup-ap.service 3mm-network-helper.service)
  always_on_services=(3mm-node-recovery.service 3mm-node-update-helper.service)
  installed_units=("${runtime_services[@]}" "${always_on_services[@]}")
fi
previous_release=""
saved_rollback_release=""
saved_rollback_link=0
rollback_link_updated=0
release_created=0
mutation_started=0
component_transition_prepared=0
database_backup_created=0
environment_backup_created=0
agent_environment_backup_created=0
environment_tmp=""
previous_active_units=()
previous_enabled_units=()

log() {
  printf '\n==> %s\n' "$1"
}

fail() {
  echo "$1" >&2
  return 1
}

if ! command -v flock >/dev/null 2>&1; then
  fail "The release installer requires flock for deployment locking."
fi
exec 9>/run/lock/3mm-release-mutation.lock
if ! flock -n 9; then
  fail "Another deployment or release cleanup is already running."
fi

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

stop_runtime_services() {
  local listing unit load_state active_state sub_state description
  local patterns=("${runtime_services[@]}")
  local units=()
  if [[ $install_profile == full ]]; then
    patterns+=('3mm-application-extension@*.service')
    patterns+=('3mm-session-worker@*.service')
    patterns+=('3mm-host-session-worker@*.service')
  fi
  # A clean host has no installed units. Enumerate actual units instead of
  # treating systemctl stop's NOTINSTALLED response as a runtime stop failure.
  # Do not hide a failed query, or skip an orphaned unit that is still active.
  if ! listing=$(systemctl list-units --all --full --plain --no-legend --no-pager "${patterns[@]}"); then
    fail "Could not inspect runtime units; runtime quiescence is unconfirmed."
    return 1
  fi
  while read -r unit load_state active_state sub_state description; do
    [[ -n $unit ]] || continue
    if [[ $load_state == not-found && $active_state == inactive && $sub_state == dead ]]; then
      continue
    fi
    units+=("$unit")
  done <<< "$listing"
  if [[ ${#units[@]} -gt 0 ]]; then
    systemctl stop "${units[@]}" || return 1
  fi
  return 0
}

install_units() {
  local source_release=$1
  local require_update_helper=${2:-1}
  local unit
  for unit in "${installed_units[@]}"; do
    if [[ ! -f $source_release/deployment/systemd/$unit ]]; then
      if [[ ( $unit == 3mm-host-session-worker.socket || $unit == 3mm-host-session-worker@.service ) && $require_update_helper == 0 ]]; then
        systemctl disable --now 3mm-host-session-worker.socket >/dev/null 2>&1 || true
        systemctl stop '3mm-host-session-worker@*.service' >/dev/null 2>&1 || true
        rm -f -- "/etc/systemd/system/$unit"
        continue
      fi
      if [[ ( $unit == 3mm-session-worker.socket || $unit == 3mm-session-worker@.service ) && $require_update_helper == 0 ]]; then
        systemctl disable --now 3mm-session-worker.socket >/dev/null 2>&1 || true
        systemctl stop '3mm-session-worker@*.service' >/dev/null 2>&1 || true
        rm -f -- "/etc/systemd/system/$unit"
        continue
      fi
      if [[ ( $unit == 3mm-public-web.socket || $unit == 3mm-public-web.service ) && $require_update_helper == 0 ]]; then
        systemctl disable --now "$unit" >/dev/null 2>&1 || true
        rm -f -- "/etc/systemd/system/$unit"
        continue
      fi
      if [[ ( $unit == 3mm-platform-runtime.service || $unit == 3mm-connector-worker.service ) && $require_update_helper == 0 ]]; then
        systemctl disable --now "$unit" >/dev/null 2>&1 || true
        rm -f -- "/etc/systemd/system/$unit"
        continue
      fi
      if [[ $unit == 3mm-setup-local.service && $require_update_helper == 0 ]]; then
        systemctl disable --now "$unit" >/dev/null 2>&1 || true
        rm -f -- "/etc/systemd/system/$unit"
        continue
      fi
      if [[ $unit == 3mm-application-extension@.service && $require_update_helper == 0 ]]; then
        systemctl stop '3mm-application-extension@*.service' >/dev/null 2>&1 || true
        rm -f -- "/etc/systemd/system/$unit"
        continue
      fi
      if [[ $unit == 3mm-update-helper.service && $require_update_helper == 0 ]]; then
        systemctl disable --now "$unit" >/dev/null 2>&1 || true
        rm -f -- "/etc/systemd/system/$unit"
        continue
      fi
      if [[ $unit == 3mm-node-update-helper.service && $require_update_helper == 0 ]]; then
        # Older Node rollback releases predate the independent update helper.
        systemctl disable --now "$unit" >/dev/null 2>&1 || true
        rm -f -- "/etc/systemd/system/$unit"
        always_on_services=(3mm-node-recovery.service)
        continue
      fi
      fail "Release is missing required service definition: $unit"
    fi
    install -o root -g root -m 0644 \
      "$source_release/deployment/systemd/$unit" "/etc/systemd/system/$unit"
  done
  systemctl daemon-reload
}

release_python() {
  local source_release=$1
  if [[ -x $source_release/.venv/bin/python ]]; then
    printf '%s\n' "$source_release/.venv/bin/python"
    # A bare return inside the ERR handler inherits the original deploy failure,
    # even after printf succeeds. Rollback must still select the old interpreter.
    return 0
  fi
  if [[ -x $install_root/venv/bin/python ]]; then
    # Compatibility only for rolling back the pre-2026-08-24 release layout.
    printf '%s\n' "$install_root/venv/bin/python"
    return 0
  fi
  fail "No Python environment is available for $source_release"
}

restore_database() {
  if [[ $database_backup_created -eq 1 ]]; then
    [[ -f $backup_root/3mm.db ]] || return 1
    install -o 3mm -g 3mm -m 0640 "$backup_root/3mm.db" "$database" || return 1
    rm -f -- "${database}-wal" "${database}-shm" || return 1
  elif [[ $database_existed_before_deploy -eq 0 ]]; then
    rm -f -- "$database" "${database}-wal" "${database}-shm" || return 1
  fi
}

fence_rollback_authority() {
  if [[ $install_profile == full && -f $database ]]; then
    # Use the candidate's stdlib-only recovery code, not the old release which
    # may predate M20. The release lock is still held; no services may start yet.
    python3 "$release_dir/deployment/authority_recovery.py" \
      --reason deployment_rollback --allow-legacy || return 1
  fi
}

restore_environment() {
  if [[ $environment_backup_created -eq 1 ]]; then
    install -o root -g 3mm -m 0640 "$backup_root/3mm.env" "$environment_file" || return 1
  elif [[ -f $backup_root/environment-was-absent ]]; then
    rm -f -- "$environment_file" || return 1
  fi
  if [[ $agent_environment_backup_created -eq 1 ]]; then
    install -d -o root -g 3mm -m 0750 /etc/3mm-agent || return 1
    install -o root -g 3mm -m 0640 "$backup_root/agent.env" "$agent_environment_file" || return 1
  elif [[ -f $backup_root/agent-environment-was-absent ]]; then
    rm -f -- "$agent_environment_file" || return 1
  fi
}

verify_endpoint() {
  local endpoint=$1
  local ready=0
  local attempt attempts=60
  if [[ $architecture == armv6l && $install_profile == full ]]; then attempts=180; fi
  for attempt in $(seq 1 "$attempts"); do
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
  local source_release=${1:-${release_dir:-}}
  local python_path
  local active_count=0
  local pair service endpoint
  local checks=(
    '3mm-agent.service|http://127.0.0.1:8890/ready'
    '3mm-core.service|http://127.0.0.1:8887/ready'
    '3mm-web.service|http://127.0.0.1:8080/user/login'
    '3mm-web.service|http://127.0.0.1/user/login'
    '3mm-setup.service|http://127.0.0.1:8895/ready'
    '3mm-setup-local.service|http://127.0.0.1:8895/ready'
  )
  if [[ $install_profile == node ]]; then
    checks=(
      '3mm-agent.service|http://127.0.0.1:8890/ready'
      '3mm-setup.service|http://127.0.0.1:8895/ready'
      '3mm-setup-local.service|http://127.0.0.1:8895/ready'
    )
  fi
  for pair in "${checks[@]}"; do
    service=${pair%%|*}
    endpoint=${pair#*|}
    if systemctl is-active --quiet "$service"; then
      active_count=$((active_count + 1))
      verify_endpoint "$endpoint" || return 1
    fi
  done
  if [[ $install_profile == full ]] && systemctl is-active --quiet 3mm-core.service; then
    if ! systemctl is-active --quiet 3mm-platform-runtime.service; then
      fail "Core role has no active independent platform Runtime."
      return 1
    fi
    python_path=$(release_python "$source_release") || return 1
    PYTHONPATH="$source_release" "$python_path" \
      "$source_release/deployment/platform_runtime_component.py" probe || return 1
  fi
  if [[ $active_count -eq 0 ]]; then
    echo "Runtime planner did not activate an application or setup service." >&2
    return 1
  fi
}

verify_frontend_access() {
  local origin status
  for origin in http://localhost http://127.0.0.1; do
    status=$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' \
      -X OPTIONS http://127.0.0.1:8887/ready \
      -H "Origin: $origin" \
      -H 'Access-Control-Request-Method: GET' \
      -H 'Access-Control-Request-Headers: authorization') || return 1
    if [[ $status != 200 ]]; then
      fail "Frontend CORS health check failed for $origin (HTTP $status)."
      return 1
    fi
  done
}

activate_runtime() {
  local source_release=$1
  local python_path activation_path
  python_path=$(release_python "$source_release") || return 1
  # Rollback executes the selected immutable release's own launcher. A previous
  # published release can predate the neutral source layout; never substitute
  # the failed candidate's planner or add import adapters to the running Core.
  if [[ -f $source_release/components/system_runtime/activate.py ]]; then
    activation_path=$source_release/components/system_runtime/activate.py
  elif [[ -f $source_release/three_mm_runtime/activate.py ]]; then
    activation_path=$source_release/three_mm_runtime/activate.py
  else
    fail "Selected release has no supported runtime activation entrypoint."
    return 1
  fi
  AI_SETTINGS_MASTER_KEY="${ai_master_key:-}" PYTHONPATH="$source_release" \
    "$python_path" "$activation_path" || return 1
  # Do not accept a healthy Web/Core while the required Agent is restarting.
  PYTHONPATH="$source_release" "$python_path" "$activation_path" --check-active || return 1
  verify_runtime "$source_release"
}

restore_runtime_units() {
  local unit
  # A rollback release may predate the optional session boundary. Never try to
  # resurrect its socket against an older Core after removing the new units.
  if [[ ! -f /etc/systemd/system/3mm-host-session-worker.socket ]]; then
    local retained_host=()
    for unit in "${previous_enabled_units[@]}"; do
      [[ $unit == 3mm-host-session-worker.socket ]] || retained_host+=("$unit")
    done
    previous_enabled_units=("${retained_host[@]}")
    retained_host=()
    for unit in "${previous_active_units[@]}"; do
      [[ $unit == 3mm-host-session-worker.socket ]] || retained_host+=("$unit")
    done
    previous_active_units=("${retained_host[@]}")
  fi
  if [[ ! -f /etc/systemd/system/3mm-session-worker.socket ]]; then
    local retained=()
    for unit in "${previous_enabled_units[@]}"; do
      [[ $unit == 3mm-session-worker.socket ]] || retained+=("$unit")
    done
    previous_enabled_units=("${retained[@]}")
    retained=()
    for unit in "${previous_active_units[@]}"; do
      [[ $unit == 3mm-session-worker.socket ]] || retained+=("$unit")
    done
    previous_active_units=("${retained[@]}")
  fi
  for unit in "${runtime_services[@]}"; do
    systemctl disable "$unit" >/dev/null 2>&1 || true
  done
  if [[ ${#previous_enabled_units[@]} -gt 0 ]]; then
    systemctl enable "${previous_enabled_units[@]}" || return 1
  fi
  if [[ ${#previous_active_units[@]} -gt 0 ]]; then
    systemctl start "${previous_active_units[@]}" || return 1
    for unit in "${previous_active_units[@]}"; do
      systemctl is-active --quiet "$unit" || return 1
    done
    verify_runtime "$previous_release"
  else
    activate_runtime "$previous_release"
  fi
}

restart_always_on_services() {
  local service
  systemctl enable "${always_on_services[@]}"
  systemctl restart "${always_on_services[@]}"
  for service in "${always_on_services[@]}"; do
    if ! systemctl is-active --quiet "$service"; then
      fail "Required service did not become active: $service"
    fi
  done
}

start_active_application_services() {
  local source_release=$1
  if [[ $install_profile != full || ! -f $database ]]; then
    return 0
  fi
  local python_path
  python_path=$(release_python "$source_release") || return 1
  local application_listing
  if ! application_listing=$(
    "$python_path" - "$database" <<'PY'
import re
import sqlite3
import sys

database = sys.argv[1]
connection = sqlite3.connect(database)
try:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "application_extension_installations" not in tables:
        raise SystemExit(0)
    rows = connection.execute(
        """
        SELECT instance_id
        FROM application_extension_installations
        WHERE enabled = 1 AND status = 'active'
        ORDER BY module_id
        """
    )
    for (instance_id,) in rows:
        if not isinstance(instance_id, str) or re.fullmatch(
            r"[0-9a-f]{24}", instance_id
        ) is None:
            raise SystemExit("Active application instance id is invalid")
        print(f"3mm-application-extension@{instance_id}.service")
finally:
    connection.close()
PY
  ); then
    fail "Could not inspect active applications; application resumption is unconfirmed."
    return 1
  fi
  if [[ -z $application_listing ]]; then
    return 0
  fi
  local application_units=()
  mapfile -t application_units <<< "$application_listing"
  # The administrator-approved release/rollback already starts these exact
  # DB-selected instances. Clear their counters once. The singleton patterns
  # match the exact names but make unloaded instances a no-op for reset-failed.
  local reset_targets=() unit
  for unit in "${application_units[@]}"; do
    reset_targets+=("[3]${unit:1}")
  done
  systemctl reset-failed --all "${reset_targets[@]}" || return 1
  systemctl start "${application_units[@]}" || return 1
  local service
  for service in "${application_units[@]}"; do
    if ! systemctl is-active --quiet "$service"; then
      fail "Active application service did not become active: $service"
      return 1
    fi
  done
  return 0
}

component_transition() {
  local operation=$1
  local arguments=("$operation" --source "$release_dir" --profile "$install_profile")
  if [[ -n $previous_release ]]; then
    arguments+=(--previous-source "$previous_release")
  fi
  if [[ $operation == prepare && ${THREE_MM_RETRY_ROLLED_BACK_TRANSITION:-0} == 1 ]]; then
    arguments+=(--retry-rolled-back)
  fi
  # fd9 is inherited: the helper attests and reuses this same release lock.
  PYTHONPATH="$release_dir" "$release_dir/.venv/bin/python" \
    "$release_dir/deployment/component_transition.py" "${arguments[@]}"
}

rollback() {
  local exit_code=$?
  trap - ERR
  set +e
  echo >&2
  echo "Deployment failed; restoring ${previous_release:-the previous system state}." >&2

  if [[ $mutation_started -eq 1 ]]; then
    if ! stop_runtime_services; then
      echo "Rollback could not stop runtime; state preserved for manual recovery." >&2
      exit "$exit_code"
    fi
    if [[ $install_profile == full ]]; then
      if ! restore_database || ! fence_rollback_authority; then
        echo "Rollback authority fencing failed; services remain stopped and recovery state is preserved." >&2
        exit "$exit_code"
      fi
    else
      systemctl stop "${always_on_services[@]}" >/dev/null 2>&1 || true
    fi
    if ! restore_environment; then
      echo "Rollback environment restore failed; services remain stopped and recovery state is preserved." >&2
      exit "$exit_code"
    fi
    if [[ ${component_transition_prepared:-0} -eq 1 ]]; then
      if ! component_transition restore; then
        echo "Component pointer recovery is unconfirmed; services remain stopped and the transition journal is preserved." >&2
        exit "$exit_code"
      fi
    fi
    if [[ -n $previous_release && -d $previous_release ]]; then
      ln -sfnT "$previous_release" "$current_link"
      if [[ $rollback_link_updated -eq 1 ]]; then
        if [[ $saved_rollback_link -eq 1 ]]; then
          ln -sfnT "$saved_rollback_release" "$previous_link"
        else
          rm -f -- "$previous_link"
        fi
      fi
      install_units "$previous_release" 0 || true
      if [[ $install_profile == node || -f $previous_release/deployment/systemd/3mm-update-helper.service ]]; then
        restart_always_on_services || true
      fi
      restore_runtime_units || {
        systemctl --no-pager --full status "${runtime_services[@]}" >&2 || true
        echo "Rollback completed, but the previous release is not healthy." >&2
      }
      start_active_application_services "$previous_release" || {
        systemctl --no-pager --full status '3mm-application-extension@*.service' >&2 || true
        echo "Rollback restored Core, but active application services are not healthy." >&2
      }
      if [[ ${component_transition_prepared:-0} -eq 1 ]]; then
        component_transition resume || {
          echo "Previous component readiness is unconfirmed; the transition journal is preserved." >&2
          exit "$exit_code"
        }
      fi
    elif [[ $install_profile == node ]]; then
      # Failed first install: do not leave enabled units or a dangling current link.
      systemctl disable --now "${installed_units[@]}" >/dev/null 2>&1 || true
      local unit
      for unit in "${installed_units[@]}"; do
        rm -f -- "/etc/systemd/system/$unit"
      done
      if [[ -L $current_link && $(readlink -f "$current_link") == "$release_dir" ]]; then
        rm -f -- "$current_link"
      fi
      systemctl daemon-reload
    fi
    if [[ -z $previous_release && ${component_transition_prepared:-0} -eq 1 ]]; then
      # A failed first install has no previous Core to resume. The helper proves
      # the original pairs and absence of originally active components before
      # marking this completed rollback eligible for an explicit later retry.
      component_transition resume || {
        echo "First-install component recovery is unconfirmed; its transition journal is preserved." >&2
        exit "$exit_code"
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
if [[ -n $previous_release ]]; then
  assert_release_path "$previous_release"
  previous_profile=full
  if [[ -f $previous_release/.3mm-install-profile ]]; then
    previous_profile=$(<"$previous_release/.3mm-install-profile")
  fi
  if [[ $previous_profile != "$install_profile" ]]; then
    echo "In-place installation profile changes are not supported." >&2
    exit 1
  fi
fi
if [[ -L $previous_link ]]; then
  saved_rollback_release=$(readlink -f "$previous_link")
  if [[ ! -d $saved_rollback_release ]]; then
    echo "Rollback release link does not resolve to a directory." >&2
    exit 1
  fi
  assert_release_path "$saved_rollback_release"
  saved_rollback_link=1
elif [[ -e $previous_link ]]; then
  echo "Rollback release path exists but is not a symbolic link." >&2
  exit 1
fi
if [[ -e $release_dir ]]; then
  echo "Release already exists: $release_dir" >&2
  exit 1
fi
assert_release_path "$release_dir"

if [[ $install_profile == node && -z $previous_release ]]; then
  # Never take ownership of units/state from an unrecognized installation.
  for unit in "${installed_units[@]}" 3mm-core.service 3mm-web.service 3mm-public-web.socket 3mm-public-web.service 3mm-update-helper.service; do
    if systemctl cat "$unit" >/dev/null 2>&1; then
      fail "Existing 3mm unit without a managed Node release: $unit"
    fi
  done
  if [[ -e $current_link || -e $environment_file || -d $core_state ]]; then
    fail "Existing 3mm state requires a managed migration, not a fresh Node install."
  fi
fi

if ! id -u 3mm >/dev/null 2>&1; then
  useradd --system --home-dir "$state_root" --shell /usr/sbin/nologin 3mm
fi
# Required even on generic Linux/VM hosts with no physical GPIO device.
if ! getent group gpio >/dev/null 2>&1; then
  groupadd --system gpio
fi
if [[ $install_profile == full ]]; then
if ! getent group 3mm-app >/dev/null 2>&1; then
  groupadd --system 3mm-app
fi
if ! id -u 3mm-app >/dev/null 2>&1; then
  useradd --system --gid 3mm-app --home-dir "$state_root/application-extensions" \
    --shell /usr/sbin/nologin 3mm-app
fi
if ! getent group 3mm-public >/dev/null 2>&1; then
  groupadd --system 3mm-public
fi
if ! id -u 3mm-public >/dev/null 2>&1; then
  useradd --system --gid 3mm-public --home-dir /nonexistent \
    --shell /usr/sbin/nologin 3mm-public
fi
if ! getent group 3mm-platform >/dev/null 2>&1; then
  groupadd --system 3mm-platform
fi
if ! id -u 3mm-platform >/dev/null 2>&1; then
  useradd --system --gid 3mm-platform --home-dir /nonexistent --shell /usr/sbin/nologin 3mm-platform
fi
if ! getent group 3mm-connectors >/dev/null 2>&1; then
  groupadd --system 3mm-connectors
fi
if ! id -u 3mm-connectors >/dev/null 2>&1; then
  useradd --system --gid 3mm-connectors --home-dir /nonexistent --shell /usr/sbin/nologin 3mm-connectors
fi
usermod -a -G 3mm-app,3mm-public,3mm-platform 3mm
fi

install -d -o root -g root -m 0755 "$install_root" "$releases_root" /etc/3mm
if [[ $install_profile == full ]]; then
install -d -o root -g root -m 0700 \
  "$deploy_cache_root" "$deploy_home" "$npm_cache"
# The main service user owns the shared state root. The dedicated application
# group receives traverse-only access so it can reach its isolated subtree
# without listing or entering Core, Agent, backup or provisioning state.
install -d -o 3mm -g 3mm-app -m 0710 "$state_root"
else
  install -d -o 3mm -g 3mm -m 0700 "$state_root"
fi
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
  backend/applications/commands/__init__.py
  backend/applications/commands/broker.py
  backend/applications/commands/discovery.py
  backend/applications/commands/passage.py
  backend/applications/commands/rebinding.py
  backend/applications/connectors/__init__.py
  backend/applications/connectors/broker.py
  backend/applications/connectors/secrets.py
  backend/applications/connectors/transport.py
  backend/applications/events/__init__.py
  backend/applications/events/api.py
  backend/applications/events/broker.py
  backend/applications/events/publication.py
  backend/applications/operations_api.py
  backend/applications/resources/__init__.py
  backend/applications/resources/discovery.py
  backend/applications/resources/providers.py
  backend/applications/runtime/__init__.py
  backend/applications/runtime/gateway.py
  backend/applications/runtime/health.py
  backend/applications/runtime/identity.py
  backend/applications/runtime/invocations.py
  backend/applications/runtime/peers.py
  backend/applications/runtime/platform.py
  backend/applications/runtime/responses.py
  backend/applications/runtime/status.py
  backend/applications/runtime/status_probe.py
  backend/applications/sessions/__init__.py
  backend/applications/sessions/api.py
  backend/applications/sessions/authority.py
  backend/applications/sessions/browser.py
  backend/applications/sessions/local.py
  backend/applications/sessions/remote.py
  backend/applications/sessions/runtimes.py
  backend/applications/tasks/__init__.py
  backend/applications/tasks/api.py
  backend/applications/tasks/broker.py
  backend/applications/tasks/schedules.py
  backend/sessions/__init__.py
  backend/sessions/acceptance.py
  backend/sessions/agent.py
  backend/sessions/api.py
  backend/sessions/broker.py
  backend/sessions/discovery.py
  backend/sessions/gateway.py
  backend/sessions/transport.py
  backend/applications/relational/__init__.py
  backend/applications/relational/activation.py
  backend/applications/relational/activation_recovery.py
  backend/applications/relational/admin_worker.py
  backend/applications/relational/authority.py
  backend/applications/relational/boot.py
  backend/applications/relational/candidate.py
  backend/applications/relational/lifecycle.py
  backend/applications/relational/namespace_recovery.py
  backend/applications/relational/preparation_recovery.py
  backend/applications/relational/reactivation.py
  backend/applications/relational/recovery.py
  backend/applications/relational/recovery_confirmation.py
  backend/applications/relational/registration.py
  backend/applications/relational/startup.py
  backend/applications/relational/upgrade.py
  backend/applications/relational/upgrade_admin.py
  backend/applications/relational/upgrade_cli.py
  backend/applications/relational/upgrade_confirmation.py
  backend/applications/relational/upgrade_rollback.py
  backend/devices/pairing/__init__.py
  backend/devices/pairing/api.py
  backend/devices/pairing/enrollment.py
  backend/devices/pairing/service.py
  backend/devices/platform/__init__.py
  backend/devices/platform/api.py
  backend/devices/platform/service.py
  backend/devices/updates/__init__.py
  backend/devices/updates/api.py
  backend/devices/updates/approval.py
  backend/devices/updates/catalog.py
  backend/devices/updates/delivery.py
  backend/devices/updates/delivery_api.py
  backend/devices/updates/execution.py
  backend/settings/__init__.py
  backend/settings/api.py
  backend/settings/crud.py
  backend/system/audit/__init__.py
  backend/system/audit/api.py
  backend/system/audit/retention.py
  backend/accounts/bootstrap.py
  backend/applications/authority/__init__.py
  backend/applications/authority/access.py
  backend/applications/authority/admin.py
  backend/applications/authority/composition.py
  backend/applications/authority/context.py
  backend/applications/authority/inspection.py
  backend/applications/authority/keys.py
  backend/applications/authority/management.py
  backend/applications/authority/metadata.py
  backend/applications/authority/policy.py
  backend/applications/authority/policy_reviews.py
  backend/applications/authority/review.py
  backend/applications/authority/sources.py
  backend/applications/authority/subjects.py
  backend/applications/authority/tasks.py
  backend/devices/modules/template_data/character-display.mock.json
  backend/devices/modules/template_data/character-display.pcf8574-2row.json
  backend/devices/modules/template_data/character-display.pcf8574-4row.json
  backend/devices/modules/template_data/gpio-input.gpiod.json
  backend/devices/modules/template_data/gpio-input.mock.json
  backend/devices/modules/templates.py
  backend/devices/telemetry/__init__.py
  backend/devices/telemetry/events_api.py
  backend/devices/telemetry/ingest_api.py
  backend/devices/telemetry/state_api.py
  backend/installation/__init__.py
  backend/installation/api.py
  backend/installation/identity.py
  backend/installation/peer_listing.py
  backend/installation/peer_read_sources.py
  backend/installation/peers.py
  backend/installation/projection.py
  backend/installation/session_tls.py
  backend/installation/status_binding.py
  backend/localization/service.py
  backend/storage/__init__.py
  backend/storage/engine.py
  backend/storage/public_assets.py
  backend/storage/sessions.py
  backend/system/components.py
  backend/artifacts/__init__.py
  backend/artifacts/api.py
  backend/artifacts/packages.py
  backend/artifacts/inspection.py
  backend/artifacts/code_scope.py
  backend/artifacts/compiled_ui.py
  backend/artifacts/provenance.py
  backend/appearance/__init__.py
  backend/appearance/api.py
  backend/appearance/packages.py
  backend/appearance/customization.py
  backend/appearance/assets.py
  backend/accounts/__init__.py
  backend/accounts/passwords.py
  backend/accounts/tokens.py
  backend/accounts/dependencies.py
  backend/accounts/users_api.py
  backend/accounts/access/__init__.py
  backend/accounts/access/api.py
  backend/accounts/access/sources.py
  backend/accounts/access/groups_api.py
  backend/accounts/access/roles_api.py
  backend/accounts/access/permissions_api.py
  backend/accounts/sessions/__init__.py
  backend/accounts/sessions/api.py
  backend/accounts/sessions/refresh.py
  backend/accounts/sessions/policy.py
  backend/system/updates/__init__.py
  backend/system/updates/api.py
  backend/system/updates/releases.py
  backend/system/updates/policy.py
  backend/system/updates/staging.py
  backend/system/updates/platform_runtime.py
  backend/system/updates/components_api.py
  backend/system/updates/components.py
  backend/applications/checkpoints.py
  backend/applications/delegations/__init__.py
  backend/applications/delegations/api.py
  backend/applications/delegations/service.py
  backend/applications/files/__init__.py
  backend/applications/files/api.py
  backend/applications/files/authority.py
  backend/applications/files/transfers.py
  backend/applications/kiosks/__init__.py
  backend/applications/kiosks/api.py
  backend/applications/kiosks/service.py
  backend/applications/public_web/__init__.py
  backend/applications/public_web/guests.py
  backend/applications/public_web/webhook_admission.py
  backend/applications/queries/__init__.py
  backend/applications/queries/configuration.py
  backend/applications/queries/transport.py
  backend/applications/public_web/routes.py
  backend/applications/public_web/transport.py
  packages/__init__.py
  packages/platform_wire/__init__.py
  packages/platform_wire/event_delivery.py
  packages/platform_wire/task_time.py
  packages/protocol/__init__.py
  packages/protocol/theme_design_defaults.json
  backend/devices/__init__.py
  backend/devices/operations.py
  backend/devices/authority.py
  backend/devices/auth.py
  backend/devices/http.py
  backend/devices/body_limit.py
  backend/devices/commands/__init__.py
  backend/devices/commands/api.py
  backend/devices/commands/queue.py
  backend/devices/commands/notifier.py
  backend/devices/capabilities/__init__.py
  backend/devices/capabilities/api.py
  backend/devices/capabilities/state_api.py
  backend/devices/capabilities/registry.py
  backend/devices/hardware_interfaces.py
  backend/devices/features/__init__.py
  backend/devices/features/api.py
  backend/devices/features/service.py
  backend/devices/modules/__init__.py
  backend/devices/modules/lifecycle.py
  backend/devices/modules/authority.py
  backend/devices/registry/__init__.py
  backend/devices/registry/api.py
  backend/devices/registry/read.py
  backend/devices/registry/online.py
  backend/localization/__init__.py
  backend/localization/api.py
  backend/localization/packages.py
  backend/applications/__init__.py
  backend/applications/management/__init__.py
  backend/applications/management/configuration.py
  backend/applications/management/requirements.py
  backend/applications/management/staging.py
  backend/applications/management/provenance.py
  backend/applications/management/api.py
  backend/applications/management/access_api.py
  backend/applications/management/connector_api.py
  backend/applications/management/ui_admin_api.py
  backend/applications/management/lifecycle.py
  backend/applications/management/consent.py
  backend/applications/management/lifecycle_consent.py
  backend/applications/management/connector_settings.py
  backend/system/__init__.py
  backend/system/backups/__init__.py
  backend/system/backups/api.py
  backend/system/backups/service.py
  backend/system/control.py
  backend/system/diagnostics/__init__.py
  backend/system/diagnostics/api.py
  backend/system/diagnostics/failures.py
  backend/system/diagnostics/operations.py
  backend/system/diagnostics/workspace.py
  backend/system/diagnostics/bundle.py
  backend/system/diagnostics/alerts.py
  backend/system/network_recovery/__init__.py
  backend/system/network_recovery/api.py
  backend/system/network_recovery/service.py
  components/__init__.py
  components/admin_web/__init__.py
  components/admin_web/__main__.py
  components/admin_web/server.py
  components/system_runtime/__init__.py
  components/system_runtime/activate.py
  components/system_runtime/services.py
  components/system_runtime/install_profile.py
  config_templates/product.json
  components/setup/__init__.py
  components/setup/__main__.py
  components/setup/captive_portal.py
  components/setup/cli.py
  components/setup/config.py
  components/setup/main.py
  components/setup/product.py
  components/setup/provision.py
  components/setup/schemas.py
  components/setup/requirements.txt
  components/setup/static/setup.html
  deployment/apply_staged_update.py
  deployment/component_transition.py
  deployment/bootstrap-local-agent.py
  deployment/create_backup.py
  deployment/local_agent_pairing.py
  deployment/portable_backup.py
  deployment/prepare_backup_storage.py
  deployment/prepare_host_sessions.py
  deployment/backup_compatibility.py
  deployment/restore_backup.py
  deployment/restore_application_extensions.py
  deployment/authority_recovery.py
  deployment/factory_reset.py
  deployment/frontend_access.py
  deployment/migrate_database.py
  deployment/update-dependency-allowlist.json
  deployment/systemd/3mm-core.service
  deployment/systemd/3mm-web.service
  deployment/systemd/3mm-public-web.socket
  deployment/systemd/3mm-public-web.service
  deployment/systemd/3mm-agent.service
  deployment/systemd/3mm-setup-local.service
  deployment/systemd/3mm-captive-portal-dnsmasq.conf
  deployment/systemd/3mm-update-helper.service
  deployment/systemd/3mm-application-extension@.service
  deployment/systemd/3mm-session-worker.socket
  deployment/systemd/3mm-session-worker@.service
  deployment/systemd/3mm-host-session-worker.socket
  deployment/systemd/3mm-host-session-worker@.service
  components/system_runtime/session_worker.py
  components/system_runtime/session_worker_client.py
  components/system_runtime/host_session_worker.py
  components/system_runtime/host_session_policy.py
  components/system_runtime/update_helper.py
  components/system_runtime/platform_runtime_updates.py
  components/platform_runtime/__init__.py
  components/platform_runtime/__main__.py
  components/platform_runtime/server.py
  components/platform_runtime/public_web.py
  components/platform_runtime/events.py
  components/platform_runtime/responses.py
  components/platform_runtime/connector_worker.py
  components/platform_runtime/connector_execute.py
  components/platform_runtime/tasks.py
  components/system_runtime/application_activation.py
  components/system_runtime/application_host.py
  components/system_runtime/application_transport.py
  components/public_web/__init__.py
  components/public_web/__main__.py
  components/public_web/server.py
  components/public_web/webhook_pilot.py
  packages/application_sdk/__init__.py
  components/system_runtime/network_recovery.py
  packages/provisioning/__init__.py
  packages/provisioning/network_recovery.py
  packages/provisioning/network_helper.py
  packages/provisioning/setup_access_point.py
  components/system_runtime/install_bootstrap.py
)
if [[ $install_profile == node ]]; then
  required_files=(
    agent/requirements.txt components/__init__.py
    components/system_runtime/__init__.py
    components/setup/__init__.py components/setup/__main__.py
    components/setup/captive_portal.py components/setup/cli.py components/setup/config.py
    components/setup/main.py components/setup/product.py components/setup/provision.py
    components/setup/schemas.py components/setup/requirements.txt
    config_templates/product.json
    packages/__init__.py packages/platform_wire/__init__.py
    packages/platform_wire/event_delivery.py packages/platform_wire/task_time.py
    packages/protocol/__init__.py packages/protocol/theme_design_defaults.json
    packages/provisioning/__init__.py packages/provisioning/network_recovery.py
    .3mm-install-profile .3mm-release.json deployment/node-wheels/provenance.json
    deployment/node-requirements.txt deployment/node_preflight.py
    deployment/component_transition.py
    components/system_runtime/install_profile.py components/system_runtime/activate.py
    components/system_runtime/services.py
    components/system_runtime/install_bootstrap.py
    components/system_runtime/node_recovery.py components/system_runtime/network_recovery.py
    components/system_runtime/node_update_helper.py deployment/apply_node_update.py
    components/system_runtime/node_update_trust.py deployment/trust_node_update_hub.py
    packages/protocol/node_updates.py agent/node_update_client.py
    agent/node_update_execution.py
    packages/provisioning/network_helper.py packages/provisioning/setup_access_point.py
    components/setup/static/setup.html deployment/systemd/3mm-captive-portal-dnsmasq.conf
  )
  for unit in "${installed_units[@]}"; do
    required_files+=("deployment/systemd/$unit")
  done
fi
for required_file in "${required_files[@]}"; do
  if [[ ! -f $release_dir/$required_file ]]; then
    fail "Release artifact is incomplete: $required_file is required."
  fi
done
if [[ $install_profile == full ]]; then
if [[ ! -d $release_dir/frontend/dist/assets ]] || \
   ! find "$release_dir/frontend/dist/assets" -maxdepth 1 -type f -name '*.js' -print -quit | grep -q .; then
  fail "Frontend artifact is incomplete: dist/assets/*.js is required."
fi
if [[ $architecture == armv6l ]]; then
  python3 - "$release_dir/.3mm-release.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as source:
    metadata = json.load(source)
if metadata.get("architecture") != "armv6l" or metadata.get("profile", "full") != "full":
    raise SystemExit("ARMv6 Hub requires its exact full-profile release artifact")
PY
  for tool in esbuild rollup.tgz; do
    [[ -f $release_dir/deployment/armv6-ui/$tool ]] || fail "ARMv6 compiler artifact is missing: $tool"
  done
fi
fi
# Profile selection belongs to this immutable release, never to mutable env state.
if [[ $install_profile == node ]]; then
  [[ $(<"$release_dir/.3mm-install-profile") == node ]] || fail "Not a Node artifact."
  python3 - "$release_dir/.3mm-release.json" <<'PY'
import json, platform, sys
with open(sys.argv[1]) as source:
    metadata = json.load(source)
if (metadata.get('profile') != 'node' or metadata.get('architecture') != platform.machine()
        or metadata.get('python') != f'{sys.version_info.major}.{sys.version_info.minor}'):
    raise SystemExit('Node artifact architecture or Python version does not match this host')
PY
fi
printf '%s\n' "$install_profile" > "$release_dir/.3mm-install-profile"

log "Creating the release-specific Python environment"
python3 -m venv "$release_dir/.venv"
if [[ $install_profile == node ]]; then
  "$release_dir/.venv/bin/python" -m pip install --disable-pip-version-check \
    --no-index --find-links "$release_dir/deployment/node-wheels" \
    --only-binary=:all: --requirement "$release_dir/deployment/node-requirements.txt"
  # Fail before stopping services; imports alone cannot validate package metadata.
  "$release_dir/.venv/bin/python" -m pip check
  "$release_dir/.venv/bin/python" "$release_dir/deployment/node_preflight.py"
  PYTHONPATH="$release_dir" "$release_dir/.venv/bin/python" -c \
    'from pathlib import Path; from packages.provisioning import FileProvisioningStore; from components.system_runtime.install_profile import InstallProfile, validate_profile_role; s = FileProvisioningStore(Path("/var/lib/3mm/provisioning")).load(); validate_profile_role(InstallProfile.NODE, s.role if s else None)'
else
"$release_dir/.venv/bin/python" -m pip install \
  --disable-pip-version-check \
  --requirement "$release_dir/backend/requirements.txt"

if ! command -v npm >/dev/null 2>&1; then
  fail "Node.js/npm is required for the compiled UI extension toolchain."
fi
if [[ $architecture == armv6l ]]; then
  HOME="$deploy_home" npm_config_cache="$npm_cache" \
    npm ci --prefix "$release_dir/frontend/compiler" --ignore-scripts --no-audit --no-fund
  python3 "$release_dir/deployment/armv6_ui_tools.py" install "$release_dir"
else
  HOME="$deploy_home" npm_config_cache="$npm_cache" \
    npm install --prefix "$release_dir/frontend/compiler" --ignore-scripts --no-audit --no-fund
fi
fi

log "Checking the runtime plan before stopping existing services"
if [[ $install_profile == full ]]; then
  # The same target-owned policy runs for console and approved UI updates.
  # Validate/merge before stopping services; never replace custom allowed origins.
  frontend_cors_origins=$("$release_dir/.venv/bin/python" \
    "$release_dir/deployment/frontend_access.py" \
    --environment "$environment_file" --frontend-origin "$frontend_origin" \
    --hostname "$device_hostname")
  # A restore replaces Core's environment and database together. The legacy
  # sidecar may still hold a different key from before that restore.
  ai_master_key=$(PYTHONPATH="$release_dir" "$release_dir/.venv/bin/python" - \
    "$database" "$environment_file" "$ai_master_key_file" <<'PY'
import sys
from pathlib import Path
from backend.installation.identity import InstallationIdentityError, select_installer_master_key

try:
    key = select_installer_master_key(*map(Path, sys.argv[1:]))
except InstallationIdentityError as error:
    raise SystemExit(str(error)) from None
print(key)
PY
  )
fi
PYTHONPATH="$release_dir" "$release_dir/.venv/bin/python" -m components.system_runtime.install_bootstrap \
  --profile "$install_profile" --check-only
log "Preparing the coordinated immutable component transition"
component_transition prepare
component_transition_prepared=1
log "Stopping services and backing up persistent state"
for unit in "${runtime_services[@]}"; do
  if systemctl is-active --quiet "$unit"; then previous_active_units+=("$unit"); fi
  if systemctl is-enabled --quiet "$unit"; then previous_enabled_units+=("$unit"); fi
done
mutation_started=1
# Application helpers share our release lock. Missing first-install units are
# harmless, but an existing runtime must stop before state is copied or changed.
stop_runtime_services
if [[ $install_profile == node ]]; then
  systemctl stop "${always_on_services[@]}" >/dev/null 2>&1 || true
fi
install -d -o root -g root -m 0700 "$backup_root"
if [[ $install_profile == full && -f $database ]]; then
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
if [[ -f $agent_environment_file ]]; then
  install -o root -g root -m 0600 "$agent_environment_file" "$backup_root/agent.env"
  agent_environment_backup_created=1
else
  : > "$backup_root/agent-environment-was-absent"
  chmod 0600 "$backup_root/agent-environment-was-absent"
fi
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
upsert_environment THREE_MM_NETWORK_BACKEND "$network_backend"
if [[ $install_profile == full ]]; then
upsert_environment DATABASE_URL sqlite:////var/lib/3mm/core/3mm.db
  # Preserve the selected native/mock GPIO driver on upgrades; wired-only
  # first installs must not implicitly enable a hardware implementation.
  if [[ $environment_backup_created -eq 0 ]]; then
    upsert_environment THREE_MM_GPIO_DRIVER mock
  fi
upsert_environment UPLOADS_DIR /var/lib/3mm/core/uploads
upsert_environment BACKEND_EXTENSIONS_DIR /var/lib/3mm/core/extensions/backend
upsert_environment FRONTEND_EXTENSIONS_DIR /var/lib/3mm/core/extensions/frontend
upsert_environment COMPILED_UI_ARTIFACTS_DIR /var/lib/3mm/core/extensions/compiled
upsert_environment BACKEND_HOST 0.0.0.0
upsert_environment BACKEND_PORT 8887
upsert_environment CORS_ORIGINS "$frontend_cors_origins"
upsert_environment DEVICE_OFFLINE_AFTER_SECONDS 90
upsert_environment THREE_MM_AGENT_HOST 127.0.0.1
upsert_environment THREE_MM_AGENT_PORT 8890
upsert_environment THREE_MM_AGENT_DATA_DIR /var/lib/3mm/agent
upsert_environment THREE_MM_AGENT_ROLE standalone
upsert_environment THREE_MM_AGENT_HARDWARE_PROFILE native
upsert_environment THREE_MM_IDENTIFIER_DRIVER mock
upsert_environment THREE_MM_IDENTIFIER_READER_ID reader.mock.1
upsert_environment THREE_MM_CORE_URL http://127.0.0.1:8887
upsert_environment THREE_MM_HEARTBEAT_INTERVAL_SECONDS 30
upsert_environment THREE_MM_PROVISIONING_DATA_DIR /var/lib/3mm/provisioning
upsert_environment THREE_MM_SETUP_HOST 0.0.0.0
upsert_environment THREE_MM_SETUP_PORT 8895
upsert_environment FRONTEND_URL "$frontend_origin"
upsert_environment THREE_MM_UPDATE_STAGING_DIR /var/lib/3mm/core/update-staging
upsert_environment THREE_MM_UPDATE_DEPENDENCY_ALLOWLIST /opt/3mm/current/deployment/update-dependency-allowlist.json
upsert_environment THREE_MM_UPDATE_HELPER_SOCKET /run/3mm/update-helper.sock
upsert_environment THREE_MM_UPDATE_HELPER_STATUS_FILE /var/lib/3mm/update-helper/status.json
upsert_environment THREE_MM_UPDATE_POLICY_FILE /var/lib/3mm/core/update-policy.json
upsert_environment THREE_MM_UPDATE_CHECK_CACHE_FILE /var/lib/3mm/core/update-check-cache.json
upsert_environment THREE_MM_NETWORK_RECOVERY_POLICY_FILE /var/lib/3mm/core/network-recovery-policy.json
upsert_environment THREE_MM_NETWORK_RECOVERY_MARKER_FILE /var/lib/3mm/provisioning/network-recovery.json
upsert_environment THREE_MM_NETWORK_RECOVERY_HELPER_SOCKET /run/3mm/update-helper.sock
upsert_environment THREE_MM_NETWORK_RECOVERY_OFFLINE_SECONDS 300
upsert_environment THREE_MM_BACKUP_HOST_CONFIG_FILE /etc/3mm/3mm.env
upsert_environment THREE_MM_BACKUP_STORAGE_DIR /var/lib/3mm/backups
upsert_environment THREE_MM_BACKUP_IMPORT_DIR /var/lib/3mm/core/backup-imports
upsert_environment THREE_MM_BACKUP_MINIMUM_FREE_BYTES 67108864
upsert_environment THREE_MM_BACKUP_MAX_IMPORT_BYTES 537919488
upsert_environment THREE_MM_APPLICATION_ROOT /var/lib/3mm/application-extensions
upsert_environment THREE_MM_APPLICATION_KEY_ROOT /etc/3mm/application-extensions
upsert_environment THREE_MM_APPLICATION_HELPER_SOCKET /run/3mm/update-helper.sock
upsert_environment THREE_MM_APPLICATION_RESPONSE_SOCKET /run/3mm-application-responses/runtime.sock
upsert_environment THREE_MM_CORE_AUTHORITY_SOCKET /run/3mm-core-authority/authority.sock
upsert_environment THREE_MM_CONNECTOR_WORKER_USER 3mm-connectors
upsert_environment THREE_MM_CONNECTOR_WORKER_SOCKET /run/3mm-connectors/worker.sock
upsert_environment THREE_MM_PLATFORM_RUNTIME_USER 3mm-platform
upsert_environment THREE_MM_PLATFORM_RUNTIME_SOCKET /run/3mm-platform/runtime.sock

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
install -d -o 3mm -g 3mm -m 0700 "$core_state/update-staging"
install -d -o 3mm -g 3mm -m 0700 "$core_state/backup-imports"
install -d -o root -g 3mm -m 0750 "$state_root/update-helper"
install -d -o root -g 3mm -m 0750 "$state_root/backups"
install -d -o root -g 3mm-app -m 0750 \
  "$state_root/application-extensions" \
  /etc/3mm/application-extensions
install -d -o 3mm -g 3mm-app -m 0750 \
  "$state_root/application-extensions/platform"
else
  upsert_environment THREE_MM_AGENT_HOST 127.0.0.1
  upsert_environment THREE_MM_AGENT_PORT 8890
  upsert_environment THREE_MM_AGENT_ROLE node
  upsert_environment THREE_MM_AGENT_DATA_DIR /var/lib/3mm/agent
  upsert_environment THREE_MM_AGENT_HARDWARE_PROFILE native
  upsert_environment THREE_MM_PROVISIONING_DATA_DIR /var/lib/3mm/provisioning
  upsert_environment THREE_MM_SETUP_HOST 0.0.0.0
  upsert_environment THREE_MM_SETUP_PORT 8895
  # Keep a configured Hub URL/driver on upgrades; never invent a mock reader.
  if [[ $environment_backup_created -eq 0 ]]; then
    upsert_environment THREE_MM_IDENTIFIER_DRIVER disabled
    upsert_environment THREE_MM_GPIO_DRIVER mock
  fi
  install -o root -g 3mm -m 0640 "$environment_tmp" "$environment_file"
  rm -f -- "$environment_tmp"
  install -d -o 3mm -g 3mm -m 0750 "$state_root/provisioning"
fi
install -d -o root -g root -m 0755 /etc/NetworkManager/dnsmasq-shared.d

log "Switching the reviewed component pointer set while services are stopped"
component_transition switch

log "Preparing the independent Agent environment"
# Only Agent configuration enters its own environment; never Core DB/signing keys.
install -d -o root -g 3mm -m 0750 /etc/3mm-agent
agent_environment_tmp=$(mktemp "${agent_environment_file}.XXXXXX")
awk -F= '$1 ~ /^THREE_MM_(AGENT_|GPIO_|IDENTIFIER_)/ || $1 ~ /^THREE_MM_(CORE_URL|HEARTBEAT_INTERVAL_SECONDS|PROVISIONING_DATA_DIR|INVENTORY_SCHEMA_VERSION)$/ {print}' "$environment_file" > "$agent_environment_tmp"
install -o root -g 3mm -m 0640 "$agent_environment_tmp" "$agent_environment_file"
rm -f -- "$agent_environment_tmp"
PYTHONPATH="$release_dir" "$release_dir/.venv/bin/python" \
  -m deployment.service_component agent bootstrap --source "$release_dir"

log "Installing service definitions"
if [[ $install_profile == full ]]; then
PYTHONPATH="$release_dir" \
  "$release_dir/.venv/bin/python" -m deployment.prepare_backup_storage
# Bootstrap only if absent. Compatible independent Runtime artifacts are retained.
PYTHONPATH="$release_dir" "$release_dir/.venv/bin/python" \
  -m deployment.platform_runtime_component bootstrap --source "$release_dir"
PYTHONPATH="$release_dir" "$release_dir/.venv/bin/python" \
  -m deployment.platform_runtime_component --component connector-worker bootstrap --source "$release_dir"
# Native worker bundle: separate code/dependencies, with per-instance pinned hosts.
PYTHONPATH="$release_dir" "$release_dir/.venv/bin/python" \
  -m deployment.application_host_component bootstrap --source "$release_dir"
PYTHONPATH="$release_dir" "$release_dir/.venv/bin/python" \
  -m deployment.service_component public-web bootstrap --source "$release_dir"
PYTHONPATH="$release_dir" "$release_dir/.venv/bin/python" \
  -m deployment.service_component session-worker bootstrap --source "$release_dir"
# Fixed-account host sessions remain explicitly disabled by their root policy.
# This only provisions the independent artifact, never application rights or a
# listening socket; existing explicit policy is validated and preserved.
PYTHONPATH="$release_dir" "$release_dir/.venv/bin/python" \
  -m deployment.prepare_host_sessions
PYTHONPATH="$release_dir" "$release_dir/.venv/bin/python" \
  -m deployment.service_component host-session-worker bootstrap --source "$release_dir"
fi
install_units "$release_dir"
if [[ $install_profile == full ]]; then
runuser -u 3mm -- env \
  DATABASE_URL=sqlite:////var/lib/3mm/core/3mm.db \
  UPLOADS_DIR=/var/lib/3mm/core/uploads \
  BACKEND_EXTENSIONS_DIR=/var/lib/3mm/core/extensions/backend \
  FRONTEND_EXTENSIONS_DIR=/var/lib/3mm/core/extensions/frontend \
  COMPILED_UI_ARTIFACTS_DIR=/var/lib/3mm/core/extensions/compiled \
  PYTHONPATH="$release_dir" \
  "$release_dir/.venv/bin/python" "$release_dir/deployment/migrate_database.py"
# The protected setup portal creates or proves the first administrator.

fi

log "Preparing the persistent runtime journal"
runuser -u 3mm -- env PYTHONPATH="$release_dir" \
  "$release_dir/.venv/bin/python" -m components.system_runtime.install_bootstrap --profile "$install_profile"

log "Activating release atomically"
ln -sfnT "$release_dir" "$current_link"

if [[ $install_profile == node ]]; then
  # The Node update helper must be available before the new Agent starts.
  # Agent startup immediately reconciles any durable OTA operation.
  restart_always_on_services
  activate_runtime "$release_dir"
else
  activate_runtime "$release_dir"
  # Setup-only first boot has no Core listener. Check browser access only when
  # Core is selected; do not impose the new policy on an older rollback release.
  if systemctl is-active --quiet 3mm-core.service; then
    verify_frontend_access
  fi
  restart_always_on_services
  start_active_application_services "$release_dir"
fi
log "Verifying the transitioned active components"
component_transition verify
if [[ $test_fail_after_health == 1 ]]; then
  fail "Injected post-health deployment failure for rollback acceptance."
fi
if [[ -n $previous_release && $previous_release != "$release_dir" ]]; then
  ln -sfnT "$previous_release" "$previous_link"
  rollback_link_updated=1
fi

rm -f -- "$release_archive"
component_transition commit
trap - ERR
log "Deployment succeeded"
systemctl --no-pager --full status "${runtime_services[@]}" "${always_on_services[@]}" 2>/dev/null || true
