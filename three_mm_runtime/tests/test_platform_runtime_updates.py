"""Disposable Runtime workflow; real artifacts/transactions, no installed services."""
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from types import SimpleNamespace

import pytest
from deployment.component_store import _write
from deployment.platform_runtime_component import INPUTS, RuntimeStore, build_component
from three_mm_runtime.platform_runtime_updates import RuntimeUpdates, validate_request

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='POSIX root-helper locks and immutable Runtime store')
ROOT = Path(__file__).resolve().parents[2]


class Control:
    def __init__(self):
        self.running, self.calls = True, []
    def active(self):
        return self.running
    def stop(self):
        self.calls.append('stop-runtime'); self.running = False
    def start(self):
        self.calls.append('start-runtime'); self.running = True


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    source = tmp_path / 'core'
    for name in (*INPUTS, 'deployment/platform-runtime-contract.json'):
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    old_source = tmp_path / 'older-core'
    shutil.copytree(source, old_source)
    entry = old_source / 'three_mm_platform_runtime/server.py'
    entry.write_bytes(entry.read_bytes() + b'\n# Older fixture Runtime\n')
    old_blob, old = build_component(old_source)
    current = {'pid': 1234, 'generation': 'a'*32, 'release': str(source), 'metadata_sha256': 'b'*64}
    control = Control()
    probe = lambda build: {'build_id': build, 'core_pid': current['pid'], 'core_process_generation': current['generation']}
    store = RuntimeStore(tmp_path/'runtime', tmp_path/'state')
    store.activate(old_blob, hashlib.sha256(old_blob).hexdigest(), control=control,
        health=probe, fingerprint=lambda: dict(current))
    control.calls.clear()
    w = RuntimeUpdates(source=source, root=store.root, state=store.state,
        fingerprint=lambda: dict(current), control=control, probe=probe,
        enforce=False, mutation_lock=nullcontext, worker_active=lambda _id: False)
    import pwd
    monkeypatch.setattr(pwd, 'getpwnam', lambda _name: SimpleNamespace(pw_uid=os.getuid()))
    monkeypatch.setattr('three_mm_platform_runtime.server.probe_runtime',
        lambda *_args, **kwargs: {'ready': True, 'query_execution_contract': 1})
    return SimpleNamespace(w=w, control=control, store=store, old=old, current=current)


def request(action='prepare', identifier='a'*32, previous=None, candidate=None):
    result = {'action': 'platform_runtime_' + action, 'request_id': identifier,
        'expected_operation_id': previous, 'requested_by_user_id': 7}
    if candidate:
        result.update(candidate_id=candidate['candidate_id'], build_id=candidate['build_id'],
            confirmation='UPDATE RUNTIME ' + candidate['build_id'])
    return result


def prepare(x):
    x.w.queue(request(), lambda _id: None)
    x.w.execute('a'*32)
    return x.w.candidate()


def test_status_is_read_only_and_prepare_never_switches_runtime(workflow):
    x = workflow
    assert not x.w.web.exists()
    initial = x.w.status()
    assert initial['ready'] and not x.w.web.exists()
    candidate = prepare(x)
    assert x.store.target('current') == x.old['build_id'] and not x.control.calls
    assert candidate['build_id'] != x.old['build_id']
    assert x.w.status()['candidate']['compatible'] is True


def test_apply_uses_real_runtime_transaction_and_preserves_core(workflow):
    x = workflow; candidate = prepare(x)
    before = dict(x.current)
    payload = request('apply', 'b'*32, 'a'*32, candidate)
    x.w.queue(payload, lambda _id: None)
    x.w.execute('b'*32)
    assert x.store.target('current') == candidate['build_id']
    assert x.store.target('previous') == x.old['build_id']
    assert x.current == before and x.control.calls == ['stop-runtime', 'start-runtime']
    assert x.w.operation()['reason'] == 'runtime_updated'


def test_exact_request_is_not_rescheduled_after_lost_scheduler_reply(workflow):
    calls = []
    def lost(identifier):
        calls.append(identifier)
        raise TimeoutError('Reply lost after scheduling')
    with pytest.raises(RuntimeError):
        workflow.w.queue(request(), lost)
    assert workflow.w.operation()['state'] == 'queued'
    workflow.w.queue(request(), lost)
    assert calls == ['a'*32]
    with pytest.raises(ValueError):
        workflow.w.queue({**request(), 'requested_by_user_id': 8}, lost)


@pytest.mark.parametrize('fault', ['core-generation', 'runtime-pointer', 'candidate-id', 'confirmation'])
def test_drift_or_changed_confirmation_cannot_switch_runtime(workflow, fault):
    x = workflow; candidate = prepare(x)
    payload = request('apply', 'b'*32, 'a'*32, candidate)
    if fault == 'core-generation': x.current['generation'] = 'c'*32
    elif fault == 'runtime-pointer':
        data = x.w.candidate(); data['current_build_id'] = 'c'*64
        _write(x.w.web/'candidate.json', json.dumps(data).encode())
    elif fault == 'candidate-id': payload['candidate_id'] = 'c'*32
    else: payload['confirmation'] = 'UPDATE ANYTHING'
    with pytest.raises(ValueError): x.w.queue(payload, lambda _id: None)
    assert x.store.target('current') == x.old['build_id'] and not x.control.calls


