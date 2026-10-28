"""Validation and explicit approval for untrusted automation proposals."""

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.db.automation import AutomationProposal
from three_mm_protocol.automation import (
    AutomationCapabilityContextV1,
    AutomationDefinitionV1,
    validate_automation_capabilities,
)


class ProposalApprovalError(ValueError):
    pass


def _canonical_hash(value: dict) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _proposal_diff(candidate: AutomationDefinitionV1) -> dict:
    return {
        "operation": "create",
        "automation": {
            "name": candidate.name,
            "execution": candidate.execution,
            "enabled": candidate.enabled,
        },
        "trigger": candidate.trigger.model_dump(mode="json"),
        "actions": [action.model_dump(mode="json") for action in candidate.actions],
        "target_devices": sorted({
            candidate.trigger.device_id,
            *(action.device_id for action in candidate.actions),
        }),
    }


def create_automation_proposal(
    db: Session,
    *,
    intent: str,
    candidate: AutomationDefinitionV1,
    context: AutomationCapabilityContextV1,
    created_by_user_id: int,
    now: datetime | None = None,
) -> AutomationProposal:
    validated_at = now or datetime.now(timezone.utc)
    candidate_data = candidate.model_dump(mode="json")
    context_data = context.model_dump(mode="json")
    issues = validate_automation_capabilities(candidate, context)
    row = AutomationProposal(
        proposal_id=f"ap_{uuid4().hex}",
        created_by_user_id=created_by_user_id,
        intent=intent,
        candidate=candidate_data,
        candidate_hash=_canonical_hash(candidate_data),
        context_hash=_canonical_hash(context_data),
        status="invalid" if issues else "validated",
        validation_issues=[issue.model_dump(mode="json") for issue in issues],
        diff=_proposal_diff(candidate),
        validated_at=validated_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def approve_automation_proposal(
    db: Session,
    *,
    proposal: AutomationProposal,
    expected_candidate_hash: str,
    approved_by_user_id: int,
    now: datetime | None = None,
) -> AutomationProposal:
    if proposal.status != "validated":
        raise ProposalApprovalError("Only a validated proposal can be approved")
    if proposal.candidate_hash != expected_candidate_hash:
        raise ProposalApprovalError("Proposal content changed after review")
    proposal.status = "approved"
    proposal.approved_by_user_id = approved_by_user_id
    proposal.approved_at = now or datetime.now(timezone.utc)
    db.commit()
    db.refresh(proposal)
    return proposal
