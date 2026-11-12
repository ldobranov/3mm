"""Generic, profile-configured input edges over the existing event-driven driver."""
import secrets
import threading
import time

from agent.hardware.gpio import MockDigitalGpioDriver
from agent.hardware.gpiod import GpiodDigitalGpioDriver
from agent.module_runtime import ModuleLifecycleError
from packages.protocol.gpio_input import (
    GpioInputProfileV1, INPUT_CAPABILITY, INPUT_EVENT, MAX_SEQUENCE, MAX_MONOTONIC_NS,
)


class GpioInputService:
    def __init__(self, profile, driver, event_sink, *, clock=time.monotonic_ns):
        self.profile, self.driver, self.event_sink, self.clock = profile, driver, event_sink, clock
        self.stream_id = secrets.token_hex(16)
        self._lock = threading.RLock()
        self._closed, self._fault = False, False
        self._sequence = {channel: 0 for channel in profile.inputs}
        self._inputs, self._values, self._unsubscribers = {}, {}, []
        try:
            self._inputs = {channel: driver.input(channel) for channel in profile.inputs}
            self._values = {channel: line.read() for channel, line in self._inputs.items()}
            self._unsubscribers = [line.subscribe(self._edge) for line in self._inputs.values()]
        except Exception:
            driver.close()
            raise

    def _edge(self, event):
        with self._lock:
            channel = event.capability_id
            if self._closed or self._fault or channel not in self._inputs or type(event.value) is not bool:
                return
            if self._values[channel] == event.value:
                return
            timestamp = getattr(event, 'monotonic_ns', None)
            if timestamp is None and self.profile.driver == 'mock':
                timestamp = self.clock()
            if type(timestamp) is not int or not 0 <= timestamp <= MAX_MONOTONIC_NS or self._sequence[channel] == MAX_SEQUENCE:
                self._fault = True
                return  # Native edge timestamps must not be guessed from callbacks.
            self._values[channel] = event.value
            self._sequence[channel] += 1
            self.event_sink({'event_type': INPUT_EVENT, 'payload': {
                'capability_id': INPUT_CAPABILITY, 'profile_sha256': self.profile.digest(),
                'channel': channel, 'bcm_pin': self.profile.inputs[channel], 'value': event.value,
                'sequence': self._sequence[channel], 'stream_id': self.stream_id,
                'monotonic_ns': timestamp, 'simulated': self.profile.driver == 'mock'}})

    def is_available(self):
        with self._lock:
            return not self._closed and not self._fault and all(
                bool(getattr(line, 'is_available', lambda: True)()) for line in self._inputs.values())

    def state_for(self, capability_id):
        with self._lock:
            if capability_id != INPUT_CAPABILITY or self._closed:
                return {}
            return {'profile_sha256': self.profile.digest(), 'stream_id': self.stream_id,
                'inputs': {channel: line.read() for channel, line in self._inputs.items()},
                'simulated': self.profile.driver == 'mock'}

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for unsubscribe in self._unsubscribers:
                unsubscribe()
        self.driver.close()  # Joining an edge thread cannot hold its callback lock.


def gpio_input_handler(*, native_allowed=False, model=None, event_sink=lambda _event: None, driver_factory=None):
    def activate(manifest, _data_dir):
        profile = GpioInputProfileV1.model_validate(manifest.configuration_defaults)
        registrations = [item for item in manifest.registrations if item.kind == 'capability']
        if (set(manifest.permissions) != {'hardware.gpio', 'events.publish'} or len(registrations) != 1
                or registrations[0].registration_id != INPUT_CAPABILITY
                or registrations[0].contract != profile.contract()
                or registrations[0].metadata.get('profile_sha256') != profile.digest()
                or registrations[0].metadata.get('simulated') is not (profile.driver == 'mock')):
            raise ModuleLifecycleError('Digital input provider requires its exact profile-bound contract')
        if profile.driver == 'gpiod' and (not native_allowed or not model or not model.startswith(
                ('Raspberry Pi Zero W Rev', 'Raspberry Pi 3 Model B Rev', 'Raspberry Pi 3 Model B Plus Rev'))):
            raise ModuleLifecycleError('Native digital input profile is unsupported on this device')
        if driver_factory:
            driver = driver_factory(profile)
        elif profile.driver == 'mock':
            driver = MockDigitalGpioDriver(inputs={channel: False for channel in profile.inputs})
        else:
            driver = GpiodDigitalGpioDriver(chip='/dev/gpiochip0', inputs=profile.inputs,
                                           input_debounce_seconds=profile.debounce_ms / 1000)
        return {INPUT_CAPABILITY: GpioInputService(profile, driver, event_sink)}
    return activate