def test_worker_rechecks_core_after_queue_before_any_effect(workflow):
    x = workflow; candidate = prepare(x)
    x.w.queue(request('apply', 'b'*32, 'a'*32, candidate), lambda _id: None)
    x.current['generation'] = 'c'*32
    with pytest.raises(RuntimeError): x.w.execute('b'*32)
    assert x.store.target('current') == x.old['build_id'] and not x.control.calls


def test_failed_candidate_health_confirms_previous_runtime(workflow):
    x = workflow; candidate = prepare(x)
    original = x.w.probe
    def reject_new(build):
        if build == candidate['build_id']: raise ValueError('Unhealthy candidate')
        return original(build)
    x.w.probe = reject_new
    x.w.queue(request('apply', 'b'*32, 'a'*32, candidate), lambda _id: None)
    with pytest.raises(RuntimeError): x.w.execute('b'*32)
    assert x.store.target('current') == x.old['build_id'] and x.control.running
    assert x.store.pending() is None
    assert x.w.operation()['reason'] == 'previous_runtime_ready'


def test_candidate_tampering_never_reaches_service_switch(workflow):
    x = workflow; candidate = prepare(x)
    x.w.queue(request('apply', 'b'*32, 'a'*32, candidate), lambda _id: None)
    with (x.w.web/'candidate.tar').open('ab') as stream: stream.write(b'tampered')
    with pytest.raises(RuntimeError): x.w.execute('b'*32)
    assert not x.control.calls and x.store.target('current') == x.old['build_id']


def test_interruption_is_visible_and_recovery_does_not_replay_update(workflow):
    x = workflow; candidate = prepare(x)
    x.w.queue(request('apply', 'b'*32, 'a'*32, candidate), lambda _id: None)
    operation = x.w.operation(); operation['updated_at'] = int(time.time()) - 40
    _write(x.w.web/'operation.json', json.dumps(operation).encode())
    before = (x.w.web/'operation.json').read_bytes()
    assert x.w.status()['operation']['reason'] == 'worker_interrupted'
    assert (x.w.web/'operation.json').read_bytes() == before  # GET cannot recover/mutate.
    x.w.queue(request('recover', 'c'*32, 'b'*32), lambda _id: None)
    x.w.execute('c'*32)
    assert x.store.target('current') == x.old['build_id'] and not x.control.calls
    assert x.w.operation()['reason'] == 'runtime_recovered'


@pytest.mark.parametrize('extra', [{'source': '/tmp/attacker'}, {'artifact': '/tmp/anything'},
    {'component': 'agent'}, {'url': 'https://example.invalid'}, {'command': 'reboot'}])
def test_request_never_accepts_paths_commands_urls_or_other_components(extra):
    with pytest.raises(ValueError): validate_request({**request(), **extra})


def test_stale_operation_cursor_and_concurrent_queue_are_refused(workflow):
    w = workflow.w
    w.queue(request(), lambda _id: None)
    with pytest.raises(ValueError): w.queue(request(identifier='b'*32), lambda _id: None)
    with pytest.raises(ValueError): w.queue(request(identifier='b'*32, previous='a'*32), lambda _id: None)


def test_pointer_outside_runtime_release_root_is_refused(workflow, tmp_path):
    (workflow.w.root/'current').unlink()
    (workflow.w.root/'current').symlink_to(tmp_path)
    with pytest.raises(ValueError): workflow.w.queue(request(), lambda _id: None)


def test_pending_transaction_requires_explicit_recovery_even_without_web_history(workflow):
    x = workflow
    _write(x.store.journal, json.dumps({'schema_version':1, 'phase':'switching',
        'previous':x.old['build_id'], 'previous_previous':None,
        'candidate':x.old['build_id'], 'was_active':True}).encode())
    assert x.w.status()['recovery_required'] is True
    with pytest.raises(ValueError): x.w.queue(request(), lambda _id: None)
    x.w.queue(request('recover'), lambda _id: None)
    x.w.execute('a'*32)
    assert x.store.pending() is None and x.control.running
    assert x.w.operation()['reason'] == 'runtime_recovered'


def test_interrupted_switch_restores_old_runtime_without_applying_candidate_again(workflow):
    x = workflow; candidate = prepare(x)
    x.w.queue(request('apply', 'b'*32, 'a'*32, candidate), lambda _id: None)
    blob = (x.w.web/'candidate.tar').read_bytes()
    x.store.stage(blob, candidate['sha256'])
    _write(x.store.journal, json.dumps({'schema_version':1, 'phase':'switching',
        'previous':x.old['build_id'], 'previous_previous':None,
        'candidate':candidate['build_id'], 'was_active':True}).encode())
    x.store.link('current', candidate['build_id'])
    operation = x.w.operation(); operation['updated_at'] = int(time.time()) - 40
    _write(x.w.web/'operation.json', json.dumps(operation).encode())
    x.w.queue(request('recover', 'c'*32, 'b'*32), lambda _id: None)
    x.w.execute('c'*32)
    assert x.store.target('current') == x.old['build_id'] and x.store.pending() is None
    assert x.control.calls == ['stop-runtime', 'start-runtime']
    assert x.w.operation()['reason'] == 'runtime_recovered'
