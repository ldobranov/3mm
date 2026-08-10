import pytest

from three_mm_provisioning import (
    NetworkDeviceStatus,
    NetworkInspectionError,
    NetworkManagerProvisioningPlanner,
    NetworkManagerStatus,
)


class StubInspector:
    def __init__(self, status):
        self.status = status
        self.calls = 0

    def inspect(self):
        self.calls += 1
        return self.status


def _status(*devices, running=True, wifi_hardware_enabled=True):
    return NetworkManagerStatus(
        running=running,
        state="connected",
        connectivity="full",
        wifi_hardware_enabled=wifi_hardware_enabled,
        wifi_enabled=True,
        devices=tuple(devices),
    )


def _wifi(name="wlan0"):
    return NetworkDeviceStatus(
        interface=name,
        device_type="wifi",
        state="connected",
    )


def test_dry_run_selects_the_only_wifi_interface_without_enabling_mutation():
    inspector = StubInspector(_status(_wifi()))

    plan = NetworkManagerProvisioningPlanner(inspector).dry_run()

    assert inspector.calls == 1
    assert plan.interface == "wlan0"
    assert plan.mutation_enabled is False
    assert plan.operations == (
        "enable_wifi",
        "create_open_setup_access_point",
        "expose_captive_setup_portal",
        "stage_target_wifi_profile",
        "activate_target_wifi_profile",
        "verify_connectivity",
        "commit_or_restore_setup_access_point",
    )


def test_dry_run_requires_explicit_selection_for_multiple_wifi_interfaces():
    inspector = StubInspector(_status(_wifi("wlan0"), _wifi("wlan1")))

    with pytest.raises(NetworkInspectionError):
        NetworkManagerProvisioningPlanner(inspector).dry_run()

    selected = NetworkManagerProvisioningPlanner(inspector, "wlan1").dry_run()
    assert selected.interface == "wlan1"


@pytest.mark.parametrize(
    "status",
    [
        _status(_wifi(), running=False),
        _status(_wifi(), wifi_hardware_enabled=False),
        _status(),
    ],
)
def test_dry_run_rejects_unsafe_or_unavailable_network_manager_state(status):
    with pytest.raises(NetworkInspectionError):
        NetworkManagerProvisioningPlanner(StubInspector(status)).dry_run()


def test_plan_representation_contains_no_network_credentials():
    plan = NetworkManagerProvisioningPlanner(StubInspector(_status(_wifi()))).dry_run()

    rendered = repr(plan).lower()
    assert "password" not in rendered
    assert "passphrase" not in rendered
    assert "ssid" not in rendered
