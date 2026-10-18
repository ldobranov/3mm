"""M21 local session gateway (WP2 live): composition root for the WebSocket.

Owns the one-time ticket store, the bounded local session manager and the
remote session router, registers the reference providers, and exposes the
session operations keyed by the authenticated user id. The ASGI/WebSocket
route is a thin adapter over this service; the service itself performs no
socket I/O, so it is unit-testable.

Routing: a session request for a device with a connected transport (the local
Agent or a remote Node) is routed through the ``RemoteSessionRouter``; anything
else is served by the local manager's providers. Routed sessions keep their
own user binding so a foreign user cannot use them.

Wire protocol (browser <-> Core):

- Control/lifecycle messages are JSON text frames:
  ``{"op": "open", "request": {...}}`` -> ``{"op": "opened", "acceptance": {...}}``
  ``{"op": "control", "control": {...}}`` -> ``{"op": "ok"}``
  ``{"op": "detach"|"attach"|"close"|"terminate", "session_id": "ses_..."}``
  ``{"op": "status", "session_id": "ses_..."}`` -> ``{"op": "status", "status": {...}}``
  errors -> ``{"op": "error", "detail": "..."}``
- Data is a binary frame (``encode_session_frame``/``decode_session_frame``) with
  ``op="data"`` and a real ``session_id``. PTY data never uses the JSON queue.

The ticket is redeemed exactly once at connect time; every operation re-checks
the resolved user id, so knowing a ``session_id`` grants nothing.
"""

from __future__ import annotations

import json

from backend.services.interactive_session_transport import (
    RemoteSessionError,
    RemoteSessionRouter,
)
from backend.services.interactive_sessions import (
    EchoSessionProvider,
    InteractiveSessionError,
    LocalSessionManager,
    SessionTicketIssue,
    SessionTicketStore,
)
from three_mm_protocol.interactive_session import (
    MAX_SESSION_PAYLOAD_BYTES,
    SessionControlV1,
    SessionOpenAcceptanceV1,
    SessionOpenRequestV1,
    SessionStatusV1,
    decode_session_frame,
    encode_session_frame,
)

MAX_CONTROL_MESSAGE_BYTES = 64 * 1024
_LIFECYCLE_OPS = {"detach", "attach", "close", "terminate"}


class SessionGatewayError(RuntimeError):
    """A gateway message is malformed or unauthorized."""


