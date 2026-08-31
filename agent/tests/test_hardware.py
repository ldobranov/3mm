import pytest
import threading
from types import SimpleNamespace

from agent.hardware import (
    HardwareProfile,
    HardwareSnapshot,
    LinuxHardwareDriver,
    MockHardwareDriver,
    create_hardware_driver,
    create_mock_gpio_driver,
)
from agent.hardware.gpiod import GpiodDigitalGpioDriver


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


class _FakeLineRequest:
    def __init__(self, config):
        self.config = config
        self.values = {
            line: settings.output_value or "inactive"
            for line, settings in config.items()
        }
        self.released = False
        self.edge_ready = threading.Event()

    def get_value(self, line):
        return self.values[line]

    def set_value(self, line, value):
        self.values[line] = value

    def set_input_value(self, line, value):
        self.values[line] = value
        self.edge_ready.set()

    def wait_edge_events(self, timeout=None):
        ready = self.edge_ready.wait(timeout)
        if ready:
            self.edge_ready.clear()
        return ready

    def read_edge_events(self):
        return [object()]

    def release(self):
        self.released = True


class _FakeLineSettings:
    def __init__(self, **values):
        self.__dict__.update(values)
        self.output_value = values.get("output_value")


class _FakeGpiod:
    def __init__(self):
        self.line = SimpleNamespace(
            Direction=SimpleNamespace(INPUT="input", OUTPUT="output"),
            Bias=SimpleNamespace(PULL_UP="pull-up"),
            Edge=SimpleNamespace(BOTH="both"),
            Value=SimpleNamespace(ACTIVE="active", INACTIVE="inactive"),
        )
        self.LineSettings = _FakeLineSettings
        self.requests = []

    def request_lines(self, _chip, *, consumer, config):
        request = _FakeLineRequest(config)
        request.consumer = consumer
        self.requests.append(request)
        return request


def test_gpiod_driver_maps_active_low_input_and_output_then_releases_lines():
    fake = _FakeGpiod()
    gpio = GpiodDigitalGpioDriver(
        chip="/dev/gpiochip0",
        inputs={"gpio.input.1": 17},
        outputs={"gpio.output.1": 27},
        gpiod_module=fake,
    )

    assert gpio.input("gpio.input.1").read() is False
    input_settings = fake.requests[0].config[17]
    assert input_settings.bias == "pull-up"
    assert input_settings.active_low is True
    assert input_settings.edge_detection == "both"

    gpio.output("gpio.output.1").write(True)
    assert gpio.output("gpio.output.1").read() is True

    gpio.close()
    assert all(request.released for request in fake.requests)


def test_gpiod_input_delivers_edge_without_polling_delay():
    fake = _FakeGpiod()
    gpio = GpiodDigitalGpioDriver(
        chip="/dev/gpiochip0",
        inputs={"gpio.input.1": 17},
        gpiod_module=fake,
    )
    callback_ready = threading.Event()
    events = []
    gpio.input("gpio.input.1").subscribe(
        lambda event: (events.append(event), callback_ready.set())
    )

    fake.requests[0].set_input_value(17, "active")

    assert callback_ready.wait(0.5)
    assert [(event.value, event.sequence) for event in events] == [(True, 1)]
    gpio.close()


def test_gpiod_driver_supports_output_only_mapping():
    fake = _FakeGpiod()
    gpio = GpiodDigitalGpioDriver(
        chip="/dev/gpiochip0",
        inputs={},
        outputs={"gpio.output.1": 27},
        gpiod_module=fake,
    )

    gpio.output("gpio.output.1").write(True)

    assert gpio.output("gpio.output.1").read() is True
    gpio.close()


def test_gpiod_driver_rejects_overlapping_line_mappings():
    with pytest.raises(ValueError, match="both an input and an output"):
        GpiodDigitalGpioDriver(
            chip="/dev/gpiochip0",
            inputs={"gpio.input.1": 17},
            outputs={"gpio.output.1": 17},
            gpiod_module=_FakeGpiod(),
        )
