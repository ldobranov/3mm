"""Installer transition with disposable pointers and doubled platform adapters.

No system users, application factories, real systemd, network or device updates.
"""
from pathlib import Path
from types import SimpleNamespace
import json
import os
import stat
import sys

import pytest

from deployment import component_transition as transition

INSTALLED_TRANSITION_STATE = transition.STATE
REAL_STAGE = transition.stage

@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(transition, 'OWNER', os.geteuid() if hasattr(os, 'geteuid') else 0)
    monkeypatch.setattr(transition, 'STATE', tmp_path / 'state/transitions')
    monkeypatch.setattr(transition, 'HOSTS', tmp_path / 'hosts')
    monkeypatch.setattr(transition, 'HOST_STATE', tmp_path / 'host-state')
    monkeypatch.setattr(transition, 'SERVICE_ROOTS', {name: (tmp_path / 'services' / name,
        tmp_path / 'service-state' / name) for name in transition.SERVICE_ROOTS})
    monkeypatch.setattr(transition, 'RUNTIME_ROOTS', {name: (tmp_path / 'runtimes' / name,
        tmp_path / 'runtime-state' / name) for name in transition.RUNTIME_ROOTS})
    source = tmp_path / 'releases/candidate'
    previous = tmp_path / 'releases/previous'
    source.mkdir(parents=True)
    previous.mkdir()
    (tmp_path / 'state').mkdir()
    events = []
    artifacts = {}
    activity = {}
    made = {}

    def trust(path):
        path = Path(path)
        require_inside = path.is_relative_to(tmp_path)
        assert require_inside
        while path != tmp_path.parent:
            info = path.lstat()
            assert stat.S_ISDIR(info.st_mode) and not info.st_mode & 0o022
            path = path.parent

    def trusted_source(path):
        assert path in {source, previous}
        return path

    def metadata(item, identifier, layout):
        value = artifacts[item.key, identifier]
        if value['layout'] != layout:
            raise ValueError('wrong source namespace or invalid artifact')
        return value['metadata']

    class Store:
        def __init__(self, item):
            self.item = item

        def metadata(self, identifier):
            return metadata(self.item, identifier, 'neutral')

    def legacy_worker(selected, operation, key, identifier, *, start=False):
        assert selected == previous
        item = transition.entry(key)
        value = metadata(item, identifier, 'legacy')
        events.append((operation, key, identifier))
        if operation == 'health' and start:
            activity[key] = True
        return transition.proof(value)

    def stage(item, selected, current, image, built, *, metadata_sha256):
        assert selected == source
        assert metadata_sha256 == transition.digest(transition.encoded(
            artifacts[item.key, current]['metadata']))
        events.append(('stage', item.key, image))
        identifier = transition.digest(('new:' + item.key).encode())
        add_artifact(item, identifier, 'neutral', image=image)
        return identifier

    class Control:
        def __init__(self, item):
            self.item = item

        def stop(self):
            events.append(('stop', self.item.key))
            activity[self.item.key] = False

    def verify(item, identifier, *, start=False):
        assert transition.pair(item)['current'] == identifier
        events.append(('verify', item.key, identifier))
        activity[item.key] = True

    def add_artifact(item, identifier, layout, *, image=False):
        directory = item.releases / identifier
        directory.mkdir(parents=True, exist_ok=True)
        vendor = directory / 'vendor'
        vendor.mkdir(exist_ok=True)
        artifacts[item.key, identifier] = {'layout': layout, 'metadata': {
            'build_id': identifier, 'binding': {'dependencies': {'Pillow': '12.1.0'} if image else {}}}}

    def install(key, *, current='legacy', previous_layout=None, running=False, image=False):
        item = transition.entry(key)
        item.root.mkdir(parents=True, exist_ok=True)
        item.state.mkdir(parents=True, exist_ok=True)
        item.releases.mkdir(parents=True, exist_ok=True)
        current_id = transition.digest((key + ':old-current').encode())
        previous_id = transition.digest((key + ':old-previous').encode()) if previous_layout else None
        add_artifact(item, current_id, current, image=image)
        (item.root / 'current').symlink_to(item.releases / current_id, target_is_directory=True)
        if previous_id:
            add_artifact(item, previous_id, previous_layout)
            (item.root / 'previous').symlink_to(item.releases / previous_id, target_is_directory=True)
        activity[key] = running
        made[key] = {'current': current_id, 'previous': previous_id}
        return item

    monkeypatch.setattr(transition, 'trusted_directory', trust)
    monkeypatch.setattr(transition, 'trusted_source', trusted_source)
    monkeypatch.setattr(transition, 'store_for', Store)
    monkeypatch.setattr(transition, 'worker', legacy_worker)
    monkeypatch.setattr(transition, 'stage', stage)
    monkeypatch.setattr(transition, 'active', lambda item: activity[item.key])
    monkeypatch.setattr(transition, 'control', Control)
    monkeypatch.setattr(transition, 'verify_component', verify)
    return SimpleNamespace(source=source, previous=previous, install=install, events=events,
                           artifacts=artifacts, activity=activity, original=made, root=tmp_path)


