"""Agent-owned, revision-checked configuration for one active-high output.

Only an explicit short-lived command changes hardware. Reports and reconnects
never apply configuration. Existing environment mappings remain the fallback.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent.config import AgentSettings
from agent.hardware import create_gpio_driver, HardwareProfile
from agent.module_runtime import ModuleLifecycleError
from agent.modules.gpio import gpio_runtime_handler
from agent.physical_command_journal import PhysicalCommandFailure

CHANNEL = "gpio.output.1"
# Conservative 40-pin Pi choices: exclude ID EEPROM, I2C, SPI and serial pins.
BCM_HEADER_PINS = {17: 11, 18: 12, 22: 15, 23: 16, 24: 18, 25: 22, 27: 13}


class OutputConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal[1] = 1
    driver: Literal["mock", "gpiod"]
    bcm_pin: int

    def checked(self):
        if self.bcm_pin not in BCM_HEADER_PINS:
            raise ValueError("GPIO pin is not in the supported safe selection")
        return self


class ConfigureOutputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    expected_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed_safe: Literal[True]
    configuration: OutputConfiguration


class GpioConfigurationManager:
    def __init__(self, settings: AgentSettings, *, model: str | None,
                 driver_factory=create_gpio_driver):
        self.settings = settings
        self.path = settings.data_dir / "gpio-configuration.json"
        self._factory = driver_factory
        self._lock = threading.RLock()
        self._service = None
        self._fault: str | None = None
        self._managed: OutputConfiguration | None = None
        self._native_supported = settings.hardware_profile is HardwareProfile.NATIVE and bool(
            model and (model.startswith("Raspberry Pi Zero W Rev")
                       or model.startswith("Raspberry Pi 3 Model B Plus Rev")))
        if self.path.exists():
            try:
                self._managed = OutputConfiguration.model_validate_json(
                    self.path.read_text(encoding="utf-8")).checked()
                if self._managed.driver == "gpiod" and not self._native_supported:
                    raise ValueError("Managed GPIO configuration belongs to an unsupported board")
            except (OSError, ValidationError, ValueError) as exc:
                raise RuntimeError("Cannot load managed GPIO configuration") from exc
        self.driver = self._create(self._configuration())

    def _configuration(self, managed=None) -> dict:
        value = managed or self._managed
        if value:
            return {"driver": value.driver, "chip": "/dev/gpiochip0", "inputs": {},
                    "outputs": {CHANNEL: value.bcm_pin}}
        return {"driver": self.settings.gpio_driver, "chip": self.settings.gpio_chip,
                "inputs": dict(self.settings.gpio_inputs or {}),
                "outputs": dict(self.settings.gpio_outputs or {})}

    @staticmethod
    def _revision(config: dict) -> str:
        return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def _output_channels(config: dict):
        # The isolated mock exposes this default even without an env mapping.
        return [CHANNEL] if config["driver"] == "mock" else config["outputs"]

    def _create(self, config: dict):
        driver = self._factory(self.settings.hardware_profile, driver_name=config["driver"],
                               chip=config["chip"], inputs=config["inputs"], outputs=config["outputs"])
        try:
            for channel in self._output_channels(config):
                driver.output(channel).write(False)
                if driver.output(channel).read() is not False:
                    raise RuntimeError("GPIO inactive state readback failed")
        except Exception:
            driver.close()
            raise
        return driver

    def describe(self, runtime) -> dict:
        with self._lock:
            config = self._configuration()
            simple = not config["inputs"] and set(config["outputs"]) <= {CHANNEL}
            compatible = simple and config["chip"] == "/dev/gpiochip0"
            return {"schema_version": 1, "revision": self._revision(config),
                    "source": "managed" if self._managed else "environment",
                    **config, "configurable": compatible and not self._fault,
                    "native_supported": self._native_supported,
                    "allowed_pins": [{"bcm_pin": bcm, "physical_pin": physical}
                                     for bcm, physical in BCM_HEADER_PINS.items()],
                    "blocking_modules": runtime.enabled_hardware_modules("hardware.gpio"),
                    "error": self._fault}

    def handler(self, event_sink):
        def activate(manifest, data_dir):
            with self._lock:
                if self.driver is None:
                    raise ModuleLifecycleError("GPIO configuration requires operator recovery")
                if self._managed:
                    config = manifest.configuration_defaults
                    if (config.get("inputs", []) != [] or config.get("rules", []) != []
                            or set(config.get("outputs", {})) != {CHANNEL}
                            or config["outputs"][CHANNEL] is not False):
                        raise ModuleLifecycleError("Managed GPIO requires one output with inactive default and no input rules")
                    if self._service is not None and not self._service._closed:
                        raise ModuleLifecycleError("Disable the active GPIO module before activation")
                services = gpio_runtime_handler(self.driver, event_sink)(manifest, data_dir)
                if services:
                    self._service = next(iter(services.values()))
                return services
        return activate

    def apply(self, payload: dict, runtime) -> dict:
        try:
            if payload.get("confirmed_safe") is not True:
                raise ValueError("Explicit safety confirmation is required")
            request = ConfigureOutputRequest.model_validate(payload)
            target = request.configuration.checked()
        except (ValidationError, ValueError) as exc:
            raise PhysicalCommandFailure("not_executed", "Invalid GPIO configuration request") from exc
        with self._lock:
            report = self.describe(runtime)
            if request.expected_revision != report["revision"]:
                raise PhysicalCommandFailure("not_executed", "GPIO configuration revision changed; refresh first")
            if (not report["configurable"] or report["blocking_modules"]
                    or (self._service is not None and not self._service._closed)):
                raise PhysicalCommandFailure("not_executed", "Disable all GPIO modules; only one-output configurations are supported")
            if target.driver == "gpiod" and not self._native_supported:
                raise PhysicalCommandFailure("not_executed", "Native GPIO configuration is not supported on this board")
            previous_config = self._configuration()
            previous_managed = self._managed
            candidate = None
            try:
                for channel in self._output_channels(previous_config):
                    self.driver.output(channel).write(False)
                self.driver.close()
                self.driver = None
                candidate = self._create(self._configuration(target))
                # Commit only after inactive readback. On a crash before this
                # atomic replacement, startup reloads the last valid mapping.
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix(".tmp")
                with temporary.open("w", encoding="utf-8") as saved:
                    saved.write(target.model_dump_json() + "\n")
                    saved.flush()
                    os.fsync(saved.fileno())
                os.chmod(temporary, 0o600)
                os.replace(temporary, self.path)
                self._managed = target
                self.driver = candidate
                self._service = None
            except Exception as exc:
                if candidate is not None:
                    try:
                        candidate.close()
                    except Exception:
                        pass
                self._managed = previous_managed
                try:
                    self.driver = self._create(previous_config)
                except Exception:
                    self.driver = None
                    self._fault = "GPIO rollback failed; hardware control is unavailable"
                    raise PhysicalCommandFailure("unknown", self._fault) from exc
                raise PhysicalCommandFailure("rolled_back", f"GPIO configuration failed ({type(exc).__name__}); previous mapping restored") from exc
            return {"gpio_configuration": self.describe(runtime)}

    def close(self):
        with self._lock:
            if self.driver is not None:
                try:
                    # Legacy modules may intentionally use a HIGH safe state.
                    # Preserve their shutdown behavior until managed active-high
                    # mode is explicitly approved through configuration.
                    if self._managed:
                        for channel in self._output_channels(self._configuration()):
                            self.driver.output(channel).write(False)
                finally:
                    self.driver.close()
