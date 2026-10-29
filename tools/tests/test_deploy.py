"""Local rollout cache integrity and detached dispatch, without device changes."""
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile

import pytest
from tools import deploy as local, deploy_remote as remote


def kit(tmp_path, *, key='a' * 64, with_agent=False):
    folder = tmp_path / ('bundle-' + key[:8]); folder.mkdir()
    payload = {'core.tar.gz': b'core', 'host-wheels.tar.gz': b'wheels', 'deploy_remote.py': b'worker'}
    value = {'schema_version': 2, 'key': key, 'release_id': 'local-' + key[:24],
        'architecture': platform.machine(), 'python': '.'.join(map(str, sys.version_info[:2])),
        'host': {'key': 'b'*64, 'sources': {'__main__.py': 'c'*64}, 'dependencies': {'example': '1.0'},
            'architecture': platform.machine(), 'python': '.'.join(map(str, sys.version_info[:2])), 'image_provider': True},
        'agent': None, 'files': {n: local.digest(d) for n, d in payload.items()}}
    if with_agent: value['agent'] = {k: v for k, v in value['host'].items() if k != 'image_provider'}
    payload['manifest.json'] = local.encoded(value)
    for name, data in payload.items(): (folder / name).write_bytes(data)
    (folder / 'checks.json').write_text('{}')
    local.write_tar(folder / 'kit.tar.gz', payload)
    ready = {'key': key, 'files': {n: local.digest(d) for n, d in payload.items()},
        'kit_sha256': remote.digest(folder / 'kit.tar.gz'), 'checks_sha256': remote.digest(folder / 'checks.json')}
    local.write_json(folder / 'ready.json', ready)
    return folder, value, ready


@pytest.mark.parametrize('name', ['core.tar.gz', 'manifest.json', 'kit.tar.gz', 'checks.json'])
def test_ready_detects_payload_and_evidence_tampering(tmp_path, name):
    folder, _, _ = kit(tmp_path)
    local.validate_ready(folder)
    with (folder / name).open('ab') as stream: stream.write(b'changed')
    with pytest.raises(ValueError): local.validate_ready(folder)


def test_snapshot_reuses_frozen_bytes_and_refuses_edits(tmp_path):
    repo = tmp_path / 'repo'; repo.mkdir(); (repo / 'app.py').write_bytes(b'old')
    inputs = {'app.py': local.digest(b'old')}; cache = tmp_path / 'cache'
    source = local.snapshot(repo, inputs, cache)
    (repo / 'app.py').write_bytes(b'new')
    assert local.snapshot(repo, inputs, cache) == source
    (source / 'app.py').write_bytes(b'changed')
    with pytest.raises(ValueError, match='Cached source changed'): local.snapshot(repo, inputs, cache)
    with pytest.raises(ValueError, match='Source changed'): local.snapshot(repo, {'app.py': 'f'*64}, cache)


def test_inventory_excludes_live_state_credentials_and_preserves_current_source(tmp_path, monkeypatch):
    names = ['backend/main.py', 'backend/private.env', 'backend/data/live.db', 'private-deploy.ps1',
        '.runtime/private.py', 'frontend/src/main.ts', 'libraries/example/.3mm-source-only', 'deploy.ps1']
    for name in names:
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('source')
    monkeypatch.setattr(local.subprocess, 'check_output', lambda *a, **kw: '\0'.join(names).encode())
    assert set(local.inventory(tmp_path)) == {'backend/main.py', 'frontend/src/main.ts', 'libraries/example/.3mm-source-only', 'deploy.ps1'}


def test_dependency_cache_ignores_only_tool_generated_root_directories(tmp_path):
    (tmp_path / 'library').mkdir(); (tmp_path / 'library/code.js').write_text('checked')
    expected = local.tree_inventory(tmp_path, local.NODE_BUILD_OUTPUTS)
    for name in local.NODE_BUILD_OUTPUTS:
        (tmp_path / name).mkdir(); (tmp_path / name / 'generated').write_text('build output')
    assert local.tree_inventory(tmp_path, local.NODE_BUILD_OUTPUTS) == expected
    (tmp_path / 'library/code.js').write_text('modified dependency')
    assert local.tree_inventory(tmp_path, local.NODE_BUILD_OUTPUTS) != expected


