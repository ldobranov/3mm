"""Side-effect-free simulation and audited deployment of approved automations."""

import hashlib
import json
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.automation import AutomationAuditEvent, AutomationProposal, AutomationRevision
from backend.db.device import Device
from backend.services.device_commands import DeviceCommandError, queue_command
from three_mm_protocol.automation import AutomationDefinitionV1


class AutomationExecutionError(ValueError):
    pass


def simulate(definition: AutomationDefinitionV1, event: dict | None = None) -> dict:
    conditions = definition.trigger.conditions
    supplied = event or {}
    matched = all(supplied.get(key) == value for key, value in conditions.items()) if event is not None else None
    actions = [
        {
            "device_id": action.device_id,
            "capability_id": action.capability_id,
            "action": action.action,
            "arguments": action.arguments,
            "would_execute": matched is not False and definition.enabled,
        }
        for action in definition.actions
    ]
    return {
        "mode": "simulation",
        "mutated": False,
        "enabled": definition.enabled,
        "trigger_matched": matched,
        "actions": actions,
    }


def dry_run(proposal: AutomationProposal) -> dict:
    if proposal.status not in {"approved", "applied"}:
        raise AutomationExecutionError("Only an approved proposal can be dry-run")
    definition = AutomationDefinitionV1.model_validate(proposal.candidate)
    if definition.execution != "local":
        raise AutomationExecutionError("Core automation execution is not implemented")
    device_id = definition.trigger.device_id
    return {
        "mode": "dry-run",
        "mutated": False,
        "commands": [{
            "device_id": device_id,
            "command_type": "automation.apply",
            "payload": {"automation_id": proposal.proposal_id, "revision": 1, "definition": proposal.candidate},
        }],
    }


def _audit(db: Session, *, automation_id: str, proposal_id: str | None, revision_id: str | None, actor_user_id: int, event_type: str, details: dict) -> None:
    db.add(AutomationAuditEvent(
        event_id=f"aae_{uuid4().hex}", automation_id=automation_id, proposal_id=proposal_id,
        revision_id=revision_id, actor_user_id=actor_user_id, event_type=event_type, details=details,
    ))


def apply_proposal(db: Session, *, proposal: AutomationProposal, actor_user_id: int) -> AutomationRevision:
    if proposal.status != "approved":
        raise AutomationExecutionError("Only an approved proposal can be applied")
    plan = dry_run(proposal)
    command_spec = plan["commands"][0]
    device = db.scalar(select(Device).where(Device.device_id == command_spec["device_id"]))
    if device is None or device.revoked_at is not None:
        raise AutomationExecutionError("Target device is unavailable")
    revision_id = f"ar_{uuid4().hex}"
    revision = AutomationRevision(
        revision_id=revision_id, automation_id=proposal.proposal_id, revision=1,
        proposal_id=proposal.proposal_id, definition=proposal.candidate,
        definition_hash=proposal.candidate_hash, active=True, operation="apply",
        command_ids=[], applied_by_user_id=actor_user_id,
    )
    db.add(revision)
    db.flush()
    try:
        command = queue_command(
            db, device=device, command_type="automation.apply",
            payload={**command_spec["payload"], "revision_id": revision_id},
            idempotency_key=f"automation:{proposal.proposal_id}:revision:1", ttl_seconds=300,
        )
    except DeviceCommandError as exc:
        db.rollback()
        raise AutomationExecutionError(str(exc)) from exc
    revision.command_ids = [command.command_id]
    proposal.status = "applied"
    _audit(db, automation_id=proposal.proposal_id, proposal_id=proposal.proposal_id,
           revision_id=revision_id, actor_user_id=actor_user_id, event_type="automation.applied",
           details={"intent": proposal.intent, "candidate_hash": proposal.candidate_hash, "command_ids": revision.command_ids})
    db.commit()
    db.refresh(revision)
    return revision


