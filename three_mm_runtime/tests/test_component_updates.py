"""Disposable component transactions; no installed service or device is touched."""
from contextlib import nullcontext
import hashlib
import json
import os
from types import SimpleNamespace

import pytest

from deployment.component_store import ComponentStore, _write
from three_mm_runtime.component_updates import ComponentUpdates, ComponentNotAccepted, confirmation, validate_request

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Real POSIX component journal locks')
HOST = 'c'*24


class Store(ComponentStore):
    requires_active = True
    def metadata(self, identifier):
        data = (self.releases/identifier/'artifact.tar').read_bytes()
        assert hashlib.sha256(data).hexdigest() == identifier
        return {'build_id': identifier}
    def stage(self, blob, sha):
        if hashlib.sha256(blob).hexdigest() != sha: raise ValueError('bad checksum')
        directory = self.releases/sha
        directory.mkdir(exist_ok=True)
        (directory/'artifact.tar').write_bytes(blob)
        return sha


class Adapter:
    def __init__(self, directory, core):
        self.store = Store(directory/'component', directory/'journal')
        self.core, self.binding_value, self.calls = core, 1, []
        self.running = True
        self.reject = None
        self.control = self
        self.store.bootstrap(b'old', hashlib.sha256(b'old').hexdigest())
    def active(self): return self.running
    def stop(self): self.calls.append('stop'); self.running = False
    def start(self): self.calls.append('start'); self.running = True
    def pointer(self, name): return self.store.target(name)
    def binding(self): return self.binding_value
    def fingerprint(self): return {**self.core, 'component_binding': self.binding()}
    def ready(self, build): return self.running
    def probe(self, build):
        if build == self.reject: raise ValueError('unhealthy')
        return {'core_pid': self.core['pid'], 'core_process_generation': self.core['generation']}
    def validate(self, blob, sha):
        if hashlib.sha256(blob).hexdigest() != sha: raise ValueError('checksum')
        return {'build_id': sha}
    def build(self, source, output): output.write_bytes(b'new')


@pytest.fixture(params=['agent', 'application_host'])
def workflow(tmp_path, request):
    source = tmp_path/'source'; source.mkdir()
    core = {'pid': 123, 'generation': 'a'*32, 'release': str(source), 'metadata_sha256': 'b'*64}
    selected = Adapter(tmp_path/'selected', core)
    other = Adapter(tmp_path/'other', core)
    component, target = request.param, 'local' if request.param == 'agent' else HOST
    actors = {'revision': 1}
    def factory(c, t):
        assert (c, t) == (component, target)
        return selected
    w = ComponentUpdates(source=source, state=tmp_path/'web-state', adapter_factory=factory,
        actor_revision=lambda user: actors['revision'], fingerprint=lambda: dict(core),
        mutation_lock=nullcontext, enforce=False, worker_active=lambda _: False)
    def payload(action='prepare', identifier='a'*32, expected=None, candidate=None, build=None):
        value = dict(action='component_'+action, component=component, target_id=target,
            requested_by_user_id=1, request_id=identifier, expected_operation_id=expected)
        if action == 'apply': value['candidate_id'] = candidate['candidate_id']; build = candidate['build_id']
        if action in {'apply', 'rollback'}:
            value.update(build_id=build, confirmation=confirmation(action, component, target, build))
        return value
    def prepare():
        w.queue(payload(), lambda _: None); w.execute('a'*32)
        return w.candidate()
    return SimpleNamespace(w=w, adapter=selected, other=other, core=core, actors=actors,
        payload=payload, prepare=prepare, component=component, target=target)


def test_status_and_prepare_do_not_switch_or_create_status_journals(workflow):
    x = workflow; old = x.adapter.pointer('current')
    assert x.w.status(x.component, x.target)['ready'] and not x.w.web.exists()
    candidate = x.prepare()
    assert candidate['build_id'] != old and x.adapter.pointer('current') == old
    assert not x.adapter.calls
    assert x.w.status(x.component, x.target)['candidate']['compatible']


def test_exact_update_then_explicit_previous_build_rollback(workflow):
    x = workflow; old = x.adapter.pointer('current'); other = x.other.pointer('current'); core = dict(x.core)
    candidate = x.prepare()
    x.w.queue(x.payload('apply', 'b'*32, 'a'*32, candidate), lambda _: None); x.w.execute('b'*32)
    assert x.adapter.pointer('current') == candidate['build_id'] and x.adapter.pointer('previous') == old
    assert x.adapter.calls == ['stop', 'start'] and x.core == core
    assert x.other.pointer('current') == other and not x.other.calls
    x.w.queue(x.payload('rollback', 'c'*32, 'b'*32, build=old), lambda _: None); x.w.execute('c'*32)
    assert x.adapter.pointer('current') == old and x.adapter.pointer('previous') == candidate['build_id']
    assert x.w.operation()['reason'] == 'component_rolled_back'