def test_cached_python_evidence_invalidated_by_code_and_dependencies(tmp_path, monkeypatch):
    source = tmp_path / 'source'; source.mkdir(); calls = []
    def run(command, cwd, log):
        log.write_bytes(b'passed')
        calls.append(command); return {'command': list(map(str, command)), 'log_sha256': local.digest(b'passed')}
    monkeypatch.setattr(local, 'run', run)
    monkeypatch.setattr(local.importlib.metadata, 'distributions', lambda: [])
    first = local.verify_python(source, {'backend/main.py': '1'}, tmp_path, ['backend/tests/test_x.py'])
    assert first['strategy'] == 'targeted'
    assert local.verify_python(source, {'backend/main.py': '1', 'docs/x.md': 'changed'}, tmp_path, None) == first
    assert len(calls) == 1
    local.verify_python(source, {'backend/main.py': '2'}, tmp_path, ['backend/tests/test_x.py'])
    local.verify_python(source, {'backend/main.py': '2', 'backend/requirements.txt': 'new'}, tmp_path, ['backend/tests/test_x.py'])
    assert len(calls) == 3


@pytest.mark.parametrize('entry', ['../escape', '/absolute', 'a/../b', 'a\\b'])
def test_archive_path_escape_refused_before_extraction(tmp_path, entry):
    path = tmp_path / 'bad.tar'; local.write_tar(path, {entry: b'unsafe'})
    with pytest.raises(ValueError): remote.unpack(path, tmp_path / 'output')
    assert not (tmp_path / 'output').exists()


def test_archive_symlinks_refused(tmp_path):
    path = tmp_path / 'bad.tar'
    with tarfile.open(path, 'w') as archive:
        member = tarfile.TarInfo('link'); member.type = tarfile.SYMTYPE; member.linkname = '/etc'
        archive.addfile(member)
    with pytest.raises(ValueError): remote.unpack(path, tmp_path / 'output')


@pytest.mark.parametrize('change', ['extra', 'boolean', 'escape', 'digest', 'dependencies'])
def test_manifest_contract_refuses_unsafe_input(tmp_path, change):
    _, value, _ = kit(tmp_path)
    if change == 'extra': value['extra'] = True
    if change == 'boolean': value['host']['image_provider'] = 1
    if change == 'escape': value['host']['sources'] = {'../escape': 'a'*64}
    if change == 'digest': value['files']['core.tar.gz'] = 'wrong'
    if change == 'dependencies': value['host']['dependencies'] = {'bad;command': '1'}
    with pytest.raises(ValueError): remote.manifest(value)


def setup_dispatch(tmp_path, monkeypatch):
    monkeypatch.setattr(remote, 'STATE', tmp_path / 'state')
    # Tests use an ordinary account; production still requires root-owned state.
    from contextlib import contextmanager
    @contextmanager
    def lock():
        remote.STATE.mkdir(exist_ok=True); yield
    monkeypatch.setattr(remote, 'dispatch_lock', lock)
    current = tmp_path / 'current'; current.mkdir()
    (current / '.3mm-install-profile').write_text('full\n')
    monkeypatch.setattr(remote, 'CURRENT', current)
    monkeypatch.setattr(remote, 'current_metadata', lambda: {'deployment_key': 'old'})
    monkeypatch.setattr(remote, 'ready', lambda: True)
    monkeypatch.setattr(remote, 'host_matches', lambda _: True)
    calls = []
    monkeypatch.setattr(remote.subprocess, 'run', lambda *a, **k: calls.append(a[0]))
    return calls


def test_published_core_without_metadata_profile_uses_installer_marker(tmp_path, monkeypatch):
    folder, value, ready = kit(tmp_path); calls = setup_dispatch(tmp_path, monkeypatch)
    monkeypatch.setattr(remote, 'current_metadata', lambda: {'release_id': 'v0.3.2', 'version': '0.3.2'})
    assert remote.start(folder / 'kit.tar.gz', ready['kit_sha256'])['state'] == 'dispatching'
    assert len(calls) == 1


