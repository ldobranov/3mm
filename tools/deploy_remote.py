"""Stdlib-only detached rollout controller shipped inside a checked local kit.

No runtime business logic. Uses the existing immutable installer and explicit
default-host publication. A repeat observes a job; it never replays failed work.
"""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import uuid
import venv

STATE = Path('/var/lib/3mm/local-deploy')
CACHE = Path('/var/cache/3mm/local-deploy')
CURRENT = Path('/opt/3mm/current')
HOST_DEFAULT = Path('/opt/3mm-application-hosts/default/current')
AGENT_CURRENT = Path('/opt/3mm-agent/current')
SHA = re.compile(r'^[0-9a-f]{64}$')
FILES = {'core.tar.gz', 'host-wheels.tar.gz', 'deploy_remote.py'}


def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, sort_keys=True); stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def regular(path, limit):
    import stat
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
        raise ValueError('Unsafe or oversized rollout file')
    return info


def manifest(value):
    if (type(value) is not dict or set(value) != {'schema_version', 'key', 'release_id', 'architecture', 'python', 'host', 'agent', 'files'}
            or type(value['schema_version']) is not int or value['schema_version'] != 2
            or type(value['key']) is not str or not SHA.fullmatch(value['key'])
            or value['release_id'] != 'local-' + value['key'][:24]
            or value['architecture'] not in {'aarch64', 'x86_64'} or value['python'] not in {'3.12', '3.13', '3.14'}
            or type(value['files']) is not dict or set(value['files']) != FILES
            or any(type(v) is not str or not SHA.fullmatch(v) for v in value['files'].values())):
        raise ValueError('Unsupported rollout manifest')
    host = value['host']
    for name, spec in (('host', host), ('agent', value['agent'])):
        if name == 'agent' and spec is None: continue
        fields = {'key', 'sources', 'dependencies', 'architecture', 'python'} | ({'image_provider'} if name == 'host' else set())
        if (type(spec) is not dict or set(spec) != fields
                or type(spec['key']) is not str or not SHA.fullmatch(spec['key'])
                or spec['architecture'] != value['architecture'] or spec['python'] != value['python']
                or name == 'host' and type(spec['image_provider']) is not bool
                or type(spec['sources']) is not dict or not 1 <= len(spec['sources']) <= 256
                or any(type(k) is not str or not k or PurePosixPath(k).is_absolute() or '..' in PurePosixPath(k).parts or '\\' in k
                    or type(v) is not str or not SHA.fullmatch(v) for k, v in spec['sources'].items())
                or type(spec['dependencies']) is not dict or not 1 <= len(spec['dependencies']) <= 32
                or any(type(k) is not str or type(v) is not str or not re.fullmatch(r'[A-Za-z0-9_.-]+', k)
                    or not re.fullmatch(r'[0-9][A-Za-z0-9.+-]*', v) for k, v in spec['dependencies'].items())):
            raise ValueError('Unsupported ' + name + ' specification')
    return value


def read_bundle(folder):
    regular(folder / 'manifest.json', 256 * 1024)
    value = manifest(json.loads((folder / 'manifest.json').read_text()))
    for name, sha in value['files'].items():
        regular(folder / name, 64 * 1024 * 1024)
        if digest(folder / name) != sha: raise ValueError('Rollout checksum mismatch: ' + name)
    return value


def unpack(archive_path, destination, *, kit=False):
    with tarfile.open(archive_path) as archive:
        members = []; names = set(); total = 0
        for member in archive:
            path = PurePosixPath(member.name)
            if (not member.isfile() or path.is_absolute() or '..' in path.parts or '\\' in member.name
                    or member.name != path.as_posix() or member.name in names or member.size > 64 * 1024 * 1024):
                raise ValueError('Unsafe rollout archive entry')
            names.add(member.name); total += member.size; members.append(member)
            if len(names) > 4096 or total > 512 * 1024 * 1024:
                raise ValueError('Rollout archive exceeds its contract')
        if len(names) > 4096 or total > 512 * 1024 * 1024 or kit and names != FILES | {'manifest.json'}:
            raise ValueError('Rollout archive exceeds its contract')
        destination.mkdir(mode=0o700)
        for member in members:
            path = destination / member.name
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, path.open('xb') as target:
                shutil.copyfileobj(source, target, 256 * 1024)


