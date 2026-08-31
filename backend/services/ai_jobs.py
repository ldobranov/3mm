"""Estimate, reserve, execute and settle paid AI automation planning jobs."""

import hashlib
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.automation import AiCreditAccount, AiJob, AiUsageLedger
from backend.services.ai_gateway import AiProviderGateway
from backend.services.automation_proposals import create_automation_proposal
from three_mm_protocol.automation import AutomationCapabilityContextV1, AutomationDefinitionV1


PROVIDER_DEFAULTS = {"groq": "llama-3.1-8b-instant", "openrouter": "openrouter/free"}
# The supported routes currently use provider free tiers and consume no 3mm credit.
# Paid model pricing can later be added through a catalog without changing jobs.
RATES = {"groq": (0, 0), "openrouter": (0, 0)}


class AiJobError(ValueError):
    pass


def _parse_automation_definition(content: str) -> AutomationDefinitionV1:
    candidate = json.loads(content)
    if isinstance(candidate, dict) and not {"name", "trigger", "actions"}.issubset(candidate):
        for wrapper in ("AutomationDefinitionV1", "automation", "definition"):
            wrapped = candidate.get(wrapper)
            if isinstance(wrapped, dict):
                candidate = wrapped
                break
    return AutomationDefinitionV1.model_validate(candidate)


def _hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _ledger(db: Session, job: AiJob, entry_type: str, amount: int, details: dict) -> None:
    db.add(AiUsageLedger(entry_id=f"aul_{uuid4().hex}", job_id=job.job_id, user_id=job.user_id, entry_type=entry_type, microcredits=amount, details=details))


def account_for(db: Session, user_id: int) -> AiCreditAccount:
    account = db.scalar(select(AiCreditAccount).where(AiCreditAccount.user_id == user_id))
    if account is None:
        account = AiCreditAccount(user_id=user_id, available_microcredits=0, reserved_microcredits=0)
        db.add(account); db.commit(); db.refresh(account)
    return account


