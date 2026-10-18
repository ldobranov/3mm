"""M21 Agent-side session transport handler (WP2 live remainder).

Serves Core->Agent session operations over the device WebSocket. This module
is the protocol handler only: it is transport-agnostic and unit-testable. A
production connector opens the WebSocket (device ticket from
``POST /api/v1/devices/{id}/session-ticket``), sends the hello declaration and
then pumps ``handle_text``/``handle_binary``; it needs a WebSocket client
library (``websockets``), which is a deployment dependency, not a contract one.

Protocol (Core -> Agent -> Core), every response carries its correlation key:

- ``{"op":"open","request":{...}}`` -> ``{"op":"opened","key":"open:{id}",...}``
- binary data frame -> binary data frame with the same session_id/seq
- ``{"op":"control","control":{...}}`` -> ``{"op":"ok","key":"ctl:{id}"}``
- ``{"op":"close","session_id":...}`` -> ``{"op":"ok","key":"close:{id}"}``
- errors -> ``{"op":"error","key":...,"detail":...}``

The Agent hosts providers implementing the public SDK ``SessionProvider``
contract; it binds no process and performs no OS isolation.
"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    # The minimal Node ships Agent + protocol, not the Core application SDK.
    # This protocol is used only in postponed annotations, never at runtime.
    from three_mm_application_sdk.session import SessionProvider
from three_mm_protocol.interactive_session import (
    SessionControlV1,
    SessionOpenAcceptanceV1,
    SessionOpenRequestV1,
    decode_session_frame,
    encode_session_frame,
)

AGENT_SESSION_TTL_SECONDS = 14400


class AgentSessionTransportError(RuntimeError):
    """A Core->Agent session operation cannot be served."""


class AgentSessionHost:
    """Serves Core session operations against locally registered providers."""

    def __init__(self) -> None:
        self._providers: dict[str, SessionProvider] = {}
        self._sessions: dict[str, str] = {}  # session_id -> provider_id

    def register_provider(self, provider: SessionProvider) -> None:
        if provider.provider_id in self._providers:
            raise AgentSessionTransportError("Provider is already registered")
        self._providers[provider.provider_id] = provider

    def capability_ids(self) -> list[str]:
        return sorted(
            {
                capability_id
                for provider in self._providers.values()
                for capability_id in provider.capability_ids
            }
        )

    def hello(self, display_name: str) -> str:
        return json.dumps(
            {
                "op": "hello",
                "display_name": display_name,
                "capability_ids": self.capability_ids(),
            }
        )

    def _provider(self, request: SessionOpenRequestV1) -> SessionProvider:
        provider = self._providers.get(request.provider_id)
        if provider is None or request.capability_id not in provider.capability_ids:
            raise AgentSessionTransportError("Session provider is unavailable")
        return provider

    async def handle_text(self, raw: str) -> str:
        """Serve one Core JSON operation; return the JSON response text."""
        try:
            message = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise AgentSessionTransportError("Message is not valid JSON") from exc
        if not isinstance(message, dict):
            raise AgentSessionTransportError("Message must be an object")
        op = message.get("op")
        try:
            if op == "open":
                request = SessionOpenRequestV1.model_validate(message.get("request"))
                provider = self._provider(request)
                session_id = "ses_" + secrets.token_hex(16)
                now = datetime.now(UTC)
                await provider.open(
                    {
                        "session_id": session_id,
                        "device_id": request.device_id,
                        "capability_id": request.capability_id,
                        "access_mode": request.access_mode,
                        "options": request.options,
                    }
                )
                self._sessions[session_id] = request.provider_id
                acceptance = SessionOpenAcceptanceV1(
                    session_request_version=1,
                    request_id=request.request_id,
                    session_id=session_id,
                    state="active",
                    provider_id=request.provider_id,
                    capability_id=request.capability_id,
                    device_id=request.device_id,
                    created_at=now,
                    expires_at=now + timedelta(seconds=AGENT_SESSION_TTL_SECONDS),
                )
                return json.dumps(
                    {
                        "op": "opened",
                        "key": f"open:{request.request_id}",
                        "acceptance": acceptance.model_dump(mode="json"),
                    }
                )
            if op == "control":
                control = SessionControlV1.model_validate(message.get("control"))
                session_id = control.session_id
                provider = self._session_provider(session_id)
                await provider.control(session_id, {
                    "action": control.action, "arguments": control.arguments,
                })
                return json.dumps(
                    {"op": "ok", "key": f"ctl:{control.control_id}"}
                )
            if op == "close":
                session_id = str(message.get("session_id"))
                provider = self._session_provider(session_id)
                await provider.close(session_id, str(message.get("reason") or "closed"))
                self._sessions.pop(session_id, None)
                return json.dumps({"op": "ok", "key": f"close:{session_id}"})
        except (AgentSessionTransportError, ValueError) as exc:
            return json.dumps({"op": "error", "detail": str(exc)})
        raise AgentSessionTransportError(f"Unsupported agent op: {op!r}")

    def _session_provider(self, session_id: str) -> SessionProvider:
        provider_id = self._sessions.get(session_id)
        if provider_id is None:
            raise AgentSessionTransportError("Session is unknown on this agent")
        provider = self._providers.get(provider_id)
        if provider is None:
            raise AgentSessionTransportError("Session provider was removed")
        return provider

    async def handle_binary(self, raw: bytes) -> bytes:
        """Serve one Core binary data frame; return the outbound frame."""
        try:
            header, payload = decode_session_frame(raw)
        except ValueError as exc:
            raise AgentSessionTransportError(str(exc)) from exc
        if header.op != "data":
            raise AgentSessionTransportError("Binary frames must use the data op")
        provider = self._session_provider(header.session_id)
        outbound = await provider.receive(header.session_id, payload)
        return encode_session_frame(
            op="data",
            seq=header.seq,
            session_id=header.session_id,
            payload=outbound,
            payload_kind="binary",
        )


__all__ = [
    "AgentSessionTransportError",
    "AgentSessionHost",
]
