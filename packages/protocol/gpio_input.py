"""Profile-bound generic digital inputs; interpretation belongs to consumers."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from packages.protocol.capability_contracts import CapabilityContractV1
from packages.protocol.hardware_profiles import profile_digest

INPUT_CAPABILITY = 'gpio.digital.input'
INPUT_ENTRYPOINT = 'builtin:gpio.input.v1'
INPUT_EVENT = 'gpio.input.changed'
INPUT_FEATURE = 'gpio_input_profiles.v1'
BCM_PINS = {17: 11, 18: 12, 22: 15, 23: 16, 24: 18, 25: 22, 27: 13}
MAX_SEQUENCE = 2_147_483_647
MAX_MONOTONIC_NS = 9_223_372_036_854_775_807


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def event_schema():
    return obj({'capability_id': {'type': 'string', 'maxLength': 160, 'enum': [INPUT_CAPABILITY]},
        'profile_sha256': {'type': 'string', 'minLength': 64, 'maxLength': 64},
        'channel': {'type': 'string', 'minLength': 1, 'maxLength': 64},
        'bcm_pin': {'type': 'integer', 'minimum': 0, 'maximum': 27},
        'value': {'type': 'boolean'},
        'sequence': {'type': 'integer', 'minimum': 1, 'maximum': MAX_SEQUENCE},
        'stream_id': {'type': 'string', 'minLength': 32, 'maxLength': 32},
        'monotonic_ns': {'type': 'integer', 'minimum': 0, 'maximum': MAX_MONOTONIC_NS},
        'simulated': {'type': 'boolean'}})


class GpioInputProfileV1(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    schema_version: Literal[1] = 1
    driver: Literal['mock', 'gpiod'] = 'mock'
    inputs: dict[str, int] = Field(default_factory=lambda: {'gpio.input.1': 17})
    active_low: Literal[True] = True
    pull_up: Literal[True] = True
    debounce_ms: int = Field(default=20, ge=0, le=1000)

    @field_validator('inputs')
    @classmethod
    def checked_inputs(cls, value):
        if not 1 <= len(value) <= len(BCM_PINS):
            raise ValueError('Declare one to seven digital input channels')
        if len(set(value.values())) != len(value):
            raise ValueError('Digital input channels cannot share a GPIO line')
        if any(not re.fullmatch(r'[a-z][a-z0-9_.-]{0,63}', channel) for channel in value):
            raise ValueError('Invalid logical digital input channel')
        if any(pin not in BCM_PINS for pin in value.values()):
            raise ValueError('GPIO pin is reserved or outside the supported 40-pin selection')
        return value

    def digest(self):
        return profile_digest(self.model_dump())

    def contract(self):
        return CapabilityContractV1(capability_id=INPUT_CAPABILITY, contract_version='2.0',
            state_schema=obj({'profile_sha256': {'type': 'string', 'maxLength': 64, 'enum': [self.digest()]},
                'stream_id': {'type': 'string', 'minLength': 32, 'maxLength': 32},
                'inputs': obj({channel: {'type': 'boolean'} for channel in self.inputs}),
                'simulated': {'type': 'boolean', 'enum': [self.driver == 'mock']}}),
            events={INPUT_EVENT: event_schema()})
