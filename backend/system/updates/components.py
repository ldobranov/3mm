"""Public DTOs for narrow independently pinned local component updates."""
from typing import Literal
from pydantic import Field, StrictBool, StrictInt
from backend.system.updates.platform_runtime import RuntimeModel, RuntimeAccepted

ComponentKind = Literal['agent', 'application_host']


class ComponentOperation(RuntimeModel):
    request_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    component: ComponentKind
    target_id: str = Field(pattern=r'^(local|[0-9a-f]{24})$')
    action: Literal['component_prepare', 'component_apply', 'component_rollback', 'component_recover']
    state: Literal['queued', 'preparing', 'applying', 'recovering', 'succeeded', 'failed', 'recovery_required']
    reason: Literal['candidate_prepared', 'component_updated', 'component_rolled_back', 'component_recovered',
        'preparation_failed', 'previous_component_ready', 'component_outcome_unconfirmed', 'worker_interrupted'] | None
    updated_at: StrictInt


class ComponentCandidate(RuntimeModel):
    candidate_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    build_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    bytes: StrictInt = Field(gt=0, le=128*1024*1024)
    compatible: StrictBool


class ComponentUpdateStatus(RuntimeModel):
    component: ComponentKind
    target_id: str = Field(pattern=r'^(local|[0-9a-f]{24})$')
    current_build_id: str | None = Field(pattern=r'^[0-9a-f]{64}$')
    previous_build_id: str | None = Field(pattern=r'^[0-9a-f]{64}$')
    ready: StrictBool
    recovery_required: StrictBool
    candidate: ComponentCandidate | None
    operation: ComponentOperation | None


class ComponentPrepareRequest(RuntimeModel):
    request_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    expected_operation_id: str | None = Field(pattern=r'^[0-9a-f]{32}$')


class ComponentSwitchRequest(ComponentPrepareRequest):
    build_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    confirmation: str = Field(max_length=128)
    maintenance_override: StrictBool = False


class ComponentApplyRequest(ComponentSwitchRequest):
    candidate_id: str = Field(pattern=r'^[0-9a-f]{32}$')
