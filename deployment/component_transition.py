"""Installer-owned, journaled transition between immutable component layouts.

This is not an application migrator or an independent component update. The
installer already owns the release lock and stops services before switching.
Previous artifacts and their exact pointer pairs remain available for recovery.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid

sys.dont_write_bytecode = True
OWNER = 0
RELEASES = Path('/opt/3mm/releases')
STATE = Path('/var/lib/3mm-component-transitions')
HOSTS = Path('/opt/3mm-application-hosts')
HOST_STATE = Path('/var/lib/3mm-application-host-updates')
MAX_INSTANCES = 256
MAX_JOURNAL = 1024 * 1024
MAX_ATTEMPTS = 8
PHASES = {'prepared', 'switching', 'switched', 'verified', 'restoring', 'restored', 'resumed', 'committed'}
SHA = re.compile(r'[0-9a-f]{64}')
INSTANCE = re.compile(r'[0-9a-f]{24}')
SERVICE_ROOTS = {
    name: (Path('/opt/3mm-' + name), Path('/var/lib/3mm-' + name + '-updates'))
    for name in ('agent', 'public-web', 'session-worker', 'host-session-worker', 'session-node', 'session-relay')
}
RUNTIME_ROOTS = {
    'platform-runtime': (Path('/opt/3mm-platform-runtime'), Path('/var/lib/3mm-platform-updates')),
    'connector-worker': (Path('/opt/3mm-connector-worker'), Path('/var/lib/3mm-connector-updates')),
}
_CONTEXT = {}
_ERROR_REASONS = {
    'unsafe_path': ('Untrusted transition directory', 'Untrusted transition file', 'Transition file changed',
                    'Untrusted component pointer', 'Component pointer escapes its immutable releases'),
    'source_untrusted': ('Transition source must be an immutable installed release', 'Transition source identity differs',
                         'Platform source contains a symlink', 'Previous interpreter is untrusted'),
    'inspection_bound_exceeded': ('Transition file exceeds its bound', 'Platform source inspection exceeds its bound',
                                  'Component unit inspection exceeds bound'),
    'component_invalid': ('Invalid transition component', 'Unknown transition component', 'Component outside transition profile'),
    'profile_unsupported': ('Unsupported transition profile',),
    'inventory_unsupported': ('Host instance inventory is unsupported',),
    'pending_component_operation': ('Resolve the pending component operation before installation',),
    'component_store_incomplete': ('Installed component store is incomplete',),
    'previous_adapter_refused': ('Selected previous release adapter refused the component',),
    'previous_adapter_response_invalid': ('Previous adapter returned an invalid inspection',),
    'previous_source_required': ('Installed component has no trusted transition source',),
    'service_state_unconfirmed': ('Installed component service state is unconfirmed',),
    'readiness_failed': ('Transitioned component is not active', 'Transitioned component readiness deadline expired',
                         'Transitioned component identity file is untrusted', 'Transitioned component identity exceeds bound',
                         'Component PID is unavailable', 'Transitioned component process identity differs',
                         'Transitioned component stopped during readiness'),
    'journal_too_large': ('Transition journal exceeds its bound',),
    'journal_invalid': ('Invalid transition journal', 'Invalid component transition record', 'Invalid component proof',
                        'Transition change flag differs', 'Duplicate or unsorted transition components'),
    'original_artifact_changed': ('Original component artifact changed since preparation',),
    'component_pins_changed': ('Component pins changed after preparation', 'Component pins changed during staging',
                              'Component pins changed before transition', 'Component pins changed before verification',
                              'Component pins changed before commit', 'Unrelated component pins appeared; recovery is fenced'),
    'recovery_required': ('Previous transition needs explicit recovery; no install was replayed',
                          'Transition switch already consumed; inspect recovery first',
                          'Committed transition requires separate reviewed rollback'),
    'phase_conflict': ('Transition is not ready for health verification', 'Transition was not verified'),
    'installer_lock_required': ('Transition requires the inherited installer release lock',),
    'installer_principal_required': ('Component transition requires the installer principal',),
    'adapter_request_invalid': ('Invalid fixed adapter request', 'Inspection cannot start a component'),
    'completed_rollback_retry_required': ('Completed rollback requires explicit retry approval',),
    'retry_evidence_limit': ('Completed rollback attempt evidence exceeds its bound',),
    'host_dependency_target_mismatch': ('Borrowed host dependencies do not match the target interpreter and platform',),
}
_REASON_CODES = {reason: code for code, reasons in _ERROR_REASONS.items() for reason in reasons}


class TransitionError(ValueError):
    """A static installer refusal; exception text is never an output channel."""

    def __init__(self, reason):
        self.code = _REASON_CODES.get(reason, 'transition_refused')
        super().__init__(reason if reason in _REASON_CODES else 'Component transition refused')


def failure_result(error):
    code = (error.code if isinstance(error, TransitionError) else
            'io_unavailable' if isinstance(error, OSError) else
            'previous_adapter_refused' if isinstance(error, subprocess.SubprocessError) else 'transition_refused')
    value = {'status': 'refused', 'error_code': code}
    if _CONTEXT.get('action') in {'prepare', 'switch', 'verify', 'restore', 'resume', 'commit', '_worker'}:
        value['action'] = _CONTEXT['action']
    if 'entry' in _CONTEXT:
        # Context is added only after the closed fixed-root entry validation.
        value['entry'] = _CONTEXT['entry']
    return value


def require(condition, reason):
    if not condition:
        raise TransitionError(reason)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def exists(path):
    return path.exists() or path.is_symlink()


def trusted_directory(path):
    for item in (path, *path.parents):
        info = item.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == OWNER and not info.st_mode & 0o022,
                'Untrusted transition directory')


def read_file(path, limit):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == OWNER and info.st_nlink == 1
            and not info.st_mode & 0o022 and info.st_size <= limit, 'Untrusted transition file')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        require((opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino), 'Transition file changed')
        data = stream.read(limit + 1)
    require(len(data) <= limit, 'Transition file exceeds its bound')
    return data


def trusted_source(source):
    source = Path(source)
    require(source.parent == RELEASES and source.resolve(strict=True) == source
            and re.fullmatch(r'[A-Za-z0-9._-]{1,128}', source.name) is not None,
            'Transition source must be an immutable installed release')
    trusted_directory(source)
    metadata = json.loads(read_file(source / '.3mm-release.json', 65536))
    require(metadata.get('release_id') == source.name, 'Transition source identity differs')
    # Only platform source is imported by an inspector, never application wheels.
    count = 0
    for name in ('deployment', 'components', 'packages', 'three_mm_runtime',
                 'three_mm_protocol', 'three_mm_platform_runtime', 'three_mm_platform_wire',
                 'three_mm_application_sdk'):
        folder = source / name
        if not exists(folder):
            continue
        for directory, folders, files in os.walk(folder, followlinks=False):
            trusted_directory(Path(directory))
            for child in folders:
                require(not (Path(directory) / child).is_symlink(), 'Platform source contains a symlink')
            for child in files:
                count += 1
                require(count <= 8192, 'Platform source inspection exceeds its bound')
                read_file(Path(directory) / child, 16 * 1024 * 1024)
    python = source / '.venv/bin/python'
    trusted_directory(python.parent)
    target = python.resolve(strict=True)
    trusted_directory(target.parent)
    info = target.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == OWNER and not info.st_mode & 0o022
            and os.access(python, os.X_OK), 'Previous interpreter is untrusted')
    return source


@dataclass(frozen=True)
class Entry:
    key: str
    kind: str
    name: str
    root: Path
    state: Path
    releases: Path


def entry(key):
    require(type(key) is str, 'Invalid transition component')
    kind, separator, name = key.partition(':')
    require(separator and len(key) <= 64, 'Invalid transition component')
    if kind == 'service' and name in SERVICE_ROOTS:
        root, state = SERVICE_ROOTS[name]
        _CONTEXT['entry'] = key
        return Entry(key, kind, name, root, state, root / 'releases')
    if kind == 'runtime' and name in RUNTIME_ROOTS:
        root, state = RUNTIME_ROOTS[name]
        _CONTEXT['entry'] = key
        return Entry(key, kind, name, root, state, root / 'releases')
    require(kind == 'host' and (name == 'default' or INSTANCE.fullmatch(name)), 'Unknown transition component')
    root = HOSTS / 'default' if name == 'default' else HOSTS / 'instances' / name
    _CONTEXT['entry'] = key
    return Entry(key, kind, name, root, HOST_STATE / name, HOSTS / 'releases')


def discover(profile):
    require(profile in {'full', 'node'}, 'Unsupported transition profile')
    keys = ['service:agent']
    if profile == 'full':
        keys += ['service:' + name for name in SERVICE_ROOTS if name != 'agent']
        keys += ['runtime:' + name for name in RUNTIME_ROOTS]
        keys.append('host:default')
        instances = HOSTS / 'instances'
        if exists(instances):
            trusted_directory(instances)
            with os.scandir(instances) as listing:
                for index, item in enumerate(listing):
                    require(index < MAX_INSTANCES and INSTANCE.fullmatch(item.name)
                            and item.is_dir(follow_symlinks=False), 'Host instance inventory is unsupported')
                    keys.append('host:' + item.name)
    return [entry(key) for key in sorted(keys)]


def store_for(item):
    if item.kind == 'service':
        from deployment.service_component import ServiceStore
        return ServiceStore(item.name, root=item.root, state=item.state, create=False)
    if item.kind == 'runtime':
        from deployment.platform_runtime_component import RuntimeStore
        return RuntimeStore(item.root, item.state, create=False)
    from deployment.application_host_component import HostStore
    return HostStore(item.root, item.state, item.releases, create=False)


def pointer(item, name):
    path = item.root / name
    if not exists(path):
        return None
    info = path.lstat()
    require(stat.S_ISLNK(info.st_mode) and info.st_uid == OWNER, 'Untrusted component pointer')
    target = path.resolve(strict=True)
    require(target.parent == item.releases.resolve(strict=True) and SHA.fullmatch(target.name),
            'Component pointer escapes its immutable releases')
    trusted_directory(target)
    return target.name


def pair(item):
    return {name: pointer(item, name) for name in ('current', 'previous')}


def inspect_store(item):
    _CONTEXT['entry'] = item.key
    if not exists(item.root) and not exists(item.state):
        return None
    for directory in (item.root, item.state, item.releases):
        trusted_directory(directory)
    journal = item.state / 'transaction.json'
    require(not exists(journal), 'Resolve the pending component operation before installation')
    value = pair(item)
    require(value['current'] is not None, 'Installed component store is incomplete')
    return value


def proof(metadata):
    binding = metadata.get('binding', {})
    dependencies = binding.get('dependencies', {})
    return {'metadata_sha256': digest(encoded(metadata)),
            'image_provider': any(name.lower() == 'pillow' for name in dependencies)}


def _limit_worker_output():
    import resource
    resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))


def worker(source, operation, key, identifier, *, start=False):
    # Execute fixed trusted adapter code using the selected release's imports.
    # The component archive/wheel is data to the inspector, never executed code.
    helper = Path(__file__).resolve()
    arguments = [str(source / '.venv/bin/python'), '-I', '-B', str(helper), '_worker',
                 '--source', str(source), '--operation', operation, '--entry', key, '--build', identifier]
    if start:
        arguments.append('--start')
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(arguments, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'},
            stdout=output, stderr=subprocess.DEVNULL, timeout=240 if operation == 'health' else 60,
            check=False, preexec_fn=_limit_worker_output, pass_fds=(9,) if operation == 'health' else ())
        require(result.returncode == 0 and output.tell() <= 65536,
                'Selected previous release adapter refused the component')
        output.seek(0)
        try:
            value = json.loads(output.read(65537))
        except (ValueError, UnicodeError):
            raise TransitionError('Previous adapter returned an invalid inspection') from None
    require(type(value) is dict and set(value) == {'metadata_sha256', 'image_provider'}
            and type(value['metadata_sha256']) is str and SHA.fullmatch(value['metadata_sha256'])
            and type(value['image_provider']) is bool,
            'Previous adapter returned an invalid inspection')
    return value


def classify(item, identifier, previous_source):
    try:
        result = proof(store_for(item).metadata(identifier))
        return {**result, 'adapter': 'target'}
    except (OSError, ValueError, KeyError, TypeError):
        require(previous_source is not None, 'Installed component has no trusted transition source')
    result = worker(previous_source, 'inspect', item.key, identifier)
    return {**result, 'adapter': 'previous'}


def active(item):
    if item.kind == 'host' and item.name == 'default':
        return False
    controller = control(item)
    result = subprocess.run(['/usr/bin/systemctl', 'is-active', '--quiet', controller.unit],
                            timeout=10, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode == 4:
        # A failed fresh install may have removed its units while retaining
        # immutable artifacts. Only prove actual absence; never hide DBus errors.
        inspected = subprocess.run(['/usr/bin/systemctl', 'show', controller.unit,
            '--property=LoadState,ActiveState,MainPID'], timeout=10, check=False,
            capture_output=True, text=True)
        require(len(inspected.stdout) <= 1024, 'Component unit inspection exceeds bound')
        fields = dict(line.split('=', 1) for line in inspected.stdout.splitlines() if '=' in line)
        require(inspected.returncode in {0, 1, 4} and fields.get('LoadState') == 'not-found'
                and fields.get('ActiveState') == 'inactive' and fields.get('MainPID', '0') == '0',
                'Installed component service state is unconfirmed')
        return False
    require(result.returncode in {0, 3}, 'Installed component service state is unconfirmed')
    return result.returncode == 0


def control(item):
    if item.kind == 'service':
        from deployment.service_component import ServiceControl
        return ServiceControl(item.name)
    if item.kind == 'runtime':
        from deployment.platform_runtime_component import SystemdRuntime
        return SystemdRuntime('3mm-' + item.name + '.service')
    from deployment.application_host_component import ApplicationControl
    return ApplicationControl(item.name)


def verify_component(item, identifier, *, start=False):
    if item.kind == 'host' and item.name == 'default':
        store_for(item).metadata(identifier)
        return
    controller = control(item)
    if start and not active(item):
        controller.start()
    if item.kind == 'service':
        service_readiness(item, controller, identifier)
    elif item.kind == 'runtime':
        from deployment.platform_runtime_component import runtime_health, connector_health
        (runtime_health if item.name == 'platform-runtime' else connector_health)(identifier)
    else:
        from deployment.application_host_component import health
        health(item.name, identifier)


def service_readiness(item, controller, identifier):
    """Readiness without independent-update Core-continuity requirements.

    A Full installation may itself have Node role and no local Core. The
    installer is deliberately replacing Core, so independent health's final
    fingerprint is inapplicable; process/artifact identity still must match.
    """
    from deployment import service_component as adapter

    store_for(item).metadata(identifier)
    require(controller.active(), 'Transitioned component is not active')
    if item.name in {'session-worker', 'host-session-worker'}:
        return  # Exact artifact and active per-connection socket; no shell opened.
    deadline = time.monotonic() + adapter.startup_probe_seconds(item.name)
    while True:
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'Transitioned component readiness deadline expired')
        try:
            if item.name in {'agent', 'public-web'}:
                url = ('http://127.0.0.1:8890/component-health' if item.name == 'agent'
                       else 'http://127.0.0.1:8081/__3mm_component__/health')
                value = adapter._http_identity(url, timeout=min(2, remaining))
                unit = '3mm-public-web.service' if item.name == 'public-web' else controller.unit
            else:
                import pwd
                path = Path('/run/3mm-' + item.name) / ('support.json' if item.name == 'session-node' else 'identity.json')
                uid = pwd.getpwnam(adapter.ROLES[item.name][2]).pw_uid
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
                with os.fdopen(fd, 'rb') as stream:
                    info = os.fstat(stream.fileno())
                    require(stat.S_ISREG(info.st_mode) and info.st_uid == uid and info.st_nlink == 1
                            and not info.st_mode & 0o022 and 1 <= info.st_size <= 4096,
                            'Transitioned component identity file is untrusted')
                    raw = stream.read(4097)
                require(len(raw) <= 4096, 'Transitioned component identity exceeds bound')
                value = json.loads(raw)
                unit = controller.unit
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'Transitioned component readiness deadline expired')
            result = subprocess.run(['/usr/bin/systemctl', 'show', unit, '--property=MainPID', '--value'],
                                    check=True, capture_output=True, text=True, timeout=min(5, remaining))
            require(len(result.stdout) <= 32 and result.stdout.strip().isdigit(), 'Component PID is unavailable')
            pid = int(result.stdout.strip())
            if item.name in {'agent', 'public-web'}:
                require(value == {'component': item.name, 'build_id': identifier, 'pid': pid} and pid > 0,
                        'Transitioned component process identity differs')
            else:
                require(type(value) is dict and value.get('component') == item.name
                        and value.get('build_id') == identifier and type(value.get('pid')) is int
                        and value['pid'] == pid and pid > 0 and type(value.get('expires_at')) in {int, float}
                        and 0 < value['expires_at'] - time.time() <= 12,
                        'Transitioned component process identity differs')
            require(time.monotonic() < deadline, 'Transitioned component readiness deadline expired')
            return
        except (OSError, ValueError):
            require(controller.active(), 'Transitioned component stopped during readiness')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(0.1, remaining))


def stage(item, source, current, image_provider, built, *, metadata_sha256):
    cache_key = (item.kind, item.name if item.kind == 'service' else '', image_provider)
    if cache_key not in built:
        if item.kind == 'service':
            from deployment.service_component import build_component
            blob, _ = build_component(source, item.name)
        elif item.kind == 'runtime':
            from deployment.platform_runtime_component import build_component
            blob, _ = build_component(source)
        else:
            from deployment.application_host_component import build_component, target_identity
            vendor = item.releases / current / 'vendor'
            # Missing optional dependencies may come only from the already
            # validated old vendor, after the target venv. Exact locks still win.
            if image_provider:
                metadata = json.loads(read_file(item.releases / current / 'component.json', 512 * 1024))
                require(digest(encoded(metadata)) == metadata_sha256
                        and metadata.get('binding', {}).get('target') == target_identity(),
                        'Borrowed host dependencies do not match the target interpreter and platform')
                trusted_directory(vendor)
                sys.path.append(str(vendor))
            try:
                blob, _ = build_component(source, image_provider=image_provider)
            finally:
                if image_provider:
                    sys.path.remove(str(vendor))
        built[cache_key] = blob
    blob = built[cache_key]
    return store_for(item).stage(blob, digest(blob))


def fsync(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save(path, value):
    data = encoded(value)
    require(len(data) <= MAX_JOURNAL, 'Transition journal exceeds its bound')
    temporary = path.with_name('.transition-' + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fsync(path.parent)
    finally:
        if exists(temporary):
            temporary.unlink()


def journal_path(source, *, create=False):
    path = STATE / source.name
    if create:
        trusted_directory(STATE.parent)
        STATE.mkdir(mode=0o700, exist_ok=True)
        trusted_directory(STATE)
        path.mkdir(mode=0o700, exist_ok=True)
    trusted_directory(path)
    return path / 'transition.json'


def valid_pair(value):
    return (type(value) is dict and set(value) == {'current', 'previous'}
            and all(item is None or type(item) is str and SHA.fullmatch(item) for item in value.values()))


def load(path, source, previous_source, profile):
    value = json.loads(read_file(path, MAX_JOURNAL))
    require(type(value) is dict and set(value) == {
        'schema_version', 'source', 'previous_source', 'profile', 'phase', 'entries'}
        and type(value['schema_version']) is int and value['schema_version'] == 1
        and value['source'] == str(source) and value['previous_source'] == str(previous_source or '')
        and value['profile'] == profile and value['phase'] in PHASES
        and type(value['entries']) is list and len(value['entries']) <= MAX_INSTANCES + 10,
        'Invalid transition journal')
    keys = []
    for record in value['entries']:
        require(type(record) is dict and set(record) == {'key', 'old', 'new', 'proofs', 'was_active', 'changed'}
                and type(record['key']) is str and valid_pair(record['old']) and valid_pair(record['new'])
                and record['old']['current'] is not None and record['new']['current'] is not None
                and type(record['was_active']) is bool and type(record['changed']) is bool
                and type(record['proofs']) is dict
                and set(record['proofs']) == set(filter(None, record['old'].values())), 'Invalid component transition record')
        item = entry(record['key'])
        require(profile == 'full' or item.key == 'service:agent', 'Component outside transition profile')
        for identifier, evidence in record['proofs'].items():
            require(SHA.fullmatch(identifier) and type(evidence) is dict and set(evidence) == {
                'metadata_sha256', 'image_provider', 'adapter'} and SHA.fullmatch(evidence['metadata_sha256'])
                and type(evidence['image_provider']) is bool and evidence['adapter'] in {'target', 'previous'},
                'Invalid component proof')
        require(record['changed'] == (record['old'] != record['new']), 'Transition change flag differs')
        keys.append(item.key)
    require(keys == sorted(set(keys)), 'Duplicate or unsorted transition components')
    return value


def check_original(record, previous_source):
    item = entry(record['key'])
    inspect_store(item)
    for identifier, expected in record['proofs'].items():
        actual = (worker(previous_source, 'inspect', item.key, identifier)
                  if expected['adapter'] == 'previous' else proof(store_for(item).metadata(identifier)))
        require(actual == {key: expected[key] for key in ('metadata_sha256', 'image_provider')},
                'Original component artifact changed since preparation')


def prepare(source, previous_source, profile, *, retry_rolled_back=False):
    _CONTEXT.clear()
    _CONTEXT['action'] = 'prepare'
    source = trusted_source(source)
    previous_source = trusted_source(previous_source) if previous_source else None
    path = STATE / source.name / 'transition.json'
    for directory in (STATE, path.parent):
        if exists(directory):
            trusted_directory(directory)
    if exists(path):
        value = load(path, source, previous_source, profile)
        require(value['phase'] in {'prepared', 'resumed'}, 'Previous transition needs explicit recovery; no install was replayed')
        if value['phase'] == 'resumed':
            require(retry_rolled_back, 'Completed rollback requires explicit retry approval')
        for record in value['entries']:
            check_original(record, previous_source)
            require(pair(entry(record['key'])) == record['old'], 'Component pins changed after preparation')
            if value['phase'] == 'prepared':
                for identifier in set(filter(None, record['new'].values())):
                    store_for(entry(record['key'])).metadata(identifier)
        if value['phase'] == 'prepared':
            return value
        # Only a proved completed rollback can become a new attempt. Keep its
        # exact preimages and outcome before overwriting the active journal;
        # interruption at any earlier phase is never treated as a retry.
        attempt = path.with_name('rolled-back-' + digest(encoded(value)) + '.json')
        if exists(attempt):
            require(read_file(attempt, MAX_JOURNAL) == encoded(value), 'Invalid transition journal')
        else:
            require(sum(1 for _ in path.parent.glob('rolled-back-*.json')) < MAX_ATTEMPTS,
                    'Completed rollback attempt evidence exceeds its bound')
            save(attempt, value)
    records = []
    built = {}
    # Finish every read-side proof before staging any replacement artifact.
    for item in discover(profile):
        old = inspect_store(item)
        if old is None:
            continue
        evidence = {identifier: classify(item, identifier, previous_source)
                    for identifier in sorted(set(filter(None, old.values())))}
        records.append({'key': item.key, 'old': old, 'new': dict(old), 'proofs': evidence,
                        'was_active': active(item), 'changed': False})
    for record in records:
        item = entry(record['key'])
        old = record['old']
        if record['proofs'][old['current']]['adapter'] == 'previous':
            image = record['proofs'][old['current']]['image_provider']
            record['new']['current'] = stage(item, source, old['current'], image, built,
                metadata_sha256=record['proofs'][old['current']]['metadata_sha256'])
        if old['previous'] is not None and record['proofs'][old['previous']]['adapter'] == 'previous':
            record['new']['previous'] = None  # Old pair remains in the protected coordinated rollback journal.
        record['changed'] = old != record['new']
        require(pair(item) == old, 'Component pins changed during staging')
    value = {'schema_version': 1, 'source': str(source), 'previous_source': str(previous_source or ''),
             'profile': profile, 'phase': 'prepared', 'entries': records}
    journal_path(source, create=True)
    save(path, value)
    return value


def set_pointer(item, name, identifier):
    path = item.root / name
    if identifier is None:
        if exists(path):
            path.unlink()
            fsync(item.root)
        return
    target = item.releases / identifier
    trusted_directory(target)
    temporary = item.root / ('.transition-' + uuid.uuid4().hex)
    try:
        temporary.symlink_to(target, target_is_directory=True)
        os.replace(temporary, path)
        fsync(item.root)
    finally:
        if temporary.is_symlink():
            temporary.unlink()


def operate(action, source, previous_source, profile):
    _CONTEXT.clear()
    if action in {'switch', 'verify', 'restore', 'resume', 'commit'}:
        _CONTEXT['action'] = action
    source = trusted_source(source)
    previous_source = trusted_source(previous_source) if previous_source else None
    path = journal_path(source)
    value = load(path, source, previous_source, profile)
    changed = [record for record in value['entries'] if record['changed']]
    if action == 'switch':
        require(value['phase'] == 'prepared', 'Transition switch already consumed; inspect recovery first')
        for record in value['entries']:
            check_original(record, previous_source)
            require(pair(entry(record['key'])) == record['old'], 'Component pins changed before transition')
            for identifier in set(filter(None, record['new'].values())):
                store_for(entry(record['key'])).metadata(identifier)
        value['phase'] = 'switching'
        save(path, value)
        for record in changed:
            item = entry(record['key'])
            if record['was_active']:
                control(item).stop()
            for name in ('current', 'previous'):
                set_pointer(item, name, record['new'][name])
        value['phase'] = 'switched'
    elif action == 'restore':
        require(value['phase'] in PHASES - {'committed'}, 'Committed transition requires separate reviewed rollback')
        for record in value['entries']:
            check_original(record, previous_source)
            observed = pair(entry(record['key']))
            require(all(observed[name] in {record['old'][name], record['new'][name]}
                        for name in observed), 'Unrelated component pins appeared; recovery is fenced')
        value['phase'] = 'restoring'
        save(path, value)
        # The new role planner can have started a previously inactive role.
        # Quiesce every changed live controller before restoring any preimage.
        for record in changed:
            item = entry(record['key'])
            if active(item):
                control(item).stop()
        for record in changed:
            item = entry(record['key'])
            for name in ('current', 'previous'):
                set_pointer(item, name, record['old'][name])
        value['phase'] = 'restored'
    elif action in {'verify', 'resume'}:
        target = 'new' if action == 'verify' else 'old'
        require(value['phase'] in ({'switched', 'verified'} if action == 'verify' else {'restored', 'resumed'}),
                'Transition is not ready for health verification')
        if action == 'resume' and previous_source is None:
            require(not any(record['was_active'] for record in value['entries']),
                    'Previous transition needs explicit recovery; no install was replayed')
        for record in value['entries']:
            require(pair(entry(record['key'])) == record[target], 'Component pins changed before verification')
        for record in changed:
            item = entry(record['key'])
            if not record['was_active'] and not active(item):
                continue
            identifier = record[target]['current']
            if action == 'resume' and record['proofs'][identifier]['adapter'] == 'previous':
                worker(previous_source, 'health', item.key, identifier, start=record['was_active'])
            else:
                verify_component(item, identifier, start=record['was_active'])
        value['phase'] = 'verified' if action == 'verify' else 'resumed'
    else:
        require(action == 'commit' and value['phase'] in {'verified', 'committed'}, 'Transition was not verified')
        for record in value['entries']:
            require(pair(entry(record['key'])) == record['new'], 'Component pins changed before commit')
        value['phase'] = 'committed'
    save(path, value)
    return value


def require_installer_lock():
    import fcntl
    info = os.fstat(9)
    canonical = Path('/run/lock/3mm-release-mutation.lock')
    actual = canonical.lstat()
    require(info.st_uid == actual.st_uid == OWNER and stat.S_ISREG(info.st_mode)
            and stat.S_ISREG(actual.st_mode) and not (info.st_mode | actual.st_mode) & 0o022
            and info.st_nlink == actual.st_nlink == 1
            and (info.st_dev, info.st_ino) == (actual.st_dev, actual.st_ino)
            and os.readlink('/proc/self/fd/9') == str(canonical),
            'Transition requires the inherited installer release lock')
    fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'switch', 'verify', 'restore', 'resume', 'commit', '_worker'))
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--previous-source', type=Path)
    parser.add_argument('--profile', choices=('full', 'node'), default='full')
    parser.add_argument('--operation', choices=('inspect', 'health'))
    parser.add_argument('--entry')
    parser.add_argument('--build')
    parser.add_argument('--start', action='store_true')
    parser.add_argument('--retry-rolled-back', action='store_true')
    args = parser.parse_args()
    _CONTEXT.clear()
    _CONTEXT['action'] = args.action
    require(os.geteuid() == OWNER, 'Component transition requires the installer principal')
    source = trusted_source(args.source)
    sys.path.insert(0, str(source))
    if args.action == '_worker':
        require(args.operation is not None and args.entry is not None
                and args.build is not None and SHA.fullmatch(args.build), 'Invalid fixed adapter request')
        item = entry(args.entry)
        if args.operation == 'health':
            require_installer_lock()
        metadata = store_for(item).metadata(args.build)
        if args.operation == 'health':
            verify_component(item, args.build, start=args.start)
        else:
            require(not args.start, 'Inspection cannot start a component')
        print(json.dumps(proof(metadata), sort_keys=True))
        return 0
    require_installer_lock()
    require(not args.retry_rolled_back or args.action == 'prepare', 'Invalid fixed adapter request')
    value = prepare(source, args.previous_source, args.profile, retry_rolled_back=args.retry_rolled_back) if args.action == 'prepare' else operate(
        args.action, source, args.previous_source, args.profile)
    print(json.dumps({'phase': value['phase'], 'components': len(value['entries']),
                      'changed_components': sum(record['changed'] for record in value['entries']),
                      'application_packages_changed': False, 'grants_changed': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        # Safe category only: never copy provider output, environment or paths.
        print(json.dumps(failure_result(error), sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