@pytest.mark.parametrize('profile', ['node', 'unknown', ''])
def test_invalid_or_node_profile_cannot_dispatch_even_with_full_metadata(tmp_path, monkeypatch, profile):
    folder, value, ready = kit(tmp_path); calls = setup_dispatch(tmp_path, monkeypatch)
    (remote.CURRENT / '.3mm-install-profile').write_text(profile + '\n')
    monkeypatch.setattr(remote, 'current_metadata', lambda: {'profile': 'full'})
    with pytest.raises(ValueError, match='profile'):
        remote.start(folder / 'kit.tar.gz', ready['kit_sha256'])
    assert not calls and not (remote.STATE / value['key']).exists()


def test_missing_profile_marker_cannot_dispatch(tmp_path, monkeypatch):
    folder, value, ready = kit(tmp_path); calls = setup_dispatch(tmp_path, monkeypatch)
    (remote.CURRENT / '.3mm-install-profile').unlink()
    with pytest.raises(FileNotFoundError):
        remote.start(folder / 'kit.tar.gz', ready['kit_sha256'])
    assert not calls and not (remote.STATE / value['key']).exists()


@pytest.mark.parametrize('mismatch', ['architecture', 'Python'])
def test_target_mismatch_still_refuses_before_dispatch(tmp_path, monkeypatch, mismatch):
    folder, value, ready = kit(tmp_path); calls = setup_dispatch(tmp_path, monkeypatch)
    if mismatch == 'architecture':
        monkeypatch.setattr(remote.platform, 'machine', lambda: 'foreign')
    else:
        from types import SimpleNamespace
        monkeypatch.setattr(remote, 'sys', SimpleNamespace(version_info=(9, 9)))
    with pytest.raises(ValueError, match=mismatch):
        remote.start(folder / 'kit.tar.gz', ready['kit_sha256'])
    assert not calls and not (remote.STATE / value['key']).exists()


def test_repeat_observes_and_lost_dispatch_ack_never_replays(tmp_path, monkeypatch):
    folder, value, ready = kit(tmp_path); calls = setup_dispatch(tmp_path, monkeypatch)
    def lost(*a, **kw):
        calls.append(a[0]); raise subprocess.CalledProcessError(1, a[0])
    monkeypatch.setattr(remote.subprocess, 'run', lost)
    with pytest.raises(subprocess.CalledProcessError): remote.start(folder / 'kit.tar.gz', ready['kit_sha256'])
    assert remote.start(folder / 'kit.tar.gz', ready['kit_sha256'])['state'] == 'dispatching'
    assert len(calls) == 1
    assert not list(remote.STATE.glob('.incoming-*'))
    assert not list(remote.STATE.glob('.kit-*'))
    path = remote.STATE / value['key'] / 'status.json'
    record = json.loads(path.read_text()); record['state'] = 'failed'; remote.write_json(path, record)
    with pytest.raises(ValueError, match='inspection'): remote.start(folder / 'kit.tar.gz', ready['kit_sha256'])
    assert len(calls) == 1


def test_already_installed_healthy_kit_does_not_dispatch(tmp_path, monkeypatch):
    folder, value, ready = kit(tmp_path); calls = setup_dispatch(tmp_path, monkeypatch)
    monkeypatch.setattr(remote, 'current_metadata', lambda: {'profile': 'full', 'deployment_key': value['key']})
    assert remote.start(folder / 'kit.tar.gz', ready['kit_sha256'])['result'] == 'already_ready'
    assert not calls
    assert remote.decision({'state': 'running'}, value, {'deployment_key': value['key']}, True, True) == 'observe'
    assert remote.decision({'state': 'failed'}, value, {'deployment_key': value['key']}, True, True) == 'inspect'


