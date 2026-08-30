"""Versioned opaque identifier scan event shared by Agent and Core."""

from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator


ScanMetadataValue: TypeAlias = str | int | float | bool


class StrictIdentifierModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IdentifierScanPayloadV1(StrictIdentifierModel):
    schema_version: Literal[1] = 1
    capability_id: Literal["identifier.scan.v1"] = "identifier.scan.v1"
    opaque_identifier: str = Field(min_length=1, max_length=512)
    reader_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
    adapter_kind: Literal["keyboard", "serial", "rfid_nfc", "mock"]
    sequence: int = Field(ge=1)
    device_health: Literal["ok", "degraded"] = "ok"
    scan_metadata: dict[str, ScanMetadataValue] = Field(
        default_factory=dict,
        max_length=16,
    )

    @field_validator("opaque_identifier")
    @classmethod
    def validate_opaque_identifier(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("opaque identifier contains unsupported whitespace")
        return value

    @field_validator("scan_metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, ScanMetadataValue]):
        if any(not key or len(key) > 64 for key in value):
            raise ValueError("scan metadata keys must be 1-64 characters")
        return value


class IdentifierScanEventV1(StrictIdentifierModel):
    event_id: str = Field(pattern=r"^evt_[0-9a-f]{32}$")
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    event_type: Literal["identifier.scan.v1"] = "identifier.scan.v1"
    payload: IdentifierScanPayloadV1
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_has_timezone(cls, value: datetime):
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        return value
