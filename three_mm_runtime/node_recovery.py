"""Core-independent automatic network recovery for a minimal Node.

No HTTP/socket command API is exposed. The process can only schedule the fixed
existing recovery worker after the shared link-loss monitor authorizes it.
"""

from pathlib import Path
import signal
import subprocess
import threading

from three_mm_provisioning import (
    FileNetworkRecoveryMarker, FileNetworkRecoveryPolicyStore,
    FileProvisioningStore, NetworkManagerReadOnlyAdapter,
)
from three_mm_runtime.install_profile import InstallProfile, NetworkBackend, read_install_profile, read_network_backend
from three_mm_runtime.network_recovery import NetworkRecoveryMonitor


class NodeRecoveryScheduler:
    def __init__(self, runner=subprocess.run):
        self.runner = runner

    def schedule_network_setup(self, trigger):
        if trigger != 'automatic':
            raise ValueError('The Node monitor only accepts automatic recovery')
        self.runner([
            '/usr/bin/systemd-run', '--unit=3mm-node-network-recovery',
            '--collect', '--no-block', '--property=Type=exec',
            '--property=RuntimeMaxSec=120',
            '/opt/3mm/current/.venv/bin/python', '-m',
            'three_mm_runtime.network_recovery',
            '--data-dir', '/var/lib/3mm/provisioning', '--trigger', 'automatic',
            '--user', '3mm', '--group', '3mm',
        ], check=True, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd='/opt/3mm/current')


def create_monitor(release_root=Path('/opt/3mm/current')):
    if read_install_profile(release_root) is not InstallProfile.NODE:
        raise RuntimeError('Node recovery supervisor requires a minimal Node release')
    if read_network_backend() is NetworkBackend.HOST:
        return None  # No NetworkManager probing on a host-managed installation.
    data_dir = Path('/var/lib/3mm/provisioning')
    return NetworkRecoveryMonitor(
        policy_store=FileNetworkRecoveryPolicyStore(data_dir / 'network-recovery-policy.json'),
        marker=FileNetworkRecoveryMarker(data_dir / 'network-recovery.json'),
        provisioning_store=FileProvisioningStore(data_dir),
        inspector=NetworkManagerReadOnlyAdapter.from_system(timeout_seconds=5),
        scheduler=NodeRecoveryScheduler(),
    )


def main():
    monitor = create_monitor()
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    while not stop.is_set():
        if monitor is not None:
            monitor.poll()
        stop.wait(5)


if __name__ == '__main__':
    main()
