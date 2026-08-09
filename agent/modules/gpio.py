"""Handler for the generic trusted ``builtin:gpio.digital.v1`` contract."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from agent.hardware.gpio import DigitalGpioDriver
from agent.module_runtime import ModuleLifecycleError
from three_mm_protocol import ModuleManifestV2

GPIO_ENTRYPOINT = "builtin:gpio.digital.v1"

@dataclass
class DigitalGpioCapabilityService:
    gpio: DigitalGpioDriver
    inputs: list[str]
    outputs: list[str]
    data_dir: Path

    def state(self) -> dict:
        return {"inputs": {item: self.gpio.input(item).read() for item in self.inputs}, "outputs": {item: self.gpio.output(item).read() for item in self.outputs}}

    def invoke(self, action: str, arguments: dict) -> dict:
        if action != "set_output":
            raise ModuleLifecycleError("unsupported GPIO capability action")
        capability_id = arguments.get("capability_id")
        value = arguments.get("value")
        if capability_id not in self.outputs or not isinstance(value, bool):
            raise ModuleLifecycleError("invalid GPIO output request")
        self.gpio.output(capability_id).write(value)
        state = self.state()
        (self.data_dir / "gpio-runtime.json").write_text(json.dumps(state, indent=2) + "\n")
        return state

def gpio_runtime_handler(gpio: DigitalGpioDriver):
    def activate(manifest: ModuleManifestV2, data_dir: Path) -> dict[str, DigitalGpioCapabilityService]:
        config = manifest.configuration_defaults
        inputs = config.get("inputs", [])
        outputs = config.get("outputs", {})
        if not isinstance(inputs, list) or not all(isinstance(item, str) for item in inputs):
            raise ModuleLifecycleError("GPIO inputs configuration is invalid")
        if not isinstance(outputs, dict) or not all(isinstance(key, str) and isinstance(value, bool) for key, value in outputs.items()):
            raise ModuleLifecycleError("GPIO outputs configuration is invalid")
        try:
            for capability_id in inputs:
                gpio.input(capability_id).read()
            for capability_id, value in outputs.items():
                gpio.output(capability_id).write(value)
        except KeyError as exc:
            raise ModuleLifecycleError("GPIO capability is unavailable") from exc
        state = {"inputs": {item: gpio.input(item).read() for item in inputs}, "outputs": {item: gpio.output(item).read() for item in outputs}}
        (data_dir / "gpio-runtime.json").write_text(json.dumps(state, indent=2) + "\n")
        return {item.registration_id: DigitalGpioCapabilityService(gpio, inputs, list(outputs), data_dir) for item in manifest.registrations if item.kind == "capability"}
    return activate
