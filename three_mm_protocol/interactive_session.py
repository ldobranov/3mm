"""M21 interactive session contracts; validation, not a live gateway.

Transport-neutral models and a pure lifecycle state machine. There is no socket,
WebSocket, authorization, process execution or device routing here. Callers opt
into these contracts explicitly; existing C10/C11 command contracts are unchanged.

Independent version axes: ``interactive-session.v1`` is not Module Manifest v2,
not Application SDK 1.3, and not the ``application-extension.v1`` descriptor.
"""

from __future__ import annotations

import json
import re
import struct
from datetime import datetime
from typing import ClassVar, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from three_mm_protocol.module_manifest import MODULE_ID_PATTERN
from three_mm_protocol.node_security import NODE_MESSAGE_BYTES, validate_node_json
from three_mm_protocol.runtime_extension import IDENTIFIER_PATTERN

SESSION_CONTRACT = "interactive-session.v1"
SESSION_PROTOCOL_VERSION = 1

SESSION_ID_PATTERN = r"^ses_[0-9a-f]{32}$"
DEVICE_ID_PATTERN = r"^dev_[0-9a-f]{32}$"
SESSION_CAPABILITY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$"
SESSION_CONTROL_ACTION_PATTERN = r"^[a-z][a-z0-9_.-]{0,63}$"
SESSION_CONTRACT_VERSION_PATTERN = r"^[1-9][0-9]{0,3}\.[0-9]{1,4}$"

SESSION_OPS = (
    "open",
    "attach",
    "data",
    "control",
    "detach",
    "close",
    "status",
    "terminate",
)
SessionOp = Literal[
    "open", "attach", "data", "control", "detach", "close", "status", "terminate"
]

SESSION_STATES = ("requested", "active", "detached", "closed", "terminated", "error")
SessionState = Literal[
    "requested", "active", "detached", "closed", "terminated", "error"
]
TERMINAL_SESSION_STATES = frozenset({"closed", "terminated", "error"})

AccessMode = Literal["read", "write"]

# Resource defaults; configurable through common policy, never a terminal constant.
DEFAULT_IDLE_TIMEOUT_SECONDS = 900
DEFAULT_SESSION_MAX_LIFETIME_SECONDS = 14400
DEFAULT_SESSION_BUFFER_BYTES = 65536
MAX_ACTIVE_SESSIONS_ZERO_W = 1
MAX_ACTIVE_SESSIONS_HUB = 4

FRAME_MAGIC = b"3MMS"
MAX_SESSION_FRAME_BYTES = NODE_MESSAGE_BYTES
MAX_SESSION_PAYLOAD_BYTES = MAX_SESSION_FRAME_BYTES - 258
FramePayloadKind = Literal["utf8", "binary"]


class SessionProtocolError(ValueError):
    """A session model, frame or lifecycle transition violates the contract."""


_TRANSITIONS: dict[tuple[SessionState, str], SessionState] = {
    ("requested", "open_accepted"): "active",
    ("requested", "open_rejected"): "error",
    ("active", "detach"): "detached",
    ("detached", "attach"): "active",
    ("active", "close"): "closed",
    ("detached", "close"): "closed",
    ("active", "fail"): "error",
    ("detached", "fail"): "error",
}


def is_terminal_session_state(state: str) -> bool:
    return state in TERMINAL_SESSION_STATES


def advance_session_state(current: str, transition: str) -> str:
    """Return the next state or raise. Pure; no I/O and no replay semantics."""
    if current not in SESSION_STATES:
        raise SessionProtocolError(f"Unknown session state: {current!r}")
    if transition == "terminate":
        if is_terminal_session_state(current):
            raise SessionProtocolError("Cannot terminate an already terminated session")
        return "terminated"
    target = _TRANSITIONS.get((current, transition))
    if target is None:
        raise SessionProtocolError(
            f"Session transition {transition!r} is invalid from {current!r}"
        )
    return target


