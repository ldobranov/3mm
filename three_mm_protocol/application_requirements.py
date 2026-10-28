"""Shared transport requirements and advisory platform/command observations.

Support assessment alone never grants resource authority or an execution lease,
and never asserts executor readiness or human permission.
"""
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from three_mm_protocol.application_command_discovery import BindingId, CommandDiscoveryV1
from three_mm_protocol.platform_transport import PlatformDiscoveryV1

Identifier = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_]{0,95}$')]
Operation = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$', max_length=128)]


class RequirementModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)


class ApplicationRequirementV1(RequirementModel):
    requirement_id: Identifier
    required: bool = True
    transport_contract_version: int = Field(default=1, ge=1, le=65535)
    operations: tuple[Operation, ...] = Field(min_length=1, max_length=16)
    binding_id: BindingId | None = None

    @field_validator('operations', mode='before')
    @classmethod
    def json_array(cls, value):
        # Package parsing checks duplicate keys before model validation and thus
        # supplies decoded JSON arrays. Preserve strict scalar/item validation.
        return tuple(value) if type(value) is list else value

    @model_validator(mode='after')
    def explicit_need(self):
        if len(set(self.operations)) != len(self.operations):
            raise ValueError('Requirement operations must be unique')
        if self.binding_id is not None and 'command.discover' not in self.operations:
            raise ValueError('A resource requirement needs command.discover')
        return self


class ApplicationPlatformRequirementV1(ApplicationRequirementV1):
    """Package dependency on Core transport support, not optional resource authority."""
    binding_id: None = None


class ApplicationRequirementsRequestV1(RequirementModel):
    requirements: tuple[ApplicationRequirementV1, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode='after')
    def unique_requirements(self):
        if len({item.requirement_id for item in self.requirements}) != len(self.requirements):
            raise ValueError('Requirement identifiers must be unique')
        return self


class ApplicationRequirementSupportV1(RequirementModel):
    requirement: ApplicationRequirementV1
    supported: bool
    missing_operations: tuple[Operation, ...] = Field(max_length=16)
    reason: Literal['transport_contract_mismatch', 'operations_missing'] | None


class ApplicationPlatformRequirementsV1(RequirementModel):
    assessment_version: Literal[1] = 1
    basis: Literal['core_transport_contract'] = 'core_transport_contract'
    transport_contract_version: int = Field(ge=1, le=65535)
    operations: tuple[Operation, ...] = Field(max_length=64)
    status: Literal['satisfied', 'degraded', 'blocked']
    requirements: tuple[ApplicationRequirementSupportV1, ...] = Field(max_length=16)
    permission_approval: Literal['not_evaluated'] = 'not_evaluated'
    resource_bindings: Literal['not_evaluated'] = 'not_evaluated'
    runtime_readiness: Literal['not_evaluated'] = 'not_evaluated'

    @model_validator(mode='after')
    def explained_assessment(self):
        if len(set(self.operations)) != len(self.operations):
            raise ValueError('Observed operations must be unique')
        if self.requirements:
            ApplicationRequirementsRequestV1(requirements=tuple(item.requirement for item in self.requirements))
        status = 'satisfied'
        for item in self.requirements:
            missing = tuple(op for op in item.requirement.operations if op not in self.operations)
            reason = ('transport_contract_mismatch' if item.requirement.transport_contract_version != self.transport_contract_version
                      else 'operations_missing' if missing else None)
            if item.missing_operations != missing or item.reason != reason or item.supported != (reason is None):
                raise ValueError('Support must follow the exact observed contract')
            if not item.supported:
                if item.requirement.required: status = 'blocked'
                elif status == 'satisfied': status = 'degraded'
        if self.status != status:
            raise ValueError('Assessment must distinguish required and optional needs')
        return self


def assess_platform_requirements(requirements, *, transport_contract_version, operations):
    """One pure support rule shared by package preflight and SDK discovery."""
    operations = tuple(sorted(operations))
    results = []
    for requirement in requirements:
        missing = tuple(op for op in requirement.operations if op not in operations)
        reason = ('transport_contract_mismatch' if requirement.transport_contract_version != transport_contract_version
                  else 'operations_missing' if missing else None)
        results.append(ApplicationRequirementSupportV1(requirement=requirement, supported=reason is None,
            missing_operations=missing, reason=reason))
    status = ('blocked' if any(not item.supported and item.requirement.required for item in results)
              else 'degraded' if any(not item.supported for item in results) else 'satisfied')
    return ApplicationPlatformRequirementsV1(transport_contract_version=transport_contract_version,
        operations=operations, status=status, requirements=tuple(results))


class ApplicationRequirementObservationV1(RequirementModel):
    requirement: ApplicationRequirementV1
    supported: bool
    missing_operations: tuple[Operation, ...] = Field(max_length=16)
    met: bool
    reason: Literal['transport_contract_mismatch', 'operations_missing',
        'scoped_authority_required', 'observation_unavailable', 'access_required',
        'binding_unavailable', 'resource_unavailable', 'resource_unknown'] | None
    command: CommandDiscoveryV1 | None = None

    @model_validator(mode='after')
    def correlated_observation(self):
        if self.met != (self.reason is None) or self.met and not self.supported:
            raise ValueError('A met requirement needs supported, explained evidence')
        if self.command is not None:
            if (self.command.binding_id != self.requirement.binding_id
                    or self.command.access == 'not_evaluated' or not self.supported):
                raise ValueError('Only the requested scoped command may be observed')
        if self.met and self.requirement.binding_id is not None:
            if self.command is None or self.command.access != 'granted':
                raise ValueError('A resource requirement needs its current grant')
            candidate = self.command.candidates[0]
            if not candidate.compatible or not candidate.selectable or candidate.readiness != 'ready':
                raise ValueError('A resource requirement needs compatible, ready evidence')
        return self


class ApplicationRequirementsV1(RequirementModel):
    discovery_version: Literal[1] = 1
    platform: PlatformDiscoveryV1
    observed_at: AwareDatetime
    status: Literal['satisfied', 'degraded', 'blocked']
    requirements: tuple[ApplicationRequirementObservationV1, ...] = Field(min_length=1, max_length=16)
    admission_required: Literal[True] = True
    automatic_selection: Literal[False] = False
    automatic_retry: Literal[False] = False

    @field_validator('discovery_version', mode='before')
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError('Discovery version must be an integer')
        return value

    @model_validator(mode='after')
    def explained_status(self):
        ApplicationRequirementsRequestV1(requirements=tuple(item.requirement for item in self.requirements))
        expected = 'satisfied'
        for item in self.requirements:
            missing = tuple(op for op in item.requirement.operations if op not in self.platform.operations)
            supported = not missing and item.requirement.transport_contract_version == self.platform.contract_version
            if item.missing_operations != missing or item.supported != supported:
                raise ValueError('Support must follow the observed transport contract')
            if item.met and self.platform.authority_mode != 'enforced':
                raise ValueError('Compatibility is not scoped resource authority')
            if not item.met:
                if item.requirement.required:
                    expected = 'blocked'
                elif expected == 'satisfied':
                    expected = 'degraded'
        if self.status != expected:
            raise ValueError('Summary must account for required and optional needs')
        return self
