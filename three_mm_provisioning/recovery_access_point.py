"""Temporary recovery AP alongside the configured workloads; no role reset.

The Wi-Fi transaction lock serializes AP teardown with setup commits. Root-owned
state records only connection UUIDs, never SSIDs supplied by users or passwords.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from three_mm_provisioning.models import ProvisioningState
from three_mm_provisioning.network import NetworkAdapterError
from three_mm_provisioning.network_capabilities import INTERFACE, managed_interfaces
from three_mm_provisioning.network_manager_mutation import NetworkManagerMutationBoundary
from three_mm_provisioning.network_transaction import IDENTIFIER, NetworkTransaction
from three_mm_provisioning.persistence import FileProvisioningStore
from three_mm_provisioning.setup_access_point import setup_ssid
from three_mm_provisioning.setup_journal import atomic_json

STATUS_PATH = Path('/run/3mm/access-point.json')
AP_ADDRESS = '10.42.0.1/24'
AP_URL = 'http://10.42.0.1:8895/setup'
CAPTIVE_DNS_CONFIG = Path('/etc/NetworkManager/dnsmasq-shared.d/3mm-recovery-captive.conf')
CAPTIVE_DNS_CONTENT = 'address=/#/10.42.0.1\nlocal=/#/\n'


def clear_captive_dns_configuration(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Unexpected captive DNS configuration')
    if path.exists():
        if path.read_text(encoding='utf-8') != CAPTIVE_DNS_CONTENT:
            raise ValueError('Unexpected captive DNS configuration')
        path.unlink()


@contextmanager
def captive_dns_configuration(path):
    """Load the owned AP DNS mapping only into the new shared dnsmasq process."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Refuse an existing file rather than replace configuration we do not own.
    with path.open('x', encoding='utf-8') as stream:
        stream.write(CAPTIVE_DNS_CONTENT)
    try:
        yield
    finally:
        # nmcli up waits until the new dnsmasq has loaded this configuration.
        # Other, later shared connections must not inherit the captive mapping.
        clear_captive_dns_configuration(path)


def read_status(path=STATUS_PATH):
    empty = dict(state='inactive', id=None, interface=None, expires_at=None,
                 network=None, setup_url=None, reason=None)
    path = Path(path)
    if not path.exists():
        return empty
    try:
        if path.is_symlink() or path.stat().st_size > 4096:
            raise ValueError('invalid status')
        value = json.loads(path.read_text())
        if (set(value) != set(empty) or value['state'] not in
                {'starting', 'active', 'restoring', 'inactive', 'failed'}
                or not isinstance(value['id'], str) or not IDENTIFIER.fullmatch(value['id'])
                or not isinstance(value['interface'], str) or not INTERFACE.fullmatch(value['interface'])):
            raise ValueError('invalid status')
        return value
    except (OSError, ValueError, TypeError, KeyError):
        return {**empty, 'state': 'unavailable', 'reason': 'status_unavailable'}


