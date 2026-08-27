from pathlib import Path

from three_mm_protocol import AgentRole
from three_mm_provisioning import (
    FileProvisioningStore,
    NetworkCredentials,
    ProvisioningRequest,
    ProvisioningSnapshot,
    FileNetworkRecoveryMarker,
)
from three_mm_provisioning import setup_access_point


class FakeBoundary:
    calls = []

    def connection_uuid(self, name):
        self.calls.append(("uuid", name))
        return None

    def create_temporary_open_setup_access_point(self, **values):
        self.calls.append(("create", values))


def test_unprovisioned_device_creates_open_machine_specific_ap(tmp_path, monkeypatch):
    machine_id = tmp_path / "machine-id"
    machine_id.write_text("0123456789abcdef\n", encoding="utf-8")
    FakeBoundary.calls = []
    monkeypatch.setattr(
        setup_access_point,
        "NetworkManagerMutationBoundary",
        FakeBoundary,
    )

    setup_access_point.start(tmp_path / "state", "wlan0", machine_id)

    create = next(call[1] for call in FakeBoundary.calls if call[0] == "create")
    assert create["network_name"] == "3mm Setup CDEF"
    assert "passphrase" not in create


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


def test_recovery_marker_allows_a_provisioned_device_to_create_setup_ap(
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
    monkeypatch.setattr(setup_access_point, "NetworkManagerMutationBoundary", FakeBoundary)

    setup_access_point.start(state_dir, "wlan0", machine_id)

    assert any(call[0] == "create" for call in FakeBoundary.calls)
