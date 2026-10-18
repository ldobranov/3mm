"""M21 interactive session protocol tests (WP1): models, state, frames."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from three_mm_protocol.interactive_session import (
    MAX_SESSION_FRAME_BYTES,
    MAX_SESSION_PAYLOAD_BYTES,
    SESSION_CONTRACT,
    SESSION_PROTOCOL_VERSION,
    SessionControlV1,
    SessionFrameHeaderV1,
    SessionOpenAcceptanceV1,
    SessionOpenRequestV1,
    SessionProtocolError,
    SessionStatusV1,
    advance_session_state,
    decode_session_frame,
    encode_session_frame,
    is_terminal_session_state,
    provider_declaration,
)

SESSION_ID = "ses_" + "a" * 32
DEVICE_ID = "dev_" + "b" * 32
NOW = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)


def open_request(**overrides):
    payload = {
        "request_id": "open_req_1",
        "provider_id": "org.example.echo",
        "capability_id": "org.example.echo",
        "device_id": DEVICE_ID,
        "access_mode": "read",
        "options": {},
    }
    payload.update(overrides)
    return SessionOpenRequestV1(**payload)


def open_acceptance(**overrides):
    payload = {
        "request_id": "open_req_1",
        "session_id": SESSION_ID,
        "provider_id": "org.example.echo",
        "capability_id": "org.example.echo",
        "device_id": DEVICE_ID,
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=4),
    }
    payload.update(overrides)
    return SessionOpenAcceptanceV1(**payload)


def test_contract_constants():
    assert SESSION_CONTRACT == "interactive-session.v1"
    assert SESSION_PROTOCOL_VERSION == 1


def test_open_request_round_trip():
    request = open_request()
    assert request.session_request_version == 1
    assert request.model_dump(mode="json")["access_mode"] == "read"


def test_open_request_rejects_bare_session_id():
    with pytest.raises(ValidationError):
        open_request(request_id="not-an-identifier")


def test_open_request_rejects_unknown_field():
    with pytest.raises(ValidationError):
        open_request(unexpected="nope")


def test_open_request_rejects_bad_provider_id():
    with pytest.raises(ValidationError):
        open_request(provider_id="NotAValidModuleId")


def test_open_acceptance_requires_future_expiry():
    with pytest.raises(ValidationError):
        open_acceptance(created_at=NOW, expires_at=NOW)


def test_open_acceptance_rejects_naive_datetime():
    with pytest.raises(ValidationError):
        open_acceptance(created_at=datetime(2026, 10, 12, 10, 0))


def test_open_acceptance_json_round_trip():
    acceptance = open_acceptance()
    restored = SessionOpenAcceptanceV1.model_validate_json(
        acceptance.model_dump_json()
    )
    assert restored == acceptance


def test_status_json_round_trip():
    status = SessionStatusV1(
        session_id=SESSION_ID,
        state="active",
        device_id=DEVICE_ID,
        provider_id="org.example.echo",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=4),
    )
    restored = SessionStatusV1.model_validate_json(status.model_dump_json())
    assert restored == status


def test_status_round_trip():
    status = SessionStatusV1(
        session_id=SESSION_ID,
        state="active",
        device_id=DEVICE_ID,
        provider_id="org.example.echo",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=4),
    )
    assert status.state == "active"


def test_control_validates_arguments():
    control = SessionControlV1(
        session_id=SESSION_ID,
        control_id="ctrl_1",
        action="resize",
        arguments={"rows": 24, "cols": 80},
    )
    assert control.arguments["rows"] == 24


def test_control_rejects_bad_action():
    with pytest.raises(ValidationError):
        SessionControlV1(
            session_id=SESSION_ID,
            control_id="ctrl_1",
            action="Bad Action",
            arguments={},
        )


def test_state_machine_happy_path():
    assert advance_session_state("requested", "open_accepted") == "active"
    assert advance_session_state("active", "detach") == "detached"
    assert advance_session_state("detached", "attach") == "active"
    assert advance_session_state("active", "close") == "closed"


def test_state_machine_rejects_invalid_transition():
    with pytest.raises(SessionProtocolError):
        advance_session_state("active", "attach")


def test_state_machine_terminate_from_any_active_state():
    assert advance_session_state("active", "terminate") == "terminated"
    assert advance_session_state("detached", "terminate") == "terminated"


def test_state_machine_cannot_terminate_twice():
    with pytest.raises(SessionProtocolError):
        advance_session_state("closed", "terminate")


def test_is_terminal_session_state():
    assert is_terminal_session_state("closed")
    assert is_terminal_session_state("terminated")
    assert is_terminal_session_state("error")
    assert not is_terminal_session_state("active")


def test_encode_decode_utf8_frame():
    frame = encode_session_frame(
        op="data", seq=1, session_id=SESSION_ID, payload=b"hello"
    )
    header, payload = decode_session_frame(frame)
    assert header.op == "data"
    assert header.seq == 1
    assert header.session_id == SESSION_ID
    assert header.payload_kind == "utf8"
    assert payload == b"hello"


def test_encode_decode_binary_frame():
    blob = b"\x00\x01\x02\xff"
    frame = encode_session_frame(
        op="data", seq=2, session_id=SESSION_ID, payload=blob, payload_kind="binary"
    )
    header, payload = decode_session_frame(frame)
    assert header.payload_kind == "binary"
    assert payload == blob


def test_encode_rejects_non_utf8_utf8_frame():
    with pytest.raises(SessionProtocolError):
        encode_session_frame(
            op="data",
            seq=1,
            session_id=SESSION_ID,
            payload=b"\xff\xfe",
            payload_kind="utf8",
        )


def test_encode_rejects_unknown_op():
    with pytest.raises(SessionProtocolError):
        encode_session_frame(op="bogus", seq=1, session_id=SESSION_ID)


def test_encode_rejects_oversized_payload():
    with pytest.raises(SessionProtocolError):
        encode_session_frame(
            op="data",
            seq=1,
            session_id=SESSION_ID,
            payload=b"x" * (MAX_SESSION_PAYLOAD_BYTES + 1),
        )


def test_decode_rejects_truncated_frame():
    frame = encode_session_frame(
        op="data", seq=1, session_id=SESSION_ID, payload=b"abc"
    )
    with pytest.raises(SessionProtocolError):
        decode_session_frame(frame[:-1])


def test_decode_rejects_bad_magic():
    with pytest.raises(SessionProtocolError):
        decode_session_frame(b"XXXX" + b"\x00" * 16)


def test_decode_rejects_oversized_frame():
    with pytest.raises(SessionProtocolError):
        decode_session_frame(b"3MMS" + b"\x00" * (MAX_SESSION_FRAME_BYTES + 1))


def test_decode_rejects_extra_trailing_bytes():
    frame = encode_session_frame(
        op="data", seq=1, session_id=SESSION_ID, payload=b"abc"
    )
    with pytest.raises(SessionProtocolError):
        decode_session_frame(frame + b"x")


def test_header_model_rejects_bad_session_id():
    with pytest.raises(ValidationError):
        SessionFrameHeaderV1(
            schema_version=1,
            op="data",
            seq=0,
            session_id="bad",
            payload_kind="utf8",
            payload_length=0,
        )


def test_provider_declaration_valid():
    declaration = provider_declaration(
        provider_id="org.example.echo",
        contract_version="1.0",
        capability_ids=["org.example.echo"],
        control_actions=["resize"],
    )
    assert declaration["provider_id"] == "org.example.echo"
    assert declaration["session_contract"]["contract"] == SESSION_CONTRACT


def test_provider_declaration_rejects_bad_provider():
    with pytest.raises(SessionProtocolError):
        provider_declaration(
            provider_id="Bad",
            contract_version="1.0",
            capability_ids=["org.example.echo"],
        )


def test_provider_declaration_rejects_bad_contract_version():
    with pytest.raises(SessionProtocolError):
        provider_declaration(
            provider_id="org.example.echo",
            contract_version="latest",
            capability_ids=["org.example.echo"],
        )


def test_provider_declaration_rejects_duplicate_capabilities():
    with pytest.raises(SessionProtocolError):
        provider_declaration(
            provider_id="org.example.echo",
            contract_version="1.0",
            capability_ids=["org.example.echo", "org.example.echo"],
        )


def test_provider_declaration_rejects_empty_capabilities():
    with pytest.raises(SessionProtocolError):
        provider_declaration(
            provider_id="org.example.echo", contract_version="1.0", capability_ids=[]
        )
