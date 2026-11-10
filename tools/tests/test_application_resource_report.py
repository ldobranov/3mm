import os
import subprocess

import pytest

from tools import application_resource_report as resources


INSTANCE = 'a' * 24
UNIT = f'3mm-application-extension@{INSTANCE}.service'
# The standard systemd template slice contains literal escaped hyphens.
GROUP = rf'/system.slice/system-3mm\x2dapplication\x2dextension.slice/{UNIT}'


@pytest.fixture
def host(tmp_path, monkeypatch):
    (tmp_path / 'cgroup.controllers').write_text('cpu memory pids\n', encoding='ascii')
    # A backslash is a separator on Windows rather than a cgroup name character.
    # The tests use a custom slice there; the Linux tests exercise the real spelling.
    group = f'/system.slice/3mm-apps.slice/{UNIT}' if os.name == 'nt' else GROUP
    directory = tmp_path.joinpath(*group[1:].split('/'))
    directory.mkdir(parents=True)
    (directory / 'cpu.max').write_text('50000 100000\n', encoding='ascii')
    (directory / 'memory.max').write_text('268435456\n', encoding='ascii')
    (directory / 'pids.max').write_text('64\n', encoding='ascii')
    state = dict(Id=UNIT, LoadState='loaded', ActiveState='active', ControlGroup=group, InvocationID='b' * 32)
    state.update(SubState='running', Result='success', NRestarts='0')

    def show(argv, *, capture_output, text, encoding, timeout, check):
        assert argv[:2] == ['/usr/bin/systemctl', 'show'] and argv[-1] == UNIT
        assert set(value for value in argv if value.startswith('--property=')) == {
            f'--property={name}' for name in resources.PROPERTIES}
        return subprocess.CompletedProcess(argv, 0, '\n'.join(f'{name}={value}' for name, value in state.items()))

    monkeypatch.setattr(resources.subprocess, 'run', show)
    return tmp_path, directory, state


def test_reports_kernel_limits_not_template_values(host):
    root, _, _ = host
    assert resources.collect(INSTANCE, cgroup_root=root) == {
        'schema_version': 1, 'unit': UNIT, 'scope': 'unit_cgroup', 'state': 'observed',
        'supervision': {'state': 'active', 'result': 'success', 'restart_count': 0},
        'limits': {
            'cpu': {'state': 'os_enforced', 'period_usec': 100000, 'quota_usec': 50000},
            'memory': {'state': 'os_enforced', 'max_bytes': 268435456},
            'tasks': {'state': 'os_enforced', 'max_tasks': 64},
        },
    }


@pytest.mark.parametrize(('active', 'substate', 'result', 'restarts', 'expected'), [
    ('inactive', 'dead', 'success', '0', 'stopped'),
    ('activating', 'auto-restart', 'exit-code', '2', 'restarting'),
    ('activating', 'auto-restart-queued', 'exit-code', '2', 'restarting'),
    ('activating', 'start', 'success', '0', 'starting'),
    ('failed', 'failed', 'oom-kill', '1', 'failed'),
    ('failed', 'failed', 'start-limit-hit', '5', 'failed'),
])
def test_reports_supervision_without_claiming_live_limits(host, monkeypatch, active, substate, result, restarts, expected):
    root, _, state = host
    state.update(ActiveState=active, SubState=substate, Result=result, NRestarts=restarts,
                 ControlGroup='', InvocationID='0' * 32)
    monkeypatch.setattr(resources, '_limit', lambda *_: pytest.fail('Read a non-running cgroup'))
    report = resources.collect(INSTANCE, cgroup_root=root)
    assert report['state'] == 'not_running' and 'limits' not in report
    assert report['supervision'] == {'state': expected, 'result': result, 'restart_count': int(restarts)}


