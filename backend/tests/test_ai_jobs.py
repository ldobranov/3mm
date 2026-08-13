import json
from datetime import datetime, timezone

import backend.database  # noqa: F401
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.automation import AiJob, AiUsageLedger
from backend.db.base import Base
from backend.db.user import User
from backend.services.ai_gateway import AiCompletion
from backend.services.ai_jobs import AiJobError, estimate_job, execute_job, grant_credit
from backend.utils.auth import hash_password
from three_mm_protocol.automation import AutomationCapabilityContextV1, CapabilityContextEntry


DEVICE_ID = "dev_0123456789abcdef0123456789abcdef"


def context():
    entries = []
    for capability in ("gpio.digital.input", "gpio.digital.control"):
        entries.append(CapabilityContextEntry(device_id=DEVICE_ID, device_name="Mock Pi", device_role="standalone", capability_id=capability, module_id="org.3mm.mock-gpio", module_version="1.0.0"))
    return AutomationCapabilityContextV1(capabilities=tuple(entries))


class FakeGateway:
    def __init__(self): self.calls = 0; self.keys = []
    def complete(self, **kwargs):
        self.calls += 1; self.keys.append(kwargs["api_key"])
        candidate = {
            "schema_version": 1, "name": "Mirror input", "execution": "local", "enabled": True,
            "trigger": {"kind": "capability_event", "device_id": DEVICE_ID, "capability_id": "gpio.digital.input", "event": "changed", "conditions": {"channel": "gpio.input.1", "value": True}},
            "actions": [{"kind": "capability_command", "device_id": DEVICE_ID, "capability_id": "gpio.digital.control", "action": "set_output", "arguments": {"channel": "gpio.output.1", "value": True}}],
        }
        return AiCompletion(content=json.dumps(candidate), input_tokens=120, output_tokens=80, provider_request_id="provider-secret-id")


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine); session = Session(engine)
    user = User(username="admin", email="admin@example.com", hashed_password=hash_password("password"), role="admin")
    session.add(user); session.commit()
    yield session, user
    session.close(); engine.dispose()


def test_prepaid_job_reserves_settles_and_reuses_unchanged_artifact(db, monkeypatch):
    session, user = db; monkeypatch.setenv("GROQ_API_KEY", "server-secret")
    job = estimate_job(session, user_id=user.id, intent="Mirror it", context=context(), provider="groq", model=None, payment_mode="prepaid", max_output_tokens=500)
    with pytest.raises(AiJobError, match="Insufficient"):
        execute_job(session, job=job, intent="Mirror it", context=context(), approved_max=job.estimated_max_microcredits, gateway=FakeGateway(), api_key=None)
    account = grant_credit(session, user_id=user.id, microcredits=10_000, actor_user_id=user.id)
    before = account.available_microcredits
    gateway = FakeGateway()
    completed = execute_job(session, job=job, intent="Mirror it", context=context(), approved_max=job.estimated_max_microcredits, gateway=gateway, api_key=None)
    assert completed.status == "completed" and completed.proposal_id
    assert completed.actual_input_tokens == 120 and completed.actual_output_tokens == 80
    assert account.reserved_microcredits == 0
    assert account.available_microcredits == before - min(completed.actual_microcredits, job.approved_max_microcredits)
    reused = estimate_job(session, user_id=user.id, intent="Mirror it", context=context(), provider="groq", model=None, payment_mode="prepaid", max_output_tokens=500)
    assert reused.status == "reused" and reused.proposal_id == completed.proposal_id
    assert execute_job(session, job=reused, intent="Mirror it", context=context(), approved_max=0, gateway=gateway, api_key=None).status == "reused"
    assert gateway.calls == 1


def test_byok_key_is_ephemeral_and_does_not_touch_prepaid_balance(db):
    session, user = db; gateway = FakeGateway()
    job = estimate_job(session, user_id=user.id, intent="Mirror it", context=context(), provider="openrouter", model="test-model", payment_mode="byok", max_output_tokens=500)
    completed = execute_job(session, job=job, intent="Mirror it", context=context(), approved_max=job.estimated_max_microcredits, gateway=gateway, api_key="temporary-super-secret")
    assert completed.status == "completed" and gateway.keys == ["temporary-super-secret"]
    account = grant_credit(session, user_id=user.id, microcredits=100, actor_user_id=user.id)
    assert account.available_microcredits == 100 and account.reserved_microcredits == 0
    persisted = " ".join(str(value) for row in session.scalars(select(AiUsageLedger)).all() for value in (row.details, row.entry_type))
    persisted += " " + " ".join(str(row.__dict__) for row in session.scalars(select(AiJob)).all())
    assert "temporary-super-secret" not in persisted
    assert completed.actual_microcredits > 0
