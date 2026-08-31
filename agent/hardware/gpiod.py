"""Linux character-device GPIO driver backed by the official gpiod bindings."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from agent.hardware.gpio import DigitalInputCallback, DigitalInputEvent


logger = logging.getLogger(__name__)


class GpiodDigitalGpioDriver:
    """Map stable capability IDs to explicit BCM GPIO line offsets.

    Inputs use an internal pull-up and active-low semantics. A closed contact
    between the configured GPIO and GND therefore reads ``True`` without an
    external voltage source.
    """

    def __init__(
        self,
        *,
        chip: str,
        inputs: dict[str, int],
        outputs: dict[str, int] | None = None,
        input_debounce_seconds: float = 0.02,
        gpiod_module: Any | None = None,
    ) -> None:
        if not inputs and not outputs:
            raise ValueError("At least one GPIO input or output mapping is required")
        if input_debounce_seconds < 0:
            raise ValueError("GPIO input debounce cannot be negative")
        if len(set(inputs.values())) != len(inputs):
            raise ValueError("GPIO input lines must be unique")
        output_lines = dict(outputs or {})
        if set(inputs.values()) & set(output_lines.values()):
            raise ValueError("A GPIO line cannot be both an input and an output")
        if gpiod_module is None:
            try:
                import gpiod as gpiod_module
            except ImportError as exc:
                raise RuntimeError("The official gpiod Python package is required") from exc

        self._gpiod = gpiod_module
        self._closed = False
        self._inputs = {
            capability_id: _GpiodInput(
                gpiod_module,
                chip=chip,
                capability_id=capability_id,
                line=line,
                debounce_seconds=input_debounce_seconds,
            )
            for capability_id, line in inputs.items()
        }
        self._outputs = {
            capability_id: _GpiodOutput(
                gpiod_module,
                chip=chip,
                capability_id=capability_id,
                line=line,
            )
            for capability_id, line in output_lines.items()
        }

    def input(self, capability_id: str) -> "_GpiodInput":
        try:
            return self._inputs[capability_id]
        except KeyError as exc:
            raise KeyError(f"Unknown digital input capability: {capability_id}") from exc

    def output(self, capability_id: str) -> "_GpiodOutput":
        try:
            return self._outputs[capability_id]
        except KeyError as exc:
            raise KeyError(f"Unknown digital output capability: {capability_id}") from exc

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for gpio_input in self._inputs.values():
            gpio_input.close()
        for gpio_output in self._outputs.values():
            gpio_output.close()


class _GpiodInput:
    def __init__(
        self,
        gpiod: Any,
        *,
        chip: str,
        capability_id: str,
        line: int,
        debounce_seconds: float,
    ) -> None:
        self.capability_id = capability_id
        self._gpiod = gpiod
        self._line = line
        self._debounce_seconds = debounce_seconds
        self._request = gpiod.request_lines(
            chip,
            consumer=f"3mm-agent:{capability_id}",
            config={
                line: gpiod.LineSettings(
                    direction=gpiod.line.Direction.INPUT,
                    bias=gpiod.line.Bias.PULL_UP,
                    active_low=True,
                    edge_detection=gpiod.line.Edge.BOTH,
                )
            },
        )
        self._callbacks: list[DigitalInputCallback] = []
        self._callback_lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sequence = 0

    def read(self) -> bool:
        with self._request_lock:
            value = self._request.get_value(self._line)
        return value == self._gpiod.line.Value.ACTIVE

    def subscribe(self, callback: DigitalInputCallback) -> Callable[[], None]:
        with self._callback_lock:
            self._callbacks.append(callback)
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._watch_edges,
                    name=f"3mm-gpio-{self._line}",
                    daemon=True,
                )
                self._thread.start()

        def unsubscribe() -> None:
            with self._callback_lock:
                if callback in self._callbacks:
                    self._callbacks.remove(callback)

        return unsubscribe

    def _watch_edges(self) -> None:
        previous = self.read()
        while not self._stop.is_set():
            try:
                edge_ready = self._request.wait_edge_events(timeout=0.2)
            except (OSError, RuntimeError) as exc:
                if not self._stop.is_set():
                    logger.warning("GPIO edge wait failed for line %s: %s", self._line, exc)
                return
            if not edge_ready:
                continue
            with self._request_lock:
                self._request.read_edge_events()
            if self._debounce_seconds:
                debounce_deadline = time.monotonic() + self._debounce_seconds
                while not self._stop.is_set():
                    remaining = debounce_deadline - time.monotonic()
                    if remaining <= 0 or not self._request.wait_edge_events(timeout=remaining):
                        break
                    with self._request_lock:
                        self._request.read_edge_events()
                    debounce_deadline = time.monotonic() + self._debounce_seconds
            with self._request_lock:
                value = self._request.get_value(self._line)
            current = value == self._gpiod.line.Value.ACTIVE
            if current == previous:
                continue
            previous = current
            self._sequence += 1
            event = DigitalInputEvent(self.capability_id, current, self._sequence)
            with self._callback_lock:
                callbacks = tuple(self._callbacks)
            for callback in callbacks:
                try:
                    callback(event)
                except Exception:
                    logger.exception(
                        "GPIO input callback failed for capability %s",
                        self.capability_id,
                    )

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        self._request.release()


class _GpiodOutput:
    def __init__(self, gpiod: Any, *, chip: str, capability_id: str, line: int) -> None:
        self.capability_id = capability_id
        self._gpiod = gpiod
        self._line = line
        self._lock = threading.Lock()
        self._request = gpiod.request_lines(
            chip,
            consumer=f"3mm-agent:{capability_id}",
            config={
                line: gpiod.LineSettings(
                    direction=gpiod.line.Direction.OUTPUT,
                    output_value=gpiod.line.Value.INACTIVE,
                )
            },
        )

    def read(self) -> bool:
        with self._lock:
            value = self._request.get_value(self._line)
        return value == self._gpiod.line.Value.ACTIVE

    def write(self, value: bool) -> None:
        line_value = (
            self._gpiod.line.Value.ACTIVE
            if value
            else self._gpiod.line.Value.INACTIVE
        )
        with self._lock:
            self._request.set_value(self._line, line_value)

    def close(self) -> None:
        self._request.release()
