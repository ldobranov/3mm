import pytest

from agent.hardware import (
    HardwareProfile,
    HardwareSnapshot,
    LinuxHardwareDriver,
    MockHardwareDriver,
    create_hardware_driver,
)


def test_mock_hardware_profiles_are_deterministic_and_distinct():
    pi3 = MockHardwareDriver.for_profile(HardwareProfile.MOCK_PI3).collect()
    pi3_again = MockHardwareDriver.for_profile(HardwareProfile.MOCK_PI3).collect()
    zero2 = MockHardwareDriver.for_profile(HardwareProfile.MOCK_ZERO2).collect()

    assert pi3 == pi3_again
    assert pi3.model != zero2.model
    assert pi3.memory_total_bytes > zero2.memory_total_bytes
    assert pi3.capabilities == ("hardware.inventory",)
    assert zero2.capabilities == ("hardware.inventory",)


def test_native_profile_uses_generic_linux_driver():
    driver = create_hardware_driver(HardwareProfile.NATIVE)

    assert isinstance(driver, LinuxHardwareDriver)
    assert driver.collect().driver_id == "linux"


def test_native_profile_is_not_accepted_as_a_mock():
    with pytest.raises(ValueError):
        MockHardwareDriver.for_profile(HardwareProfile.NATIVE)


@pytest.mark.parametrize(
    "values",
    [
        {"driver_id": "", "architecture": "aarch64"},
        {"driver_id": "mock", "architecture": ""},
        {
            "driver_id": "mock",
            "architecture": "aarch64",
            "logical_cpu_count": 0,
        },
        {
            "driver_id": "mock",
            "architecture": "aarch64",
            "memory_total_bytes": 0,
        },
    ],
)
def test_hardware_snapshot_rejects_invalid_values(values):
    with pytest.raises(ValueError):
        HardwareSnapshot(model=None, **values)
