"""Reviewed local Agent / per-application-host updates through the root helper.

Uses the Runtime web workflow's bounded root-owned journal helpers and the
existing immutable component stores, health and rollback controllers. No URLs,
uploads, arbitrary paths, dependencies installation, default-host change, Core
restart, application lifecycle/grant mutation or remote-device update.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import time

from deployment.component_store import _write, release_mutation_lock
from deployment.platform_runtime_component import core_fingerprint
from components.system_runtime.hardware_interfaces import admin_revision
from components.system_runtime.platform_runtime_updates import RuntimeUpdates, BUSY, HEX32, HEX64

STATE = Path('/var/lib/3mm-component-updates')
DATABASE = Path('/var/lib/3mm/core/3mm.db')
logger = logging.getLogger(__name__)
ACTIONS = frozenset('component_' + action for action in ('status', 'prepare', 'apply', 'rollback', 'recover'))


class ComponentNotAccepted(ValueError):
    """Proven preflight refusal: no operation persisted or worker scheduled."""


def validate_target(component, target_id):
    if not ((component == 'agent' and target_id == 'local') or
            (component == 'application_host' and type(target_id) is str
             and re.fullmatch(r'[0-9a-f]{24}', target_id))):
        raise ValueError('Unsupported local component target')


def confirmation(action, component, target_id, build_id):
    return f'{action.upper()} {component} {target_id} {build_id}'


def validate_request(payload):
    if type(payload) is not dict or type(payload.get('action')) is not str or payload['action'] not in ACTIONS:
        raise ValueError('Invalid component operation')
    fields = {'action', 'component', 'target_id', 'requested_by_user_id'}
    validate_target(payload.get('component'), payload.get('target_id'))
    action = payload['action'].removeprefix('component_')
    if action != 'status': fields |= {'request_id', 'expected_operation_id'}
    if action in {'apply', 'rollback'}: fields |= {'build_id', 'confirmation'}
    if action == 'apply': fields.add('candidate_id')
    if (set(payload) != fields or type(payload['requested_by_user_id']) is not int
            or payload['requested_by_user_id'] <= 0):
        raise ValueError('Invalid component request fields')
    if action != 'status' and (type(payload['request_id']) is not str or not HEX32.fullmatch(payload['request_id'])
            or payload['expected_operation_id'] is not None and (type(payload['expected_operation_id']) is not str
                or not HEX32.fullmatch(payload['expected_operation_id']))):
        raise ValueError('Invalid component request identity')
    if action in {'apply', 'rollback'} and (type(payload['build_id']) is not str
            or not HEX64.fullmatch(payload['build_id']) or payload['confirmation'] != confirmation(
                action, payload['component'], payload['target_id'], payload['build_id'])):
        raise ValueError('Exact component confirmation required')
    if action == 'apply' and (type(payload['candidate_id']) is not str or not HEX32.fullmatch(payload['candidate_id'])):
        raise ValueError('Invalid candidate identity')
    return payload


def _json_file(path, *, uid=0, maximum=1024*1024):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != uid
                or info.st_mode & 0o022 or not 0 < info.st_size <= maximum):
            raise ValueError('Untrusted component metadata')
        data = stream.read(maximum + 1)
    if len(data) > maximum: raise ValueError('Component metadata exceeds budget')
    result = json.loads(data)
    if type(result) is not dict: raise ValueError('Invalid component metadata')
    return result


def _protected_directory(path):
    for part in (path, *path.parents):
        info = part.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Installed component directories are not protected')


def _protected_sources(source, names):
    for name in names:
        path = source / name
        for part in (path, *path.parents):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise ValueError('Installed component source is not protected')
            if part == source: break


class InstalledComponent:
    """Only fixed local stores; construction and status do not create directories."""
    def __init__(self, component, target_id, *, database=DATABASE):
        validate_target(component, target_id)
        self.component, self.target_id, self.database = component, target_id, Path(database)
        if component == 'agent':
            from deployment.service_component import ServiceStore, ServiceControl
            self.root = Path('/opt/3mm-agent')
            self.store = ServiceStore('agent', create=False)
            self.control = ServiceControl('agent')
        else:
            from deployment.application_host_component import ROOT, STATE, HostStore, ApplicationControl
            self.root = ROOT / 'instances' / target_id
            self.store = HostStore(self.root, STATE / target_id, ROOT / 'releases', create=False)
            self.control = ApplicationControl(target_id)
        for directory in (self.root, self.store.state, self.store.releases):
            _protected_directory(directory)

    def pointer(self, name):
        link = self.root / name
        if not link.exists() and not link.is_symlink(): return None
        if not link.is_symlink() or link.lstat().st_uid != 0: raise ValueError('Unsafe component pointer')
        directory = link.resolve(strict=True)
        if directory.parent != self.store.releases.resolve() or not HEX64.fullmatch(directory.name):
            raise ValueError('Component pointer escaped its store')
        _protected_directory(directory)
        metadata = _json_file(directory / 'component.json')
        if metadata.get('build_id') != directory.name: raise ValueError('Component identity changed')
        return directory.name

    def binding(self):
        """Current DB authority and durable app/device identity, not a UI claim."""
        if self.component == 'agent':
            import pwd
            identity = _json_file(Path('/var/lib/3mm/agent/identity.json'), uid=pwd.getpwnam('3mm').pw_uid, maximum=4096)
            return {'device_id': identity['device_id']}
        with closing(sqlite3.connect(self.database.as_uri() + '?mode=ro', uri=True, timeout=.2)) as db:
            db.set_progress_handler(lambda: 1, 10000)
            row = db.execute('SELECT id,module_id,module_package_id,active_version,status,enabled,'
                'authority_incarnation,authority_epoch,authority_mode FROM application_extension_installations '
                'WHERE instance_id=?', (self.target_id,)).fetchone()
        if not row or row[4:6] != ('active', 1): raise ValueError('Application is not currently enabled and active')
        from deployment.application_host_component import _metadata
        return {'installation': list(row), 'active_metadata': hashlib.sha256(
            json.dumps(_metadata(self.target_id), sort_keys=True).encode()).hexdigest()}

    def ready(self, build):
        if not self.control.active(): return False
        if self.component == 'agent':
            from deployment.service_component import _http_identity
            result = _http_identity('http://127.0.0.1:8890/component-health', timeout=1)
            pid = int(subprocess.check_output(['/usr/bin/systemctl', 'show', '3mm-agent.service',
                '--property=MainPID', '--value'], text=True, timeout=2).strip())
            return pid > 0 and result == {'component': 'agent', 'build_id': build, 'pid': pid}
        import pwd
        from deployment.application_host_component import _metadata, host_probe, APPLICATIONS, KEYS
        key = (KEYS / (self.target_id + '.key')).read_bytes()
        if len(key) != 32: raise ValueError('Host transport key is invalid')
        host_probe(self.target_id, APPLICATIONS / self.target_id / 'run/service.sock', key,
            expected_uid=pwd.getpwnam('3mm-app').pw_uid, expected_build=build, metadata=_metadata(self.target_id))
        return True

    def fingerprint(self):
        if self.component == 'agent': value = core_fingerprint()
        else:
            from deployment.application_host_component import fingerprint
            value = fingerprint(self.target_id)
        return {**value, 'component_binding': self.binding()}

    def probe(self, build):
        if self.component == 'agent':
            from deployment.service_component import health
            return health(self.store, self.control, build)
        from deployment.application_host_component import health
        return health(self.target_id, build)

    def validate(self, blob, sha):
        if self.component == 'agent':
            from deployment.service_component import validate_artifact
            return validate_artifact(blob, sha, 'agent')[0]
        from deployment.application_host_component import validate_artifact
        return validate_artifact(blob, sha)[0]

    def build(self, source, output):
        current = self.pointer('current')
        directory = self.store.releases / current
        metadata = self.store.metadata(current)  # Validate native closure before using its interpreter/vendor.
        image = self.component == 'application_host' and 'Pillow' in metadata['binding']['dependencies']
        if self.component == 'agent':
            from deployment.service_component import inputs, CONTRACT_FILE
            names = inputs(source, 'agent') + [CONTRACT_FILE, 'deployment/service-agent-requirements.txt']
        else:
            from deployment.application_host_component import inputs
            names = inputs(source) + ['deployment/application-host-contract.json', 'deployment/application-host-requirements.txt']
            if image: names.append('deployment/application-media-requirements.txt')
        names += ['deployment/component_store.py',
            'deployment/platform_runtime_component.py', 'deployment/application_host_component.py', 'deployment/service_component.py']
        _protected_sources(source, names)
        # The component already contains its exact locked distributions. No pip,
        # network or dependency installation into Core. A changed lock refuses.
        script = """import sys
