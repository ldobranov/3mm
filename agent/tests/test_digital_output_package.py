import hashlib
import importlib.util
import io
from pathlib import Path
import time
from zipfile import ZipFile

import pytest

from agent.config import AgentSettings
from agent.gpio_configuration import GpioConfigurationManager
from agent.hardware import HardwareProfile, MockDigitalGpioDriver
from agent.module_runtime import AgentModuleRuntime
from agent.modules.gpio import GPIO_ENTRYPOINT, gpio_runtime_handler
from backend.services.module_packages import validate_module_package
from three_mm_protocol.capability_contracts import CapabilityContractError


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


def test_versioned_output_package_matches_managed_mock_and_refuses_drift(tmp_path):
    source = Path(__file__).resolve().parents[2] / "modules/digital-output"
    spec = importlib.util.spec_from_file_location("output_fixture_builder", source / "build_package.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    payload = builder.build_package(versioned=True)
    assert payload == builder.build_package(versioned=True)
    manifest = validate_module_package(payload, architecture="armv6l").manifest
    assert manifest.version == "1.1.0"
    assert validate_module_package(builder.build_package(), architecture="armv6l").manifest.version == "1.0.0"
    contract = manifest.registrations[0].contract

    class OutputOnlyDriver(MockDigitalGpioDriver):
        def input(self, capability_id):
            raise AssertionError("Output-only package must not access inputs")

    def factory(_profile, *, driver_name, **_kwargs):
        assert driver_name == "mock"
        return OutputOnlyDriver()

    manager = GpioConfigurationManager(
        AgentSettings(data_dir=tmp_path, hardware_profile=HardwareProfile.NATIVE, gpio_driver="mock"),
        model="Raspberry Pi Zero W Rev 1.1", driver_factory=factory)
    runtime = AgentModuleRuntime(tmp_path, architecture="armv6l",
        runtime_handlers={GPIO_ENTRYPOINT: manager.handler(lambda _event: None)})
    manager.apply({"expected_revision": manager.describe(runtime)["revision"], "confirmed_safe": True,
                   "configuration": {"driver": "mock", "bcm_pin": 17}}, runtime)
    runtime.install(payload, expected_sha256=hashlib.sha256(payload).hexdigest())
    args = {"channel": "gpio.output.1", "duration_ms": 50}
    valid = {"contract_version": "1.0", "contract_digest": contract.digest()}
    try:
        for action, values, binding in (
            ("pulse_output", args, {}),
            ("pulse_output", args, {**valid, "contract_digest": "0" * 64}),
            ("pulse_output", args, {**valid, "contract_version": "2.0"}),
            ("pulse", args, valid),
            ("pulse_output", {**args, "channel": "gpio.output.2"}, valid),
            ("pulse_output", {**args, "duration_ms": 49}, valid),
            ("pulse_output", {**args, "duration_ms": True}, valid),
            ("pulse_output", {**args, "extra": True}, valid),
        ):
            with pytest.raises(CapabilityContractError):
                runtime.invoke("gpio.digital.control", action, values, **binding)
            assert manager.driver.output("gpio.output.1").read() is False
        result = runtime.invoke("gpio.digital.control", "pulse_output", args, **valid)
        assert result["inputs"] == {}
        assert result["outputs"] == {"gpio.output.1": True}
        deadline = time.monotonic() + 2
        while manager.driver.output("gpio.output.1").read() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runtime.capability_states() == {"gpio.digital.control": {"gpio.output.1": False}}
        runtime.invoke("gpio.digital.control", "set_output",
                       {"channel": "gpio.output.1", "value": True}, **valid)
        assert manager.driver.output("gpio.output.1").read() is True
        runtime.disable(manifest.module_id)
        assert manager.driver.output("gpio.output.1").read() is False
    finally:
        runtime.close()
        manager.close()