def binding_matches(binding, spec):
    return (binding['sources'] == spec['sources'] and binding['dependencies'] == spec['dependencies']
        and binding['target']['machine'] == spec['architecture']
        and binding['target']['python_tag'] == 'cpython-' + spec['python'].replace('.', ''))


def host_matches(spec, pointer=HOST_DEFAULT, *, releases=None):
    try:
        if not pointer.is_symlink(): return False
        target = pointer.resolve(strict=True)
        if target.parent != (releases or pointer.parent.parent / 'releases') or not SHA.fullmatch(target.name): return False
        info = regular(target / 'component.json', 512 * 1024)
        if info.st_uid != 0 or info.st_mode & 0o022: return False
        value = json.loads((target / 'component.json').read_text())['binding']
        return binding_matches(value, spec)
    except (OSError, ValueError, TypeError, KeyError): return False


def agent_ready(spec):
    if spec is None: return True
    journal = Path('/var/lib/3mm-agent-updates/transaction.json')
    if journal.exists() or journal.is_symlink(): return False
    if not host_matches(spec, AGENT_CURRENT, releases=AGENT_CURRENT.parent / 'releases'): return False
    # Probe validates every installed artifact byte and the actual process identity.
    try:
        command([CURRENT / '.venv/bin/python', '-m', 'deployment.service_component', 'agent', 'probe'], source=CURRENT, quiet=True)
        return True
    except (OSError, ValueError, subprocess.SubprocessError): return False


def current_metadata():
    regular(CURRENT / '.3mm-release.json', 64 * 1024)
    return json.loads((CURRENT / '.3mm-release.json').read_text())


def ready():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8887/ready', timeout=5) as response:
            return response.status == 200
    except OSError: return False


def unit_name(key): return '3mm-deploy-' + key[:24] + '.service'


