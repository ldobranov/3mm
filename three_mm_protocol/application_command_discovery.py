"""Read-only command requirements over the existing device capability registry."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

BindingId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")]
DeviceId = Annotated[str, Field(pattern=r"^dev_[0-9a-f]{32}$")]


class CommandDiscoveryRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    binding_id: BindingId


class CommandCandidateV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    device_id: DeviceId
    provider_type: str | None = None
    provider_id: str | None = None
    provider_version: str | None = None
    contract_version: str | None = None
    compatible: bool
    selectable: bool
    blockers: list[str] = Field(max_length=8)
    readiness: Literal["ready", "unavailable", "unknown"]
    readiness_reason: str | None = None

    @model_validator(mode="after")
    def consistent_candidate(self):
        if self.selectable != (self.compatible and not self.blockers):
            raise ValueError("Selection must satisfy every requirement")
        if (self.readiness == "ready") != (self.readiness_reason is None):
            raise ValueError("Readiness requires a consistent explanation")
        return self


class CommandDiscoveryV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    discovery_version: Literal[1] = 1
    binding_id: BindingId
    capability_id: str
    contract_version: str | None
    action: str
    observed_at: AwareDatetime
    access: Literal["not_evaluated", "required", "granted"]
    selected_device_id: DeviceId | None
    candidates: list[CommandCandidateV1] = Field(max_length=32)
    next_after_device_id: DeviceId | None = None

    @field_validator("discovery_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("Discovery version must be an integer")
        return value

    @model_validator(mode="after")
    def scoped_observation(self):
        if len({item.device_id for item in self.candidates}) != len(self.candidates):
            raise ValueError("Duplicate candidate device")
        if self.access == "required" and (self.candidates or self.selected_device_id is not None):
            raise ValueError("Denied discovery must not expose resources")
        if self.access == "granted" and (len(self.candidates) != 1
                or self.candidates[0].device_id != self.selected_device_id):
            raise ValueError("SDK discovery must describe only its granted selection")
        if self.access != "not_evaluated" and self.next_after_device_id is not None:
            raise ValueError("SDK discovery cannot enumerate other resources")
        return self
