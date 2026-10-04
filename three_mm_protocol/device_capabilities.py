"""Provider-neutral declarations over device protocol 1.0; not user permissions."""

import json
import math
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
    model_serializer,
)

from three_mm_protocol.models import ProtocolModel
from three_mm_protocol.capability_contracts import CapabilityContractV1, registration_contract

ProviderType = Annotated[
    str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_.-]*$")
]
ProviderId = Annotated[
    str, Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
]
Revision = Annotated[StrictInt, Field(ge=0, le=2_147_483_646)]


class CapabilityAdvertisementV1(ProtocolModel):
    capability_id: ProviderId
    contract: CapabilityContractV1 | None = None
    metadata: dict[str, StrictStr | StrictBool | StrictInt | StrictFloat] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def bounded_metadata(self):
        registration_contract(self.capability_id, self.contract)
        if len(self.metadata) > 32:
            raise ValueError("Capability metadata has too many fields")
        for key, value in self.metadata.items():
            if not key or len(key) > 96:
                raise ValueError("Capability metadata key is invalid")
            if isinstance(value, str) and len(value) > 512:
                raise ValueError("Capability metadata value is too long")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Capability metadata must be finite")
        if len(json.dumps(self.metadata, ensure_ascii=False).encode()) > 8192:
            raise ValueError("Capability metadata is too large")
        return self

    @model_serializer(mode="wrap")
    def wire(self, handler):
        data = handler(self)
        if self.contract is None:
            data.pop("contract", None)
        return data


class CapabilityProviderReportV1(ProtocolModel):
    schema_version: Literal[1]
    protocol_version: Literal["1.0"] = "1.0"
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    provider_type: ProviderType
    provider_id: ProviderId
    provider_version: str = Field(min_length=1, max_length=64)
    expected_revision: Revision
    capabilities: tuple[CapabilityAdvertisementV1, ...] = Field(max_length=64)

    @model_validator(mode="after")
    def unique_bounded_declarations(self):
        if self.provider_type == "agent_module":
            raise ValueError(
                "Agent module declarations are managed through module installations"
            )
        ids = [item.capability_id for item in self.capabilities]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate capability declaration")
        if len(self.model_dump_json().encode()) > 65536:
            raise ValueError("Capability provider report is too large")
        return self


class CapabilityProviderSnapshotV1(ProtocolModel):
    schema_version: Literal[1] = 1
    device_id: str
    provider_type: ProviderType
    provider_id: ProviderId
    provider_version: str
    revision: Revision
    enabled: bool
    capabilities: tuple[CapabilityAdvertisementV1, ...]
    reported_at: datetime


class CapabilityProviderReportV2(CapabilityProviderReportV1):
    """Supported offers only. Core-owned configuration selects registrations."""
    schema_version: Literal[2]


class CapabilityProviderSnapshotV2(CapabilityProviderSnapshotV1):
    schema_version: Literal[2] = 2
    configured_capability_ids: tuple[ProviderId, ...]


class CapabilityProviderControlV1(ProtocolModel):
    expected_revision: Revision
    enabled: StrictBool


class CapabilityRegistrationV2(ProtocolModel):
    capability_id: str
    provider_type: str
    provider_id: str
    provider_version: str
    metadata: dict = Field(default_factory=dict)
    status: Literal["active"] = "active"
    contract_version: str | None = None
    contract: CapabilityContractV1 | None = None

    @model_serializer(mode="wrap")
    def wire(self, handler):
        data = handler(self)
        if self.contract is None:
            data.pop("contract", None)
            data.pop("contract_version", None)
        return data