def rollback(db: Session, *, current: AutomationRevision, actor_user_id: int) -> AutomationRevision:
    if not current.active:
        raise AutomationExecutionError("Only the active revision can be rolled back")
    device_id = (current.definition or {}).get("trigger", {}).get("device_id")
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if device is None or device.revoked_at is not None:
        raise AutomationExecutionError("Target device is unavailable")
    next_number = (db.scalar(select(func.max(AutomationRevision.revision)).where(
        AutomationRevision.automation_id == current.automation_id
    )) or 0) + 1
    previous = db.scalar(select(AutomationRevision).where(
        AutomationRevision.automation_id == current.automation_id,
        AutomationRevision.revision < current.revision,
        AutomationRevision.definition.is_not(None),
    ).order_by(AutomationRevision.revision.desc()))
    revision_id = f"ar_{uuid4().hex}"
    definition = previous.definition if previous else None
    command_type = "automation.apply" if definition else "automation.remove"
    payload = {"automation_id": current.automation_id, "revision": next_number, "revision_id": revision_id}
    if definition is not None:
        payload["definition"] = definition
    command = queue_command(
        db, device=device, command_type=command_type, payload=payload,
        idempotency_key=f"automation:{current.automation_id}:revision:{next_number}", ttl_seconds=300,
    )
    current.active = False
    restored = AutomationRevision(
        revision_id=revision_id, automation_id=current.automation_id, revision=next_number,
        proposal_id=previous.proposal_id if previous else None, definition=definition,
        definition_hash=previous.definition_hash if previous else None, active=definition is not None,
        operation="rollback", command_ids=[command.command_id], applied_by_user_id=actor_user_id,
    )
    db.add(restored)
    _audit(db, automation_id=current.automation_id, proposal_id=current.proposal_id,
           revision_id=revision_id, actor_user_id=actor_user_id, event_type="automation.rolled_back",
           details={"from_revision_id": current.revision_id, "restored_revision_id": previous.revision_id if previous else None, "command_ids": [command.command_id]})
    db.commit()
    db.refresh(restored)
    return restored


def set_enabled(
    db: Session,
    *,
    current: AutomationRevision,
    enabled: bool,
    actor_user_id: int,
) -> AutomationRevision:
    if not current.active or current.definition is None:
        raise AutomationExecutionError("Only an active automation can be enabled or disabled")
    definition = AutomationDefinitionV1.model_validate(current.definition)
    if definition.enabled is enabled:
        raise AutomationExecutionError("Automation already has the requested state")
    updated = definition.model_copy(update={"enabled": enabled})
    definition_json = updated.model_dump(mode="json")
    device = db.scalar(select(Device).where(Device.device_id == updated.trigger.device_id))
    if device is None or device.revoked_at is not None:
        raise AutomationExecutionError("Target device is unavailable")
    next_number = (db.scalar(select(func.max(AutomationRevision.revision)).where(
        AutomationRevision.automation_id == current.automation_id
    )) or 0) + 1
    revision_id = f"ar_{uuid4().hex}"
    command = queue_command(
        db,
        device=device,
        command_type="automation.apply",
        payload={
            "automation_id": current.automation_id,
            "revision": next_number,
            "revision_id": revision_id,
            "definition": definition_json,
        },
        idempotency_key=f"automation:{current.automation_id}:revision:{next_number}",
        ttl_seconds=300,
    )
    current.active = False
    revision = AutomationRevision(
        revision_id=revision_id,
        automation_id=current.automation_id,
        revision=next_number,
        proposal_id=current.proposal_id,
        definition=definition_json,
        definition_hash=hashlib.sha256(json.dumps(
            definition_json, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()).hexdigest(),
        active=True,
        operation="enable" if enabled else "disable",
        command_ids=[command.command_id],
        applied_by_user_id=actor_user_id,
    )
    db.add(revision)
    _audit(
        db,
        automation_id=current.automation_id,
        proposal_id=current.proposal_id,
        revision_id=revision_id,
        actor_user_id=actor_user_id,
        event_type="automation.enabled" if enabled else "automation.disabled",
        details={"from_revision_id": current.revision_id, "command_ids": [command.command_id]},
    )
    db.commit()
    db.refresh(revision)
    return revision
