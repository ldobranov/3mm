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
    unsubscribers: list
    automation_unsubscribers: dict

    def state(self) -> dict:
        return {"inputs": {item: self.gpio.input(item).read() for item in self.inputs}, "outputs": {item: self.gpio.output(item).read() for item in self.outputs}}

    def state_for(self, capability_id: str) -> dict:
        if capability_id == "gpio.digital.input":
            return {item: self.gpio.input(item).read() for item in self.inputs}
        return {item: self.gpio.output(item).read() for item in self.outputs}

    def invoke(self, action: str, arguments: dict) -> dict:
        if action != "set_output":
            raise ModuleLifecycleError("unsupported GPIO capability action")
        capability_id = arguments.get("capability_id") or arguments.get("channel")
        value = arguments.get("value")
        if capability_id not in self.outputs or not isinstance(value, bool):
            raise ModuleLifecycleError("invalid GPIO output request")
        self.gpio.output(capability_id).write(value)
        state = self.state()
        (self.data_dir / "gpio-runtime.json").write_text(json.dumps(state, indent=2) + "\n")
        return state

    def close(self) -> None:
        for unsubscribe in self.unsubscribers:
            unsubscribe()
        self.unsubscribers.clear()
        for unsubscribe in self.automation_unsubscribers.values():
            unsubscribe()
        self.automation_unsubscribers.clear()

    def subscribe(self, automation_id: str, event: str, conditions: dict, callback) -> None:
        if event not in {"changed", "input.changed", "gpio.input.changed"}:
            raise ModuleLifecycleError("unsupported GPIO automation event")
        input_id = conditions.get("channel") or conditions.get("capability_id")
        expected = conditions.get("value")
        if input_id not in self.inputs or not isinstance(expected, bool):
            raise ModuleLifecycleError("invalid GPIO automation trigger")
        self.unsubscribe(automation_id)
        self.automation_unsubscribers[automation_id] = self.gpio.input(input_id).subscribe(
            lambda input_event: callback() if input_event.value == expected else None
        )

    def unsubscribe(self, automation_id: str) -> None:
        unsubscribe = self.automation_unsubscribers.pop(automation_id, None)
        if unsubscribe is not None:
            unsubscribe()

def gpio_runtime_handler(gpio: DigitalGpioDriver, event_sink=lambda _event: None):
    def activate(manifest: ModuleManifestV2, data_dir: Path) -> dict[str, DigitalGpioCapabilityService]:
        config = manifest.configuration_defaults
        inputs = config.get("inputs", [])
        outputs = config.get("outputs", {})
        rules = config.get("rules", [])
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
        if not isinstance(rules, list):
            raise ModuleLifecycleError("GPIO rules configuration is invalid")
        unsubscribers = []
        for input_id in inputs:
            unsubscribers.append(gpio.input(input_id).subscribe(
                lambda event: event_sink({
                    "event_type": "gpio.input.changed",
                    "payload": {
                        "capability_id": "gpio.digital.input",
                        "channel": event.capability_id,
                        "value": event.value,
                        "sequence": event.sequence,
                    },
                })
            ))
        for rule in rules:
            if not isinstance(rule, dict) or not all(key in rule for key in ("input", "output", "when", "set")):
                raise ModuleLifecycleError("GPIO rule is invalid")
            input_id, output_id = rule["input"], rule["output"]
            if not isinstance(input_id, str) or not isinstance(output_id, str) or not isinstance(rule["when"], bool) or not isinstance(rule["set"], bool):
                raise ModuleLifecycleError("GPIO rule is invalid")
            gpio.input(input_id).read(); gpio.output(output_id).read()
            def on_input(event, expected=rule["when"], target=output_id, target_value=rule["set"]):
                if event.value == expected:
                    gpio.output(target).write(target_value)
            unsubscribers.append(gpio.input(input_id).subscribe(on_input))
        state = {"inputs": {item: gpio.input(item).read() for item in inputs}, "outputs": {item: gpio.output(item).read() for item in outputs}}
        (data_dir / "gpio-runtime.json").write_text(json.dumps(state, indent=2) + "\n")
        service = DigitalGpioCapabilityService(gpio, inputs, list(outputs), data_dir, unsubscribers, {})
        return {item.registration_id: service for item in manifest.registrations if item.kind == "capability"}
    return activate
