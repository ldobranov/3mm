"""AI automation planning and explicit proposal approval boundaries."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.automation import AiJob, AiUsageLedger, AutomationAuditEvent, AutomationProposal, AutomationRevision
from backend.db.settings import Settings
from backend.db.user import User
from backend.services.ai_capability_context import build_automation_capability_context
from backend.services.ai_gateway import AiProviderGateway, get_ai_gateway
from backend.services.ai_jobs import AiJobError, account_for, estimate_job, execute_job, grant_credit
from backend.services.automation_proposals import (
    ProposalApprovalError,
    approve_automation_proposal,
    create_automation_proposal,
)
from backend.services.automation_execution import (
    AutomationExecutionError,
    apply_proposal,
    dry_run,
    rollback,
    simulate,
)
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from backend.utils.secure_settings import SecureSettingsError, decrypt_secret
from three_mm_protocol.automation import (
    AutomationCapabilityContextV1,
    AutomationDefinitionV1,
)


router = APIRouter(prefix="/api/v1/ai", tags=["ai-automations"])


def _server_managed_provider_key(db: Session, provider: str) -> str | None:
    setting_key = {
        "groq": "ai_groq_api_key",
        "openrouter": "ai_openrouter_api_key",
    }.get(provider)
    if setting_key is None:
        return None
    row = db.scalar(select(Settings).where(
        Settings.key == setting_key,
        Settings.language_code.is_(None),
        Settings.user_id.is_(None),
    ))
    return decrypt_secret(row.value) if row and row.value else None


class CreateAutomationProposalRequest(BaseModel):
    intent: str = Field(min_length=1, max_length=4000)
    candidate: AutomationDefinitionV1
    model_config = ConfigDict(extra="forbid")


class ApproveAutomationProposalRequest(BaseModel):
    expected_candidate_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid")


class AutomationProposalResponse(BaseModel):
    proposal_id: str
    created_by_user_id: int
    intent: str
    candidate: dict
    candidate_hash: str
    context_hash: str
    status: str
    validation_issues: list[dict]
    diff: dict
    created_at: datetime
    validated_at: datetime
    approved_at: datetime | None
    approved_by_user_id: int | None
    model_config = ConfigDict(from_attributes=True, extra="forbid")


ProposalStatus = Literal["validated", "invalid", "approved", "applied"]


class SimulationRequest(BaseModel):
    event: dict | None = None
    model_config = ConfigDict(extra="forbid")


class AutomationRevisionResponse(BaseModel):
    revision_id: str
    automation_id: str
    revision: int
    proposal_id: str | None
    definition: dict | None
    definition_hash: str | None
    active: bool
    operation: str
    command_ids: list[str]
    applied_by_user_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class AutomationAuditResponse(BaseModel):
    event_id: str
    automation_id: str
    proposal_id: str | None
    revision_id: str | None
    actor_user_id: int
    event_type: str
    details: dict
    created_at: datetime
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class AiJobEstimateRequest(BaseModel):
    intent: str = Field(min_length=1, max_length=4000)
    provider: Literal["groq", "openrouter"]
    model: str | None = Field(default=None, max_length=160)
    payment_mode: Literal["prepaid", "byok"] = "prepaid"
    max_output_tokens: int = Field(default=1200, ge=100, le=8000)
    model_config = ConfigDict(extra="forbid")


class AiJobExecuteRequest(BaseModel):
    intent: str = Field(min_length=1, max_length=4000)
    approved_max_microcredits: int = Field(ge=0)
    model_config = ConfigDict(extra="forbid")


class AiJobResponse(BaseModel):
    job_id: str; purpose: str; provider: str; model: str; payment_mode: str; status: str
    estimated_input_tokens: int; estimated_output_tokens: int; estimated_max_microcredits: int
    approved_max_microcredits: int | None; reserved_microcredits: int
    actual_input_tokens: int | None; actual_output_tokens: int | None; actual_microcredits: int | None
    artifact_hash: str | None; proposal_id: str | None; error_code: str | None; created_at: datetime; completed_at: datetime | None
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class CreditAccountResponse(BaseModel):
    user_id: int; available_microcredits: int; reserved_microcredits: int
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class CreditGrantRequest(BaseModel):
    user_id: int = Field(ge=1)
    microcredits: int = Field(gt=0, le=1_000_000_000)
    model_config = ConfigDict(extra="forbid")


class UsageLedgerResponse(BaseModel):
    entry_id: str; job_id: str; user_id: int; entry_type: str; microcredits: int; details: dict; created_at: datetime
    model_config = ConfigDict(from_attributes=True, extra="forbid")


@router.get(
    "/automation-context",
    response_model=AutomationCapabilityContextV1,
    summary="Read the trusted capability context available for AI planning",
)
def read_automation_context(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AutomationCapabilityContextV1:
    return build_automation_capability_context(db)


def _proposal(db: Session, proposal_id: str) -> AutomationProposal:
    row = db.scalar(select(AutomationProposal).where(
        AutomationProposal.proposal_id == proposal_id
    ))
    if row is None:
        raise HTTPException(status_code=404, detail="Automation proposal was not found")
    return row


@router.post("/automation-proposals", response_model=AutomationProposalResponse)
def create_proposal(
    payload: CreateAutomationProposalRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AutomationProposal:
    return create_automation_proposal(
        db,
        intent=payload.intent,
        candidate=payload.candidate,
        context=build_automation_capability_context(db),
        created_by_user_id=admin.id,
    )


@router.get("/automation-proposals", response_model=list[AutomationProposalResponse])
def list_proposals(
    status: ProposalStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AutomationProposal]:
    statement = select(AutomationProposal).order_by(
        AutomationProposal.created_at.desc(),
        AutomationProposal.id.desc(),
    )
    if status is not None:
        statement = statement.where(AutomationProposal.status == status)
    return list(db.scalars(statement.limit(limit)).all())


@router.get(
    "/automation-proposals/{proposal_id}",
    response_model=AutomationProposalResponse,
)
def read_proposal(
    proposal_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AutomationProposal:
    return _proposal(db, proposal_id)


@router.post(
    "/automation-proposals/{proposal_id}/approve",
    response_model=AutomationProposalResponse,
)
def approve_proposal(
    proposal_id: str,
    payload: ApproveAutomationProposalRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AutomationProposal:
    try:
        return approve_automation_proposal(
            db,
            proposal=_proposal(db, proposal_id),
            expected_candidate_hash=payload.expected_candidate_hash,
            approved_by_user_id=admin.id,
        )
    except ProposalApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/automation-proposals/{proposal_id}/simulate")
def simulate_proposal(
    proposal_id: str,
    payload: SimulationRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    proposal = _proposal(db, proposal_id)
    return simulate(AutomationDefinitionV1.model_validate(proposal.candidate), payload.event)


@router.post("/automation-proposals/{proposal_id}/dry-run")
def dry_run_proposal(
    proposal_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return dry_run(_proposal(db, proposal_id))
    except AutomationExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/automation-proposals/{proposal_id}/apply",
    response_model=AutomationRevisionResponse,
)
def apply_approved_proposal(
    proposal_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AutomationRevision:
    try:
        return apply_proposal(db, proposal=_proposal(db, proposal_id), actor_user_id=admin.id)
    except AutomationExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/automation-revisions/{revision_id}/rollback",
    response_model=AutomationRevisionResponse,
)
def rollback_revision(
    revision_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AutomationRevision:
    current = db.scalar(select(AutomationRevision).where(AutomationRevision.revision_id == revision_id))
    if current is None:
        raise HTTPException(status_code=404, detail="Automation revision was not found")
    try:
        return rollback(db, current=current, actor_user_id=admin.id)
    except AutomationExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/automation-revisions", response_model=list[AutomationRevisionResponse])
def list_automation_revisions(
    automation_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AutomationRevision]:
    statement = select(AutomationRevision).order_by(
        AutomationRevision.created_at.desc(), AutomationRevision.id.desc()
    )
    if automation_id:
        statement = statement.where(AutomationRevision.automation_id == automation_id)
    return list(db.scalars(statement.limit(limit)).all())


@router.get("/automation-audit", response_model=list[AutomationAuditResponse])
def list_automation_audit(
    automation_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AutomationAuditEvent]:
    statement = select(AutomationAuditEvent).order_by(
        AutomationAuditEvent.created_at.desc(), AutomationAuditEvent.id.desc()
    )
    if automation_id:
        statement = statement.where(AutomationAuditEvent.automation_id == automation_id)
    return list(db.scalars(statement.limit(limit)).all())


@router.post("/jobs/estimate", response_model=AiJobResponse)
def estimate_ai_job(payload: AiJobEstimateRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> AiJob:
    try:
        return estimate_job(db, user_id=admin.id, intent=payload.intent, context=build_automation_capability_context(db), provider=payload.provider, model=payload.model, payment_mode=payload.payment_mode, max_output_tokens=payload.max_output_tokens)
    except AiJobError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/execute", response_model=AiJobResponse)
def execute_ai_job(
    job_id: str, payload: AiJobExecuteRequest,
    temporary_provider_key: str | None = Header(default=None, alias="X-3mm-AI-Key"),
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
    gateway: AiProviderGateway = Depends(get_ai_gateway),
) -> AiJob:
    job = db.scalar(select(AiJob).where(AiJob.job_id == job_id, AiJob.user_id == admin.id))
    if job is None:
        raise HTTPException(status_code=404, detail="AI job was not found")
    try:
        provider_key = temporary_provider_key
        if job.payment_mode == "prepaid":
            provider_key = _server_managed_provider_key(db, job.provider)
        return execute_job(db, job=job, intent=payload.intent, context=build_automation_capability_context(db), approved_max=payload.approved_max_microcredits, gateway=gateway, api_key=provider_key)
    except SecureSettingsError as exc:
        raise HTTPException(status_code=500, detail="Server-managed provider key could not be decrypted") from exc
    except AiJobError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/credits", response_model=CreditAccountResponse)
def read_credit_account(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return account_for(db, admin.id)


@router.post("/credits/grant", response_model=CreditAccountResponse)
def grant_ai_credit(payload: CreditGrantRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        return grant_credit(db, user_id=payload.user_id, microcredits=payload.microcredits, actor_user_id=admin.id)
    except AiJobError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/usage", response_model=list[UsageLedgerResponse])
def read_usage(limit: int = Query(default=100, ge=1, le=200), admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return list(db.scalars(select(AiUsageLedger).where(AiUsageLedger.user_id == admin.id).order_by(AiUsageLedger.id.desc()).limit(limit)).all())
