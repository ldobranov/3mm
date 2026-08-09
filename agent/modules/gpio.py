"""Handler for the generic trusted ``builtin:gpio.digital.v1`` contract."""
from __future__ import annotations
import json
from pathlib import Path
from agent.hardware.gpio import DigitalGpioDriver
from agent.module_runtime import ModuleLifecycleError
from three_mm_protocol import ModuleManifestV2

GPIO_ENTRYPOINT = "builtin:gpio.digital.v1"

def gpio_runtime_handler(gpio: DigitalGpioDriver):
    def activate(manifest: ModuleManifestV2, data_dir: Path) -> None:
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
    return activate
