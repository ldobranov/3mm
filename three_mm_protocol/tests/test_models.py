from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from three_mm_protocol import PROTOCOL_VERSION, AgentHello, AgentRole


def valid_hello_data() -> dict:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "agent_version": "0.1.0-dev",
        "device_id": "dev_0123456789abcdef0123456789abcdef",
        "display_name": "test-agent",
        "role": AgentRole.NODE,
        "started_at": datetime.now(UTC),
        "capabilities": (),
    }


def test_protocol_models_reject_unknown_fields():
    data = valid_hello_data()
    data["unexpected"] = "not allowed"

    with pytest.raises(ValidationError):
        AgentHello.model_validate(data)


def test_protocol_models_reject_unknown_versions():
    data = valid_hello_data()
    data["protocol_version"] = "99.0"

    with pytest.raises(ValidationError):
        AgentHello.model_validate(data)


def test_protocol_round_trip_uses_json_safe_values():
    original = AgentHello.model_validate(valid_hello_data())

    restored = AgentHello.model_validate_json(original.model_dump_json())

    assert restored == original