def test_active_job_blocks_another_key_and_corruption_blocks_dispatch(tmp_path, monkeypatch):
    folder, _, ready = kit(tmp_path); calls = setup_dispatch(tmp_path, monkeypatch)
    remote.start(folder / 'kit.tar.gz', ready['kit_sha256'])
    second, _, ready2 = kit(tmp_path, key='d'*64)
    with pytest.raises(ValueError, match='Another rollout'): remote.start(second / 'kit.tar.gz', ready2['kit_sha256'])
    with pytest.raises(ValueError, match='checksum'): remote.start(second / 'kit.tar.gz', '0'*64)
    assert len(calls) == 1


def test_work_build_failure_precedes_core_and_cannot_be_replayed(tmp_path, monkeypatch):
    folder, value, ready = kit(tmp_path); calls = setup_dispatch(tmp_path, monkeypatch)
    remote.start(folder / 'kit.tar.gz', ready['kit_sha256'])
    monkeypatch.setattr(remote, 'frontend_origin', lambda: 'http://device.local')
    monkeypatch.setattr(remote, 'host_matches', lambda _: False)
    def unpack(archive, destination, **kw):
        destination.mkdir(); (destination / '.3mm-release.json').write_text(json.dumps({'deployment_key': value['key'], 'profile': 'full'}))
    monkeypatch.setattr(remote, 'unpack', unpack)
    def fail(*a): raise ValueError('Native build failed')
    monkeypatch.setattr(remote, 'native_artifact', fail)
    with pytest.raises(ValueError, match='Native build failed'): remote.work(value['key'])
    assert len(calls) == 1  # Only systemd dispatch, never the Core installer.
    state = json.loads((remote.STATE / value['key'] / 'status.json').read_text())
    assert state['state'] == 'failed' and state['phase'] == 'prepare native host'
    with pytest.raises(ValueError, match='no replay'): remote.work(value['key'])