def _aware_datetime(value: object) -> AwareDatetime:
    """Accept a datetime or an ISO 8601 string so JSON round-trips work."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Session timestamp is invalid") from exc
    else:
        raise ValueError("Session timestamps must be datetime or ISO 8601 strings")
    if parsed.tzinfo is None:
        raise ValueError("Session timestamps require a timezone")
    return parsed


class SessionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    _message_bytes_limit: ClassVar[int] = NODE_MESSAGE_BYTES

    @field_validator(
        "session_request_version",
        "schema_version",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def exact_integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("Session version must be an integer")
        return value

    @model_validator(mode="after")
    def bounded(self):
        validate_node_json(
            self.model_dump(mode="json"), max_bytes=self._message_bytes_limit
        )
        return self


class SessionOpenRequestV1(SessionModel):
    session_request_version: Literal[1] = 1
    request_id: str = Field(pattern=IDENTIFIER_PATTERN)
    provider_id: str = Field(pattern=MODULE_ID_PATTERN)
    capability_id: str = Field(pattern=SESSION_CAPABILITY_PATTERN)
    device_id: str = Field(pattern=DEVICE_ID_PATTERN)
    access_mode: AccessMode = "read"
    options: dict[str, object] = Field(default_factory=dict)

    @field_validator("options")
    @classmethod
    def bounded_options(cls, value):
        validate_node_json(value, max_bytes=NODE_MESSAGE_BYTES // 2)
        return value


class SessionOpenAcceptanceV1(SessionModel):
    session_request_version: Literal[1] = 1
    request_id: str = Field(pattern=IDENTIFIER_PATTERN)
    session_id: str = Field(pattern=SESSION_ID_PATTERN)
    state: Literal["active"] = "active"
    provider_id: str = Field(pattern=MODULE_ID_PATTERN)
    capability_id: str = Field(pattern=SESSION_CAPABILITY_PATTERN)
    device_id: str = Field(pattern=DEVICE_ID_PATTERN)
    created_at: AwareDatetime
    expires_at: AwareDatetime

    @field_validator("created_at", "expires_at", mode="before")
    @classmethod
    def normalize_timestamps(cls, value):
        return _aware_datetime(value)

    @model_validator(mode="after")
    def valid_lifetime(self):
        if self.expires_at <= self.created_at:
            raise ValueError("Session expiry must follow creation")
        return self


class SessionStatusV1(SessionModel):
    session_id: str = Field(pattern=SESSION_ID_PATTERN)
    state: SessionState
    device_id: str = Field(pattern=DEVICE_ID_PATTERN)
    provider_id: str = Field(pattern=MODULE_ID_PATTERN)
    created_at: AwareDatetime
    expires_at: AwareDatetime

    @field_validator("created_at", "expires_at", mode="before")
    @classmethod
    def normalize_timestamps(cls, value):
        return _aware_datetime(value)

    @model_validator(mode="after")
    def valid_lifetime(self):
        if self.expires_at <= self.created_at:
            raise ValueError("Session expiry must follow creation")
        return self


class SessionControlV1(SessionModel):
    session_id: str = Field(pattern=SESSION_ID_PATTERN)
    control_id: str = Field(pattern=IDENTIFIER_PATTERN)
    action: str = Field(pattern=SESSION_CONTROL_ACTION_PATTERN)
    arguments: dict[str, object] = Field(default_factory=dict)

    @field_validator("arguments")
    @classmethod
    def bounded_arguments(cls, value):
        validate_node_json(value, max_bytes=NODE_MESSAGE_BYTES // 2)
        return value


class SessionTargetV1(SessionModel):
    """One device that may offer interactive sessions to the current user.

    ``available`` is reported separately from the presence of an installed
    provider: an offline device can be listed but must not be offered as a
    working session. ``sessions`` lists capability ids, never terminal names.
    """

    device_id: str = Field(pattern=DEVICE_ID_PATTERN)
    display_name: str = Field(min_length=1, max_length=160)
    local: bool = False
    sessions: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    available: bool = False
    unavailable_reason: str | None = Field(default=None, max_length=64)

    @field_validator("sessions")
    @classmethod
    def bounded_sessions(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Session target capabilities must be unique")
        for item in value:
            if not re.fullmatch(SESSION_CAPABILITY_PATTERN, item):
                raise ValueError("Session target capability id is invalid")
        return value


class SessionDiscoveryV1(SessionModel):
    schema_version: Literal[1] = 1
    targets: tuple[SessionTargetV1, ...] = Field(default_factory=tuple, max_length=256)

    @field_validator("targets")
    @classmethod
    def unique_targets(cls, value):
        ids = [item.device_id for item in value]
        if len(set(ids)) != len(ids):
            raise ValueError("Session discovery targets must be unique")
        return value


class SessionFrameHeaderV1(BaseModel):
    """Metadata carried by one bidirectional, ordered, bounded frame.

    The frame is transport-neutral: a WebSocket is one possible transport, not
    the only one. PTY data must use data frames, never the C10/C11 JSON queue.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    op: SessionOp
    seq: int = Field(ge=0, le=2**32 - 1)
    session_id: str = Field(pattern=SESSION_ID_PATTERN)
    payload_kind: FramePayloadKind = "utf8"
    payload_length: int = Field(ge=0, le=MAX_SESSION_PAYLOAD_BYTES)