from pathlib import Path
source,vendor,kind,output,image=sys.argv[1:]
sys.path[:0]=[source,vendor]
if kind=='agent':
 from deployment.service_component import build_component
 blob,_=build_component(Path(source),'agent')
else:
 from deployment.application_host_component import build_component
 blob,_=build_component(Path(source),image_provider=image=='1')
Path(output).write_bytes(blob)
"""
        subprocess.run([str(directory / '.venv/bin/python'), '-B', '-I', '-c', script, str(source),
            str(directory / 'vendor'), self.component, str(output), '1' if image else '0'],
            cwd=source, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'},
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=True, timeout=180)


class ComponentUpdates(RuntimeUpdates):
    """Reuse Runtime's bounded secure journal I/O, never its Runtime mutation path."""
    def __init__(self, *, source=Path('/opt/3mm/current'), state=STATE, database=DATABASE,
                 adapter_factory=None, actor_revision=None, **kwargs):
        super().__init__(source=source, state=state, **kwargs)
        self.adapter_factory = adapter_factory or (lambda c, t: InstalledComponent(c, t, database=database))
        self.actor_revision = actor_revision or (lambda user: admin_revision(database, user))

    def adapter(self, payload):
        return self.adapter_factory(payload['component'], payload['target_id'])

    def status(self, component, target_id):
        validate_target(component, target_id)
        current = previous = None
        ready = False
        pending = False
        try:
            adapter = self.adapter_factory(component, target_id)
            current, previous = adapter.pointer('current'), adapter.pointer('previous')
            pending = adapter.store.pending() is not None
            adapter.binding()
            ready = current is not None and adapter.ready(current)
        except (OSError, ValueError, KeyError, RuntimeError, sqlite3.Error, subprocess.SubprocessError):
            pass
        operation, candidate = self.operation(), self.candidate()
        interrupted = self.interrupted(operation)
        compatible = False
        try:
            compatible = bool(candidate and candidate['component'] == component and candidate['target_id'] == target_id
                and candidate['current_build_id'] == current and candidate['source'] == str(self.source.resolve(strict=True))
                and candidate['core'] == self.fingerprint() and candidate['binding'] == adapter.fingerprint())
        except (OSError, ValueError, KeyError, RuntimeError, UnboundLocalError, sqlite3.Error, subprocess.SubprocessError):
            pass
        public_operation = None if operation is None else {k: operation[k] for k in
            ('request_id', 'component', 'target_id', 'action', 'state', 'reason', 'updated_at')}
        if interrupted: public_operation.update(state='recovery_required', reason='worker_interrupted')
        public_candidate = None
        if candidate and candidate['component'] == component and candidate['target_id'] == target_id:
            public_candidate = {k: candidate[k] for k in ('candidate_id', 'build_id', 'sha256', 'bytes')}
            public_candidate['compatible'] = compatible
        return {'component': component, 'target_id': target_id, 'current_build_id': current,
            'previous_build_id': previous, 'ready': ready, 'candidate': public_candidate, 'operation': public_operation,
            'recovery_required': bool(interrupted or operation and operation['state'] == 'recovery_required'
                or pending and not (operation and operation['state'] in BUSY and not interrupted))}

    def check_candidate(self, payload, core, adapter):
        candidate = self.candidate()
        if (not candidate or any(candidate[k] != payload[k] for k in ('component', 'target_id', 'candidate_id', 'build_id'))
                or candidate['core'] != core or candidate['source'] != str(self.source.resolve(strict=True))
                or candidate['current_build_id'] != adapter.pointer('current')
                or candidate['binding'] != adapter.fingerprint() or candidate['build_id'] == candidate['current_build_id']):
            raise ValueError('Component candidate changed; prepare again')
        return candidate

    def queue(self, payload, scheduler):
        validate_request(payload)
        with self.locked():
            # Classification ends BEFORE durable acceptance. Persistence errors
            # and lost scheduler replies must remain unconfirmed, not refusals.
            try:
                record = self._preflight(payload)
            except (OSError, ValueError, KeyError, RuntimeError, sqlite3.Error, subprocess.SubprocessError):
                raise ComponentNotAccepted('Component state changed or preparation is unavailable; refresh and review') from None
            if record.get('state') is not None: return record  # Exact accepted identity, never reschedule.
            operation = self.save_operation(record, 'queued')
            try: scheduler(operation['request_id'])
            except Exception: raise RuntimeError('Component scheduling outcome is unconfirmed') from None
            return operation

    def _preflight(self, payload):
        old = self.operation()
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if old and old['request_id'] == payload['request_id']:
            if old['request_digest'] != digest: raise ValueError('Component request conflict')
            return old  # An accepted request is never scheduled twice.
        if payload['expected_operation_id'] != (old['request_id'] if old else None):
            raise ValueError('Component operation changed; refresh')
        recover = payload['action'] == 'component_recover'
        if old and old['state'] in BUSY and not (recover and self.interrupted(old)):
            raise ValueError('Component operation is still running')
        if old and old['state'] == 'recovery_required' and not recover:
            raise ValueError('Explicit component recovery required')
        if recover and old and (old['component'], old['target_id']) != (payload['component'], payload['target_id']):
            raise ValueError('Recover the original component target')
        with self.mutation_lock():
            actor = self.actor_revision(payload['requested_by_user_id'])
            core = self.fingerprint()
            source = self.source.resolve(strict=True)
            self.secure(source, directory=True)
            if core['release'] != str(source): raise ValueError('Core source changed')
            adapter = self.adapter(payload)
            pending = adapter.store.pending() is not None
            if pending and not recover: raise ValueError('Resolve the interrupted component transaction first')
            if recover and not (pending or old and (old['state'] == 'recovery_required' or self.interrupted(old))):
                raise ValueError('No component operation to recover')
            current = adapter.pointer('current')
            if current is None: raise ValueError('Component bootstrap is outside this workflow')
            if not recover and not adapter.control.active(): raise ValueError('Component must already be active')
            binding = adapter.fingerprint()
            if payload['action'] == 'component_apply': self.check_candidate(payload, core, adapter)
            if payload['action'] == 'component_rollback' and adapter.pointer('previous') != payload['build_id']:
                raise ValueError('Previous component build changed')
            return {**payload, 'request_digest': digest, 'core': core,
                'source': str(source), 'binding': binding, 'admin_revision': actor,
                'current_build_id': current}

    def execute(self, identifier):
        if type(identifier) is not str or not HEX32.fullmatch(identifier): raise ValueError('Invalid component worker')
        with self.locked(), self.mutation_lock():
            operation = self.operation()
            if not operation or operation['request_id'] != identifier or operation['state'] != 'queued':
                raise ValueError('Component operation is not queued')
            adapter = None
            phase = 'preflight'
            try:
                validate_request({k: v for k, v in operation.items() if k in {
                    'action', 'component', 'target_id', 'requested_by_user_id', 'request_id',
                    'expected_operation_id', 'build_id', 'confirmation', 'candidate_id'}})
                adapter = self.adapter(operation)
                def fresh():
                    if (self.actor_revision(operation['requested_by_user_id']) != operation['admin_revision']
                            or self.fingerprint() != operation['core'] or adapter.fingerprint() != operation['binding']
                            or str(self.source.resolve(strict=True)) != operation['source']):
                        raise ValueError('Component approval state changed')
                    return adapter.fingerprint()
                fresh()
                action = operation['action']
                if action != 'component_recover' and adapter.store.pending() is not None:
                    raise ValueError('Component transaction requires explicit recovery')
                if action == 'component_prepare':
                    phase = 'prepare'
                    operation = self.save_operation(operation, 'preparing')
                    artifact = self.web / 'building.tar'
                    if artifact.exists() or artifact.is_symlink(): raise ValueError('Unresolved component preparation')
                    try:
                        adapter.build(self.source.resolve(strict=True), artifact)
                        self.secure(artifact)
                        if artifact.stat().st_size > 128*1024*1024: raise ValueError('Component archive exceeds budget')
                        blob = artifact.read_bytes()
                        sha = hashlib.sha256(blob).hexdigest()
                        metadata = adapter.validate(blob, sha)
                        fresh()
                        if adapter.pointer('current') != operation['current_build_id']: raise ValueError('Component changed during preparation')
                        _write(self.web / 'candidate.tar', blob)
                        _write(self.web / 'candidate.json', json.dumps({'candidate_id': identifier,
                            'component': operation['component'], 'target_id': operation['target_id'],
                            'build_id': metadata['build_id'], 'sha256': sha, 'bytes': len(blob), 'core': operation['core'],
                            'source': operation['source'], 'binding': operation['binding'],
                            'current_build_id': operation['current_build_id']}, sort_keys=True).encode())
                    finally:
                        if artifact.exists() and not artifact.is_symlink(): artifact.unlink()
                    self.save_operation(operation, 'succeeded', 'candidate_prepared')
                    return
                # Recheck current authority before every possible service start,
                # including the existing store's rollback path.
                original = adapter.control
                class CheckedControl:
                    def active(self): return original.active()
                    def stop(self): fresh(); original.stop()
                    def start(self): fresh(); original.start()
                control = CheckedControl()
                if action == 'component_recover':
                    phase = 'recover'
                    operation = self.save_operation(operation, 'recovering')
                    with adapter.store.locked(): adapter.store.recover(control, adapter.probe)
                    adapter.probe(adapter.pointer('current'))
                    artifact = self.web / 'building.tar'
                    if artifact.exists() or artifact.is_symlink():
                        self.secure(artifact)
                        artifact.unlink()  # Discard only interrupted preparation, never replay it.
                    self.save_operation(operation, 'succeeded', 'component_recovered')
                    return
                if action == 'component_apply':
                    candidate = self.check_candidate(operation, operation['core'], adapter)
                    path, sha = self.web / 'candidate.tar', candidate['sha256']
                else:
                    if adapter.pointer('previous') != operation['build_id']: raise ValueError('Previous build changed')
                    path = adapter.store.releases / operation['build_id'] / 'artifact.tar'
                    sha = None
                self.secure(path)
                if path.stat().st_size > 128*1024*1024: raise ValueError('Component archive exceeds budget')
                blob = path.read_bytes()
                sha = sha or hashlib.sha256(blob).hexdigest()
                if adapter.validate(blob, sha)['build_id'] != operation['build_id']: raise ValueError('Component candidate identity changed')
                operation = self.save_operation(operation, 'applying')
                phase = 'activate'
                adapter.store.activate(blob, sha, control=control, health=adapter.probe, fingerprint=fresh)
                self.save_operation(operation, 'succeeded', 'component_rolled_back' if action == 'component_rollback' else 'component_updated')
            except Exception as failure:
                # Keep a safe failure location even when the store has already
                # restored the old build. Never log exception messages, keys,
                # application responses or artifact content.
                origin = failure.__traceback__
                while origin is not None and origin.tb_next is not None:
                    origin = origin.tb_next
                logger.warning('Component operation failed: request=%s component=%s phase=%s type=%s function=%s line=%s',
                    identifier, operation['component'], phase, type(failure).__name__,
                    origin.tb_frame.f_code.co_name if origin else 'unknown', origin.tb_lineno if origin else 0)
                state, reason = 'failed', 'preparation_failed'
                if operation['action'] != 'component_prepare':
                    state, reason = 'recovery_required', 'component_outcome_unconfirmed'
                    try:
                        if adapter and adapter.store.pending() is None and adapter.pointer('current') == operation['current_build_id']:
                            adapter.probe(operation['current_build_id'])
                            state, reason = 'failed', 'previous_component_ready'
                    except Exception: pass
                self.save_operation(operation, state, reason)
                raise RuntimeError('Component operation did not complete; inspect its recorded status') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job-id', required=True)
    args = parser.parse_args()
    if os.geteuid() != 0: raise ValueError('Component worker requires the local root helper')
    ComponentUpdates().execute(args.job_id)


if __name__ == '__main__': main()
