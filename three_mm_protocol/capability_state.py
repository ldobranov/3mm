"""Authenticated capability state snapshots shared by Agent and Core."""

from datetime import datetime
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator

from three_mm_protocol.capability_builder import CAPABILITY_ID_PATTERN


CapabilityValue: TypeAlias = str | int | float | bool


class StrictCapabilityStateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CapabilityStateReportV1(StrictCapabilityStateModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    capability_id: str = Field(pattern=CAPABILITY_ID_PATTERN)
    values: dict[str, CapabilityValue] = Field(min_length=1, max_length=256)
    observed_at: datetime

    @field_validator("values")
    @classmethod
    def validate_channel_names(cls, values):
        if any(not key or len(key) > 160 for key in values):
            raise ValueError("capability state channel names must be 1-160 characters")
        return values

    @field_validator("observed_at")
    @classmethod
    def observed_at_has_timezone(cls, value):
        if value.tzinfo is None:
            raise ValueError("observed_at must include a timezone")
        return value


class CapabilityStateSnapshotV1(CapabilityStateReportV1):
    received_at: datetime