@contextmanager
def dispatch_lock():
    import fcntl
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    if STATE.is_symlink() or STATE.stat().st_uid != 0 or STATE.stat().st_mode & 0o022:
        raise ValueError('Unsafe rollout state directory')
    with (STATE / 'dispatch.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def decision(record, value, installed, healthy, native_matches):
    """Pure dispatch policy; uncertainty is never converted into another install."""
    same = installed.get('deployment_key') == value['key']
    if record is not None and record.get('state') in {'dispatching', 'running'}:
        return 'observe'
    if record is not None and record.get('state') != 'succeeded': return 'inspect'
    if same and healthy and native_matches:
        return 'already_ready'
    if record is not None:
        return 'inspect'
    if same: return 'inspect'
    return 'start'


def start(kit, expected):
    if not SHA.fullmatch(expected): raise ValueError('Invalid kit digest')
    regular(kit, 128 * 1024 * 1024)
    if digest(kit) != expected: raise ValueError('Kit checksum mismatch')
    with dispatch_lock():
        # Verify a private snapshot, not a user-writable path between reads.
        frozen = STATE / ('.kit-' + uuid.uuid4().hex)
        fd = os.open(kit, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            with os.fdopen(fd, 'rb') as source, frozen.open('xb') as target:
                shutil.copyfileobj(source, target, 256 * 1024)
            if digest(frozen) != expected: raise ValueError('Kit changed during transfer snapshot')
            return dispatch(frozen)
        finally:
            frozen.unlink(missing_ok=True)


def dispatch(kit):
    incoming = STATE / ('.incoming-' + uuid.uuid4().hex)
    try:
        return dispatch_snapshot(kit, incoming)
    finally:
        # Only this invocation's private, randomly named temporary stage.
        if incoming.exists(): shutil.rmtree(incoming)


def dispatch_snapshot(kit, incoming):
    unpack(kit, incoming, kit=True)
    value = read_bundle(incoming); key = value['key']; target = STATE / key
    installed = current_metadata()
    if installed.get('profile') != 'full' or platform.machine() != value['architecture'] or '.'.join(map(str, sys.version_info[:2])) != value['python']:
        raise ValueError('Installed profile/architecture/Python does not match this kit')
    record_path = target / 'status.json'
    record = json.loads(record_path.read_text()) if record_path.exists() else None
    result = decision(record, value, installed, ready(), host_matches(value['host']) and agent_ready(value['agent']))
    if result == 'already_ready':
        return {'state': 'succeeded', 'result': result, 'key': key, 'unit': unit_name(key)}
    if result == 'observe': return record
    if result == 'inspect': raise ValueError('Previous rollout needs inspection; use Status/Logs, no install was replayed')
    for status in STATE.glob('*/status.json'):
        other = json.loads(status.read_text())
        if other.get('state') in {'dispatching', 'running'}:
            raise ValueError('Another rollout is active or uncertain; inspect its status first')
    if target.exists(): raise ValueError('Existing rollout stage requires inspection')
    incoming.rename(target)
    record = {'key': key, 'release_id': value['release_id'], 'state': 'dispatching', 'phase': 'dispatch', 'unit': unit_name(key), 'timings': {}}
    write_json(record_path, record)
    subprocess.run(['systemd-run', '--unit=' + unit_name(key).removesuffix('.service'), '--collect', '--no-block',
        '--property=Type=exec', '--property=RuntimeMaxSec=90min', '--property=UMask=0022',
        sys.executable, str(target / 'deploy_remote.py'), 'work', '--key', key], check=True)
    return record


def frontend_origin():
    value = ''
    for line in Path('/etc/3mm/3mm.env').read_text().splitlines():
        name, separator, text = line.partition('=')
        if separator and name.strip() == 'FRONTEND_URL': value = text.strip()
    if len(value) > 1 and value[0] in {'"', "'"} and value[-1] == value[0]: value = value[1:-1]
    if not value: raise ValueError('Installed frontend URL is missing')
    return value


def command(args, *, source=None, quiet=False):
    environment = dict(os.environ)
    environment.pop('THREE_MM_NETWORK_BACKEND', None)
    if source is not None: environment['PYTHONPATH'] = str(source)
    subprocess.run(list(map(str, args)), env=environment, check=True, stdout=subprocess.DEVNULL if quiet else None)


def native_artifact(folder, source, value):
    spec = value['host']; destination = CACHE / 'hosts' / spec['key']
    marker = destination / 'ready.json'
    if marker.exists():
        record = json.loads(marker.read_text())
        regular(destination / 'artifact.tar', 64 * 1024 * 1024)
        if digest(destination / 'artifact.tar') != record['sha256']:
            raise ValueError('Cached native host changed')
        return destination / 'artifact.tar', record['sha256']
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = destination.with_name('.build-' + uuid.uuid4().hex); stage.mkdir(mode=0o700)
    unpack(folder / 'host-wheels.tar.gz', stage / 'wheels')
    venv.EnvBuilder(with_pip=True).create(stage / 'builder')
    python = stage / 'builder/bin/python'
    command([python, '-m', 'pip', 'install', '--no-index', '--only-binary=:all:', '--find-links=' + str(stage / 'wheels'),
        '--require-hashes', '-r', stage / 'wheels/requirements.lock'])
    args = [python, '-m', 'deployment.application_host_component', 'build', '--source', source, '--output', stage / 'artifact.tar']
    if spec['image_provider']: args.append('--image-provider')
    command(args, source=source)
    if spec['image_provider']:
        command([python, '-c', "from PIL import Image; import io; image=Image.new('RGB',(2,2)); output=io.BytesIO(); image.save(output,format='WEBP'); Image.open(io.BytesIO(output.getvalue())).load()"])
    sha = digest(stage / 'artifact.tar')
    write_json(stage / 'ready.json', {'sha256': sha, 'host_key': spec['key']})
    stage.rename(destination)
    return destination / 'artifact.tar', sha


def agent_artifact(source, spec):
    destination = CACHE / 'agents' / spec['key']
    marker = destination / 'ready.json'
    if marker.exists():
        record = json.loads(marker.read_text())
        regular(destination / 'artifact.tar', 128 * 1024 * 1024)
        if digest(destination / 'artifact.tar') != record['sha256']: raise ValueError('Cached Agent artifact changed')
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage = destination.with_name('.build-' + uuid.uuid4().hex); stage.mkdir(mode=0o700)
        # The normal installer has already installed the exact service dependency
        # constraints in the new release venv. No second download/build environment.
        command([source / '.venv/bin/python', '-m', 'deployment.service_component', 'agent', 'build',
            '--source', source, '--output', stage / 'artifact.tar'], source=source, quiet=True)
        write_json(stage / 'ready.json', {'sha256': digest(stage / 'artifact.tar')})
        stage.rename(destination)
    with tarfile.open(destination / 'artifact.tar') as archive:
        entry = archive.getmember('component.json')
        if not entry.isfile() or entry.size > 512 * 1024: raise ValueError('Invalid Agent metadata')
        metadata = json.loads(archive.extractfile(entry).read())
    if metadata['component'] != 'agent' or not binding_matches(metadata['binding'], spec):
        raise ValueError('Built Agent does not match the checked source/dependencies/target')
    return destination / 'artifact.tar', digest(destination / 'artifact.tar')


def work(key):
    folder = STATE / key
    value = read_bundle(folder); status_path = folder / 'status.json'
    with dispatch_lock():
        status = json.loads(status_path.read_text())
        if status['state'] != 'dispatching': raise ValueError('This job was already consumed; no replay')
        status['state'] = 'running'; write_json(status_path, status)
    def phase(name, action):
        status['phase'] = name; write_json(status_path, status)
        print('==> ' + name, flush=True); started = time.monotonic()
        result = action()
        status['timings'][name] = round(time.monotonic() - started, 3); write_json(status_path, status)
        return result
    try:
        origin = frontend_origin()
        source = folder / 'source'
        phase('validate and extract', lambda: unpack(folder / 'core.tar.gz', source))
        installed = json.loads((source / '.3mm-release.json').read_text())
        if installed.get('deployment_key') != key or installed.get('profile') != 'full': raise ValueError('Core metadata does not match kit')
        reuse = host_matches(value['host'])
        native = None if reuse else phase('prepare native host', lambda: native_artifact(folder, source, value))
        if reuse: print('Native host: unchanged, reused installed default.', flush=True)
        # The normal installer consumes its input archive; retain the checked kit.
        install_archive = folder / 'install-core.tar.gz'
        shutil.copyfile(folder / 'core.tar.gz', install_archive)
        phase('install Core', lambda: command(['bash', source / 'deployment/install-systemd.sh', install_archive,
            value['release_id'], origin, '', value['files']['core.tar.gz'], 'full']))
        if current_metadata().get('deployment_key') != key: raise ValueError('Core did not retain expected release')
        if native is not None:
            release = CURRENT.resolve(strict=True)
            phase('publish native host', lambda: command([release / '.venv/bin/python', '-m', 'deployment.application_host_component',
                'publish-default', '--artifact', native[0], '--sha256', native[1]], source=release))
        if value['agent'] is not None:
            release = CURRENT.resolve(strict=True)
            artifact = phase('prepare Agent', lambda: agent_artifact(release, value['agent']))
            phase('update Agent', lambda: command([release / '.venv/bin/python', '-m', 'deployment.service_component',
                'agent', 'update', '--artifact', artifact[0], '--sha256', artifact[1]], source=release))
        if not ready() or not host_matches(value['host']) or not agent_ready(value['agent']):
            raise ValueError('Final Core/host/selected Agent readiness was not confirmed')
        status.update(state='succeeded', phase='ready'); write_json(status_path, status)
        print('3mm update succeeded', flush=True)
    except BaseException as error:
        status.update(state='failed', error_type=type(error).__name__)
        write_json(status_path, status)
        print('3mm update failed; inspect Status/Logs before another action.', flush=True)
        raise


def follow(key):
    """The viewer may disconnect; the systemd-owned worker continues."""
    process = subprocess.Popen(['journalctl', '--no-pager', '-n', '100', '-f', '-u', unit_name(key)])
    try:
        while True:
            status = json.loads((STATE / key / 'status.json').read_text())
            if status['state'] in {'succeeded', 'failed'}:
                time.sleep(1)  # Let journalctl flush the last worker messages.
                print(json.dumps(status), flush=True)
                return 0 if status['state'] == 'succeeded' else 1
            time.sleep(2)
    finally:
        process.terminate(); process.wait()


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'work', 'status', 'logs'])
    parser.add_argument('--kit', type=Path); parser.add_argument('--sha256'); parser.add_argument('--key')
    parser.add_argument('--follow', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0: raise SystemExit('Use sudo for the rollout controller')
    if args.action == 'start':
        result = start(args.kit, args.sha256)
        print(json.dumps(result), flush=True)
        if args.follow and result['state'] in {'dispatching', 'running'}:
            raise SystemExit(follow(result['key']))
        return
    if not args.key or not SHA.fullmatch(args.key): raise SystemExit('Invalid rollout key')
    if args.action == 'work': work(args.key)
    elif args.action == 'status':
        path = STATE / args.key / 'status.json'
        print(path.read_text() if path.exists() else json.dumps({'state': 'not_started', 'key': args.key}))
    else: os.execvp('journalctl', ['journalctl', '--no-pager', '-n', '100', '-f', '-u', unit_name(args.key)])


if __name__ == '__main__': main()
