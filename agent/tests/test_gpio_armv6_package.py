"""Exercise the shipped GPIO package with ARMv6 admission and mock hardware."""

import hashlib
import io
from pathlib import Path
from zipfile import ZipFile

from agent.hardware import MockDigitalGpioDriver
from agent.module_runtime import AgentModuleRuntime
from agent.modules.gpio import GPIO_ENTRYPOINT, gpio_runtime_handler
from backend.services.module_packages import validate_module_package


SOURCE = Path(__file__).resolve().parents[2] / "modules/mock-gpio"


def test_shipped_gpio_package_accepts_armv6_and_executes_with_mock(tmp_path):
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        for name in ("manifest.json", "health/ready"):
            archive.writestr(name, (SOURCE / name).read_bytes())
    payload = output.getvalue()
    validated = validate_module_package(payload, architecture="armv6l")
    assert validated.manifest.version == "1.0.6"

    gpio = MockDigitalGpioDriver()
    events = []
    runtime = AgentModuleRuntime(
        tmp_path,
        architecture="armv6l",
        runtime_handlers={GPIO_ENTRYPOINT: gpio_runtime_handler(gpio, events.append)},
    )
    result = runtime.install(payload, expected_sha256=hashlib.sha256(payload).hexdigest())
    assert result.status == "active"
    assert {item["registration_id"] for item in runtime.registrations()} == {
        "gpio.digital.input", "gpio.digital.control"
    }
    gpio.set_input("gpio.input.1", True)
    assert runtime.capability_states()["gpio.digital.input"] == {"gpio.input.1": True}
    assert events[-1]["event_type"] == "gpio.input.changed"
    state = runtime.invoke(
        "gpio.digital.control", "set_output", {"channel": "gpio.output.1", "value": True}
    )
    assert state["outputs"]["gpio.output.1"] is True
    runtime.disable(validated.manifest.module_id)
    assert gpio.output("gpio.output.1").read() is False
    assert runtime.registrations() == []