def test_absent_clean_stores_need_no_transition_or_service_actions(lab):
    prepared = transition.prepare(lab.source, None, 'full')
    assert prepared['entries'] == []
    for action in ('switch', 'verify', 'commit'):
        transition.operate(action, lab.source, None, 'full')
    assert lab.events == []


def test_transition_journal_is_outside_service_owned_core_state(lab, monkeypatch):
    assert not INSTALLED_TRANSITION_STATE.is_relative_to(Path('/var/lib/3mm'))
    core_state = lab.root / 'core-service-owned-state'
    core_state.mkdir(mode=0o770)
    # The real installer assigns the Core state tree to 3mm. Model an untrusted
    # ancestor there; do not relax the journal's root-owned ancestor rule.
    original = transition.trusted_directory

    def trusted(path):
        assert not path.is_relative_to(core_state)
        original(path)

    monkeypatch.setattr(transition, 'trusted_directory', trusted)
    transition.prepare(lab.source, None, 'node')
    assert transition.journal_path(lab.source).is_file()


def test_neutral_current_and_previous_stay_exactly_pinned(lab):
    item = lab.install('service:agent', current='neutral', previous_layout='neutral', running=True)
    before = transition.pair(item)
    prepared = transition.prepare(lab.source, lab.previous, 'node')
    assert prepared['entries'][0]['changed'] is False
    for action in ('switch', 'verify', 'commit'):
        transition.operate(action, lab.source, lab.previous, 'node')
    assert transition.pair(item) == before
    assert lab.events == []


def test_transition_all_existing_roles_and_disabled_image_host_without_data_changes(lab):
    keys = [*('service:' + name for name in transition.SERVICE_ROOTS),
            *('runtime:' + name for name in transition.RUNTIME_ROOTS), 'host:default',
            'host:' + 'a' * 24, 'host:' + 'b' * 24]
    items = [lab.install(key, previous_layout='legacy', running=key not in {
        'host:default', 'host:' + 'b' * 24}, image=key == 'host:' + 'b' * 24) for key in keys]
    sentinel = lab.root / 'application-package-data-rights'
    sentinel.write_bytes(b'unchanged')
    prepared = transition.prepare(lab.source, lab.previous, 'full')
    assert {record['key'] for record in prepared['entries']} == set(keys)
    assert all(record['changed'] and record['new']['previous'] is None for record in prepared['entries'])
    assert ('stage', 'host:' + 'b' * 24, True) in lab.events
    assert not any(event[0] == 'stop' for event in lab.events)
    for item in items:
        assert transition.pair(item) == lab.original[item.key]
    transition.operate('switch', lab.source, lab.previous, 'full')
    transition.operate('verify', lab.source, lab.previous, 'full')
    result = transition.operate('commit', lab.source, lab.previous, 'full')
    assert result['phase'] == 'committed'
    assert not any(event[0] in {'stop', 'verify'} and event[1] in {'host:default', 'host:' + 'b' * 24}
                   for event in lab.events)
    assert sentinel.read_bytes() == b'unchanged'
    for item in items:
        assert all((item.releases / identifier).is_dir()
                   for identifier in lab.original[item.key].values() if identifier)
    assert transition.journal_path(lab.source).is_file()


