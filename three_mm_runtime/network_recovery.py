"""Automatic link-loss monitoring and fixed setup-runtime activation worker."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Callable, Protocol

from three_mm_provisioning import (
    FileNetworkRecoveryMarker,
    FileNetworkRecoveryPolicyStore,
    FileProvisioningStore,
    NetworkInspectionAdapter,
    NetworkInspectionError,
    ProvisioningState,
)
from three_mm_provisioning.network_recovery import RecoveryTrigger


class NetworkSetupScheduler(Protocol):
    def schedule_network_setup(self, trigger: RecoveryTrigger) -> None: ...


def has_active_local_link(status) -> bool:
    """Return true for an active Wi-Fi or Ethernet device, without Internet probes."""

    return any(
        device.device_type in {"wifi", "ethernet"}
        and device.state.strip().lower() == "connected"
        for device in status.devices
    )


class NetworkRecoveryMonitor:
    """Trigger setup after one uninterrupted, policy-controlled offline interval."""

    def __init__(
        self,
        *,
        policy_store: FileNetworkRecoveryPolicyStore,
        marker: FileNetworkRecoveryMarker,
        provisioning_store: FileProvisioningStore,
        inspector: NetworkInspectionAdapter,
        scheduler: NetworkSetupScheduler,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._policy_store = policy_store
        self._marker = marker
        self._provisioning_store = provisioning_store
        self._inspector = inspector
        self._scheduler = scheduler
        self._clock = clock
        self._offline_since: float | None = None
        self._pending_since: float | None = None

    def poll(self) -> bool:
        now = self._clock()
        try:
            policy = self._policy_store.load()
            snapshot = self._provisioning_store.load()
            marker_active = self._marker.is_active()
        except Exception:
            self._reset()
            return False

        if (
            not policy.automatic_setup_enabled
            or marker_active
            or snapshot is None
            or snapshot.state is not ProvisioningState.PROVISIONED
        ):
            self._reset()
            return False

        if self._pending_since is not None:
            if now - self._pending_since < 30:
                return False
            self._pending_since = None

        try:
            connected = has_active_local_link(self._inspector.inspect())
        except NetworkInspectionError:
            self._offline_since = None
            return False

        if connected:
            self._reset()
            return False
        if self._offline_since is None:
            self._offline_since = now
            return False
        if now - self._offline_since < policy.offline_after_seconds:
            return False

        try:
            self._scheduler.schedule_network_setup("automatic")
        except Exception:
            self._offline_since = now
            return False
        self._pending_since = now
        return True

    def _reset(self) -> None:
        self._offline_since = None
        self._pending_since = None


def activate_setup_runtime(
    *,
    data_dir: Path,
    trigger: RecoveryTrigger,
    service_user: str,
    service_group: str,
    mutation_lock: Path = Path("/run/lock/3mm-release-mutation.lock"),
) -> None:
    """Set the recovery marker and atomically ask the runtime planner for setup."""

    import fcntl
    import grp
    import pwd

    from three_mm_runtime.activate import activate

    marker = FileNetworkRecoveryMarker(data_dir / "network-recovery.json")
    mutation_lock.parent.mkdir(parents=True, exist_ok=True)
    with mutation_lock.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("A release mutation is already running") from exc
        owner = (
            pwd.getpwnam(service_user).pw_uid,
            grp.getgrnam(service_group).gr_gid,
        )
        marker.activate(trigger, owner=owner)
        try:
            activate(data_dir)
        except Exception:
            marker.clear()
            try:
                activate(data_dir)
            except Exception:
                pass
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--trigger", choices=("manual", "automatic"), required=True)
    parser.add_argument("--user", default="3mm")
    parser.add_argument("--group", default="3mm")
    arguments = parser.parse_args()
    activate_setup_runtime(
        data_dir=arguments.data_dir,
        trigger=arguments.trigger,
        service_user=arguments.user,
        service_group=arguments.group,
    )


if __name__ == "__main__":
    main()
