"""Run bounded installer shell sections with command doubles, never real services.

These are profile regression tests, not Linux clean-install/rollback acceptance.
"""
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest


SCRIPT = (Path(__file__).parents[1] / 'install-systemd.sh').read_text(encoding='utf-8')
BASH = (
    'C:/Program Files/Git/bin/bash.exe'
    if Path('C:/Program Files/Git/bin/bash.exe').is_file() else None
) or shutil.which('bash')
pytestmark = pytest.mark.skipif(BASH is None, reason='Bash is required')


def run(source):
    # Bytes prevent Windows subprocess from translating shell stdin to CRLF.
    result = subprocess.run([BASH, '--noprofile', '--norc'],
                            input=('set -Eeuo pipefail\n' + source).encode(),
                            capture_output=True, timeout=10)
    return subprocess.CompletedProcess(result.args, result.returncode,
                                       result.stdout.decode(), result.stderr.decode())


def section(start, end):
    return SCRIPT[SCRIPT.index(start):SCRIPT.index(end)]


def quiescence_function():
    return section('stop_runtime_services() {', 'install_units() {')


@pytest.mark.parametrize('profile,listing', [
    ('full', ''),
    ('node', ''),
    ('full', '3mm-core.service not-found inactive dead missing'),
    ('full', '3mm-core.service loaded active running Core\n'
             '3mm-application-extension@0123456789abcdef01234567.service loaded active running App'),
    ('node', '3mm-agent.service loaded active running Agent'),
    # A removed unit definition does not prove its existing process is stopped.
    ('full', '3mm-core.service not-found active running Core'),
])
def test_installer_stops_only_existing_runtime_without_rejecting_clean_install(profile, listing):
    expected = [line.split()[0] for line in listing.splitlines()
                if line.split()[1:4] != ['not-found', 'inactive', 'dead']]
    result = run(
        f'install_profile={profile}\ntest_listing={shlex.quote(listing)}\n'
        f'test_existing={shlex.quote(" " + " ".join(expected) + " ")}\n'
        + section('runtime_services=(', 'previous_release=""') + '''
log() { :; }
fail() { echo "$*" >&2; return 1; }
systemctl() {
  case "$1" in
    is-active|is-enabled) return 3 ;;
    list-units) printf '%s\\n' "$test_listing" ;;
    stop)
      shift
      for unit in "$@"; do
        [[ $test_existing == *" $unit "* ]] || return 5
        printf 'stopped %s\\n' "$unit"
      done
      ;;
    *) return 1 ;;
  esac
}
''' + quiescence_function()
        + section('log "Stopping services and backing up persistent state"',
                  'install -d -o root -g root -m 0700 "$backup_root"')
        + '\nprintf "safe-to-copy\\n"\n'
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [*[f'stopped {unit}' for unit in expected], 'safe-to-copy']


@pytest.mark.parametrize('failure', ['query', 'stop'])
def test_runtime_query_or_stop_failure_blocks_state_copy_even_without_errexit(failure):
    # Actual rollback uses set +e: the function must propagate errors itself.
    result = run(f'test_failure={failure}\n' + '''
install_profile=full
runtime_services=(3mm-core.service)
fail() { echo "$*" >&2; return 1; }
systemctl() {
  case "$1" in
    list-units)
      [[ $test_failure != query ]] || return 1
      printf '3mm-core.service loaded active running Core\\n'
      ;;
    stop) echo attempted-stop; return 1 ;;
  esac
}
''' + quiescence_function() + '''
set +e
stop_runtime_services
result=$?
[[ $result -ne 0 ]] || echo unsafe-copy
exit "$result"
''')
    assert result.returncode != 0
    assert 'unsafe-copy' not in result.stdout
    assert ('attempted-stop' in result.stdout) == (failure == 'stop')


def test_shell_syntax():
    result = subprocess.run([BASH, '-n'], input=SCRIPT.encode(),
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    bootstrap = (Path(__file__).parents[2] / 'install.sh').read_text()
    result = subprocess.run([BASH, '-n'], input=bootstrap.encode(),
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('profile', ['full', 'node'])
@pytest.mark.parametrize('backend', ['host', 'network-manager'])
def test_bootstrap_installs_network_packages_only_for_explicit_management(profile, backend):
    bootstrap = (Path(__file__).parents[2] / 'install.sh').read_text()
    package_selection = bootstrap[bootstrap.index('THREE_MM_BOOTSTRAP_PACKAGES=('):bootstrap.index('[[ $channel == stable')]
    result = run(f'THREE_MM_DEFAULT_CHANNEL=beta\nTHREE_MM_NETWORK_BACKEND={backend}\n'
        f'set -- --profile {profile} --network-backend {backend}\n' + package_selection
        + '\nprintf "%s\\n" "${THREE_MM_BOOTSTRAP_PACKAGES[@]}"\n')
    assert result.returncode == 0, result.stderr
    packages = result.stdout.splitlines()
    assert ('network-manager' in packages) == (backend == 'network-manager')
    assert ('dnsmasq-base' in packages) == (backend == 'network-manager')
    assert ('nodejs' in packages) == (profile == 'full')


@pytest.mark.parametrize('profile', ['full', 'node'])
def test_profile_selects_only_its_units(profile):
    result = run(f'install_profile={profile}\n' +
                 section('runtime_services=(', 'previous_release=""') +
                 '\nprintf "%s\\n" "${installed_units[@]}"\n')
    assert result.returncode == 0, result.stderr
    units = result.stdout.splitlines()
    assert '3mm-agent.service' in units and '3mm-setup.service' in units
    assert '3mm-setup-local.service' in units
    assert ('3mm-core.service' in units) == (profile == 'full')
    assert ('3mm-update-helper.service' in units) == (profile == 'full')
    assert ('3mm-application-extension@.service' in units) == (profile == 'full')
    assert ('3mm-public-web.socket' in units) == (profile == 'full')
    assert ('3mm-public-web.service' in units) == (profile == 'full')
    assert ('3mm-node-recovery.service' in units) == (profile == 'node')


@pytest.mark.parametrize('profile', ['full', 'node'])
def test_dependency_branch_and_validation_order(profile):
    # Replace only the interpreter command with a shell function. No venv or
    # dependencies are installed by this bounded test.
    source = section('log "Creating the release-specific Python environment"',
                     'log "Stopping services and backing up persistent state"')
    source = source.replace('"$release_dir/.venv/bin/python"', 'test_python')
    result = run(f'install_profile={profile}\n' + '''
release_dir=/test/release
deploy_home=/test/home
npm_cache=/test/npm
environment_file=/test/env
device_hostname=test-host
frontend_origin=http://localhost
log() { :; }
python3() { printf 'venv\\n'; }
test_python() { printf 'python %s\\n' "$*"; }
npm() { printf 'npm %s\\n' "$*"; }
fail() { return 1; }
''' + source)
    assert result.returncode == 0, result.stderr
    if profile == 'node':
        assert '--only-binary=:all:' in result.stdout
        assert 'node-requirements.txt' in result.stdout
        assert result.stdout.index('-m pip check') < result.stdout.index('node_preflight.py')
        assert 'validate_profile_role' in result.stdout
        assert 'backend/requirements' not in result.stdout
        assert 'npm install' not in result.stdout
    else:
        assert 'backend/requirements.txt' in result.stdout
        assert 'npm install' in result.stdout


def test_node_failed_dependency_check_stops_before_preflight():
    source = section('log "Creating the release-specific Python environment"',
                     'log "Stopping services and backing up persistent state"')
    source = source.replace('"$release_dir/.venv/bin/python"', 'test_python')
    result = run('''
install_profile=node
release_dir=/test/release
log() { :; }
python3() { :; }
test_python() {
  printf '%s\\n' "$*"
  if [[ "$*" == '-m pip check' ]]; then return 1; fi
}
''' + source + '\necho must-not-continue\n')
    assert result.returncode != 0
    assert 'node_preflight.py' not in result.stdout
    assert 'must-not-continue' not in result.stdout


def test_node_health_checks_do_not_consider_core():
    result = run('install_profile=node\n' +
                 section('verify_runtime() {', 'activate_runtime() {') + '''
systemctl() { [[ "$*" != 'is-active --quiet 3mm-setup-local.service' ]]; }
verify_endpoint() { printf '%s\\n' "$1"; }
verify_runtime
''')
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ['http://127.0.0.1:8890/ready',
                                          'http://127.0.0.1:8895/ready']


def test_failed_endpoint_cannot_be_hidden_by_later_health_during_rollback():
    result = run('install_profile=full\n' +
                 section('verify_runtime() {', 'activate_runtime() {') + '''
systemctl() { return 0; }
verify_endpoint() { [[ "$1" != 'http://127.0.0.1:8890/ready' ]]; }
# Rollback disables errexit, so explicit failure propagation is required.
set +e
verify_runtime
exit $?
''')
    assert result.returncode == 1


def test_backup_preparation_still_precedes_full_unit_installation():
    assert SCRIPT.index('-m deployment.prepare_backup_storage') < SCRIPT.index('install_units "$release_dir"')


@pytest.mark.parametrize('profile', ['full', 'node'])
def test_first_boot_local_status_is_a_complete_health_checked_runtime(profile):
    result = run(f'install_profile={profile}\n' + '''
systemctl() { [[ "$*" == 'is-active --quiet 3mm-setup-local.service' ]]; }
verify_endpoint() { printf '%s\\n' "$1"; }
''' + section('verify_runtime() {', 'activate_runtime() {') + '\nverify_runtime\n')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'http://127.0.0.1:8895/ready'


def test_rollback_to_release_without_local_setup_removes_only_its_obsolete_unit():
    result = run('''
installed_units=(3mm-setup-local.service)
systemctl() { printf '%s\\n' "$*"; }
rm() { printf 'removed %s\\n' "$*"; }
install() { echo forbidden-install; return 1; }
fail() { echo "$*" >&2; return 1; }
''' + section('install_units() {', 'restore_database() {') + '\ninstall_units /missing-rollback-release 0\n')
    assert result.returncode == 0, result.stderr
    assert 'forbidden-install' not in result.stdout
    assert '3mm-setup-local.service' in result.stdout


def test_wired_preflight_and_gpio_group_precede_runtime_mutation():
    assert SCRIPT.index('groupadd --system gpio') < SCRIPT.index('install_units "$release_dir"')
    assert SCRIPT.index('--profile "$install_profile" --check-only') < SCRIPT.index('mutation_started=1')


def test_rollback_restores_actual_previous_units_without_replanning_setup():
    result = run('''
runtime_services=(3mm-core.service 3mm-web.service 3mm-agent.service 3mm-setup.service)
previous_enabled_units=(3mm-core.service 3mm-agent.service)
previous_active_units=(3mm-core.service 3mm-web.service 3mm-agent.service)
systemctl() { printf '%s\\n' "$*"; }
activate_runtime() { echo forbidden-planner; return 1; }
verify_runtime() { echo health-verified; }
''' + section('restore_runtime_units() {', 'restart_always_on_services() {') + '\nrestore_runtime_units\n')
    assert result.returncode == 0, result.stderr
    assert 'enable 3mm-core.service 3mm-agent.service' in result.stdout
    assert 'start 3mm-core.service 3mm-web.service 3mm-agent.service' in result.stdout
    assert 'is-active --quiet 3mm-agent.service' in result.stdout
    assert 'forbidden-planner' not in result.stdout
    assert 'health-verified' in result.stdout


def test_node_environment_does_not_overwrite_hub_or_hardware_on_upgrade():
    source = section('if [[ $install_profile == full ]]; then\nupsert_environment DATABASE_URL',
                     'log "Preparing the independent Agent environment"')
    result = run('''
install_profile=node
environment_backup_created=1
environment_tmp=/test/tmp
environment_file=/test/env
state_root=/test/state
upsert_environment() { printf '%s=%s\\n' "$1" "$2"; }
install() { :; }
rm() { :; }
''' + source)
    assert result.returncode == 0, result.stderr
    assert 'THREE_MM_AGENT_ROLE=node' in result.stdout
    for key in ('DATABASE_URL', 'THREE_MM_CORE_URL', 'THREE_MM_GPIO_DRIVER',
                'THREE_MM_IDENTIFIER_DRIVER', 'AI_SETTINGS_MASTER_KEY'):
        assert key not in result.stdout


@pytest.mark.parametrize('previous', ['', '/'])
def test_node_rollback_restores_previous_or_removes_fresh_units(previous):
    result = run(f'previous_release="{previous}"\n' + '''
install_profile=node
mutation_started=1
rollback_link_updated=0
release_created=0
environment_tmp=''
release_archive=/test/archive
release_dir=/test/new
current_link=/test/current
runtime_services=(3mm-agent.service 3mm-setup.service)
always_on_services=(3mm-node-recovery.service)
installed_units=("${runtime_services[@]}" "${always_on_services[@]}")
systemctl() { :; }
restore_database() { echo forbidden-database-restore; }
restore_environment() { echo restore-environment; }
ln() { echo restore-current-link; }
install_units() { echo restore-previous-units; }
restart_always_on_services() { echo restart-recovery; }
activate_runtime() { echo verify-previous-runtime; }
restore_runtime_units() { activate_runtime "$previous_release"; }
rm() { printf 'remove %s\\n' "$*"; }
''' + quiescence_function() + section('rollback() {', 'if [[ -L $current_link ]]; then') + '''
trap rollback ERR
false
''')
    assert result.returncode == 1
    assert 'restore-environment' in result.stdout
    assert 'forbidden-database-restore' not in result.stdout
    if previous:
        for step in ('restore-current-link', 'restore-previous-units',
                     'restart-recovery', 'verify-previous-runtime'):
            assert step in result.stdout
    else:
        assert '/etc/systemd/system/3mm-node-recovery.service' in result.stdout
        assert '/etc/systemd/system/3mm-agent.service' in result.stdout
        assert 'verify-previous-runtime' not in result.stdout



def test_full_profile_creates_separate_public_web_identity():
    source = section('if [[ $install_profile == full ]]; then\nif ! getent group 3mm-app',
                     'install -d -o root -g root -m 0755 "$install_root"')
    result = run('''
install_profile=full
state_root=/test/state
getent() { return 1; }
id() { return 1; }
groupadd() { printf 'groupadd %s\\n' "$*"; }
useradd() { printf 'useradd %s\\n' "$*"; }
usermod() { printf 'usermod %s\\n' "$*"; }
''' + source)
    assert result.returncode == 0, result.stderr
    assert 'groupadd --system 3mm-public' in result.stdout
    assert 'useradd --system --gid 3mm-public --home-dir /nonexistent --shell /usr/sbin/nologin 3mm-public' in result.stdout
    assert 'usermod -a -G 3mm-app,3mm-public,3mm-platform 3mm' in result.stdout


@pytest.mark.parametrize('failure', ['', 'query', 'stop', 'database', 'fence', 'environment'])
def test_full_rollback_fences_before_any_restart_and_fails_closed(failure):
    result = run(f'test_failure="{failure}"\n' + '''
install_profile=full
mutation_started=1
previous_release=/
rollback_link_updated=0
release_created=0
environment_tmp=''
release_archive=/test/archive
release_dir=/test/new
current_link=/test/current
runtime_services=(3mm-core.service 3mm-agent.service)
always_on_services=(3mm-update-helper.service)
installed_units=("${runtime_services[@]}")
fail() { echo "$*" >&2; return 1; }
systemctl() {
  if [[ $1 == list-units ]]; then
    [[ $test_failure != query ]] || return 1
    printf '3mm-core.service loaded active running Core\\n'
  else
    echo stop-runtime
    [[ $test_failure != stop ]]
  fi
}
restore_database() { echo restore-database; [[ $test_failure != database ]]; }
fence_rollback_authority() { echo fence-authority; [[ $test_failure != fence ]]; }
restore_environment() { echo restore-environment; [[ $test_failure != environment ]]; }
ln() { :; }
install_units() { :; }
restart_always_on_services() { echo restart-helper; }
restore_runtime_units() { echo restart-runtime; }
start_active_application_services() { echo restart-apps; }
rm() { echo cleanup; }
''' + quiescence_function() + section('rollback() {', 'if [[ -L $current_link ]]; then') + '''
trap rollback ERR
false
''')
    assert result.returncode == 1, result.stderr
    if failure:
        assert 'restart-' not in result.stdout
        assert 'cleanup' not in result.stdout  # Keep candidate and recovery evidence.
    else:
        assert result.stdout.index('restore-database') < result.stdout.index('fence-authority')
        assert result.stdout.index('fence-authority') < result.stdout.index('restart-runtime')
        assert result.stdout.index('restart-runtime') < result.stdout.index('restart-apps')


def test_full_rollback_uses_candidate_stdlib_recovery_not_previous_runtime(tmp_path):
    database = tmp_path / 'disposable.db'
    database.touch()
    result = run(f'database="{database.as_posix()}"\n' + '''
install_profile=full
release_dir=/test/new
python3() { printf '%s\\n' "$*"; }
''' + section('fence_rollback_authority() {', 'restore_environment() {') + '''
fence_rollback_authority
''')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '/test/new/deployment/authority_recovery.py --reason deployment_rollback --allow-legacy'


@pytest.mark.parametrize('missing_backup', [False, True])
def test_actual_database_restore_propagates_failure_with_errexit_disabled(tmp_path, missing_backup):
    if not missing_backup:
        (tmp_path / '3mm.db').touch()
    result = run(f'backup_root="{tmp_path.as_posix()}"\n' + '''
database_backup_created=1
database_existed_before_deploy=1
database=/test/live.db
install() { echo failed-copy; return 1; }
rm() { echo unsafe-cleanup; return 0; }
''' + section('restore_database() {', 'fence_rollback_authority() {') + '''
set +e
restore_database
exit $?
''')
    assert result.returncode == 1, result.stderr
    assert 'unsafe-cleanup' not in result.stdout


@pytest.mark.parametrize('legacy', [False, True])
def test_release_python_succeeds_inside_actual_error_trap(tmp_path, legacy):
    release = tmp_path / 'release'
    executable = tmp_path / ('venv/bin/python' if legacy else 'release/.venv/bin/python')
    executable.parent.mkdir(parents=True)
    executable.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
    executable.chmod(0o755)
    result = run(
        f'install_root={shlex.quote(tmp_path.as_posix())}\n'
        f'previous_release={shlex.quote(release.as_posix())}\n'
        + 'fail() { echo "$*" >&2; return 1; }\n'
        + section('release_python() {', 'restore_database() {') + '''
rollback_test() {
  local failure=$?
  trap - ERR
  set +e
  local selected
  selected=$(release_python "$previous_release")
  local selected_status=$?
  printf 'selected-status=%s\\nselected=%s\\n' "$selected_status" "$selected"
  exit "$failure"
}
trap rollback_test ERR
false
''')
    assert result.returncode == 1, result.stderr  # Keep the original deploy failure.
    assert 'selected-status=0' in result.stdout, result.stdout + result.stderr
    assert f'selected={executable.as_posix()}' in result.stdout


@pytest.mark.parametrize('query', ['one', 'none', 'failed', 'start-failed', 'inactive-first'])
def test_active_application_resume_inside_error_trap(tmp_path, query):
    database = tmp_path / 'fixture.db'
    database.touch()
    executable = tmp_path / '.venv/bin/python'
    executable.parent.mkdir(parents=True)
    executable.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
    executable.chmod(0o755)
    source = section('start_active_application_services() {', 'rollback() {')
    source = source.replace('"$python_path" - "$database"', 'test_query - "$database"')
    result = run(
        f'database={shlex.quote(database.as_posix())}\n'
        f'install_root={shlex.quote(tmp_path.as_posix())}\n'
        f'previous_release={shlex.quote(tmp_path.as_posix())}\n'
        f'test_query_result={query}\n'
        + '''
install_profile=full
fail() { echo "$*" >&2; return 1; }
test_query() {
  cat >/dev/null
  case "$test_query_result" in
    one|start-failed) echo 3mm-application-extension@0123456789abcdef01234567.service ;;
    inactive-first)
      echo 3mm-application-extension@0123456789abcdef01234567.service
      echo 3mm-application-extension@abcdef0123456789abcdef01.service
      ;;
    none) return 0 ;;
    failed) echo unreadable-database >&2; return 1 ;;
  esac
}
systemctl() {
  printf 'systemctl %s\\n' "$*"
  if [[ $1 == start && $test_query_result == start-failed ]]; then return 1; fi
  if [[ $1 == is-active && $test_query_result == inactive-first &&
        $3 == 3mm-application-extension@0123456789abcdef01234567.service ]]; then
    return 3
  fi
  return 0
}
'''
        + section('release_python() {', 'restore_database() {') + source + '''
rollback_test() {
  local failure=$?
  trap - ERR
  set +e
  start_active_application_services "$previous_release"
  local resumed=$?
  printf 'resumed=%s\\n' "$resumed"
  exit "$failure"
}
trap rollback_test ERR
false
''')
    assert result.returncode == 1, result.stderr
    if query in ('failed', 'start-failed', 'inactive-first'):
        assert 'resumed=1' in result.stdout
        if query == 'failed':
            assert 'unreadable-database' in result.stderr
            assert 'systemctl ' not in result.stdout
        elif query == 'start-failed':
            assert 'systemctl is-active' not in result.stdout
        else:
            assert 'Active application service did not become active:' in result.stderr
            assert 'is-active --quiet 3mm-application-extension@abcdef0123456789abcdef01.service' not in result.stdout
    else:
        assert 'resumed=0' in result.stdout, result.stdout + result.stderr
        assert ('systemctl start 3mm-application-extension@0123456789abcdef01234567.service'
                in result.stdout) == (query == 'one')


def test_agent_environment_filters_core_secrets_and_keeps_host_settings(tmp_path):
    original=tmp_path/'core.env';original.write_text('DATABASE_URL=private\nAI_SETTINGS_MASTER_KEY=private\nJWT_SECRET=private\nTHREE_MM_AGENT_ROLE=node\nTHREE_MM_CORE_URL=https://hub.example\nTHREE_MM_GPIO_DRIVER=gpiod\nTHREE_MM_GPIO_INPUTS=1,2\nTHREE_MM_PROVISIONING_DATA_DIR=/state\n')
    destination=tmp_path/'agent.env'
    start=SCRIPT.index('# Only Agent configuration enters its own environment;')
    source=SCRIPT[start:SCRIPT.index('PYTHONPATH=',start)]
    result=run(f'environment_file={original}\nagent_environment_file={destination}\n'+"""
install() {
  if [[ $1 == -d ]]; then return; fi
  cp "${@: -2:1}" "${@: -1}"
}
"""+source)
    assert result.returncode==0,result.stderr
    saved=destination.read_text()
    assert 'THREE_MM_AGENT_ROLE=node' in saved and 'THREE_MM_GPIO_INPUTS=1,2' in saved
    assert 'THREE_MM_CORE_URL=https://hub.example' in saved and 'THREE_MM_PROVISIONING_DATA_DIR=/state' in saved
    assert all(key not in saved for key in ('DATABASE_URL','AI_SETTINGS_MASTER_KEY','JWT_SECRET'))


@pytest.mark.parametrize('master_key', ['', 'environment-only-test-key'])
def test_runtime_activation_gets_local_identity_key_without_argument_disclosure(master_key):
    result = run(
        'release_python() { printf checked_python; }\n'
        'verify_runtime() { :; }\n'
        f'expected_key={shlex.quote(master_key)}\n'
        + (f'ai_master_key={shlex.quote(master_key)}\n' if master_key else '')
        + """
checked_python() {
  if [[ $* != *--check-active* ]]; then
    [[ ${AI_SETTINGS_MASTER_KEY-} == "$expected_key" ]] || return 1
    if [[ -n $expected_key ]]; then [[ $* != *"$expected_key"* ]] || return 1; fi
  fi
}
"""
        + section('activate_runtime() {', 'restore_runtime_units() {')
        + '\nactivate_runtime /fixture-release\n'
    )
    assert result.returncode == 0, result.stderr