def test_node_inventory_is_only_agent_even_when_other_roles_exist(lab):
    lab.install('service:agent')
    old_optional = lab.install('service:session-relay')
    prepared = transition.prepare(lab.source, lab.previous, 'node')
    assert [record['key'] for record in prepared['entries']] == ['service:agent']
    assert transition.pair(old_optional) == lab.original[old_optional.key]


def test_role_planner_started_agent_is_probed_without_enabling_or_restarting(lab, monkeypatch):
    item = lab.install('service:agent', running=False)
    transition.prepare(lab.source, lab.previous, 'node')
    transition.operate('switch', lab.source, lab.previous, 'node')
    lab.activity[item.key] = True  # Existing authorized role planner, not this helper.
    checks = []
    monkeypatch.setattr(transition, 'verify_component',
                        lambda item, identifier, *, start: checks.append((item.key, identifier, start)))
    result = transition.operate('verify', lab.source, lab.previous, 'node')
    assert result['phase'] == 'verified'
    assert checks == [(item.key, transition.pair(item)['current'], False)]


def test_full_profile_node_role_proves_agent_identity_without_a_local_core(monkeypatch):
    from deployment import service_component

    identifier = 'a' * 64
    calls = []
    monkeypatch.setattr(transition, 'store_for', lambda item: SimpleNamespace(
        metadata=lambda build: calls.append(('metadata', build))))
    monkeypatch.setattr(service_component, 'fingerprint', lambda: pytest.fail('No Core exists for this role'))
    monkeypatch.setattr(service_component, 'health', lambda *args: pytest.fail('Independent update continuity is not installer readiness'))
    monkeypatch.setattr(service_component, '_http_identity', lambda url, **kwargs: {
        'component': 'agent', 'build_id': identifier, 'pid': 123})
    monkeypatch.setattr(transition.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout='123\n'))
    transition.service_readiness(transition.entry('service:agent'),
        SimpleNamespace(active=lambda: True, unit='3mm-agent.service'), identifier)
    assert calls == [('metadata', identifier)]


def test_rollback_stops_planner_started_components_before_any_pointer_restore(lab, monkeypatch):
    items = [lab.install('service:agent'), lab.install('service:session-relay')]
    transition.prepare(lab.source, lab.previous, 'full')
    transition.operate('switch', lab.source, lab.previous, 'full')
    for item in items:
        lab.activity[item.key] = True
    original = transition.set_pointer

    def restore_pointer(item, name, identifier):
        assert all(not lab.activity[other.key] for other in items)
        original(item, name, identifier)

    monkeypatch.setattr(transition, 'set_pointer', restore_pointer)
    transition.operate('restore', lab.source, lab.previous, 'full')
    transition.operate('resume', lab.source, lab.previous, 'full')
    assert not any(event[0] == 'health' for event in lab.events)
    assert all(transition.pair(item) == lab.original[item.key] for item in items)


@pytest.mark.parametrize('inspection,returncode,accepted', [
    ('LoadState=not-found\nActiveState=inactive\nMainPID=0\n', 1, True),
    ('', 1, False),
    ('LoadState=loaded\nActiveState=failed\nMainPID=0\n', 0, False),
    ('LoadState=not-found\nActiveState=active\nMainPID=100\n', 0, False),
])
def test_absent_unit_after_failed_clean_install_is_not_a_service_inspection_error(
        monkeypatch, inspection, returncode, accepted):
    monkeypatch.setattr(transition, 'control', lambda item: SimpleNamespace(unit='3mm-agent.service'))
    results = iter([SimpleNamespace(returncode=4), SimpleNamespace(returncode=returncode, stdout=inspection)])
    monkeypatch.setattr(transition.subprocess, 'run', lambda *args, **kwargs: next(results))
    if accepted:
        assert transition.active(transition.entry('service:agent')) is False
    else:
        with pytest.raises(ValueError):
            transition.active(transition.entry('service:agent'))


