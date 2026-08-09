import pytest

from agent.hardware import (
    HardwareProfile,
    HardwareSnapshot,
    LinuxHardwareDriver,
    MockHardwareDriver,
    create_hardware_driver,
    create_mock_gpio_driver,
)


def test_mock_hardware_profiles_are_deterministic_and_distinct():
    pi3 = MockHardwareDriver.for_profile(HardwareProfile.MOCK_PI3).collect()
    pi3_again = MockHardwareDriver.for_profile(HardwareProfile.MOCK_PI3).collect()
    zero2 = MockHardwareDriver.for_profile(HardwareProfile.MOCK_ZERO2).collect()

    assert pi3 == pi3_again
    assert pi3.model != zero2.model
    assert pi3.memory_total_bytes > zero2.memory_total_bytes
    assert "hardware.gpio.digital_input" in pi3.capabilities
    assert "hardware.gpio.digital_output" in zero2.capabilities


def test_native_profile_uses_generic_linux_driver():
    driver = create_hardware_driver(HardwareProfile.NATIVE)

    assert isinstance(driver, LinuxHardwareDriver)
    assert driver.collect().driver_id == "linux"


def test_native_profile_has_an_isolated_mock_gpio_driver():
    gpio = create_mock_gpio_driver(HardwareProfile.NATIVE)

    gpio.output("gpio.output.1").write(True)

    assert gpio.output("gpio.output.1").read() is True


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


def test_mock_gpio_is_deterministic_and_emits_only_real_input_transitions():
    from agent.hardware import MockDigitalGpioDriver

    gpio = MockDigitalGpioDriver(inputs={"input.button": False}, outputs={"output.led": False})
    events = []
    unsubscribe = gpio.input("input.button").subscribe(events.append)

    assert gpio.set_input("input.button", False) is None
    first = gpio.set_input("input.button", True)
    gpio.output("output.led").write(True)
    second = gpio.set_input("input.button", False)
    unsubscribe()
    gpio.set_input("input.button", True)

    assert (first.sequence, first.value) == (1, True)
    assert (second.sequence, second.value) == (2, False)
    assert events == [first, second]
    assert gpio.output("output.led").read() is True


def test_mock_gpio_rejects_unknown_capabilities():
    from agent.hardware import MockDigitalGpioDriver
    gpio = MockDigitalGpioDriver()
    with pytest.raises(KeyError):
        gpio.input("missing")
    with pytest.raises(KeyError):
        gpio.output("missing")
