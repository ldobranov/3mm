"""Bounded own-data schema; routing and current permissions belong to Core."""
from datetime import date, datetime
import json, math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from three_mm_protocol.ui_metadata import IDENTIFIER_PATTERN, LocalizedTextV1

class CrudError(RuntimeError):
    """Application request refusal, distinct from SDK receipt validation errors."""

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

class CrudField(Strict):
    field_id: str = Field(pattern=IDENTIFIER_PATTERN, max_length=32)
    label: LocalizedTextV1
    kind: Literal['text','multiline','integer','number','boolean','date','datetime']
    required: bool = False
    read_only: bool = False

class CrudEntity(Strict):
    entity_id: str = Field(pattern=IDENTIFIER_PATTERN, max_length=32)
    label: LocalizedTextV1
    fields: tuple[CrudField,...] = Field(min_length=1,max_length=32)

    @model_validator(mode='after')
    def unique_fields(self):
        if len({f.field_id for f in self.fields})!=len(self.fields):raise ValueError('Duplicate field')
        return self

    def validate_data(self, data, *, partial=False, restored=False):
        if not isinstance(data,dict):raise CrudError('Record data must be an object')
        fields={f.field_id:f for f in self.fields}
        if set(data)-set(fields):raise CrudError('Unknown record field')
        if not partial and any(f.required and (restored or not f.read_only) and f.field_id not in data for f in self.fields):
            raise CrudError('Required record field is missing')
        for name,value in data.items():
            field=fields[name]
            if field.read_only and not restored:raise CrudError('Read-only record field')
            if value is None:
                if field.required:raise CrudError('Required record field is null')
                continue
            valid=False
            if field.kind in {'text','multiline'}:valid=isinstance(value,str) and len(value)<=1024
            elif field.kind=='integer':valid=type(value) is int and abs(value)<=9007199254740991
            elif field.kind=='number':valid=type(value) in (int,float) and math.isfinite(value) and abs(value)<=9007199254740991
            elif field.kind=='boolean':valid=type(value) is bool
            elif field.kind in {'date','datetime'} and isinstance(value,str):
                try:
                    (date.fromisoformat if field.kind=='date' else datetime.fromisoformat)(value)
                    valid=True
                except ValueError:pass
            if not valid:raise CrudError('Invalid record value')
        if len(json.dumps(data,ensure_ascii=False,allow_nan=False).encode())>4096:raise CrudError('Record exceeds its byte limit')
        return dict(data)

class CrudDefinition(Strict):
    crud_version: Literal[1]
    name: LocalizedTextV1
    entities: tuple[CrudEntity,...] = Field(min_length=1,max_length=16)

    @model_validator(mode='after')
    def unique_entities(self):
        if len({e.entity_id for e in self.entities})!=len(self.entities):raise ValueError('Duplicate entity')
        return self
