"""Execute public bootstrap options/catalog/manifest with disposable command doubles.

No root check bypass in the product, network, APT, systemd or real installation.
These bounded sections stop before prerequisite installation and artifact download.
"""
import json
from pathlib import Path
import shlex
import sys

import pytest

from deployment.tests.test_node_installer import BASH, run

BOOTSTRAP = (Path(__file__).parents[2] / 'install.sh').read_text(encoding='utf-8')
pytestmark = pytest.mark.skipif(BASH is None, reason='Bash is required')
REPOSITORY = 'ldobranov/3mm'


def release(tag='v0.3.7', **values):
    return {'tag_name': tag, 'draft': False, 'prerelease': '-' in tag, **values}


def selection(tmp_path, arguments=(), *, channel='', network='', stored=None,
              tag='', payload=None, manifest_changes=None):
    environment = tmp_path/'stored.env'
    if stored is not None:
        environment.write_text('THREE_MM_NETWORK_BACKEND='+stored+'\n')
    catalog = tmp_path/'catalog.json'
    catalog.write_text(json.dumps(payload if payload is not None else release()))
    selected = payload if isinstance(payload, dict) else release()
    version = selected.get('tag_name', 'v0.3.7')[1:]
    profile = 'node' if 'node' in arguments else 'full'
    architecture = 'armv6l' if profile == 'node' else 'aarch64'
    release_channel = ('test' if version.partition('-')[2].split('.')[0].lower() == 'test'
                       else 'beta') if '-' in version else 'stable'
    filename = f'3mm-{version}-{architecture}.tar.gz'
    manifest = {'schema_version': 1, 'profile': profile, 'version': version,
        'release_id': 'v'+version, 'channel': release_channel, 'commit': 'a'*40,
        'artifacts': [{'architecture': architecture, 'filename': filename,
            'python': f'{sys.version_info.major}.{sys.version_info.minor}',
            'download_url': f'https://github.com/{REPOSITORY}/releases/download/v{version}/{filename}',
            'sha256': 'b'*64, 'size_bytes': 123}], 'dependencies': {'apt_packages': []}}
    manifest.update(manifest_changes or {})
    fixture = tmp_path/'manifest.json'
    fixture.write_text(json.dumps(manifest))
    stage = tmp_path/'stage'
    stage.mkdir()
    options = BOOTSTRAP[:BOOTSTRAP.index('[[ ${EUID:-')].replace('/etc/3mm/3mm.env', environment.as_posix())
    paths = BOOTSTRAP[BOOTSTRAP.index('release_json="$stage/release.json"'):
                      BOOTSTRAP.index("printf 'Selecting the published")]
    choose = BOOTSTRAP[BOOTSTRAP.index("printf 'Selecting the published"):
                       BOOTSTRAP.index('mapfile -t packages <')]
    return run(
        f'THREE_MM_CHANNEL={shlex.quote(channel)}\nTHREE_MM_TAG={shlex.quote(tag)}\n'
        f'THREE_MM_NETWORK_BACKEND={shlex.quote(network)}\nTHREE_MM_FRONTEND_ORIGIN=\n'
        + 'set -- '+shlex.join(arguments)+'\n'+options
        + f'\nstage={shlex.quote(stage.as_posix())}\narchitecture={architecture}\n'
        + f'python3() {{ {shlex.quote(sys.executable)} "$@"; }}\n'
        + 'apt-get() { echo forbidden-apt; return 98; }\n'
        + 'systemd-run() { echo forbidden-systemd; return 98; }\n'
        + '''wget() {
  local destination= url=
  while [[ $# -gt 0 ]]; do
    if [[ $1 == -qO ]]; then destination=$2; shift 2; else url=$1; shift; fi
  done
  printf 'fetch=%s\\n' "$url"
  case "$url" in
    https://api.github.com/repos/ldobranov/3mm/releases*) cp "$catalog_fixture" "$destination" ;;
    https://github.com/ldobranov/3mm/releases/download/*/*manifest.json) cp "$manifest_fixture" "$destination" ;;
    *) echo unexpected-download >&2; return 99 ;;
  esac
}
'''
        + f'catalog_fixture={shlex.quote(catalog.as_posix())}\nmanifest_fixture={shlex.quote(fixture.as_posix())}\n'
        + paths+choose
        + '\nprintf "selected=%s channel=%s backend=%s profile=%s\\n" "$selected_tag" "$channel" "$network_backend" "$install_profile"\n'
        + 'printf "packages=%s\\n" "${THREE_MM_BOOTSTRAP_PACKAGES[*]}"\n'
    )


