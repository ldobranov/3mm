"""Hardware inventory drivers available to the Agent."""

from agent.hardware.base import HardwareInventoryDriver, HardwareSnapshot
from agent.hardware.linux import LinuxHardwareDriver
from agent.hardware.mock import HardwareProfile, MockHardwareDriver
from agent.hardware.gpio import (
    DigitalGpioDriver, DigitalInput, DigitalInputEvent, DigitalOutput,
    MockDigitalGpioDriver,
)


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


__all__ = [
    "HardwareInventoryDriver",
    "HardwareProfile",
    "HardwareSnapshot",
    "LinuxHardwareDriver",
    "MockHardwareDriver",
    "create_hardware_driver",
    "create_mock_gpio_driver",
    "DigitalGpioDriver",
    "DigitalInput",
    "DigitalInputEvent",
    "DigitalOutput",
    "MockDigitalGpioDriver",
]