@pytest.mark.parametrize(('properties', 'result'), [
    ({}, None),
    ({'Result': 'unexpected detail', 'NRestarts': 'bad'}, 'other'),
    ({'Result': '', 'NRestarts': str(2**32)}, None),
])
def test_missing_or_invalid_supervision_values_do_not_hide_limits(host, properties, result):
    root, _, state = host
    for field in ('SubState', 'Result', 'NRestarts'):
        state.pop(field)
    state.update(properties)
    report = resources.collect(INSTANCE, cgroup_root=root)
    assert report['state'] == 'observed' and 'limits' in report
    assert report['supervision'] == {'state': 'active', 'result': result, 'restart_count': None}


def test_missing_and_malformed_limits_are_not_treated_as_unbounded(host):
    root, directory, _ = host
    (directory / 'cpu.max').write_text('max 100000\n', encoding='ascii')
    (directory / 'memory.max').unlink()
    (directory / 'pids.max').write_text('untrusted contents', encoding='ascii')
    assert resources.collect(INSTANCE, cgroup_root=root)['limits'] == {
        'cpu': {'state': 'not_set_here', 'period_usec': 100000},
        'memory': {'state': 'unavailable', 'reason': 'controller_file_absent'},
        'tasks': {'state': 'unavailable', 'reason': 'invalid_value'},
    }


@pytest.mark.parametrize(('changes', 'expected'), [
    ({'LoadState': 'not-found'}, 'not_found'),
    ({'ActiveState': 'inactive'}, 'not_running'),
    ({'ControlGroup': f'/system.slice/../{UNIT}'}, 'unavailable'),
    ({'ControlGroup': '/system.slice/unrelated.service'}, 'unavailable'),
    ({'InvocationID': '0' * 32}, 'unavailable'),
])
def test_does_not_read_limits_for_unverified_unit(host, monkeypatch, changes, expected):
    root, _, state = host
    state.update(changes)
    monkeypatch.setattr(resources, '_limit', lambda *_: pytest.fail('Read an unverified cgroup'))
    report = resources.collect(INSTANCE, cgroup_root=root)
    assert report['state'] == expected and 'limits' not in report


def test_does_not_claim_v2_when_host_hides_the_hierarchy(host):
    root, _, _ = host
    (root / 'cgroup.controllers').unlink()
    report = resources.collect(INSTANCE, cgroup_root=root)
    assert report['state'] == 'unsupported' and 'limits' not in report


def test_distinguishes_missing_host_controller_from_missing_unit_file(host):
    root, directory, _ = host
    (root / 'cgroup.controllers').write_text('cpu pids\n', encoding='ascii')
    (directory / 'memory.max').unlink()
    limits = resources.collect(INSTANCE, cgroup_root=root)['limits']
    assert limits['memory'] == {'state': 'unavailable', 'reason': 'controller_not_available_on_host'}
    assert limits['cpu']['state'] == limits['tasks']['state'] == 'os_enforced'


def test_discards_sample_if_service_restarts_during_read(host, monkeypatch):
    root, _, state = host
    read = resources._limit

    def restart(*args):
        state['InvocationID'] = 'c' * 32
        return read(*args)

    monkeypatch.setattr(resources, '_limit', restart)
    report = resources.collect(INSTANCE, cgroup_root=root)
    assert report['reason'] == 'unit_or_cgroup_changed' and 'limits' not in report
    assert 'supervision' not in report


def test_discards_supervision_if_failed_service_starts_between_samples(host, monkeypatch):
    root, _, state = host
    state.update(ActiveState='failed', SubState='failed', Result='oom-kill')
    show = resources._unit_state

    def start_after_read(unit):
        sample = show(unit)
        state.update(ActiveState='activating', SubState='start', Result='success')
        return sample

    monkeypatch.setattr(resources, '_unit_state', start_after_read)
    report = resources.collect(INSTANCE, cgroup_root=root)
    assert report['reason'] == 'unit_or_cgroup_changed'
    assert 'supervision' not in report and 'limits' not in report


def test_rejects_arbitrary_systemd_targets_before_running_a_command(host, monkeypatch):
    root, _, _ = host
    monkeypatch.setattr(resources, '_unit_state', lambda _: pytest.fail('Called systemd with untrusted target'))
    with pytest.raises(ValueError, match='instance ID'):
        resources.collect('3mm-core.service', cgroup_root=root)
