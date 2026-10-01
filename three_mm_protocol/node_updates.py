"""Versioned, Core-independent handoff for an already prepared Node update."""

import base64
import hashlib
import json
from datetime import UTC
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

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

    @field_validator("created_at", "expires_at")
    @classmethod
    def normalize_deadline(cls, value):
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def bound_handoff(self):
        duration = (self.expires_at - self.created_at).total_seconds()
        if not 0 < duration <= MAX_HANDOFF_SECONDS:
            raise ValueError("Node update handoff must expire within 120 seconds")
        return self


def _canonical_base64(value: str, length: int) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid approval encoding") from exc
    if len(decoded) != length or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError("Invalid approval length or encoding")
    return decoded


class NodeUpdateApprovalKey(BaseModel):
    """Public Hub identity, explicitly pinned by the Node's root administrator."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    algorithm: Literal["ed25519"] = "ed25519"
    key_id: str = Field(pattern=SHA256_PATTERN)
    public_key: str = Field(min_length=44, max_length=44)

    @model_validator(mode="after")
    def check_identity(self):
        if hashlib.sha256(_canonical_base64(self.public_key, 32)).hexdigest() != self.key_id:
            raise ValueError("Hub approval key fingerprint does not match")
        return self


class NodeUpdateAuthorization(BaseModel):
    """Hub-signed approval; the Agent cannot change its identity or deadline."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    key_id: str = Field(pattern=SHA256_PATTERN)
    request: NodeUpdateApplyRequest
    signature: str = Field(min_length=88, max_length=88)

    @field_validator("signature")
    @classmethod
    def check_signature(cls, value):
        _canonical_base64(value, 64)
        return value


class NodeUpdateSupport(BaseModel):
    """Root helper readiness, distinct from Node installation or enrollment."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    signed_apply_supported: Literal[True] = True
    approval_key_id: str | None = Field(default=None, pattern=SHA256_PATTERN)
    trusted_device_id: str | None = Field(default=None, pattern=DEVICE_PATTERN)

    @model_validator(mode="after")
    def check_binding(self):
        if (self.approval_key_id is None) != (self.trusted_device_id is None):
            raise ValueError("Incomplete Node update trust binding")
        return self


def canonical_node_update_authorization(request: NodeUpdateApplyRequest, key_id: str) -> bytes:
    """Stable domain-separated bytes shared by the Hub signer and root verifier."""
    return b"3mm.node-update.apply.v1\n" + json.dumps(
        {"key_id": key_id, "request": request.model_dump(mode="json")},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")


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