@pytest.mark.parametrize('drift', ['actor', 'binding', 'core', 'confirmation', 'candidate', 'checksum'])
def test_drift_and_tamper_never_switch_component(workflow, drift):
    x = workflow; candidate = x.prepare(); payload = x.payload('apply', 'b'*32, 'a'*32, candidate)
    old = x.adapter.pointer('current')
    if drift == 'confirmation':
        payload['confirmation'] = 'UPDATE EVERYTHING'
        with pytest.raises(ValueError): x.w.queue(payload, lambda _: None)
    elif drift == 'candidate':
        payload['candidate_id'] = 'f'*32
        with pytest.raises(ValueError): x.w.queue(payload, lambda _: None)
    else:
        x.w.queue(payload, lambda _: None)
        if drift == 'actor': x.actors['revision'] += 1
        elif drift == 'binding': x.adapter.binding_value += 1
        elif drift == 'core': x.core['generation'] = 'e'*32
        else: (x.w.web/'candidate.tar').write_bytes(b'tampered')
        with pytest.raises(RuntimeError): x.w.execute('b'*32)
    assert x.adapter.pointer('current') == old and not x.adapter.calls


def test_authority_rechecked_after_staging_before_stop(workflow, monkeypatch):
    x = workflow; candidate = x.prepare(); original = x.adapter.store.stage
    def stage(blob, sha):
        result = original(blob, sha); x.actors['revision'] += 1
        return result
    monkeypatch.setattr(x.adapter.store, 'stage', stage)
    x.w.queue(x.payload('apply', 'b'*32, 'a'*32, candidate), lambda _: None)
    with pytest.raises(RuntimeError): x.w.execute('b'*32)
    assert not x.adapter.calls


def test_failed_health_restores_previous_and_clears_standard_journal(workflow, caplog):
    x = workflow; old = x.adapter.pointer('current'); candidate = x.prepare()
    x.adapter.reject = candidate['build_id']
    x.w.queue(x.payload('apply', 'b'*32, 'a'*32, candidate), lambda _: None)
    with pytest.raises(RuntimeError): x.w.execute('b'*32)
    assert x.adapter.pointer('current') == old and x.adapter.running and x.adapter.store.pending() is None
    assert x.w.operation()['reason'] == 'previous_component_ready'
    assert 'phase=activate type=ValueError function=probe' in caplog.text
    assert 'request=' + 'b'*32 in caplog.text
    assert 'unhealthy' not in caplog.text


def test_lost_scheduler_ack_is_not_permission_to_reschedule(workflow):
    x = workflow; calls = []
    def lost(identifier): calls.append(identifier); raise TimeoutError()
    with pytest.raises(RuntimeError): x.w.queue(x.payload(), lost)
    x.w.queue(x.payload(), lost)
    assert calls == ['a'*32]
    with pytest.raises(ValueError): x.w.queue(x.payload(identifier='b'*32), lost)
    assert not x.adapter.calls


def test_proven_preflight_refusal_differs_from_uncertain_persistence(workflow,monkeypatch):
    x=workflow
    x.adapter.running=False
    with pytest.raises(ComponentNotAccepted): x.w.queue(x.payload(),lambda _:pytest.fail('must not schedule'))
    assert x.w.operation() is None
    x.adapter.running=True
    original=x.w.save_operation
    def lost_after_write(record,state,*args):
        original(record,state,*args)
        raise OSError('Lost durability acknowledgement')
    monkeypatch.setattr(x.w,'save_operation',lost_after_write)
    with pytest.raises(OSError): x.w.queue(x.payload(),lambda _:pytest.fail('must not schedule'))
    assert x.w.operation()['request_id']=='a'*32 and not x.adapter.calls


def test_interrupted_prepare_requires_explicit_recovery_and_cleans_only_staging(workflow):
    x = workflow; x.w.queue(x.payload(), lambda _: None)
    op = x.w.operation(); op['updated_at'] = 0
    _write(x.w.web/'operation.json', json.dumps(op).encode())
    (x.w.web/'building.tar').write_bytes(b'interrupted')
    assert x.w.status(x.component, x.target)['recovery_required']
    with pytest.raises(ValueError): x.w.queue(x.payload(identifier='b'*32, expected='a'*32), lambda _: None)
    x.w.queue(x.payload('recover', 'b'*32, 'a'*32), lambda _: None); x.w.execute('b'*32)
    assert not (x.w.web/'building.tar').exists() and not x.adapter.calls
    assert x.w.operation()['reason'] == 'component_recovered'


def test_interrupted_pointer_transaction_recovers_without_replaying_update(workflow):
    x = workflow; old = x.adapter.pointer('current'); candidate = x.prepare()
    new = x.adapter.store.stage(b'new', candidate['sha256'])
    _write(x.adapter.store.journal, json.dumps(dict(schema_version=1, phase='switching', previous=old,
        previous_previous=None, candidate=new, was_active=True)).encode())
    x.adapter.store.link('current', new)
    x.w.queue(x.payload('recover', 'b'*32, 'a'*32), lambda _: None); x.w.execute('b'*32)
    assert x.adapter.pointer('current') == old and x.adapter.calls == ['stop', 'start']
    assert x.adapter.store.pending() is None


def test_read_only_store_open_never_bootstraps_directories(tmp_path):
    with pytest.raises(ValueError): ComponentStore(tmp_path/'missing', tmp_path/'state', create=False)
    assert not (tmp_path/'missing').exists() and not (tmp_path/'state').exists()


@pytest.mark.parametrize('change', [{'target_id': '../../escape'}, {'component': 'runtime'},
    {'artifact': '/tmp/upload'}, {'requested_by_user_id': True}, {'target_id': 'default'}])
def test_no_paths_default_host_or_caller_authority(change):
    value = dict(action='component_status', component='agent', target_id='local', requested_by_user_id=1)
    with pytest.raises(ValueError): validate_request({**value, **change})
