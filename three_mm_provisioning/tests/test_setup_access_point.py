from pathlib import Path

from three_mm_protocol import AgentRole
from three_mm_provisioning import (
    FileNetworkRecoveryMarker,
    FileProvisioningStore,
    NetworkCredentials,
    NetworkDeviceStatus,
    NetworkManagerStatus,
    ProvisioningRequest,
    ProvisioningSnapshot,
    setup_access_point,
)
from three_mm_provisioning.network_manager import WifiNetwork
from three_mm_provisioning.wifi_scan_cache import read_wifi_scan_cache


class FakeBoundary:
    calls = []

    def connection_uuid(self, name):
        self.calls.append(("uuid", name))
        return None

    def create_temporary_open_setup_access_point(self, **values):
        self.calls.append(("create", values))


class FakeScanner:
    calls = []

    @classmethod
    def from_system(cls, **values):
        cls.calls.append(("from_system", values))
        return cls()

    def scan_wifi_networks(self, **values):
        self.calls.append(("scan", values))
        return (
            WifiNetwork("Nearby Wi-Fi", 77, True),
            WifiNetwork("3mm Setup CDEF", 100, False),
        )

    def inspect(self):
        return NetworkManagerStatus(True, 'connected', 'full', True, True,
            (NetworkDeviceStatus('wlan0', 'wifi', 'connected'),))

    def _execute(self, *arguments):
        return 'yes' if 'WIFI-PROPERTIES.AP' in arguments else 'Existing SSH Wi-Fi'


def test_unprovisioned_device_creates_open_machine_specific_ap_from_connected_wifi(tmp_path, monkeypatch):
    machine_id = tmp_path / "machine-id"
    machine_id.write_text("0123456789abcdef\n", encoding="utf-8")
    FakeBoundary.calls = []
    monkeypatch.setattr(
        setup_access_point,
        "NetworkManagerMutationBoundary",
        FakeBoundary,
    )
    FakeScanner.calls = []
    monkeypatch.setattr(
        setup_access_point,
        "NetworkManagerReadOnlyAdapter",
        FakeScanner,
    )

    monkeypatch.setenv('THREE_MM_NETWORK_BACKEND', 'network-manager')
    monkeypatch.setattr('three_mm_provisioning.network_capabilities.NetworkManagerReadOnlyAdapter', FakeScanner)
    state_dir = tmp_path / "state"
    setup_access_point.start(state_dir, "wlan0", machine_id)

    create = next(call[1] for call in FakeBoundary.calls if call[0] == "create")
    assert create["network_name"] == "3mm Setup CDEF"
    assert create["ipv4_address"] == "10.42.0.1/24"
    assert "passphrase" not in create
    assert ("scan", {"rescan": True, "interface": "wlan0"}) in FakeScanner.calls
    assert read_wifi_scan_cache(state_dir) == (WifiNetwork("Nearby Wi-Fi", 77, True),)


def test_provisioned_device_does_not_create_setup_ap(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    FileProvisioningStore(Path(state_dir)).save(
        ProvisioningSnapshot.provisioned(
            ProvisioningRequest(
                network=NetworkCredentials("private-network", "not-persisted"),
                locale="en-GB",
                device_name="test-device",
                administrator_name="admin",
                role=AgentRole.STANDALONE,
            )
        )
    )
    FakeBoundary.calls = []
    monkeypatch.setattr(
        setup_access_point,
        "NetworkManagerMutationBoundary",
        FakeBoundary,
    )

    setup_access_point.start(state_dir, "wlan0", tmp_path / "missing")

    assert FakeBoundary.calls == []


def test_recovery_marker_never_replaces_workloads_with_setup_ap(
    tmp_path, monkeypatch
):
    state_dir = tmp_path / "state"
    FileProvisioningStore(state_dir).save(
        ProvisioningSnapshot.provisioned(
            ProvisioningRequest(
                network=NetworkCredentials("private-network", "not-persisted"),
                locale="en-GB",
                device_name="test-device",
                administrator_name="admin",
                role=AgentRole.STANDALONE,
            )
        )
    )
    FileNetworkRecoveryMarker(state_dir / "network-recovery.json").activate("manual")
    machine_id = tmp_path / "machine-id"
    machine_id.write_text("0123456789abcdef\n", encoding="utf-8")
    FakeBoundary.calls = []
    monkeypatch.setattr(
        setup_access_point, "NetworkManagerMutationBoundary", FakeBoundary
    )

    setup_access_point.start(state_dir, "wlan0", machine_id)

    assert FakeBoundary.calls == []
