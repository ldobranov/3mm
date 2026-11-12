"""Local Raspberry I²C-1 administration. No bus I/O, live activation or reboot.

The Core peer admits an administrator's revision-bound request. A fixed root
worker journals preimages before writing three allowlisted files. Reboot is a
separate system-control operation; only a new kernel boot can verify activation.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import time
import uuid

from deployment.component_store import _write, _fsync, release_mutation_lock

STATE = Path('/var/lib/3mm-hardware-interfaces')
ACTIONS = frozenset({'hardware_interfaces_status', 'hardware_interfaces_enable_i2c', 'hardware_interfaces_restart'})
DEVICE = re.compile(r'dev_[0-9a-f]{32}')
HEX32 = re.compile(r'[0-9a-f]{32}')
HEX64 = re.compile(r'[0-9a-f]{64}')
PROFILE = 'raspberry-i2c1-100khz-v1'
MODULES = '/etc/modules-load.d/3mm-i2c.conf'
DROPIN = '/etc/systemd/system/3mm-agent.service.d/50-3mm-i2c.conf'
MODULE_BYTES = b'# Managed by 3mm hardware interfaces\ni2c-dev\n'
DROPIN_BYTES = b'# Managed by 3mm hardware interfaces\n[Service]\nSupplementaryGroups=i2c\n'
BOOT_BYTES = b'\n# 3mm hardware interfaces: I2C-1\n[all]\ndtoverlay=\ndtparam=i2c_arm=on\ndtparam=i2c_arm_baudrate=100000\n'
# Firmware model filters are not exact model names: e.g. a 3B+ reads both
# [pi3] and [pi3+], but a 4B does not read [cm4]. Keep the supported host profile
# separate from the set of known (and provably foreign) firmware model filters.
# https://www.raspberrypi.com/documentation/computers/config_txt.html#model-filters
BOARD_FILTERS = {
    'Raspberry Pi Zero W Rev': frozenset({'pi0', 'pi0w'}),
    'Raspberry Pi 3 Model B Plus Rev': frozenset({'pi3', 'pi3+'}),
    'Raspberry Pi 4 Model B Rev': frozenset({'pi4'}),
    'Raspberry Pi 5 Model B Rev': frozenset({'pi5'}),
}
BOARDS = tuple(BOARD_FILTERS)
MODEL_FILTERS = frozenset({'pi1', 'pi2', 'pi3', 'pi3+', 'pi4', 'pi5', 'pi400',
    'pi500', 'cm0', 'cm1', 'cm3', 'cm3+', 'cm4', 'cm4s', 'cm5', 'pi0', 'pi0w', 'pi02'})


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_request(value):
    if type(value) is not dict or type(value.get('action')) is not str or value['action'] not in ACTIONS:
        raise ValueError('invalid_request')
    fields = {'action', 'device_id', 'requested_by_user_id'}
    if value['action'] != 'hardware_interfaces_status':
        fields |= {'request_id', 'expected_revision', 'confirmation'}
    if value['action'] == 'hardware_interfaces_restart':
        fields |= {'source_request_id'}
    if (set(value) != fields or type(value['device_id']) is not str
            or DEVICE.fullmatch(value['device_id']) is None
            or type(value['requested_by_user_id']) is not int or value['requested_by_user_id'] <= 0):
        raise ValueError('invalid_request')
    if value['action'] != 'hardware_interfaces_status' and (
            type(value['request_id']) is not str or not HEX32.fullmatch(value['request_id'])
            or type(value['expected_revision']) is not str or not HEX64.fullmatch(value['expected_revision'])
            or value['confirmation'] != ('ENABLE I2C ' if value['action'] == 'hardware_interfaces_enable_i2c'
                                         else 'RESTART ') + value['device_id']):
        raise ValueError('invalid_confirmation_or_revision')
    if value['action'] == 'hardware_interfaces_restart' and (
            type(value['source_request_id']) is not str or not HEX32.fullmatch(value['source_request_id'])):
        raise ValueError('invalid_source_request_id')
    return value


def admin_revision(database, user_id):
    """Read current authority, not the role/identity supplied in a JSON claim."""
    with closing(sqlite3.connect(Path(database).as_uri() + '?mode=ro', uri=True, timeout=.2)) as db:
        db.set_progress_handler(lambda: 1, 10000)
        row = db.execute('SELECT role,is_blocked,token_version FROM users WHERE id=?', (user_id,)).fetchone()
    if row is None or row[0] != 'admin' or row[1] != 0:
        raise ValueError('administrator_required')
    return row[2]


def agent_process():
    """Kernel-observed Agent groups, never configured groups or the helper UID."""
    result = subprocess.run(['/usr/bin/systemctl', 'show', '3mm-agent.service',
        '--property=MainPID', '--value'], capture_output=True, text=True, timeout=2, check=False)
    pid = int(result.stdout.strip()) if result.returncode == 0 else 0
    if pid <= 0:
        return None
    root = Path('/proc') / str(pid)
    arguments = (root/'cmdline').read_bytes().decode().strip('\0').split('\0')
    if ('/opt/3mm-agent/current/service.pyz' not in arguments
            or '--hardware-profile' not in arguments
            or arguments[arguments.index('--hardware-profile') + 1] != 'native'):
        return None
    environment = dict(item.split('=', 1) for item in (root/'environ').read_bytes().decode().split('\0') if '=' in item)
    pins = []
    for key in ('THREE_MM_GPIO_INPUTS', 'THREE_MM_GPIO_OUTPUTS'):
        pins.extend(int(item.rsplit(':', 1)[1]) for item in environment.get(key, '').split(',') if item)
    fields = dict(line.split(':', 1) for line in (root/'status').read_text().splitlines() if ':' in line)
    if int(fields['Uid'].split()[1]) == 0:
        return None
    # stat's comm may contain spaces or parentheses. Identity binds the start tick.
    start = (root/'stat').read_text().rsplit(')', 1)[1].split()[19]
    return {'pid': pid, 'start': start, 'uid': int(fields['Uid'].split()[1]),
            'gid': int(fields['Gid'].split()[1]), 'groups': [int(x) for x in fields['Groups'].split()],
            'gpio_pins': sorted(set(pins))}


def i2c_group_id():
    import grp
    try:
        gid = grp.getgrnam('i2c').gr_gid
    except KeyError:
        raise ValueError('i2c_group_unavailable') from None
    if gid <= 0:
        raise ValueError('i2c_group_unavailable')
    return gid


class HardwareInterfaces:
    def __init__(self, *, root=Path('/'), state=STATE,
                 database=Path('/var/lib/3mm/core/3mm.db'), process=agent_process,
                 worker_active=None, mutation_lock=release_mutation_lock, enforce=True):
        self.root, self.state, self.database = Path(root), Path(state), Path(database)
        self.process = process
        self.worker_active = worker_active or (lambda _id: True)
        self.mutation_lock, self.enforce = mutation_lock, enforce

    def path(self, path):
        return self.root / path.lstrip('/')

    def secure(self, path, *, directory=False):
        info = path.lstat()
        if (stat.S_ISLNK(info.st_mode) or
                (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))
                or not directory and info.st_nlink != 1
                or self.enforce and (info.st_uid != 0 or info.st_mode & 0o022)):
            raise ValueError('unsafe_managed_path')

    def parents(self, path):
        for parent in reversed(path.parents):
            if parent == self.root.parent or self.root not in (parent, *parent.parents):
                continue
            if not parent.exists() and not parent.is_symlink():
                continue
            self.secure(parent, directory=True)

    def read(self, path, *, optional=False, trusted=True):
        if trusted:
            self.parents(path)
        if not path.exists() and not path.is_symlink() and optional:
            return None
        if trusted:
            self.secure(path)
        with path.open('rb') as stream:
            data = stream.read(65537)
        if len(data) > 65536:
            raise ValueError('file_budget_exceeded')
        return data

    def operation(self):
        if not self.state.exists() and not self.state.is_symlink():
            return None
        self.secure(self.state, directory=True)
        raw = self.read(self.state/'operation.json', optional=True)
        if raw is None:
            return None
        value = json.loads(raw)
        if (value.get('schema_version') != 1 or value.get('profile') != PROFILE
                or not HEX32.fullmatch(str(value.get('request_id', '')))
                or value.get('state') not in {'queued', 'applying', 'pending_reboot', 'failed', 'recovery_required'}):
            raise ValueError('invalid_operation_journal')
        return value

    def save(self, operation, state, reason=None):
        now = int(time.time())
        operation = {**operation, 'state': state, 'reason': reason,
                     'created_at': operation.get('created_at', now), 'updated_at': now}
        _write(self.state/'operation.json', json.dumps(operation, sort_keys=True).encode())
        return operation

    @contextmanager
    def locked(self):
        import fcntl
        self.state.mkdir(mode=0o750, parents=True, exist_ok=True)
        self.parents(self.state)
        self.secure(self.state, directory=True)
        fd = os.open(self.state/'operation.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if self.enforce and os.fstat(fd).st_uid != 0:
                raise ValueError('unsafe_operation_lock')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)

    def identity(self):
        # Agent owns this file. It is read only, never load_or_create().
        path = self.path('/var/lib/3mm/agent/identity.json')
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o022:
            raise ValueError('local_agent_identity_unavailable')
        value = json.loads(self.read(path, trusted=False))['device_id']
        if type(value) is not str or not DEVICE.fullmatch(value):
            raise ValueError('local_agent_identity_unavailable')
        return value

    def boot_id(self):
        value = self.path('/proc/sys/kernel/random/boot_id').read_text().strip()
        if str(uuid.UUID(value)) != value:
            raise ValueError('boot_identity_unavailable')
        return value

    def config(self):
        group_id = i2c_group_id()  # Do not prepare an Agent unit that cannot start at boot.
        model = self.read(self.path('/sys/firmware/devicetree/base/model'), trusted=False).rstrip(b'\0').decode()
        release_path = self.path('/etc/os-release')
        if release_path.is_symlink() and release_path.resolve() == self.path('/usr/lib/os-release').resolve():
            release_path = self.path('/usr/lib/os-release')
        release = self.read(release_path).decode()
        os_info = dict(line.split('=', 1) for line in release.splitlines() if '=' in line and not line.startswith('#'))
        if (not model.startswith(BOARDS) or os_info.get('ID', '').strip('"') not in {'debian', 'raspbian'}
                or os_info.get('VERSION_CODENAME', '').strip('"') not in {'bookworm', 'trixie'}):
            raise ValueError('unsupported_board_or_os')
        # Modern Raspberry Pi OS's canonical firmware partition only. Never edit
        # a guessed /boot path on another distribution or an unrelated host.
        boot_path = '/boot/firmware/config.txt'
        if self.enforce and not os.path.ismount(self.path('/boot/firmware')):
            raise ValueError('firmware_mount_unverified')
        boot = self.read(self.path(boot_path))
        if len(boot) > 8192:
            raise ValueError('boot_configuration_budget_exceeded')
        matching_filters = next(filters for prefix, filters in BOARD_FILTERS.items() if model.startswith(prefix))
        model_active, unverified_filter, enabled, speed = True, False, False, None
        for raw in boot.decode('utf-8').splitlines():
            line = re.sub(r'\s*=\s*', '=', raw.partition('#')[0].strip())
            if not line:
                continue
            if line.startswith('['):
                if re.fullmatch(r'\[[a-z0-9+]+\]', line) and line[1:-1] == 'all':
                    model_active, unverified_filter = True, False
                elif re.fullmatch(r'\[[a-z0-9+]+\]', line) and line[1:-1] in MODEL_FILTERS:
                    # A model filter replaces the previous model filter only.
                    # It cannot clear an unknown EDID/GPIO/serial/etc. condition.
                    model_active = line[1:-1] in matching_filters
                else:
                    # Do not guess the semantics of unknown filter classes (or
                    # malformed headers). Only [all] clears this uncertainty.
                    model_active, unverified_filter = True, True
                continue
            line = line.lower()
            # Includes may introduce additional filters; the first profile does
            # not interpret them, even when the surrounding model looks foreign.
            if line.startswith('include'):
                raise ValueError('host_configuration_conflict')
            if not model_active:
                continue
            if unverified_filter and line.startswith(('gpio=', 'dtoverlay=', 'dtparam=')):
                raise ValueError('unverified_boot_filter')
            if line.startswith('gpio='):
                raise ValueError('host_configuration_conflict')
            if line.startswith('dtoverlay=') and line.split('=', 1)[1].split(',')[0] not in {'', 'vc4-kms-v3d', 'dwc2'}:
                raise ValueError('unverified_overlay_conflict')
            if line.startswith('dtparam='):
                for parameter in line[8:].split(','):
                    name, _, value = parameter.strip().partition('=')
                    if name in {'i2c', 'i2c_arm', 'i2c1', 'i2c_baudrate', 'i2c_arm_baudrate', 'i2c1_baudrate'}:
                        if name.endswith('baudrate'):
                            if value != '100000':
                                raise ValueError('i2c_speed_conflict')
                            speed = 100000
                        else:
                            if value not in {'on', 'true', '1', ''}:
                                raise ValueError('host_i2c_disabled_explicitly')
                            enabled = True
        managed_gpio = self.path('/var/lib/3mm/agent/gpio-configuration.json')
        if managed_gpio.exists():
            if managed_gpio.is_symlink():
                raise ValueError('gpio_configuration_unverified')
            gpio = json.loads(self.read(managed_gpio, trusted=False))
            if gpio.get('bcm_pin') in (2, 3):
                raise ValueError('gpio_pin_conflict')
        if self.path('/sys/firmware/devicetree/base/hat').exists():
            raise ValueError('unverified_hat_conflict')
        files = {boot_path: boot, MODULES: self.read(self.path(MODULES), optional=True),
                 DROPIN: self.read(self.path(DROPIN), optional=True)}
        for name, expected in ((MODULES, MODULE_BYTES), (DROPIN, DROPIN_BYTES)):
            if files[name] not in (None, expected):
                raise ValueError('managed_file_conflict')
        return model, files, enabled, speed, group_id

    def live(self):
        process = None
        try:
            process = self.process()
        except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError):
            pass
        # I2C adapters are bus devices; an i2c-adapter class is not required.
        # https://docs.kernel.org/i2c/i2c-sysfs.html
        adapter = self.path('/sys/bus/i2c/devices/i2c-1')
        clock = None
        for suffix in ('of_node/clock-frequency', 'device/of_node/clock-frequency'):
            try:
                raw = (adapter/suffix).read_bytes()
                if len(raw) == 4:
                    clock = int.from_bytes(raw, 'big')
                    break
            except OSError:
                pass
        access, node = False, False
        try:
            device = self.path('/dev/i2c-1')
            info = device.lstat()
            host_rdev = info.st_rdev
            node = stat.S_ISCHR(info.st_mode) and os.major(info.st_rdev) == 89 and os.minor(info.st_rdev) == 1
            if process and node:
                # Observe the device in the running service's mount namespace.
                device = self.path(f'/proc/{process["pid"]}/root/dev/i2c-1')
                info = device.stat()
                # Extended ACLs need an explicit verifier; never guess readiness.
                acl = 'system.posix_acl_access' in os.listxattr(device)
                bits = (info.st_mode >> (6 if info.st_uid == process['uid'] else
                    3 if info.st_gid in [process['gid'], *process['groups']] else 0)) & 7
                access = (not acl and process['uid'] != 0 and bits & 6 == 6
                          and stat.S_ISCHR(info.st_mode) and info.st_rdev == host_rdev
                          and not info.st_mode & 0o002)
        except (OSError, ValueError):
            pass
        return {'adapter_present': adapter.exists(), 'device_node_present': node,
                'clock_hz': clock, 'agent_running': process is not None,
                'agent_access': access, 'agent_process': process}

    def inspect(self, device_id):
        if self.identity() != device_id:
            return {'device_id': device_id, 'supported': False, 'reason': 'remote_device_unsupported',
                    'can_enable': False, 'operation': None}
        boot_id, live, operation = self.boot_id(), self.live(), self.operation()
        reason, files, model, enabled, speed, group_id = None, {}, None, False, None, None
        try:
            model, files, enabled, speed, group_id = self.config()
            if live['agent_process'] and set(live['agent_process'].get('gpio_pins', [])) & {2, 3}:
                raise ValueError('gpio_pin_conflict')
            if live['adapter_present'] and live['clock_hz'] != 100000:
                raise ValueError('live_i2c_speed_unverified_or_conflicting')
        except (OSError, ValueError, UnicodeError) as error:
            reason = str(error) if isinstance(error, ValueError) else 'unsupported_host_files'
        configured = enabled and speed == 100000 and files.get(MODULES) == MODULE_BYTES and files.get(DROPIN) == DROPIN_BYTES
        ready = (reason is None and configured and live['adapter_present'] and live['device_node_present']
                 and live['agent_access'] and live['clock_hz'] == 100000)
        public = None
        if operation:
            state, why = operation['state'], operation.get('reason')
            if operation['device_id'] != device_id:
                state, why = 'recovery_required', 'local_identity_changed'
            elif state == 'pending_reboot':
                if any((None if value is None else value.hex()) != operation['postimages'].get(key)
                       for key, value in files.items()) or reason:
                    state, why, ready = 'recovery_required', 'configuration_changed_after_apply', False
                elif boot_id != operation['boot_id']:
                    state = 'verified' if ready and not reason else 'verification_failed'
                else:
                    ready = False
            elif state in {'queued', 'applying'} and not self.worker_active(operation['request_id']):
                state, why = 'recovery_required', 'worker_outcome_unconfirmed'
            public = {key: operation[key] for key in ('request_id', 'device_id', 'requested_by_user_id')}
            public.update(state=state, reason=why, restart_request_id=operation.get('restart_request_id'),
                          restart_state=operation.get('restart_state'))
            if state != 'verified':
                ready = False
        revision = digest({'device': device_id, 'boot': boot_id,
            'files': {key: None if value is None else value.hex() for key, value in files.items()},
            'live': live, 'operation': public, 'reason': reason, 'i2c_group_id': group_id})
        can_enable = (reason is None and live['agent_running'] and not configured
                      and (public is None or public['state'] == 'failed'))
        return {'device_id': device_id, 'profile': PROFILE, 'supported': reason is None,
                'reason': reason, 'model': model, 'revision': revision, 'can_enable': can_enable,
                'configured': configured, 'ready': ready, 'clock_hz': 100000,
                'i2c_group_id': group_id,
                'pins': [{'bcm': 2, 'physical': 3, 'signal': 'SDA'}, {'bcm': 3, 'physical': 5, 'signal': 'SCL'}],
                'live': live, 'operation': public,
                'changes': ['/boot/firmware/config.txt', MODULES, DROPIN],
                'reboot_required': configured and not ready}

    def queue(self, payload, schedule):
        validate_request(payload)
        if payload['action'] != 'hardware_interfaces_enable_i2c':
            raise ValueError('invalid_enable_request')
        user_revision = admin_revision(self.database, payload['requested_by_user_id'])
        with self.mutation_lock(), self.locked():
            previous = self.operation()
            fingerprint = digest(payload)
            if previous and previous['request_id'] == payload['request_id']:
                if previous['request_digest'] != fingerprint:
                    raise ValueError('request_id_conflict')
                return payload['request_id']  # Reconcile only. Never schedule again.
            current = self.inspect(payload['device_id'])
            if not current['can_enable'] or current['revision'] != payload['expected_revision']:
                raise ValueError('review_stale_or_unavailable')
            operation = {**payload, 'schema_version': 1, 'profile': PROFILE,
                         'admin_revision': user_revision, 'request_digest': fingerprint,
                         'boot_id': self.boot_id(), 'baseline': current['revision'],
                         'prior_operation': current['operation']}
            operation = self.save(operation, 'queued')
        # Never start a worker while holding the very non-blocking mutation
        # lock it needs. Admission is durable; another request sees queued.
        try:
            schedule(payload['request_id'])
        except Exception:
            with self.locked():
                current = self.operation()
                if current and current['request_id'] == payload['request_id'] and current['state'] == 'queued':
                    self.save(current, 'recovery_required', 'scheduling_unconfirmed')
            raise
        return payload['request_id']

    def restart(self, payload, schedule):
        validate_request(payload)
        if payload['action'] != 'hardware_interfaces_restart':
            raise ValueError('invalid_restart_request')
        admin_revision(self.database, payload['requested_by_user_id'])
        with self.mutation_lock(), self.locked():
            operation = self.operation()
            if operation and operation.get('restart_request_id') == payload['request_id']:
                if operation['restart_digest'] != digest(payload):
                    raise ValueError('request_id_conflict')
                return payload['request_id']
            current = self.inspect(payload['device_id'])
            if (not operation or operation['request_id'] != payload['source_request_id']
                    or operation.get('restart_request_id') or not current['supported']
                    or not current['configured'] or current['operation']['state'] != 'pending_reboot'
                    or current['revision'] != payload['expected_revision']):
                raise ValueError('restart_review_stale_or_unavailable')
            operation.update(restart_request_id=payload['request_id'], restart_digest=digest(payload),
                             restart_state='requested', restart_requested_by_user_id=payload['requested_by_user_id'])
            self.save(operation, operation['state'])
            try:
                schedule('restart_device')
            except Exception:
                operation['restart_state'] = 'unconfirmed'
                self.save(operation, operation['state'])
                raise
            return payload['request_id']

    def replace(self, name, expected, replacement):
        path = self.path(name)
        if not path.parent.exists():
            self.parents(path.parent)
            self.secure(path.parent.parent, directory=True)
            path.parent.mkdir(mode=0o755)
        if self.read(path, optional=True) != expected:
            raise ValueError('file_changed_during_operation')
        if replacement is None:
            if path.exists():
                path.unlink()
                _fsync(path.parent)
        else:
            _write(path, replacement, mode=0o644)

    def execute(self, request_id):
        if not HEX32.fullmatch(request_id):
            raise ValueError('invalid_request_id')
        with self.mutation_lock(), self.locked():
            operation = self.operation()
            if not operation or operation['request_id'] != request_id or operation['state'] != 'queued':
                raise ValueError('operation_not_queued')
            # Remove the queued operation from the revision calculation only for
            # admission; the original revision already fenced earlier operations.
            current = self.inspect(operation['device_id'])
            try:
                actor_unchanged = admin_revision(self.database, operation['requested_by_user_id']) == operation['admin_revision']
            except (ValueError, sqlite3.Error):
                actor_unchanged = False
            if (self.identity() != operation['device_id'] or self.boot_id() != operation['boot_id']
                    or not actor_unchanged
                    or not current['supported'] or not current['live']['agent_running']):
                self.save(operation, 'failed', 'authority_or_host_changed')
                return
            model, files, enabled, speed, group_id = self.config()
            # Reconstruct the exact preview, excluding only this queue admission.
            prior_public = operation.get('prior_operation')
            baseline = digest({'device': operation['device_id'], 'boot': operation['boot_id'],
                'files': {key: None if value is None else value.hex() for key, value in files.items()},
                'live': current['live'], 'operation': prior_public, 'reason': None, 'i2c_group_id': group_id})
            if baseline != operation['baseline']:
                self.save(operation, 'failed', 'review_stale_before_apply')
                return
            after = {**files, '/boot/firmware/config.txt': files['/boot/firmware/config.txt'] +
                     (b'' if enabled and speed == 100000 else BOOT_BYTES), MODULES: MODULE_BYTES, DROPIN: DROPIN_BYTES}
            operation['preimages'] = {key: None if value is None else value.hex() for key, value in files.items()}
            operation['postimages'] = {key: value.hex() for key, value in after.items()}
            operation = self.save(operation, 'applying')  # durable before the first file mutation
            changed = []
            try:
                for name in files:
                    if after[name] != files[name]:
                        # Include attempted writes: fsync can fail after replace.
                        changed.append(name)
                        self.replace(name, files[name], after[name])
                self.save(operation, 'pending_reboot')
            except Exception:
                restored = True
                for name in reversed(changed):
                    try:
                        actual = self.read(self.path(name), optional=True)
                        if actual == files[name]:
                            continue
                        self.replace(name, after[name], files[name])
                    except Exception:
                        restored = False
                self.save(operation, 'failed' if restored else 'recovery_required',
                          'apply_failed_preimages_restored' if restored else 'preimage_restore_unconfirmed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request-id', required=True)
    args = parser.parse_args()
    HardwareInterfaces().execute(args.request_id)


if __name__ == '__main__':
    main()