@pytest.mark.parametrize('profile', ['full', 'node'])
def test_plain_bootstrap_uses_published_stable_and_keeps_lan_without_network_packages(tmp_path, profile):
    result = selection(tmp_path, ['--profile', profile])
    assert result.returncode == 0, result.stderr
    assert 'fetch=https://api.github.com/repos/ldobranov/3mm/releases/latest\n' in result.stdout
    assert f'selected=v0.3.7 channel=stable backend=host profile={profile}' in result.stdout
    assert 'network-manager' not in result.stdout and 'dnsmasq-base' not in result.stdout
    assert 'forbidden-' not in result.stdout
    assert ('3mm-node-manifest.json' in result.stdout) == (profile == 'node')


@pytest.mark.parametrize('flag', ['-ap', '--ap'])
@pytest.mark.parametrize('profile', ['full', 'node'])
def test_explicit_ap_selects_managed_setup_and_dependencies(tmp_path, flag, profile):
    result = selection(tmp_path, ['--profile', profile, flag], network='host')
    assert result.returncode == 0, result.stderr
    assert 'backend=network-manager' in result.stdout
    assert 'network-manager' in result.stdout.split('packages=')[1]
    assert 'dnsmasq-base' in result.stdout


@pytest.mark.parametrize('arguments', [
    ['-ap', '--network-backend', 'host'], ['--network-backend', 'host', '-ap'],
    ['-ap', '--network-backend', 'invalid'],
])
def test_conflicting_network_options_refuse_before_any_download(tmp_path, arguments):
    result = selection(tmp_path, arguments)
    assert result.returncode != 0
    assert 'conflicts' in result.stderr and 'fetch=' not in result.stdout


@pytest.mark.parametrize('stored', ['host', 'network-manager'])
def test_saved_network_choice_is_preserved_without_an_override(tmp_path, stored):
    result = selection(tmp_path, stored=stored)
    assert result.returncode == 0, result.stderr
    assert 'backend='+stored in result.stdout


@pytest.mark.parametrize('tag', ['v0.3.7', 'v0.3.0-beta.57', 'v0.3.8-test.1', 'v0.3.8-TEST.1'])
@pytest.mark.parametrize('source', ['option', 'environment'])
def test_exact_tag_infers_channel_only_when_not_explicit(tmp_path, tag, source):
    arguments = ['--tag', tag] if source == 'option' else []
    result = selection(tmp_path, arguments, tag=tag if source == 'environment' else '', payload=release(tag))
    assert result.returncode == 0, result.stderr
    assert f'fetch=https://api.github.com/repos/{REPOSITORY}/releases/tags/{tag}' in result.stdout
    assert 'selected='+tag in result.stdout


@pytest.mark.parametrize('channel,tag', [('beta', 'v0.3.0-beta.57'), ('test', 'v0.3.8-test.1')])
def test_explicit_prerelease_channel_is_not_replaced_by_stable(tmp_path, channel, tag):
    # Includes newer releases from the wrong channel; never install those instead.
    result = selection(tmp_path, ['--channel', channel], payload=[release('v9.0.0'), release(tag)],
                       manifest_changes={'version': tag[1:], 'release_id': tag, 'channel': channel,
                           'artifacts': [{'architecture': 'aarch64', 'filename': '3mm-test-aarch64.tar.gz',
                               'download_url': f'https://github.com/{REPOSITORY}/releases/download/{tag}/3mm-test-aarch64.tar.gz',
                               'sha256': 'b'*64, 'size_bytes': 123}]})
    assert result.returncode == 0, result.stderr
    assert '/releases?per_page=20' in result.stdout and f'selected={tag} channel={channel}' in result.stdout


