"""Public, bounded Runtime update DTOs; privileged state stays in the root helper."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt


class RuntimeModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class RuntimeOperation(RuntimeModel):
    request_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    action: Literal['platform_runtime_prepare', 'platform_runtime_apply', 'platform_runtime_recover']
    state: Literal['queued', 'preparing', 'applying', 'recovering', 'succeeded', 'failed', 'recovery_required']
    reason: Literal['candidate_prepared', 'runtime_recovered', 'runtime_updated',
        'preparation_failed', 'previous_runtime_ready', 'runtime_outcome_unconfirmed', 'worker_interrupted'] | None
    updated_at: StrictInt


class RuntimeCandidate(RuntimeModel):
    candidate_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    build_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    bytes: StrictInt = Field(gt=0, le=2*1024*1024)
    features: dict[str, StrictInt | None] = Field(max_length=6)
    compatible: StrictBool


class RuntimeUpdateStatus(RuntimeModel):
    current_build_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    previous_build_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    ready: StrictBool
    recovery_required: StrictBool
    features: dict[str, StrictInt | None] = Field(max_length=6)
    reason: Literal['runtime_unavailable', 'core_unavailable'] | None
    candidate: RuntimeCandidate | None
    operation: RuntimeOperation | None


class RuntimePrepareRequest(RuntimeModel):
    request_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    expected_operation_id: str | None = Field(pattern=r'^[0-9a-f]{32}$')


class RuntimeApplyRequest(RuntimePrepareRequest):
    candidate_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    build_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    confirmation: str = Field(max_length=79)
    maintenance_override: StrictBool = False


class RuntimeAccepted(RuntimeModel):
    request_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    state: Literal['queued'] = 'queued'