def publish_status(status, path=STATUS_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    try:
        os.fchmod(fd, 0o640)
        os.fchown(fd, os.geteuid(), path.parent.stat().st_gid)
        with os.fdopen(fd, 'w') as stream:
            json.dump(status, stream); stream.flush(); os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class RecoveryAccessPoint:
    def __init__(self, directory=Path('/var/lib/3mm-setup-helper'), *, boundary=None,
                 status_path=STATUS_PATH, provisioning=Path('/var/lib/3mm/provisioning'),
                 interfaces=managed_interfaces, activate=None, clock=time.time,
                 network_name=None, dns_config=CAPTIVE_DNS_CONFIG):
        self.transaction = NetworkTransaction(directory, boundary=boundary)
        self.boundary = self.transaction.boundary
        self.path = Path(directory) / 'access-point.json'
        self.status_path = Path(status_path)
        self.provisioning = Path(provisioning)
        self.interfaces, self.activate, self.clock = interfaces, activate, clock
        self.network_name = network_name
        self.dns_config = Path(dns_config)

    def _load(self):
        if not self.path.exists():
            return None
        if self.path.is_symlink() or self.path.stat().st_size > 4096:
            raise ValueError('Invalid AP journal')
        record = json.loads(self.path.read_text())
        fields = {'id', 'interface', 'previous', 'profile', 'expires_at', 'phase', 'network'}
        if (set(record) != fields or not IDENTIFIER.fullmatch(record['id'])
                or not INTERFACE.fullmatch(record['interface'])
                or record['phase'] not in {'starting', 'active', 'restoring', 'inactive', 'failed'}
                or str(uuid.UUID(record['profile'])) != record['profile']
                or (record['previous'] is not None and str(uuid.UUID(record['previous'])) != record['previous'])
                or type(record['expires_at']) not in {float, int}
                or not isinstance(record['network'], str) or not record['network'].startswith('3mm Setup ')):
            raise ValueError('Invalid AP journal')
        return record

    def _save(self, record, phase, reason=None):
        record['phase'] = phase
        atomic_json(self.path, record)
        status = dict(state=phase, id=record['id'], interface=record['interface'],
                      expires_at=record['expires_at'], network=record['network'],
                      setup_url=AP_URL, reason=reason)
        publish_status(status, self.status_path)

    def _current(self, interface):
        try:
            value = self.boundary.active_connection_uuid(interface)
            return None if value == '--' else value
        except NetworkAdapterError:
            return None

    def start(self, interface, identifier, duration=300):
        if (not isinstance(interface, str) or not INTERFACE.fullmatch(interface)
                or not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier)
                or type(duration) is not int or not 60 <= duration <= 900):
            raise ValueError('Invalid recovery AP request')
        store = FileProvisioningStore(self.provisioning)
        snapshot = store.load_runtime_snapshot()
        if snapshot is None or snapshot.state is not ProvisioningState.PROVISIONED or store.setup_pending():
            raise ValueError('Complete pending setup before starting recovery AP')
        if not any(item['name'] == interface and item['access_point'] for item in self.interfaces()):
            raise ValueError('AP-capable interface unavailable')
        # Starting the protected portal does not replace the configured workloads.
        # Do this before taking the Wi-Fi lock: the helper startup uses that lock.
        if self.activate:
            self.activate()
        with self.transaction.locked():
            previous = self._load()
            if previous and previous['phase'] == 'failed':
                self._restore(previous)
            elif previous and previous['phase'] != 'inactive':
                raise ValueError('An access-point session is already pending')
            pending = self.transaction._load()
            if pending and pending['phase'] in {'applying', 'verified'}:
                raise ValueError('A Wi-Fi setup transaction is pending')
            record = dict(id=identifier, interface=interface, previous=self._current(interface),
                          profile=str(uuid.uuid4()), expires_at=self.clock() + duration,
                          phase='starting', network=self.network_name or setup_ssid(Path('/etc/machine-id')))
            self._save(record, 'starting')
            try:
                # No radio mutation is allowed before an independent timer exists.
                self.boundary.schedule_access_point_stop(identifier, duration)
                with captive_dns_configuration(self.dns_config):
                    self.boundary.create_temporary_open_setup_access_point(
                        interface=interface, connection_name='3mm-recovery-' + identifier,
                        network_name=record['network'], connection_uuid=record['profile'],
                        ipv4_address=AP_ADDRESS)
                if self._current(interface) != record['profile'] or not self.boundary.has_local_address(interface):
                    raise NetworkAdapterError('AP activation unconfirmed')
                self._save(record, 'active')
            except Exception:
                self._restore(record)
                raise
        return read_status(self.status_path)

    def _restore(self, record):
        self._save(record, 'restoring')
        try:
            clear_captive_dns_configuration(self.dns_config)
            pending = self.transaction._load()
            if (pending and pending['interface'] == record['interface']
                    and pending['previous'] == record['profile']):
                if pending['phase'] in {'applying', 'verified'}:
                    # Once the AP closes, its rollback target must be the original
                    # network rather than the AP profile that is about to be removed.
                    pending['previous'] = record['previous']
                    atomic_json(self.transaction.path, pending)
                    self.transaction._rollback(pending)
                elif pending['phase'] == 'committed':
                    self.transaction._finish_commit(pending)
            current = self._current(record['interface'])
            failure = False
            try:
                # A newly committed Wi-Fi or independent host connection wins.
                if current in {None, record['profile']} and record['previous']:
                    self.boundary.restore_connection(record['previous'])
            except Exception:
                failure = True
            finally:
                if self.boundary.connection_uuid(record['profile']) == record['profile']:
                    self.boundary.delete_connection(record['profile'])
            if failure:
                raise NetworkAdapterError('Previous connection restoration unconfirmed')
            self._save(record, 'inactive')
        except Exception:
            self._save(record, 'failed', 'restore_unconfirmed')
            raise

    def stop(self, identifier=None):
        with self.transaction.locked():
            record = self._load()
            if record is None:
                clear_captive_dns_configuration(self.dns_config)
                status = read_status(self.status_path)
                if identifier is not None and status['id'] == identifier and status['state'] == 'starting':
                    publish_status({**status, 'state': 'inactive'}, self.status_path)
                return read_status(self.status_path)
            if record['phase'] == 'inactive':
                clear_captive_dns_configuration(self.dns_config)
                return read_status(self.status_path)
            if identifier is not None and record['id'] != identifier:
                return read_status(self.status_path)  # Stale timers cannot close a new AP.
            self._restore(record)
        return read_status(self.status_path)

    def recover(self):
        # Recovery on boot/helper restart closes any unfinished, non-autoconnect AP.
        return self.stop()


def recover_on_startup():
    try:
        RecoveryAccessPoint().recover()
    except Exception:
        import logging
        logging.getLogger(__name__).error('Temporary access-point recovery is unconfirmed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'stop', 'recover'))
    parser.add_argument('--interface')
    parser.add_argument('--id')
    parser.add_argument('--duration', type=int, default=300)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Root required')
    def activate():
        from three_mm_runtime.network_recovery import activate_setup_runtime
        activate_setup_runtime(data_dir=Path('/var/lib/3mm/provisioning'), trigger='manual',
                               service_user='3mm', service_group='3mm')
    ap = RecoveryAccessPoint(activate=activate)
    if args.action == 'start':
        if not args.interface or not args.id:
            parser.error('start requires --interface and --id')
        try:
            # Reject a collision with a different, concurrently connected subnet.
            routes = json.loads(subprocess.check_output(['ip', '-j', '-4', 'route', 'show'], text=True))
            subnet = ipaddress.ip_interface(AP_ADDRESS).network
            if any(r.get('dst') not in {None, 'default'} and r.get('dev') != args.interface
                   and ipaddress.ip_network(r['dst'], strict=False).overlaps(subnet) for r in routes):
                raise ValueError('Setup subnet overlaps another interface')
            result = ap.start(args.interface, args.id, args.duration)
        except Exception:
            current = read_status()
            if current['id'] == args.id and current['state'] == 'starting':
                publish_status({**current, 'state': 'failed', 'reason': 'start_unconfirmed'})
            raise
    else:
        if args.action == 'recover':
            recover_on_startup()
            result = read_status()
        else:
            result = ap.stop(args.id)
    print(json.dumps(result))

if __name__ == '__main__':
    main()