@pytest.mark.parametrize('invalid', ['current', 'previous', 'pending', 'partial'])
def test_invalid_or_pending_store_fails_before_staging_or_stopping(lab, invalid):
    item = lab.install('service:agent', previous_layout='legacy')
    if invalid in {'current', 'previous'}:
        identifier = lab.original[item.key][invalid]
        lab.artifacts[item.key, identifier]['layout'] = 'corrupt'
    elif invalid == 'pending':
        (item.state / 'transaction.json').write_text('{}')
    else:
        (item.root / 'current').unlink()
    with pytest.raises(ValueError):
        transition.prepare(lab.source, lab.previous, 'node')
    assert not any(event[0] in {'stage', 'stop'} for event in lab.events)
    assert not transition.STATE.exists()


def test_prepared_retry_reuses_staged_candidate_without_rebuilding(lab):
    lab.install('service:agent')
    original = transition.prepare(lab.source, lab.previous, 'node')
    count = len([event for event in lab.events if event[0] == 'stage'])
    assert transition.prepare(lab.source, lab.previous, 'node') == original
    assert len([event for event in lab.events if event[0] == 'stage']) == count


def test_partial_switch_restores_every_original_pair_before_resume(lab, monkeypatch):
    agent = lab.install('service:agent', previous_layout='legacy', running=True)
    runtime = lab.install('runtime:platform-runtime', previous_layout='legacy', running=True)
    transition.prepare(lab.source, lab.previous, 'full')
    setter = transition.set_pointer
    switched = []

    def interrupted(item, name, identifier):
        setter(item, name, identifier)
        switched.append((item.key, name))
        if len(switched) == 3:
            raise OSError('simulated interruption after a durable pointer change')

    monkeypatch.setattr(transition, 'set_pointer', interrupted)
    with pytest.raises(OSError):
        transition.operate('switch', lab.source, lab.previous, 'full')
    monkeypatch.setattr(transition, 'set_pointer', setter)
    transition.operate('restore', lab.source, lab.previous, 'full')
    for item in (agent, runtime):
        assert transition.pair(item) == lab.original[item.key]
    assert not any(event[0] == 'health' for event in lab.events)
    transition.operate('resume', lab.source, lab.previous, 'full')
    assert {event[1] for event in lab.events if event[0] == 'health'} == {agent.key, runtime.key}


def test_unrelated_pointer_replacement_fences_global_recovery(lab):
    item = lab.install('service:agent', previous_layout='legacy')
    prepared = transition.prepare(lab.source, lab.previous, 'node')
    transition.operate('switch', lab.source, lab.previous, 'node')
    unrelated = 'f' * 64
    (item.releases / unrelated).mkdir()
    transition.set_pointer(item, 'current', unrelated)
    before = transition.pair(item)
    with pytest.raises(ValueError, match='Unrelated component'):
        transition.operate('restore', lab.source, lab.previous, 'node')
    assert transition.pair(item) == before
    assert prepared['entries'][0]['old'] == lab.original[item.key]


def test_changed_original_artifact_fences_switch_without_replacing_any_pin(lab):
    item = lab.install('service:agent')
    transition.prepare(lab.source, lab.previous, 'node')
    lab.artifacts[item.key, lab.original[item.key]['current']]['metadata']['changed'] = True
    with pytest.raises(ValueError, match='Original component artifact changed'):
        transition.operate('switch', lab.source, lab.previous, 'node')
    assert transition.pair(item) == lab.original[item.key]
    assert not any(event[0] == 'stop' for event in lab.events)


def test_active_application_health_failure_keeps_global_rollback_available(lab, monkeypatch):
    item = lab.install('host:' + 'c' * 24, previous_layout='legacy', running=True)
    transition.prepare(lab.source, lab.previous, 'full')
    transition.operate('switch', lab.source, lab.previous, 'full')
    monkeypatch.setattr(transition, 'verify_component', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('not ready')))
    with pytest.raises(ValueError):
        transition.operate('verify', lab.source, lab.previous, 'full')
    transition.operate('restore', lab.source, lab.previous, 'full')
    assert transition.pair(item) == lab.original[item.key]
    transition.operate('resume', lab.source, lab.previous, 'full')


