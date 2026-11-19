"""Read-only Linux service budgets. Also ships on minimal Nodes, without Core."""

from pathlib import Path
from fractions import Fraction
import re
import stat
import subprocess


CGROUP_ROOT = Path('/sys/fs/cgroup')
PROC_ROOT = Path('/proc')
INSTANCE = re.compile(r'[0-9a-f]{24}')
REQUIRED_PROPERTIES = ('Id', 'LoadState', 'ActiveState', 'ControlGroup', 'InvocationID')
PROPERTIES = (*REQUIRED_PROPERTIES, 'SubState', 'Result', 'NRestarts', 'MainPID',
              'Restart', 'RestartUSec', 'StartLimitBurst', 'StartLimitIntervalUSec',
              'TimeoutStopUSec', 'PrivateNetwork', 'RestrictAddressFamilies')
LIMIT_FILES = {'cpu': 'cpu.max', 'memory': 'memory.max', 'tasks': 'pids.max'}
MAX_PARENT_LEVELS = 16
SERVICE_RESULTS = frozenset({
    'success', 'resources', 'protocol', 'timeout', 'exit-code', 'signal',
    'core-dump', 'watchdog', 'start-limit-hit', 'oom-kill', 'exit-condition',
})


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
    if not set(REQUIRED_PROPERTIES).issubset(values) or values['Id'] != unit:
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


def _current(path):
    """One instantaneous kernel counter, never an inferred value from a limit."""
    try:
        with path.open('rb') as stream:
            raw = stream.read(32)
        if len(raw) == 32:
            return None
        return _natural(raw.decode('ascii').strip())
    except (OSError, ValueError):
        return None


def _ceiling_value(resource, limit):
    if resource == 'cpu':
        return Fraction(limit['quota_usec'], limit['period_usec'])
    return limit['max_bytes' if resource == 'memory' else 'max_tasks']


def _hierarchy_limits(directory, root, local, controllers):
    """Smallest visible long-run ceiling, not guaranteed capacity or free headroom."""
    best = {r: (v, 'unit') for r, v in local.items() if v['state'] == 'os_enforced'}
    incomplete = {r for r, v in local.items() if v['state'] == 'unavailable'}
    parent = directory.parent
    for _ in range(MAX_PARENT_LEVELS):
        for resource, filename in LIMIT_FILES.items():
            limit = _limit(parent, resource, filename, controllers)
            if limit['state'] == 'unavailable':
                # The real hierarchy root normally has none of these three
                # files. A mounted subtree root can expose them; count those.
                if parent != root or limit['reason'] not in (
                        'controller_file_absent', 'controller_not_available_on_host'):
                    incomplete.add(resource)
            elif limit['state'] == 'os_enforced' and (
                    resource not in best or
                    _ceiling_value(resource, limit) < _ceiling_value(resource, best[resource][0])):
                best[resource] = limit, 'parent'
        if parent == root:
            break
        parent = parent.parent
    else:
        incomplete.update(LIMIT_FILES)
    result = {}
    for resource in LIMIT_FILES:
        if resource in best:
            limit, source = best[resource]
            result[resource] = dict(limit, source=source, complete=resource not in incomplete)
        else:
            result[resource] = {'state': 'unavailable' if resource in incomplete else 'no_visible_cap',
                                'complete': resource not in incomplete}
    return result


def _controllers(path):
    with path.open('rb') as stream:
        value = stream.read(1025)
    if len(value) > 1024:
        raise ValueError('Invalid cgroup controller list')
    names = value.decode('ascii').split()
    if any(re.fullmatch(r'[a-z][a-z0-9_]*', name) is None for name in names):
        raise ValueError('Invalid cgroup controller list')
    return frozenset(names)


def _supervision(snapshot):
    active = snapshot['ActiveState']
    if active in {'activating', 'inactive'} and snapshot.get('SubState') in {
        'auto-restart', 'auto-restart-queued',
    }:
        state = 'restarting'
    else:
        state = {'active': 'active', 'inactive': 'stopped', 'failed': 'failed',
                 'activating': 'starting', 'deactivating': 'stopping'}.get(active, 'unknown')
    result = snapshot.get('Result')
    restarts = snapshot.get('NRestarts', '')
    # systemd exposes NRestarts as an unsigned 32-bit counter.
    count = int(restarts) if re.fullmatch(r'[0-9]{1,10}', restarts) else None
    return {
        'state': state,
        'result': result if result in SERVICE_RESULTS else 'other' if result else None,
        'restart_count': count if count is not None and count < 2**32 else None,
    }


def _bounded_text(path, maximum):
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('Observation exceeds bound')
    return raw.decode('ascii')


def _main_process_fds(snapshot):
    """A per-process soft/hard pair from procfs, never a whole-app FD cap."""
    pid = snapshot.get('MainPID', '')
    if not re.fullmatch(r'[1-9][0-9]{0,9}', pid):
        return {'state': 'unavailable'}
    directory = PROC_ROOT / pid
    group = '0::' + snapshot['ControlGroup']
    try:
        if group not in _bounded_text(directory / 'cgroup', 8192).splitlines():
            return {'state': 'unavailable'}
        limits = _bounded_text(directory / 'limits', 8192)
        line, = [line for line in limits.splitlines() if line.startswith('Max open files ')]
        match = re.fullmatch(r'Max open files\s+(unlimited|[0-9]+)\s+(unlimited|[0-9]+)\s+files\s*', line)
        if match is None:
            return {'state': 'unavailable'}
        soft, hard = [v if v == 'unlimited' else _natural(v) for v in match.groups()]
        if hard != 'unlimited' and (soft == 'unlimited' or soft > hard):
            return {'state': 'unavailable'}
        return {'state': 'os_enforced', 'soft': soft, 'hard': hard}
    except (OSError, ValueError):
        return {'state': 'unavailable'}