def _encode_frame_header(header: dict[str, object]) -> bytes:
    header_bytes = json.dumps(
        header, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if len(header_bytes) > (MAX_SESSION_FRAME_BYTES - MAX_SESSION_PAYLOAD_BYTES):
        raise SessionProtocolError("Session frame header is too large")
    return header_bytes


def encode_session_frame(
    *,
    op: str,
    seq: int,
    session_id: str,
    payload: bytes = b"",
    payload_kind: str = "utf8",
) -> bytes:
    """Encode one binary session frame. Returns the exact bytes to send."""
    if op not in SESSION_OPS:
        raise SessionProtocolError(f"Unknown session op: {op!r}")
    if payload_kind == "utf8":
        try:
            payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SessionProtocolError(
                "UTF-8 frame payload is not valid UTF-8"
            ) from exc
    elif payload_kind != "binary":
        raise SessionProtocolError("Session payload kind must be utf8 or binary")
    if len(payload) > MAX_SESSION_PAYLOAD_BYTES:
        raise SessionProtocolError("Session frame payload exceeds the bound")

    header = SessionFrameHeaderV1(
        schema_version=1,
        op=op,
        seq=seq,
        session_id=session_id,
        payload_kind=payload_kind,
        payload_length=len(payload),
    )
    header_bytes = _encode_frame_header(header.model_dump(mode="json"))
    frame = (
        FRAME_MAGIC
        + struct.pack(">BI", 1, len(header_bytes))
        + header_bytes
        + payload
    )
    if len(frame) > MAX_SESSION_FRAME_BYTES:
        raise SessionProtocolError("Session frame exceeds the total bound")
    return frame


def decode_session_frame(data: bytes) -> tuple[SessionFrameHeaderV1, bytes]:
    """Decode and validate one frame. Raises on malformed/fail-closed input."""
    if not isinstance(data, (bytes, bytearray)) or len(data) > MAX_SESSION_FRAME_BYTES:
        raise SessionProtocolError("Session frame is invalid or too large")
    raw = bytes(data)
    if len(raw) < 9 or raw[:4] != FRAME_MAGIC:
        raise SessionProtocolError("Session frame magic is invalid")
    version, header_length = struct.unpack(">BI", raw[4:9])
    if version != 1:
        raise SessionProtocolError("Session frame version is unsupported")
    if header_length < 2 or 9 + header_length > len(raw):
        raise SessionProtocolError("Session frame header length is invalid")
    header_bytes = raw[9 : 9 + header_length]
    try:
        parsed = json.loads(header_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SessionProtocolError("Session frame header is invalid") from exc
    try:
        header = SessionFrameHeaderV1.model_validate(parsed)
    except ValueError as exc:
        raise SessionProtocolError("Session frame header is invalid") from exc
    payload = raw[9 + header_length :]
    if len(payload) != header.payload_length:
        raise SessionProtocolError("Session frame payload length does not match")
    if header.payload_kind == "utf8":
        try:
            payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SessionProtocolError("Session UTF-8 payload is invalid") from exc
    return header, payload


def provider_declaration(
    *,
    provider_id: str,
    contract_version: str,
    capability_ids: list[str] | tuple[str, ...],
    control_actions: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    """Shape a provider declaration for validation; not an applied grant.

    The returned dictionary is descriptive metadata for M20 review, never a
    durable authority or an installed-runtime claim on its own.
    """
    if not re.fullmatch(MODULE_ID_PATTERN, provider_id):
        raise SessionProtocolError("Session provider id is invalid")
    if not re.fullmatch(SESSION_CONTRACT_VERSION_PATTERN, contract_version):
        raise SessionProtocolError("Session contract version is invalid")
    if not capability_ids or any(
        not re.fullmatch(SESSION_CAPABILITY_PATTERN, item) for item in capability_ids
    ):
        raise SessionProtocolError("Session provider capabilities are invalid")
    if len(set(capability_ids)) != len(capability_ids):
        raise SessionProtocolError("Session provider capabilities must be unique")
    if any(
        not re.fullmatch(SESSION_CONTROL_ACTION_PATTERN, item)
        for item in control_actions
    ):
        raise SessionProtocolError("Session control actions are invalid")
    session_contract = {
        "contract": SESSION_CONTRACT,
        "contract_version": contract_version,
        "capability_ids": list(capability_ids),
        "control_actions": list(control_actions),
    }
    return {
        "provider_id": provider_id,
        "session_contract": session_contract,
    }


__all__ = [
    "SESSION_CONTRACT",
    "SESSION_PROTOCOL_VERSION",
    "SESSION_ID_PATTERN",
    "DEVICE_ID_PATTERN",
    "SESSION_CAPABILITY_PATTERN",
    "SESSION_CONTRACT_VERSION_PATTERN",
    "SESSION_OPS",
    "SESSION_STATES",
    "TERMINAL_SESSION_STATES",
    "DEFAULT_IDLE_TIMEOUT_SECONDS",
    "DEFAULT_SESSION_MAX_LIFETIME_SECONDS",
    "DEFAULT_SESSION_BUFFER_BYTES",
    "MAX_ACTIVE_SESSIONS_ZERO_W",
    "MAX_ACTIVE_SESSIONS_HUB",
    "MAX_SESSION_FRAME_BYTES",
    "MAX_SESSION_PAYLOAD_BYTES",
    "SessionProtocolError",
    "SessionOp",
    "SessionState",
    "AccessMode",
    "FramePayloadKind",
    "is_terminal_session_state",
    "advance_session_state",
    "SessionOpenRequestV1",
    "SessionOpenAcceptanceV1",
    "SessionStatusV1",
    "SessionControlV1",
    "SessionTargetV1",
    "SessionDiscoveryV1",
    "SessionFrameHeaderV1",
    "encode_session_frame",
    "decode_session_frame",
    "provider_declaration",
]
