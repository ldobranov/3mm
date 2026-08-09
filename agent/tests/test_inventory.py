from agent.inventory import _network_manager_active
from three_mm_provisioning import (
    NetworkInspectionError,
    NetworkManagerStatus,
)


class StubAdapter:
    def inspect(self):
        return NetworkManagerStatus(
            running=True,
            state="connected",
            connectivity="full",
            wifi_hardware_enabled=True,
            wifi_enabled=True,
            devices=(),
        )


def test_network_manager_inventory_uses_read_only_adapter(monkeypatch):
    monkeypatch.setattr(
        "agent.inventory.NetworkManagerReadOnlyAdapter.from_system",
        lambda: StubAdapter(),
    )

    assert _network_manager_active() is True


def test_network_manager_inventory_is_unknown_when_inspection_fails(monkeypatch):
    def unavailable():
        raise NetworkInspectionError("unavailable")

    monkeypatch.setattr(
        "agent.inventory.NetworkManagerReadOnlyAdapter.from_system",
        unavailable,
    )

    assert _network_manager_active() is None
