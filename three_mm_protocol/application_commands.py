"""Narrow declarative command authority; no caller-selected device or action."""
from typing import Literal
from datetime import UTC, datetime
import math
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


def validate_argument_schema(schema: dict) -> None:
    if set(schema) - {'type', 'properties', 'required', 'additionalProperties'}:
        raise ValueError('Unsupported command schema keyword')
    properties = schema.get('properties')
    if schema.get('type') != 'object' or schema.get('additionalProperties') is not False or not isinstance(properties, dict) or len(properties) > 32:
        raise ValueError('Command arguments require a bounded strict object schema')
    required = schema.get('required', [])
    if not isinstance(required, list) or any(not isinstance(k, str) for k in required) or len(set(required)) != len(required) or set(required) - set(properties):
        raise ValueError('Invalid required command arguments')
    for name, field in properties.items():
        if not isinstance(name, str) or not name or not isinstance(field, dict):
            raise ValueError('Invalid command argument schema')
        if set(field) - {'type', 'enum', 'minimum', 'maximum', 'minLength', 'maxLength'} or field.get('type') not in {'string', 'boolean', 'integer', 'number'}:
            raise ValueError('Only explicit scalar command argument schemas are supported')
        allowed = {'type', 'enum'} | ({'minimum', 'maximum'} if field['type'] in {'integer', 'number'} else {'minLength', 'maxLength'} if field['type'] == 'string' else set())
        if set(field) - allowed:
            raise ValueError('Argument constraint does not apply to its type')
        if field['type'] in {'integer', 'number'}:
            if not all(isinstance(field.get(k), (int, float)) and not isinstance(field[k], bool) and math.isfinite(field[k]) for k in ('minimum', 'maximum')) or field['minimum'] > field['maximum']:
                raise ValueError('Numeric arguments require finite ordered limits')
        if field['type'] == 'string' and (type(field.get('maxLength')) is not int or not 1 <= field['maxLength'] <= 512 or type(field.get('minLength', 0)) is not int or not 0 <= field.get('minLength', 0) <= field['maxLength']):
            raise ValueError('String arguments require a bounded maxLength')
        if 'enum' in field and (not isinstance(field['enum'], list) or not field['enum']):
            raise ValueError('Invalid argument enum')
        for value in field.get('enum', []):
            kind = field['type']
            valid = (
                type(value) is bool if kind == 'boolean' else
                isinstance(value, str) and field.get('minLength', 0) <= len(value) <= field['maxLength'] if kind == 'string' else
                type(value) in ((int,) if kind == 'integer' else (int, float))
                and math.isfinite(value) and field['minimum'] <= value <= field['maximum']
            )
            if not valid:
                raise ValueError('Argument enum violates its declared type or bounds')


class ApplicationCommandBindingV1(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    binding_id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,95}$')
    target_device_config_key: str = Field(pattern=r'^[A-Z][A-Z0-9_]{1,63}$')
    capability_id: str = Field(pattern=r'^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$')
    action: str = Field(pattern=r'^[a-z][a-z0-9_]{0,95}$')
    arguments_schema: dict
    max_ttl_seconds: int = Field(default=10, ge=1, le=10, strict=True)
    sensor_device_config_key: str | None = Field(default=None, pattern=r'^[A-Z][A-Z0-9_]{1,63}$')
    sensor_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$')

    @model_validator(mode='after')
    def validate_binding(self):
        validate_argument_schema(self.arguments_schema)
        if (self.sensor_device_config_key is None) != (self.sensor_id is None):
            raise ValueError('Passage requires both a sensor device binding and sensor identity')
        return self


class ApplicationCommandSubmitV1(BaseModel):
    model_config = ConfigDict(extra='forbid')
    binding_id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,95}$')
    request_id: str = Field(min_length=1, max_length=96)
    arguments: dict = Field(default_factory=dict)
    ttl_seconds: int = Field(default=10, ge=1, le=10, strict=True)
    direction: Literal['forward', 'reverse'] = 'forward'
    not_after: AwareDatetime | None = None

    @field_validator('not_after', mode='before')
    @classmethod
    def deadline_type(cls, value):
        if value is not None and not isinstance(value, (str, datetime)):
            raise ValueError('not_after requires an ISO datetime with timezone')
        return value

    @field_validator('not_after')
    @classmethod
    def utc_deadline(cls, value):
        return value.astimezone(UTC) if value is not None else None


class ApplicationCommandLookupV1(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(min_length=1, max_length=96)
    binding_id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,95}$')