def test_installer_preserves_host_network_selection(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setenv('THREE_MM_NETWORK_BACKEND', 'wrong')
    monkeypatch.setattr(remote.subprocess, 'run', lambda a, **kw: seen.append(kw['env']))
    remote.command(['true'], source=tmp_path)
    assert 'THREE_MM_NETWORK_BACKEND' not in seen[0]
    assert seen[0]['PYTHONPATH'] == str(tmp_path)


def test_core_only_work_reuses_native_host_and_retains_checked_archive(tmp_path, monkeypatch):
    folder, value, ready = kit(tmp_path); setup_dispatch(tmp_path, monkeypatch)
    remote.start(folder / 'kit.tar.gz', ready['kit_sha256'])
    monkeypatch.setattr(remote, 'frontend_origin', lambda: 'http://device.local:8080')
    def unpack(archive, destination, **kw):
        destination.mkdir(); (destination / '.3mm-release.json').write_text(json.dumps({'deployment_key': value['key'], 'profile': 'full'}))
    monkeypatch.setattr(remote, 'unpack', unpack)
    monkeypatch.setattr(remote, 'native_artifact', lambda *a: pytest.fail('Unchanged host rebuilt'))
    def install(args, **kw):
        assert str(args[1]).endswith('/deployment/install-systemd.sh')
        assert args[4] == 'http://device.local:8080' and args[-1] == 'full'
        archive = Path(args[2]); assert archive.read_bytes() == b'core'; archive.unlink()
        monkeypatch.setattr(remote, 'current_metadata', lambda: {'deployment_key': value['key']})
    monkeypatch.setattr(remote, 'command', install)
    remote.work(value['key'])
    stage = remote.STATE / value['key']
    assert (stage / 'core.tar.gz').read_bytes() == b'core'
    assert json.loads((stage / 'status.json').read_text())['state'] == 'succeeded'
    remote.read_bundle(stage)


def test_host_fingerprint_requires_exact_sources_dependencies_and_target(tmp_path, monkeypatch):
    _, value, _ = kit(tmp_path); spec = value['host']
    root = tmp_path / 'hosts'; release = root / 'releases' / ('c'*64); release.mkdir(parents=True)
    pointer = root / 'default/current'; pointer.parent.mkdir(); pointer.symlink_to(release)
    metadata = {'binding': {'sources': spec['sources'], 'dependencies': spec['dependencies'],
        'target': {'machine': spec['architecture'], 'python_tag': 'cpython-' + spec['python'].replace('.', '')}}}
    path = release / 'component.json'; path.write_text(json.dumps(metadata))
    original = remote.regular
    def root_owned(path, limit):
        info = original(path, limit)
        from types import SimpleNamespace
        return SimpleNamespace(st_uid=0, st_mode=info.st_mode)
    monkeypatch.setattr(remote, 'regular', root_owned)
    assert remote.host_matches(spec, pointer)
    metadata['binding']['sources'] = {'__main__.py': 'd'*64}; path.write_text(json.dumps(metadata))
    assert not remote.host_matches(spec, pointer)
    assert not remote.host_matches({**spec, 'python': '0.0'}, pointer)


@pytest.mark.parametrize('change', ['extra', 'target', 'sources', 'dependency', 'boolean'])
def test_agent_selection_is_bounded_and_target_bound(tmp_path, change):
    _, value, _ = kit(tmp_path, with_agent=True)
    if change == 'extra': value['agent']['extra'] = True
    if change == 'target': value['agent']['architecture'] = 'foreign'
    if change == 'sources': value['agent']['sources'] = {'../escape': 'a'*64}
    if change == 'dependency': value['agent']['dependencies'] = {'x': ['1']}
    if change == 'boolean': value['agent'] = True
    with pytest.raises(ValueError): remote.manifest(value)


@pytest.mark.parametrize('fail_update', [False, True])
def test_selected_agent_uses_standard_update_after_core_and_failure_is_not_success(tmp_path, monkeypatch, fail_update):
    folder, value, ready = kit(tmp_path, with_agent=True); setup_dispatch(tmp_path, monkeypatch)
    monkeypatch.setattr(remote, 'agent_ready', lambda _: False)
    remote.start(folder / 'kit.tar.gz', ready['kit_sha256'])
    monkeypatch.setattr(remote, 'frontend_origin', lambda: 'http://device.local')
    def unpack(archive, destination, **kw):
        destination.mkdir(); (destination / '.3mm-release.json').write_text(json.dumps({'deployment_key': value['key'], 'profile': 'full'}))
    monkeypatch.setattr(remote, 'unpack', unpack)
    monkeypatch.setattr(remote, 'CURRENT', tmp_path)
    operations = []
    def prepare(source, spec):
        assert operations == ['Core'] and spec == value['agent'] and source == tmp_path
        operations.append('build Agent')
        return tmp_path / 'agent.tar', 'd'*64
    monkeypatch.setattr(remote, 'agent_artifact', prepare)
    def run(args, **kw):
        if args[0] == 'bash':
            operations.append('Core')
            monkeypatch.setattr(remote, 'current_metadata', lambda: {'deployment_key': value['key']})
        else:
            assert args[1:5] == ['-m', 'deployment.service_component', 'agent', 'update']
            assert args[5:] == ['--artifact', tmp_path / 'agent.tar', '--sha256', 'd'*64]
            operations.append('update Agent')
            if fail_update: raise ValueError('Agent update failed/rolled back')
            monkeypatch.setattr(remote, 'agent_ready', lambda _: True)
    monkeypatch.setattr(remote, 'command', run)
    if fail_update:
        with pytest.raises(ValueError, match='Agent update failed'): remote.work(value['key'])
    else: remote.work(value['key'])
    assert operations == ['Core', 'build Agent', 'update Agent']
    status = json.loads((remote.STATE / value['key'] / 'status.json').read_text())
    assert status['state'] == ('failed' if fail_update else 'succeeded')
    with pytest.raises(ValueError, match='no replay'): remote.work(value['key'])


def test_installed_core_does_not_hide_stale_or_unhealthy_selected_agent(tmp_path, monkeypatch):
    folder, value, ready = kit(tmp_path, with_agent=True); calls = setup_dispatch(tmp_path, monkeypatch)
    monkeypatch.setattr(remote, 'current_metadata', lambda: {'profile': 'full', 'deployment_key': value['key']})
    monkeypatch.setattr(remote, 'agent_ready', lambda _: False)
    with pytest.raises(ValueError, match='inspection'): remote.start(folder / 'kit.tar.gz', ready['kit_sha256'])
    assert not calls


def test_agent_ready_requires_matching_bytes_and_real_process_probe(tmp_path, monkeypatch):
    _, value, _ = kit(tmp_path, with_agent=True); calls = []
    monkeypatch.setattr(remote, 'host_matches', lambda *a, **k: False)
    monkeypatch.setattr(remote, 'command', lambda *a, **k: calls.append(a))
    assert not remote.agent_ready(value['agent']) and not calls
    monkeypatch.setattr(remote, 'host_matches', lambda *a, **k: True)
    assert remote.agent_ready(value['agent']) and len(calls) == 1
    def fail(*a, **k): raise subprocess.CalledProcessError(1, 'probe')
    monkeypatch.setattr(remote, 'command', fail)
    assert not remote.agent_ready(value['agent'])
    assert remote.agent_ready(None)


def test_agent_artifact_cache_rejects_foreign_binding_and_tampering(tmp_path, monkeypatch):
    _, value, _ = kit(tmp_path, with_agent=True); spec = value['agent']
    monkeypatch.setattr(remote, 'CACHE', tmp_path / 'cache')
    target = remote.CACHE / 'agents' / spec['key']; target.mkdir(parents=True)
    metadata = {'component': 'agent', 'binding': {'sources': spec['sources'], 'dependencies': spec['dependencies'],
        'target': {'machine': spec['architecture'], 'python_tag': 'cpython-' + spec['python'].replace('.', '')}}}
    def write():
        local.write_tar(target / 'artifact.tar', {'component.json': local.encoded(metadata)})
        remote.write_json(target / 'ready.json', {'sha256': remote.digest(target / 'artifact.tar')})
    write()
    assert remote.agent_artifact(tmp_path, spec)[0] == target / 'artifact.tar'
    metadata['binding']['sources'] = {'__main__.py': 'e'*64}; write()
    with pytest.raises(ValueError, match='does not match'): remote.agent_artifact(tmp_path, spec)
    with (target / 'artifact.tar').open('ab') as stream: stream.write(b'changed')
    with pytest.raises(ValueError, match='Cached Agent artifact changed'): remote.agent_artifact(tmp_path, spec)


@pytest.mark.skipif(sys.platform != 'linux', reason='Native Linux Agent delivery')
def test_selected_agent_builds_from_release_environment_and_stages_in_isolation(tmp_path, monkeypatch):
    from deployment import service_component as component
    source = tmp_path / 'release'; source.mkdir()
    names = component.inputs(local.ROOT, 'agent') + [component.CONTRACT_FILE,
        'deployment/service-agent-requirements.txt', 'deployment/service_component.py',
        'deployment/component_store.py']
    for name in names:
        target = source / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local.ROOT / name, target)
    (source / '.venv').symlink_to(Path(sys.prefix), target_is_directory=True)
    monkeypatch.setattr(remote, 'CACHE', tmp_path / 'cache')
    spec = local.agent_spec(source, platform.machine(), '.'.join(map(str, sys.version_info[:2])))
    artifact, sha = remote.agent_artifact(source, spec)
    assert remote.agent_artifact(source, spec) == (artifact, sha)
    store = component.ServiceStore('agent', root=tmp_path / 'installed', state=tmp_path / 'state')
    identifier = store.stage(artifact.read_bytes(), sha)
    assert store.metadata(identifier)['binding']['sources'] == spec['sources']
    with zipfile.ZipFile(store.releases / identifier / 'service.pyz') as archive:
        assert 'agent/capability_providers.py' in archive.namelist()
        assert not any(name.startswith('backend/') for name in archive.namelist())
    assert store.target('current') is None  # Staging never activates a service.
