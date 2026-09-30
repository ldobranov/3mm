"""Run bounded installer shell sections with command doubles, never real services.

These are profile regression tests, not Linux clean-install/rollback acceptance.
"""
from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = (Path(__file__).parents[1] / 'install-systemd.sh').read_text(encoding='utf-8')
BASH = shutil.which('bash') or (
    'C:/Program Files/Git/bin/bash.exe'
    if Path('C:/Program Files/Git/bin/bash.exe').is_file() else None
)
pytestmark = pytest.mark.skipif(BASH is None, reason='Bash is required')


def run(source):
    return subprocess.run([BASH, '--noprofile', '--norc'],
                          input='set -Eeuo pipefail\n' + source,
                          text=True, capture_output=True, timeout=10)


def section(start, end):
    return SCRIPT[SCRIPT.index(start):SCRIPT.index(end)]


def test_shell_syntax():
    result = subprocess.run([BASH, '-n'], input=SCRIPT, text=True,
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    bootstrap = (Path(__file__).parents[2] / 'install.sh').read_text()
    result = subprocess.run([BASH, '-n'], input=bootstrap, text=True,
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('profile', ['full', 'node'])
def test_profile_selects_only_its_units(profile):
    result = run(f'install_profile={profile}\n' +
                 section('runtime_services=(', 'previous_release=""') +
                 '\nprintf "%s\\n" "${installed_units[@]}"\n')
    assert result.returncode == 0, result.stderr
    units = result.stdout.splitlines()
    assert '3mm-agent.service' in units and '3mm-setup.service' in units
    assert ('3mm-core.service' in units) == (profile == 'full')
    assert ('3mm-update-helper.service' in units) == (profile == 'full')
    assert ('3mm-application-extension@.service' in units) == (profile == 'full')
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
systemctl() { return 0; }
verify_endpoint() { printf '%s\\n' "$1"; }
verify_runtime
''')
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ['http://127.0.0.1:8890/ready',
                                          'http://127.0.0.1:8895/ready']


def test_backup_preparation_still_precedes_full_unit_installation():
    assert SCRIPT.index('-m deployment.prepare_backup_storage') < SCRIPT.index('install_units "$release_dir"')


def test_node_environment_does_not_overwrite_hub_or_hardware_on_upgrade():
    source = section('if [[ $install_profile == full ]]; then\nupsert_environment DATABASE_URL',
                     'log "Installing service definitions"')
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
rm() { printf 'remove %s\\n' "$*"; }
''' + section('rollback() {', 'if [[ -L $current_link ]]; then') + '''
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