def _service_policy(snapshot):
    def duration(name):
        value = snapshot.get(name, '')
        # Retain only manager-produced finite duration tokens, never free text.
        return value if len(value) <= 48 and re.fullmatch(
            r'(?:0|infinity|[0-9]+(?:\.[0-9]+)?(?:us|µs|ms|s|min|h|d)'
            r'(?: [0-9]+(?:\.[0-9]+)?(?:us|µs|ms|s|min|h|d))*)', value) else None
    burst = snapshot.get('StartLimitBurst', '')
    return {
        'restart': snapshot.get('Restart') if snapshot.get('Restart') in {
            'no', 'always', 'on-success', 'on-failure', 'on-abnormal', 'on-watchdog', 'on-abort'} else None,
        'restart_delay': duration('RestartUSec'), 'start_window': duration('StartLimitIntervalUSec'),
        'start_burst': int(burst) if re.fullmatch(r'[0-9]{1,9}', burst) else None,
        'stop_timeout': duration('TimeoutStopUSec'),
        'private_network': {'yes': True, 'no': False}.get(snapshot.get('PrivateNetwork')),
        'unix_sockets_only': (snapshot['RestrictAddressFamilies'].split() == ['AF_UNIX']
                              if 'RestrictAddressFamilies' in snapshot else None),
    }


def _observe_cgroup(unit, before, cgroup_root):
    if before['ActiveState'] != 'active':
        return {'state': 'not_running'}, None
    group = before['ControlGroup']
    segments = group[1:].split('/')
    invocation = before['InvocationID']
    if (not group.startswith('/') or '\x00' in group or segments[-1] != unit
            or any(segment in {'', '.', '..'} for segment in segments)
            or re.fullmatch(r'[0-9a-f]{32}', invocation) is None or invocation == '0' * 32):
        return {'state': 'unavailable', 'reason': 'cgroup_identity_unavailable'}, None
    try:
        root_controllers = _controllers(cgroup_root / 'cgroup.controllers')
    except FileNotFoundError:
        return {'state': 'unsupported', 'reason': 'cgroup_v2_not_visible'}, None
    except (OSError, ValueError):
        root_controllers = None  # Kernel limit files may still be readable.
    directory = cgroup_root.joinpath(*segments)
    try:
        identity = _cgroup_identity(directory)
    except (OSError, ValueError, RuntimeError):
        return {'state': 'unavailable', 'reason': 'cgroup_unavailable'}, None
    limits = {resource: _limit(directory, resource, name, root_controllers)
              for resource, name in LIMIT_FILES.items()}
    usage = {'memory_bytes': _current(directory / 'memory.current'),
             'tasks': _current(directory / 'pids.current')}
    return {'state': 'observed', 'limits': limits, 'usage': usage, 'main_process_fds': _main_process_fds(before),
            'hierarchy_limits': _hierarchy_limits(directory, cgroup_root, limits, root_controllers)}, (directory, identity)


def collect(instance, *, cgroup_root=CGROUP_ROOT):
    if INSTANCE.fullmatch(instance) is None:
        raise ValueError('Use the exact 24-hex application instance ID')
    return _collect_unit(f'3mm-application-extension@{instance}.service', cgroup_root)


def collect_node_agent(*, cgroup_root=CGROUP_ROOT):
    # A minimal Node runs the device Agent, not the Core application host.
    return _collect_unit('3mm-agent.service', cgroup_root)


def _collect_unit(unit, cgroup_root):
    report = {'schema_version': 1, 'unit': unit, 'scope': 'unit_cgroup'}
    try:
        before = _unit_state(unit)
    except (OSError, ValueError, subprocess.SubprocessError):
        return dict(report, state='unavailable', reason='unit_status_unavailable')
    if before['LoadState'] == 'not-found':
        return dict(report, state='not_found')
    if before['LoadState'] != 'loaded':
        return dict(report, state='unavailable', reason='unit_not_loaded')
    observation, witness = _observe_cgroup(unit, before, cgroup_root)
    try:
        after = _unit_state(unit)
        if after != before or (witness is not None and _cgroup_identity(witness[0]) != witness[1]):
            return dict(report, state='unavailable', reason='unit_or_cgroup_changed')
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        return dict(report, state='unavailable', reason='cgroup_recheck_failed')
    return dict(report, **observation, supervision=_supervision(before), service_policy=_service_policy(before))


def main():
    import argparse
    import json
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('instance', nargs='?', help='Exact 24-hex application instance')
    target.add_argument('--node-agent', action='store_true', help='Inspect the local device Agent, not hosted applications')
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('Run on the Linux system hosting the service')
    if not args.node_agent and not INSTANCE.fullmatch(args.instance):
        parser.error('Expected the exact 24-hex application instance ID')
    report = collect_node_agent() if args.node_agent else collect(args.instance)
    print(json.dumps(report, sort_keys=True))
    return 0 if report['state'] == 'observed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
