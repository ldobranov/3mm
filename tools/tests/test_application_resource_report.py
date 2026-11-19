import os
import subprocess

import pytest

from deployment import service_resources as resources


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
    for parent in (directory.parent, directory.parent.parent):
        for filename, value in [('cpu.max', 'max 100000'), ('memory.max', 'max'), ('pids.max', 'max')]:
            (parent / filename).write_text(value, encoding='ascii')
    (directory / 'cpu.max').write_text('50000 100000\n', encoding='ascii')
    (directory / 'memory.max').write_text('268435456\n', encoding='ascii')
    (directory / 'pids.max').write_text('64\n', encoding='ascii')
    (directory / 'memory.current').write_text('5242880\n', encoding='ascii')
    (directory / 'pids.current').write_text('3\n', encoding='ascii')
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
        'usage': {'memory_bytes': 5242880, 'tasks': 3},
        'main_process_fds': {'state': 'unavailable'},
        'service_policy': dict(restart=None, restart_delay=None, start_window=None, start_burst=None,
                               stop_timeout=None, private_network=None, unix_sockets_only=None),
        'hierarchy_limits': {
            'cpu': {'state': 'os_enforced', 'period_usec': 100000, 'quota_usec': 50000, 'source': 'unit', 'complete': True},
            'memory': {'state': 'os_enforced', 'max_bytes': 268435456, 'source': 'unit', 'complete': True},
            'tasks': {'state': 'os_enforced', 'max_tasks': 64, 'source': 'unit', 'complete': True},
        },
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


@pytest.mark.parametrize('bad', [None, b'-1', b'max', b'\xff', b'0' * 64, b'18446744073709551616'])
def test_missing_or_invalid_usage_does_not_hide_limits_or_become_zero(host, bad):
    root, directory, _ = host
    path = directory / 'memory.current'
    if bad is None:
        path.unlink()
    else:
        path.write_bytes(bad)
    (directory / 'pids.current').write_text('0\n')
    report = resources.collect(INSTANCE, cgroup_root=root)
    assert report['usage'] == {'memory_bytes': None, 'tasks': 0}
    assert report['limits']['memory']['max_bytes'] == 268435456


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


def test_strictest_visible_cap_can_be_shared_or_defined_at_mount_root(host):
    root, unit, _ = host
    (unit.parent / 'cpu.max').write_text('60000 200000')  # 30% < 50%, despite larger quota.
    (unit.parent / 'pids.max').write_text('90')
    (unit.parent.parent / 'pids.max').write_text('32')
    (unit / 'memory.max').write_text('max')
    (root / 'memory.max').write_text('16777216')  # Delegated mount, not the host-global root.
    values = resources.collect(INSTANCE, cgroup_root=root)
    assert values['limits']['tasks']['max_tasks'] == 64
    caps = values['hierarchy_limits']
    assert all(row['source'] == 'parent' and row['complete'] for row in caps.values())
    assert (caps['cpu']['quota_usec'], caps['cpu']['period_usec']) == (60000, 200000)
    assert caps['tasks']['max_tasks'] == 32 and caps['memory']['max_bytes'] == 16777216


def test_incomplete_ancestry_is_not_proof_of_capacity(host, monkeypatch):
    root, unit, _ = host
    (unit / 'cpu.max').write_text('max 100000')
    (unit / 'memory.max').write_text('max')
    (unit.parent / 'memory.max').write_text('not a number')
    (unit.parent / 'pids.max').unlink()
    caps = resources.collect(INSTANCE, cgroup_root=root)['hierarchy_limits']
    assert caps['cpu'] == {'state': 'no_visible_cap', 'complete': True}
    assert caps['memory'] == {'state': 'unavailable', 'complete': False}
    assert caps['tasks'] == {'state': 'os_enforced', 'source': 'unit', 'max_tasks': 64, 'complete': False}
    monkeypatch.setattr(resources, 'MAX_PARENT_LEVELS', 1)
    caps = resources.collect(INSTANCE, cgroup_root=root)['hierarchy_limits']
    assert all(not cap['complete'] for cap in caps.values())


def test_fd_rlimit_is_the_exact_running_process_not_unit_configuration(host, monkeypatch):
    root, _, state = host
    proc = root/'proc'
    pid = proc/'123'
    pid.mkdir(parents=True)
    monkeypatch.setattr(resources, 'PROC_ROOT', proc)
    state.update(MainPID='123', Restart='on-failure', RestartUSec='3s', StartLimitIntervalUSec='1min',
                 StartLimitBurst='5', TimeoutStopUSec='30s', PrivateNetwork='yes', RestrictAddressFamilies='AF_UNIX')
    (pid/'cgroup').write_text('0::'+state['ControlGroup']+'\n')
    (pid/'limits').write_text('Max open files            128                 unlimited             files\n')
    report = resources.collect(INSTANCE, cgroup_root=root)
    assert report['main_process_fds'] == {'state':'os_enforced','soft':128,'hard':'unlimited'}
    assert report['service_policy'] == dict(restart='on-failure', restart_delay='3s', start_window='1min',
        start_burst=5, stop_timeout='30s', private_network=True, unix_sockets_only=True)
    (pid/'cgroup').write_text('0::/system.slice/other.service\n')
    assert resources.collect(INSTANCE, cgroup_root=root)['main_process_fds'] == {'state':'unavailable'}
    (pid/'cgroup').write_text('0::'+state['ControlGroup']+'\n')
    (pid/'limits').write_text('Max open files 300 256 files\n')
    assert resources.collect(INSTANCE, cgroup_root=root)['main_process_fds'] == {'state':'unavailable'}


def test_node_target_is_only_the_device_agent_not_an_application_host(monkeypatch, tmp_path):
    def unavailable(unit):
        assert unit == '3mm-agent.service'
        return {'Id':unit, 'LoadState':'not-found'}
    monkeypatch.setattr(resources,'_unit_state',unavailable)
    assert resources.collect_node_agent(cgroup_root=tmp_path) == {
        'unit':'3mm-agent.service', 'scope':'unit_cgroup', 'state':'not_found', 'schema_version':1}


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
    assert 'supervision' not in report and 'usage' not in report


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