def estimate_job(db: Session, *, user_id: int, intent: str, context: AutomationCapabilityContextV1, provider: str, model: str | None, payment_mode: str, max_output_tokens: int) -> AiJob:
    if provider not in PROVIDER_DEFAULTS or payment_mode not in {"prepaid", "byok"}:
        raise AiJobError("Unsupported provider or payment mode")
    request = {"purpose": "automation.plan", "intent": intent, "context": context.model_dump(mode="json"), "provider": provider, "model": model or PROVIDER_DEFAULTS[provider], "max_output_tokens": max_output_tokens}
    request_hash = _hash(request)
    reusable = db.scalar(select(AiJob).where(AiJob.user_id == user_id, AiJob.request_hash == request_hash, AiJob.status.in_(("completed", "reused")), AiJob.proposal_id.is_not(None)).order_by(AiJob.id.desc()))
    estimated_input = max(1, len(json.dumps(request, ensure_ascii=False)) // 4)
    input_rate, output_rate = RATES[provider]
    estimated_cost = (estimated_input * input_rate + max_output_tokens * output_rate + 999) // 1000
    job = AiJob(
        job_id=f"aij_{uuid4().hex}", user_id=user_id, purpose="automation.plan", request_hash=request_hash,
        provider=provider, model=request["model"], payment_mode=payment_mode,
        status="reused" if reusable else "estimated", estimated_input_tokens=estimated_input,
        estimated_output_tokens=max_output_tokens, estimated_max_microcredits=0 if reusable else estimated_cost,
        reserved_microcredits=0, proposal_id=reusable.proposal_id if reusable else None,
        artifact_hash=reusable.artifact_hash if reusable else None,
        actual_input_tokens=0 if reusable else None, actual_output_tokens=0 if reusable else None,
        actual_microcredits=0 if reusable else None, completed_at=datetime.now(timezone.utc) if reusable else None,
    )
    db.add(job)
    if reusable:
        _ledger(db, job, "artifact.reused", 0, {"source_job_id": reusable.job_id})
    db.commit(); db.refresh(job)
    return job


def execute_job(db: Session, *, job: AiJob, intent: str, context: AutomationCapabilityContextV1, approved_max: int, gateway: AiProviderGateway, api_key: str | None) -> AiJob:
    if job.status == "reused":
        return job
    if job.status != "estimated":
        raise AiJobError("AI job is not awaiting approval")
    expected_request = {"purpose": "automation.plan", "intent": intent, "context": context.model_dump(mode="json"), "provider": job.provider, "model": job.model, "max_output_tokens": job.estimated_output_tokens}
    if _hash(expected_request) != job.request_hash:
        raise AiJobError("AI job input or capability context changed after estimate")
    if approved_max < job.estimated_max_microcredits:
        raise AiJobError("Approved maximum is below the estimate")
    if job.payment_mode == "byok" and not api_key:
        raise AiJobError("A temporary provider key is required for BYOK")
    if job.payment_mode == "prepaid" and not (api_key or os.getenv(f"{job.provider.upper()}_API_KEY")):
        raise AiJobError("Server-managed provider key is not configured")
    account = account_for(db, job.user_id)
    if job.payment_mode == "prepaid":
        if account.available_microcredits < approved_max:
            raise AiJobError("Insufficient AI credit balance")
        account.available_microcredits -= approved_max
        account.reserved_microcredits += approved_max
        job.reserved_microcredits = approved_max
        _ledger(db, job, "budget.reserved", approved_max, {"approved_max_microcredits": approved_max})
    job.approved_max_microcredits = approved_max
    job.status = "running"
    db.commit()
    prompt = (
        "Return exactly one AutomationDefinitionV1 JSON object at the top level. "
        "Do not wrap it in AutomationDefinitionV1, automation, definition, markdown, or prose. "
        "Required top-level fields are schema_version, name, description, execution, enabled, "
        "trigger, and actions. Use only the supplied device_id and capability_id values; never generate code. "
        "Capability metadata is authoritative: automation_role selects trigger or action, automation_events "
        "and automation_actions list allowed operations, automation_channels lists allowed channel values, "
        "automation_required_fields lists required conditions or arguments, and automation_value_type defines "
        "the JSON type for value. Operation-specific automation_required_fields_<operation> and "
        "automation_value_type_<operation> override those generic fields. Use JSON booleans true/false "
        "when that type is boolean."
    )
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps({
        "intent": intent,
        "output_schema": AutomationDefinitionV1.model_json_schema(),
        "context": context.model_dump(mode="json"),
    }, ensure_ascii=False)}]
    try:
        completion = gateway.complete(provider=job.provider, model=job.model, messages=messages, max_tokens=job.estimated_output_tokens, api_key=api_key)
        definition = _parse_automation_definition(completion.content)
        proposal = create_automation_proposal(db, intent=intent, candidate=definition, context=context, created_by_user_id=job.user_id)
        input_rate, output_rate = RATES[job.provider]
        actual_cost = (completion.input_tokens * input_rate + completion.output_tokens * output_rate + 999) // 1000
        charged = min(actual_cost, approved_max) if job.payment_mode == "prepaid" else 0
        if job.payment_mode == "prepaid":
            account.reserved_microcredits -= approved_max
            account.available_microcredits += approved_max - charged
            _ledger(db, job, "usage.charged", charged, {"actual_microcredits": actual_cost})
            if approved_max > charged:
                _ledger(db, job, "budget.released", approved_max - charged, {})
        job.status = "completed"; job.actual_input_tokens = completion.input_tokens; job.actual_output_tokens = completion.output_tokens
        job.actual_microcredits = actual_cost; job.reserved_microcredits = 0; job.proposal_id = proposal.proposal_id
        job.artifact_hash = proposal.candidate_hash; job.completed_at = datetime.now(timezone.utc)
        db.commit(); db.refresh(job); return job
    except Exception as exc:
        db.rollback()
        job = db.scalar(select(AiJob).where(AiJob.job_id == job.job_id))
        account = account_for(db, job.user_id)
        if job.payment_mode == "prepaid" and job.reserved_microcredits:
            account.reserved_microcredits -= job.reserved_microcredits
            account.available_microcredits += job.reserved_microcredits
            _ledger(db, job, "budget.released", job.reserved_microcredits, {"reason": "job_failed"})
        job.reserved_microcredits = 0; job.status = "failed"; job.error_code = "provider_or_validation_error"; job.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise AiJobError("AI job failed; reserved credit was released") from exc


def grant_credit(db: Session, *, user_id: int, microcredits: int, actor_user_id: int) -> AiCreditAccount:
    if microcredits <= 0:
        raise AiJobError("Credit grant must be positive")
    account = account_for(db, user_id)
    account.available_microcredits += microcredits
    db.add(AiUsageLedger(
        entry_id=f"aul_{uuid4().hex}", job_id="account", user_id=user_id,
        entry_type="credit.granted", microcredits=microcredits,
        details={"actor_user_id": actor_user_id},
    ))
    db.commit(); db.refresh(account); return account
