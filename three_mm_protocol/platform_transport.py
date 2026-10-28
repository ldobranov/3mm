"""Current local transport result; discovery never grants rights."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from three_mm_platform_wire import (
    TRANSPORT_VERSION, CONTRACT_VERSION, MAX_MESSAGE_BYTES, MAX_CONNECTIONS,
    READ_TIMEOUT_SECONDS, REQUEST_TIMEOUT_SECONDS, MAX_CLOCK_SKEW_SECONDS,
    MAX_RECENT_REQUESTS, DISCOVERY_ACTION, SCOPED_ACTIONS, COMPATIBILITY_ACTIONS,
    ERROR_REASONS, ENVELOPE_FIELDS, canonical, decode_frame, remaining, read_frame,
)

class PlatformDiscoveryV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    contract_version: Literal[1] = 1
    transport_version: Literal[1] = 1
    sdk_version: Literal["1.3"] = "1.3"
    instance_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    transport_generation: str = Field(pattern=r"^[0-9a-f]{32}$")
    recovery_generation: str = Field(pattern=r"^[0-9a-f]{32}$")
    authority_revision: int = Field(ge=1, le=2**53-1)
    application_incarnation: str = Field(pattern=r"^[0-9a-f]{32}$")
    authority_epoch: str = Field(pattern=r"^[0-9a-f]{32}$")
    authority_mode: Literal["compatibility", "review_required", "enforced"]
    operations: list[str] = Field(max_length=64)
    max_message_bytes: Literal[6291456] = MAX_MESSAGE_BYTES
    max_connections: Literal[16] = MAX_CONNECTIONS
    read_timeout_seconds: Literal[5] = READ_TIMEOUT_SECONDS
    request_timeout_seconds: Literal[35] = REQUEST_TIMEOUT_SECONDS
    admission_cache_ms: Literal[0] = 0
    automatic_retry: Literal[False] = False
    jobs_supported: Literal[False] = False

    @field_validator("contract_version", "transport_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("Contract version must be an integer")
        return value

    @field_validator("operations")
    @classmethod
    def supported_actions(cls, values):
        if len(values) != len(set(values)) or set(values) - (COMPATIBILITY_ACTIONS | SCOPED_ACTIONS):
            raise ValueError("Discovery operations are invalid")
        return values
