"""Versioned, Core-independent handoff for an already prepared Node update."""

from datetime import UTC
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator

OPERATION_PATTERN = r"^nodeupd_[0-9a-f]{32}$"
RELEASE_PATTERN = r"^v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$"
DEVICE_PATTERN = r"^dev_[0-9a-f]{32}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
MAX_HANDOFF_SECONDS = 120


class NodeUpdatePayload(BaseModel):
    """Administrative queue payload; Agent supplies device and original deadline."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    operation_id: str = Field(pattern=OPERATION_PATTERN)
    release_id: str = Field(pattern=RELEASE_PATTERN, max_length=80)
    archive_sha256: str = Field(pattern=SHA256_PATTERN)
    confirmed_install: StrictBool

    @model_validator(mode="after")
    def require_confirmation(self):
        if self.confirmed_install is not True:
            raise ValueError("Node runtime installation requires explicit confirmation")
        return self

class NodeUpdatePrepareRequest(BaseModel):
    """Metadata for one Node archive already downloaded by the Agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    operation_id: str = Field(pattern=OPERATION_PATTERN)
    device_id: str = Field(pattern=DEVICE_PATTERN)
    release_id: str = Field(pattern=RELEASE_PATTERN, max_length=80)
    archive_sha256: str = Field(pattern=SHA256_PATTERN)
    archive_size_bytes: int = Field(
        gt=0,
        le=512 * 1024 * 1024,
    )

class NodeUpdatePreparedArtifact(BaseModel):
    """Root-owned immutable copy prepared for later explicit installation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    operation_id: str = Field(pattern=OPERATION_PATTERN)
    device_id: str = Field(pattern=DEVICE_PATTERN)
    release_id: str = Field(pattern=RELEASE_PATTERN, max_length=80)
    archive_sha256: str = Field(pattern=SHA256_PATTERN)
    archive_size_bytes: int = Field(gt=0, le=512 * 1024 * 1024)
    prepared_at: AwareDatetime

class NodeUpdateApplyRequest(NodeUpdatePayload):
    device_id: str = Field(pattern=DEVICE_PATTERN)
    created_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def bound_handoff(self):
        duration = (self.expires_at - self.created_at).total_seconds()
        if not 0 < duration <= MAX_HANDOFF_SECONDS:
            raise ValueError("Node update handoff must expire within 120 seconds")
        return self


class NodeUpdateOperation(BaseModel):
    """Durable installation outcome, distinct from command delivery/acceptance."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    operation_id: str = Field(pattern=OPERATION_PATTERN)
    device_id: str = Field(pattern=DEVICE_PATTERN)
    release_id: str = Field(pattern=RELEASE_PATTERN, max_length=80)
    archive_sha256: str = Field(pattern=SHA256_PATTERN)
    status: Literal["accepted", "running", "succeeded", "rolled_back", "failed", "unknown"]
    updated_at: AwareDatetime
    previous_release_id: str | None = Field(default=None, pattern=RELEASE_PATTERN, max_length=80)
    error_code: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,80}$")

    @model_validator(mode="after")
    def normalize_time(self):
        object.__setattr__(self, "updated_at", self.updated_at.astimezone(UTC))
        return self
