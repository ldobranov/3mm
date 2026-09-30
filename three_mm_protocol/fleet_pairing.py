"""Code-free enrollment into an explicitly selected, trusted Hub."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class NodeEnrollmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    protocol_version: Literal["1.0"] = "1.0"
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    display_name: str = Field(min_length=1, max_length=100)
    request_token: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    credential_id: str = Field(pattern=r"^cred_[0-9a-f]{32}$")
    credential_secret_hash: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)


class NodeEnrollmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    device_id: str
    credential_id: str
    status: Literal["pending_approval", "approved", "expired", "rejected", "revoked"]
