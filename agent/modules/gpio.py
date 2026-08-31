"""Handler for the generic trusted ``builtin:gpio.digital.v1`` contract."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from agent.hardware.gpio import DigitalGpioDriver
from agent.module_runtime import ModuleLifecycleError
from three_mm_protocol import ModuleManifestV2


GPIO_ENTRYPOINT = "builtin:gpio.digital.v1"
logger = logging.getLogger(__name__)


@dataclass
class DigitalGpioCapabilityService:
    gpio: DigitalGpioDriver
    inputs: list[str]
    outputs: list[str]
    output_safe_states: dict[str, bool]
    data_dir: Path
    event_sink: Callable[[dict], None]
    pulse_min_ms: int
    pulse_max_ms: int
    pulse_cooldown_ms: int
    unsubscribers: list[Callable[[], None]] = field(default_factory=list)
    automation_unsubscribers: dict[str, Callable[[], None]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _pulse_timers: dict[str, threading.Timer] = field(default_factory=dict, init=False, repr=False)
    _cooldown_until: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def _state_locked(self) -> dict:
        return {
            "inputs": {item: self.gpio.input(item).read() for item in self.inputs},
            "outputs": {item: self.gpio.output(item).read() for item in self.outputs},
        }

    def _persist_state_locked(self) -> None:
        state_path = self.data_dir / "gpio-runtime.json"
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._state_locked(), indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, state_path)

    def _emit_output_event(
        self,
        *,
        channel: str,
        value: bool,
        reason: str,
        duration_ms: int | None = None,
    ) -> None:
        payload = {
            "capability_id": "gpio.digital.control",
            "channel": channel,
            "value": value,
            "reason": reason,
        }
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        try:
            self.event_sink({"event_type": "gpio.output.changed", "payload": payload})
        except Exception:
            logger.exception("GPIO output event delivery failed for capability %s", channel)

    def state(self) -> dict:
        with self._lock:
            return self._state_locked()

    def state_for(self, capability_id: str) -> dict:
        with self._lock:
            if capability_id == "gpio.digital.input":
                return {item: self.gpio.input(item).read() for item in self.inputs}
            return {item: self.gpio.output(item).read() for item in self.outputs}

    def invoke(self, action: str, arguments: dict) -> dict:
        if action == "set_output":
            return self._set_output(arguments)
        if action == "pulse_output":
            return self._pulse_output(arguments)
        raise ModuleLifecycleError("unsupported GPIO capability action")

    def _output_id(self, arguments: dict) -> str:
        capability_id = arguments.get("capability_id") or arguments.get("channel")
        if capability_id not in self.outputs:
            raise ModuleLifecycleError("invalid GPIO output request")
        return capability_id

    def _set_output(self, arguments: dict) -> dict:
        capability_id = self._output_id(arguments)
        value = arguments.get("value")
        if not isinstance(value, bool):
            raise ModuleLifecycleError("invalid GPIO output request")
        with self._lock:
            if self._closed:
                raise ModuleLifecycleError("GPIO capability is closed")
            if capability_id in self._pulse_timers:
                raise ModuleLifecycleError("GPIO output pulse is already active")
            self.gpio.output(capability_id).write(value)
            self._persist_state_locked()
            state = self._state_locked()
        self._emit_output_event(channel=capability_id, value=value, reason="set")
        return state

    def _pulse_output(self, arguments: dict) -> dict:
        capability_id = self._output_id(arguments)
        duration_ms = arguments.get("duration_ms")
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, int):
            raise ModuleLifecycleError(
                "GPIO pulse duration must be an integer number of milliseconds"
            )
        if not self.pulse_min_ms <= duration_ms <= self.pulse_max_ms:
            raise ModuleLifecycleError(
                f"GPIO pulse duration must be between {self.pulse_min_ms} and "
                f"{self.pulse_max_ms} milliseconds"
            )

        with self._lock:
            if self._closed:
                raise ModuleLifecycleError("GPIO capability is closed")
            if capability_id in self._pulse_timers:
                raise ModuleLifecycleError("GPIO output pulse is already active")
            if time.monotonic() < self._cooldown_until.get(capability_id, 0.0):
                raise ModuleLifecycleError("GPIO output pulse is cooling down")
            safe_value = self.output_safe_states[capability_id]
            active_value = not safe_value
            self.gpio.output(capability_id).write(active_value)
            timer = threading.Timer(
                duration_ms / 1000,
                self._complete_pulse,
                kwargs={"capability_id": capability_id, "duration_ms": duration_ms},
            )
            timer.daemon = True
            self._pulse_timers[capability_id] = timer
            self._persist_state_locked()
            state = self._state_locked()
            timer.start()
        self._emit_output_event(
            channel=capability_id,
            value=active_value,
            reason="pulse_started",
            duration_ms=duration_ms,
        )
        return {
            **state,
            "pulse": {
                "channel": capability_id,
                "duration_ms": duration_ms,
                "active_value": active_value,
                "safe_value": safe_value,
            },
        }

    def _complete_pulse(self, *, capability_id: str, duration_ms: int) -> None:
        with self._lock:
            if self._closed or capability_id not in self._pulse_timers:
                return
            self._pulse_timers.pop(capability_id, None)
            safe_value = self.output_safe_states[capability_id]
            self.gpio.output(capability_id).write(safe_value)
            self._cooldown_until[capability_id] = (
                time.monotonic() + self.pulse_cooldown_ms / 1000
            )
            self._persist_state_locked()
        self._emit_output_event(
            channel=capability_id,
            value=safe_value,
            reason="pulse_completed",
            duration_ms=duration_ms,
        )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for timer in self._pulse_timers.values():
                timer.cancel()
            self._pulse_timers.clear()
            for capability_id, safe_value in self.output_safe_states.items():
                self.gpio.output(capability_id).write(safe_value)
            self._persist_state_locked()
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


def _integer_setting(
    config: dict,
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = config.get(name, default)
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise ModuleLifecycleError(f"GPIO {name} configuration is invalid")
    return value


def gpio_runtime_handler(gpio: DigitalGpioDriver, event_sink=lambda _event: None):
    def activate(
        manifest: ModuleManifestV2,
        data_dir: Path,
    ) -> dict[str, DigitalGpioCapabilityService]:
        config = manifest.configuration_defaults
        inputs = config.get("inputs", [])
        outputs = config.get("outputs", {})
        rules = config.get("rules", [])
        if not isinstance(inputs, list) or not all(isinstance(item, str) for item in inputs):
            raise ModuleLifecycleError("GPIO inputs configuration is invalid")
        if not isinstance(outputs, dict) or not all(
            isinstance(key, str) and isinstance(value, bool)
            for key, value in outputs.items()
        ):
            raise ModuleLifecycleError("GPIO outputs configuration is invalid")
        if not isinstance(rules, list):
            raise ModuleLifecycleError("GPIO rules configuration is invalid")

        pulse_min_ms = _integer_setting(
            config, "pulse_min_ms", 50, minimum=1, maximum=60_000
        )
        pulse_max_ms = _integer_setting(
            config, "pulse_max_ms", 10_000, minimum=1, maximum=60_000
        )
        pulse_cooldown_ms = _integer_setting(
            config, "pulse_cooldown_ms", 0, minimum=0, maximum=60_000
        )
        if pulse_min_ms > pulse_max_ms:
            raise ModuleLifecycleError("GPIO pulse duration limits are invalid")

        validated_rules: list[dict] = []
        try:
            for capability_id in inputs:
                gpio.input(capability_id).read()
            for capability_id, value in outputs.items():
                gpio.output(capability_id).write(value)
            for rule in rules:
                if not isinstance(rule, dict) or not all(
                    key in rule for key in ("input", "output", "when", "set")
                ):
                    raise ModuleLifecycleError("GPIO rule is invalid")
                input_id, output_id = rule["input"], rule["output"]
                if (
                    not isinstance(input_id, str)
                    or not isinstance(output_id, str)
                    or not isinstance(rule["when"], bool)
                    or not isinstance(rule["set"], bool)
                ):
                    raise ModuleLifecycleError("GPIO rule is invalid")
                gpio.input(input_id).read()
                gpio.output(output_id).read()
                validated_rules.append(rule)
        except KeyError as exc:
            raise ModuleLifecycleError("GPIO capability is unavailable") from exc

        service = DigitalGpioCapabilityService(
            gpio=gpio,
            inputs=inputs,
            outputs=list(outputs),
            output_safe_states=dict(outputs),
            data_dir=data_dir,
            event_sink=event_sink,
            pulse_min_ms=pulse_min_ms,
            pulse_max_ms=pulse_max_ms,
            pulse_cooldown_ms=pulse_cooldown_ms,
        )
        try:
            with service._lock:
                service._persist_state_locked()
            for rule in validated_rules:
                def on_input(
                    event,
                    expected=rule["when"],
                    target=rule["output"],
                    target_value=rule["set"],
                ):
                    if event.value == expected:
                        service.invoke(
                            "set_output",
                            {"channel": target, "value": target_value},
                        )

                service.unsubscribers.append(
                    gpio.input(rule["input"]).subscribe(on_input)
                )
            for input_id in inputs:
                service.unsubscribers.append(
                    gpio.input(input_id).subscribe(
                        lambda event: event_sink(
                            {
                                "event_type": "gpio.input.changed",
                                "payload": {
                                    "capability_id": "gpio.digital.input",
                                    "channel": event.capability_id,
                                    "value": event.value,
                                    "sequence": event.sequence,
                                },
                            }
                        )
                    )
                )
        except Exception:
            service.close()
            raise
        return {
            item.registration_id: service
            for item in manifest.registrations
            if item.kind == "capability"
        }

    return activate
