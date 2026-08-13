from datetime import datetime, timezone

import backend.database  # noqa: F401
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.automation import AutomationProposal
from backend.db.base import Base
from backend.services.automation_proposals import (
    ProposalApprovalError,
    approve_automation_proposal,
    create_automation_proposal,
)
from three_mm_protocol.automation import (
    AutomationCapabilityContextV1,
    AutomationDefinitionV1,
    CapabilityCommandAction,
    CapabilityContextEntry,
    CapabilityEventTrigger,
)


DEVICE_ID = "dev_0123456789abcdef0123456789abcdef"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


def _context(*capability_ids: str) -> AutomationCapabilityContextV1:
    return AutomationCapabilityContextV1(capabilities=tuple(
        CapabilityContextEntry(
            device_id=DEVICE_ID,
            device_name="Mock Pi",
            device_role="standalone",
            capability_id=capability_id,
            module_id="org.3mm.mock-gpio",
            module_version="1.0.0",
        )
        for capability_id in capability_ids
    ))


def _candidate(action_capability: str = "gpio.digital.control") -> AutomationDefinitionV1:
    return AutomationDefinitionV1(
        name="Mirror GPIO",
        trigger=CapabilityEventTrigger(
            device_id=DEVICE_ID,
            capability_id="gpio.digital.input",
            event="changed",
        ),
        actions=(CapabilityCommandAction(
            device_id=DEVICE_ID,
            capability_id=action_capability,
            action="set_output",
            arguments={"channel": "gpio.output.1", "value": True},
        ),),
    )


def test_validated_proposal_has_reviewable_diff_and_requires_matching_hash(db):
    row = create_automation_proposal(
        db,
        intent="When input one is on, turn output one on",
        candidate=_candidate(),
        context=_context("gpio.digital.input", "gpio.digital.control"),
        created_by_user_id=7,
        now=datetime(2026, 8, 13, tzinfo=timezone.utc),
    )
    assert row.status == "validated"
    assert row.diff["target_devices"] == [DEVICE_ID]
    assert row.diff["actions"][0]["arguments"]["channel"] == "gpio.output.1"

    with pytest.raises(ProposalApprovalError, match="changed after review"):
        approve_automation_proposal(
            db,
            proposal=row,
            expected_candidate_hash="0" * 64,
            approved_by_user_id=7,
        )

    approved = approve_automation_proposal(
        db,
        proposal=row,
        expected_candidate_hash=row.candidate_hash,
        approved_by_user_id=7,
    )
    assert approved.status == "approved"
    assert approved.approved_at is not None
    with pytest.raises(ProposalApprovalError, match="Only a validated"):
        approve_automation_proposal(
            db,
            proposal=approved,
            expected_candidate_hash=approved.candidate_hash,
            approved_by_user_id=7,
        )


def test_invalid_proposal_cannot_be_approved(db):
    row = create_automation_proposal(
        db,
        intent="Take a photo",
        candidate=_candidate("camera.capture"),
        context=_context("gpio.digital.input", "gpio.digital.control"),
        created_by_user_id=7,
    )
    assert row.status == "invalid"
    assert row.validation_issues[0]["code"] == "capability.unavailable"
    with pytest.raises(ProposalApprovalError, match="Only a validated"):
        approve_automation_proposal(
            db,
            proposal=row,
            expected_candidate_hash=row.candidate_hash,
            approved_by_user_id=7,
        )
    assert db.query(AutomationProposal).count() == 1