class SessionGateway:
    """Composition root for local interactive sessions over one WebSocket."""

    def __init__(
        self,
        *,
        ticket_store: SessionTicketStore | None = None,
        manager: LocalSessionManager | None = None,
        router: RemoteSessionRouter | None = None,
    ) -> None:
        self.tickets = ticket_store or SessionTicketStore()
        self.manager = manager or LocalSessionManager()
        self.manager.register_provider(EchoSessionProvider())
        self.router = router or RemoteSessionRouter()
        # Routed (Agent/Node) sessions keep their own user binding.
        self._routed: dict[str, int] = {}

    def issue_ticket(self, user_id: int) -> SessionTicketIssue:
        return self.tickets.issue(user_id)

    def redeem(self, ticket: str) -> int:
        return self.tickets.redeem(ticket)

    def _require_routed_user(self, session_id: str, user_id: int) -> None:
        owner = self._routed.get(session_id)
        if owner is not None and owner != user_id:
            raise SessionGatewayError("Session does not belong to this user")

    async def open(
        self, user_id: int, request: SessionOpenRequestV1
    ) -> SessionOpenAcceptanceV1:
        if self.router.offers(request.device_id, request.capability_id):
            try:
                acceptance = await self.router.open(request)
            except RemoteSessionError as exc:
                raise SessionGatewayError(str(exc)) from exc
            self._routed[acceptance.session_id] = user_id
            return acceptance
        return await self.manager.open(request, user_id=user_id)

    async def deliver(self, user_id: int, session_id: str, data: bytes) -> bytes:
        if session_id in self._routed:
            self._require_routed_user(session_id, user_id)
            try:
                return await self.router.deliver(session_id, data)
            except RemoteSessionError as exc:
                raise SessionGatewayError(str(exc)) from exc
        return await self.manager.deliver(session_id, data, user_id=user_id)

    async def control(self, user_id: int, control: SessionControlV1) -> None:
        if control.session_id in self._routed:
            self._require_routed_user(control.session_id, user_id)
            try:
                await self.router.control(
                    control.session_id,
                    {"action": control.action, "arguments": control.arguments},
                )
            except RemoteSessionError as exc:
                raise SessionGatewayError(str(exc)) from exc
            return
        await self.manager.control(
            control.session_id,
            {"action": control.action, "arguments": control.arguments},
            user_id=user_id,
        )

    async def status(self, user_id: int, session_id: str) -> SessionStatusV1:
        if session_id in self._routed:
            self._require_routed_user(session_id, user_id)
            try:
                return self.router.status(session_id)
            except RemoteSessionError as exc:
                raise SessionGatewayError(str(exc)) from exc
        return await self.manager.status(session_id, user_id=user_id)

    async def detach(self, user_id: int, session_id: str) -> None:
        if session_id in self._routed:
            raise SessionGatewayError(
                "Detach is not supported for agent-hosted sessions"
            )
        await self.manager.detach(session_id, user_id=user_id)

    async def attach(self, user_id: int, session_id: str) -> None:
        if session_id in self._routed:
            raise SessionGatewayError(
                "Attach is not supported for agent-hosted sessions"
            )
        await self.manager.attach(session_id, user_id=user_id)

    async def close(self, user_id: int, session_id: str) -> None:
        if session_id in self._routed:
            self._require_routed_user(session_id, user_id)
            try:
                await self.router.close(session_id, "closed")
            except RemoteSessionError as exc:
                raise SessionGatewayError(str(exc)) from exc
            self._routed.pop(session_id, None)
            return
        await self.manager.close(session_id, user_id=user_id)

    async def terminate(self, user_id: int, session_id: str) -> None:
        if session_id in self._routed:
            self._require_routed_user(session_id, user_id)
            try:
                await self.router.close(session_id, "terminated")
            except RemoteSessionError as exc:
                raise SessionGatewayError(str(exc)) from exc
            self._routed.pop(session_id, None)
            return
        await self.manager.terminate(session_id, user_id=user_id)

    async def handle_text(self, user_id: int, raw: str) -> str:
        """Handle one JSON control message; return the JSON response text."""
        if len(raw.encode("utf-8")) > MAX_CONTROL_MESSAGE_BYTES:
            raise SessionGatewayError("Control message is too large")
        try:
            message = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise SessionGatewayError("Control message is not valid JSON") from exc
        if not isinstance(message, dict):
            raise SessionGatewayError("Control message must be an object")
        op = message.get("op")
        try:
            if op == "open":
                request = SessionOpenRequestV1.model_validate(message.get("request"))
                acceptance = await self.open(user_id, request)
                return json.dumps(
                    {"op": "opened", "acceptance": acceptance.model_dump(mode="json")}
                )
            if op == "control":
                control = SessionControlV1.model_validate(message.get("control"))
                await self.control(user_id, control)
                return json.dumps({"op": "ok"})
            if op == "status":
                status = await self.status(user_id, str(message.get("session_id")))
                return json.dumps(
                    {"op": "status", "status": status.model_dump(mode="json")}
                )
            if op in _LIFECYCLE_OPS:
                session_id = str(message.get("session_id"))
                await getattr(self, op)(user_id, session_id)
                return json.dumps({"op": "ok"})
        except (InteractiveSessionError, ValueError) as exc:
            raise SessionGatewayError(str(exc)) from exc
        raise SessionGatewayError(f"Unsupported control op: {op!r}")

    async def handle_binary(self, user_id: int, raw: bytes) -> bytes:
        """Handle one binary data frame; return the outbound data frame bytes."""
        try:
            header, payload = decode_session_frame(raw)
        except ValueError as exc:
            raise SessionGatewayError(str(exc)) from exc
        if header.op != "data":
            raise SessionGatewayError("Binary frames must use the data op")
        try:
            outbound = await self.deliver(user_id, header.session_id, payload)
            if type(outbound) is not bytes or len(outbound) > MAX_SESSION_PAYLOAD_BYTES:
                raise SessionGatewayError("Session provider output exceeds frame bounds")
            return encode_session_frame(
                op="data",
                seq=header.seq,
                session_id=header.session_id,
                payload=outbound,
                payload_kind="binary",
            )
        except (InteractiveSessionError, ValueError) as exc:
            raise SessionGatewayError(str(exc)) from exc


_GATEWAY: SessionGateway | None = None


def get_session_gateway() -> SessionGateway:
    """Process-wide gateway; providers are registered once at first use."""
    global _GATEWAY
    if _GATEWAY is None:
        _GATEWAY = SessionGateway()
    return _GATEWAY


__all__ = [
    "MAX_CONTROL_MESSAGE_BYTES",
    "SessionGatewayError",
    "SessionGateway",
    "get_session_gateway",
]
