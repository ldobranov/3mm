import hashlib
import io
from pathlib import Path
from zipfile import ZipFile

from agent.hardware import MockDigitalGpioDriver
from agent.module_runtime import AgentModuleRuntime
from agent.modules.gpio import GPIO_ENTRYPOINT, gpio_runtime_handler
from backend.services.module_packages import validate_module_package


def test_digital_output_package_does_not_request_an_input(tmp_path):
    source = Path(__file__).resolve().parents[2] / "modules/digital-output"
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        for name in ("manifest.json", "health/ready"):
            archive.writestr(name, (source / name).read_bytes())
    payload = output.getvalue()
    manifest = validate_module_package(payload, architecture="armv6l").manifest
    assert manifest.configuration_defaults["inputs"] == []

    class OutputOnlyDriver(MockDigitalGpioDriver):
        def input(self, capability_id):
            raise AssertionError("Output-only package must not claim an input")

    gpio = OutputOnlyDriver()
    runtime = AgentModuleRuntime(tmp_path, architecture="armv6l", runtime_handlers={
        GPIO_ENTRYPOINT: gpio_runtime_handler(gpio),
    })
    runtime.install(payload, expected_sha256=hashlib.sha256(payload).hexdigest())
    assert runtime.capability_states() == {"gpio.digital.control": {"gpio.output.1": False}}
    runtime.invoke("gpio.digital.control", "set_output", {"channel": "gpio.output.1", "value": True})
    assert gpio.output("gpio.output.1").read() is True
    runtime.disable(manifest.module_id)
    assert gpio.output("gpio.output.1").read() is False
