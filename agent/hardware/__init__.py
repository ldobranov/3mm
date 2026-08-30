"""Hardware inventory drivers available to the Agent."""

from agent.hardware.base import HardwareInventoryDriver, HardwareSnapshot
from agent.hardware.linux import LinuxHardwareDriver
from agent.hardware.mock import HardwareProfile, MockHardwareDriver
from agent.hardware.gpio import (
    DigitalGpioDriver, DigitalInput, DigitalInputEvent, DigitalOutput,
    MockDigitalGpioDriver,
)
from agent.hardware.gpiod import GpiodDigitalGpioDriver
from agent.hardware.identifier import MockIdentifierAdapter


def create_hardware_driver(
    profile: HardwareProfile,
) -> HardwareInventoryDriver:
    if profile is HardwareProfile.NATIVE:
        return LinuxHardwareDriver()
    return MockHardwareDriver.for_profile(profile)


def create_mock_gpio_driver(_profile: HardwareProfile) -> MockDigitalGpioDriver:
    """Create the isolated test GPIO driver for every Agent profile.

    This driver is never mapped to Linux GPIO pins.  Keeping it available on
    native hardware lets an approved mock module be acceptance-tested on a
    real device without granting it access to physical hardware.
    """
    return MockDigitalGpioDriver()


def create_gpio_driver(
    profile: HardwareProfile,
    *,
    driver_name: str = "mock",
    chip: str = "/dev/gpiochip0",
    inputs: dict[str, int] | None = None,
    outputs: dict[str, int] | None = None,
) -> DigitalGpioDriver:
    if driver_name == "mock":
        return create_mock_gpio_driver(profile)
    if driver_name == "gpiod":
        if profile is not HardwareProfile.NATIVE:
            raise ValueError("The gpiod driver requires the native hardware profile")
        return GpiodDigitalGpioDriver(
            chip=chip,
            inputs=dict(inputs or {}),
            outputs=dict(outputs or {}),
        )
    raise ValueError(f"Unsupported GPIO driver: {driver_name}")


__all__ = [
    "HardwareInventoryDriver",
    "HardwareProfile",
    "HardwareSnapshot",
    "LinuxHardwareDriver",
    "MockHardwareDriver",
    "create_hardware_driver",
    "create_gpio_driver",
    "create_mock_gpio_driver",
    "DigitalGpioDriver",
    "DigitalInput",
    "DigitalInputEvent",
    "DigitalOutput",
    "MockDigitalGpioDriver",
    "GpiodDigitalGpioDriver",
    "MockIdentifierAdapter",
]
