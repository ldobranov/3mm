"""Root-owned web workflow for the installed Core's Platform Runtime ONLY.

No uploads, URLs, caller paths, dependency installation, grants or Core restart.
Preparation builds the immutable installed release; execution reuses RuntimeStore.
One durable operation and one candidate are retained. Lost replies are not retries.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

from deployment.component_store import _write, release_mutation_lock
from deployment.platform_runtime_component import (
    INPUTS, MAX_ARTIFACT, ROOT, STATE, RuntimeStore, SystemdRuntime,
    build_component, core_fingerprint, runtime_health, validate_artifact, validate_metadata,
)
from deployment.deployment_contract import validate_platform_runtime_contract

ACTIONS = frozenset({'platform_runtime_status', 'platform_runtime_prepare',
    'platform_runtime_apply', 'platform_runtime_recover'})
HEX32 = re.compile(r'^[0-9a-f]{32}$')
HEX64 = re.compile(r'^[0-9a-f]{64}$')
FEATURES = ('authority_contract', 'query_execution_contract', 'connector_execution_contract',
    'application_response_contract', 'public_web_contract', 'event_delivery_contract')
BUSY = frozenset({'queued', 'preparing', 'applying', 'recovering'})


def validate_request(payload):
    if type(payload) is not dict or type(payload.get('action')) is not str or payload['action'] not in ACTIONS:
        raise ValueError('Invalid Runtime request')
    action = payload['action']
    if action == 'platform_runtime_status':
        if set(payload) != {'action'}:
            raise ValueError('Invalid Runtime status request')
        return payload
    fields = {'action', 'request_id', 'expected_operation_id', 'requested_by_user_id'}
    if action == 'platform_runtime_apply':
        fields |= {'candidate_id', 'build_id', 'confirmation'}
    if (set(payload) != fields or type(payload.get('request_id')) is not str
            or not HEX32.fullmatch(payload['request_id'])):
        raise ValueError('Invalid Runtime request fields')
    previous = payload['expected_operation_id']
    if (previous is not None and (type(previous) is not str or not HEX32.fullmatch(previous))
            or type(payload['requested_by_user_id']) is not int or payload['requested_by_user_id'] <= 0):
        raise ValueError('Invalid Runtime request identity')
    if action == 'platform_runtime_apply' and (
            type(payload['candidate_id']) is not str or not HEX32.fullmatch(payload['candidate_id'])
            or type(payload['build_id']) is not str or not HEX64.fullmatch(payload['build_id'])
            or payload['confirmation'] != 'UPDATE RUNTIME ' + payload['build_id']):
        raise ValueError('Exact Runtime confirmation required')
    return payload


class RuntimeUpdates:
    def __init__(self, *, source=Path('/opt/3mm/current'), root=ROOT, state=STATE,
                 fingerprint=core_fingerprint, probe=runtime_health, control=None,
                 builder=build_component, worker_active=None, enforce=True,
                 mutation_lock=release_mutation_lock):
        self.source, self.root, self.state = Path(source), Path(root), Path(state)
        self.web = self.state / 'web'
        self.fingerprint, self.probe = fingerprint, probe
        self.control = control or SystemdRuntime()
        self.builder = builder
        self.worker_active = worker_active or (lambda _identifier: True)
        self.enforce, self.mutation_lock = enforce, mutation_lock

    def secure(self, path, *, directory=False):
        info = path.lstat()
        if (stat.S_ISLNK(info.st_mode)
                or (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))
                or self.enforce and (info.st_uid != 0 or info.st_mode & 0o022)):
            raise ValueError('Runtime managed path is unsafe')

    def read(self, path, *, optional=False):
        if optional and not path.exists() and not path.is_symlink():
            return None
        self.secure(path)
        with path.open('rb') as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError('Runtime metadata exceeds its budget')
        value = json.loads(raw)
        if type(value) is not dict:
            raise ValueError('Runtime metadata is invalid')
        return value

    def pointer(self, name):
        self.secure(self.root, directory=True)
        releases = self.root / 'releases'
        self.secure(releases, directory=True)
        link = self.root / name
        if not link.exists() and not link.is_symlink():
            return None
        if not link.is_symlink() or self.enforce and link.lstat().st_uid != 0:
            raise ValueError('Runtime pointer is unsafe')
        target = link.resolve(strict=True)
        if target.parent != releases.resolve() or not HEX64.fullmatch(target.name):
            raise ValueError('Runtime pointer escapes its root')
        self.secure(target, directory=True)
        code = target / 'runtime.pyz'
        self.secure(code)
        if code.stat().st_size > MAX_ARTIFACT:
            raise ValueError('Runtime payload exceeds its budget')
        metadata = self.read(target / 'component.json')
        if validate_metadata(metadata, code.read_bytes())['build_id'] != target.name:
            raise ValueError('Runtime identity changed')
        return target.name

    def operation(self):
        if not self.web.exists() and not self.web.is_symlink():
            return None
        self.secure(self.state, directory=True)
        self.secure(self.web, directory=True)
        result = self.read(self.web / 'operation.json', optional=True)
        if result is not None and (not HEX32.fullmatch(str(result.get('request_id', '')))
                or result.get('state') not in BUSY | {'succeeded', 'failed', 'recovery_required'}):
            raise ValueError('Runtime operation is invalid')
        return result

    def candidate(self):
        if not self.web.exists():
            return None
        result = self.read(self.web / 'candidate.json', optional=True)
        if result is not None and (not HEX32.fullmatch(str(result.get('candidate_id', '')))
                or not HEX64.fullmatch(str(result.get('build_id', '')))
                or not HEX64.fullmatch(str(result.get('sha256', '')))):
            raise ValueError('Runtime candidate is invalid')
        return result

    def save_operation(self, operation, state, reason=None):
        operation = {**operation, 'state': state, 'reason': reason,
            'updated_at': int(time.time())}
        _write(self.web / 'operation.json', json.dumps(operation, sort_keys=True).encode())
        return operation

    @contextmanager
    def locked(self):
        import fcntl
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.secure(self.state, directory=True)
        self.web.mkdir(exist_ok=True, mode=0o700)
        self.secure(self.web, directory=True)
        fd = os.open(self.web / 'lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            if self.enforce and os.fstat(fd).st_uid != 0:
                raise ValueError('Runtime workflow lock is unsafe')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)

    def interrupted(self, operation):
        return bool(operation and operation['state'] in BUSY
            and time.time() - operation['updated_at'] > 10
            and not self.worker_active(operation['request_id']))

    def pending_transaction(self):
        path = self.state / 'transaction.json'
        return path.exists() or path.is_symlink()

    def status(self):
        # Read-only: no directory, lock, candidate, service or grant creation.
        current = previous = None
        ready, reason, features = False, None, {}
        try:
            current, previous = self.pointer('current'), self.pointer('previous')
            if current is None:
                raise ValueError('Runtime not installed')
            from three_mm_platform_runtime.server import probe_runtime
            import pwd
            peer = probe_runtime(Path('/run/3mm-platform/runtime.sock'),
                expected_uid=pwd.getpwnam('3mm-platform').pw_uid, expected_build=current)
            ready = peer.get('ready') is True
            features = {name: peer.get(name) if type(peer.get(name)) is int else None for name in FEATURES}
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError):
            reason = 'runtime_unavailable'
        operation = self.operation()
        candidate = self.candidate()
        compatible = False
        try:
            core = self.fingerprint()
            compatible = bool(candidate and candidate['core'] == core
                and candidate['source'] == str(self.source.resolve(strict=True))
                and candidate['current_build_id'] == current)
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError):
            reason = reason or 'core_unavailable'
        interrupted = self.interrupted(operation)
        requires_recovery = bool(interrupted or operation and operation['state'] == 'recovery_required'
            or self.pending_transaction() and not (operation and operation['state'] in BUSY and not interrupted))
        public_operation = None if operation is None else {key: operation[key] for key in
            ('request_id', 'action', 'state', 'reason', 'updated_at')}
        if interrupted:
            public_operation.update(state='recovery_required', reason='worker_interrupted')
        public_candidate = None if candidate is None else {key: candidate[key] for key in
            ('candidate_id', 'build_id', 'sha256', 'bytes', 'features')}
        if public_candidate is not None:
            public_candidate['compatible'] = compatible
        return {'current_build_id': current, 'previous_build_id': previous,
            'ready': ready, 'features': features, 'reason': reason,
            'candidate': public_candidate, 'operation': public_operation,
            'recovery_required': requires_recovery}

    def queue(self, payload, scheduler):
        validate_request(payload)
        with self.locked():
            old = self.operation()
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            if old and old['request_id'] == payload['request_id']:
                if old['request_digest'] != digest:
                    raise ValueError('Runtime request ID conflict')
                return old  # Same accepted request, never schedule it twice.
            if payload['expected_operation_id'] != (old['request_id'] if old else None):
                raise ValueError('Runtime operation changed; refresh')
            recover = payload['action'] == 'platform_runtime_recover'
            if old and old['state'] in BUSY and not (recover and self.interrupted(old)):
                raise ValueError('Runtime operation is still running')
            if old and old['state'] == 'recovery_required' and not recover:
                raise ValueError('Explicit Runtime recovery required')
            if not recover and self.pending_transaction():
                raise ValueError('An interrupted Runtime transaction requires explicit recovery')
            if recover and not (self.pending_transaction() or old and (old['state'] == 'recovery_required' or self.interrupted(old))):
                raise ValueError('No Runtime operation to recover')
            with self.mutation_lock():
                core = self.fingerprint()
                source = self.source.resolve(strict=True)
                self.secure(source, directory=True)
                if core['release'] != str(source):
                    raise ValueError('Core source changed')
                current = self.pointer('current')
                if current is None:
                    raise ValueError('Runtime bootstrap is outside this workflow')
                if not recover and not self.control.active():
                    raise ValueError('Runtime must already be active')
                if payload['action'] == 'platform_runtime_apply':
                    self.check_candidate(payload, core, current)
                operation = {**payload, 'core': core, 'source': str(source),
                    'current_build_id': current, 'request_digest': digest}
                operation = self.save_operation(operation, 'queued')
            try:
                scheduler(operation['request_id'])
            except Exception:
                # The scheduler's reply can be lost AFTER systemd accepted work.
                # Preserve the queued identity; never manufacture a retry permission.
                raise RuntimeError('Runtime scheduling outcome is unconfirmed') from None
            return operation

    def check_candidate(self, payload, core, current):
        candidate = self.candidate()
        if (not candidate or candidate['candidate_id'] != payload['candidate_id']
                or candidate['build_id'] != payload['build_id'] or candidate['core'] != core
                or candidate['source'] != str(self.source.resolve(strict=True))
                or candidate['current_build_id'] != current or current == candidate['build_id']):
            raise ValueError('Runtime candidate changed; prepare again')
        return candidate

    def execute(self, identifier):
        if type(identifier) is not str or not HEX32.fullmatch(identifier):
            raise ValueError('Invalid Runtime worker identity')
        with self.locked(), self.mutation_lock():
            operation = self.operation()
            if not operation or operation['request_id'] != identifier or operation['state'] != 'queued':
                raise ValueError('Runtime operation is not queued')
            try:
                if operation['core'] != self.fingerprint() or operation['source'] != str(self.source.resolve(strict=True)):
                    raise ValueError('Core changed after approval')
                action = operation['action']
                if action != 'platform_runtime_recover' and self.pending_transaction():
                    raise ValueError('An interrupted Runtime transaction requires explicit recovery')
                if action == 'platform_runtime_prepare':
                    operation = self.save_operation(operation, 'preparing')
                    source = self.source.resolve(strict=True)
                    for name in INPUTS:
                        path = source / name
                        self.secure(path)
                        for parent in path.parents:
                            if parent == source:
                                break
                            self.secure(parent, directory=True)
                    declared = validate_platform_runtime_contract((source / 'deployment/platform-runtime-contract.json').read_bytes())
                    blob, metadata = self.builder(source)
                    validate_artifact(blob, hashlib.sha256(blob).hexdigest())
                    if operation['core'] != self.fingerprint() or operation['current_build_id'] != self.pointer('current'):
                        raise ValueError('Core or Runtime changed during preparation')
                    candidate = {'candidate_id': identifier, 'build_id': metadata['build_id'],
                        'sha256': hashlib.sha256(blob).hexdigest(), 'bytes': len(blob),
                        'core': operation['core'], 'source': operation['source'],
                        'current_build_id': operation['current_build_id'],
                        'features': {name: declared.get(name) for name in FEATURES}}
                    _write(self.web / 'candidate.tar', blob)
                    _write(self.web / 'candidate.json', json.dumps(candidate, sort_keys=True).encode())
                    self.save_operation(operation, 'succeeded', 'candidate_prepared')
                    return
                store = RuntimeStore(self.root, self.state)
                if action == 'platform_runtime_recover':
                    operation = self.save_operation(operation, 'recovering')
                    with store.locked():
                        store.recover(self.control, self.probe)
                    self.probe(store.target('current'))
                    self.save_operation(operation, 'succeeded', 'runtime_recovered')
                    return
                candidate = self.check_candidate(operation, operation['core'], self.pointer('current'))
                artifact = self.web / 'candidate.tar'
                self.secure(artifact)
                if artifact.stat().st_size > MAX_ARTIFACT:
                    raise ValueError('Runtime candidate exceeds its budget')
                blob = artifact.read_bytes()
                parsed, _ = validate_artifact(blob, candidate['sha256'])
                if parsed['build_id'] != candidate['build_id'] or not self.control.active():
                    raise ValueError('Runtime candidate/availability changed')
                operation = self.save_operation(operation, 'applying')
                store.activate(blob, candidate['sha256'], control=self.control, health=self.probe,
                    fingerprint=self.fingerprint)
                self.save_operation(operation, 'succeeded', 'runtime_updated')
            except Exception:
                state, reason = 'failed', 'preparation_failed'
                if operation['action'] != 'platform_runtime_prepare':
                    state, reason = 'recovery_required', 'runtime_outcome_unconfirmed'
                    try:
                        store = RuntimeStore(self.root, self.state)
                        if store.pending() is None and store.target('current') == operation['current_build_id']:
                            self.probe(operation['current_build_id'])
                            state, reason = 'failed', 'previous_runtime_ready'
                    except Exception:
                        pass
                self.save_operation(operation, state, reason)
                raise RuntimeError('Runtime operation did not complete; inspect its recorded status') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job-id', required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise ValueError('Runtime worker requires the local root helper')
    RuntimeUpdates().execute(args.job_id)


if __name__ == '__main__':
    main()
