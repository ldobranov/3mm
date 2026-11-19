"""Opt-in Linux acceptance: a new slice and one harmless process; no installed units."""
import os
from pathlib import Path
import subprocess
import time
import uuid

import pytest

from deployment import service_resources


@pytest.mark.skipif(os.environ.get('TEST_RESOURCE_HIERARCHY') != '1',
                    reason='Requires explicitly selected disposable systemd/cgroup v2 Linux')
def test_real_parent_caps_and_main_process_rlimit():
    assert os.geteuid() == 0 and Path('/run/systemd/system').is_dir()
    # Submit both transient units in one manager transaction. No unit files,
    # shared parent settings or runtime override files are edited.
    stem = 'resourcecheck' + uuid.uuid4().hex
    unit, parent = stem + '.service', stem + '.slice'
    run = lambda *args, **kw: subprocess.run(args, text=True, capture_output=True, timeout=15, **kw)
    assert service_resources._unit_state(unit)['LoadState'] == 'not-found'
    created = run('busctl', 'call', 'org.freedesktop.systemd1', '/org/freedesktop/systemd1',
        'org.freedesktop.systemd1.Manager', 'StartTransientUnit', 'ssa(sv)a(sa(sv))',
        unit, 'fail', '11', 'Type', 's', 'exec', 'Slice', 's', parent, 'User', 's', 'nobody',
        'ExecStart', 'a(sasb)', '1', '/usr/bin/sleep', '2', '/usr/bin/sleep', '45', 'false',
        'TasksMax', 't', '12', 'CPUQuotaPerSecUSec', 't', '750000',
        'MemoryMax', 't', str(48 << 20), 'LimitNOFILE', 't', '193', 'LimitNOFILESoft', 't', '128',
        'Restart', 's', 'no', 'RuntimeMaxUSec', 't', '50000000',
        '1', parent, '3', 'TasksMax', 't', '6',
        'CPUQuotaPerSecUSec', 't', '250000', 'MemoryMax', 't', str(32 << 20))
    assert created.returncode == 0, created.stderr
    try:
        for _ in range(30):
            report = service_resources._collect_unit(unit, service_resources.CGROUP_ROOT)
            if report['state'] == 'observed':
                break
            time.sleep(.1)
        assert report['state'] == 'observed', report
        own, visible = report['limits'], report['hierarchy_limits']
        assert own['tasks']['max_tasks'] == 12 and visible['tasks']['max_tasks'] == 6
        assert own['memory']['max_bytes'] == 48 << 20 and visible['memory']['max_bytes'] == 32 << 20
        assert own['cpu']['quota_usec'] * 4 == 3 * own['cpu']['period_usec']
        assert visible['cpu']['quota_usec'] * 4 == visible['cpu']['period_usec']
        assert all(lim['source'] == 'parent' and lim['complete'] for lim in visible.values())
        assert report['main_process_fds'] == {'state':'os_enforced', 'soft':128, 'hard':193}
    finally:
        stopped = run('systemctl', 'stop', unit, parent)
        assert stopped.returncode == 0, stopped.stderr
    assert service_resources._unit_state(unit)['LoadState'] == 'not-found'