def test_explicit_cli_channel_overrides_environment(tmp_path):
    result = selection(tmp_path, ['--channel', 'stable'], channel='beta')
    assert result.returncode == 0, result.stderr
    assert '/releases/latest' in result.stdout and 'channel=stable' in result.stdout


def test_explicit_tag_option_overrides_environment_pin(tmp_path):
    result = selection(tmp_path, ['--tag', 'v0.3.7'], tag='v0.3.0-beta.57')
    assert result.returncode == 0, result.stderr
    assert 'selected=v0.3.7 channel=stable' in result.stdout


@pytest.mark.parametrize('arguments', [
    ['--channel', 'invalid'], ['--channel', ''], ['--tag', '../invalid'], ['--channel'], ['--tag'],
    ['--network-backend'], ['--profile', 'invalid'], ['--unknown'],
])
def test_invalid_options_stop_before_download(tmp_path, arguments):
    result = selection(tmp_path, arguments)
    assert result.returncode != 0 and 'fetch=' not in result.stdout


@pytest.mark.parametrize('arguments,channel,tag', [
    (['--channel', 'stable', '--tag', 'v0.3.0-beta.57'], '', 'v0.3.0-beta.57'),
    (['--tag', 'v0.3.7'], 'beta', 'v0.3.7'),
])
def test_explicit_channel_mismatch_never_falls_back(tmp_path, arguments, channel, tag):
    result = selection(tmp_path, arguments, channel=channel, payload=release(tag))
    assert result.returncode != 0 and 'not a published release in this channel' in result.stderr
    assert '/releases/download/' not in result.stdout and 'selected=' not in result.stdout


@pytest.mark.parametrize('payload', [
    release(draft=True), release(prerelease=True), release('v0.3.0-beta.57'),
    release('../invalid'), [release()], {'message': 'Not Found'},
])
def test_invalid_latest_never_falls_back_to_old_beta_or_downloads_artifact(tmp_path, payload):
    result = selection(tmp_path, payload=payload)
    assert result.returncode != 0
    assert '/releases/download/' not in result.stdout and 'selected=' not in result.stdout


@pytest.mark.parametrize('changes', [
    {'channel': 'beta'}, {'version': '0.3.6'}, {'release_id': 'v0.3.6'},
    {'commit': 'invalid'}, {'artifacts': []}, {'dependencies': {'apt_packages': ['$(false)']}},
])
def test_invalid_manifest_stops_before_installation(tmp_path, changes):
    result = selection(tmp_path, manifest_changes=changes)
    assert result.returncode != 0
    assert 'selected=' not in result.stdout and 'forbidden-' not in result.stdout


@pytest.mark.parametrize('backend', ['host', 'network-manager'])
@pytest.mark.parametrize('profile', ['full', 'node'])
def test_detached_worker_receives_resolved_network_choice_without_starting_real_job(tmp_path, backend, profile):
    source = BOOTSTRAP[BOOTSTRAP.index('unit_suffix=$(basename "$stage"'):]
    result = run(f'stage={shlex.quote(tmp_path.as_posix())}\nnetwork_backend={backend}\n'
        f'install_profile={profile}\nrelease_id=v0.3.7\nfrontend_origin=http://192.0.2.1\n'
        'worker=/unused/worker\ninstaller=/unused/installer\narchive=/unused/archive\n'
        'artifact_sha256='+'b'*64+'\n'
        'systemd-run() { printf "job-argument=%s\\n" "$@"; }\n'+source)
    assert result.returncode == 0, result.stderr
    assert 'job-argument=--setenv=THREE_MM_NETWORK_BACKEND='+backend in result.stdout
    assert 'job-argument=--no-block' in result.stdout and 'job-argument='+profile in result.stdout
    assert ('Host networking is preserved.' in result.stdout) == (backend == 'host')
    assert ('On fresh media, Wi-Fi SSH may close' in result.stdout) == (backend == 'network-manager')