@pytest.mark.parametrize('bad', ['duplicate', 'source', 'phase', 'pointer', 'role'])
def test_journal_shape_and_exact_source_bindings_fail_closed(lab, bad):
    lab.install('service:agent')
    value = transition.prepare(lab.source, lab.previous, 'node')
    if bad == 'duplicate':
        value['entries'].append(value['entries'][0])
    elif bad == 'source':
        value['previous_source'] = str(lab.source)
    elif bad == 'phase':
        value['phase'] = 'assume-success'
    elif bad == 'pointer':
        value['entries'][0]['new']['current'] = '../../outside'
    else:
        value['entries'][0]['key'] = 'service:public-web'
    transition.save(transition.journal_path(lab.source), value)
    with pytest.raises(ValueError):
        transition.operate('switch', lab.source, lab.previous, 'node')


def test_lock_attestation_uses_same_inherited_fd_and_never_opens_another(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, 'fcntl', SimpleNamespace(LOCK_EX=2, LOCK_NB=4,
                                                            flock=lambda *args: calls.append(args)))
    inode = SimpleNamespace(st_uid=transition.OWNER, st_mode=stat.S_IFREG | 0o600,
                            st_dev=1, st_ino=2, st_nlink=1)
    monkeypatch.setattr(os, 'fstat', lambda fd: inode)
    monkeypatch.setattr(Path, 'lstat', lambda path: inode)
    monkeypatch.setattr(os, 'readlink', lambda path: '/run/lock/3mm-release-mutation.lock')
    monkeypatch.setattr(os, 'open', lambda *args, **kwargs: pytest.fail('must not open a second lock'))
    transition.require_installer_lock()
    assert calls == [(9, 6)]
    monkeypatch.setattr(os, 'readlink', lambda path: '/tmp/caller-selected-lock')
    with pytest.raises(ValueError):
        transition.require_installer_lock()
    assert calls == [(9, 6)]


@pytest.mark.parametrize('unsafe', ['writable', 'different_inode', 'symlink', 'hardlink'])
def test_installer_lock_requires_the_trusted_canonical_inode(monkeypatch, unsafe):
    monkeypatch.setitem(sys.modules, 'fcntl', SimpleNamespace(LOCK_EX=2, LOCK_NB=4,
        flock=lambda *args: pytest.fail('Untrusted fd must not be locked')))
    inode = dict(st_uid=transition.OWNER, st_mode=stat.S_IFREG | 0o600, st_dev=1, st_ino=2, st_nlink=1)
    actual = dict(inode)
    if unsafe == 'writable':
        actual['st_mode'] |= 0o020
    elif unsafe == 'different_inode':
        actual['st_ino'] = 3
    elif unsafe == 'symlink':
        actual['st_mode'] = stat.S_IFLNK | 0o777
    else:
        actual['st_nlink'] = 2
    monkeypatch.setattr(os, 'fstat', lambda fd: SimpleNamespace(**inode))
    monkeypatch.setattr(Path, 'lstat', lambda path: SimpleNamespace(**actual))
    monkeypatch.setattr(os, 'readlink', lambda path: '/run/lock/3mm-release-mutation.lock')
    with pytest.raises(transition.TransitionError) as failure:
        transition.require_installer_lock()
    assert failure.value.code == 'installer_lock_required'


def test_previous_adapter_subprocess_has_closed_command_environment_and_bounds(tmp_path, monkeypatch):
    seen = []
    expected = {'metadata_sha256': 'a' * 64, 'image_provider': False}

    def fake_run(arguments, **options):
        seen.append((arguments, options))
        options['stdout'].write(json.dumps(expected).encode())
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(transition.subprocess, 'run', fake_run)
    assert transition.worker(tmp_path, 'inspect', 'service:agent', 'b' * 64) == expected
    arguments, options = seen[0]
    assert arguments[:3] == [str(tmp_path / '.venv/bin/python'), '-I', '-B']
    assert arguments[4:8] == ['_worker', '--source', str(tmp_path), '--operation']
    assert options['env'] == {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}
    assert options['timeout'] == 60 and options['preexec_fn'] is transition._limit_worker_output
    assert options['pass_fds'] == ()
    assert '--start' not in arguments
    transition.worker(tmp_path, 'health', 'service:agent', 'b' * 64, start=True)
    assert seen[-1][1]['pass_fds'] == (9,)
    assert seen[-1][1]['timeout'] == 240
    assert '--start' in seen[-1][0]


