"""Adapter-confirmed passage, distinct from a scan, raw GPIO edge or pulse."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PassagePayloadV1(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal[1] = 1
    capability_id: Literal['access.passage.v1'] = 'access.passage.v1'
    binding_id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,95}$')
    direction: Literal['forward', 'reverse']
    command_id: str = Field(pattern=r'^cmd_[0-9a-f]{32}$')
    generation: str = Field(pattern=r'^[0-9a-f]{32}$')
    sensor_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$')
    device_health: Literal['ok', 'degraded']


class PassageEventV1(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    event_id: str = Field(pattern=r'^evt_[0-9a-f]{32}$')
    device_id: str = Field(pattern=r'^dev_[0-9a-f]{32}$')
    event_type: Literal['access.passage.v1'] = 'access.passage.v1'
    occurred_at: datetime
    payload: PassagePayloadV1

    @field_validator('occurred_at')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError('Passage time requires a timezone')
        return value
