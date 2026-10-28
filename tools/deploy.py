"""Prepare immutable local rollout kits; reuse content-bound checks and builds.

This tool never connects to a device, publishes Git or changes a project version.
deploy.ps1 handles the owner-authenticated transfer. The existing release builder
and installer remain authoritative for payload validation and rollback.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import UTC, datetime
from email.parser import BytesParser
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CACHE = Path('/var/tmp/3mm-deploy-cache')
EXCLUDED = {'.git', '.runtime', '.venv', 'node_modules', '__pycache__', '.codex-remote-attachments'}
NODE_BUILD_OUTPUTS = {'.tmp', '.vite', '.vite-temp', '.vue-global-types'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def identity(value):
    return digest(encoded(value))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
    temporary.write_bytes(encoded(value) + b'\n')
    temporary.replace(path)


def inventory(repo):
    from tools.dev_lab import SOURCE_ROOTS, ROOT_FILES, EXCLUDED_PARTS, EXCLUDED_SUFFIXES
    names = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard', '-z'], cwd=repo).decode().split('\0')
    result = {}
    root = repo.resolve(); parents = {}
    for name in sorted(set(names)):
        path = repo / name
        parts = Path(name).parts
        if (not parts or name not in ROOT_FILES and parts[0] not in SOURCE_ROOTS | {'frontend', 'libraries', 'docs'}
                or (EXCLUDED | EXCLUDED_PARTS).intersection(parts)
                or any(p.lower().startswith('.env') for p in parts)
                or path.suffix.lower() in EXCLUDED_SUFFIXES or not path.exists()):
            continue
        if path.parent not in parents: parents[path.parent] = path.parent.resolve().is_relative_to(root)
        if path.is_symlink() or not path.is_file() or not parents[path.parent] or '..' in parts or path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError('Unsupported source input: ' + name)
        result[name] = digest(path.read_bytes())
    return result


def production_file(name):
    parts = Path(name).parts
    if 'tests' in parts or name.endswith(('.test.ts', '.test.js', '.md')):
        return False
    if parts[0] in {'tools', 'docs', '.github'} or name in {'deploy.ps1', '.gitignore', '.gitattributes'}:
        return False
    if parts[0] == 'frontend':
        return name.startswith('frontend/compiler/')
    return True


def validation_inputs(inputs):
    return {name: value for name, value in inputs.items() if not name.endswith('.md') and not name.startswith('docs/')}


@contextmanager
def locked(cache):
    import fcntl
    cache.mkdir(parents=True, exist_ok=True)
    with (cache / 'prepare.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another preparation is running; no duplicate build started') from None
        yield


def run(command, cwd, log):
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    print('Running: ' + ' '.join(map(str, command)), flush=True)
    with log.open('w') as stream:
        result = subprocess.run(list(map(str, command)), cwd=cwd,
            env={**os.environ, 'TMPDIR': '/tmp'}, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        print(log.read_text(errors='replace')[-5000:], file=sys.stderr)
        raise ValueError('Check/build failed; see ' + str(log))
    return {'command': list(map(str, command)), 'seconds': round(time.monotonic() - started, 3), 'log': str(log), 'log_sha256': digest(log.read_bytes())}


def snapshot(repo, inputs, cache):
    key = identity(inputs)
    target = cache / 'sources' / key
    marker = target / '.snapshot.json'
    if marker.exists():
        if json.loads(marker.read_text()) != inputs:
            raise ValueError('Cached source inventory changed')
        for name, sha in inputs.items():
            if digest((target / name).read_bytes()) != sha:
                raise ValueError('Cached source changed: ' + name)
        return target
    target.mkdir(parents=True, exist_ok=False, mode=0o755)
    for name, sha in inputs.items():
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = (repo / name).read_bytes()
        if digest(data) != sha:
            raise ValueError('Source changed during snapshot: ' + name)
        destination.write_bytes(data)
        destination.chmod(0o755 if name.endswith('.sh') else 0o644)
    write_json(marker, inputs)
    return target


def environment_matches():
    try:
        from packaging.requirements import Requirement
        for name in ('backend/requirements.txt', 'backend/requirements-dev.txt',
                'deployment/application-host-requirements.txt', 'deployment/service-agent-requirements.txt'):
            for line in (ROOT / name).read_text().splitlines():
                line = line.split('#')[0].strip()
                if not line or line.startswith('-'): continue
                requirement = Requirement(line)
                if name.endswith('requirements-dev.txt') and requirement.name not in {'pytest', 'pytest-asyncio'}: continue
                if requirement.marker is None or requirement.marker.evaluate():
                    if importlib.metadata.version(requirement.name) not in requirement.specifier: return False
        return True
    except (ImportError, importlib.metadata.PackageNotFoundError): return False


def dependency_environment():
    """Use the existing local test environment; bootstrap once on a new machine."""
    if environment_matches():
        return
    candidates = [os.environ.get('THREE_MM_DEPLOY_PYTHON', ''), str(ROOT / '.venv/bin/python'),
        str(ROOT / 'backend/.venv/bin/python'), '/var/tmp/3mm-local-build/test-venv/bin/python']
    visited = os.environ.get('THREE_MM_DEPLOY_CHECKED_PYTHONS', '').split(':') + [sys.executable]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and str(Path(candidate).absolute()) not in visited:
            # Do not compare resolved Python symlinks: different venvs may share
            # one interpreter binary while providing different site-packages.
            os.environ['THREE_MM_DEPLOY_CHECKED_PYTHONS'] = ':'.join(visited)
            os.execv(candidate, [candidate, str(Path(__file__)), *sys.argv[1:]])
    key = identity({'requirements': {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in [
        ROOT / 'backend/requirements.txt', ROOT / 'backend/requirements-dev.txt',
        ROOT / 'deployment/application-host-requirements.txt', ROOT / 'deployment/service-agent-requirements.txt']},
        'python': sys.version, 'platform': platform.platform()})
    environment = CACHE / 'python' / (key + '-' + sys.implementation.cache_tag)
    python = environment / 'bin/python'
    if not (environment / 'ready.json').exists():
        if environment.exists():
            raise ValueError('Incomplete cached Python environment; inspect ' + str(environment))
        venv.EnvBuilder(with_pip=True).create(environment)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'backend/requirements-dev.txt')], check=True)
        write_json(environment / 'ready.json', {'requirements': key})
    os.execv(str(python), [str(python), str(Path(__file__)), *sys.argv[1:]])


def tree_inventory(root, exclude=()):
    return {p.relative_to(root).as_posix(): digest(p.read_bytes()) for p in sorted(root.rglob('*'))
        if p.is_file() and p.relative_to(root).parts[0] not in exclude}


def verify_tree(root, expected):
    if tree_inventory(root) != expected:
        raise ValueError('Cached output changed: ' + str(root))


def node_dependencies(source, relative, cache):
    folder = source / relative
    locks = {name: digest((folder / name).read_bytes()) for name in ('package.json', 'package-lock.json') if (folder / name).exists()}
    node = subprocess.check_output(['node', '--version'], text=True).strip()
    npm = subprocess.check_output(['npm', '--version'], text=True).strip()
    key = identity({'locks': locks, 'node': node, 'npm': npm, 'platform': platform.platform()})
    location = cache / 'node' / key
    marker = location / 'ready.json'
    if not marker.exists():
        if location.exists():
            raise ValueError('Incomplete dependency cache: ' + str(location))
        location.mkdir(parents=True)
        for name in locks:
            shutil.copyfile(folder / name, location / name)
        run(['npm', 'ci' if 'package-lock.json' in locks else 'install', '--no-audit', '--no-fund'], location, location / 'install.log')
        write_json(marker, {'key': key, 'locks': locks, 'outputs': tree_inventory(location / 'node_modules', NODE_BUILD_OUTPUTS)})
    cached = json.loads(marker.read_text())
    if cached['key'] != key or cached['locks'] != locks:
        raise ValueError('Dependency cache identity changed')
    if tree_inventory(location / 'node_modules', NODE_BUILD_OUTPUTS) != cached['outputs']:
        raise ValueError('Cached dependency files changed: ' + str(location))
    link = folder / 'node_modules'
    if not link.exists():
        link.symlink_to(location / 'node_modules', target_is_directory=True)
    elif link.resolve() != (location / 'node_modules').resolve():
        raise ValueError('Snapshot has unexpected frontend dependencies')
    return key


def frontend(source, inputs, cache):
    dependency = node_dependencies(source, 'frontend', cache)
    node_dependencies(source, 'frontend/compiler', cache)
    key = identity({'inputs': {n: sha for n, sha in inputs.items() if n.startswith('frontend/')}, 'dependencies': dependency})
    target = cache / 'frontend' / key
    marker = target / 'ready.json'
    if marker.exists():
        value = json.loads(marker.read_text())
        if value['key'] != key: raise ValueError('Frontend evidence identity changed')
        verify_tree(target / 'dist', value['outputs'])
        print('Frontend: reused checked build ' + key[:12], flush=True)
        return target / 'dist', key, value
    target.mkdir(parents=True, exist_ok=True)
    checks = [run(['npm', 'run', 'test:unit', '--', '--run'], source / 'frontend', target / 'tests.log'),
        run(['npm', 'run', 'build'], source / 'frontend', target / 'build.log')]
    shutil.copytree(source / 'frontend/dist', target / 'dist')
    value = {'key': key, 'checks': checks, 'outputs': tree_inventory(target / 'dist')}
    write_json(marker, value)
    return target / 'dist', key, value


def verify_python(source, inputs, cache, test_paths):
    from tools.checks import PYTHON_SUITES, commands, full_plan
    packages = sorted((d.metadata['Name'], d.version) for d in importlib.metadata.distributions())
    values = validation_inputs(inputs)
    environment_key = identity({'inputs': values, 'python': sys.version, 'packages': packages})
    selection = cache / 'selections' / (environment_key + '.json')
    paths = list(test_paths) if test_paths else (json.loads(selection.read_text()) if selection.exists() else [*PYTHON_SUITES, 'tools/tests'])
    if any(not p or p.startswith('-') or '..' in Path(p.split('::')[0]).parts or Path(p).is_absolute() for p in paths):
        raise ValueError('Test paths must be repository-relative pytest nodes')
    key = identity({'environment': environment_key, 'paths': paths})
    full = paths == [*PYTHON_SUITES, 'tools/tests']
    directory = cache / 'checks' / key
    marker = directory / 'ready.json'
    if marker.exists():
        value = json.loads(marker.read_text())
        if (value['key'] != key or value['inputs'] != values or any(
                digest((directory / ('checks.log' if i == 0 else f'checks-{i}.log')).read_bytes()) != item['log_sha256']
                for i, item in enumerate(value['checks']))):
            raise ValueError('Cached verification evidence changed')
        print('Checks: reused exact checked inputs ' + key[:12], flush=True)
        write_json(selection, paths)
        return value
    directory.mkdir(parents=True, exist_ok=True)
    groups = [cmd[4:] for _, cmd in commands(full_plan('local deployment'), 'python', sys.executable)] + [['tools/tests']] if full else [paths]
    evidence = []
    for i, group in enumerate(groups):
        with tempfile.TemporaryDirectory(prefix='dv-', dir='/tmp') as temporary:
            evidence.append(run([sys.executable, '-m', 'pytest', '-q', '--basetemp=' + temporary, *group], source,
                directory / ('checks.log' if i == 0 else f'checks-{i}.log')))
    value = {'key': key, 'inputs': values, 'strategy': 'full' if full else 'targeted', 'checks': evidence}
    write_json(marker, value)
    write_json(selection, paths)
    return value


def host_spec(source, architecture, python_version, image_provider):
    from deployment.application_host_component import inputs, ENTRY
    sources = {name: digest((source / name).read_bytes().replace(b'\r\n', b'\n')) for name in inputs(source)}
    sources['__main__.py'] = digest(ENTRY)
    requirements = (source / 'deployment/application-host-requirements.txt').read_text()
    if image_provider:
        requirements += '\n' + (source / 'deployment/application-media-requirements.txt').read_text()
    dependencies = dict(line.split('==') for line in requirements.splitlines() if line.strip())
    value = {'sources': sources, 'dependencies': dependencies, 'architecture': architecture,
        'python': python_version, 'image_provider': image_provider}
    value['key'] = identity(value)
    return value


def agent_spec(source, architecture, python_version):
    from deployment.service_component import inputs, ENTRY
    sources = {name: digest((source / name).read_bytes().replace(b'\r\n', b'\n')) for name in inputs(source, 'agent')}
    sources['__main__.py'] = digest(ENTRY)
    dependencies = dict(line.split('==') for line in (source / 'deployment/service-agent-requirements.txt').read_text().splitlines() if line.strip())
    value = {'sources': sources, 'dependencies': dependencies, 'architecture': architecture, 'python': python_version}
    value['key'] = identity(value)
    return value


def wheelhouse(source, spec, cache):
    key = identity({k: spec[k] for k in ('dependencies', 'architecture', 'python')})
    folder = cache / 'wheels' / key
    marker = folder / 'ready.json'
    if marker.exists():
        value = json.loads(marker.read_text())
        if digest((folder / 'host-wheels.tar.gz').read_bytes()) != value['sha256']:
            raise ValueError('Cached wheel archive changed')
        return folder / 'host-wheels.tar.gz', value
    folder.mkdir(parents=True, exist_ok=True)
    wheels = folder / 'files'; wheels.mkdir(exist_ok=True)
    requirements = folder / 'requirements.txt'
    requirements.write_text('\n'.join(name + '==' + version for name, version in sorted(spec['dependencies'].items())) + '\n')
    arch = spec['architecture']; abi = 'cp' + spec['python'].replace('.', '')
    platforms = ['manylinux_2_28_' + arch, 'manylinux_2_17_' + arch, 'manylinux2014_' + arch]
    command = [sys.executable, '-m', 'pip', 'download', '--only-binary=:all:', '--dest', str(wheels),
        '--python-version', spec['python'].replace('.', ''), '--implementation', 'cp', '--abi', abi, '--abi', 'abi3']
    for target in platforms: command += ['--platform', target]
    run([*command, '-r', requirements], source, folder / 'download.log')
    payload, locks, names = {}, [], set()
    for path in sorted(wheels.glob('*.whl')):
        with zipfile.ZipFile(path) as archive:
            metadata = BytesParser().parsebytes(archive.read(next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))))
        name, version = metadata['Name'], metadata['Version']
        expected = next((v for k, v in spec['dependencies'].items() if k.lower().replace('-', '_') == name.lower().replace('-', '_')), None)
        if version != expected or name in names:
            raise ValueError('Unexpected native build dependency')
        names.add(name); data = path.read_bytes(); payload[path.name] = data
        locks.append(name + '==' + version + ' --hash=sha256:' + digest(data))
    if len(names) != len(spec['dependencies']): raise ValueError('Incomplete native wheel closure')
    payload['requirements.lock'] = ('\n'.join(locks) + '\n').encode()
    archive = folder / 'host-wheels.tar.gz'
    write_tar(archive, payload)
    value = {'key': key, 'sha256': digest(archive.read_bytes()), 'files': {n: digest(d) for n, d in payload.items()}}
    write_json(marker, value)
    return archive, value


def write_tar(path, files):
    with tarfile.open(path, 'w:gz') as archive:
        for name, data in sorted(files.items()):
            item = tarfile.TarInfo(name); item.size = len(data); item.mode = 0o644; item.mtime = 0
            archive.addfile(item, io.BytesIO(data))


def validate_ready(folder):
    value = json.loads((folder / 'ready.json').read_text())
    for name, sha in value['files'].items():
        if Path(name).name != name or digest((folder / name).read_bytes()) != sha:
            raise ValueError('Prepared rollout payload changed: ' + name)
    if digest((folder / 'kit.tar.gz').read_bytes()) != value['kit_sha256']:
        raise ValueError('Prepared rollout kit changed')
    if digest((folder / 'checks.json').read_bytes()) != value['checks_sha256']:
        raise ValueError('Prepared verification evidence changed')
    return value


def prepare(repo, output, cache, architecture, python_version, image_provider, test_paths, with_agent=False):
    started = time.monotonic()
    inputs = inventory(repo)
    source = snapshot(repo, inputs, cache)
    # Imports use only this exact frozen source, not a later edit to the workspace.
    sys.path.insert(0, str(source))
    dist, frontend_key, frontend_proof = frontend(source, inputs, cache)
    proof = verify_python(source, inputs, cache, test_paths)
    spec = host_spec(source, architecture, python_version, image_provider)
    agent = agent_spec(source, architecture, python_version) if with_agent else None
    wheels, wheel_proof = wheelhouse(source, spec, cache)
    core_inputs = {n: sha for n, sha in inputs.items() if production_file(n)}
    runner = (source / 'tools/deploy_remote.py').read_bytes().replace(b'\r\n', b'\n')
    key = identity({'source': core_inputs, 'frontend': frontend_key, 'checks': proof['key'], 'host': spec['key'],
        'agent': agent, 'runner': digest(runner)})
    destination = output / key
    if (destination / 'ready.json').exists():
        value = validate_ready(destination)
        if inventory(repo) != inputs: raise ValueError('Workspace changed during preparation')
        return {'bundle': str(destination), 'key': key, 'reused': True, 'seconds': round(time.monotonic() - started, 3)}
    from deployment.build_release import read_source_payload, read_frontend_payload, write_release_archive
    destination.mkdir(parents=True, exist_ok=False)
    source_tar = cache / 'sources' / (key + '.tar')
    with tarfile.open(source_tar, 'w') as archive:
        for name in sorted(core_inputs):
            data = (source / name).read_bytes()
            if name.endswith('.sh'): data = data.replace(b'\r\n', b'\n')
            item = tarfile.TarInfo(name); item.size = len(data); item.mode = 0o755 if name.endswith('.sh') else 0o644
            archive.addfile(item, io.BytesIO(data))
    payload = read_source_payload(source_tar) + read_frontend_payload(dist)
    from deployment.deployment_contract import validate_deployment_contract
    contract = next(item.data for item in payload if item.name == 'deployment/deployment-contract.json')
    validate_deployment_contract(contract, {item.name for item in payload} | {'.3mm-release.json'})
    release_id = 'local-' + key[:24]
    metadata = {'release_id': release_id, 'version': (source / 'VERSION').read_text().strip(), 'architecture': architecture,
        'python': python_version, 'profile': 'full', 'deployment_key': key, 'includes_working_tree': True,
        'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
        'created_at': datetime.now(UTC).isoformat(), 'published': False}
    sha, _ = write_release_archive(destination / 'core.tar.gz', payload, metadata, epoch=0)
    shutil.copyfile(wheels, destination / 'host-wheels.tar.gz')
    (destination / 'deploy_remote.py').write_bytes(runner)
    manifest = {'schema_version': 2, 'key': key, 'release_id': release_id, 'architecture': architecture,
        'python': python_version, 'host': spec, 'agent': agent,
        'files': {'core.tar.gz': sha, 'host-wheels.tar.gz': wheel_proof['sha256'], 'deploy_remote.py': digest(runner)}}
    (destination / 'manifest.json').write_bytes(encoded(manifest) + b'\n')
    evidence = {'source_inputs': inputs, 'python': proof, 'frontend': frontend_proof, 'frontend_key': frontend_key}
    write_json(destination / 'checks.json', evidence)
    files = {name: (destination / name).read_bytes() for name in ('core.tar.gz', 'host-wheels.tar.gz', 'deploy_remote.py', 'manifest.json')}
    write_tar(destination / 'kit.tar.gz', files)
    ready = {'schema_version': 1, 'key': key, 'release_id': release_id, 'files': {n: digest(d) for n, d in files.items()},
        'kit_sha256': digest((destination / 'kit.tar.gz').read_bytes()), 'checks_sha256': digest((destination / 'checks.json').read_bytes())}
    write_json(destination / 'ready.json', ready)
    if inventory(repo) != inputs: raise ValueError('Workspace changed during preparation; new artifact is not selected')
    return {'bundle': str(destination), 'key': key, 'reused': False, 'seconds': round(time.monotonic() - started, 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'validate'])
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--cache', type=Path, default=CACHE)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--architecture', choices=['aarch64', 'x86_64'], default='aarch64')
    parser.add_argument('--python-version', choices=['3.12', '3.13', '3.14'], default='3.13')
    parser.add_argument('--without-images', action='store_true')
    parser.add_argument('--with-agent', action='store_true', help='Explicitly update the independently pinned Agent, preserving its configuration')
    parser.add_argument('--test-paths', nargs='+')
    args = parser.parse_args()
    try:
        if args.action == 'validate':
            validate_ready(args.bundle)
            if args.with_agent and not json.loads((args.bundle / 'manifest.json').read_text()).get('agent'):
                raise ValueError('Prepared bundle does not include an Agent update; prepare a new bundle with --with-agent')
            result = {'bundle': str(args.bundle), 'key': json.loads((args.bundle / 'ready.json').read_text())['key'], 'reused': True}
        else:
            dependency_environment()
            with locked(args.cache):
                result = prepare(args.repo, args.output or args.repo / '.runtime/deploy/artifacts', args.cache,
                    args.architecture, args.python_version, not args.without_images, args.test_paths, args.with_agent)
        write_json(args.result, result)
        print(json.dumps(result), flush=True)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit('Preparation refused: ' + str(error)) from None


if __name__ == '__main__': main()
