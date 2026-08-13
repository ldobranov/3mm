from datetime import datetime, timezone

import backend.database  # noqa: F401
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.automation import AutomationAuditEvent, AutomationProposal
from backend.db.base import Base
from backend.db.device import Device, DeviceCommand
from backend.db.user import User
from backend.services.automation_execution import apply_proposal, dry_run, rollback, simulate
from backend.utils.auth import hash_password
from three_mm_protocol.automation import AutomationDefinitionV1


DEVICE_ID = "dev_0123456789abcdef0123456789abcdef"


def candidate():
    return AutomationDefinitionV1.model_validate({
        "schema_version": 1, "name": "Mirror input", "execution": "local", "enabled": True,
        "trigger": {"kind": "capability_event", "device_id": DEVICE_ID, "capability_id": "gpio.digital.input", "event": "changed", "conditions": {"value": True}},
        "actions": [{"kind": "capability_command", "device_id": DEVICE_ID, "capability_id": "gpio.digital.control", "action": "set_output", "arguments": {"channel": "gpio.output.1", "value": True}}],
    })


def test_simulation_is_pure_and_apply_and_rollback_are_audited():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    user = User(username="admin", email="admin@example.com", hashed_password=hash_password("password"), role="admin")
    device = Device(device_id=DEVICE_ID, role="standalone", protocol_version="1.0", approved_at=datetime.now(timezone.utc))
    db.add_all([user, device]); db.commit()
    definition = candidate()
    proposal = AutomationProposal(
        proposal_id="ap_test", created_by_user_id=user.id, intent="Mirror it", candidate=definition.model_dump(mode="json"),
        candidate_hash="a" * 64, context_hash="b" * 64, status="approved", validation_issues=[], diff={},
        validated_at=datetime.now(timezone.utc), approved_at=datetime.now(timezone.utc), approved_by_user_id=user.id,
    )
    db.add(proposal); db.commit()

    result = simulate(definition, {"value": False})
    assert result["mutated"] is False and result["actions"][0]["would_execute"] is False
    assert dry_run(proposal)["commands"][0]["command_type"] == "automation.apply"
    assert db.scalar(select(DeviceCommand)) is None

    applied = apply_proposal(db, proposal=proposal, actor_user_id=user.id)
    command = db.scalar(select(DeviceCommand).where(DeviceCommand.command_id == applied.command_ids[0]))
    assert command.command_type == "automation.apply"
    assert proposal.status == "applied"

    removed = rollback(db, current=applied, actor_user_id=user.id)
    rollback_command = db.scalar(select(DeviceCommand).where(DeviceCommand.command_id == removed.command_ids[0]))
    assert removed.operation == "rollback" and removed.active is False
    assert rollback_command.command_type == "automation.remove"
    events = list(db.scalars(select(AutomationAuditEvent).order_by(AutomationAuditEvent.id)))
    assert [event.event_type for event in events] == ["automation.applied", "automation.rolled_back"]
    assert events[0].details["intent"] == "Mirror it"
    db.close(); engine.dispose()
