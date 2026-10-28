"""CAP13 declaration-only query contracts; never grants or dispatches a call.

Contract identity/version belongs to the application interface, independently of
Core, SDK and provider package versions. Exact matching only; no inferred schema
compatibility, service discovery, credentials or transport are supplied here.
"""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from three_mm_protocol.capability_contracts import ContractVersion, validate_schema
from three_mm_protocol.node_security import validate_node_json

Identifier = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_]{0,95}$')]
ContractId = Annotated[str, Field(
    pattern=r'^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$', max_length=160)]


class CompositionModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


class ApplicationQueryContractV1(CompositionModel):
    contract_id: ContractId
    contract_version: ContractVersion
    kind: Literal['query'] = 'query'
    input_schema: dict
    output_schema: dict
    timeout_seconds: int = Field(default=5, ge=1, le=5)
    max_response_bytes: int = Field(default=16 * 1024, ge=1, le=16 * 1024)

    @model_validator(mode='after')
    def bounded_query(self):
        for schema in (self.input_schema, self.output_schema):
            validate_node_json(schema, max_bytes=8192)
            validate_schema(schema)
            if schema.get('type') != 'object':
                raise ValueError('Application queries require strict object schemas')
        return self

    def digest(self) -> str:
        # Models contain mutable schema dictionaries; revalidate at this boundary.
        current = type(self).model_validate(self.model_dump(mode='python'))
        return hashlib.sha256(b'3mm.application-query-contract.v1\0'
                              + _canonical(current.model_dump(mode='json'))).hexdigest()


class ApplicationQueryExportV1(CompositionModel):
    export_id: Identifier
    handler_operation_id: Identifier
    contract: ApplicationQueryContractV1


class ApplicationQueryDependencyV1(CompositionModel):
    binding_id: Identifier
    contract: ApplicationQueryContractV1
    provider_instance_config_key: str = Field(pattern=r'^[A-Z][A-Z0-9_]{1,63}$')
    provider_export_config_key: str = Field(pattern=r'^[A-Z][A-Z0-9_]{1,63}$')

    @model_validator(mode='after')
    def separate_selection(self):
        if self.provider_instance_config_key == self.provider_export_config_key:
            raise ValueError('Provider instance and export require separate configuration fields')
        return self


class ApplicationQueryRequestV1(CompositionModel):
    binding_id: Identifier
    arguments: dict

    @model_validator(mode='after')
    def bounded(self):
        validate_node_json(self.arguments, max_bytes=8192)
        return self


class ApplicationQueryCallerV1(CompositionModel):
    """Core-signed machine attribution, never a human delegation or a grant."""
    instance_id: str = Field(pattern=r'^[0-9a-f]{24}$')
    module_id: str = Field(pattern=r'^[a-z0-9]+(?:[.-][a-z0-9]+)+$', max_length=160)
    artifact_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    binding_id: Identifier
    contract_digest: str = Field(pattern=r'^[0-9a-f]{64}$')


class ApplicationQueryResultV1(CompositionModel):
    query_version: Literal[1] = 1
    binding_id: Identifier
    provider_instance_id: str = Field(pattern=r'^[0-9a-f]{24}$')
    contract_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    output: dict

    @field_validator('query_version', mode='before')
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int:
            raise ValueError('Query version requires an integer')
        return value

    @model_validator(mode='after')
    def bounded(self):
        validate_node_json(self.output, max_bytes=16384)
        return self


class ApplicationQueryCompatibilityV1(CompositionModel):
    assessment_version: Literal[1] = 1
    basis: Literal['declarations_only'] = 'declarations_only'
    binding_id: Identifier
    export_id: Identifier
    compatible: bool
    reason: Literal['dependency_not_declared', 'export_not_declared',
                    'same_application', 'contract_id_mismatch',
                    'contract_version_mismatch', 'schema_mismatch', 'limits_mismatch'] | None
    contract_digest: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    permission_approval: Literal['not_evaluated'] = 'not_evaluated'
    instance_binding: Literal['not_evaluated'] = 'not_evaluated'
    runtime_readiness: Literal['not_evaluated'] = 'not_evaluated'
    invocation_supported: Literal[False] = False

    @field_validator('assessment_version', 'invocation_supported', mode='before')
    @classmethod
    def exact_constants(cls, value, info):
        expected = int if info.field_name == 'assessment_version' else bool
        if type(value) is not expected:
            raise ValueError('Assessment constants require exact types')
        return value

    @model_validator(mode='after')
    def explained(self):
        if self.compatible != (self.reason is None):
            raise ValueError('Compatibility requires an explained result')
        if self.compatible and self.contract_digest is None:
            raise ValueError('Compatible declarations require the exact contract digest')
        return self


def assess_application_query(consumer, provider, *, binding_id: str,
                             export_id: str) -> ApplicationQueryCompatibilityV1:
    """Compare two declarations without selecting instances or granting authority.

    These arguments are descriptors, not evidence of installation/code trust or
    permission. The future Core binding boundary must load the exact verified
    packages and obtain separate M20 consent before any invocation is possible.
    """
    from three_mm_protocol.application_extension import ApplicationExtensionV1

    # Validate again rather than trusting model_copy/update or mutated schemas.
    def definition(value):
        if isinstance(value, ApplicationExtensionV1):
            value = value.model_dump(mode='python')
        return ApplicationExtensionV1.model_validate(value)

    consumer, provider = definition(consumer), definition(provider)
    # Validate request IDs even when one side does not publish a declaration.
    request = ApplicationQueryCompatibilityV1(binding_id=binding_id, export_id=export_id,
        compatible=False, reason='dependency_not_declared')
    dependency = next((item for item in consumer.query_dependencies
                       if item.binding_id == request.binding_id), None)
    export = next((item for item in provider.query_exports
                   if item.export_id == request.export_id), None)
    expected = dependency.contract if dependency is not None else None
    offered = export.contract if export is not None else None
    if expected is None:
        reason = 'dependency_not_declared'
    elif offered is None:
        reason = 'export_not_declared'
    elif consumer.module_id == provider.module_id:
        reason = 'same_application'
    elif expected.contract_id != offered.contract_id:
        reason = 'contract_id_mismatch'
    elif expected.contract_version != offered.contract_version:
        reason = 'contract_version_mismatch'
    elif (_canonical([expected.input_schema, expected.output_schema])
          != _canonical([offered.input_schema, offered.output_schema])):
        # Canonical JSON also distinguishes True from 1, unlike Python equality.
        reason = 'schema_mismatch'
    elif (expected.timeout_seconds, expected.max_response_bytes) != (
            offered.timeout_seconds, offered.max_response_bytes):
        reason = 'limits_mismatch'
    else:
        reason = None
    return ApplicationQueryCompatibilityV1(binding_id=request.binding_id,
        export_id=request.export_id, compatible=reason is None, reason=reason,
        contract_digest=expected.digest() if expected is not None else None)
