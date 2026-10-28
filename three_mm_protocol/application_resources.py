"""Installation-scoped, advisory resource observations; never execution authority."""
from typing import Annotated, Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

ResourceScope = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_.:-]{0,191}$')]
Reason = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_]{0,95}$')]


class ResourceModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)


class ResourceDiscoveryRequestV1(ResourceModel):
    scopes: tuple[ResourceScope, ...] = Field(min_length=1, max_length=16)

    @field_validator('scopes', mode='before')
    @classmethod
    def json_array(cls, value):
        return tuple(value) if type(value) is list else value

    @model_validator(mode='after')
    def unique_scopes(self):
        if len(set(self.scopes)) != len(self.scopes): raise ValueError('Resource scopes must be unique')
        return self


class ResourceProviderV1(ResourceModel):
    provider_type: str = Field(min_length=1, max_length=64)
    provider_id: str = Field(min_length=1, max_length=160)
    provider_version: str | None = Field(default=None, max_length=64)
    contract_version: str | None = Field(default=None, max_length=32)


class ResourceObservationV1(ResourceModel):
    scope: ResourceScope
    required: bool = True
    declared: bool | None
    configured: bool | None
    access: Literal['not_evaluated', 'required', 'granted']
    readiness: Literal['not_evaluated', 'unknown', 'unavailable', 'ready']
    reasons: tuple[Reason, ...] = Field(max_length=8)
    provider: ResourceProviderV1 | None = None
    selected_resource_id: str | None = Field(default=None, max_length=160)

    @model_validator(mode='after')
    def access_is_not_readiness(self):
        if self.access != 'granted' and (self.provider is not None or self.selected_resource_id is not None
                or self.configured is not None or self.readiness != 'not_evaluated'):
            raise ValueError('Unapproved discovery cannot reveal resource metadata')
        if self.access == 'granted' and self.declared is not True:
            raise ValueError('Only an exact declared scope can be granted')
        if self.readiness == 'ready' and (self.configured is not True or self.reasons):
            raise ValueError('Ready requires configured, explained evidence')
        if self.readiness in {'unknown', 'unavailable'} and not self.reasons:
            raise ValueError('Unconfirmed readiness needs a reason')
        return self


class ResourceDiscoveryV1(ResourceModel):
    discovery_version: Literal[1] = 1
    instance_id: str = Field(pattern=r'^[0-9a-f]{24}$')
    artifact_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    observed_at: AwareDatetime
    resources: tuple[ResourceObservationV1, ...] = Field(min_length=1, max_length=16)
    admission_required: Literal[True] = True

    @field_validator('discovery_version', mode='before')
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int: raise ValueError('Discovery version must be an integer')
        return value

    @field_validator('admission_required', mode='before')
    @classmethod
    def exact_admission(cls, value):
        if value is not True: raise ValueError('Observation cannot waive execution admission')
        return value

    @model_validator(mode='after')
    def unique_resources(self):
        ResourceDiscoveryRequestV1(scopes=tuple(item.scope for item in self.resources))
        return self
