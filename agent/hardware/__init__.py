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


def create_mock_gpio_driver(profile: HardwareProfile) -> MockDigitalGpioDriver | None:
    if profile is HardwareProfile.NATIVE:
        return None
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
