"""C14 discovery and runtime availability; neither grants configuration authority."""

import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator
from three_mm_protocol.models import ProtocolModel
from three_mm_protocol.device_capabilities import ProviderId, ProviderType, Revision
from three_mm_protocol.node_security import bounded_node_message

AVAILABILITY_FEATURE = "capability_availability.v1"
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def declaration_digest(provider_type, provider_id, provider_version, capabilities):
    """Pin the reported health to a complete provider declaration, not inventory."""
    value = {
        "provider_type": provider_type,
        "provider_id": provider_id,
        "provider_version": provider_version,
        "capabilities": sorted(capabilities, key=lambda item: item["capability_id"]),
    }
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


class CapabilityConfigurationV1(ProtocolModel):
    expected_revision: Revision
    capability_ids: tuple[ProviderId, ...] = Field(max_length=64)

    @model_validator(mode="after")
    def unique_ids(self):
        if len(set(self.capability_ids)) != len(self.capability_ids):
            raise ValueError("Duplicate configured capability")
        return self


class CapabilityHealthV1(ProtocolModel):
    capability_id: ProviderId
    healthy: StrictBool
    reason: str | None = Field(default=None, max_length=120, pattern=r"^[a-z0-9_.-]+$")


class CapabilityAvailabilityReportV1(ProtocolModel):
    schema_version: Literal[1] = 1
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    provider_type: ProviderType
    provider_id: ProviderId
    provider_version: str = Field(min_length=1, max_length=64)
    declaration_digest: Digest
    observed_at: datetime
    valid_for_seconds: Annotated[StrictInt, Field(ge=5, le=300)] = 90
    capabilities: tuple[CapabilityHealthV1, ...] = Field(max_length=64)

    @field_validator("observed_at")
    @classmethod
    def aware_time(cls, value):
        if value.utcoffset() is None:
            raise ValueError("Availability time requires a timezone")
        return value

    @model_validator(mode="after")
    def bounded_unique(self):
        ids = [item.capability_id for item in self.capabilities]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate health entry")
        return bounded_node_message(self)


class CapabilityDiscoveryV3(ProtocolModel):
    capability_id: str
    provider_type: str | None = None
    provider_id: str | None = None
    provider_version: str | None = None
    metadata: dict = Field(default_factory=dict)
    contract_version: str | None = None
    contract: dict | None = None
    supported: bool
    registered: bool
    available: bool | None
    unavailable_reason: str | None
    declaration_digest: str | None = None