def test_previous_health_worker_requires_lock_before_any_probe_or_start(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(sys, 'argv', ['component_transition', '_worker', '--source', str(tmp_path),
        '--operation', 'health', '--entry', 'service:agent', '--build', 'a' * 64, '--start'])
    monkeypatch.setattr(os, 'geteuid', lambda: transition.OWNER)
    monkeypatch.setattr(transition, 'trusted_source', lambda path: path)
    monkeypatch.setattr(transition, 'store_for', lambda *args: pytest.fail('No read/probe before lock proof'))
    monkeypatch.setattr(transition, 'verify_component', lambda *args, **kwargs: pytest.fail('No unlocked start'))

    def refuse_lock():
        calls.append('lock')
        raise transition.TransitionError('Transition requires the inherited installer release lock')

    monkeypatch.setattr(transition, 'require_installer_lock', refuse_lock)
    with pytest.raises(transition.TransitionError) as failure:
        transition.main()
    assert calls == ['lock']
    assert transition.failure_result(failure.value) == {'status': 'refused',
        'error_code': 'installer_lock_required', 'action': '_worker', 'entry': 'service:agent'}


def test_refusals_are_actionable_but_never_expose_paths_or_worker_output(lab, monkeypatch):
    item = lab.install('service:agent')
    (item.state / 'transaction.json').write_text('{}')
    with pytest.raises(transition.TransitionError) as failure:
        transition.prepare(lab.source, lab.previous, 'node')
    assert transition.failure_result(failure.value) == {'status': 'refused',
        'error_code': 'pending_component_operation', 'action': 'prepare', 'entry': 'service:agent'}
    for error in (OSError('/private/token=secret'), ValueError('/private/key=secret'),
                  transition.TransitionError('/private/provider=secret')):
        output = json.dumps(transition.failure_result(error))
        assert '/private/' not in output and 'secret' not in output
    transition._CONTEXT.clear()
    with pytest.raises(transition.TransitionError):
        transition.entry('host:/private/secret')
    assert 'entry' not in transition.failure_result(ValueError('secret'))


@pytest.mark.parametrize('reply,returncode,code', [
    (b'/private/secret', 1, 'previous_adapter_refused'),
    (b'/private/secret', 0, 'previous_adapter_response_invalid'),
    (b'{"metadata_sha256":123,"image_provider":false}', 0, 'previous_adapter_response_invalid'),
])
def test_previous_adapter_refusal_never_echoes_its_response(tmp_path, monkeypatch, reply, returncode, code):
    def fake_run(arguments, **options):
        options['stdout'].write(reply)
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr(transition.subprocess, 'run', fake_run)
    with pytest.raises(transition.TransitionError) as failure:
        transition.worker(tmp_path, 'inspect', 'service:agent', 'a' * 64)
    assert transition.failure_result(failure.value)['error_code'] == code
    assert 'secret' not in json.dumps(transition.failure_result(failure.value))


def test_completed_rollback_requires_explicit_bounded_retry_and_retains_evidence(lab):
    item = lab.install('service:agent', previous_layout='legacy', running=True)
    transition.prepare(lab.source, lab.previous, 'node')
    transition.operate('switch', lab.source, lab.previous, 'node')
    transition.operate('restore', lab.source, lab.previous, 'node')
    prior = transition.operate('resume', lab.source, lab.previous, 'node')
    before = transition.journal_path(lab.source).read_bytes()
    with pytest.raises(transition.TransitionError) as failure:
        transition.prepare(lab.source, lab.previous, 'node')
    assert failure.value.code == 'completed_rollback_retry_required'
    retried = transition.prepare(lab.source, lab.previous, 'node', retry_rolled_back=True)
    assert retried['phase'] == 'prepared'
    assert retried['entries'][0]['old'] == prior['entries'][0]['old'] == lab.original[item.key]
    attempts = list(transition.journal_path(lab.source).parent.glob('rolled-back-*.json'))
    assert len(attempts) == 1 and attempts[0].read_bytes() == before


@pytest.mark.parametrize('phase', ['switching', 'switched', 'restoring', 'restored', 'committed'])
def test_retry_flag_cannot_erase_an_interrupted_or_unfinished_transition(lab, phase):
    lab.install('service:agent')
    value = transition.prepare(lab.source, lab.previous, 'node')
    value['phase'] = phase
    path = transition.journal_path(lab.source)
    transition.save(path, value)
    before = path.read_bytes()
    with pytest.raises(transition.TransitionError) as failure:
        transition.prepare(lab.source, lab.previous, 'node', retry_rolled_back=True)
    assert failure.value.code == 'recovery_required'
    assert path.read_bytes() == before
    assert not list(path.parent.glob('rolled-back-*.json'))


def test_first_install_completed_rollback_can_retry_without_starting_any_old_service(lab):
    transition.prepare(lab.source, None, 'node')
    transition.operate('restore', lab.source, None, 'node')
    completed = transition.operate('resume', lab.source, None, 'node')
    assert completed['phase'] == 'resumed' and lab.events == []
    assert transition.prepare(lab.source, None, 'node', retry_rolled_back=True)['phase'] == 'prepared'


def test_host_inventory_is_bounded_and_never_follows_instance_symlinks(lab):
    instances = transition.HOSTS / 'instances'
    instances.mkdir(parents=True)
    (instances / ('d' * 24)).symlink_to(lab.previous, target_is_directory=True)
    with pytest.raises(ValueError):
        transition.discover('full')
    (instances / ('d' * 24)).unlink()
    (instances / ('a' * 24)).mkdir()
    (instances / ('b' * 24)).mkdir()
    original_limit = transition.MAX_INSTANCES
    transition.MAX_INSTANCES = 1
    try:
        with pytest.raises(ValueError):
            transition.discover('full')
    finally:
        transition.MAX_INSTANCES = original_limit


@pytest.mark.parametrize('mismatch', ['python_tag', 'platform', 'metadata'])
def test_borrowed_native_host_dependencies_require_verified_exact_target(lab, monkeypatch, mismatch):
    from deployment import application_host_component as host

    item = lab.install('host:default', image=True)
    identifier = lab.original[item.key]['current']
    target = {'python_tag': 'cpython-313', 'platform': 'linux-aarch64', 'machine': 'aarch64'}
    metadata = {'binding': {'target': dict(target)}}
    expected = transition.digest(transition.encoded(metadata))
    if mismatch in target:
        metadata['binding']['target'][mismatch] = 'incompatible'
        expected = transition.digest(transition.encoded(metadata))
    else:
        metadata['changed'] = True
    (item.releases / identifier / 'component.json').write_bytes(transition.encoded(metadata))
    monkeypatch.setattr(host, 'target_identity', lambda: target)
    monkeypatch.setattr(host, 'build_component', lambda *args, **kwargs: pytest.fail('No ABI-mismatched build'))
    original_path = list(sys.path)
    with pytest.raises(transition.TransitionError) as failure:
        # Call the real staging boundary, not the fixture's doubled builder.
        REAL_STAGE(item, lab.source, identifier, True, {}, metadata_sha256=expected)
    assert failure.value.code == 'host_dependency_target_mismatch'
    assert sys.path == original_path


def test_matching_native_host_vendor_is_used_only_during_the_locked_build(lab, monkeypatch):
    from deployment import application_host_component as host

    item = lab.install('host:default', image=True)
    identifier = lab.original[item.key]['current']
    target = {'python_tag': 'cpython-313', 'platform': 'linux-aarch64', 'machine': 'aarch64'}
    metadata = {'binding': {'target': target}}
    (item.releases / identifier / 'component.json').write_bytes(transition.encoded(metadata))
    monkeypatch.setattr(host, 'target_identity', lambda: target)
    calls = []

    def build(source, *, image_provider):
        assert sys.path[-1] == str(item.releases / identifier / 'vendor')
        calls.append((source, image_provider))
        return b'component', {}

    monkeypatch.setattr(host, 'build_component', build)
    monkeypatch.setattr(transition, 'store_for', lambda item: SimpleNamespace(
        stage=lambda blob, expected: transition.digest(blob)))
    original_path = list(sys.path)
    result = REAL_STAGE(item, lab.source, identifier, True, {},
                        metadata_sha256=transition.digest(transition.encoded(metadata)))
    assert result == transition.digest(b'component') and calls == [(lab.source, True)]
    assert sys.path == original_path
