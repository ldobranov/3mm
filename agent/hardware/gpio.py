"""Portable digital GPIO capability contracts and deterministic mock driver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass(frozen=True, slots=True)
class DigitalInputEvent:
    capability_id: str
    value: bool
    sequence: int


DigitalInputCallback = Callable[[DigitalInputEvent], None]


class DigitalInput(Protocol):
    capability_id: str

    def read(self) -> bool: ...
    def subscribe(self, callback: DigitalInputCallback) -> Callable[[], None]: ...


class DigitalOutput(Protocol):
    capability_id: str

    def read(self) -> bool: ...
    def write(self, value: bool) -> None: ...


class DigitalGpioDriver(Protocol):
    def input(self, capability_id: str) -> DigitalInput: ...
    def output(self, capability_id: str) -> DigitalOutput: ...
    def close(self) -> None: ...


class MockDigitalGpioDriver:
    """In-memory GPIO with explicit, reproducible input transitions.

    Inputs may change only via ``set_input``. Outputs never feed back into
    inputs, making module and automation tests deterministic.
    """

    def __init__(self, *, inputs: dict[str, bool] | None = None, outputs: dict[str, bool] | None = None) -> None:
        self._inputs = dict(inputs or {"gpio.input.1": False})
        self._outputs = dict(outputs or {"gpio.output.1": False})
        self._callbacks: dict[str, list[DigitalInputCallback]] = {name: [] for name in self._inputs}
        self._sequence = 0

    def input(self, capability_id: str) -> "_MockInput":
        if capability_id not in self._inputs:
            raise KeyError(f"Unknown digital input capability: {capability_id}")
        return _MockInput(self, capability_id)

    def output(self, capability_id: str) -> "_MockOutput":
        if capability_id not in self._outputs:
            raise KeyError(f"Unknown digital output capability: {capability_id}")
        return _MockOutput(self, capability_id)

    def set_input(self, capability_id: str, value: bool) -> DigitalInputEvent | None:
        if capability_id not in self._inputs:
            raise KeyError(f"Unknown digital input capability: {capability_id}")
        normalized = bool(value)
        if self._inputs[capability_id] == normalized:
            return None
        self._inputs[capability_id] = normalized
        self._sequence += 1
        event = DigitalInputEvent(capability_id, normalized, self._sequence)
        for callback in tuple(self._callbacks[capability_id]):
            callback(event)
        return event

    def _subscribe(self, capability_id: str, callback: DigitalInputCallback) -> Callable[[], None]:
        callbacks = self._callbacks[capability_id]
        callbacks.append(callback)
        def unsubscribe() -> None:
            if callback in callbacks:
                callbacks.remove(callback)
        return unsubscribe

    def close(self) -> None:
        for callbacks in self._callbacks.values():
            callbacks.clear()


@dataclass(frozen=True, slots=True)
class _MockInput:
    driver: MockDigitalGpioDriver
    capability_id: str

    def read(self) -> bool:
        return self.driver._inputs[self.capability_id]

    def subscribe(self, callback: DigitalInputCallback) -> Callable[[], None]:
        return self.driver._subscribe(self.capability_id, callback)


@dataclass(frozen=True, slots=True)
class _MockOutput:
    driver: MockDigitalGpioDriver
    capability_id: str

    def read(self) -> bool:
        return self.driver._outputs[self.capability_id]

    def write(self, value: bool) -> None:
        self.driver._outputs[self.capability_id] = bool(value)
