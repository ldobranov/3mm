from pathlib import Path
import subprocess

import pytest

from three_mm_runtime.node_recovery import NodeRecoveryScheduler, create_monitor


def test_supervisor_does_not_run_on_full_release(tmp_path):
    with pytest.raises(RuntimeError, match='minimal Node'):
        create_monitor(tmp_path)


def test_scheduler_only_runs_fixed_worker():
    calls = []
    scheduler = NodeRecoveryScheduler(lambda args, **kwargs: calls.append((args, kwargs)))
    scheduler.schedule_network_setup('automatic')
    args, options = calls[0]
    assert args[0] == '/usr/bin/systemd-run'
    assert 'three_mm_runtime.network_recovery' in args
    assert args[args.index('--data-dir') + 1] == '/var/lib/3mm/provisioning'
    assert options['timeout'] == 10 and options['check']
    with pytest.raises(ValueError):
        scheduler.schedule_network_setup('manual; arbitrary-command')
    assert len(calls) == 1


def test_scheduling_failure_is_not_reported_as_success():
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired('systemd-run', 10)
    with pytest.raises(subprocess.TimeoutExpired):
        NodeRecoveryScheduler(fail).schedule_network_setup('automatic')


def test_supervisor_has_no_core_dependency_or_public_listener():
    unit = (Path(__file__).parents[2] / 'deployment/systemd/3mm-node-recovery.service').read_text()
    assert 'three_mm_runtime.node_recovery' in unit
    assert 'RestrictAddressFamilies=AF_UNIX' in unit
    assert 'ProtectSystem=strict' in unit
    assert 'update_helper' not in unit
