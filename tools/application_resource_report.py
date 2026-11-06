"""Read the live cgroup v2 limits of one supervised 3mm application host."""

import argparse
import json
from pathlib import Path
import re
import stat
import subprocess
import sys


CGROUP_ROOT = Path('/sys/fs/cgroup')
INSTANCE = re.compile(r'[0-9a-f]{24}')
PROPERTIES = ('Id', 'LoadState', 'ActiveState', 'ControlGroup', 'InvocationID')
LIMIT_FILES = {'cpu': 'cpu.max', 'memory': 'memory.max', 'tasks': 'pids.max'}


def _unit_state(unit):
    result = subprocess.run(
        ['/usr/bin/systemctl', 'show', '--no-pager', *(f'--property={name}' for name in PROPERTIES), unit],
        capture_output=True, text=True, encoding='utf-8', timeout=5, check=True,
    )
    values = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition('=')
        if not separator or key not in PROPERTIES or key in values:
            raise ValueError('Unexpected unit status')
        values[key] = value
    if values.keys() != set(PROPERTIES) or values['Id'] != unit:
        raise ValueError('Unexpected unit identity')
    return values


def _natural(value, *, positive=False):
    if re.fullmatch(r'[0-9]{1,20}', value) is None:
        raise ValueError('Invalid cgroup limit')
    number = int(value)
    if number > 2**64 - 1 or (positive and number == 0):
        raise ValueError('Invalid cgroup limit')
    return number


def _limit(directory, resource, filename, root_controllers):
    try:
        with (directory / filename).open('rb') as stream:
            raw = stream.read(129)
        if len(raw) > 128:
            raise ValueError('Invalid cgroup limit')
        parts = raw.decode('ascii').split()
        if len(parts) != (2 if resource == 'cpu' else 1):
            raise ValueError('Invalid cgroup limit')
        value = parts[0]
        result = {'state': 'not_set_here'} if value == 'max' else {'state': 'os_enforced'}
        if resource == 'cpu':
            result['period_usec'] = _natural(parts[1], positive=True)
            if value != 'max':
                result['quota_usec'] = _natural(value, positive=True)
        elif value != 'max':
            result['max_bytes' if resource == 'memory' else 'max_tasks'] = _natural(value)
        return result
    except FileNotFoundError:
        controller = filename.split('.', 1)[0]
        reason = ('controller_not_available_on_host' if root_controllers is not None
                  and controller not in root_controllers else 'controller_file_absent')
        return {'state': 'unavailable', 'reason': reason}
    except OSError:
        return {'state': 'unavailable', 'reason': 'read_failed'}
    except ValueError:
        return {'state': 'unavailable', 'reason': 'invalid_value'}


def _cgroup_identity(directory):
    if directory.resolve(strict=True) != directory:
        raise ValueError('Unexpected cgroup path')
    info = directory.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('Unexpected cgroup path')
    return info.st_dev, info.st_ino


def _controllers(path):
    with path.open('rb') as stream:
        value = stream.read(1025)
    if len(value) > 1024:
        raise ValueError('Invalid cgroup controller list')
    names = value.decode('ascii').split()
    if any(re.fullmatch(r'[a-z][a-z0-9_]*', name) is None for name in names):
        raise ValueError('Invalid cgroup controller list')
    return frozenset(names)


def collect(instance, *, cgroup_root=CGROUP_ROOT):
    if INSTANCE.fullmatch(instance) is None:
        raise ValueError('Use the exact 24-hex application instance ID')
    unit = f'3mm-application-extension@{instance}.service'
    report = {'schema_version': 1, 'unit': unit, 'scope': 'unit_cgroup'}
    try:
        before = _unit_state(unit)
    except (OSError, ValueError, subprocess.SubprocessError):
        return dict(report, state='unavailable', reason='unit_status_unavailable')
    if before['LoadState'] == 'not-found':
        return dict(report, state='not_found')
    if before['LoadState'] != 'loaded':
        return dict(report, state='unavailable', reason='unit_not_loaded')
    if before['ActiveState'] != 'active':
        return dict(report, state='not_running')
    group = before['ControlGroup']
    segments = group[1:].split('/')
    invocation = before['InvocationID']
    if (not group.startswith('/') or '\x00' in group or segments[-1] != unit
            or any(segment in {'', '.', '..'} for segment in segments)
            or re.fullmatch(r'[0-9a-f]{32}', invocation) is None or invocation == '0' * 32):
        return dict(report, state='unavailable', reason='cgroup_identity_unavailable')
    try:
        root_controllers = _controllers(cgroup_root / 'cgroup.controllers')
    except FileNotFoundError:
        return dict(report, state='unsupported', reason='cgroup_v2_not_visible')
    except (OSError, ValueError):
        root_controllers = None  # Kernel limit files may still be readable.
    directory = cgroup_root.joinpath(*segments)
    try:
        identity = _cgroup_identity(directory)
    except (OSError, ValueError, RuntimeError):
        return dict(report, state='unavailable', reason='cgroup_unavailable')
    limits = {resource: _limit(directory, resource, name, root_controllers)
              for resource, name in LIMIT_FILES.items()}
    try:
        after = _unit_state(unit)
        if after != before or _cgroup_identity(directory) != identity:
            return dict(report, state='unavailable', reason='unit_or_cgroup_changed')
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        return dict(report, state='unavailable', reason='cgroup_recheck_failed')
    return dict(report, state='observed', limits=limits)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('instance', help='Exact 24-hex instance ID, not a package name')
    args = parser.parse_args()
    if INSTANCE.fullmatch(args.instance) is None:
        parser.error('Use the exact 24-hex application instance ID')
    if sys.platform != 'linux':
        parser.error('Run on the Linux system hosting the application')
    result = collect(args.instance)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['state'] == 'observed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
