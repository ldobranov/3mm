from pathlib import Path

from three_mm_protocol import AgentRole
from three_mm_provisioning import (
    FileNetworkRecoveryMarker,
    FileNetworkRecoveryPolicyStore,
    FileProvisioningStore,
    NetworkCredentials,
    NetworkDeviceStatus,
    NetworkManagerStatus,
    NetworkRecoveryPolicy,
    ProvisioningRequest,
    ProvisioningSnapshot,
)
from three_mm_runtime.network_recovery import NetworkRecoveryMonitor


def provisioned_store(path: Path) -> FileProvisioningStore:
    store = FileProvisioningStore(path)
    store.save(
        ProvisioningSnapshot.provisioned(
            ProvisioningRequest(
                network=NetworkCredentials("network", "not-persisted"),
                locale="en-GB",
                device_name="device",
                administrator_name="admin",
                role=AgentRole.STANDALONE,
            )
        )
    )
    return store


def network_status(*, connected_type: str | None) -> NetworkManagerStatus:
    devices = () if connected_type is None else (
        NetworkDeviceStatus("test0", connected_type, "connected"),
    )
    return NetworkManagerStatus(
        running=True,
        state="connected" if connected_type else "disconnected",
        connectivity="full" if connected_type else "none",
        wifi_hardware_enabled=True,
        wifi_enabled=True,
        devices=devices,
    )


class Inspector:
    def __init__(self, status: NetworkManagerStatus) -> None:
        self.status = status

    def inspect(self) -> NetworkManagerStatus:
        return self.status


class Scheduler:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def schedule_network_setup(self, trigger: str) -> None:
        self.calls.append(trigger)


def build_monitor(tmp_path: Path, clock, inspector: Inspector, scheduler: Scheduler):
    data_dir = tmp_path / "provisioning"
    return NetworkRecoveryMonitor(
        policy_store=FileNetworkRecoveryPolicyStore(tmp_path / "policy.json"),
        marker=FileNetworkRecoveryMarker(data_dir / "network-recovery.json"),
        provisioning_store=provisioned_store(data_dir),
        inspector=inspector,
        scheduler=scheduler,
        clock=lambda: clock[0],
    )


def test_both_links_must_remain_disconnected_for_five_uninterrupted_minutes(
    tmp_path: Path,
) -> None:
    clock = [0.0]
    inspector = Inspector(network_status(connected_type=None))
    scheduler = Scheduler()
    monitor = build_monitor(tmp_path, clock, inspector, scheduler)

    assert monitor.poll() is False
    clock[0] = 299.0
    assert monitor.poll() is False
    inspector.status = network_status(connected_type="ethernet")
    assert monitor.poll() is False
    inspector.status = network_status(connected_type=None)
    clock[0] = 400.0
    assert monitor.poll() is False
    clock[0] = 700.0
    assert monitor.poll() is True
    assert scheduler.calls == ["automatic"]


def test_wifi_also_resets_the_offline_timer(tmp_path: Path) -> None:
    clock = [0.0]
    inspector = Inspector(network_status(connected_type=None))
    scheduler = Scheduler()
    monitor = build_monitor(tmp_path, clock, inspector, scheduler)
    monitor.poll()
    clock[0] = 200.0
    inspector.status = network_status(connected_type="wifi")
    monitor.poll()
    clock[0] = 500.0
    inspector.status = network_status(connected_type=None)

    assert monitor.poll() is False
    assert scheduler.calls == []


def test_disabled_policy_never_schedules_setup(tmp_path: Path) -> None:
    policy = FileNetworkRecoveryPolicyStore(tmp_path / "policy.json")
    policy.save(NetworkRecoveryPolicy(automatic_setup_enabled=False))
    clock = [0.0]
    inspector = Inspector(network_status(connected_type=None))
    scheduler = Scheduler()
    data_dir = tmp_path / "provisioning"
    monitor = NetworkRecoveryMonitor(
        policy_store=policy,
        marker=FileNetworkRecoveryMarker(data_dir / "network-recovery.json"),
        provisioning_store=provisioned_store(data_dir),
        inspector=inspector,
        scheduler=scheduler,
        clock=lambda: clock[0],
    )

    monitor.poll()
    clock[0] = 1000.0
    monitor.poll()

    assert scheduler.calls == []
